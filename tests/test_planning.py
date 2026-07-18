import os
import pytest
from unittest.mock import MagicMock, patch
from tools import run_tool
from main import run_single_turn_with_planning
from agent.llm import LLMClient
from agent.config import Config

def test_sensitive_path_restrictions():
    # Attempting to access sensitive files directly via view_file/write_file/edit_file should fail
    res_view = run_tool("view_file", path=".env")
    assert "Error: Access to sensitive file" in res_view
    
    res_write = run_tool("write_file", path="subdir/.env", content="SECRET")
    assert "Error: Access to sensitive file" in res_write
    
    res_edit = run_tool("edit_file", path=".env.local", old_content="A", new_content="B")
    assert "Error: Access to sensitive file" in res_edit

    res_search_grep_path = run_tool("search_grep", query="something", path=".env")
    assert "Error: Access to sensitive file" in res_search_grep_path

    res_search_files_path = run_tool("search_files", pattern="*", path=".env")
    assert "Error: Access to sensitive file" in res_search_files_path


def test_search_grep_skips_sensitive_files():
    temp_dir = "temp_sensitive_grep_test"
    os.makedirs(temp_dir, exist_ok=True)
    f1 = os.path.join(temp_dir, ".env")
    f2 = os.path.join(temp_dir, "clean_file.txt")
    
    with open(f1, "w", encoding="utf-8") as f:
        f.write("SECRET_KEY=12345")
    with open(f2, "w", encoding="utf-8") as f:
        f.write("SECRET_KEY=public")
        
    try:
        # Search for SECRET_KEY. It should only find the one in clean_file.txt
        res = run_tool("search_grep", query="SECRET_KEY", path=temp_dir)
        assert "clean_file.txt:1: SECRET_KEY=public" in res
        assert ".env" not in res
    finally:
        for f in (f1, f2):
            if os.path.exists(f):
                os.remove(f)
        if os.path.exists(temp_dir):
            os.rmdir(temp_dir)


@patch("click.confirm")
@patch("main.run_tool")
def test_planning_flow_approved(mock_run_tool, mock_confirm):
    # Mock approvals:
    # 1st confirm: tool call write_file plan.md -> True
    # 2nd confirm: Do you approve this plan? -> True
    # 3rd confirm: execute tool call edit_file main.py (in execution) -> True
    mock_confirm.side_effect = [True, True, True]
    
    mock_run_tool.side_effect = [
        "Success: File plan.md written",  # write_file plan.md
        "Success: File edited"             # edit_file main.py
    ]
    
    mock_client = MagicMock(spec=LLMClient)
    mock_client.config = Config(
        provider="gemini",
        gemini_api_key="fake",
        gemini_model="gemini-3.5-flash",
        groq_api_key=None,
        groq_model="llama-3.3-70b-versatile",
        max_tokens=4096,
    )
    
    # LLM streams:
    # 1. Planning phase tool call (write_file plan.md)
    # 2. Planning phase response with no tool calls (plan written)
    # 3. Execution phase tool call (edit_file main.py)
    # 4. Execution phase final explanation
    mock_client.stream.side_effect = [
        iter(['<tool_call name="write_file" path="plan.md"># Plan</tool_call>']),
        iter(['I have generated the plan.']),
        iter(['<tool_call name="edit_file" path="main.py"><old_content>foo</old_content><new_content>bar</new_content></tool_call>']),
        iter(['Execution finished successfully.'])
    ]

    if os.path.exists("plan.md"):
        os.remove("plan.md")
        
    # Physically create plan.md when write_file is called
    with open("plan.md", "w", encoding="utf-8") as f:
        f.write("# Mock Plan")
        
    try:
        response = run_single_turn_with_planning(mock_client, "Do task")
        assert response == "Execution finished successfully."
        assert mock_confirm.call_count == 3
        # First call write_file plan.md
        mock_run_tool.assert_any_call("write_file", path="plan.md", content="# Plan")
        # Second call edit_file main.py
        mock_run_tool.assert_any_call("edit_file", path="main.py", old_content="foo", new_content="bar")
    finally:
        if os.path.exists("plan.md"):
            os.remove("plan.md")
