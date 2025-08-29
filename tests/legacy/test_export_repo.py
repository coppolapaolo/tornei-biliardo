"""
Test module for export_repo.py
"""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch

# Import the functions we want to test
from export_repo import (
    _should_ignore,
    _directory_has_source,
    _file_priority,
    _lang_for,
    _flat_name,
    _compute_sha1,
    export_repository_md,
    export_repository_zip,
    _parse_args,
)


class TestExportRepo:
    """Test cases for export_repo.py functions."""

    def test_should_ignore_gitignore(self):
        """Test _should_ignore function with gitignore patterns."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            gitignore_path = tmp_path / ".gitignore"
            gitignore_path.write_text("*.log\n__pycache__\n")

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

    def test_directory_has_source(self):
        """Test _directory_has_source function."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)

            # Create a Python file
            py_file = tmp_path / "test.py"
            py_file.write_text("print('hello')")

            # Test that directory has source files
            assert _directory_has_source(tmp_path, [], None, None, tmp_path)

            # Test directory without source files
            with tempfile.TemporaryDirectory() as tmpdir2:
                tmp_path2 = Path(tmpdir2)
                txt_file = tmp_path2 / "test.txt"
                txt_file.write_text("hello")
                assert not _directory_has_source(tmp_path2, [], None, None, tmp_path2)

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

    def test_flat_name(self):
        """Test _flat_name function."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            subdir = tmp_path / "subdir"
            subdir.mkdir()

            # Test root directory
            assert _flat_name(tmp_path, tmp_path) == "root"

            # Test subdirectory
            assert _flat_name(subdir, tmp_path) == "subdir"

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

    @patch("export_repo._load_gitignore_patterns")
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

    @patch("export_repo._load_gitignore_patterns")
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
        assert args.source_depth is None

        # Test zip argument
        args = _parse_args(["-zip"])
        assert args.as_zip is True

        # Test source argument
        args = _parse_args(["-source", "2"])
        assert args.source_depth == 2


if __name__ == "__main__":
    pytest.main([__file__])
