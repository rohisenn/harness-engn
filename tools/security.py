import os

def is_sensitive_path(path: str) -> bool:
    """
    Checks if a path refers to a sensitive file or directory (like .env or .git)
    that the agent should be restricted from reading, writing, or editing.
    """
    normalized_path = os.path.normpath(path).replace("\\", "/")
    parts = normalized_path.split("/")
    
    # Check if any path segment matches sensitive directories or files
    for part in parts:
        # Prevent accessing any .env file
        if part.startswith(".env"):
            return True
        # Prevent accessing version control, virtual envs, or test caches
        if part in (".git", "venv", ".venv", ".pytest_cache"):
            return True
            
    return False
