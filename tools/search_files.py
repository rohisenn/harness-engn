import os
import fnmatch

def search_files(pattern: str, path: str = ".") -> str:
    """
    Search for files under path (defaults to '.') whose filename matches pattern.
    The path is resolved relative to the current working directory.
    """
    if not pattern:
        return "Error: Search pattern is empty."
        
    if not path:
        path = "."

    target_path = os.path.abspath(path)
    cwd = os.path.abspath(os.getcwd())
    
    # Security check: prevent searching outside the workspace
    if not target_path.startswith(cwd):
        return f"Error: Path '{path}' is outside the workspace."
        
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
                if fnmatch.fnmatch(file, pattern):
                    full_path = os.path.join(root, file)
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
