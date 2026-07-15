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
    # The client will stream once to execute a tool, and we will feed it back the error output.
    # The second streaming turn will return the final explanation response.
    mock_client.stream.side_effect = [
        iter(['<tool_call name="view_file" path="test.txt" />']),
        iter(['Tool execution was cancelled, so I stopped.'])
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
    
    assert response == "Tool execution was cancelled, so I stopped."
    mock_run_tool.assert_not_called()
    assert mock_client.stream.call_count == 2
    mock_confirm.assert_called_once_with("Do you want to execute this tool call?", default=True)

