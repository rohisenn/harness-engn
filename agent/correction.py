import os
import re
import subprocess
from tools.security import is_sensitive_command

def extract_verification_commands(plan_content: str) -> list[str]:
    """
    Parses verification/test commands from the provided implementation plan content.
    Looks under verification-related headings or general code blocks.
    """
    if not plan_content:
        return []

    lines = plan_content.splitlines()
    in_verification_section = False
    section_lines = []

    # Check if there is a verification heading. If not, scan the whole file.
    has_verification_heading = any(
        re.match(r'^#+\s+.*(verify|verification|test|check).*$', line, re.IGNORECASE)
        for line in lines
    )

    if has_verification_heading:
        for line in lines:
            heading_match = re.match(r'^(#+)\s+(.*)$', line)
            if heading_match:
                title = heading_match.group(2).lower()
                if in_verification_section:
                    # Keep collecting until we hit a heading that does not relate to testing/verification
                    if not any(x in title for x in ["verify", "verification", "test", "check", "automate", "manual", "run"]):
                        in_verification_section = False

                if any(x in title for x in ["verify", "verification", "test", "check"]):
                    in_verification_section = True

            if in_verification_section:
                section_lines.append(line)

        content_to_scan = "\n".join(section_lines)
    else:
        content_to_scan = plan_content

    # Extract all bash/shell/cmd code blocks
    code_blocks = re.findall(
        r'```(?:bash|sh|shell|cmd|powershell)?\s*\n(.*?)\n```',
        content_to_scan,
        re.DOTALL | re.IGNORECASE
    )

    commands = []
    for block in code_blocks:
        for line in block.splitlines():
            line = line.strip()
            if line and not line.startswith("#") and not line.startswith("//"):
                commands.append(line)

    # Fallback: extract inline code blocks if no code blocks are found
    if not commands:
        inline_codes = re.findall(r'`([^`\n]+)`', content_to_scan)
        for code in inline_codes:
            code = code.strip()
            if any(keyword in code for keyword in ["pytest", "python", "npm", "cargo", "go test", "make", "sh", "bash", "run"]):
                commands.append(code)

    return commands

def run_verification_command(command: str, timeout: int = 30) -> tuple[int, str]:
    """
    Executes a verification command and returns (exit_code, output).
    Enforces same security restrictions as the run_command tool.
    """
    if not command:
        return -1, "Error: Verification command is empty."

    if is_sensitive_command(command):
        return -1, "Error: Verification command blocked due to security restrictions."

    try:
        result = subprocess.run(
            command,
            shell=True,
            text=True,
            capture_output=True,
            timeout=timeout
        )

        output_parts = []
        if result.stdout:
            output_parts.append(result.stdout)
        if result.stderr:
            output_parts.append(result.stderr)

        output = "\n".join(output_parts)
        if not output.strip():
            output = "(No output produced)"

        return result.returncode, output

    except subprocess.TimeoutExpired as e:
        output_parts = [f"Error: Command timed out after {timeout} seconds."]
        if e.stdout:
            stdout_str = e.stdout if isinstance(e.stdout, str) else e.stdout.decode('utf-8', errors='replace')
            output_parts.append(f"Captured stdout:\n{stdout_str}")
        if e.stderr:
            stderr_str = e.stderr if isinstance(e.stderr, str) else e.stderr.decode('utf-8', errors='replace')
            output_parts.append(f"Captured stderr:\n{stderr_str}")
        return -999, "\n".join(output_parts)
    except Exception as e:
        return -1, f"Error executing verification command: {e}"

def get_correction_prompt(command: str, exit_code: int, output: str) -> str:
    """
    Generates a prompt instructing the LLM that a verification command failed
    and requesting corrections.
    """
    return f"""\
[Verification Failure]: The verification command '{command}' failed with exit code {exit_code}.

Here is the tool execution output:
--------------------------------------------------
{output}
--------------------------------------------------

Please analyze the failure, determine what went wrong in your implementation, edit the files appropriately to fix the issue, and explain your changes.
"""
