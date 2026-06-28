# tests/test_two_pass_pipeline.py
"""Unit tests for the two-pass prose and code generation pipeline.

Validates Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 4.5
"""
import unittest
from unittest.mock import patch, MagicMock, call

from local_coder.two_pass import (
    execute_two_pass,
    TwoPassResult,
    PROSE_MODEL,
    FAST_MODEL,
    HEAVY_MODEL,
    _extract_eval_count,
)
from local_coder.ollama_client import OllamaError


# Prose output with TODO placeholders (clean — no hallucinations)
CLEAN_PROSE = """\
# My Document

Here is some explanation text.

```python
# TODO: Implement the main function
```

More prose explaining the design.

```python
# TODO: Implement the helper class
```
"""

# Final code output from Pass 2
CODE_OUTPUT = """\
# My Document

Here is some explanation text.

```python
def main():
    print("Hello, world!")
```

More prose explaining the design.

```python
class Helper:
    pass
```
"""


def _make_response(text: str, eval_count: int | None = 150, total_duration: int = 5_000_000_000) -> dict:
    """Helper to build an Ollama response dict."""
    result = {"response": text, "total_duration": total_duration}
    if eval_count is not None:
        result["eval_count"] = eval_count
    return result


class TestTwoPassPipeline(unittest.TestCase):
    """Unit tests for execute_two_pass()."""

    @patch("local_coder.two_pass.call_ollama")
    def test_pass1_no_context_files(self, mock_call_ollama):
        """Pass 1 calls call_ollama with context_files=None (Req 7.1)."""
        mock_call_ollama.side_effect = [
            _make_response(CLEAN_PROSE, eval_count=100),
            _make_response(CODE_OUTPUT, eval_count=200),
        ]

        execute_two_pass(
            task="Write a document",
            context_files=["src/module.py", "src/utils.py"],
        )

        # First call is Pass 1 — must have context_files=None
        first_call = mock_call_ollama.call_args_list[0]
        self.assertIsNone(first_call.kwargs.get("context_files"))

    @patch("local_coder.two_pass.call_ollama")
    def test_pass2_has_context_files(self, mock_call_ollama):
        """Pass 2 calls call_ollama with the actual context_files list (Req 7.2)."""
        context = ["src/module.py", "src/utils.py"]
        mock_call_ollama.side_effect = [
            _make_response(CLEAN_PROSE, eval_count=100),
            _make_response(CODE_OUTPUT, eval_count=200),
        ]

        execute_two_pass(
            task="Write a document",
            context_files=context,
        )

        # Second call is Pass 2 — must have the real context_files
        self.assertEqual(len(mock_call_ollama.call_args_list), 2)
        second_call = mock_call_ollama.call_args_list[1]
        self.assertEqual(second_call.kwargs.get("context_files"), context)

    @patch("local_coder.two_pass.call_ollama")
    @patch("local_coder.two_pass.scan_for_hallucinations")
    def test_escalation_on_more_than_3_hallucination_violations(
        self, mock_scan, mock_call_ollama
    ):
        """When Pass 1 has >3 violations, escalate immediately (Req 7.5)."""
        from local_coder.hallucination_guard import ScanResult, BannedPattern

        pattern = BannedPattern("import_statement", MagicMock(), "Import statement")
        mock_scan.return_value = ScanResult(
            violations=[
                (1, "import os", pattern),
                (2, "import sys", pattern),
                (3, "from json import loads", pattern),
                (4, "import collections", pattern),
            ],
            total_count=4,
            should_abort=True,
        )

        # Pass 1 returns prose with hallucinations
        prose_with_hallucinations = (
            "import os\nimport sys\nfrom json import loads\nimport collections\n"
            "# TODO: Implement function\n"
        )
        mock_call_ollama.return_value = _make_response(prose_with_hallucinations, eval_count=50)

        result = execute_two_pass(
            task="Write a document",
            context_files=["src/module.py"],
        )

        # Should escalate — Pass 2 never called
        self.assertTrue(result.escalated)
        self.assertIn("Hallucination guardrail", result.escalation_reason)
        self.assertEqual(mock_call_ollama.call_count, 1)

    @patch("local_coder.two_pass.call_ollama")
    @patch("local_coder.two_pass.remove_violations")
    @patch("local_coder.two_pass.scan_for_hallucinations")
    def test_violation_removal_on_3_or_fewer(
        self, mock_scan, mock_remove, mock_call_ollama
    ):
        """When Pass 1 has ≤3 violations, remove them before Pass 2 (Req 9.4)."""
        from local_coder.hallucination_guard import ScanResult, BannedPattern

        pattern = BannedPattern("import_statement", MagicMock(), "Import statement")

        prose_with_violations = (
            "import os\n"
            "# My Document\n"
            "from sys import exit\n"
            "# TODO: Implement function\n"
        )

        # Scan returns 2 violations (should NOT abort)
        mock_scan.return_value = ScanResult(
            violations=[
                (1, "import os", pattern),
                (3, "from sys import exit", pattern),
            ],
            total_count=2,
            should_abort=False,
        )

        # remove_violations returns the cleaned prose
        cleaned_prose = "# My Document\n# TODO: Implement function\n"
        mock_remove.return_value = cleaned_prose

        mock_call_ollama.side_effect = [
            _make_response(prose_with_violations, eval_count=80),
            _make_response(CODE_OUTPUT, eval_count=200),
        ]

        result = execute_two_pass(
            task="Write a document",
            context_files=["src/module.py"],
        )

        # remove_violations was called
        mock_remove.assert_called_once_with(prose_with_violations, mock_scan.return_value)

        # Pass 2 prompt should contain the cleaned prose (no violation lines)
        second_call = mock_call_ollama.call_args_list[1]
        pass2_prompt = second_call.kwargs.get("prompt")
        self.assertIn("# My Document", pass2_prompt)
        self.assertIn("# TODO: Implement function", pass2_prompt)
        self.assertNotIn("import os", pass2_prompt)
        self.assertNotIn("from sys import exit", pass2_prompt)

        # Should NOT escalate
        self.assertFalse(result.escalated)

    @patch("local_coder.two_pass.call_ollama")
    def test_happy_path_prose_to_code(self, mock_call_ollama):
        """Normal flow: prose with TODOs → code output, no escalation."""
        mock_call_ollama.side_effect = [
            _make_response(CLEAN_PROSE, eval_count=100),
            _make_response(CODE_OUTPUT, eval_count=200),
        ]

        result = execute_two_pass(
            task="Write a document",
            context_files=["src/module.py"],
        )

        self.assertFalse(result.escalated)
        self.assertIsNone(result.escalation_reason)
        self.assertEqual(result.final_output, CODE_OUTPUT)
        self.assertEqual(result.pass1_model, PROSE_MODEL)
        self.assertEqual(result.pass2_model, FAST_MODEL)

    @patch("local_coder.two_pass.call_ollama")
    def test_pass1_ollama_error_escalates(self, mock_call_ollama):
        """Pass 1 OllamaError → escalate immediately (Req 7.5)."""
        mock_call_ollama.side_effect = OllamaError("Connection refused")

        result = execute_two_pass(
            task="Write a document",
            context_files=["src/module.py"],
        )

        self.assertTrue(result.escalated)
        self.assertIn("Pass 1 OllamaError", result.escalation_reason)
        self.assertEqual(result.final_output, "")

    @patch("local_coder.two_pass.call_ollama")
    def test_pass2_ollama_error_retry_succeeds(self, mock_call_ollama):
        """Pass 2 fails once, retry succeeds → no escalation."""
        # Pass 1 succeeds, Pass 2 fails first try, retry succeeds
        mock_call_ollama.side_effect = [
            _make_response(CLEAN_PROSE, eval_count=100),  # Pass 1 OK
            OllamaError("Timeout"),                        # Pass 2 first try fails
            _make_response(CODE_OUTPUT, eval_count=200),   # Pass 2 retry succeeds
        ]

        result = execute_two_pass(
            task="Write a document",
            context_files=["src/module.py"],
        )

        self.assertFalse(result.escalated)
        self.assertEqual(result.final_output, CODE_OUTPUT)
        self.assertEqual(mock_call_ollama.call_count, 3)

    @patch("local_coder.two_pass.call_ollama")
    def test_pass2_ollama_error_retry_fails_escalates(self, mock_call_ollama):
        """Pass 2 fails on both tries → escalate."""
        # Pass 1 succeeds, Pass 2 fails twice
        mock_call_ollama.side_effect = [
            _make_response(CLEAN_PROSE, eval_count=100),  # Pass 1 OK
            OllamaError("Timeout"),                        # Pass 2 first try fails
            OllamaError("Timeout 2"),                      # Pass 2 retry fails
        ]

        result = execute_two_pass(
            task="Write a document",
            context_files=["src/module.py"],
        )

        self.assertTrue(result.escalated)
        self.assertIn("Pass 2 OllamaError after retry", result.escalation_reason)
        self.assertEqual(mock_call_ollama.call_count, 3)

    @patch("local_coder.two_pass.call_ollama")
    def test_code_complexity_selects_heavy_model(self, mock_call_ollama):
        """code_complexity='complex' selects the HEAVY_MODEL for Pass 2."""
        mock_call_ollama.side_effect = [
            _make_response(CLEAN_PROSE, eval_count=100),
            _make_response(CODE_OUTPUT, eval_count=300),
        ]

        result = execute_two_pass(
            task="Write a document",
            context_files=["src/module.py"],
            code_complexity="complex",
        )

        self.assertEqual(result.pass2_model, HEAVY_MODEL)
        # Pass 2 should call with the heavy model
        second_call = mock_call_ollama.call_args_list[1]
        self.assertEqual(second_call.kwargs.get("model"), HEAVY_MODEL)

    @patch("local_coder.two_pass.call_ollama")
    def test_token_tracking_separate_pass1_pass2(self, mock_call_ollama):
        """Token counts are recorded separately for Pass 1 and Pass 2 (Req 4.5)."""
        mock_call_ollama.side_effect = [
            _make_response(CLEAN_PROSE, eval_count=120),
            _make_response(CODE_OUTPUT, eval_count=350),
        ]

        result = execute_two_pass(
            task="Write a document",
            context_files=["src/module.py"],
        )

        self.assertEqual(result.pass1_eval_count, 120)
        self.assertEqual(result.pass2_eval_count, 350)

    @patch("local_coder.two_pass.call_ollama")
    def test_token_fallback_when_eval_count_missing(self, mock_call_ollama):
        """When eval_count is missing, fallback estimation is used (Req 4.2)."""
        # Pass 1: no eval_count key, Pass 2: eval_count=0
        mock_call_ollama.side_effect = [
            {"response": CLEAN_PROSE, "total_duration": 3_000_000_000},
            {"response": CODE_OUTPUT, "eval_count": 0, "total_duration": 5_000_000_000},
        ]

        result = execute_two_pass(
            task="Write a document",
            context_files=["src/module.py"],
        )

        # Pass 1: estimated from text length
        expected_pass1 = len(CLEAN_PROSE) // 4
        self.assertEqual(result.pass1_eval_count, expected_pass1)

        # Pass 2: eval_count=0 triggers fallback
        expected_pass2 = len(CODE_OUTPUT) // 4
        self.assertEqual(result.pass2_eval_count, expected_pass2)

    @patch("local_coder.two_pass.call_ollama")
    def test_token_from_successful_retry_not_failed(self, mock_call_ollama):
        """Fallback chain records tokens from successful model, not failed one (Req 4.4)."""
        # Pass 1 succeeds, Pass 2 fails first, retry succeeds with different token count
        mock_call_ollama.side_effect = [
            _make_response(CLEAN_PROSE, eval_count=100),    # Pass 1 OK
            OllamaError("Timeout"),                          # Pass 2 first try fails
            _make_response(CODE_OUTPUT, eval_count=250),     # Pass 2 retry succeeds
        ]

        result = execute_two_pass(
            task="Write a document",
            context_files=["src/module.py"],
        )

        # Pass 2 tokens come from the successful retry, not the failed attempt
        self.assertEqual(result.pass2_eval_count, 250)
        self.assertFalse(result.escalated)


class TestExtractEvalCount(unittest.TestCase):
    """Unit tests for _extract_eval_count helper."""

    def test_returns_eval_count_when_present(self):
        result = {"eval_count": 500, "response": "hello"}
        self.assertEqual(_extract_eval_count(result, "hello"), 500)

    def test_falls_back_when_eval_count_none(self):
        result = {"response": "hello world this is test"}
        text = "hello world this is test"
        expected = len(text) // 4
        self.assertEqual(_extract_eval_count(result, text), expected)

    def test_falls_back_when_eval_count_zero(self):
        result = {"eval_count": 0, "response": "some response text"}
        text = "some response text"
        expected = len(text) // 4
        self.assertEqual(_extract_eval_count(result, text), expected)


if __name__ == "__main__":
    unittest.main()
