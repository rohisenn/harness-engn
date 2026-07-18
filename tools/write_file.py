import os
from tools.security import is_sensitive_path

def write_file(path: str, content: str) -> str:
    """
    Creates a new file or completely overwrites an existing file with the specified content.
    The path is resolved relative to the current working directory.
    """
    if not path:
        return "Error: Path is empty."
        
    if is_sensitive_path(path):
        return f"Error: Access to sensitive file or directory '{path}' is restricted."
        
    target_path = os.path.abspath(path)
    cwd = os.path.abspath(os.getcwd())
    
    # Security check: prevent writing outside workspace
    if not target_path.startswith(cwd):
        return f"Error: Path '{path}' is outside the workspace."
        
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
