import os
import fnmatch
from tools.security import is_sensitive_path

def search_files(pattern: str, path: str = ".") -> str:
    """
    Search for files under path (defaults to '.') whose filename matches pattern.
    The path is resolved relative to the current working directory.
    """
    if not pattern:
        return "Error: Search pattern is empty."
        
    if not path:
        path = "."
        
    try:
        target_path = os.path.realpath(path)
        cwd = os.path.realpath(os.getcwd())
    except Exception as e:
        return f"Error resolving path: {e}"
        
    # Security check: prevent searching outside the workspace
    try:
        if os.path.commonpath([cwd, target_path]) != cwd:
            return f"Error: Path '{path}' is outside the workspace."
    except ValueError:
        return f"Error: Path '{path}' is outside the workspace."
        
    if is_sensitive_path(target_path):
        return f"Error: Access to sensitive file or directory '{path}' is restricted."
        
    if not os.path.exists(target_path):
        return f"Error: Path '{path}' does not exist."
        
    if not os.path.isdir(target_path):
        return f"Error: Path '{path}' is not a directory."

    ignored_dirs = {".git", "venv", ".venv", "__pycache__", ".pytest_cache"}
    matched_files = []
    
    try:
        for root, dirs, files in os.walk(target_path):
            # Modify dirs in-place to avoid walking down ignored directories
            dirs[:] = [d for d in dirs if d not in ignored_dirs]
            
            for file in files:
                full_path = os.path.join(root, file)
                if is_sensitive_path(full_path):
                    continue
                    
                if fnmatch.fnmatch(file, pattern):
                    rel_path = os.path.relpath(full_path, cwd)
                    # Normalize separators for cross-platform consistency
                    rel_path = rel_path.replace("\\", "/")
                    matched_files.append(rel_path)
                    
        if not matched_files:
            return f"No files found matching pattern '{pattern}' under path '{path}'."
            
        matched_files.sort()
        result = [f"Found {len(matched_files)} file(s) matching pattern '{pattern}':"]
        for f in matched_files:
            result.append(f"  {f}")
        return "\n".join(result)
        
    except Exception as e:
        return f"Error searching files: {e}"
