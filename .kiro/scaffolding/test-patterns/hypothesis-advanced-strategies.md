---
name: hypothesis-advanced-strategies
tags: [test, property, hypothesis, strategy]
category: test-patterns
complexity: any
description: Correct Hypothesis strategy syntax to prevent API hallucination
priority: 15
---

# Hypothesis Advanced Strategies Reference

## Strategy Syntax Reference

### `st.from_regex`

Generate strings matching a regular expression.

```python
from hypothesis import given, strategies as st

@given(value=st.from_regex(r"\d{3}-\d{2}-\d{4}", fullmatch=True))
def test_ssn_format(value):
    parts = value.split("-")
    assert len(parts) == 3
    assert len(parts[0]) == 3
    assert len(parts[1]) == 2
    assert len(parts[2]) == 4
```

**Parameters:**
- `regex`: A string pattern or compiled `re.Pattern`.
- `fullmatch` (bool): If `True`, the entire string must match the pattern. Defaults to `False` (partial match allowed).

---

### `st.composite`

Build custom strategies by combining other strategies with draw logic.

```python
from hypothesis import given, strategies as st

@st.composite
def sorted_lists(draw, min_size=0, max_size=10):
    xs = draw(st.lists(st.integers(), min_size=min_size, max_size=max_size))
    return sorted(xs)

@given(xs=sorted_lists(min_size=1))
def test_sorted_list_is_ordered(xs):
    for i in range(len(xs) - 1):
        assert xs[i] <= xs[i + 1]
```

**Rules:**
- The first argument must be named `draw`.
- Call `draw(strategy)` to sample from a strategy inside the composite.
- Return the constructed value at the end.

---

### `st.builds`

Construct objects by calling a callable with generated arguments.

```python
from dataclasses import dataclass
from hypothesis import given, strategies as st

@dataclass
class User:
    name: str
    age: int

@given(user=st.builds(User, name=st.text(min_size=1, max_size=50), age=st.integers(min_value=0, max_value=150)))
def test_user_has_valid_age(user):
    assert 0 <= user.age <= 150
    assert len(user.name) >= 1
```

**Parameters:**
- First argument: the callable (class, function, or factory).
- Remaining keyword arguments: strategies for each parameter.

---

### `st.one_of`

Choose from multiple strategies, generating values from any of them.

```python
from hypothesis import given, strategies as st

@given(value=st.one_of(st.integers(), st.text(), st.booleans()))
def test_value_is_one_of_three_types(value):
    assert isinstance(value, (int, str, bool))
```

**Parameters:**
- Positional arguments: two or more strategies.

---

### `st.just`

Always produce a single fixed value.

```python
from hypothesis import given, strategies as st

@given(value=st.just(42))
def test_just_always_returns_42(value):
    assert value == 42
```

**Use case:** Useful inside `st.one_of` or `st.composite` when one branch must return a constant.

---

### `st.none`

Always produce `None`. Equivalent to `st.just(None)`.

```python
from hypothesis import given, strategies as st

@given(value=st.one_of(st.integers(), st.none()))
def test_nullable_integer(value):
    assert value is None or isinstance(value, int)
```

---

### `st.fixed_dictionaries`

Generate dictionaries with fixed keys and strategy-driven values.

```python
from hypothesis import given, strategies as st

@given(config=st.fixed_dictionaries({
    "host": st.text(min_size=1, max_size=100),
    "port": st.integers(min_value=1, max_value=65535),
    "debug": st.booleans(),
}))
def test_config_has_expected_keys(config):
    assert set(config.keys()) == {"host", "port", "debug"}
    assert 1 <= config["port"] <= 65535
```

**Parameters:**
- `mapping`: A dict where keys are fixed strings and values are strategies.
- `optional` (dict, optional): Keys that may or may not appear in the output.

---

### `st.from_type`

Generate values of a given type using Hypothesis's type inference.

```python
from hypothesis import given, strategies as st

@given(value=st.from_type(int))
def test_from_type_int(value):
    assert isinstance(value, int)
```

**Works with:** Built-in types, `typing` generics, dataclasses, `attrs` classes, and any type with a registered strategy.

---

## Anti-Patterns Table

| Incorrect Usage | Problem | Correct Alternative |
|---|---|---|
| `re.compile(r"\d+").match` as a strategy | `re.match` is a function, not a Hypothesis strategy | `st.from_regex(r"\d+", fullmatch=True)` |
| `st.text().filter(lambda x: x.isdigit())` | Extremely slow — filters discard almost everything | `st.from_regex(r"\d+", fullmatch=True)` |
| `st.sampled_from([])` | Empty sequence raises `InvalidArgument` | `st.nothing()` or guard with `assume(len(items) > 0)` |
| `st.integers().filter(lambda x: x > 0)` | Inefficient; use bounded generation | `st.integers(min_value=1)` |
| `st.lists(st.integers()).filter(lambda x: len(x) > 5)` | Filter discards most short lists | `st.lists(st.integers(), min_size=6)` |
| `random.choice(["a", "b"])` inside a test | Non-reproducible; bypasses Hypothesis shrinking | `st.sampled_from(["a", "b"])` |
| `st.text(alphabet="abc", min_size=5).filter(lambda x: "a" in x)` | Filter may be slow for short alphabets | `st.text(alphabet="abc", min_size=5).map(lambda x: "a" + x[1:])` or use `st.composite` |
| Using `@given` with pytest `tmp_path` fixture | pytest fixtures don't work with `@given` | Use `tempfile.TemporaryDirectory()` inside the test body |

---

## Strategy Composition

### `.map()` — Transform generated values

Apply a function to transform the output of a strategy.

```python
from hypothesis import given, strategies as st

@given(value=st.integers(min_value=0, max_value=100).map(lambda x: x * 2))
def test_even_numbers(value):
    assert value % 2 == 0
    assert 0 <= value <= 200
```

---

### `.filter()` — Constrain with a predicate

Keep only values that satisfy a condition. Use sparingly — prefer bounded generation.

```python
from hypothesis import given, strategies as st

@given(value=st.integers(min_value=-100, max_value=100).filter(lambda x: x != 0))
def test_nonzero_integers(value):
    assert value != 0
    assert 1 / value  # no ZeroDivisionError
```

**Warning:** If the filter rejects more than ~50% of values, Hypothesis will raise `Unsatisfied`. Prefer `.map()` or bounded parameters instead.

---

### `.flatmap()` — Dependent strategies

Generate a value, then use it to construct the next strategy.

```python
from hypothesis import given, strategies as st

@given(
    data=st.integers(min_value=1, max_value=10).flatmap(
        lambda n: st.lists(st.integers(), min_size=n, max_size=n)
    )
)
def test_list_length_matches_drawn_size(data):
    # data is a list whose length was determined by a random int [1, 10]
    assert 1 <= len(data) <= 10
```

**Use case:** When the shape or constraints of one strategy depend on a previously drawn value.

---

### `st.one_of()` — Union of strategies

Combine strategies so Hypothesis picks from any of them.

```python
from hypothesis import given, strategies as st

positive_ints = st.integers(min_value=1)
negative_ints = st.integers(max_value=-1)
zero = st.just(0)

@given(value=st.one_of(positive_ints, negative_ints, zero))
def test_all_integers_covered(value):
    assert isinstance(value, int)
```

**Composition example — combining multiple patterns:**

```python
from hypothesis import given, strategies as st

# A strategy that produces either a valid email-like string or None
email_or_none = st.one_of(
    st.from_regex(r"[a-z]+@[a-z]+\.[a-z]{2,4}", fullmatch=True),
    st.none(),
)

@given(value=email_or_none)
def test_email_or_none(value):
    if value is not None:
        assert "@" in value
```
