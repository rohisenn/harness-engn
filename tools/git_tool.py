import subprocess
import os
from tools.security import is_sensitive_path

def _run_git_cmd(args: list[str]) -> tuple[int, str]:
    """Helper to run a git command in the current working directory."""
    try:
        res = subprocess.run(
            ["git"] + args,
            capture_output=True,
            text=True,
            check=False
        )
        output = res.stdout or ""
        if res.stderr:
            if output:
                output += "\n"
            output += res.stderr
        return res.returncode, output.strip()
    except FileNotFoundError:
        return -1, "Error: git executable not found on the system."
    except Exception as e:
        return -1, f"Error running git command: {e}"

def git_status() -> str:
    """
    Returns the current git status of the repository.
    Shows staged, unstaged, and untracked files.
    """
    code, out = _run_git_cmd(["status"])
    return f"Git Status (Exit Code: {code}):\n{out}"

def git_diff(path: str = None) -> str:
    """
    Returns the git diff for a specific file or the entire repository.
    """
    if path:
        if is_sensitive_path(path):
            return f"Error: Access to sensitive path '{path}' is restricted."
        args = ["diff", path]
    else:
        args = ["diff"]
        
    code, out = _run_git_cmd(args)
    return f"Git Diff (Exit Code: {code}):\n{out}"

def git_add(paths: str | list[str]) -> str:
    """
    Stages specified paths in git.
    Enforces security checks to prevent staging sensitive files.
    """
    if isinstance(paths, str):
        import shlex
        paths = shlex.split(paths)

    if not paths:
        return "Error: No paths specified to add."
        
    for path in paths:
        if is_sensitive_path(path):
            return f"Error: Access to sensitive path '{path}' is restricted."
            
    code, out = _run_git_cmd(["add"] + paths)
    if code == 0:
        return f"Success: Added paths {paths} to git staging."
    return f"Error: Failed to add paths. Output:\n{out}"

def git_commit(message: str) -> str:
    """
    Commits staged changes with the specified message.
    """
    if not message:
        return "Error: Commit message cannot be empty."
    code, out = _run_git_cmd(["commit", "-m", message])
    if code == 0:
        return f"Success: Changes committed. Output:\n{out}"
    return f"Error: Failed to commit changes. Output:\n{out}"

def git_checkout(branch: str, create: bool = False) -> str:
    """
    Switches to a branch, optionally creating it first.
    """
    if not branch:
        return "Error: Branch name cannot be empty."
        
    args = ["checkout", "-b", branch] if create else ["checkout", branch]
    code, out = _run_git_cmd(args)
    if code == 0:
        return f"Success: Switched to branch '{branch}'."
    return f"Error: Failed to checkout branch. Output:\n{out}"

def git_push(branch: str = None, remote: str = "origin") -> str:
    """
    Pushes local commits to a remote repository.
    """
    args = ["push", remote]
    if branch:
        args.append(branch)
    code, out = _run_git_cmd(args)
    if code == 0:
        return f"Success: Pushed changes to remote '{remote}'."
    return f"Error: Failed to push changes. Output:\n{out}"
