import os
import pytest
from unittest.mock import MagicMock, patch
from agent.config import Config
from agent.llm import LLMClient
from agent.multi_agent import run_multi_agent_session, get_multi_agent_system_prompt
from tools import run_tool

def test_get_multi_agent_system_prompt_no_facts():
    # If facts are empty/not set, it should return prompt unchanged
    with patch("agent.multi_agent.load_facts", return_value=[]):
        p = get_multi_agent_system_prompt("Base Prompt")
        assert p == "Base Prompt"

def test_get_multi_agent_system_prompt_with_facts():
    # Prepend facts after first newline or append
    with patch("agent.multi_agent.load_facts", return_value=["Fact 1"]):
        p = get_multi_agent_system_prompt("Base Prompt\nInstructions here")
        assert "[Repository Facts/Memory]" in p
        assert "- Fact 1" in p


@patch("click.confirm")
@patch("agent.multi_agent.run_tool")
def test_multi_agent_collaboration_workflow(mock_run_tool, mock_confirm):
    # Mock approvals:
    # 1st confirm: Planner write_file plan.md -> True
    # 2nd confirm: Do you approve plan.md? -> True
    # 3rd confirm: Coder edit_file logic -> True
    mock_confirm.side_effect = [True, True, True]
    
    def mock_run_tool_impl(name, **kwargs):
        if name == "write_file" and kwargs.get("path") == "plan.md":
            with open("plan.md", "w", encoding="utf-8") as f:
                f.write(kwargs.get("content", ""))
            return "Success: plan.md written"
        elif name == "edit_file":
            return "Success: logic updated"
        return "Success"

    mock_run_tool.side_effect = mock_run_tool_impl
    
    config = Config(
        provider="gemini",
        gemini_api_key="fake",
        gemini_model="gemini-3.5-flash",
        groq_api_key=None,
        groq_model="llama-3.3-70b-versatile",
        max_tokens=4096,
        verify_cmd="pytest tests/dummy_test.py", # mock verify command
    )
    mock_client = MagicMock(spec=LLMClient)
    mock_client.config = config

    # Mock client stream calls for each agent phase:
    # 1. Researcher -> yields context report
    # 2. Planner -> tool call write_file plan.md
    # 3. Planner -> text summary
    # 4. Coder -> tool call edit_file
    # 5. Coder -> text summary
    mock_client.stream.side_effect = [
        iter(["We found clean_file.py in the repository."]), # Researcher
        iter(['<tool_call name="write_file" path="plan.md"># Plan\n\n## Verification\n```bash\npytest tests/dummy_test.py\n```\n</tool_call>']), # Planner tool call
        iter(["I have created plan.md for implementing the task."]), # Planner text
        iter(['<tool_call name="edit_file" path="clean_file.py"><old_content>1</old_content><new_content>2</new_content></tool_call>']), # Coder tool call
        iter(["Completed logic updates on clean_file.py."]), # Coder text
    ]

    # Mock verify command to return exit code 0 (success)
    mock_run_verify = MagicMock(return_value=(0, "All tests passed."))
    
    if os.path.exists("plan.md"):
        os.remove("plan.md")

    # Physicall write plan.md to avoid file read failure
    with open("plan.md", "w", encoding="utf-8") as f:
        f.write("# Plan\n\n## Verification\n```bash\npytest tests/dummy_test.py\n```\n")

    try:
        with patch("agent.correction.run_verification_command", mock_run_verify):
            res = run_multi_agent_session(mock_client, "Fix math bugs")
            assert "Task completed and verified successfully" in res
            assert mock_confirm.call_count == 3
            mock_run_verify.assert_called_with("pytest tests/dummy_test.py")
    finally:
        if os.path.exists("plan.md"):
            os.remove("plan.md")
