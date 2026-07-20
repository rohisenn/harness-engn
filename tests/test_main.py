import pytest
from main import parse_tool_call, run_single_turn
from unittest.mock import MagicMock, patch
from agent.llm import LLMClient
from agent.config import Config


def test_parse_tool_call():
    # Valid inline syntax
    res = parse_tool_call('<tool_call name="view_file" path="agent/llm.py" />')
    assert res == ("view_file", {"path": "agent/llm.py"})

    res = parse_tool_call('<tool_call name="list_dir" path="." />')
    assert res == ("list_dir", {"path": "."})

    res = parse_tool_call('<tool_call name="list_dir" />')
    assert res == ("list_dir", {})

    # Valid write_file block syntax
    res = parse_tool_call(
        '<tool_call name="write_file" path="temp.txt">\n'
        'line 1\n'
        'line 2\n'
        '</tool_call>'
    )
    assert res == ("write_file", {"path": "temp.txt", "content": "line 1\nline 2"})

    # Valid edit_file block syntax
    res = parse_tool_call(
        '<tool_call name="edit_file" path="temp.py">\n'
        '<old_content>\n'
        'def old():\n'
        '    pass\n'
        '</old_content>\n'
        '<new_content>\n'
        'def new():\n'
        '    pass\n'
        '</new_content>\n'
        '</tool_call>'
    )
    assert res == (
        "edit_file",
        {
            "path": "temp.py",
            "old_content": "\ndef old():\n    pass\n",
            "new_content": "\ndef new():\n    pass\n"
        }
    )

    # No tag
    res = parse_tool_call('Hello from model')
    assert res is None

    # Missing name
    res = parse_tool_call('<tool_call path="abc" />')
    assert res is None

    # Edge cases: attribute order reversed
    res = parse_tool_call('<tool_call path="agent/llm.py" name="view_file" />')
    assert res == ("view_file", {"path": "agent/llm.py"})

    # Edge cases: spaces around equals
    res = parse_tool_call('<tool_call name = "list_dir" path = "." />')
    assert res == ("list_dir", {"path": "."})

    # Edge cases: extra attributes
    res = parse_tool_call('<tool_call name="list_dir" path="." depth="2" />')
    assert res == ("list_dir", {"path": ".", "depth": "2"})

    # Edge cases: block tool call with attributes reversed & spaces
    res = parse_tool_call(
        '<tool_call path = "temp.txt" name = "write_file" mode = "overwrite">\n'
        'line 1\n'
        '</tool_call>'
    )
    assert res == ("write_file", {"path": "temp.txt", "content": "line 1", "mode": "overwrite"})



@patch("main.run_tool")
@patch("click.confirm")
def test_run_single_turn_with_tool(mock_confirm, mock_run_tool):
    # Mock click.confirm to return True to bypass manual interaction
    mock_confirm.return_value = True
    
    # Setup LLMClient mock that streams a tool call then a plain response
    mock_client = MagicMock(spec=LLMClient)
    mock_client.stream.side_effect = [
        iter(['<tool_call name="view_file" path="test.txt" />']),
        iter(['This is the file content summary.'])
    ]
    mock_client.config = Config(
        provider="gemini",
        gemini_api_key="fake",
        gemini_model="gemini-3.5-flash",
        groq_api_key=None,
        groq_model="llama-3.3-70b-versatile",
        max_tokens=4096,
    )
    
    mock_run_tool.return_value = "Content of test.txt"

    response = run_single_turn(mock_client, "Read test.txt")
    
    assert response == "This is the file content summary."
    mock_run_tool.assert_called_once_with("view_file", path="test.txt")
    assert mock_client.stream.call_count == 2
    mock_confirm.assert_called_once_with("Do you want to execute this tool call?", default=True)


@patch("main.run_tool")
@patch("click.confirm")
def test_run_single_turn_with_tool_rejected(mock_confirm, mock_run_tool):
    # Mock click.confirm to return False to simulate user rejection
    mock_confirm.return_value = False
    
    mock_client = MagicMock(spec=LLMClient)
    # The client will only stream once because the loop breaks immediately on tool rejection.
    mock_client.stream.side_effect = [
        iter(['<tool_call name="view_file" path="test.txt" />'])
    ]
    mock_client.config = Config(
        provider="gemini",
        gemini_api_key="fake",
        gemini_model="gemini-3.5-flash",
        groq_api_key=None,
        groq_model="llama-3.3-70b-versatile",
        max_tokens=4096,
    )
    
    response = run_single_turn(mock_client, "Read test.txt")
    
    assert response == "Tool execution cancelled by the user."
    mock_run_tool.assert_not_called()
    assert mock_client.stream.call_count == 1
    mock_confirm.assert_called_once_with("Do you want to execute this tool call?", default=True)

