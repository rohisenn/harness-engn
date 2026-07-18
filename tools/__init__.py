from tools.view_file import view_file
from tools.list_dir import list_dir
from tools.write_file import write_file
from tools.edit_file import edit_file
from tools.run_command import run_command
from tools.search_files import search_files
from tools.search_grep import search_grep

# Registry of all tools available to the agent
TOOLS = {
    "view_file": view_file,
    "list_dir": list_dir,
    "write_file": write_file,
    "edit_file": edit_file,
    "run_command": run_command,
    "search_files": search_files,
    "search_grep": search_grep,
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
