---
name: property-test-skeleton
tags: [test, property, hypothesis]
category: test-skeleton
complexity: any
description: 'Hypothesis PBT skeleton with strategies and settings for property-based testing'
priority: 10
---

# Hypothesis Property-Based Test Skeleton

Use this skeleton as a starting point for property-based tests with Hypothesis.

```python
import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st


# --- Strategy Examples ---
# st.integers(min_value=-100, max_value=100)  # Bounded integers
# st.text(min_size=1, max_size=50)            # Non-empty text up to 50 chars
# st.lists(st.integers(), min_size=0, max_size=20)  # Lists of integers
# st.floats(allow_nan=False, allow_infinity=False)  # Finite floats
# st.booleans()                                # True/False
# st.tuples(st.integers(), st.text())          # Composite strategies
# st.one_of(st.integers(), st.text())          # Union strategies
# st.dictionaries(st.text(min_size=1), st.integers())  # Dict strategies


# --- Basic Property Test ---
@given(
    x=st.integers(),
    y=st.integers(),
)
@settings(max_examples=100)
def test_property_example(x, y):
    """Replace with your property description.

    A good property test asserts something that should hold for ALL valid inputs,
    not just specific examples.
    """
    # CUSTOMIZE: Replace with your property assertion
    # Common property patterns:
    #   - Roundtrip: decode(encode(x)) == x
    #   - Invariant: len(sort(xs)) == len(xs)
    #   - Idempotent: f(f(x)) == f(x)
    #   - Commutativity: f(x, y) == f(y, x)
    #   - Monotonicity: x <= y implies f(x) <= f(y)
    result = x + y
    assert result - y == x  # Roundtrip property


# --- Property Test with Filtering (assume) ---
@given(
    items=st.lists(st.integers(), min_size=1, max_size=50),
)
@settings(max_examples=100)
def test_property_with_precondition(items):
    """Use assume() to filter inputs that don't meet preconditions."""
    assume(len(items) > 0)  # Skip empty lists

    # CUSTOMIZE: Your property assertion on filtered inputs
    sorted_items = sorted(items)
    assert len(sorted_items) == len(items)
    assert all(sorted_items[i] <= sorted_items[i + 1] for i in range(len(sorted_items) - 1))


# --- Property Test with Composite Strategy ---
@st.composite
def custom_strategy(draw):
    """Build complex test data from simpler strategies.

    CUSTOMIZE: Combine strategies to generate domain-specific inputs.
    """
    name = draw(st.text(min_size=1, max_size=20))
    age = draw(st.integers(min_value=0, max_value=150))
    return {"name": name, "age": age}


@given(data=custom_strategy())
@settings(max_examples=100)
def test_property_with_composite(data):
    """Test with custom composite strategy."""
    # CUSTOMIZE: Assert properties about your domain object
    assert isinstance(data["name"], str)
    assert 0 <= data["age"] <= 150
```

## Customization Points

1. **Strategies**: Replace `st.integers()`, `st.text()`, etc. with strategies matching your domain.
2. **Settings**: Adjust `max_examples` (higher = more thorough, slower). Add `deadline=None` for slow functions.
3. **Properties**: Choose the right property pattern (roundtrip, invariant, idempotent, etc.).
4. **Preconditions**: Use `assume()` to skip invalid inputs rather than try/except.
5. **Composite strategies**: Use `@st.composite` for complex structured inputs.

## Common Pitfalls

### Pytest Fixtures Are Incompatible with `@given`

Pytest fixtures like `tmp_path`, `capsys`, and `monkeypatch` do **NOT** work with `@given`-decorated test functions. Hypothesis calls the test function body multiple times with generated data, but pytest fixtures are only injected once per test invocation. Mixing them causes `TypeError` or silently broken behavior where the fixture value is stale across Hypothesis iterations.

**Affected fixtures:** `tmp_path`, `tmp_path_factory`, `capsys`, `capfd`, `monkeypatch`, `request`

---

❌ **WRONG** — Using pytest fixture with `@given`:

```python
@given(data=st.text())
def test_writes_file(data: str, tmp_path):  # tmp_path won't work!
    filepath = tmp_path / "output.txt"
    filepath.write_text(data)
    assert filepath.read_text() == data
```

✅ **CORRECT** — Using `tempfile` inside the test body:

```python
import tempfile
from pathlib import Path

@given(data=st.text())
def test_writes_file(data: str):
    with tempfile.TemporaryDirectory() as tmpdir:
        filepath = Path(tmpdir) / "output.txt"
        filepath.write_text(data)
        assert filepath.read_text() == data
```

---

### Workarounds for Other Fixtures

**`capsys` replacement** — capture stdout/stderr manually with `io.StringIO`:

```python
import io
import sys
from unittest.mock import patch

@given(msg=st.text())
def test_prints_message(msg: str):
    captured = io.StringIO()
    with patch("sys.stdout", captured):
        print(msg)
    assert captured.getvalue().strip() == msg
```

**`monkeypatch` replacement** — use `unittest.mock.patch` instead:

```python
from unittest.mock import patch

@given(value=st.integers())
def test_reads_env_var(value: int):
    with patch.dict("os.environ", {"MY_VAR": str(value)}):
        import os
        assert os.environ["MY_VAR"] == str(value)
```

### Why This Happens

Hypothesis manages the test lifecycle differently from pytest's fixture system. When `@given` decorates a function, Hypothesis becomes the test runner for the function body — it calls it repeatedly with different generated inputs. Pytest fixtures expect to be injected by pytest's own machinery, which only runs once per test function invocation. The two systems are incompatible at the parameter-injection level.

**Rule of thumb:** If your property test needs external resources (filesystem, environment, stdout capture), create and tear them down *inside* the test body using context managers (`with` statements).
