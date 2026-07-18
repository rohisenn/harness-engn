import os
from tools.security import is_sensitive_path

def search_grep(query: str, path: str = ".") -> str:
    """
    Search for exact text matches of query inside files under path.
    The path is resolved relative to the current working directory.
    """
    if not query:
        return "Error: Query is empty."
        
    if not path:
        path = "."
        
    if is_sensitive_path(path):
        return f"Error: Access to sensitive file or directory '{path}' is restricted."

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
    # Common binary and non-text extensions to ignore
    ignored_extensions = {
        ".pyc", ".pyo", ".pyd", ".db", ".sqlite", ".sqlite3",
        ".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf",
        ".zip", ".tar", ".gz", ".7z", ".rar", ".exe", ".dll",
        ".so", ".dylib", ".woff", ".woff2", ".eot", ".ttf",
    }

    max_total_matches = 50
    max_file_matches = 5
    total_matches = 0
    results = []
    truncated = False

    try:
        for root, dirs, files in os.walk(target_path):
            # Modify dirs in-place to avoid walking down ignored directories
            dirs[:] = [d for d in dirs if d not in ignored_dirs]
            
            for file in files:
                full_path = os.path.join(root, file)
                if is_sensitive_path(full_path):
                    continue
                    
                _, ext = os.path.splitext(file)
                if ext.lower() in ignored_extensions:
                    continue
                    
                rel_path = os.path.relpath(full_path, cwd).replace("\\", "/")
                
                try:
                    file_matches = 0
                    with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                        for line_num, line in enumerate(f, 1):
                            if query in line:
                                if total_matches >= max_total_matches:
                                    truncated = True
                                    break
                                    
                                file_matches += 1
                                if file_matches > max_file_matches:
                                    results.append(f"  {rel_path}:... (additional matches in this file truncated)")
                                    break
                                    
                                results.append(f"  {rel_path}:{line_num}: {line.rstrip()}")
                                total_matches += 1
                                
                    if truncated:
                        break
                except Exception:
                    # Ignore files that fail to read (e.g. permission or binary formatting errors)
                    continue
            if truncated:
                break
                
        if not results:
            return f"No occurrences of '{query}' found under path '{path}'."
            
        header = f"Found {total_matches} occurrence(s) of '{query}':"
        if truncated:
            results.append("  ... (results truncated: reached search limit)")
            
        return header + "\n" + "\n".join(results)
        
    except Exception as e:
        return f"Error running grep search: {e}"
