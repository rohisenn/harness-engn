import os
import subprocess
import pytest
from tools.git_tool import (
    git_status,
    git_diff,
    git_add,
    git_commit,
    git_checkout,
    git_push
)

@pytest.fixture
def temp_git_repo(tmp_path, monkeypatch):
    # Change working directory to tmp_path so git commands run inside the temp folder
    monkeypatch.chdir(tmp_path)
    
    # Initialize repository
    subprocess.run(["git", "init"], check=True)
    
    # Configure mock user for commits
    subprocess.run(["git", "config", "user.name", "Test User"], check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], check=True)
    
    # Git default branch name config (avoid warning)
    subprocess.run(["git", "config", "init.defaultBranch", "main"], check=True)
    
    # Create an initial commit so checking out/diffing works cleanly
    test_file = tmp_path / "init.txt"
    test_file.write_text("initial content", encoding="utf-8")
    subprocess.run(["git", "add", "init.txt"], check=True)
    subprocess.run(["git", "commit", "-m", "initial commit"], check=True)
    subprocess.run(["git", "branch", "-M", "main"], check=True)
    
    return tmp_path

def test_git_status_untracked(temp_git_repo):
    # Create a new untracked file
    untracked_file = temp_git_repo / "untracked.py"
    untracked_file.write_text("print('hello')", encoding="utf-8")
    
    res = git_status()
    assert "untracked.py" in res

def test_git_add_and_commit(temp_git_repo):
    new_file = temp_git_repo / "feature.py"
    new_file.write_text("x = 10", encoding="utf-8")
    
    # 1. Add file
    add_res = git_add(["feature.py"])
    assert "Success: Added paths" in add_res
    
    # Verify staged via status
    status_res = git_status()
    assert "Changes to be committed" in status_res
    assert "feature.py" in status_res
    
    # 2. Commit file
    commit_res = git_commit("add feature file")
    assert "Success: Changes committed" in commit_res
    
    # Verify status is clean regarding feature.py
    assert "feature.py" not in git_status()

def test_git_add_security(temp_git_repo):
    # Creating a sensitive file
    env_file = temp_git_repo / ".env"
    env_file.write_text("API_KEY=123", encoding="utf-8")
    
    # Staging .env should fail due to is_sensitive_path
    res = git_add([".env"])
    assert "Error: Access to sensitive path" in res

def test_git_diff_success(temp_git_repo):
    # Modify the initial file
    init_file = temp_git_repo / "init.txt"
    init_file.write_text("modified content", encoding="utf-8")
    
    res = git_diff("init.txt")
    assert "modified content" in res
    assert "-initial content" in res

def test_git_diff_security(temp_git_repo):
    # Accessing sensitive paths should be blocked
    res = git_diff(".env")
    assert "Error: Access to sensitive path" in res

def test_git_checkout_branch(temp_git_repo):
    # Create and checkout branch dev
    checkout_res = git_checkout("dev", create=True)
    assert "Success: Switched to branch 'dev'" in checkout_res
    
    # Verify we are on dev branch
    status = git_status()
    assert "On branch dev" in status

def test_git_push_local(temp_git_repo, tmp_path):
    # Create a bare remote repository in the parent folder
    remote_path = tmp_path.parent / "remote.git"
    subprocess.run(["git", "init", "--bare", str(remote_path)], check=True)
    
    # Link local repository to the mock remote
    subprocess.run(["git", "remote", "add", "origin", str(remote_path)], check=True)
    
    # Push to origin main
    push_res = git_push("main")
    assert "Success: Pushed changes to remote 'origin'" in push_res
