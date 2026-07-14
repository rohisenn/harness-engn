"""
harness - an open-source coding agent.

Milestone 1: a CLI that sends a prompt to an LLM and prints the response.

Usage:
    python main.py "Add JWT authentication"
    python main.py "Fix failing tests" --provider openai
    python main.py             # interactive mode, keeps chatting until you exit
"""

from __future__ import annotations

import sys

import click
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from agent.config import load_config
from agent.llm import LLMClient, LLMError
from agent.prompts import SYSTEM_PROMPT

console = Console()


def run_single_turn(client: LLMClient, task: str) -> str:
    """Send one task to the model, streaming the response to the terminal."""
    messages = [{"role": "user", "content": task}]

    console.print()
    full_response = ""
    with console.status("[bold cyan]harness is thinking...[/bold cyan]", spinner="dots"):
        chunks = list(client.stream(system=SYSTEM_PROMPT, messages=messages))
    full_response = "".join(chunks)

    console.print(Panel(Markdown(full_response), title="harness", border_style="cyan"))
    return full_response


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

        console.print()
        with console.status("[bold cyan]harness is thinking...[/bold cyan]", spinner="dots"):
            chunks = list(client.stream(system=SYSTEM_PROMPT, messages=history))
        response = "".join(chunks)

        console.print(Panel(Markdown(response), title="harness", border_style="cyan"))
        history.append({"role": "assistant", "content": response})


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
