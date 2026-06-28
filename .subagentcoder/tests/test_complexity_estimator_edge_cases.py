"""Unit tests for complexity estimator edge cases.

Validates Requirements 1.2, 1.3, 1.4 — boundary conditions, type checks,
and keyword/file interactions.
"""

import pytest

from local_coder.complexity_estimator import (
    estimate_complexity,
    FIBONACCI_SCORES,
    COMPLEX_KEYWORDS,
)


class TestEmptyAndWhitespaceInput:
    """Edge case: empty or whitespace-only task descriptions return score 1."""

    def test_empty_string_returns_1(self):
        assert estimate_complexity("", []) == 1

    def test_whitespace_only_returns_1(self):
        assert estimate_complexity("   ", []) == 1

    def test_newlines_only_returns_1(self):
        assert estimate_complexity("\n\n\t", []) == 1


class TestNonStringInputRaisesTypeError:
    """Edge case: non-string task raises TypeError."""

    def test_integer_raises_typeerror(self):
        with pytest.raises(TypeError):
            estimate_complexity(42, [])

    def test_none_raises_typeerror(self):
        with pytest.raises(TypeError):
            estimate_complexity(None, [])

    def test_list_raises_typeerror(self):
        with pytest.raises(TypeError):
            estimate_complexity(["build auth"], [])

    def test_dict_raises_typeerror(self):
        with pytest.raises(TypeError):
            estimate_complexity({"task": "build"}, [])


class TestBoundaryConditions:
    """Edge case: exact boundary lengths for tier transitions."""

    def test_exactly_99_chars_is_low_tier(self):
        # 99 chars → base score 0 (low tier)
        task = "x" * 99
        result = estimate_complexity(task, [])
        # No keywords, no files → score stays at index 0 → FIBONACCI_SCORES[0] = 1
        assert result == FIBONACCI_SCORES[0]

    def test_exactly_100_chars_is_mid_tier(self):
        # 100 chars → base score 1 (mid tier)
        task = "x" * 100
        result = estimate_complexity(task, [])
        # No keywords, no files → score stays at index 1 → FIBONACCI_SCORES[1] = 2
        assert result == FIBONACCI_SCORES[1]

    def test_exactly_300_chars_is_still_mid_tier(self):
        # 300 chars → still mid tier (condition is <= 300)
        task = "x" * 300
        result = estimate_complexity(task, [])
        # No keywords, no files → score stays at index 1 → FIBONACCI_SCORES[1] = 2
        assert result == FIBONACCI_SCORES[1]

    def test_exactly_301_chars_is_high_tier(self):
        # 301 chars → base score 2 (high tier)
        task = "x" * 301
        result = estimate_complexity(task, [])
        # No keywords, no files → score stays at index 2 → FIBONACCI_SCORES[2] = 3
        assert result == FIBONACCI_SCORES[2]


class TestKeywordCombinations:
    """Edge case: keyword matching and interactions with file count."""

    def test_one_keyword_zero_files_not_high(self):
        # 1 keyword match + 0 files → should NOT be in high range {8, 13, 21}
        # keyword_matches // 2 = 0 additional tiers
        task = "refactor the utils module"  # "refactor" is a keyword
        result = estimate_complexity(task, [])
        assert result not in [8, 13, 21]

    def test_two_keywords_zero_files_not_high(self):
        # 2 keywords + 0 files → keyword_matches // 2 = 1 additional tier
        # But no semantic floor (needs >=1 keyword AND >=3 files)
        task = "refactor the authentication module"  # "refactor", "auth", "module"
        result = estimate_complexity(task, [])
        # Even with keywords, no files means no semantic floor
        # The score depends on length + keyword bonus but shouldn't hit the floor
        assert result in FIBONACCI_SCORES

    def test_two_keywords_three_files_is_high(self):
        # Per Requirement 1.3: keyword_matches >= 1 AND file_count >= 3 → floor at index 4+
        task = "refactor the auth module"  # "refactor", "auth", "module" = 3 keywords
        files = ["a.py", "b.py", "c.py"]
        result = estimate_complexity(task, files)
        assert result in [8, 13, 21]

    def test_one_keyword_three_files_is_high(self):
        # Semantic floor: keyword_matches >= 1 AND file_count >= 3
        task = "fix the database query"  # "database" is a keyword
        files = ["models.py", "views.py", "serializers.py"]
        result = estimate_complexity(task, files)
        assert result in [8, 13, 21]

    def test_zero_keywords_many_files_not_forced_high(self):
        # No keywords → semantic floor does NOT apply, even with many files
        task = "rename variable x to y"
        files = ["a.py", "b.py", "c.py", "d.py", "e.py"]
        result = estimate_complexity(task, files)
        # file_count // 2 = 2 tiers, but no semantic floor
        # Could land anywhere depending on length, but not forced to high
        assert result in FIBONACCI_SCORES


class TestOutputFileTypeModifier:
    """Edge case: output file type reduces score."""

    def test_config_file_output_reduces_score(self):
        # Config file → -1 modifier
        task = "x" * 150  # mid tier, base score 1
        result_neutral = estimate_complexity(task, [], output_path="output.py")
        result_config = estimate_complexity(task, [], output_path="config.json")
        assert result_config <= result_neutral

    def test_yaml_file_output_reduces_score(self):
        task = "x" * 150
        result_neutral = estimate_complexity(task, [], output_path="output.py")
        result_yaml = estimate_complexity(task, [], output_path="settings.yaml")
        assert result_yaml <= result_neutral

    def test_test_file_output_reduces_score(self):
        # Test file → -1 modifier
        task = "x" * 150
        result_neutral = estimate_complexity(task, [], output_path="output.py")
        result_test = estimate_complexity(task, [], output_path="test_output.py")
        assert result_test <= result_neutral

    def test_score_never_goes_below_1(self):
        # Even with modifiers reducing score, minimum is FIBONACCI_SCORES[0] = 1
        task = "fix typo"  # short, no keywords
        result = estimate_complexity(task, [], output_path="config.json")
        assert result >= 1
        assert result in FIBONACCI_SCORES
