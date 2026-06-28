# Feature: skill-distillation, Property 5: Case-insensitive matching with stop-word exclusion
"""Property-based tests for case-insensitive matching and stop-word exclusion.

**Validates: Requirements 1.7**

For any task description and section content, the Relevance_Score SHALL be
identical regardless of the case of characters in the task or section.
Additionally, tokens that are in the stop-word list SHALL NOT contribute
to the shared-word count.
"""

import sys
from pathlib import Path

# Make distiller importable from .kiro/scripts/
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / ".kiro" / "scripts"))

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from distiller import score_section, Section, CodeBlock, DEFAULT_STOP_WORDS


# --- Helpers ---

def preprocess_task(task_description: str, stop_words: frozenset[str]) -> set[str]:
    """Simulate task pre-processing: split on whitespace, lowercase, remove stop words."""
    return {w.lower() for w in task_description.split() if w.lower() not in stop_words}


def make_section(heading: str, body: str) -> Section:
    """Create a Section with the given heading and body (no code blocks)."""
    return Section(heading=heading, body=body, code_blocks=[], is_preamble=False)


# --- Strategies ---

# Words that are NOT stop words (ASCII alphabetic, length > 3 to avoid overlap with stop words)
# Restricted to ASCII letters to match the design's intent (English keyword matching).
_ascii_letters = st.sampled_from(list("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"))

non_stop_word = st.text(
    alphabet=_ascii_letters,
    min_size=4,
    max_size=12,
).filter(lambda w: w.lower() not in DEFAULT_STOP_WORDS and w.strip())

# Generate a list of non-stop words to form text content
non_stop_words_list = st.lists(non_stop_word, min_size=1, max_size=8)

# Stop words sampled from the actual set
stop_word = st.sampled_from(sorted(DEFAULT_STOP_WORDS))
stop_words_list = st.lists(stop_word, min_size=1, max_size=8)

# Mixed content: some non-stop words and some stop words
mixed_words_list = st.lists(
    st.one_of(non_stop_word, stop_word),
    min_size=1,
    max_size=10,
)


@st.composite
def case_variant(draw, text: str) -> str:
    """Apply a random case transformation to text."""
    variant_type = draw(st.sampled_from(["upper", "lower", "title", "random"]))
    if variant_type == "upper":
        return text.upper()
    elif variant_type == "lower":
        return text.lower()
    elif variant_type == "title":
        return text.title()
    else:
        # Random per-character case flipping
        chars = []
        for c in text:
            if draw(st.booleans()):
                chars.append(c.upper())
            else:
                chars.append(c.lower())
        return "".join(chars)


@st.composite
def task_and_section_with_case_variants(draw):
    """Generate a task description and section content with different case variants.

    Returns (task_text, heading, body, task_variant, heading_variant, body_variant)
    where variants have different casing but same words.
    """
    # Generate shared words (will appear in both task and section)
    words = draw(non_stop_words_list)
    task_text = " ".join(words)
    # Section heading uses a subset of words
    heading_words = words[:max(1, len(words) // 2)]
    heading = " ".join(heading_words)
    # Section body uses all words plus possibly more
    extra_words = draw(st.lists(non_stop_word, min_size=0, max_size=4))
    body = " ".join(words + extra_words)

    # Generate case variants
    task_variant = draw(case_variant(task_text))
    heading_variant = draw(case_variant(heading))
    body_variant = draw(case_variant(body))

    return (task_text, heading, body, task_variant, heading_variant, body_variant)


# --- Property Tests ---


@settings(max_examples=100)
@given(data=task_and_section_with_case_variants())
def test_case_invariance_score_identical_regardless_of_case(data):
    """Score is identical regardless of the case of characters in task or section.

    score_section(preprocess(task.upper()), section_upper) ==
    score_section(preprocess(task.lower()), section_lower)
    """
    task_text, heading, body, task_variant, heading_variant, body_variant = data

    # Preprocess both case variants of the task
    task_tokens_original = preprocess_task(task_text, DEFAULT_STOP_WORDS)
    task_tokens_variant = preprocess_task(task_variant, DEFAULT_STOP_WORDS)

    # Create sections with original and variant casing
    section_original = make_section(heading, body)
    section_variant = make_section(heading_variant, body_variant)

    # Score with original casing
    score_original = score_section(task_tokens_original, section_original, DEFAULT_STOP_WORDS)

    # Score with variant casing
    score_variant = score_section(task_tokens_variant, section_variant, DEFAULT_STOP_WORDS)

    assert score_original == score_variant, (
        f"Case mismatch: original={score_original}, variant={score_variant}, "
        f"task='{task_text}' vs '{task_variant}', "
        f"heading='{heading}' vs '{heading_variant}'"
    )


@settings(max_examples=100)
@given(stop_words=stop_words_list, more_stop_words=stop_words_list)
def test_stop_word_only_content_scores_zero(stop_words, more_stop_words):
    """If both task and section consist ONLY of stop words, score is 0.0."""
    task_text = " ".join(stop_words)
    heading = " ".join(more_stop_words[:max(1, len(more_stop_words) // 2)])
    body = " ".join(more_stop_words)

    task_tokens = preprocess_task(task_text, DEFAULT_STOP_WORDS)
    section = make_section(heading, body)

    score = score_section(task_tokens, section, DEFAULT_STOP_WORDS)

    assert score == 0.0, (
        f"Expected 0.0 for all-stop-word content, got {score}. "
        f"task_tokens={task_tokens}, heading='{heading}', body='{body}'"
    )


@settings(max_examples=100)
@given(
    content_words=non_stop_words_list,
    heading_words=non_stop_words_list,
    injected_stop_words=stop_words_list,
)
def test_stop_words_do_not_change_score(content_words, heading_words, injected_stop_words):
    """Adding/removing stop words from section body does NOT change the score.

    When non-stop-word content remains the same, interspersing stop words
    should not affect the relevance score.
    """
    # Task uses same words as content to ensure non-zero score
    task_text = " ".join(content_words)
    task_tokens = preprocess_task(task_text, DEFAULT_STOP_WORDS)
    assume(len(task_tokens) > 0)

    heading = " ".join(heading_words)

    # Section body without stop words
    body_without = " ".join(content_words)
    section_without = make_section(heading, body_without)
    score_without = score_section(task_tokens, section_without, DEFAULT_STOP_WORDS)

    # Section body with stop words interspersed
    # Insert stop words between each content word
    mixed = []
    for i, word in enumerate(content_words):
        mixed.append(word)
        if i < len(injected_stop_words):
            mixed.append(injected_stop_words[i])
    # Also prepend and append some stop words
    body_with = " ".join(injected_stop_words[:2] + mixed + injected_stop_words[-2:])
    section_with = make_section(heading, body_with)
    score_with = score_section(task_tokens, section_with, DEFAULT_STOP_WORDS)

    assert score_without == score_with, (
        f"Stop words changed the score: without={score_without}, with={score_with}. "
        f"body_without='{body_without}', body_with='{body_with}'"
    )
