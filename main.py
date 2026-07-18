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

console = Console()


def get_console(config: Config) -> Console:
    """Returns a Console configured with or without colors depending on config settings."""
    if not config.color:
        return Console(color_system=None, highlight=False)
    return console


def parse_tool_call(response: str) -> tuple[str, dict[str, str]] | None:
    """
    Looks for a <tool_call name="tool_name" path="relative/path">body</tool_call>
    or <tool_call name="tool_name" path="path" /> tag in the response.
    Returns (tool_name, attributes_dict) if found, otherwise None.
    """
    # First search for full block tag: <tool_call name="name" path="path">body</tool_call>
    match_block = re.search(
        r'<tool_call\s+name="([^"]+)"\s+path="([^"]+)"\s*>(.*?)</tool_call>',
        response,
        re.DOTALL
    )
    if match_block:
        tool_name = match_block.group(1)
        path = match_block.group(2)
        body = match_block.group(3)

        if tool_name == "edit_file":
            old_match = re.search(r'<old_content>(.*?)</old_content>', body, re.DOTALL)
            new_match = re.search(r'<new_content>(.*?)</new_content>', body, re.DOTALL)
            if old_match and new_match:
                return tool_name, {
                    "path": path,
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
                "path": path,
                "content": content
            }

    # Fallback to inline syntax
    match_inline = re.search(r'<tool_call\s+([^>]+)/?>', response)
    if not match_inline:
        return None

    attributes_str = match_inline.group(1)
    attrs = re.findall(r'(\w+)="([^"]*)"', attributes_str)
    attrs_dict = dict(attrs)

    if "name" not in attrs_dict:
        return None

    tool_name = attrs_dict.pop("name")
    return tool_name, attrs_dict


def run_single_turn(client: LLMClient, task: str) -> str:
    """Send one task to the model, streaming the response to the terminal, executing tools if requested."""
    console = get_console(client.config)
    messages = [{"role": "user", "content": task}]

    while True:
        console.print()
        console.print("[bold cyan]harness is thinking...[/bold cyan]")
        chunks = list(client.stream(system=SYSTEM_PROMPT, messages=messages))
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
            else:
                console.print("[yellow]Tool execution cancelled by user. Returning control to you.[/yellow]")
                return "Tool execution cancelled by the user."
        else:
            console.print(Panel(Markdown(response), title="harness", border_style="cyan"))
            return response


def run_single_turn_with_planning(client: LLMClient, task: str) -> str:
    """Send one task to the model, running a research, planning, and execution loop."""
    console = get_console(client.config)
    messages = [{"role": "user", "content": task}]

    # 1. Research & Planning Phase
    while True:
        console.print()
        console.print("[bold cyan]harness is researching and planning...[/bold cyan]")
        chunks = list(client.stream(system=PLANNING_SYSTEM_PROMPT, messages=messages))
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
                continue

            console.print(f"[bold yellow]Tool Call (Planning):[/bold yellow] `{tool_name}` with args {tool_args}")
            if click.confirm("Do you want to execute this tool call?", default=True):
                result = run_tool(tool_name, **tool_args)
                console.print(f"[bold green]Tool Output (first 100 chars):[/bold green]\n{result[:100]}...")
                messages.append({"role": "assistant", "content": response})
                messages.append({"role": "user", "content": f"[Tool Output for {tool_name}]:\n{result}"})
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
            else:
                prompt_msg = "Please write the proposed implementation plan to 'plan.md' using the write_file tool."
                messages.append({"role": "assistant", "content": response})
                messages.append({"role": "user", "content": prompt_msg})

    # 2. Execution Phase
    messages.append({"role": "user", "content": "The plan has been approved. Please execute the plan now."})
    while True:
        console.print()
        console.print("[bold cyan]harness is executing plan...[/bold cyan]")
        chunks = list(client.stream(system=EXECUTION_SYSTEM_PROMPT, messages=messages))
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
            else:
                console.print("[yellow]Tool execution cancelled by user. Returning control to you.[/yellow]")
                return "Tool execution cancelled by the user during execution."
        else:
            console.print(Panel(Markdown(response), title="harness (Execution Finished)", border_style="cyan"))
            return response


def run_interactive(client: LLMClient) -> None:
    console = get_console(client.config)
    console.print(
        "[bold cyan]harness[/bold cyan] interactive mode. "
        "Type a task, or 'exit' to quit.\n"
    )
    history: list[dict[str, str]] = []

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

        while True:
            console.print()
            console.print("[bold cyan]harness is thinking...[/bold cyan]")
            chunks = list(client.stream(system=SYSTEM_PROMPT, messages=history))
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
                else:
                    console.print("[yellow]Tool execution cancelled by user. Returning control to you.[/yellow]")
                    break
            else:
                console.print(Panel(Markdown(response), title="harness", border_style="cyan"))
                history.append({"role": "assistant", "content": response})
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
def cli(task: str | None, provider: str | None, model: str | None, no_plan: bool) -> None:
    """Send TASK to the coding agent. Omit TASK to start interactive mode."""
    try:
        config = load_config(provider_override=provider, model_override=model)
        client = LLMClient(config)
    except LLMError as exc:
        console.print(f"[bold red]Configuration error:[/bold red] {exc}")
        sys.exit(1)

    console.print(
        f"[dim]provider={config.provider} model={config.active_model}[/dim]"
    )

    if task:
        try:
            if no_plan:
                run_single_turn(client, task)
            else:
                run_single_turn_with_planning(client, task)
        except LLMError as exc:
            console.print(f"[bold red]Error:[/bold red] {exc}")
            sys.exit(1)
    else:
        run_interactive(client)


if __name__ == "__main__":
    cli()
