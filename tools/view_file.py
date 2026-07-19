import os
from tools.security import is_sensitive_path

def view_file(path: str) -> str:
    """
    Reads the content of a file located at path.
    The path is resolved relative to the current working directory.
    """
    if not path:
        return "Error: Path is empty."
        
    try:
        target_path = os.path.realpath(path)
        cwd = os.path.realpath(os.getcwd())
    except Exception as e:
        return f"Error resolving path: {e}"
        
    # Security check: prevent directory traversal outside workspace
    try:
        if os.path.commonpath([cwd, target_path]) != cwd:
            return f"Error: Path '{path}' is outside the workspace."
    except ValueError:
        return f"Error: Path '{path}' is outside the workspace."
        
    if is_sensitive_path(target_path):
        return f"Error: Access to sensitive file or directory '{path}' is restricted."
        
    if not os.path.exists(target_path):
        return f"Error: File '{path}' does not exist."
        
    if os.path.isdir(target_path):
        return f"Error: '{path}' is a directory, not a file. Use list_dir to inspect directories."
        
    try:
        with open(target_path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except Exception as e:
        return f"Error reading file '{path}': {e}"
