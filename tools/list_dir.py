import os
from tools.security import is_sensitive_path

def list_dir(path: str = ".") -> str:
    """
    Lists the contents of a directory located at path.
    The path is resolved relative to the current working directory.
    """
    if not path:
        path = "."
        
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
        return f"Error: Directory '{path}' does not exist."
        
    if not os.path.isdir(target_path):
        return f"Error: '{path}' is not a directory. Use view_file to inspect files."
        
    try:
        entries = os.listdir(target_path)
        
        # Filter out sensitive entries
        visible_entries = []
        for entry in sorted(entries):
            full_entry_path = os.path.realpath(os.path.join(target_path, entry))
            if is_sensitive_path(full_entry_path):
                continue
            visible_entries.append((entry, full_entry_path))
            
        if not visible_entries:
            return f"Directory '{path}' is empty."
            
        result = [f"Contents of directory '{path}':"]
        for entry, full_entry_path in visible_entries:
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
