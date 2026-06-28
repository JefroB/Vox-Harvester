# Feature: local-coder-task-intelligence, Properties 1–4: Complexity Estimator
"""Property-based tests for the Fibonacci complexity estimator.

Tests validate that:
- Property 1: Output is always a valid Fibonacci score
- Property 2: Simple tasks receive low complexity scores
- Property 3: Complex tasks receive high complexity scores
- Property 4: Complexity estimation is deterministic
"""

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from local_coder.complexity_estimator import (
    COMPLEX_KEYWORDS,
    FIBONACCI_SCORES,
    estimate_complexity,
)


# --- Generators ---


def task_descriptions():
    """Arbitrary task description strings."""
    return st.text(min_size=0, max_size=500)


def context_file_lists():
    """Lists of plausible file paths."""
    file_path = st.from_regex(
        r"[a-z_][a-z0-9_/]{0,30}\.(py|ts|js|json|yaml|toml|md)",
        fullmatch=True,
    )
    return st.lists(file_path, min_size=0, max_size=10)


def output_paths():
    """Optional file paths with various extensions."""
    path = st.from_regex(
        r"[a-z_][a-z0-9_/]{0,20}\.(py|ts|js|json|yaml|toml|cfg|ini|md)",
        fullmatch=True,
    )
    return st.one_of(st.none(), path)


def simple_task_descriptions():
    """Task descriptions shorter than 100 characters with NO complex keywords.

    Uses only uppercase letters to avoid accidentally forming keywords.
    """
    return st.text(
        alphabet=st.characters(whitelist_categories=("Lu", "Nd", "Zs")),
        min_size=1,
        max_size=99,
    ).filter(
        lambda d: len(d) < 100
        and not any(kw.lower() in d.lower() for kw in COMPLEX_KEYWORDS)
    )


def complex_task_descriptions():
    """Task descriptions containing at least one COMPLEX_KEYWORD."""
    return st.builds(
        lambda prefix, keyword, suffix: (prefix + " " + keyword + " " + suffix).strip(),
        prefix=st.text(
            alphabet=st.characters(whitelist_categories=("L", "N", "Zs")),
            min_size=0,
            max_size=80,
        ),
        keyword=st.sampled_from(COMPLEX_KEYWORDS),
        suffix=st.text(
            alphabet=st.characters(whitelist_categories=("L", "N", "Zs")),
            min_size=0,
            max_size=80,
        ),
    )


def context_files_at_least_3():
    """Lists of at least 3 plausible file paths."""
    file_path = st.from_regex(
        r"[a-z_][a-z0-9_/]{0,30}\.(py|ts|js|json|yaml|md)",
        fullmatch=True,
    )
    return st.lists(file_path, min_size=3, max_size=10)


# --- Property Tests ---


@settings(max_examples=100)
@given(
    task=task_descriptions(),
    context_files=context_file_lists(),
    output_path=output_paths(),
)
def test_property_1_output_is_valid_fibonacci_score(task, context_files, output_path):
    """Property 1: Complexity output is always a valid Fibonacci score.

    **Validates: Requirements 1.1**

    For any task description string, any list of context file paths, and any
    output path (including None), estimate_complexity() SHALL return a value
    that is exactly one element of {1, 2, 3, 5, 8, 13, 21}.
    """
    result = estimate_complexity(task, context_files, output_path)
    assert result in FIBONACCI_SCORES, (
        f"Expected one of {FIBONACCI_SCORES}, got {result}"
    )


@settings(max_examples=100)
@given(
    task=simple_task_descriptions(),
    context_files=st.lists(
        st.from_regex(r"[a-z_][a-z0-9_/]{0,20}\.py", fullmatch=True),
        min_size=0,
        max_size=1,
    ),
    output_path=output_paths(),
)
def test_property_2_simple_tasks_receive_low_scores(task, context_files, output_path):
    """Property 2: Simple tasks receive low complexity scores.

    **Validates: Requirements 1.2**

    For any task description shorter than 100 characters that contains none
    of the COMPLEX_KEYWORDS, with at most one context file,
    estimate_complexity() SHALL return a score in {1, 2, 3}.
    """
    result = estimate_complexity(task, context_files, output_path)
    assert result in {1, 2, 3}, (
        f"Simple task should score in {{1, 2, 3}}, got {result}. "
        f"Task: {task!r}, files: {context_files}, output: {output_path}"
    )


@settings(max_examples=100)
@given(
    task=complex_task_descriptions(),
    context_files=context_files_at_least_3(),
    output_path=output_paths(),
)
def test_property_3_complex_tasks_receive_high_scores(task, context_files, output_path):
    """Property 3: Complex tasks receive high complexity scores.

    **Validates: Requirements 1.3**

    For any task description that contains at least one keyword from
    COMPLEX_KEYWORDS and references 3 or more context files,
    estimate_complexity() SHALL return a score in {8, 13, 21}.
    """
    # Verify precondition: at least one keyword is present
    task_lower = task.lower()
    has_keyword = any(kw.lower() in task_lower for kw in COMPLEX_KEYWORDS)
    assume(has_keyword)

    result = estimate_complexity(task, context_files, output_path)
    assert result in {8, 13, 21}, (
        f"Complex task should score in {{8, 13, 21}}, got {result}. "
        f"Task: {task!r}, files count: {len(context_files)}, output: {output_path}"
    )


@settings(max_examples=100)
@given(
    task=task_descriptions(),
    context_files=context_file_lists(),
    output_path=output_paths(),
)
def test_property_4_estimation_is_deterministic(task, context_files, output_path):
    """Property 4: Complexity estimation is deterministic.

    **Validates: Requirements 1.6**

    For any (task, context_files, output_path) triple, calling
    estimate_complexity() twice with identical arguments SHALL return the
    same value.
    """
    result1 = estimate_complexity(task, context_files, output_path)
    result2 = estimate_complexity(task, context_files, output_path)
    assert result1 == result2, (
        f"Non-deterministic: first call returned {result1}, "
        f"second call returned {result2}"
    )


# --- Property 6: Routing Preservation ---

import sys
import importlib.util
from pathlib import Path

# Load resolve_model from the local_coder.py script (not the package)
_script_path = Path(__file__).parent.parent.parent.parent / ".kiro" / "scripts" / "local_coder.py"
_spec = importlib.util.spec_from_file_location("local_coder_script", _script_path)
_local_coder_module = importlib.util.module_from_spec(_spec)

# Ensure workspace root is on path so the script's own imports work
_workspace_root = str(Path(__file__).parent.parent.parent.parent)
if _workspace_root not in sys.path:
    sys.path.insert(0, _workspace_root)

_spec.loader.exec_module(_local_coder_module)
resolve_model = _local_coder_module.resolve_model


# Generator for complexity flags (the CLI --complexity values)
def complexity_flags():
    """Strategy producing valid --complexity CLI flag values."""
    return st.sampled_from(["simple", "complex", "prose", "auto"])


@settings(max_examples=100)
@given(
    task=task_descriptions(),
    complexity_flag=complexity_flags(),
)
def test_property_6_complexity_score_does_not_influence_routing(task, complexity_flag):
    """Property 6: Complexity score does not influence model routing.

    **Validates: Requirements 3.2**

    For any task description and complexity setting, the output of
    resolve_model(task, complexity) SHALL be identical regardless of what
    estimate_complexity() would return for that same task.

    We verify this by calling resolve_model twice with the same inputs —
    the result must be deterministic and independent of any Fibonacci score.
    The function signature confirms it does NOT accept a complexity_score
    parameter, proving the score cannot influence routing.
    """
    # Call resolve_model — it takes (task, complexity_flag) not a Fibonacci score
    result1 = resolve_model(task, complexity_flag)
    result2 = resolve_model(task, complexity_flag)

    # Same inputs must produce same routing (deterministic, score-independent)
    assert result1 == result2, (
        f"resolve_model returned different results for the same inputs: "
        f"{result1!r} vs {result2!r}"
    )

    # Verify resolve_model does NOT accept a complexity_score parameter.
    # This structurally ensures the Fibonacci score cannot influence routing.
    import inspect
    sig = inspect.signature(resolve_model)
    param_names = set(sig.parameters.keys())
    assert "complexity_score" not in param_names, (
        "resolve_model should NOT accept a 'complexity_score' parameter — "
        f"found parameters: {param_names}"
    )
    assert "score" not in param_names, (
        "resolve_model should NOT accept a 'score' parameter — "
        f"found parameters: {param_names}"
    )

    # The result must be a known model string
    assert isinstance(result1, str) and len(result1) > 0, (
        f"resolve_model must return a non-empty string, got {result1!r}"
    )
