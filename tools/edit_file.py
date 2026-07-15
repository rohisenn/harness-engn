import os

def edit_file(path: str, old_content: str, new_content: str) -> str:
    """
    Performs block replacement in an existing file by searching for a unique occurrence
    of old_content and replacing it with new_content.
    """
    if not path:
        return "Error: Path is empty."
        
    target_path = os.path.abspath(path)
    cwd = os.path.abspath(os.getcwd())
    
    # Security check: prevent editing outside workspace
    if not target_path.startswith(cwd):
        return f"Error: Path '{path}' is outside the workspace."
        
    if not os.path.exists(target_path):
        return f"Error: File '{path}' does not exist. Use write_file to create new files."
        
    if os.path.isdir(target_path):
        return f"Error: '{path}' is a directory, not a file."
        
    if not old_content:
        return "Error: old_content to replace is empty."
        
    try:
        with open(target_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
            
        occurrences = content.count(old_content)
        
        if occurrences == 0:
            return (
                f"Error: The target block 'old_content' was not found in '{path}'. "
                "Make sure it matches the file text exactly (including indentation, newlines, and spaces)."
            )
        elif occurrences > 1:
            return (
                f"Error: Found {occurrences} occurrences of the target block in '{path}'. "
                "Please make the 'old_content' block larger and more specific to target a single location."
            )
            
        new_file_content = content.replace(old_content, new_content)
        
        with open(target_path, "w", encoding="utf-8") as f:
            f.write(new_file_content)
            
        return f"Success: File '{path}' edited successfully (replaced 1 block)."
    except Exception as e:
        return f"Error editing file '{path}': {e}"
