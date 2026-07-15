import os

def list_dir(path: str = ".") -> str:
    """
    Lists the contents of a directory located at path.
    The path is resolved relative to the current working directory.
    """
    if not path:
        path = "."
        
    target_path = os.path.abspath(path)
    cwd = os.path.abspath(os.getcwd())
    
    # Optional security check: prevent directory traversal outside workspace
    if not target_path.startswith(cwd):
        return f"Error: Path '{path}' is outside the workspace."
        
    if not os.path.exists(target_path):
        return f"Error: Directory '{path}' does not exist."
        
    if not os.path.isdir(target_path):
        return f"Error: '{path}' is not a directory. Use view_file to inspect files."
        
    try:
        entries = os.listdir(target_path)
        if not entries:
            return f"Directory '{path}' is empty."
            
        result = [f"Contents of directory '{path}':"]
        for entry in sorted(entries):
            full_entry_path = os.path.join(target_path, entry)
            rel_entry_path = os.path.join(path, entry) if path != "." else entry
            # Normalize path separators to forward slashes for cross-platform ease
            rel_entry_path = rel_entry_path.replace("\\", "/")
            if os.path.isdir(full_entry_path):
                result.append(f"  [DIR]  {rel_entry_path}/")
            else:
                try:
                    size = os.path.getsize(full_entry_path)
                    result.append(f"  [FILE] {rel_entry_path} ({size} bytes)")
                except Exception:
                    result.append(f"  [FILE] {rel_entry_path}")
        return "\n".join(result)
    except Exception as e:
        return f"Error listing directory '{path}': {e}"
