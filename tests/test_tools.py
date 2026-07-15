import os
import pytest
from tools import run_tool, TOOLS
from tools.view_file import view_file
from tools.list_dir import list_dir


def test_view_file_success(tmp_path):
    # Create a temp file
    temp_file = tmp_path / "test_file.txt"
    temp_file.write_text("Hello, this is a test file contents.", encoding="utf-8")
    
    # Run view_file (using absolute path or relative, since it's within the tmp directory)
    # Note: target_path resolves relative to os.getcwd(). Let's mock/use os.chdir or absolute path check.
    # Wait, the tool has a security check: target_path.startswith(cwd).
    # Since tmp_path is outside the CWD (which is workspace), target_path.startswith(cwd) might fail if traversal prevention is active.
    # Let's check how the traversal check behaves: target_path must start with cwd.
    # Therefore, to test success, the file must be created inside the current working directory, e.g. a temp directory in the workspace!
    # Let's create a temporary test file inside the current working directory (workspace) and clean it up afterwards!
    
    filename = "temp_test_file_success.txt"
    with open(filename, "w", encoding="utf-8") as f:
        f.write("Hello, test success.")
        
    try:
        content = view_file(filename)
        assert content == "Hello, test success."
    finally:
        if os.path.exists(filename):
            os.remove(filename)


def test_view_file_errors():
    # File does not exist
    res = view_file("non_existent_file_xyz.txt")
    assert "Error: File" in res
    assert "does not exist" in res
    
    # Path is directory
    res = view_file("agent")
    assert "Error:" in res
    assert "is a directory" in res

    # Empty path
    res = view_file("")
    assert "Error: Path is empty" in res


def test_list_dir_success():
    # Let's create a temp directory structure inside CWD
    temp_dir = "temp_test_dir"
    os.makedirs(temp_dir, exist_ok=True)
    temp_file = os.path.join(temp_dir, "file1.txt")
    with open(temp_file, "w") as f:
        f.write("data")
        
    os.makedirs(os.path.join(temp_dir, "subdir"), exist_ok=True)
    
    try:
        res = list_dir(temp_dir)
        assert f"Contents of directory '{temp_dir}':" in res
        assert "  [FILE] temp_test_dir/file1.txt" in res
        assert "  [DIR]  temp_test_dir/subdir/" in res
    finally:
        # Clean up
        if os.path.exists(temp_file):
            os.remove(temp_file)
        if os.path.exists(os.path.join(temp_dir, "subdir")):
            os.rmdir(os.path.join(temp_dir, "subdir"))
        if os.path.exists(temp_dir):
            os.rmdir(temp_dir)


def test_list_dir_errors():
    # Directory does not exist
    res = list_dir("non_existent_dir_abc")
    assert "Error: Directory" in res
    assert "does not exist" in res

    # Is not a directory (is a file)
    res = list_dir("main.py")
    assert "Error:" in res
    assert "is not a directory" in res


def test_run_tool_dispatcher():
    # Test execution
    res = run_tool("invalid_tool_name")
    assert "Error: Tool 'invalid_tool_name' not found" in res
    
    # Test valid tool execution (view_file with missing argument or invalid key)
    res = run_tool("view_file", path="non_existent_file_xyz.txt")
    assert "Error: File 'non_existent_file_xyz.txt' does not exist." in res


def test_write_file_and_edit_file():
    filename = "temp_test_write_and_edit.txt"
    if os.path.exists(filename):
        os.remove(filename)
        
    try:
        # 1. Test write_file creates file
        res = run_tool("write_file", path=filename, content="Line 1\nLine 2\nLine 3")
        assert "Success: File" in res
        assert os.path.exists(filename)
        
        # Verify content
        assert view_file(filename) == "Line 1\nLine 2\nLine 3"
        
        # 2. Test edit_file edits successfully (unique match)
        res = run_tool("edit_file", path=filename, old_content="Line 2", new_content="Line Two Changed")
        assert "Success" in res
        assert "replaced 1 block" in res
        assert view_file(filename) == "Line 1\nLine Two Changed\nLine 3"
        
        # 3. Test edit_file fails with 0 occurrences
        res = run_tool("edit_file", path=filename, old_content="Line 5", new_content="Nope")
        assert "Error: The target block 'old_content' was not found" in res
        
        # 4. Test edit_file fails with multiple occurrences
        run_tool("write_file", path=filename, content="hello\nhello\nworld")
        res = run_tool("edit_file", path=filename, old_content="hello", new_content="hi")
        assert "Error: Found 2 occurrences" in res
    finally:
        if os.path.exists(filename):
            os.remove(filename)


def test_write_file_directory_creation():
    dir_path = "temp_sub_dir_for_test"
    filename = os.path.join(dir_path, "sub_file.txt")
    
    if os.path.exists(filename):
        os.remove(filename)
    if os.path.exists(dir_path):
        os.rmdir(dir_path)
        
    try:
        # Verify write_file automatically creates directories
        res = run_tool("write_file", path=filename, content="Subdir content")
        assert "Success" in res
        assert os.path.exists(filename)
        assert view_file(filename) == "Subdir content"
    finally:
        if os.path.exists(filename):
            os.remove(filename)
        if os.path.exists(dir_path):
            os.rmdir(dir_path)


def test_run_command_success():
    res = run_tool("run_command", command="python -c \"print('Hello from test')\"")
    assert "Exit Code: 0" in res
    assert "Standard Output:" in res
    assert "Hello from test" in res


def test_run_command_failure():
    res = run_tool("run_command", command="python -c \"import sys; sys.exit(42)\"")
    assert "Exit Code: 42" in res


def test_run_command_timeout():
    res = run_tool("run_command", command="python -c \"import time; time.sleep(5)\"", timeout=1)
    assert "timed out after 1 seconds" in res


