import os
import subprocess
import pytest
from unittest.mock import MagicMock, patch
from agent.config import Config
from agent.llm import LLMClient
from main import setup_git_branch, handle_git_success, sanitize_branch_name

@pytest.fixture
def temp_git_repo(tmp_path, monkeypatch):
    # Change working directory to tmp_path so git commands run inside the temp folder
    monkeypatch.chdir(tmp_path)
    
    # Initialize repository
    subprocess.run(["git", "init"], check=True)
    
    # Configure mock user for commits
    subprocess.run(["git", "config", "user.name", "Test User"], check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], check=True)
    
    # Git default branch name config
    subprocess.run(["git", "config", "init.defaultBranch", "main"], check=True)
    
    # Create an initial commit so branch switching/diffing works
    test_file = tmp_path / "init.txt"
    test_file.write_text("initial content", encoding="utf-8")
    subprocess.run(["git", "add", "init.txt"], check=True)
    subprocess.run(["git", "commit", "-m", "initial commit"], check=True)
    subprocess.run(["git", "branch", "-M", "main"], check=True)
    
    return tmp_path

def test_sanitize_branch_name():
    assert sanitize_branch_name("Fix a critical BUG in parsing!") == "fix-a-critical-bug-in-parsing"
    assert sanitize_branch_name("  spaces  and --- dashes  ") == "spaces-and-dashes"
    # Length limit (30 chars)
    assert len(sanitize_branch_name("this-is-a-very-long-task-description-that-exceeds-thirty-characters")) == 30

def test_setup_git_branch(temp_git_repo):
    config = Config(
        provider="gemini",
        gemini_api_key="fake",
        gemini_model="gemini-3.5-flash",
        groq_api_key=None,
        groq_model="llama-3.3-70b-versatile",
        max_tokens=4096,
        git_integration=True,
        git_branch_prefix="harness-test/"
    )
    
    branch_name = setup_git_branch(config, "Implement testing feature")
    assert branch_name.startswith("harness-test/task-")
    
    # Verify active branch
    res = subprocess.run(["git", "branch", "--show-current"], capture_output=True, text=True)
    assert res.stdout.strip() == branch_name

def test_handle_git_success_commit(temp_git_repo):
    config = Config(
        provider="gemini",
        gemini_api_key="fake",
        gemini_model="gemini-3.5-flash",
        groq_api_key=None,
        groq_model="llama-3.3-70b-versatile",
        max_tokens=4096,
        git_integration=True,
    )
    mock_client = MagicMock(spec=LLMClient)
    mock_client.config = config
    
    # Stub client stream to return formatted XML
    xml_response = (
        "<commit_message>feat: add main integration logic</commit_message>\n"
        "<pr_description>\n"
        "# Integration Pull Request\n\n"
        "Testing git integration automation.\n"
        "</pr_description>"
    )
    mock_client.stream.return_value = iter([xml_response])
    
    # Create changes in repo
    new_file = temp_git_repo / "new_module.py"
    new_file.write_text("print('hello integrations')", encoding="utf-8")
    
    # Run helper
    mock_console = MagicMock()
    handle_git_success(mock_client, mock_console)
    
    # 1. Assert git commit message is matching
    res_log = subprocess.run(["git", "log", "-1", "--pretty=%B"], capture_output=True, text=True)
    assert "feat: add main integration logic" in res_log.stdout
    
    # 2. Assert PR_DESCRIPTION.md was written
    pr_file = temp_git_repo / "PR_DESCRIPTION.md"
    assert pr_file.exists()
    content = pr_file.read_text(encoding="utf-8")
    assert "# Integration Pull Request" in content
    assert "Testing git integration automation." in content

def test_handle_git_success_no_changes(temp_git_repo):
    config = Config(
        provider="gemini",
        gemini_api_key="fake",
        gemini_model="gemini-3.5-flash",
        groq_api_key=None,
        groq_model="llama-3.3-70b-versatile",
        max_tokens=4096,
        git_integration=True,
    )
    mock_client = MagicMock(spec=LLMClient)
    mock_client.config = config
    mock_console = MagicMock()
    
    handle_git_success(mock_client, mock_console)
    
    # Verify print was called informing no changes
    mock_console.print.assert_any_call("[yellow]Git: No modified files to commit.[/yellow]")


def test_handle_git_success_commit_and_push(temp_git_repo):
    config = Config(
        provider="gemini",
        gemini_api_key="fake",
        gemini_model="gemini-3.5-flash",
        groq_api_key=None,
        groq_model="llama-3.3-70b-versatile",
        max_tokens=4096,
        git_integration=True,
        git_push=True,
    )
    mock_client = MagicMock(spec=LLMClient)
    mock_client.config = config

    # Stub client stream to return formatted XML
    xml_response = (
        "<commit_message>feat: add push test logic</commit_message>\n"
        "<pr_description>\n"
        "# Integration Push Test\n\n"
        "Testing remote push logic.\n"
        "</pr_description>"
    )
    mock_client.stream.return_value = iter([xml_response])

    # Create changes in repo
    new_file = temp_git_repo / "pushed_module.py"
    new_file.write_text("print('push me')", encoding="utf-8")

    mock_console = MagicMock()

    # Mock subprocess.run for git push specifically, while letting other git commands run
    orig_run = subprocess.run
    def mock_run_cmd(args, **kwargs):
        if "push" in args:
            # Mock success of push
            return MagicMock(returncode=0, stdout="Pushed successfully", stderr="")
        return orig_run(args, **kwargs)

    with patch("subprocess.run", side_effect=mock_run_cmd):
        handle_git_success(mock_client, mock_console)

    # Verify commit log matches
    res_log = orig_run(["git", "log", "-1", "--pretty=%B"], capture_output=True, text=True)
    assert "feat: add push test logic" in res_log.stdout

    # Verify console output indicates success push
    mock_console.print.assert_any_call("[bold green]Git: Successfully pushed branch 'main' to remote![/bold green]")

