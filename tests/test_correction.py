import os
import pytest
from unittest.mock import MagicMock, patch
from agent.config import Config
from agent.llm import LLMClient
from agent.correction import (
    extract_verification_commands,
    run_verification_command,
    get_correction_prompt,
)
from main import run_single_turn_with_planning

def test_extract_verification_commands_basic():
    plan = """
# Task

## Proposed Changes
Modifying some files.

## Verification Plan
### Automated Tests
- Run `pytest tests/test_simple.py` to check logic.
```bash
pytest tests/test_simple.py
python -m unittest tests/test_db.py
```
    """
    cmds = extract_verification_commands(plan)
    assert cmds == ["pytest tests/test_simple.py", "python -m unittest tests/test_db.py"]

def test_extract_verification_commands_fallback():
    # If no heading is found, search code blocks everywhere
    plan = """
Just some text without a verification heading, but with code blocks.
```bash
pytest tests/test_other.py
```
    """
    cmds = extract_verification_commands(plan)
    assert cmds == ["pytest tests/test_other.py"]

def test_extract_verification_commands_empty():
    assert extract_verification_commands("") == []
    assert extract_verification_commands(None) == []

def test_run_verification_command_security():
    # Attempting to read .env should fail the security check
    code, output = run_verification_command("cat .env")
    assert code == -1
    assert "blocked due to security restrictions" in output

def test_get_correction_prompt():
    prompt = get_correction_prompt("pytest", 1, "AssertionError")
    assert "[Verification Failure]" in prompt
    assert "pytest" in prompt
    assert "AssertionError" in prompt

@patch("click.confirm")
@patch("main.run_tool")
@patch("agent.correction.run_verification_command")
def test_self_correction_loop_success_after_retry(mock_run_verify, mock_run_tool, mock_confirm):
    # Mock approvals:
    # 1. Approve plan writing (write_file plan.md) -> True
    # 2. Approve plan -> True
    # 3. Approve correction tool call -> True
    mock_confirm.side_effect = [True, True, True]

    # Mock tool runs
    mock_run_tool.side_effect = [
        "Success: File plan.md written",  # planning write_file
        "Success: File edited"             # correction edit_file
    ]

    # Mock verification commands:
    # First execution phase finishes, run verification -> fails (exit code 1, Output: "fail")
    # After correction edits, run verification -> succeeds (exit code 0, Output: "ok")
    mock_run_verify.side_effect = [
        (1, "Failure log output"),
        (0, "All tests passed")
    ]

    mock_client = MagicMock(spec=LLMClient)
    mock_client.config = Config(
        provider="gemini",
        gemini_api_key="fake",
        gemini_model="gemini-3.5-flash",
        groq_api_key=None,
        groq_model="llama-3.3-70b-versatile",
        max_tokens=4096,
        verify_cmd="pytest",
        max_correct=3,
        auto_correct=False
    )

    # LLM Stream phases:
    # 1. Planning phase tool call (write_file plan.md)
    # 2. Planning phase response with no tool calls (plan written)
    # 3. Execution phase ends (no tool calls)
    # 4. Correction phase tool call (edit_file main.py)
    # 5. Correction phase ends (no tool calls)
    mock_client.stream.side_effect = [
        iter(['<tool_call name="write_file" path="plan.md"># Plan\n## Verification\n```bash\npytest\n```</tool_call>']),
        iter(['Plan prepared.']),
        iter(['Main implementation finished.']),  # Execution ends, enters verification, fails
        iter(['<tool_call name="edit_file" path="main.py"><old_content>x</old_content><new_content>y</new_content></tool_call>']), # correction
        iter(['Fixed the bug.']) # correction ends, verify succeeds
    ]

    if os.path.exists("plan.md"):
        os.remove("plan.md")
    # Physically create plan.md when write_file is called
    with open("plan.md", "w", encoding="utf-8") as f:
        f.write("# Plan\n## Verification\n```bash\npytest\n```")

    try:
        response = run_single_turn_with_planning(mock_client, "Fix the bug")
        assert response == "Fixed the bug."
        assert mock_run_verify.call_count == 2
        mock_run_verify.assert_any_call("pytest")
    finally:
        if os.path.exists("plan.md"):
            os.remove("plan.md")
