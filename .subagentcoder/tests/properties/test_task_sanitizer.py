# Feature: local-coder-reliability, Property 9: Task Sanitization Strips Project References
"""Property tests for task sanitization.

Property 9: Task Sanitization Strips Project References (Requirements 9.1)
"""

import os
import re
import tempfile

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from local_coder.hallucination_guard import sanitize_task_for_prose


# --- Strategies ---

# Valid Python identifiers (lowercase function names)
_symbol_strategy = st.from_regex(r"[a-z][a-z_]{2,10}", fullmatch=True)

# General words that won't be confused with Python symbols (capitalized)
_general_word_strategy = st.from_regex(r"[A-Z][a-z]{2,8}", fullmatch=True)


# Validates: Requirements 9.1
@settings(max_examples=100)
@given(
    symbols=st.lists(_symbol_strategy, min_size=1, max_size=5),
    general_words=st.lists(_general_word_strategy, min_size=3, max_size=8),
)
def test_task_sanitization_strips_project_references(
    symbols: list[str], general_words: list[str]
) -> None:
    """Feature: local-coder-reliability, Property 9: Task Sanitization Strips Project References"""

    # Ensure symbols are unique
    assume(len(set(symbols)) == len(symbols))

    # Ensure general words don't accidentally match any symbol (case-insensitive)
    symbols_set = set(symbols)
    assume(not any(w.lower() in symbols_set for w in general_words))

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a temporary Python file that defines the project symbols
        temp_file = os.path.join(tmpdir, "project_module.py")
        lines = []
        for sym in symbols:
            lines.append(f"def {sym}(): pass")
        with open(temp_file, "w") as f:
            f.write("\n".join(lines))

        # Build a task description that embeds project symbols among general words
        task_parts = list(general_words) + list(symbols)
        task = " ".join(task_parts)

        # Call sanitize_task_for_prose
        result = sanitize_task_for_prose(task, context_files=[temp_file])

        # a. NONE of the project-specific symbols appear in the sanitized output
        for sym in symbols:
            assert not re.search(r"\b" + re.escape(sym) + r"\b", result), (
                f"Symbol {sym!r} still present in sanitized output: {result!r}"
            )

        # b. The sanitized output is non-empty (general text preserved)
        assert result.strip(), "Sanitized output is empty"

        # c. Words that are NOT project symbols remain in the output
        for word in general_words:
            assert word in result, (
                f"General word {word!r} missing from sanitized output: {result!r}"
            )
