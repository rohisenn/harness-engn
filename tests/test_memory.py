import os
import shutil
import pytest
from unittest.mock import MagicMock, patch
from agent.memory import (
    HARNESS_DIR,
    MEMORY_FILE,
    SESSIONS_DIR,
    remember_fact,
    forget_fact,
    load_facts,
    save_facts,
    generate_session_id,
    save_session,
    load_session,
    list_sessions,
)
from tools import run_tool
from main import get_system_prompt

@pytest.fixture(autouse=True)
def setup_clean_harness_dir():
    # Store existing .harness if any, to avoid corrupting user's real memories during test execution
    backed_up = False
    backup_dir = ".harness_backup_test"
    if os.path.exists(HARNESS_DIR):
        if os.path.exists(backup_dir):
            shutil.rmtree(backup_dir)
        shutil.move(HARNESS_DIR, backup_dir)
        backed_up = True
    
    yield

    # Clean up test output
    if os.path.exists(HARNESS_DIR):
        shutil.rmtree(HARNESS_DIR)
        
    # Restore backup
    if backed_up and os.path.exists(backup_dir):
        shutil.move(backup_dir, HARNESS_DIR)

def test_fact_management():
    # Empty at start
    assert load_facts() == []
    
    # Remember first fact
    res1 = remember_fact("This is fact 1")
    assert "Success" in res1
    assert load_facts() == ["This is fact 1"]
    
    # Remember duplicate fact
    res2 = remember_fact("This is fact 1")
    assert "already in memory" in res2
    assert load_facts() == ["This is fact 1"]
    
    # Remember another fact
    remember_fact("Second fact about Python 3.12")
    assert len(load_facts()) == 2
    
    # Forget case-insensitive partial match
    res_forget = forget_fact("python")
    assert "Success" in res_forget
    assert "Second fact about Python 3.12" in res_forget
    assert load_facts() == ["This is fact 1"]
    
    # Forget non-matching query
    res_forget_none = forget_fact("non-existent")
    assert "No matching facts" in res_forget_none

def test_session_lifecycle():
    assert list_sessions() == []
    
    session_id = generate_session_id()
    messages = [{"role": "user", "content": "Hello!"}, {"role": "assistant", "content": "Hi there!"}]
    
    save_session(session_id, messages)
    
    loaded = load_session(session_id)
    assert loaded == messages
    
    sessions = list_sessions()
    assert len(sessions) == 1
    assert sessions[0]["id"] == session_id
    assert sessions[0]["preview"] == "Hello!"
    
    with pytest.raises(FileNotFoundError):
        load_session("invalid_session_id")

def test_security_blocks_harness_dir():
    # General view_file should block accessing .harness dir/files
    res_view = run_tool("view_file", path=".harness/memory.json")
    assert "restricted" in res_view
    
    res_write = run_tool("write_file", path=".harness/malicious.txt", content="hack")
    assert "restricted" in res_write

def test_prompt_injection():
    base_prompt = "You are harness.\nAvailable tools:\n..."
    # With no facts
    assert get_system_prompt(base_prompt) == base_prompt
    
    # With facts
    remember_fact("First fact")
    injected = get_system_prompt(base_prompt)
    assert "[Repository Facts/Memory]:" in injected
    assert "- First fact" in injected
    # Should insert after the first line (intro)
    lines = injected.split("\n")
    assert lines[0] == "You are harness."
    assert lines[1] == ""
    assert lines[2] == "[Repository Facts/Memory]:"
    assert lines[3] == "- First fact"

def test_list_facts_tool():
    # Empty memory
    res_empty = run_tool("list_facts")
    assert "No facts remembered yet" in res_empty
    
    # Non-empty memory
    remember_fact("Fact 1")
    remember_fact("Fact 2")
    res_facts = run_tool("list_facts")
    assert "Repository Facts/Memory:" in res_facts
    assert "- Fact 1" in res_facts
    assert "- Fact 2" in res_facts

