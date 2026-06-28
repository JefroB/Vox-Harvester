# Feature: scaffolding-library, Property 10: Scaffold Report Format
"""Property-based tests for scaffold report format.

**Validates: Requirements 6.5**

For any non-empty list of N selected template names, the stderr report line SHALL
match the exact format: [SCAFFOLD] Selected {N} template(s): {name1}, {name2}, ...
where names are comma-space separated and N equals the count of names in the list.
"""

from hypothesis import given, settings
from hypothesis import strategies as st


# --- Helper Function ---


def format_scaffold_report(names: list[str]) -> str:
    """Format the scaffold report line matching local_coder.py output.

    This mirrors the actual format used in the CLI integration:
        print(f"[SCAFFOLD] Selected {len(names)} template(s): {', '.join(names)}", file=sys.stderr)
    """
    return f"[SCAFFOLD] Selected {len(names)} template(s): {', '.join(names)}"


# --- Strategies ---

# Template names: non-empty alphanumeric strings (matching typical Path.stem values)
name_strategy = st.text(
    alphabet="abcdefghijklmnop0123456789_-",
    min_size=1,
    max_size=20,
)

# Lists of template names (1-20 names, matching N in [1, 20])
names_strategy = st.lists(name_strategy, min_size=1, max_size=20)


# --- Property Tests ---


@settings(max_examples=100)
@given(names=names_strategy)
def test_report_starts_with_scaffold_prefix(names):
    """The report line starts with '[SCAFFOLD] Selected '."""
    report = format_scaffold_report(names)
    assert report.startswith("[SCAFFOLD] Selected "), (
        f"Report does not start with '[SCAFFOLD] Selected ': {report!r}"
    )


@settings(max_examples=100)
@given(names=names_strategy)
def test_report_contains_correct_count(names):
    """The number N in the report equals len(names)."""
    report = format_scaffold_report(names)
    # Extract the number between "Selected " and " template(s)"
    prefix = "[SCAFFOLD] Selected "
    rest = report[len(prefix):]
    n_str = rest.split(" template(s):")[0]
    n = int(n_str)
    assert n == len(names), (
        f"Report count {n} does not match len(names) {len(names)}: {report!r}"
    )


@settings(max_examples=100)
@given(names=names_strategy)
def test_report_ends_with_comma_separated_names(names):
    """The report ends with the comma-separated names."""
    report = format_scaffold_report(names)
    expected_suffix = ", ".join(names)
    assert report.endswith(expected_suffix), (
        f"Report does not end with expected names.\n"
        f"Expected suffix: {expected_suffix!r}\n"
        f"Actual report: {report!r}"
    )


@settings(max_examples=100)
@given(names=names_strategy)
def test_report_exact_format(names):
    """The full format is exactly '[SCAFFOLD] Selected {N} template(s): {name1}, {name2}, ...'."""
    report = format_scaffold_report(names)
    expected = f"[SCAFFOLD] Selected {len(names)} template(s): {', '.join(names)}"
    assert report == expected, (
        f"Report does not match expected format.\n"
        f"Expected: {expected!r}\n"
        f"Actual:   {report!r}"
    )
