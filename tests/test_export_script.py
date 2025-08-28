"""
Test module for export_script.py
"""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch

# Import the functions we want to test
from export_script import (
    load_gitignore_patterns,
    should_ignore,
    get_directory_tree,
    read_file_content,
    get_file_extension_priority,
    get_language_from_extension,
    export_repository,
)


class TestExportScript:
    """Test cases for export_script.py functions."""

    def test_load_gitignore_patterns(self):
        """Test load_gitignore_patterns function."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            gitignore_path = tmp_path / ".gitignore"
            gitignore_path.write_text("*.log\n__pycache__\n")

            # Test loading gitignore patterns
            gitignore_spec = load_gitignore_patterns(tmp_path)
            assert gitignore_spec is not None

            # Test with non-existent .gitignore
            with tempfile.TemporaryDirectory() as tmpdir2:
                tmp_path2 = Path(tmpdir2)
                gitignore_spec = load_gitignore_patterns(tmp_path2)
                assert gitignore_spec is None

    def test_should_ignore_gitignore(self):
        """Test should_ignore function with gitignore patterns."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            gitignore_path = tmp_path / ".gitignore"
            gitignore_path.write_text("*.log\n")

            # Create a mock gitignore spec
            from pathspec import PathSpec

            gitignore_spec = PathSpec.from_lines("gitwildmatch", ["*.log"])

            # Test ignoring .log files
            log_file = tmp_path / "test.log"
            assert should_ignore(log_file, [], None, gitignore_spec, tmp_path)

            # Test not ignoring other files
            py_file = tmp_path / "test.py"
            assert not should_ignore(py_file, [], None, gitignore_spec, tmp_path)

    def test_should_ignore_patterns(self):
        """Test should_ignore function with ignore patterns."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)

            # Test ignoring __pycache__ directories
            pycache_dir = tmp_path / "__pycache__"
            pycache_dir.mkdir()
            assert should_ignore(pycache_dir, ["__pycache__"])

            # Test ignoring .git directories
            git_dir = tmp_path / ".git"
            git_dir.mkdir()
            assert should_ignore(git_dir, [".git"])

    def test_get_directory_tree(self):
        """Test get_directory_tree function."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)

            # Create some test files and directories
            subdir = tmp_path / "subdir"
            subdir.mkdir()
            test_file = subdir / "test.py"
            test_file.write_text("print('hello')")

            # Test directory tree generation
            tree = get_directory_tree(tmp_path)
            assert "subdir" in tree
            assert "test.py" in tree

    def test_read_file_content(self):
        """Test read_file_content function."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)

            # Test reading a text file
            test_file = tmp_path / "test.txt"
            test_content = "Hello, World!"
            test_file.write_text(test_content)

            content = read_file_content(test_file)
            assert content == test_content

            # Test reading a file with encoding errors
            binary_file = tmp_path / "binary.dat"
            binary_file.write_bytes(b"\x80\x81\x82")

            content = read_file_content(binary_file)
            # The function should return the binary content as string "
            # "or an error message
            assert isinstance(content, str)

    def test_get_file_extension_priority(self):
        """Test get_file_extension_priority function."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)

            # Test README.md priority (should be 0)
            readme = tmp_path / "README.md"
            assert get_file_extension_priority(readme) == 0

            # Test Python file priority (should be 1)
            py_file = tmp_path / "test.py"
            assert get_file_extension_priority(py_file) == 1

            # Test HTML file priority (should be 2)
            html_file = tmp_path / "test.html"
            assert get_file_extension_priority(html_file) == 2

            # Test unknown file priority (should be 5)
            unknown_file = tmp_path / "test.unknown"
            assert get_file_extension_priority(unknown_file) == 5

    def test_get_language_from_extension(self):
        """Test get_language_from_extension function."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)

            # Test Python language
            py_file = tmp_path / "test.py"
            assert get_language_from_extension(py_file) == "python"

            # Test HTML language
            html_file = tmp_path / "test.html"
            assert get_language_from_extension(html_file) == "html"

            # Test unknown language
            unknown_file = tmp_path / "test.unknown"
            assert get_language_from_extension(unknown_file) == "text"

    @patch("export_script.load_gitignore_patterns")
    def test_export_repository(self, mock_load_gitignore):
        """Test export_repository function."""
        mock_load_gitignore.return_value = None

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            output_file = tmp_path / "export.md"

            # Create a test Python file
            py_file = tmp_path / "test.py"
            py_file.write_text("print('hello')")

            # Test repository export
            export_repository(tmp_path, str(output_file))

            # Check that the output file was created
            assert output_file.exists()

            # Check that the output file has content
            content = output_file.read_text()
            assert "# Repository Export" in content
            assert "test.py" in content


if __name__ == "__main__":
    pytest.main([__file__])
