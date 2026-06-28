---
name: hypothesis-stateful-testing
tags: [test, property, hypothesis, stateful]
category: test-patterns
complexity: complex
description: Stateful and controlled-sequence testing patterns for threshold and state-transition scenarios
priority: 12
---

# Hypothesis Stateful Testing Patterns

Patterns for testing stateful systems where purely random inputs miss critical state transitions. These techniques guarantee coverage of threshold crossings and state-machine invariants.

---

## 1. Deterministic Prefix + Random Suffix Pattern

### Concept

When testing stateful systems, purely random action sequences may never reach interesting states. The **deterministic prefix** guarantees a specific state transition occurs, then the **random suffix** exercises the system from that state onward to verify invariants hold.

This is useful when:
- A bug only manifests after a specific sequence of setup steps
- You need to test post-transition behavior across many random continuations
- Random exploration alone is unlikely to trigger the state you care about

### Working Example

```python
from hypothesis import given, settings, assume
from hypothesis import strategies as st


class ConnectionPool:
    """Example system under test with state transitions."""

    def __init__(self, max_connections: int = 5):
        self.max_connections = max_connections
        self.active: list[str] = []
        self.closed: list[str] = []

    def connect(self, name: str) -> bool:
        if len(self.active) >= self.max_connections:
            return False
        self.active.append(name)
        return True

    def disconnect(self, name: str) -> bool:
        if name in self.active:
            self.active.remove(name)
            self.closed.append(name)
            return True
        return False

    def is_full(self) -> bool:
        return len(self.active) >= self.max_connections


# Strategy: deterministic prefix fills the pool, random suffix exercises it
@given(
    random_actions=st.lists(
        st.tuples(
            st.sampled_from(["connect", "disconnect"]),
            st.text(min_size=1, max_size=10, alphabet="abcdefgh"),
        ),
        min_size=1,
        max_size=20,
    )
)
@settings(max_examples=200)
def test_pool_invariants_after_saturation(random_actions):
    """After deterministic prefix saturates the pool, random actions maintain invariants.

    Feature: local-coder-reliability, Deterministic prefix + random suffix
    Validates: Requirements 2.2
    """
    pool = ConnectionPool(max_connections=3)

    # --- Deterministic prefix: guarantee the pool is full ---
    assert pool.connect("fixed_a")
    assert pool.connect("fixed_b")
    assert pool.connect("fixed_c")
    assert pool.is_full()

    # --- Random suffix: exercise the system from the saturated state ---
    for action, name in random_actions:
        if action == "connect":
            result = pool.connect(name)
            # Invariant: cannot exceed max when full (unless disconnect happened)
            assert len(pool.active) <= pool.max_connections
        elif action == "disconnect":
            pool.disconnect(name)

        # Invariant: active count is always non-negative and bounded
        assert 0 <= len(pool.active) <= pool.max_connections
```

### Key Points

- The deterministic prefix uses direct assertions to confirm the state was reached.
- The random suffix uses strategies (`st.lists`, `st.tuples`, `st.sampled_from`) to explore behavior.
- Invariants are checked after every random action, not just at the end.

---

## 2. Controlled Element Strategies with `st.lists`

### Concept

When testing threshold-crossing behavior, purely random lists may rarely (or never) produce inputs that cross the threshold. **Controlled element strategies** construct lists with guaranteed distributions — ensuring at least N elements satisfy a condition.

### Working Example: Guarantee Threshold Crossing

```python
from hypothesis import given, settings
from hypothesis import strategies as st


def compute_alert_level(readings: list[float], threshold: float = 80.0) -> str:
    """Returns 'critical' if more than 60% of readings exceed threshold."""
    if not readings:
        return "normal"
    above = sum(1 for r in readings if r > threshold)
    ratio = above / len(readings)
    if ratio > 0.6:
        return "critical"
    elif ratio > 0.3:
        return "warning"
    return "normal"


@st.composite
def readings_guaranteeing_critical(draw):
    """Generate a list of readings where >60% exceed the threshold.

    Strategy: draw a total size, then split into 'above' and 'below' portions
    with the above portion guaranteed to be >60% of total.
    """
    total_size = draw(st.integers(min_value=5, max_value=50))

    # At least 61% must be above threshold
    min_above = int(total_size * 0.61) + 1
    num_above = draw(st.integers(min_value=min_above, max_value=total_size))
    num_below = total_size - num_above

    above_values = draw(
        st.lists(
            st.floats(min_value=80.1, max_value=200.0, allow_nan=False, allow_infinity=False),
            min_size=num_above,
            max_size=num_above,
        )
    )
    below_values = draw(
        st.lists(
            st.floats(min_value=0.0, max_value=80.0, allow_nan=False, allow_infinity=False),
            min_size=num_below,
            max_size=num_below,
        )
    )

    # Shuffle to avoid position bias
    combined = above_values + below_values
    indices = draw(st.permutations(range(len(combined))))
    return [combined[i] for i in indices]


@given(readings=readings_guaranteeing_critical())
@settings(max_examples=200)
def test_critical_alert_when_threshold_crossed(readings):
    """When >60% of readings exceed threshold, alert level must be 'critical'.

    Feature: local-coder-reliability, Controlled element strategies
    Validates: Requirements 2.3
    """
    result = compute_alert_level(readings, threshold=80.0)
    assert result == "critical", f"Expected 'critical' but got '{result}' for {len(readings)} readings"


@st.composite
def readings_below_warning(draw):
    """Generate readings where <=30% exceed threshold (should be 'normal')."""
    total_size = draw(st.integers(min_value=5, max_value=50))

    # At most 30% above threshold
    max_above = int(total_size * 0.3)
    num_above = draw(st.integers(min_value=0, max_value=max_above))
    num_below = total_size - num_above

    above_values = draw(
        st.lists(
            st.floats(min_value=80.1, max_value=200.0, allow_nan=False, allow_infinity=False),
            min_size=num_above,
            max_size=num_above,
        )
    )
    below_values = draw(
        st.lists(
            st.floats(min_value=0.0, max_value=80.0, allow_nan=False, allow_infinity=False),
            min_size=num_below,
            max_size=num_below,
        )
    )

    combined = above_values + below_values
    indices = draw(st.permutations(range(len(combined))))
    return [combined[i] for i in indices]


@given(readings=readings_below_warning())
@settings(max_examples=200)
def test_normal_alert_below_threshold(readings):
    """When <=30% of readings exceed threshold, alert level must be 'normal'.

    Feature: local-coder-reliability, Controlled element strategies
    Validates: Requirements 2.3
    """
    result = compute_alert_level(readings, threshold=80.0)
    assert result == "normal", f"Expected 'normal' but got '{result}'"
```

### Key Points

- Use `@st.composite` to build strategies with precise control over element distribution.
- Split the list into "above" and "below" portions, then shuffle to avoid position-dependent bugs.
- Draw the split ratio from a constrained integer strategy to guarantee the threshold is crossed.
- This avoids the trap of `st.lists(st.floats(...))` which almost never produces the right ratio by chance.

---

## 3. RuleBasedStateMachine Example

### Concept

Hypothesis `RuleBasedStateMachine` explores state spaces by randomly selecting from defined rules, respecting preconditions, and checking invariants after every step. This finds complex multi-step bugs that unit tests miss.

### Full Working Example

```python
from hypothesis import settings
from hypothesis.stateful import (
    RuleBasedStateMachine,
    initialize,
    invariant,
    precondition,
    rule,
    Bundle,
)
from hypothesis import strategies as st


class BankAccount:
    """System under test: a simple bank account with overdraft protection."""

    def __init__(self, overdraft_limit: float = 100.0):
        self.balance: float = 0.0
        self.overdraft_limit = overdraft_limit
        self.transactions: list[tuple[str, float]] = []
        self.frozen: bool = False

    def deposit(self, amount: float) -> bool:
        if self.frozen or amount <= 0:
            return False
        self.balance += amount
        self.transactions.append(("deposit", amount))
        return True

    def withdraw(self, amount: float) -> bool:
        if self.frozen or amount <= 0:
            return False
        if self.balance - amount < -self.overdraft_limit:
            return False
        self.balance -= amount
        self.transactions.append(("withdraw", amount))
        return True

    def freeze(self) -> None:
        self.frozen = True
        self.transactions.append(("freeze", 0.0))

    def unfreeze(self) -> None:
        self.frozen = False
        self.transactions.append(("unfreeze", 0.0))


class BankAccountStateMachine(RuleBasedStateMachine):
    """Stateful test exploring BankAccount behavior across all valid action sequences."""

    def __init__(self):
        super().__init__()
        self.account = BankAccount(overdraft_limit=100.0)
        self.expected_balance: float = 0.0
        self.expected_frozen: bool = False

    @initialize()
    def init_account(self):
        self.account = BankAccount(overdraft_limit=100.0)
        self.expected_balance = 0.0
        self.expected_frozen = False

    @rule(amount=st.floats(min_value=0.01, max_value=10000.0, allow_nan=False, allow_infinity=False))
    @precondition(lambda self: not self.expected_frozen)
    def deposit(self, amount):
        result = self.account.deposit(amount)
        assert result is True
        self.expected_balance += amount

    @rule(amount=st.floats(min_value=0.01, max_value=10000.0, allow_nan=False, allow_infinity=False))
    @precondition(lambda self: not self.expected_frozen)
    def withdraw_valid(self, amount):
        if self.expected_balance - amount >= -100.0:
            result = self.account.withdraw(amount)
            assert result is True
            self.expected_balance -= amount
        else:
            result = self.account.withdraw(amount)
            assert result is False

    @rule()
    @precondition(lambda self: not self.expected_frozen)
    def freeze_account(self):
        self.account.freeze()
        self.expected_frozen = True

    @rule()
    @precondition(lambda self: self.expected_frozen)
    def unfreeze_account(self):
        self.account.unfreeze()
        self.expected_frozen = False

    @rule(amount=st.floats(min_value=0.01, max_value=10000.0, allow_nan=False, allow_infinity=False))
    @precondition(lambda self: self.expected_frozen)
    def deposit_while_frozen(self, amount):
        result = self.account.deposit(amount)
        assert result is False  # Deposits rejected when frozen

    @rule(amount=st.floats(min_value=0.01, max_value=10000.0, allow_nan=False, allow_infinity=False))
    @precondition(lambda self: self.expected_frozen)
    def withdraw_while_frozen(self, amount):
        result = self.account.withdraw(amount)
        assert result is False  # Withdrawals rejected when frozen

    @invariant()
    def balance_matches_model(self):
        """Balance always matches our expected model state."""
        assert abs(self.account.balance - self.expected_balance) < 1e-9, (
            f"Balance drift: actual={self.account.balance}, expected={self.expected_balance}"
        )

    @invariant()
    def balance_within_overdraft_limit(self):
        """Balance never goes below the negative overdraft limit."""
        assert self.account.balance >= -self.account.overdraft_limit - 1e-9, (
            f"Balance {self.account.balance} exceeds overdraft limit {self.account.overdraft_limit}"
        )

    @invariant()
    def frozen_state_consistent(self):
        """Frozen state in model matches actual account state."""
        assert self.account.frozen == self.expected_frozen


TestBankAccount = BankAccountStateMachine.TestCase
TestBankAccount.settings = settings(max_examples=100, stateful_step_count=30)
```

### Structure Breakdown

| Component | Purpose |
|-----------|---------|
| `__init__` | Initialize the model state that mirrors the system under test |
| `@initialize()` | Reset state at the start of each test run |
| `@rule(...)` | Define actions the state machine can take, with strategy-generated arguments |
| `@precondition(...)` | Guard rules so they only fire when the system is in a valid state for that action |
| `@invariant()` | Assertions checked after every single step — catches violations immediately |
| `TestCase` | Expose the state machine as a standard pytest test class |

---

## 4. Decision Matrix: Controlled Construction vs. Purely Random

### When to Use Controlled Construction

| Scenario | Why Random Fails | Controlled Approach |
|----------|-----------------|-------------------|
| **Threshold testing** | Random values almost never produce the exact ratio needed to cross a threshold | `@st.composite` strategy that guarantees N elements above/below the boundary |
| **Guaranteed state transitions** | Random action sequences may never reach the target state within step limits | Deterministic prefix forces the transition, random suffix explores from there |
| **Reproducible edge cases** | Known edge cases (empty + full, exact boundary) are astronomically unlikely to appear randomly | Construct the exact scenario, then randomize surrounding context |
| **Ordered sequences** | Random permutations rarely produce meaningful orderings (sorted, reverse-sorted, interleaved) | Draw random elements, then apply a deterministic ordering before passing to the system |
| **Protocol compliance** | Random byte sequences are almost never valid protocol messages | Build valid message structure with random field values |

### When to Use Purely Random Generation

| Scenario | Why Controlled Hurts | Random Approach |
|----------|---------------------|----------------|
| **General robustness** | Over-constraining inputs misses unexpected failure modes | `st.text()`, `st.binary()`, `st.from_type()` with minimal constraints |
| **Discovering unknown edge cases** | You can't construct what you haven't imagined | Let Hypothesis explore freely; shrinking reveals minimal failures |
| **Fuzz testing** | Controlled inputs are biased toward expected behavior | Wide input ranges with no distribution constraints |
| **API contract testing** | Specific constructions test your assumptions, not the contract | Generate any valid input per the type signature |
| **Regression discovery** | After fixing a bug, random testing catches related issues you didn't consider | Broad strategy covering the full input space |

### Decision Flowchart

```
Is there a specific state/threshold you MUST reach?
├── YES → Does random generation reliably reach it within 200 examples?
│         ├── YES → Use purely random (simpler, broader coverage)
│         └── NO  → Use controlled construction (deterministic prefix or composite strategy)
└── NO  → Are you testing general correctness across all inputs?
          ├── YES → Use purely random
          └── NO  → Use controlled construction for the specific scenario
```

### Combining Both Approaches

The most robust test suites use both:

1. **Controlled tests** verify known-critical paths are always exercised.
2. **Random tests** discover unknown failure modes you didn't think to construct.

```python
# Controlled: guarantee the threshold is crossed
@given(readings=readings_guaranteeing_critical())
def test_critical_detection_guaranteed(readings):
    assert compute_alert_level(readings) == "critical"


# Random: discover any input that breaks the contract
@given(readings=st.lists(st.floats(min_value=0, max_value=200, allow_nan=False, allow_infinity=False), min_size=1, max_size=100))
def test_alert_level_always_valid(readings):
    result = compute_alert_level(readings)
    assert result in ("normal", "warning", "critical")
```

This pairing ensures you both **cover what you know matters** and **discover what you don't know yet**.
