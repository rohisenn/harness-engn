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
        part_lower = part.lower()
        # Prevent accessing any .env file (except .env.example template)
        if part_lower.startswith(".env") and not part_lower.endswith(".example"):
            return True
        # Prevent accessing version control, virtual envs, or test caches
        if part_lower in (".git", "venv", ".venv", ".pytest_cache", ".harness"):
            return True
            
    return False


def is_sensitive_command(command: str) -> bool:
    """
    Checks if a shell command tries to access or expose sensitive files/folders.
    """
    import re
    cmd_lower = command.lower()
    
    # Check for .env access (but allow .env.example)
    cleaned_cmd = cmd_lower.replace(".env.example", "")
    if ".env" in cleaned_cmd:
        return True
        
    # Check for version control access (.git folder)
    if re.search(r'\b\.git\b', cmd_lower):
        return True
        
    # Check for harness directory (.harness) or test cache (.pytest_cache)
    if ".harness" in cmd_lower or ".pytest_cache" in cmd_lower:
        return True
        
    # Check for virtual environments
    if re.search(r'\b\.?venv\b', cmd_lower) or ".venv" in cmd_lower:
        return True
        
    # Prevent printing/exposing all environment variables if they contain API keys
    if cmd_lower.strip() in ("env", "printenv", "set"):
        return True
        
    # Prevent common python env dumps
    if "os.environ" in cmd_lower or "os.getenv" in cmd_lower or "environ.get" in cmd_lower:
        return True
        
    return False

