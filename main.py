"""
harness - an open-source coding agent.

Milestone 1: a CLI that sends a prompt to an LLM and prints the response.

Usage:
    python main.py "Add JWT authentication"
    python main.py "Fix failing tests" --provider openai
    python main.py             # interactive mode, keeps chatting until you exit
"""

from __future__ import annotations

import re
import sys

import click
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from agent.config import load_config
from agent.llm import LLMClient, LLMError
from agent.prompts import SYSTEM_PROMPT
from tools import run_tool

console = Console()


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
    messages = [{"role": "user", "content": task}]

    while True:
        console.print()
        with console.status("[bold cyan]harness is thinking...[/bold cyan]", spinner="dots"):
            chunks = list(client.stream(system=SYSTEM_PROMPT, messages=messages))
        response = "".join(chunks)

        tool_info = parse_tool_call(response)
        if tool_info:
            tool_name, tool_args = tool_info
            console.print(f"[bold yellow]Tool Call:[/bold yellow] `{tool_name}` with args {tool_args}")
            
            if click.confirm("Do you want to execute this tool call?", default=True):
                result = run_tool(tool_name, **tool_args)
                console.print(f"[bold green]Tool Output (first 100 chars):[/bold green]\n{result[:100]}...")
            else:
                result = "Error: Tool execution cancelled by the user."
                console.print("[yellow]Tool execution cancelled by user.[/yellow]")

            messages.append({"role": "assistant", "content": response})
            messages.append({"role": "user", "content": f"[Tool Output for {tool_name}]:\n{result}"})
        else:
            console.print(Panel(Markdown(response), title="harness", border_style="cyan"))
            return response


def run_interactive(client: LLMClient) -> None:
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
            with console.status("[bold cyan]harness is thinking...[/bold cyan]", spinner="dots"):
                chunks = list(client.stream(system=SYSTEM_PROMPT, messages=history))
            response = "".join(chunks)

            tool_info = parse_tool_call(response)
            if tool_info:
                tool_name, tool_args = tool_info
                console.print(f"[bold yellow]Tool Call:[/bold yellow] `{tool_name}` with args {tool_args}")

                if click.confirm("Do you want to execute this tool call?", default=True):
                    result = run_tool(tool_name, **tool_args)
                    console.print(f"[bold green]Tool Output (first 100 chars):[/bold green]\n{result[:100]}...")
                else:
                    result = "Error: Tool execution cancelled by the user."
                    console.print("[yellow]Tool execution cancelled by user.[/yellow]")

                history.append({"role": "assistant", "content": response})
                history.append({"role": "user", "content": f"[Tool Output for {tool_name}]:\n{result}"})
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
def cli(task: str | None, provider: str | None, model: str | None) -> None:
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
            run_single_turn(client, task)
        except LLMError as exc:
            console.print(f"[bold red]Error:[/bold red] {exc}")
            sys.exit(1)
    else:
        run_interactive(client)


if __name__ == "__main__":
    cli()
