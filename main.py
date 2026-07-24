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
import subprocess

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
from agent.prompts import SYSTEM_PROMPT, NEW_PROJECT_HINT
from agent.planning_prompts import PLANNING_SYSTEM_PROMPT, EXECUTION_SYSTEM_PROMPT
from tools import run_tool
from agent.memory import load_facts, save_session, generate_session_id
from agent.context import maybe_compress

console = Console()


def is_git_repo() -> bool:
    try:
        res = subprocess.run(["git", "rev-parse", "--is-inside-work-tree"], capture_output=True, text=True)
        return res.returncode == 0 and "true" in res.stdout.lower()
    except Exception:
        return False


def sanitize_branch_name(task_desc: str) -> str:
    s = task_desc.lower()
    s = re.sub(r'[^a-z0-9]+', '-', s)
    s = s.strip('-')
    return s[:30]


def setup_git_branch(config: Config, task_desc: str) -> str:
    if not is_git_repo():
        raise Exception("Not a git repository.")
    slug = sanitize_branch_name(task_desc)
    branch_name = f"{config.git_branch_prefix}task-{slug}"
    # Try creating branch
    res = subprocess.run(["git", "checkout", "-b", branch_name], capture_output=True, text=True)
    if res.returncode != 0:
        # Already exists, just checkout
        res = subprocess.run(["git", "checkout", branch_name], capture_output=True, text=True)
        if res.returncode != 0:
            raise Exception(f"Failed to create or checkout branch '{branch_name}': {res.stderr}")
    return branch_name


def handle_git_success(client: LLMClient, console: Console) -> None:
    # 1. Get status of modified/untracked files
    res = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True)
    if res.returncode != 0:
        console.print("[bold red]Git success handler: git status failed.[/bold red]")
        return

    files_to_add = []
    for line in res.stdout.splitlines():
        if len(line) < 4:
            continue
        status_code = line[:2]
        filepath = line[3:].strip()
        # Clean quotes if any
        if filepath.startswith('"') and filepath.endswith('"'):
            filepath = filepath[1:-1]
        
        # Verify it's not sensitive
        from tools.security import is_sensitive_path
        if not is_sensitive_path(filepath):
            files_to_add.append(filepath)

    if not files_to_add:
        console.print("[yellow]Git: No modified files to commit.[/yellow]")
        return

    # Add files
    add_res = subprocess.run(["git", "add"] + files_to_add, capture_output=True, text=True)
    if add_res.returncode != 0:
        console.print(f"[bold red]Git: Failed to stage files: {add_res.stderr}[/bold red]")
        return

    # 2. Get git diff of staged files to generate commit message
    diff_res = subprocess.run(["git", "diff", "--cached"], capture_output=True, text=True)
    staged_diff = diff_res.stdout
    if not staged_diff.strip():
        console.print("[yellow]Git: Staged diff is empty. Skipping commit.[/yellow]")
        return

    # 3. Call LLM to generate commit message and PR description
    console.print("[bold cyan]Git: Requesting LLM to generate commit message and PR description...[/bold cyan]")
    
    prompt = f"""You are a Git assistant. All implementation and verification steps for the current coding task have succeeded.
Below is the diff of the changes made to the repository.
Please generate:
1. A concise, descriptive commit message (max 72 characters, preferably in conventional commit format like `feat: add ...` or `fix: resolve ...`).
2. A detailed Pull Request description in markdown format summarizing the changes, the files modified, and the verification results.

Format your response EXACTLY like this:
<commit_message>
[Your commit message here]
</commit_message>
<pr_description>
[Your markdown PR description here]
</pr_description>

Here is the diff:
--------------------------------------------------
{{staged_diff[:8000]}}
--------------------------------------------------
"""
    try:
        # Request standard stream response from LLM, combine chunks
        response_chunks = list(client.stream(
            system="You are a helpful git helper assistant.",
            messages=[{"role": "user", "content": prompt}]
        ))
        llm_out = "".join(response_chunks)
        
        commit_msg = "feat: implement coding task"
        pr_desc = "# Pull Request\n\nTask implemented successfully."
        
        commit_match = re.search(r'<commit_message>(.*?)</commit_message>', llm_out, re.DOTALL)
        if commit_match:
            commit_msg = commit_match.group(1).strip()
            
        pr_match = re.search(r'<pr_description>(.*?)</pr_description>', llm_out, re.DOTALL)
        if pr_match:
            pr_desc = pr_match.group(1).strip()
            
    except Exception as e:
        console.print(f"[bold yellow]Git: LLM request failed ({e}). Using default commit message.[/bold yellow]")
        commit_msg = "feat: implement coding task"
        pr_desc = f"# Pull Request\n\nChanges:\n" + "\n".join(f"- {f}" for f in files_to_add)

    # 4. Commit changes
    commit_res = subprocess.run(["git", "commit", "-m", commit_msg], capture_output=True, text=True)
    if commit_res.returncode != 0:
        console.print(f"[bold red]Git: Commit failed: {commit_res.stderr}[/bold red]")
        return
        
    # Get short commit hash
    hash_res = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True)
    commit_hash = hash_res.stdout.strip()
    
    # 5. Write PR description file
    pr_file = "PR_DESCRIPTION.md"
    try:
        with open(pr_file, "w", encoding="utf-8") as f:
            f.write(pr_desc)
        console.print(f"[bold green]Git: Successfully committed changes [{commit_hash}] and wrote PR description to {pr_file}![/bold green]")
    except Exception as e:
        console.print(f"[bold red]Git: Failed to write PR description file: {e}[/bold red]")

    # 6. Optionally push changes to remote
    if client.config.git_push:
        console.print("[bold cyan]Git: Pushing commits to remote...[/bold cyan]")
        branch_res = subprocess.run(["git", "branch", "--show-current"], capture_output=True, text=True)
        branch_name = branch_res.stdout.strip()
        if branch_name:
            push_res = subprocess.run(["git", "push", "origin", branch_name], capture_output=True, text=True)
            if push_res.returncode == 0:
                console.print(f"[bold green]Git: Successfully pushed branch '{branch_name}' to remote![/bold green]")
            else:
                console.print(f"[bold red]Git: Push failed: {push_res.stderr.strip() or push_res.stdout.strip()}[/bold red]")
        else:
            console.print("[bold red]Git: Could not determine current branch name for pushing.[/bold red]")


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


def is_empty_dir() -> bool:
    """Returns True if cwd has no user files (ignores hidden dirs like .harness, .git)."""
    entries = [e for e in os.listdir(".") if not e.startswith(".")]
    return len(entries) == 0


def get_system_prompt(base_prompt: str) -> str:
    parts = [base_prompt]
    if is_empty_dir():
        parts.append(NEW_PROJECT_HINT)
    facts = load_facts()
    if facts:
        parts.append("[Repository Facts/Memory]:\n" + "\n".join(f"- {f}" for f in facts))
    return "\n".join(parts)


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
        messages, compressed = maybe_compress(client, messages, client.config.context_window, client.config.compress_tail)
        if compressed:
            console.print("[dim]Context compressed.[/dim]")
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
            if client.config.git_integration:
                handle_git_success(client, console)
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
        messages, compressed = maybe_compress(client, messages, client.config.context_window, client.config.compress_tail)
        if compressed:
            console.print("[dim]Context compressed.[/dim]")
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
        messages, compressed = maybe_compress(client, messages, client.config.context_window, client.config.compress_tail)
        if compressed:
            console.print("[dim]Context compressed.[/dim]")
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
                if client.config.git_integration:
                    handle_git_success(client, console)
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
                    if client.config.git_integration:
                        handle_git_success(client, console)
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
                    messages, compressed = maybe_compress(client, messages, client.config.context_window, client.config.compress_tail)
                    if compressed:
                        console.print("[dim]Context compressed.[/dim]")
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
            history, compressed = maybe_compress(client, history, client.config.context_window, client.config.compress_tail)
            if compressed:
                console.print("[dim]Context compressed.[/dim]")
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
@click.option(
    "--git",
    is_flag=True,
    help="Enable Git integration (auto-branching and committing on success).",
)
@click.option(
    "--git-push",
    is_flag=True,
    help="Enable automatic Git push of the created branch on success.",
)
@click.option(
    "--multi",
    is_flag=True,
    help="Enable Multi-Agent Collaboration mode.",
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
    git: bool,
    git_push: bool,
    multi: bool,
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
            git_integration_override=git,
            git_push_override=git_push,
        )
        client = LLMClient(config)
    except LLMError as exc:
        console.print(f"[bold red]Configuration error:[/bold red] {exc}")
        sys.exit(1)

    console.print(
        f"[dim]provider={config.provider} model={config.active_model}[/dim]"
    )

    if is_empty_dir():
        console.print(Panel(
            "[bold green]New project mode[/bold green] — current directory is empty.\n"
            "Describe what you want to build and harness will scaffold it from scratch.",
            border_style="green",
            title="harness"
        ))

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
        if config.git_integration:
            try:
                branch_name = setup_git_branch(config, task)
                console.print(f"[bold green]Git: Created/Checked out branch '{branch_name}'[/bold green]")
            except Exception as e:
                console.print(f"[bold red]Git branch setup failed: {e}[/bold red]")
                sys.exit(1)

        try:
            if multi:
                from agent.multi_agent import run_multi_agent_session
                run_multi_agent_session(client, task, session_id, initial_history)
            elif no_plan:
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
