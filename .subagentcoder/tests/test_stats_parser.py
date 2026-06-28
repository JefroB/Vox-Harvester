"""Unit tests for stats_parser module."""

from local_coder.stats_parser import ExecutionStats, parse_stats_line


class TestParseStatsLine:
    """Tests for parse_stats_line()."""

    def test_parses_valid_stats_line(self):
        stdout = "Generated 847 tokens in 16.2s (52.3 tok/s)"
        result = parse_stats_line(stdout)
        assert result.tokens_generated == 847
        assert result.generation_speed == 52.3

    def test_parses_integer_time_and_speed(self):
        stdout = "1000 tokens in 50s (20 tok/s)"
        result = parse_stats_line(stdout)
        assert result.tokens_generated == 1000
        assert result.generation_speed == 20.0

    def test_parses_stats_embedded_in_larger_output(self):
        stdout = (
            "Loading model...\n"
            "Generating response...\n"
            "Done. 2341 tokens in 125.2s (18.7 tok/s)\n"
            "Model unloaded.\n"
        )
        result = parse_stats_line(stdout)
        assert result.tokens_generated == 2341
        assert result.generation_speed == 18.7

    def test_returns_none_when_pattern_not_found(self):
        stdout = "No stats here, just regular output."
        result = parse_stats_line(stdout)
        assert result.tokens_generated is None
        assert result.generation_speed is None
        assert result.model_name is None

    def test_returns_none_for_empty_string(self):
        result = parse_stats_line("")
        assert result.tokens_generated is None
        assert result.generation_speed is None

    def test_model_name_is_none(self):
        """model_name is always None from parse_stats_line (set externally)."""
        stdout = "500 tokens in 10s (50 tok/s)"
        result = parse_stats_line(stdout)
        assert result.model_name is None

    def test_returns_none_for_malformed_pattern(self):
        stdout = "abc tokens in 10s (50 tok/s)"
        result = parse_stats_line(stdout)
        assert result.tokens_generated is None

    def test_returns_none_for_missing_speed(self):
        stdout = "500 tokens in 10s"
        result = parse_stats_line(stdout)
        assert result.tokens_generated is None

    def test_zero_tokens(self):
        stdout = "0 tokens in 1.0s (0 tok/s)"
        result = parse_stats_line(stdout)
        assert result.tokens_generated == 0
        assert result.generation_speed == 0.0

    def test_singular_token(self):
        """Handles '1 token in' (singular)."""
        stdout = "1 token in 0.5s (2.0 tok/s)"
        result = parse_stats_line(stdout)
        assert result.tokens_generated == 1
        assert result.generation_speed == 2.0

    def test_returns_execution_stats_dataclass(self):
        result = parse_stats_line("100 tokens in 5s (20 tok/s)")
        assert isinstance(result, ExecutionStats)


from local_coder.stats_parser import parse_exit_result


class TestParseExitResult:
    """Tests for parse_exit_result()."""

    def test_timeout_returns_fail_with_timeout_issue(self):
        result, issues = parse_exit_result(exit_code=0, stderr="", timeout=True)
        assert result == "fail"
        assert issues == ["timeout"]

    def test_timeout_ignores_exit_code_and_stderr(self):
        result, issues = parse_exit_result(exit_code=1, stderr="some error", timeout=True)
        assert result == "fail"
        assert issues == ["timeout"]

    def test_nonzero_exit_code_with_stderr(self):
        result, issues = parse_exit_result(exit_code=1, stderr="segfault")
        assert result == "fail"
        assert issues == ["exit_code:1", "segfault"]

    def test_nonzero_exit_code_without_stderr(self):
        result, issues = parse_exit_result(exit_code=127, stderr="")
        assert result == "fail"
        assert issues == ["exit_code:127"]

    def test_nonzero_exit_code_truncates_long_stderr(self):
        long_stderr = "x" * 300
        result, issues = parse_exit_result(exit_code=2, stderr=long_stderr)
        assert result == "fail"
        assert issues[0] == "exit_code:2"
        assert len(issues[1]) == 200
        assert issues[1] == "x" * 200

    def test_stderr_exactly_200_chars_not_truncated(self):
        stderr = "a" * 200
        result, issues = parse_exit_result(exit_code=1, stderr=stderr)
        assert issues[1] == "a" * 200

    def test_zero_exit_code_returns_success(self):
        result, issues = parse_exit_result(exit_code=0, stderr="")
        assert result == "success"
        assert issues == []

    def test_zero_exit_code_ignores_stderr(self):
        result, issues = parse_exit_result(exit_code=0, stderr="warning: something")
        assert result == "success"
        assert issues == []
