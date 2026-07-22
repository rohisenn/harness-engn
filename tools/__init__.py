from tools.view_file import view_file
from tools.list_dir import list_dir
from tools.write_file import write_file
from tools.edit_file import edit_file
from tools.run_command import run_command
from tools.search_files import search_files
from tools.search_grep import search_grep
from tools.remember_fact import remember_fact
from tools.forget_fact import forget_fact
from tools.list_facts import list_facts
from tools.git_tool import git_status, git_diff, git_add, git_commit, git_checkout, git_push

# Registry of all tools available to the agent
TOOLS = {
    "view_file": view_file,
    "list_dir": list_dir,
    "write_file": write_file,
    "edit_file": edit_file,
    "run_command": run_command,
    "search_files": search_files,
    "search_grep": search_grep,
    "remember_fact": remember_fact,
    "forget_fact": forget_fact,
    "list_facts": list_facts,
    "git_status": git_status,
    "git_diff": git_diff,
    "git_add": git_add,
    "git_commit": git_commit,
    "git_checkout": git_checkout,
    "git_push": git_push,
}

def run_tool(name: str, **kwargs) -> str:
    """
    Executes the tool with the specified name and arguments, returning the output as a string.
    """
    if name not in TOOLS:
        return f"Error: Tool '{name}' not found. Available tools: {', '.join(TOOLS.keys())}"
    try:
        return TOOLS[name](**kwargs)
    except Exception as e:
        return f"Error executing tool '{name}': {e}"
