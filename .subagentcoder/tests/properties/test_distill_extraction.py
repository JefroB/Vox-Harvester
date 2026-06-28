# Feature: skill-distillation, Property 6: Rule extraction captures all actionable items
"""Property-based tests for rule extraction.

**Validates: Requirements 2.1, 2.2**

For any Section containing bullet points (lines starting with `- ` or `* `),
numbered items (lines starting with `N. `), or imperative statements (containing
"SHALL", "MUST", "NEVER", or "ALWAYS"), the extraction function SHALL include all
such items in its output. For any code block whose preceding text shares at least
one non-stop keyword with the task description, that code block SHALL appear
verbatim in the extracted output.
"""

import sys
from pathlib import Path

# Make distiller importable from .kiro/scripts/
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / ".kiro" / "scripts"))

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from distiller import extract_rules, Section, CodeBlock, DEFAULT_STOP_WORDS


# --- Strategies ---

# Vocabulary of non-stop words (words NOT in DEFAULT_STOP_WORDS)
NON_STOP_VOCAB = [
    "python", "function", "validate", "input", "security",
    "database", "query", "server", "client", "module",
    "parse", "token", "config", "error", "handler",
    "cache", "async", "deploy", "testing", "build",
    "route", "middleware", "schema", "model", "endpoint",
    "logger", "metric", "timeout", "retry", "buffer",
]

IMPERATIVE_KEYWORDS = ["SHALL", "MUST", "NEVER", "ALWAYS"]

# Strategy for a single non-stop word
non_stop_word = st.sampled_from(NON_STOP_VOCAB)

# Strategy for plain text that is NOT a bullet, numbered item, or imperative
plain_text = st.lists(
    non_stop_word, min_size=2, max_size=8
).map(lambda words: " ".join(words)).filter(
    lambda line: not line.startswith("- ")
    and not line.startswith("* ")
    and not any(kw in line.upper() for kw in IMPERATIVE_KEYWORDS)
)

# Strategy for bullet lines (starting with "- " or "* ")
bullet_line = st.tuples(
    st.sampled_from(["- ", "* "]),
    st.lists(non_stop_word, min_size=1, max_size=6).map(lambda w: " ".join(w)),
).map(lambda t: t[0] + t[1])

# Strategy for numbered item lines (starting with "N. ")
numbered_line = st.tuples(
    st.integers(min_value=1, max_value=99),
    st.lists(non_stop_word, min_size=1, max_size=6).map(lambda w: " ".join(w)),
).map(lambda t: f"{t[0]}. {t[1]}")

# Strategy for imperative statement lines (containing SHALL/MUST/NEVER/ALWAYS)
imperative_line = st.tuples(
    st.lists(non_stop_word, min_size=1, max_size=3).map(lambda w: " ".join(w)),
    st.sampled_from(IMPERATIVE_KEYWORDS),
    st.lists(non_stop_word, min_size=1, max_size=3).map(lambda w: " ".join(w)),
).map(lambda t: f"{t[0]} {t[1]} {t[2]}")


@st.composite
def section_with_actionable_items(draw):
    """Generate a Section body with a mix of actionable and plain lines.

    Returns (body_text, expected_bullets, expected_numbered, expected_imperatives).
    All actionable lines are placed OUTSIDE code fences.
    """
    # Generate some bullet lines
    bullets = draw(st.lists(bullet_line, min_size=0, max_size=5))
    # Generate some numbered lines
    numbered = draw(st.lists(numbered_line, min_size=0, max_size=5))
    # Generate some imperative lines
    imperatives = draw(st.lists(imperative_line, min_size=0, max_size=5))
    # Generate some plain lines (filler)
    plains = draw(st.lists(plain_text, min_size=0, max_size=3))

    # Ensure at least one actionable line exists
    assume(len(bullets) + len(numbered) + len(imperatives) > 0)

    # Interleave all lines (outside code fences)
    all_lines = []
    for b in bullets:
        all_lines.append(b)
    for n in numbered:
        all_lines.append(n)
    for imp in imperatives:
        all_lines.append(imp)
    for p in plains:
        all_lines.append(p)

    # Shuffle deterministically via draw
    shuffled = draw(st.permutations(all_lines))

    body = "\n".join(shuffled)
    return (body, bullets, numbered, imperatives)


@st.composite
def code_block_with_shared_keywords(draw):
    """Generate a CodeBlock whose preceding_text shares keywords with task_tokens.

    Returns (code_block, task_tokens) where preceding_text shares at least one
    non-stop keyword with task_tokens.
    """
    # Pick shared keywords (at least 1)
    shared_words = draw(st.lists(non_stop_word, min_size=1, max_size=3))

    # Build preceding_text containing the shared words plus some extras
    extra_words = draw(st.lists(non_stop_word, min_size=0, max_size=4))
    preceding_words = shared_words + extra_words
    preceding_text = " ".join(preceding_words)

    # Build task_tokens containing the shared words plus some others
    other_task_words = draw(st.lists(non_stop_word, min_size=0, max_size=5))
    task_tokens = {w.lower() for w in (shared_words + other_task_words)} - DEFAULT_STOP_WORDS
    assume(len(task_tokens) > 0)

    # Generate code block content
    code_content = draw(st.text(
        alphabet=st.characters(whitelist_categories=("L", "N", "P", "Z")),
        min_size=5,
        max_size=80,
    ))
    language = draw(st.sampled_from(["python", "javascript", "bash", ""]))

    code_block = CodeBlock(
        language=language,
        content=code_content,
        preceding_text=preceding_text,
    )

    return (code_block, task_tokens)


@st.composite
def code_block_without_shared_keywords(draw):
    """Generate a CodeBlock whose preceding_text shares NO keywords with task_tokens.

    Returns (code_block, task_tokens) where preceding_text has zero overlap
    with task_tokens (after stop word removal).
    """
    # Partition the vocabulary into two disjoint sets
    # Use first half for task, second half for preceding_text
    half = len(NON_STOP_VOCAB) // 2
    task_vocab = NON_STOP_VOCAB[:half]
    preceding_vocab = NON_STOP_VOCAB[half:]

    # Build task_tokens from first partition
    task_words = draw(st.lists(
        st.sampled_from(task_vocab), min_size=1, max_size=5
    ))
    task_tokens = {w.lower() for w in task_words} - DEFAULT_STOP_WORDS
    assume(len(task_tokens) > 0)

    # Build preceding_text from second partition (no overlap guaranteed)
    preceding_words = draw(st.lists(
        st.sampled_from(preceding_vocab), min_size=1, max_size=5
    ))
    preceding_text = " ".join(preceding_words)

    # Verify no overlap
    preceding_tokens = {w.lower() for w in preceding_words} - DEFAULT_STOP_WORDS
    assume(len(preceding_tokens & task_tokens) == 0)

    # Generate code block content
    code_content = draw(st.text(
        alphabet=st.characters(whitelist_categories=("L", "N", "P", "Z")),
        min_size=5,
        max_size=80,
    ))
    language = draw(st.sampled_from(["python", "javascript", "bash", ""]))

    code_block = CodeBlock(
        language=language,
        content=code_content,
        preceding_text=preceding_text,
    )

    return (code_block, task_tokens)


# --- Property Tests ---


@settings(max_examples=100)
@given(data=section_with_actionable_items())
def test_bullet_lines_extracted(data):
    """Every bullet line (- or *) in the section body appears in extracted rules."""
    body, bullets, _numbered, _imperatives = data

    section = Section(heading="Test Section", body=body, code_blocks=[], is_preamble=False)
    task_tokens = {"placeholder"}  # Irrelevant for rule extraction of text lines

    rules, _code_blocks = extract_rules(section, task_tokens)

    for bullet in bullets:
        assert bullet in rules, (
            f"Bullet line not found in extracted rules:\n"
            f"  Missing: {bullet!r}\n"
            f"  Rules: {rules!r}\n"
            f"  Body:\n{body}"
        )


@settings(max_examples=100)
@given(data=section_with_actionable_items())
def test_numbered_items_extracted(data):
    """Every numbered item (N. ) in the section body appears in extracted rules."""
    body, _bullets, numbered, _imperatives = data

    section = Section(heading="Test Section", body=body, code_blocks=[], is_preamble=False)
    task_tokens = {"placeholder"}

    rules, _code_blocks = extract_rules(section, task_tokens)

    for item in numbered:
        assert item in rules, (
            f"Numbered item not found in extracted rules:\n"
            f"  Missing: {item!r}\n"
            f"  Rules: {rules!r}\n"
            f"  Body:\n{body}"
        )


@settings(max_examples=100)
@given(data=section_with_actionable_items())
def test_imperative_statements_extracted(data):
    """Every line containing SHALL/MUST/NEVER/ALWAYS appears in extracted rules."""
    body, _bullets, _numbered, imperatives = data

    section = Section(heading="Test Section", body=body, code_blocks=[], is_preamble=False)
    task_tokens = {"placeholder"}

    rules, _code_blocks = extract_rules(section, task_tokens)

    for imp in imperatives:
        assert imp in rules, (
            f"Imperative statement not found in extracted rules:\n"
            f"  Missing: {imp!r}\n"
            f"  Rules: {rules!r}\n"
            f"  Body:\n{body}"
        )


@settings(max_examples=100)
@given(data=code_block_with_shared_keywords())
def test_code_blocks_with_shared_keywords_included(data):
    """Code blocks whose preceding_text shares at least one non-stop keyword
    with task_tokens appear verbatim in the extracted output."""
    code_block, task_tokens = data

    section = Section(
        heading="Test Section",
        body="Some content here",
        code_blocks=[code_block],
        is_preamble=False,
    )

    _rules, relevant_blocks = extract_rules(section, task_tokens)

    assert code_block in relevant_blocks, (
        f"Code block should be included (shared keywords exist):\n"
        f"  preceding_text: {code_block.preceding_text!r}\n"
        f"  task_tokens: {task_tokens}\n"
        f"  preceding_tokens (non-stop): "
        f"{({w.lower() for w in code_block.preceding_text.split()} - DEFAULT_STOP_WORDS)}\n"
        f"  overlap: "
        f"{task_tokens & ({w.lower() for w in code_block.preceding_text.split()} - DEFAULT_STOP_WORDS)}"
    )
    # Verify content is preserved verbatim
    matched = [b for b in relevant_blocks if b.content == code_block.content]
    assert len(matched) > 0, (
        f"Code block content not preserved verbatim:\n"
        f"  Expected content: {code_block.content!r}"
    )


@settings(max_examples=100)
@given(data=code_block_without_shared_keywords())
def test_code_blocks_without_shared_keywords_excluded(data):
    """Code blocks whose preceding_text shares NO non-stop keywords
    with task_tokens do NOT appear in the extracted output."""
    code_block, task_tokens = data

    section = Section(
        heading="Test Section",
        body="Some content here",
        code_blocks=[code_block],
        is_preamble=False,
    )

    _rules, relevant_blocks = extract_rules(section, task_tokens)

    assert code_block not in relevant_blocks, (
        f"Code block should NOT be included (no shared keywords):\n"
        f"  preceding_text: {code_block.preceding_text!r}\n"
        f"  task_tokens: {task_tokens}\n"
        f"  preceding_tokens (non-stop): "
        f"{({w.lower() for w in code_block.preceding_text.split()} - DEFAULT_STOP_WORDS)}\n"
        f"  overlap: "
        f"{task_tokens & ({w.lower() for w in code_block.preceding_text.split()} - DEFAULT_STOP_WORDS)}"
    )
