"""
Test module for export_zip_md.py
"""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch

# Import the functions we want to test
from export_zip_md import (
    _load_gitignore_patterns,
    _should_ignore,
    _get_directory_tree,
    _file_priority,
    _lang_for,
    _compute_sha1,
    export_repository_md,
    export_repository_zip,
    _parse_args,
)


class TestExportZipMd:
    """Test cases for export_zip_md.py functions."""

    def test_load_gitignore_patterns(self):
        """Test _load_gitignore_patterns function."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            gitignore_path = tmp_path / ".gitignore"
            gitignore_path.write_text("*.log\n__pycache__\n")

            # Test loading gitignore patterns
            gitignore_spec = _load_gitignore_patterns(tmp_path)
            assert gitignore_spec is not None

            # Test with non-existent .gitignore
            with tempfile.TemporaryDirectory() as tmpdir2:
                tmp_path2 = Path(tmpdir2)
                gitignore_spec = _load_gitignore_patterns(tmp_path2)
                assert gitignore_spec is None

    def test_should_ignore_gitignore(self):
        """Test _should_ignore function with gitignore patterns."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            gitignore_path = tmp_path / ".gitignore"
            gitignore_path.write_text("*.log\n")

            # Create a mock gitignore spec
            from pathspec import PathSpec

            gitignore_spec = PathSpec.from_lines("gitwildmatch", ["*.log"])

            # Test ignoring .log files
            log_file = tmp_path / "test.log"
            assert _should_ignore(log_file, [], None, gitignore_spec, tmp_path)

            # Test not ignoring other files
            py_file = tmp_path / "test.py"
            assert not _should_ignore(py_file, [], None, gitignore_spec, tmp_path)

    def test_should_ignore_patterns(self):
        """Test _should_ignore function with ignore patterns."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)

            # Test ignoring __pycache__ directories
            pycache_dir = tmp_path / "__pycache__"
            pycache_dir.mkdir()
            assert _should_ignore(pycache_dir, ["__pycache__"], None, None, tmp_path)

            # Test ignoring .git directories
            git_dir = tmp_path / ".git"
            git_dir.mkdir()
            assert _should_ignore(git_dir, [".git"], None, None, tmp_path)

    def test_get_directory_tree(self):
        """Test _get_directory_tree function."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)

            # Create some test files and directories
            subdir = tmp_path / "subdir"
            subdir.mkdir()
            test_file = subdir / "test.py"
            test_file.write_text("print('hello')")

            # Test directory tree generation
            tree = _get_directory_tree(tmp_path, "", [], None, None)
            assert "subdir" in tree
            assert "test.py" in tree

    def test_file_priority(self):
        """Test _file_priority function."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)

            # Test README.md priority (should be 0)
            readme = tmp_path / "README.md"
            assert _file_priority(readme) == 0

            # Test Python file priority (should be 1)
            py_file = tmp_path / "test.py"
            assert _file_priority(py_file) == 1

            # Test HTML file priority (should be 2)
            html_file = tmp_path / "test.html"
            assert _file_priority(html_file) == 2

            # Test unknown file priority (should be 5)
            unknown_file = tmp_path / "test.unknown"
            assert _file_priority(unknown_file) == 5

    def test_lang_for(self):
        """Test _lang_for function."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)

            # Test Python language
            py_file = tmp_path / "test.py"
            assert _lang_for(py_file) == "python"

            # Test HTML language
            html_file = tmp_path / "test.html"
            assert _lang_for(html_file) == "html"

            # Test unknown language
            unknown_file = tmp_path / "test.unknown"
            assert _lang_for(unknown_file) == "text"

    def test_compute_sha1(self):
        """Test _compute_sha1 function."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            test_file = tmp_path / "test.txt"
            test_file.write_text("hello world")

            # Test SHA1 computation
            sha1 = _compute_sha1(test_file)
            assert sha1 is not None
            assert isinstance(sha1, str)
            assert len(sha1) == 40  # SHA1 is 40 characters

            # Test with non-existent file
            non_existent = tmp_path / "non_existent.txt"
            assert _compute_sha1(non_existent) is None

    @patch("export_zip_md._load_gitignore_patterns")
    def test_export_repository_md(self, mock_load_gitignore):
        """Test export_repository_md function."""
        mock_load_gitignore.return_value = None

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            output_file = tmp_path / "export.md"

            # Create a test Python file
            py_file = tmp_path / "test.py"
            py_file.write_text("print('hello')")

            # Test markdown export
            export_repository_md(tmp_path, output_file)

            # Check that the output file was created
            assert output_file.exists()

            # Check that the output file has content
            content = output_file.read_text()
            assert "# Repository Export" in content
            assert "test.py" in content

    @patch("export_zip_md._load_gitignore_patterns")
    def test_export_repository_zip(self, mock_load_gitignore):
        """Test export_repository_zip function."""
        mock_load_gitignore.return_value = None

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            output_zip = tmp_path / "export.zip"

            # Create a test Python file
            py_file = tmp_path / "test.py"
            py_file.write_text("print('hello')")

            # Test zip export
            export_repository_zip(tmp_path, output_zip)

            # Check that the output zip was created
            assert output_zip.exists()

    def test_parse_args(self):
        """Test _parse_args function."""
        # Test default arguments
        args = _parse_args([])
        assert args.path == "."
        assert args.as_zip is False

        # Test zip argument
        args = _parse_args(["-zip"])
        assert args.as_zip is True


if __name__ == "__main__":
    pytest.main([__file__])
