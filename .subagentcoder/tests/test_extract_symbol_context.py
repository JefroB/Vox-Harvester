"""Smoke tests for extract_symbol_context() — CodeSearch integration."""

from unittest.mock import patch, MagicMock

import pytest

from local_coder.patch_mode import extract_symbol_context, SymbolNotFoundError


class TestExtractSymbolContext:
    """Tests for extract_symbol_context using mocked subprocess."""

    def test_successful_extraction(self):
        """Parses codesearch output with valid header and source code."""
        mock_output = (
            "// File: src/utils.py, Lines: 10-25\n"
            "def validate_email(email: str) -> bool:\n"
            "    \"\"\"Check if email is valid.\"\"\"\n"
            "    return '@' in email\n"
        )
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = mock_output

        with patch("local_coder.patch_mode.subprocess.run", return_value=mock_result) as mock_run:
            source, start, end = extract_symbol_context("validate_email")

        mock_run.assert_called_once_with(
            ["codesearch", "get-symbol-code", "validate_email"],
            capture_output=True,
            text=True,
        )
        assert start == 10
        assert end == 25
        assert "def validate_email" in source
        assert "@" in source

    def test_nonzero_exit_code_raises(self):
        """Raises SymbolNotFoundError when codesearch exits non-zero."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""

        with patch("local_coder.patch_mode.subprocess.run", return_value=mock_result):
            with pytest.raises(SymbolNotFoundError) as exc_info:
                extract_symbol_context("nonexistent_symbol")

        assert exc_info.value.symbol_name == "nonexistent_symbol"

    def test_empty_output_raises(self):
        """Raises SymbolNotFoundError when codesearch returns empty output."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""

        with patch("local_coder.patch_mode.subprocess.run", return_value=mock_result):
            with pytest.raises(SymbolNotFoundError):
                extract_symbol_context("missing_func")

    def test_whitespace_only_output_raises(self):
        """Raises SymbolNotFoundError when output is only whitespace."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "   \n\n  "

        with patch("local_coder.patch_mode.subprocess.run", return_value=mock_result):
            with pytest.raises(SymbolNotFoundError):
                extract_symbol_context("some_func")

    def test_no_header_raises(self):
        """Raises SymbolNotFoundError when output has no recognizable header."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "def foo():\n    pass\n"

        with patch("local_coder.patch_mode.subprocess.run", return_value=mock_result):
            with pytest.raises(SymbolNotFoundError):
                extract_symbol_context("foo")

    def test_multiline_source_code(self):
        """Correctly extracts multi-line source from codesearch output."""
        mock_output = (
            "// File: local_coder/patch_mode.py, Lines: 40-80\n"
            "class EditOperation:\n"
            "    \"\"\"A single search-and-replace edit operation.\"\"\"\n"
            "\n"
            "    old_text: str\n"
            "    new_text: str\n"
            "    index: int\n"
        )
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = mock_output

        with patch("local_coder.patch_mode.subprocess.run", return_value=mock_result):
            source, start, end = extract_symbol_context("EditOperation")

        assert start == 40
        assert end == 80
        assert "class EditOperation:" in source
        assert "old_text: str" in source

    def test_symbol_name_stored_on_error(self):
        """SymbolNotFoundError stores the symbol name for diagnostics."""
        error = SymbolNotFoundError("MyClass.my_method")
        assert error.symbol_name == "MyClass.my_method"
        assert "MyClass.my_method" in str(error)
