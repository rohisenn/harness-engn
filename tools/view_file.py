import os

def view_file(path: str) -> str:
    """
    Reads the content of a file located at path.
    The path is resolved relative to the current working directory.
    """
    if not path:
        return "Error: Path is empty."
    
    # Resolve the path relative to the current working directory
    target_path = os.path.abspath(path)
    cwd = os.path.abspath(os.getcwd())
    
    # Optional security check: prevent directory traversal outside workspace
    if not target_path.startswith(cwd):
        return f"Error: Path '{path}' is outside the workspace."
        
    if not os.path.exists(target_path):
        return f"Error: File '{path}' does not exist."
        
    if os.path.isdir(target_path):
        return f"Error: '{path}' is a directory, not a file. Use list_dir to inspect directories."
        
    try:
        with open(target_path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except Exception as e:
        return f"Error reading file '{path}': {e}"
