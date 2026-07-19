import os
from tools.security import is_sensitive_path

def write_file(path: str, content: str) -> str:
    """
    Creates a new file or completely overwrites an existing file with the specified content.
    The path is resolved relative to the current working directory.
    """
    if not path:
        return "Error: Path is empty."
        
    try:
        target_path = os.path.realpath(path)
        cwd = os.path.realpath(os.getcwd())
    except Exception as e:
        return f"Error resolving path: {e}"
        
    # Security check: prevent writing outside workspace
    try:
        if os.path.commonpath([cwd, target_path]) != cwd:
            return f"Error: Path '{path}' is outside the workspace."
    except ValueError:
        return f"Error: Path '{path}' is outside the workspace."
        
    if is_sensitive_path(target_path):
        return f"Error: Access to sensitive file or directory '{path}' is restricted."
        
    try:
        # Create parent directories if they don't exist
        parent_dir = os.path.dirname(target_path)
        if parent_dir:
            os.makedirs(parent_dir, exist_ok=True)
            
        with open(target_path, "w", encoding="utf-8") as f:
            f.write(content)
            
        return f"Success: File '{path}' written successfully."
    except Exception as e:
        return f"Error writing file '{path}': {e}"
