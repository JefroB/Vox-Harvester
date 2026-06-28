# Feature: subagent-improvements, Property 8: Checkpoint Command Validation
"""Property test: For any string value for a checkpoint command field, the validator
shall accept non-empty, non-whitespace-only strings of length ≤1024 characters, and
shall reject empty strings, whitespace-only strings, and strings exceeding 1024
characters.

**Validates: Requirements 4.5, 4.6**
"""

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from models.task_graph import TaskMetadata, MAX_COMMAND_LENGTH


# Strategy: valid checkpoint commands — non-empty, non-whitespace-only, ≤1024 chars
valid_commands = st.text(min_size=1, max_size=MAX_COMMAND_LENGTH).filter(
    lambda s: s.strip() != ""
)

# Strategy: whitespace-only strings (at least one char, all whitespace)
whitespace_only = st.text(
    alphabet=st.sampled_from([" ", "\t", "\n", "\r", "\x0b", "\x0c"]),
    min_size=1,
    max_size=100,
)

# Strategy: strings exceeding 1024 characters
too_long_commands = st.text(min_size=MAX_COMMAND_LENGTH + 1, max_size=MAX_COMMAND_LENGTH + 200)


@settings(max_examples=100)
@given(command=valid_commands)
def test_checkpoint_accepts_valid_commands(command: str) -> None:
    """Checkpoint tasks accept non-empty, non-whitespace-only strings ≤1024 chars."""
    task = TaskMetadata(
        task_id="test-task",
        description="A test checkpoint",
        type="checkpoint",
        command=command,
    )
    assert task.command == command


@settings(max_examples=100)
@given(command=whitespace_only)
def test_checkpoint_rejects_whitespace_only(command: str) -> None:
    """Checkpoint tasks reject whitespace-only command strings."""
    with pytest.raises(ValueError, match="whitespace-only"):
        TaskMetadata(
            task_id="test-task",
            description="A test checkpoint",
            type="checkpoint",
            command=command,
        )


@settings(max_examples=100)
@given(command=too_long_commands)
def test_checkpoint_rejects_commands_exceeding_max_length(command: str) -> None:
    """Checkpoint tasks reject commands longer than 1024 characters."""
    with pytest.raises(ValueError, match="at most"):
        TaskMetadata(
            task_id="test-task",
            description="A test checkpoint",
            type="checkpoint",
            command=command,
        )


def test_checkpoint_rejects_empty_string() -> None:
    """Checkpoint tasks reject empty string commands."""
    with pytest.raises(ValueError, match="whitespace-only"):
        TaskMetadata(
            task_id="test-task",
            description="A test checkpoint",
            type="checkpoint",
            command="",
        )


def test_checkpoint_rejects_none_command() -> None:
    """Checkpoint tasks reject None as the command field."""
    with pytest.raises(ValueError, match="non-empty"):
        TaskMetadata(
            task_id="test-task",
            description="A test checkpoint",
            type="checkpoint",
            command=None,
        )
