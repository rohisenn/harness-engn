import subprocess

def run_command(command: str, timeout: int = 30) -> str:
    """
    Executes a terminal command and returns its output.
    The command is run in the current working directory of the process.
    """
    if not command:
        return "Error: Command is empty."

    try:
        # Run command with shell=True, capturing stdout and stderr
        result = subprocess.run(
            command,
            shell=True,
            text=True,
            capture_output=True,
            timeout=timeout
        )
        
        output = []
        output.append(f"Exit Code: {result.returncode}")
        if result.stdout:
            output.append(f"Standard Output:\n{result.stdout}")
        if result.stderr:
            output.append(f"Standard Error:\n{result.stderr}")
            
        if not result.stdout and not result.stderr:
            output.append("(No output produced)")
            
        return "\n\n".join(output)
        
    except subprocess.TimeoutExpired as e:
        output = [f"Error: Command timed out after {timeout} seconds."]
        if e.stdout:
            stdout_str = e.stdout if isinstance(e.stdout, str) else e.stdout.decode('utf-8', errors='replace')
            output.append(f"Captured stdout before timeout:\n{stdout_str}")
        if e.stderr:
            stderr_str = e.stderr if isinstance(e.stderr, str) else e.stderr.decode('utf-8', errors='replace')
            output.append(f"Captured stderr before timeout:\n{stderr_str}")
        return "\n\n".join(output)
    except Exception as e:
        return f"Error executing command: {e}"
