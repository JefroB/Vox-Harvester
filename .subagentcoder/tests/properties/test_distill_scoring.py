# Feature: skill-distillation, Property 1: Score formula correctness
"""Property-based tests for relevance score formula.

**Validates: Requirements 1.1, 1.2**

For any task description and any skill section (heading + body), the computed
Relevance_Score SHALL equal the ratio of shared non-stop-word tokens
(case-insensitive, whitespace-split) to total section tokens, where each shared
token that also appears in the section heading contributes twice. The result
SHALL be in the range [0.0, 1.0].
"""

import sys
from pathlib import Path

# Make distiller importable from .kiro/scripts/
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / ".kiro" / "scripts"))

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from distiller import score_section, Section, CodeBlock, DEFAULT_STOP_WORDS


# --- Strategies ---

# Fixed vocabulary to ensure non-trivial overlap scenarios
VOCAB = [
    "python", "function", "validate", "input", "security",
    "database", "query", "server", "client", "module",
    "parse", "token", "config", "error", "handler",
    "cache", "async", "deploy", "testing", "build",
    "route", "middleware", "schema", "model", "endpoint",
]

# Random word: mix of vocabulary words and novel words
word_strategy = st.one_of(
    st.sampled_from(VOCAB),
    st.text(
        alphabet=st.characters(
            whitelist_categories=("L", "N"),
            blacklist_categories=("Cs",),
        ),
        min_size=1,
        max_size=12,
    ).filter(lambda s: s.strip() and " " not in s and "\t" not in s),
)

# Task description: 1-10 words
task_description_strategy = st.lists(
    word_strategy, min_size=1, max_size=10
).map(lambda words: " ".join(words))

# Section heading: 1-5 words
heading_strategy = st.lists(
    word_strategy, min_size=1, max_size=5
).map(lambda words: " ".join(words))

# Section body: 1-50 words
body_strategy = st.lists(
    word_strategy, min_size=1, max_size=50
).map(lambda words: " ".join(words))


@st.composite
def section_with_task_overlap(draw):
    """Generate a task description and section that may share words.

    Mixes some task words into section content to ensure non-trivial matches.
    """
    # Generate task words
    task_words = draw(st.lists(word_strategy, min_size=1, max_size=10))

    # Generate heading words, potentially borrowing from task
    heading_words = draw(st.lists(word_strategy, min_size=1, max_size=5))
    # Optionally inject task words into heading
    inject_to_heading = draw(st.lists(
        st.sampled_from(task_words) if task_words else st.just("placeholder"),
        min_size=0,
        max_size=min(3, len(task_words)),
    ))
    heading_words = heading_words + inject_to_heading

    # Generate body words, potentially borrowing from task
    body_words = draw(st.lists(word_strategy, min_size=1, max_size=50))
    # Optionally inject task words into body
    inject_to_body = draw(st.lists(
        st.sampled_from(task_words) if task_words else st.just("placeholder"),
        min_size=0,
        max_size=min(5, len(task_words)),
    ))
    body_words = body_words + inject_to_body

    task_desc = " ".join(task_words)
    heading = " ".join(heading_words)
    body = " ".join(body_words)

    return (task_desc, heading, body)


# --- Reference Implementation ---

def reference_score(task_desc: str, heading: str, body: str, stop_words: frozenset[str]) -> float:
    """Manually compute the expected score using the formula from the spec.

    1. Task tokens = set of lowercase whitespace-split words from task description, stop words removed
    2. Section tokens = all whitespace-split words from (heading + " " + body), lowercased, stop words removed
    3. Heading tokens = whitespace-split words from heading only, lowercased, stop words removed
    4. shared = task_tokens ∩ set(section_tokens)
    5. numerator = sum(2 if word in heading_tokens else 1 for word in shared)
    6. denominator = len(section_tokens) (total count, not unique)
    7. score = min(numerator / denominator, 1.0) if denominator > 0 else 0.0
    """
    # Step 1: Task tokens
    task_tokens = {w.lower() for w in task_desc.split() if w.lower() not in stop_words}

    # Step 2: Section tokens (list, not set - denominator uses total count)
    full_text = heading + " " + body
    section_tokens_list = [w.lower() for w in full_text.split() if w.lower() not in stop_words]

    # Step 3: Heading tokens
    heading_tokens = {w.lower() for w in heading.split() if w.lower() not in stop_words}

    # Step 4: Shared words
    shared = task_tokens & set(section_tokens_list)

    # Step 5: Weighted numerator
    numerator = sum(2 if word in heading_tokens else 1 for word in shared)

    # Step 6: Denominator
    denominator = len(section_tokens_list)

    # Step 7: Score
    if denominator == 0:
        return 0.0
    return min(numerator / denominator, 1.0)


# --- Property Tests ---


@settings(max_examples=100)
@given(data=section_with_task_overlap())
def test_score_in_valid_range(data):
    """Score is always in [0.0, 1.0] for any inputs."""
    task_desc, heading, body = data

    task_tokens = {w.lower() for w in task_desc.split() if w.lower() not in DEFAULT_STOP_WORDS}
    section = Section(heading=heading, body=body, code_blocks=[], is_preamble=False)

    score = score_section(task_tokens, section, DEFAULT_STOP_WORDS)

    assert 0.0 <= score <= 1.0, f"Score {score} out of range [0.0, 1.0]"


@settings(max_examples=100)
@given(data=section_with_task_overlap())
def test_score_matches_reference_formula(data):
    """Score matches the manually computed formula using the same algorithm."""
    task_desc, heading, body = data

    task_tokens = {w.lower() for w in task_desc.split() if w.lower() not in DEFAULT_STOP_WORDS}
    section = Section(heading=heading, body=body, code_blocks=[], is_preamble=False)

    actual_score = score_section(task_tokens, section, DEFAULT_STOP_WORDS)
    expected_score = reference_score(task_desc, heading, body, DEFAULT_STOP_WORDS)

    assert abs(actual_score - expected_score) < 1e-10, (
        f"Score mismatch: actual={actual_score}, expected={expected_score}\n"
        f"Task: {task_desc!r}\nHeading: {heading!r}\nBody: {body!r}"
    )


@settings(max_examples=100)
@given(
    task_desc=task_description_strategy,
    heading=heading_strategy,
    body=body_strategy,
)
def test_no_shared_words_gives_zero_score(task_desc, heading, body):
    """If task_tokens and section content share no non-stop words, score is 0.0."""
    # Compute task tokens
    task_tokens = {w.lower() for w in task_desc.split() if w.lower() not in DEFAULT_STOP_WORDS}

    # Compute section tokens (as set for intersection check)
    full_text = heading + " " + body
    section_token_set = {w.lower() for w in full_text.split() if w.lower() not in DEFAULT_STOP_WORDS}

    # Only test when there are truly no shared words
    assume(len(task_tokens & section_token_set) == 0)

    section = Section(heading=heading, body=body, code_blocks=[], is_preamble=False)
    score = score_section(task_tokens, section, DEFAULT_STOP_WORDS)

    assert score == 0.0, (
        f"Expected 0.0 when no shared words, got {score}\n"
        f"Task tokens: {task_tokens}\nSection tokens: {section_token_set}"
    )


@settings(max_examples=100)
@given(
    task_desc=task_description_strategy,
    heading=heading_strategy,
    body=body_strategy,
)
def test_all_section_tokens_in_task_gives_high_score(task_desc, heading, body):
    """If all section tokens appear in task_tokens, score is >= len(section_tokens) / len(section_tokens_list).

    When all unique section tokens are in the task, the score is at least 1.0 (since each
    token contributes at least 1, and heading tokens contribute 2).
    """
    # Compute section tokens
    full_text = heading + " " + body
    section_tokens_list = [w.lower() for w in full_text.split() if w.lower() not in DEFAULT_STOP_WORDS]
    section_token_set = set(section_tokens_list)

    # Filter: only test when denominator > 0
    assume(len(section_tokens_list) > 0)

    # Build task tokens that include ALL section tokens (guarantees full overlap)
    task_tokens = section_token_set.copy()

    section = Section(heading=heading, body=body, code_blocks=[], is_preamble=False)
    score = score_section(task_tokens, section, DEFAULT_STOP_WORDS)

    # When all section tokens are in task, numerator = sum(2 if heading else 1 for each unique shared word)
    # denominator = total non-stop section tokens (count with duplicates)
    # The score should be >= number_of_unique_section_tokens / len(section_tokens_list)
    min_expected = len(section_token_set) / len(section_tokens_list)
    assert score >= min_expected - 1e-10, (
        f"Expected score >= {min_expected}, got {score}\n"
        f"Section tokens (unique): {section_token_set}\n"
        f"Section tokens (list): {section_tokens_list}"
    )
