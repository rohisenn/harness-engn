"""
Multi-Agent Collaboration module for harness.

Coordinates specialized Researcher, Planner, Coder, and QA Agents to complete tasks.
"""

from __future__ import annotations

import os
import re
import sys
import subprocess
import click
from rich.panel import Panel
from rich.markdown import Markdown

from agent.config import Config
from agent.llm import LLMClient
from agent.memory import load_facts, save_session, generate_session_id
from agent.context import maybe_compress
from agent.prompts import (
    RESEARCHER_SYSTEM_PROMPT,
    CODER_SYSTEM_PROMPT,
    QA_SYSTEM_PROMPT,
)
from agent.planning_prompts import PLANNING_SYSTEM_PROMPT
from tools import run_tool


def get_multi_agent_system_prompt(base_prompt: str) -> str:
    """Prepend persistent repository facts/memory to the agent's base system prompt."""
    facts = load_facts()
    if not facts:
        return base_prompt
    facts_block = "\n[Repository Facts/Memory]:\n" + "\n".join(f"- {f}" for f in facts) + "\n"
    intro_end = base_prompt.find("\n")
    if intro_end != -1:
        return base_prompt[:intro_end] + "\n" + facts_block + base_prompt[intro_end:]
    return base_prompt + "\n" + facts_block


def run_agent_loop(
    client: LLMClient,
    system_prompt: str,
    messages: list[dict[str, str]],
    agent_name: str,
    session_id: str,
    allowed_tools: list[str] | None = None,
    disallowed_tools: list[str] | None = None,
) -> str:
    """Runs a single agent's execution loop until they finish (i.e. output text with no tool calls)."""
    from main import parse_tool_call, get_console
    console = get_console(client.config)

    while True:
        console.print()
        console.print(f"[bold cyan]{agent_name} is thinking...[/bold cyan]")
        
        messages, compressed = maybe_compress(client, messages, client.config.context_window, client.config.compress_tail)
        if compressed:
            console.print("[dim]Context compressed.[/dim]")

        system = get_multi_agent_system_prompt(system_prompt)
        chunks = list(client.stream(system=system, messages=messages))
        response = "".join(chunks)

        tool_info = parse_tool_call(response)
        if tool_info:
            tool_name, tool_args = tool_info
            
            # Check tool permissions for the agent
            if allowed_tools is not None and tool_name not in allowed_tools:
                error_msg = f"Error: The tool '{tool_name}' is disabled for the {agent_name} Agent."
                console.print(f"[bold red]{error_msg}[/bold red]")
                messages.append({"role": "assistant", "content": response})
                messages.append({"role": "user", "content": error_msg})
                save_session(session_id, messages)
                continue

            if disallowed_tools is not None and tool_name in disallowed_tools:
                error_msg = f"Error: The tool '{tool_name}' is disabled for the {agent_name} Agent."
                console.print(f"[bold red]{error_msg}[/bold red]")
                messages.append({"role": "assistant", "content": response})
                messages.append({"role": "user", "content": error_msg})
                save_session(session_id, messages)
                continue

            console.print(f"[bold yellow]{agent_name} Tool Call:[/bold yellow] `{tool_name}` with args {tool_args}")
            if click.confirm("Do you want to execute this tool call?", default=True):
                result = run_tool(tool_name, **tool_args)
                console.print(f"[bold green]Tool Output (first 100 chars):[/bold green]\n{result[:100]}...")
                messages.append({"role": "assistant", "content": response})
                messages.append({"role": "user", "content": f"[Tool Output for {tool_name}]:\n{result}"})
                save_session(session_id, messages)
            else:
                console.print(f"[yellow]Tool execution cancelled by user. Terminating {agent_name} loop.[/yellow]")
                raise RuntimeError(f"Tool execution cancelled by the user during {agent_name} phase.")
        else:
            console.print(Panel(Markdown(response), title=agent_name, border_style="cyan"))
            messages.append({"role": "assistant", "content": response})
            save_session(session_id, messages)
            return response


def run_multi_agent_session(
    client: LLMClient,
    task: str,
    session_id: str | None = None,
    initial_history: list[dict[str, str]] | None = None,
) -> str:
    """Runs the full multi-agent workflow: Researcher -> Planner -> Coder -> QA Agent."""
    from main import get_console, handle_git_success
    console = get_console(client.config)

    if session_id is None:
        session_id = generate_session_id()
    if initial_history is None:
        messages = [{"role": "user", "content": task}]
    else:
        messages = list(initial_history)
        if not any(msg["role"] == "user" and msg["content"] == task for msg in messages):
            messages.append({"role": "user", "content": task})

    save_session(session_id, messages)

    console.print(Panel("[bold green]Starting Multi-Agent Collaboration Workflow[/bold green]", border_style="green"))

    # ==========================================
    # 1. RESEARCH PHASE
    # ==========================================
    console.print("\n[bold magenta]=== PHASE 1: Codebase Research ===[/bold magenta]")
    research_history = list(messages)
    context_report = run_agent_loop(
        client=client,
        system_prompt=RESEARCHER_SYSTEM_PROMPT,
        messages=research_history,
        agent_name="Researcher",
        session_id=session_id,
        disallowed_tools=["edit_file", "run_command"],
    )

    # Add the researcher's context report back to the main history
    messages.append({
        "role": "user",
        "content": f"[Researcher Context Report]:\n{context_report}\n\nPlease proceed to generate the plan."
    })
    save_session(session_id, messages)

    # ==========================================
    # 2. PLANNING PHASE
    # ==========================================
    console.print("\n[bold magenta]=== PHASE 2: Implementation Planning ===[/bold magenta]")
    if os.path.exists("plan.md"):
        try:
            os.remove("plan.md")
        except Exception:
            pass

    planner_history = list(messages)
    while True:
        run_agent_loop(
            client=client,
            system_prompt=PLANNING_SYSTEM_PROMPT,
            messages=planner_history,
            agent_name="Planner",
            session_id=session_id,
            allowed_tools=["list_dir", "view_file", "search_files", "search_grep", "write_file", "remember_fact", "forget_fact", "list_facts"],
        )

        if os.path.exists("plan.md"):
            try:
                with open("plan.md", "r", encoding="utf-8") as f:
                    plan_content = f.read()
            except Exception as e:
                plan_content = f"Error reading plan.md: {e}"

            console.print()
            console.print(Panel(Markdown(plan_content), title="plan.md", border_style="yellow"))

            if click.confirm("Do you approve this plan?", default=True):
                console.print("[bold green]Plan approved. Transitioning to Coder/Execution Phase...[/bold green]")
                break
            else:
                feedback = click.prompt("Provide feedback/adjustments to the plan")
                planner_history.append({
                    "role": "user",
                    "content": f"The user rejected the plan. Feedback:\n{feedback}\nPlease update 'plan.md' to reflect this feedback."
                })
                save_session(session_id, planner_history)
        else:
            prompt_msg = "Please write the proposed implementation plan to 'plan.md' using the write_file tool."
            planner_history.append({"role": "user", "content": prompt_msg})
            save_session(session_id, planner_history)

    # Update main messages with the approved plan
    messages.append({"role": "user", "content": "The plan has been approved. Please execute the plan now."})
    save_session(session_id, messages)

    # ==========================================
    # 3. CODING/EXECUTION PHASE
    # ==========================================
    console.print("\n[bold magenta]=== PHASE 3: Code Implementation ===[/bold magenta]")
    coder_history = list(messages)
    coder_summary = run_agent_loop(
        client=client,
        system_prompt=CODER_SYSTEM_PROMPT,
        messages=coder_history,
        agent_name="Coder",
        session_id=session_id,
        disallowed_tools=["run_command"],
    )

    # Update main messages with coder summary
    messages.append({
        "role": "user",
        "content": f"[Coder Completion Summary]:\n{coder_summary}\n\nPlease proceed to verification."
    })
    save_session(session_id, messages)

    # ==========================================
    # 4. QA/VERIFICATION & CORRECTION PHASE
    # ==========================================
    console.print("\n[bold magenta]=== PHASE 4: QA & Verification ===[/bold magenta]")
    verify_commands = []
    if client.config.verify_cmd:
        verify_commands = [client.config.verify_cmd]
    elif os.path.exists("plan.md"):
        try:
            with open("plan.md", "r", encoding="utf-8") as f:
                plan_content = f.read()
            from agent.correction import extract_verification_commands
            verify_commands = extract_verification_commands(plan_content)
        except Exception as e:
            console.print(f"[bold red]Failed to read plan.md or extract verification commands: {e}[/bold red]")

    if not verify_commands:
        console.print("[yellow]No verification commands specified or found in plan.md. Skipping verification.[/yellow]")
        if client.config.git_integration:
            handle_git_success(client, console)
        return "Task completed. Verification skipped."

    from agent.correction import run_verification_command, get_correction_prompt

    qa_history = list(messages)
    correction_attempts = 0
    max_correct = client.config.max_correct

    while True:
        failures = []
        for cmd in verify_commands:
            console.print(f"[bold blue]QA Agent running verification command:[/bold blue] `{cmd}`")
            exit_code, output = run_verification_command(cmd)
            if exit_code != 0:
                failures.append((cmd, exit_code, output))
                console.print(f"[bold red]Verification command '{cmd}' failed (exit code {exit_code}).[/bold red]")
                preview = "\n".join(output.splitlines()[:10])
                console.print(f"[dim]{preview}[/dim]")
                if len(output.splitlines()) > 10:
                    console.print(f"[dim]... ({len(output.splitlines()) - 10} more lines omitted)[/dim]")
            else:
                console.print(f"[bold green]Verification command '{cmd}' succeeded (exit code 0).[/bold green]")

        if not failures:
            console.print("[bold green]QA Agent: All verification commands passed successfully![/bold green]")
            if client.config.git_integration:
                handle_git_success(client, console)
            return "Task completed and verified successfully."

        if correction_attempts >= max_correct:
            console.print(f"[bold red]QA Agent reached maximum correction attempts ({max_correct}). Verification failed.[/bold red]")
            return f"Verification failed after {max_correct} correction attempts. Output of last failure:\n{failures[0][2]}"

        correction_attempts += 1
        prompt = "\n\n".join(get_correction_prompt(cmd, code, out) for cmd, code, out in failures)
        console.print(f"[bold yellow]QA Agent entering self-correction loop (Attempt {correction_attempts}/{max_correct})...[/bold yellow]")

        qa_history.append({"role": "user", "content": prompt})
        save_session(session_id, qa_history)

        # Run correction edits
        run_agent_loop(
            client=client,
            system_prompt=QA_SYSTEM_PROMPT,
            messages=qa_history,
            agent_name="QA_Agent_Correction",
            session_id=session_id,
        )
