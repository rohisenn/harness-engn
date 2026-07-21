"""
harness - an open-source coding agent.

Milestone 1: a CLI that sends a prompt to an LLM and prints the response.

Usage:
    python main.py "Add JWT authentication"
    python main.py "Fix failing tests" --provider openai
    python main.py             # interactive mode, keeps chatting until you exit
"""

from __future__ import annotations

import os
import re
import sys

def init_win_ansi():
    """Enable Virtual Terminal Processing on Windows to support ANSI escape sequences (colors, spinners)."""
    if os.name == "nt":
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            # STD_OUTPUT_HANDLE is -11
            stdout_handle = kernel32.GetStdHandle(-11)
            mode = ctypes.c_ulong()
            if kernel32.GetConsoleMode(stdout_handle, ctypes.byref(mode)):
                # ENABLE_VIRTUAL_TERMINAL_PROCESSING is 0x0004
                kernel32.SetConsoleMode(stdout_handle, mode.value | 0x0004)
        except Exception:
            pass

init_win_ansi()

import click
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from agent.config import load_config, Config
from agent.llm import LLMClient, LLMError
from agent.prompts import SYSTEM_PROMPT
from agent.planning_prompts import PLANNING_SYSTEM_PROMPT, EXECUTION_SYSTEM_PROMPT
from tools import run_tool
from agent.memory import load_facts, save_session, generate_session_id

console = Console()


def get_console(config: Config) -> Console:
    """Returns a Console configured with or without colors depending on config settings."""
    if not config.color:
        return Console(color_system=None, highlight=False)
    return console


def parse_tool_call(response: str) -> tuple[str, dict[str, str]] | None:
    """
    Looks for a <tool_call ...>body</tool_call> or <tool_call ... /> tag in the response.
    Returns (tool_name, attributes_dict) if found, otherwise None.
    Supports attributes in any order, extra spaces, and optional trailing slash.
    """
    # Find the opening tag <tool_call ...>
    match_open = re.search(r'<tool_call\s+([^>]*?)(\/?)>', response, re.DOTALL)
    if not match_open:
        return None

    attributes_str = match_open.group(1)
    is_inline = bool(match_open.group(2))

    # Parse attributes using regex
    attrs = re.findall(r'(\w+)\s*=\s*"([^"]*)"', attributes_str)
    attrs_dict = dict(attrs)

    if "name" not in attrs_dict:
        return None

    tool_name = attrs_dict.pop("name")

    # If it's not inline, look for the closing </tool_call> tag
    if not is_inline:
        start_body_idx = match_open.end()
        match_close = re.search(r'</tool_call>', response[start_body_idx:])
        if match_close:
            end_body_idx = start_body_idx + match_close.start()
            body = response[start_body_idx:end_body_idx]

            if tool_name == "edit_file":
                old_match = re.search(r'<old_content>(.*?)</old_content>', body, re.DOTALL)
                new_match = re.search(r'<new_content>(.*?)</new_content>', body, re.DOTALL)
                if old_match and new_match:
                    return tool_name, {
                        **attrs_dict,
                        "old_content": old_match.group(1),
                        "new_content": new_match.group(1)
                    }
                return None

            elif tool_name == "write_file":
                # Strip initial/final newline immediately adjacent to tag bounds if present
                content = body
                if content.startswith("\n"):
                    content = content[1:]
                if content.endswith("\n"):
                    content = content[:-1]
                return tool_name, {
                    **attrs_dict,
                    "content": content
                }

    # Fallback/Inline behavior
    return tool_name, attrs_dict


def get_system_prompt(base_prompt: str) -> str:
    facts = load_facts()
    if not facts:
        return base_prompt
    facts_block = "\n[Repository Facts/Memory]:\n" + "\n".join(f"- {f}" for f in facts) + "\n"
    intro_end = base_prompt.find("\n")
    if intro_end != -1:
        return base_prompt[:intro_end] + "\n" + facts_block + base_prompt[intro_end:]
    return base_prompt + "\n" + facts_block


def run_single_turn(client: LLMClient, task: str, session_id: str | None = None, initial_history: list[dict[str, str]] | None = None) -> str:
    """Send one task to the model, streaming the response to the terminal, executing tools if requested."""
    if session_id is None:
        session_id = generate_session_id()
    if initial_history is None:
        initial_history = []
    console = get_console(client.config)
    messages = list(initial_history)
    messages.append({"role": "user", "content": task})
    save_session(session_id, messages)

    while True:
        console.print()
        console.print("[bold cyan]harness is thinking...[/bold cyan]")
        chunks = list(client.stream(system=get_system_prompt(SYSTEM_PROMPT), messages=messages))
        response = "".join(chunks)

        tool_info = parse_tool_call(response)
        if tool_info:
            tool_name, tool_args = tool_info
            console.print(f"[bold yellow]Tool Call:[/bold yellow] `{tool_name}` with args {tool_args}")
            
            if click.confirm("Do you want to execute this tool call?", default=True):
                result = run_tool(tool_name, **tool_args)
                console.print(f"[bold green]Tool Output (first 100 chars):[/bold green]\n{result[:100]}...")
                messages.append({"role": "assistant", "content": response})
                messages.append({"role": "user", "content": f"[Tool Output for {tool_name}]:\n{result}"})
                save_session(session_id, messages)
            else:
                console.print("[yellow]Tool execution cancelled by user. Returning control to you.[/yellow]")
                return "Tool execution cancelled by the user."
        else:
            console.print(Panel(Markdown(response), title="harness", border_style="cyan"))
            messages.append({"role": "assistant", "content": response})
            save_session(session_id, messages)
            return response


def run_single_turn_with_planning(client: LLMClient, task: str, session_id: str | None = None, initial_history: list[dict[str, str]] | None = None) -> str:
    """Send one task to the model, running a research, planning, and execution loop."""
    if session_id is None:
        session_id = generate_session_id()
    if initial_history is None:
        initial_history = []
    console = get_console(client.config)
    messages = list(initial_history)
    messages.append({"role": "user", "content": task})
    save_session(session_id, messages)

    # 1. Research & Planning Phase
    while True:
        console.print()
        console.print("[bold cyan]harness is researching and planning...[/bold cyan]")
        chunks = list(client.stream(system=get_system_prompt(PLANNING_SYSTEM_PROMPT), messages=messages))
        response = "".join(chunks)

        tool_info = parse_tool_call(response)
        if tool_info:
            tool_name, tool_args = tool_info
            
            # Restrict tools during planning phase
            if tool_name in ("edit_file", "run_command") or (tool_name == "write_file" and tool_args.get("path") != "plan.md"):
                error_msg = f"Error: The tool '{tool_name}' is disabled during the Research & Planning Phase. You must write the plan to 'plan.md' first."
                console.print(f"[bold red]{error_msg}[/bold red]")
                messages.append({"role": "assistant", "content": response})
                messages.append({"role": "user", "content": error_msg})
                save_session(session_id, messages)
                continue

            console.print(f"[bold yellow]Tool Call (Planning):[/bold yellow] `{tool_name}` with args {tool_args}")
            if click.confirm("Do you want to execute this tool call?", default=True):
                result = run_tool(tool_name, **tool_args)
                console.print(f"[bold green]Tool Output (first 100 chars):[/bold green]\n{result[:100]}...")
                messages.append({"role": "assistant", "content": response})
                messages.append({"role": "user", "content": f"[Tool Output for {tool_name}]:\n{result}"})
                save_session(session_id, messages)
            else:
                console.print("[yellow]Tool execution cancelled by user. Returning control to you.[/yellow]")
                return "Tool execution cancelled by the user during planning."
        else:
            # Check if plan.md exists
            if os.path.exists("plan.md"):
                console.print(Panel(Markdown(response), title="harness (Planning Summary)", border_style="cyan"))
                try:
                    with open("plan.md", "r", encoding="utf-8") as f:
                        plan_content = f.read()
                except Exception as e:
                    plan_content = f"Error reading plan.md: {e}"

                console.print()
                console.print(Panel(Markdown(plan_content), title="plan.md", border_style="yellow"))

                if click.confirm("Do you approve this plan?", default=True):
                    console.print("[bold green]Plan approved. Transitioning to Execution Phase...[/bold green]")
                    break
                else:
                    feedback = click.prompt("Provide feedback/adjustments to the plan")
                    messages.append({"role": "assistant", "content": response})
                    messages.append({
                        "role": "user",
                        "content": f"The user rejected the plan. Feedback:\n{feedback}\nPlease update 'plan.md' to reflect this feedback."
                    })
                    save_session(session_id, messages)
            else:
                prompt_msg = "Please write the proposed implementation plan to 'plan.md' using the write_file tool."
                messages.append({"role": "assistant", "content": response})
                messages.append({"role": "user", "content": prompt_msg})
                save_session(session_id, messages)

    # 2. Execution Phase
    messages.append({"role": "user", "content": "The plan has been approved. Please execute the plan now."})
    save_session(session_id, messages)
    while True:
        console.print()
        console.print("[bold cyan]harness is executing plan...[/bold cyan]")
        chunks = list(client.stream(system=get_system_prompt(EXECUTION_SYSTEM_PROMPT), messages=messages))
        response = "".join(chunks)

        tool_info = parse_tool_call(response)
        if tool_info:
            tool_name, tool_args = tool_info
            console.print(f"[bold yellow]Tool Call (Execution):[/bold yellow] `{tool_name}` with args {tool_args}")
            if click.confirm("Do you want to execute this tool call?", default=True):
                result = run_tool(tool_name, **tool_args)
                console.print(f"[bold green]Tool Output (first 100 chars):[/bold green]\n{result[:100]}...")
                messages.append({"role": "assistant", "content": response})
                messages.append({"role": "user", "content": f"[Tool Output for {tool_name}]:\n{result}"})
                save_session(session_id, messages)
            else:
                console.print("[yellow]Tool execution cancelled by user. Returning control to you.[/yellow]")
                return "Tool execution cancelled by the user during execution."
        else:
            console.print(Panel(Markdown(response), title="harness (Execution Finished)", border_style="cyan"))
            messages.append({"role": "assistant", "content": response})
            save_session(session_id, messages)

            # --- Verification and Self-Correction Loop ---
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
                return response

            from agent.correction import run_verification_command, get_correction_prompt
            correction_attempts = 0
            max_correct = client.config.max_correct

            while True:
                failures = []
                for cmd in verify_commands:
                    console.print(f"[bold blue]Running verification command:[/bold blue] `{cmd}`")
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
                    console.print("[bold green]All verification commands passed successfully![/bold green]")
                    return response

                if correction_attempts >= max_correct:
                    console.print(f"[bold red]Reached maximum correction attempts ({max_correct}). Verification failed.[/bold red]")
                    return f"Verification failed after {max_correct} correction attempts. Output of last failure:\n{failures[0][2]}"

                correction_attempts += 1
                prompt = "\n\n".join(get_correction_prompt(cmd, code, out) for cmd, code, out in failures)
                console.print(f"[bold yellow]Entering self-correction loop (Attempt {correction_attempts}/{max_correct})...[/bold yellow]")

                messages.append({"role": "user", "content": prompt})
                save_session(session_id, messages)

                # Inner loop for correction edits
                while True:
                    console.print()
                    console.print(f"[bold cyan]harness is correcting (Attempt {correction_attempts})...[/bold cyan]")
                    chunks = list(client.stream(system=get_system_prompt(EXECUTION_SYSTEM_PROMPT), messages=messages))
                    response = "".join(chunks)

                    tool_info = parse_tool_call(response)
                    if tool_info:
                        tool_name, tool_args = tool_info
                        console.print(f"[bold yellow]Tool Call (Correction):[/bold yellow] `{tool_name}` with args {tool_args}")

                        should_approve = False
                        if client.config.auto_correct:
                            console.print("[bold green]Auto-approving tool call in auto-correction mode.[/bold green]")
                            should_approve = True
                        else:
                            should_approve = click.confirm("Do you want to execute this tool call?", default=True)

                        if should_approve:
                            result = run_tool(tool_name, **tool_args)
                            console.print(f"[bold green]Tool Output (first 100 chars):[/bold green]\n{result[:100]}...")
                            messages.append({"role": "assistant", "content": response})
                            messages.append({"role": "user", "content": f"[Tool Output for {tool_name}]:\n{result}"})
                            save_session(session_id, messages)
                        else:
                            console.print("[yellow]Tool execution cancelled by user during correction.[/yellow]")
                            return "Tool execution cancelled by the user during correction."
                    else:
                        console.print(Panel(Markdown(response), title=f"harness (Correction Attempt {correction_attempts} Finished)", border_style="cyan"))
                        messages.append({"role": "assistant", "content": response})
                        save_session(session_id, messages)
                        break


def run_interactive(client: LLMClient, session_id: str | None = None, initial_history: list[dict[str, str]] | None = None) -> None:
    if session_id is None:
        session_id = generate_session_id()
    if initial_history is None:
        initial_history = []
    console = get_console(client.config)
    console.print(
        "[bold cyan]harness[/bold cyan] interactive mode. "
        "Type a task, or 'exit' to quit.\n"
    )
    history = list(initial_history)
    if history:
        console.print("[bold yellow]Resumed History:[/bold yellow]")
        for msg in history:
            role = "[bold cyan]harness[/bold cyan]" if msg["role"] == "assistant" else "[bold green]user[/bold green]"
            if msg["role"] == "user" and msg["content"].startswith("[Tool Output"):
                console.print(f"[bold dim]Tool Output:[/bold dim] [dim]{msg['content'][:150]}...[/dim]")
            else:
                console.print(f"{role}: {msg['content']}")
        console.print("-" * 40)

    while True:
        try:
            task = console.input("[bold green]> [/bold green]")
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]goodbye[/dim]")
            break

        if not task.strip():
            continue
        if task.strip().lower() in ("exit", "quit"):
            console.print("[dim]goodbye[/dim]")
            break

        history.append({"role": "user", "content": task})
        save_session(session_id, history)

        while True:
            console.print()
            console.print("[bold cyan]harness is thinking...[/bold cyan]")
            chunks = list(client.stream(system=get_system_prompt(SYSTEM_PROMPT), messages=history))
            response = "".join(chunks)

            tool_info = parse_tool_call(response)
            if tool_info:
                tool_name, tool_args = tool_info
                console.print(f"[bold yellow]Tool Call:[/bold yellow] `{tool_name}` with args {tool_args}")

                if click.confirm("Do you want to execute this tool call?", default=True):
                    result = run_tool(tool_name, **tool_args)
                    console.print(f"[bold green]Tool Output (first 100 chars):[/bold green]\n{result[:100]}...")
                    history.append({"role": "assistant", "content": response})
                    history.append({"role": "user", "content": f"[Tool Output for {tool_name}]:\n{result}"})
                    save_session(session_id, history)
                else:
                    console.print("[yellow]Tool execution cancelled by user. Returning control to you.[/yellow]")
                    break
            else:
                console.print(Panel(Markdown(response), title="harness", border_style="cyan"))
                history.append({"role": "assistant", "content": response})
                save_session(session_id, history)
                break

@click.command()
@click.argument("task", required=False)
@click.option(
    "--provider",
    type=click.Choice(["gemini", "groq", "grok"]),
    default=None,
    help="Override the LLM provider (defaults to HARNESS_PROVIDER in .env).",
)
@click.option(
    "--model",
    default=None,
    help="Override the model name for the selected provider.",
)
@click.option(
    "--no-plan",
    is_flag=True,
    help="Skip the planning phase and run the task in one-shot execution mode.",
)
@click.option(
    "--resume",
    default=None,
    help="Resume a previous session by ID or specify 'latest' to resume the most recent session.",
)
@click.option(
    "--sessions",
    is_flag=True,
    help="List all saved interactive sessions.",
)
@click.option(
    "--verify-cmd",
    default=None,
    help="Command to verify changes (e.g. 'pytest'). Overrides plan.md.",
)
@click.option(
    "--max-correct",
    type=int,
    default=None,
    help="Maximum number of self-correction attempts (default: 3).",
)
@click.option(
    "--auto-correct",
    is_flag=True,
    help="Automatically execute tools without confirmation during the self-correction loop.",
)
def cli(
    task: str | None,
    provider: str | None,
    model: str | None,
    no_plan: bool,
    resume: str | None,
    sessions: bool,
    verify_cmd: str | None,
    max_correct: int | None,
    auto_correct: bool,
) -> None:
    """Send TASK to the coding agent. Omit TASK to start interactive mode."""
    if sessions:
        from agent.memory import list_sessions
        saved = list_sessions()
        if not saved:
            console.print("No saved sessions found.")
        else:
            console.print("[bold cyan]Saved Sessions:[/bold cyan]")
            for s in saved:
                console.print(f"  [bold yellow]{s['id']}[/bold yellow] (Modified: {s['timestamp']})")
                console.print(f"    Preview: {s['preview']}")
        sys.exit(0)

    try:
        config = load_config(
            provider_override=provider,
            model_override=model,
            verify_cmd_override=verify_cmd,
            max_correct_override=max_correct,
            auto_correct_override=auto_correct,
        )
        client = LLMClient(config)
    except LLMError as exc:
        console.print(f"[bold red]Configuration error:[/bold red] {exc}")
        sys.exit(1)

    console.print(
        f"[dim]provider={config.provider} model={config.active_model}[/dim]"
    )

    session_id = None
    initial_history = []
    if resume:
        from agent.memory import list_sessions, load_session
        if resume.lower() == "latest":
            saved = list_sessions()
            if not saved:
                console.print("[bold red]Error:[/bold red] No saved sessions found to resume.")
                sys.exit(1)
            session_id = saved[0]["id"]
        else:
            session_id = resume
        
        try:
            initial_history = load_session(session_id)
            console.print(f"[bold green]Resumed session: {session_id}[/bold green]")
        except FileNotFoundError:
            console.print(f"[bold red]Error:[/bold red] Session '{session_id}' not found.")
            sys.exit(1)
    else:
        from agent.memory import generate_session_id
        session_id = generate_session_id()

    if task:
        try:
            if no_plan:
                run_single_turn(client, task, session_id, initial_history)
            else:
                run_single_turn_with_planning(client, task, session_id, initial_history)
        except LLMError as exc:
            console.print(f"[bold red]Error:[/bold red] {exc}")
            sys.exit(1)
    else:
        run_interactive(client, session_id, initial_history)
if __name__ == "__main__":
    cli()
