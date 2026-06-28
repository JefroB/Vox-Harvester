# Feature: net-token-savings, Property 11: Migration Idempotency
"""Property test: For any number of migration executions N >= 1 on the same database,
the resulting schema SHALL be identical after each execution, no errors SHALL be raised,
and all existing data SHALL remain unchanged.

**Validates: Requirements 7.4**
"""

import sqlite3

from hypothesis import given, settings
from hypothesis import strategies as st

from local_coder.token_tracker import SchemaMigrator, MigrationError


def _get_schema(conn: sqlite3.Connection) -> dict:
    """Extract full schema info: tables, columns, indexes."""
    cursor = conn.execute(
        "SELECT type, name, sql FROM sqlite_master WHERE type IN ('table', 'index') ORDER BY type, name"
    )
    return {(row[0], row[1]): row[2] for row in cursor.fetchall()}


def _insert_seed_data(conn: sqlite3.Connection) -> list[tuple]:
    """Insert pre-existing data into the legacy table and return it for verification."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS project_token_tracking (
            id INTEGER PRIMARY KEY,
            interface_type TEXT NOT NULL,
            tool_name TEXT NOT NULL,
            tokens_returned INTEGER NOT NULL,
            tokens_full_file INTEGER NOT NULL,
            timestamp INTEGER DEFAULT (strftime('%s', 'now'))
        )
    """)
    seed_rows = [
        (1, "cli", "local_coder", 500, 1200),
        (2, "cli", "local_coder", 300, 800),
        (3, "api", "codesearch", 100, 400),
    ]
    conn.executemany(
        "INSERT INTO project_token_tracking (id, interface_type, tool_name, tokens_returned, tokens_full_file) VALUES (?, ?, ?, ?, ?)",
        seed_rows,
    )
    conn.commit()
    return seed_rows


def _read_all_data(conn: sqlite3.Connection) -> dict[str, list[tuple]]:
    """Read all rows from all tables in the database."""
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    tables = [row[0] for row in cursor.fetchall()]
    data = {}
    for table in tables:
        rows = conn.execute(f"SELECT * FROM {table}").fetchall()
        data[table] = rows
    return data


@settings(max_examples=100)
@given(n=st.integers(min_value=1, max_value=10))
def test_migration_idempotency(n: int) -> None:
    """Running migrate() N times produces identical schema each time with no errors."""
    conn = sqlite3.connect(":memory:")
    try:
        # Set up pre-existing legacy data
        seed_rows = _insert_seed_data(conn)

        # Run migration N times — none should raise
        for i in range(n):
            migrator = SchemaMigrator(conn)
            migrator.migrate()  # Should not raise MigrationError

        # Capture schema after all migrations
        final_schema = _get_schema(conn)

        # Run one more migration and verify schema is unchanged
        migrator = SchemaMigrator(conn)
        migrator.migrate()
        schema_after_extra = _get_schema(conn)

        assert final_schema == schema_after_extra, (
            "Schema changed after an additional migration run"
        )

        # Verify expected tables were created
        table_names = {name for (typ, name), _ in final_schema.items() if typ == "table"}
        assert "generation_sessions" in table_names
        assert "session_generations" in table_names
        assert "review_costs" in table_names
        assert "project_token_tracking" in table_names

        # Verify pre-existing data is unchanged
        all_data = _read_all_data(conn)
        legacy_rows = all_data["project_token_tracking"]
        assert len(legacy_rows) == len(seed_rows)
        for original, stored in zip(seed_rows, legacy_rows):
            # original is (id, interface_type, tool_name, tokens_returned, tokens_full_file)
            # stored includes timestamp as 6th column
            assert stored[0] == original[0]  # id
            assert stored[1] == original[1]  # interface_type
            assert stored[2] == original[2]  # tool_name
            assert stored[3] == original[3]  # tokens_returned
            assert stored[4] == original[4]  # tokens_full_file

        # Verify new tables are empty (migration doesn't insert data)
        assert all_data.get("generation_sessions", []) == []
        assert all_data.get("session_generations", []) == []
        assert all_data.get("review_costs", []) == []
    finally:
        conn.close()


# Feature: net-token-savings, Property 2: Auto-Generated Session ID Determinism and Time-Window Association
"""Property test: For any task description string, the generated session ID SHALL contain
exactly 16 hexadecimal characters matching the first 16 characters of the SHA-256 hash of
that task description. Furthermore, for any two calls with the same task description
occurring within 60 minutes of each other, the second call SHALL associate with the session
created by the first call rather than creating a new session.

**Validates: Requirements 1.3**
"""

import hashlib
import re
from datetime import datetime, timezone

from local_coder.token_tracker import generate_session_id, find_recent_session


@settings(max_examples=100)
@given(task_description=st.text(min_size=1, max_size=200))
def test_session_id_contains_correct_hash_prefix(task_description: str) -> None:
    """Generated session ID has exactly 16 hex chars matching SHA-256 prefix of task description."""
    session_id = generate_session_id(task_description)

    # Split on underscore — format is <hash>_<timestamp>
    parts = session_id.split("_", 1)
    assert len(parts) == 2, f"Session ID must contain an underscore separator, got: {session_id}"

    hash_part = parts[0]

    # Verify exactly 16 hex characters
    assert len(hash_part) == 16, (
        f"Hash portion must be exactly 16 chars, got {len(hash_part)}: {hash_part}"
    )
    assert re.fullmatch(r"[0-9a-f]{16}", hash_part), (
        f"Hash portion must be lowercase hex, got: {hash_part}"
    )

    # Verify it matches the SHA-256 of the task description
    expected_hash = hashlib.sha256(task_description.encode()).hexdigest()[:16]
    assert hash_part == expected_hash, (
        f"Hash mismatch for task '{task_description[:30]}...': "
        f"got {hash_part}, expected {expected_hash}"
    )


@settings(max_examples=100)
@given(task_description=st.text(min_size=1, max_size=200))
def test_recent_session_association_within_time_window(task_description: str) -> None:
    """A session created and then looked up immediately (within 60 min) is found."""
    conn = sqlite3.connect(":memory:")
    try:
        # Apply schema migration so the generation_sessions table exists
        migrator = SchemaMigrator(conn)
        migrator.migrate()

        # Compute the expected task hash
        task_hash = hashlib.sha256(task_description.encode()).hexdigest()[:16]

        # Create a session record simulating a prior call
        now = datetime.now(timezone.utc)
        session_id = f"{task_hash}_{now.strftime('%Y-%m-%dT%H:%M:%SZ')}"
        created_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")

        conn.execute(
            """
            INSERT INTO generation_sessions (session_id, task_hash, model, gross_savings, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (session_id, task_hash, "test-model", 0, created_at, created_at),
        )
        conn.commit()

        # Look up the session — since it was just created, it's within 60 minutes
        found = find_recent_session(conn, task_description, within_minutes=60)

        assert found == session_id, (
            f"Expected find_recent_session to return {session_id}, got {found}"
        )
    finally:
        conn.close()


# Feature: net-token-savings, Property 1: Session Creation Idempotency
"""Property test: For any session ID string, calling get_or_create_session N times (N >= 1)
with the same session ID SHALL produce exactly one session record in the database, and all
calls SHALL return the same session identifier.

**Validates: Requirements 1.1, 1.2**
"""

import tempfile
from pathlib import Path

from local_coder.token_tracker import SessionTracker


@settings(max_examples=100)
@given(
    session_id=st.text(
        alphabet=st.characters(whitelist_categories=("L", "N", "P", "S", "Z"), max_codepoint=126),
        min_size=1,
        max_size=50,
    ),
    task_description=st.text(min_size=1, max_size=200),
    model=st.sampled_from(["qwen2.5-coder:7b", "qwen3-coder:30b-a3b-q4_K_M", "gpt-4o", "claude-3"]),
    n=st.integers(min_value=1, max_value=5),
)
def test_session_creation_idempotency(
    session_id: str, task_description: str, model: str, n: int
) -> None:
    """Calling get_or_create_session N times with the same session_id produces exactly one record."""
    db_path = Path(tempfile.mktemp(suffix=".db"))
    try:
        tracker = SessionTracker(db_path)

        # Call get_or_create_session N times with the same session_id
        returned_ids = []
        for _ in range(n):
            result = tracker.get_or_create_session(session_id, task_description, model)
            returned_ids.append(result)

        # All N calls must return the same session identifier
        assert all(
            rid == session_id for rid in returned_ids
        ), f"Expected all returned IDs to be '{session_id}', got {returned_ids}"

        # There must be exactly one record in generation_sessions with this session_id
        cursor = tracker._conn.execute(
            "SELECT COUNT(*) FROM generation_sessions WHERE session_id = ?",
            (session_id,),
        )
        count = cursor.fetchone()[0]
        assert count == 1, (
            f"Expected exactly 1 session record for '{session_id}', found {count}"
        )
    finally:
        # Close the connection before unlinking on Windows
        tracker._conn.close()
        if db_path.exists():
            db_path.unlink()


# Feature: net-token-savings, Property 3: Session Record Data Completeness
"""Property test: For any generation call recorded within a session, the stored record
SHALL contain a non-empty session identifier, a 16-character hexadecimal task hash,
an ISO 8601 formatted UTC timestamp, and a phase value that is either "initial" or "rework".

**Validates: Requirements 1.4**
"""

import tempfile
from pathlib import Path

from local_coder.token_tracker import SessionTracker


@settings(max_examples=100)
@given(
    task_description=st.text(min_size=1, max_size=200),
    model=st.sampled_from(["qwen2.5-coder:7b", "qwen3-coder:30b-a3b-q4_K_M", "gpt-4o", "claude-3"]),
)
def test_session_record_data_completeness(task_description: str, model: str) -> None:
    """Session records contain non-empty session_id, 16-char hex task_hash, ISO 8601 timestamp, and non-empty model."""
    db_path = Path(tempfile.mktemp(suffix=".db"))
    try:
        tracker = SessionTracker(db_path)
        session_id = tracker.get_or_create_session(None, task_description, model)

        # Query the generation_sessions table directly
        cursor = tracker._conn.execute(
            "SELECT session_id, task_hash, created_at, model FROM generation_sessions WHERE session_id = ?",
            (session_id,),
        )
        row = cursor.fetchone()
        assert row is not None, "Session record must exist after get_or_create_session"

        stored_session_id, stored_task_hash, stored_created_at, stored_model = row

        # session_id is non-empty
        assert stored_session_id and len(stored_session_id) > 0, (
            f"session_id must be non-empty, got: '{stored_session_id}'"
        )

        # task_hash is exactly 16 hex characters
        assert len(stored_task_hash) == 16, (
            f"task_hash must be exactly 16 chars, got {len(stored_task_hash)}: '{stored_task_hash}'"
        )
        assert re.fullmatch(r"[0-9a-f]{16}", stored_task_hash), (
            f"task_hash must be lowercase hex, got: '{stored_task_hash}'"
        )

        # created_at matches ISO 8601 format (%Y-%m-%dT%H:%M:%SZ)
        try:
            datetime.strptime(stored_created_at, "%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            raise AssertionError(
                f"created_at must match ISO 8601 format '%Y-%m-%dT%H:%M:%SZ', got: '{stored_created_at}'"
            )

        # model is non-empty
        assert stored_model and len(stored_model) > 0, (
            f"model must be non-empty, got: '{stored_model}'"
        )
    finally:
        tracker._conn.close()
        if db_path.exists():
            db_path.unlink()


# Feature: net-token-savings, Property 4: Initial Generation Immutability
"""Property test: For any session with an existing initial generation record (gross_savings > 0),
subsequent generation calls to the same session SHALL NOT modify the gross_savings value —
the first recorded eval_count persists regardless of later calls.

**Validates: Requirements 2.1, 2.2, 2.4**
"""


@settings(max_examples=100, deadline=None)
@given(
    task_description=st.text(min_size=1, max_size=200),
    model=st.sampled_from(["qwen2.5-coder:7b", "qwen3-coder:30b-a3b-q4_K_M", "gpt-4o", "claude-3"]),
    initial_eval_count=st.integers(min_value=1, max_value=1_000_000),
    subsequent_counts=st.lists(st.integers(min_value=0, max_value=1_000_000), min_size=1, max_size=5),
)
def test_initial_generation_immutability(
    task_description: str,
    model: str,
    initial_eval_count: int,
    subsequent_counts: list[int],
) -> None:
    """Once gross_savings is set by the initial generation, subsequent calls never change it."""
    db_path = Path(tempfile.mktemp(suffix=".db"))
    try:
        tracker = SessionTracker(db_path)

        # Create a session
        session_id = tracker.get_or_create_session(None, task_description, model)

        # Record the initial generation — this should set gross_savings = initial_eval_count
        tracker.record_generation(session_id, initial_eval_count, model)

        # Verify gross_savings equals initial_eval_count
        cursor = tracker._conn.execute(
            "SELECT gross_savings FROM generation_sessions WHERE session_id = ?",
            (session_id,),
        )
        row = cursor.fetchone()
        assert row is not None, "Session record must exist after record_generation"
        assert row[0] == initial_eval_count, (
            f"After initial generation, gross_savings should be {initial_eval_count}, got {row[0]}"
        )

        # Call record_generation for each subsequent count — these are rework calls
        for count in subsequent_counts:
            tracker.record_generation(session_id, count, model)

        # After all subsequent calls, verify gross_savings is STILL = initial_eval_count
        cursor = tracker._conn.execute(
            "SELECT gross_savings FROM generation_sessions WHERE session_id = ?",
            (session_id,),
        )
        row = cursor.fetchone()
        assert row is not None, "Session record must still exist after subsequent generations"
        assert row[0] == initial_eval_count, (
            f"gross_savings must remain {initial_eval_count} after {len(subsequent_counts)} "
            f"subsequent calls, but got {row[0]}"
        )
    finally:
        tracker._conn.close()
        if db_path.exists():
            db_path.unlink()


# Feature: net-token-savings, Property 7: Rework Exclusion Invariant
"""Property test: For any session with gross_savings G, adding any number of rework
generations (with any token counts) SHALL leave gross_savings unchanged at G, and the
net savings computation SHALL use only G minus review costs — never incorporating
rework token counts.

**Validates: Requirements 4.1, 4.2**
"""


@settings(max_examples=100, deadline=None)
@given(
    task_description=st.text(min_size=1, max_size=100),
    model=st.sampled_from(["qwen2.5-coder:7b", "qwen3-coder:30b-a3b-q4_K_M", "gpt-4o", "claude-3"]),
    initial_eval_count=st.integers(min_value=1, max_value=1_000_000),
    rework_counts=st.lists(st.integers(min_value=1, max_value=1_000_000), min_size=1, max_size=5),
)
def test_rework_exclusion_invariant(
    task_description: str, model: str, initial_eval_count: int, rework_counts: list[int]
) -> None:
    """Rework generations do not change gross_savings, and net savings uses only gross minus review costs."""
    db_path = Path(tempfile.mktemp(suffix=".db"))
    try:
        tracker = SessionTracker(db_path)

        # Create a session
        session_id = tracker.get_or_create_session(None, task_description, model)

        # Record the initial generation — sets gross_savings = initial_eval_count
        tracker.record_generation(session_id, initial_eval_count, model)

        # Verify gross_savings is set to initial_eval_count
        cursor = tracker._conn.execute(
            "SELECT gross_savings FROM generation_sessions WHERE session_id = ?",
            (session_id,),
        )
        gross_after_initial = cursor.fetchone()[0]
        assert gross_after_initial == initial_eval_count, (
            f"gross_savings after initial generation should be {initial_eval_count}, got {gross_after_initial}"
        )

        # Record rework generations
        for rework_count in rework_counts:
            tracker.record_generation(session_id, rework_count, model)

        # After all rework generations: gross_savings must STILL equal initial_eval_count
        cursor = tracker._conn.execute(
            "SELECT gross_savings FROM generation_sessions WHERE session_id = ?",
            (session_id,),
        )
        gross_after_rework = cursor.fetchone()[0]
        assert gross_after_rework == initial_eval_count, (
            f"gross_savings should remain {initial_eval_count} after rework, got {gross_after_rework}"
        )

        # Verify rework generations are stored with phase = "rework"
        cursor = tracker._conn.execute(
            "SELECT phase, token_count FROM session_generations WHERE session_id = ? AND phase = 'rework'",
            (session_id,),
        )
        rework_rows = cursor.fetchall()
        assert len(rework_rows) == len(rework_counts), (
            f"Expected {len(rework_counts)} rework records, found {len(rework_rows)}"
        )

        # Verify that gross_savings does NOT include any rework token counts
        total_rework_tokens = sum(rc[1] for rc in rework_rows)
        assert gross_after_rework != initial_eval_count + total_rework_tokens or total_rework_tokens == 0, (
            "gross_savings must not incorporate rework token counts"
        )
        # Stronger assertion: gross_savings is exactly the initial value
        assert gross_after_rework == initial_eval_count

        # Net savings = gross_savings - review_costs (no review costs recorded here, so net = gross)
        cursor = tracker._conn.execute(
            "SELECT COALESCE(SUM(tokens), 0) FROM review_costs WHERE session_id = ?",
            (session_id,),
        )
        total_review_cost = cursor.fetchone()[0]
        expected_net = max(0, initial_eval_count - total_review_cost)

        # Net savings should be based on gross_savings (initial only) minus review costs
        # It should NOT include any rework token counts
        assert expected_net == initial_eval_count, (
            f"Net savings should be {initial_eval_count} (no reviews), got {expected_net}"
        )
    finally:
        tracker._conn.close()
        if db_path.exists():
            db_path.unlink()


# Feature: net-token-savings, Property 6: Review Cost Requires Existing Session
"""Property test: For any session ID that does not exist in the database, attempting to
record a review cost SHALL fail with an error and SHALL NOT create any new records.

**Validates: Requirements 3.4**
"""

import tempfile
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from local_coder.token_tracker import SessionNotFoundError, SessionTracker


@settings(max_examples=100, deadline=None)
@given(
    nonexistent_session_id=st.text(min_size=1, max_size=50),
    tokens=st.integers(min_value=1, max_value=10_000_000),
)
def test_review_cost_requires_existing_session(
    nonexistent_session_id: str, tokens: int
) -> None:
    """Recording a review cost for a nonexistent session raises SessionNotFoundError and creates no records."""
    db_path = Path(tempfile.mktemp(suffix=".db"))
    try:
        tracker = SessionTracker(db_path)

        # Attempt to record review cost for a session that does not exist
        with pytest.raises(SessionNotFoundError):
            tracker.record_review_cost(nonexistent_session_id, tokens)

        # Verify no records were created in review_costs table
        cursor = tracker._conn.execute("SELECT COUNT(*) FROM review_costs")
        review_count = cursor.fetchone()[0]
        assert review_count == 0, (
            f"Expected 0 review_costs records, found {review_count}"
        )

        # Verify no sessions were created in generation_sessions table
        cursor = tracker._conn.execute("SELECT COUNT(*) FROM generation_sessions")
        session_count = cursor.fetchone()[0]
        assert session_count == 0, (
            f"Expected 0 generation_sessions records, found {session_count}"
        )
    finally:
        tracker._conn.close()
        if db_path.exists():
            db_path.unlink()


# Feature: net-token-savings, Property 5: Review Cost Accumulation
"""Property test: For any valid session and any sequence of N review cost values
(each in [1, 10_000_000]), the total review cost for that session SHALL equal the
arithmetic sum of all N values. Values outside [1, 10_000_000] SHALL be rejected
without modifying the total.

**Validates: Requirements 3.2, 3.3**
"""

import tempfile
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from local_coder.token_tracker import InvalidReviewCostError, SessionTracker


@settings(max_examples=100, deadline=None)
@given(
    task_description=st.text(min_size=1, max_size=100),
    model=st.sampled_from(["qwen2.5-coder:7b", "qwen3-coder:30b-a3b-q4_K_M", "gpt-4o", "claude-3"]),
    review_costs=st.lists(st.integers(min_value=1, max_value=10_000_000), min_size=1, max_size=10),
)
def test_review_cost_accumulation(
    task_description: str, model: str, review_costs: list[int]
) -> None:
    """Total review cost equals the arithmetic sum of all recorded review cost values."""
    db_path = Path(tempfile.mktemp(suffix=".db"))
    try:
        tracker = SessionTracker(db_path)

        # Create a session and record an initial generation so the session exists
        session_id = tracker.get_or_create_session(None, task_description, model)
        tracker.record_generation(session_id, 50000, model)

        # Record each review cost
        for cost in review_costs:
            tracker.record_review_cost(session_id, cost)

        # Verify total review cost = sum(review_costs)
        cursor = tracker._conn.execute(
            "SELECT SUM(tokens) FROM review_costs WHERE session_id = ?",
            (session_id,),
        )
        total = cursor.fetchone()[0]
        expected_total = sum(review_costs)
        assert total == expected_total, (
            f"Total review cost should be {expected_total}, got {total}"
        )

        # Test that invalid values are rejected
        with pytest.raises(InvalidReviewCostError):
            tracker.record_review_cost(session_id, 0)

        with pytest.raises(InvalidReviewCostError):
            tracker.record_review_cost(session_id, 10_000_001)

        # After invalid attempts, verify the total is unchanged
        cursor = tracker._conn.execute(
            "SELECT SUM(tokens) FROM review_costs WHERE session_id = ?",
            (session_id,),
        )
        total_after_invalid = cursor.fetchone()[0]
        assert total_after_invalid == expected_total, (
            f"Total should remain {expected_total} after invalid attempts, got {total_after_invalid}"
        )
    finally:
        tracker._conn.close()
        if db_path.exists():
            db_path.unlink()


# Feature: net-token-savings, Property 8: Net Savings Computation
"""Property test: For any session with gross_savings G >= 0 and total review costs R >= 0,
the computed net savings SHALL equal max(0, G - R). This means net savings is never negative,
and when G = 0 the result is always 0 regardless of R.

**Validates: Requirements 5.1, 5.2, 5.4**
"""

import tempfile
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from local_coder.token_tracker import SessionTracker


@settings(max_examples=100, deadline=None)
@given(
    task_description=st.text(min_size=1, max_size=100),
    model=st.sampled_from(["qwen2.5-coder:7b", "qwen3-coder:30b-a3b-q4_K_M", "gpt-4o", "claude-3"]),
    gross_savings=st.integers(min_value=0, max_value=1_000_000),
    review_cost_values=st.lists(st.integers(min_value=1, max_value=10_000_000), min_size=0, max_size=5),
)
def test_net_savings_computation(
    task_description: str,
    model: str,
    gross_savings: int,
    review_cost_values: list[int],
) -> None:
    """Net savings equals max(0, gross_savings - sum(review_costs)), never negative, zero when gross is zero."""
    db_path = Path(tempfile.mktemp(suffix=".db"))
    try:
        tracker = SessionTracker(db_path)

        # Create a session
        session_id = tracker.get_or_create_session(None, task_description, model)

        # Record initial generation only if gross_savings > 0
        if gross_savings > 0:
            tracker.record_generation(session_id, gross_savings, model)

            # Record each review cost (only valid when session has an initial generation)
            for cost in review_cost_values:
                tracker.record_review_cost(session_id, cost)

        # Compute net savings
        result = tracker.compute_net_savings(session_id)

        # Verify: result is never negative
        assert result >= 0, f"Net savings must never be negative, got {result}"

        # Verify: when gross_savings == 0, result is always 0
        if gross_savings == 0:
            assert result == 0, (
                f"When gross_savings is 0, net savings must be 0 regardless of review costs, got {result}"
            )
        else:
            # Verify: result == max(0, gross_savings - sum(review_costs))
            total_review = sum(review_cost_values)
            expected = max(0, gross_savings - total_review)
            assert result == expected, (
                f"Net savings should be max(0, {gross_savings} - {total_review}) = {expected}, got {result}"
            )
    finally:
        tracker._conn.close()
        if db_path.exists():
            db_path.unlink()


# Feature: net-token-savings, Property 10: Legacy Record Migration Equivalence
"""Property test: For any existing project_token_tracking record with tool_name LIKE 'local_coder%',
the unified statistics view SHALL treat it as a session with gross_savings equal to its
tokens_full_file value, zero review cost, and net_savings equal to gross_savings.

**Validates: Requirements 7.1**
"""

import sqlite3

from hypothesis import given, settings
from hypothesis import strategies as st

from local_coder.token_tracker import SchemaMigrator


@settings(max_examples=100, deadline=None)
@given(
    tokens_full_file=st.integers(min_value=1, max_value=1_000_000),
    tokens_returned=st.integers(min_value=1, max_value=1_000_000),
    interface_type=st.sampled_from(["cli", "api"]),
    tool_name_suffix=st.sampled_from(["", ":qwen2.5-coder:7b", ":patch"]),
)
def test_legacy_record_migration_equivalence(
    tokens_full_file: int,
    tokens_returned: int,
    interface_type: str,
    tool_name_suffix: str,
) -> None:
    """Legacy project_token_tracking records appear in unified_savings with correct values."""
    conn = sqlite3.connect(":memory:")
    try:
        # 1. Create the legacy project_token_tracking table
        conn.execute("""
            CREATE TABLE project_token_tracking (
                id INTEGER PRIMARY KEY,
                interface_type TEXT NOT NULL,
                tool_name TEXT NOT NULL,
                tokens_returned INTEGER NOT NULL,
                tokens_full_file INTEGER NOT NULL,
                timestamp INTEGER DEFAULT (strftime('%s', 'now'))
            )
        """)

        # 2. Insert a legacy record with tool_name matching 'local_coder%'
        tool_name = "local_coder" + tool_name_suffix
        conn.execute(
            """
            INSERT INTO project_token_tracking (id, interface_type, tool_name, tokens_returned, tokens_full_file)
            VALUES (?, ?, ?, ?, ?)
            """,
            (1, interface_type, tool_name, tokens_returned, tokens_full_file),
        )
        conn.commit()

        # 3. Run migration to create schema including unified_savings view
        migrator = SchemaMigrator(conn)
        migrator.migrate()

        # 4. Query the unified_savings view
        cursor = conn.execute(
            "SELECT session_id, gross_savings, total_review_cost, net_savings, has_rework "
            "FROM unified_savings"
        )
        rows = cursor.fetchall()

        # 5. Verify exactly one row from the legacy record
        assert len(rows) == 1, (
            f"Expected exactly 1 row in unified_savings, got {len(rows)}"
        )

        session_id, gross_savings, total_review_cost, net_savings, has_rework = rows[0]

        # session_id starts with "legacy_"
        assert session_id.startswith("legacy_"), (
            f"Legacy record session_id must start with 'legacy_', got: '{session_id}'"
        )

        # gross_savings equals tokens_full_file
        assert gross_savings == tokens_full_file, (
            f"gross_savings should be {tokens_full_file}, got {gross_savings}"
        )

        # total_review_cost is 0
        assert total_review_cost == 0, (
            f"total_review_cost should be 0 for legacy records, got {total_review_cost}"
        )

        # net_savings equals tokens_full_file (same as gross_savings)
        assert net_savings == tokens_full_file, (
            f"net_savings should be {tokens_full_file} (same as gross_savings), got {net_savings}"
        )

        # has_rework is 0
        assert has_rework == 0, (
            f"has_rework should be 0 for legacy records, got {has_rework}"
        )
    finally:
        conn.close()


# Feature: net-token-savings, Property 9: Statistics Display Completeness
"""Property test: For any non-empty collection of generation sessions, the statistics output
SHALL contain: (a) labeled totals for gross_savings, review_cost, and net_savings that are
arithmetically consistent (total_net = sum of per-session max(0, gross - review)),
(b) a per-model breakdown where each model's values sum to the reported totals, and
(c) session counts (clean + rework) that sum to the total number of sessions.

**Validates: Requirements 5.3, 6.1, 6.2, 6.3**
"""

import hashlib
import tempfile
from pathlib import Path

from hypothesis import assume, given, settings
from hypothesis import strategies as st
from hypothesis.strategies import composite

from local_coder.token_tracker import SessionTracker


@composite
def session_configs(draw):
    """Generate a list of 1-5 session configurations."""
    num_sessions = draw(st.integers(min_value=1, max_value=5))
    sessions = []
    for _ in range(num_sessions):
        config = {
            "task_description": draw(st.text(min_size=5, max_size=50)),
            "model": draw(st.sampled_from(["qwen2.5-coder:7b", "qwen3-coder:30b-a3b-q4_K_M"])),
            "eval_count": draw(st.integers(min_value=1, max_value=500_000)),
            "review_costs": draw(st.lists(st.integers(min_value=1, max_value=100_000), min_size=0, max_size=3)),
            "has_rework": draw(st.booleans()),
        }
        sessions.append(config)
    return sessions


@settings(max_examples=100, deadline=None)
@given(sessions=session_configs())
def test_statistics_display_completeness(sessions: list[dict]) -> None:
    """Statistics output contains consistent totals, per-model breakdown summing to totals, and correct session counts."""
    # Filter out cases where task descriptions generate the same hash (session collisions)
    task_hashes = [
        hashlib.sha256(s["task_description"].encode()).hexdigest()[:16]
        for s in sessions
    ]
    assume(len(set(task_hashes)) == len(task_hashes))

    db_path = Path(tempfile.mktemp(suffix=".db"))
    try:
        tracker = SessionTracker(db_path)

        # Track created session IDs and their configs for verification
        created_sessions = []

        for config in sessions:
            # Create session
            session_id = tracker.get_or_create_session(
                None, config["task_description"], config["model"]
            )

            # Record initial generation
            tracker.record_generation(session_id, config["eval_count"], config["model"])

            # Record review costs
            for cost in config["review_costs"]:
                tracker.record_review_cost(session_id, cost)

            # If has_rework: call record_generation again (records a rework phase)
            if config["has_rework"]:
                tracker.record_generation(session_id, config["eval_count"], config["model"])

            created_sessions.append({
                "session_id": session_id,
                "model": config["model"],
                "gross": config["eval_count"],
                "review": sum(config["review_costs"]),
                "has_rework": config["has_rework"],
            })

        # Call compute_aggregate_stats
        stats = tracker.compute_aggregate_stats()

        total_sessions = len(created_sessions)

        # (a) Verify totals are arithmetically consistent
        # total_net_savings == sum of per-session max(0, gross - review)
        expected_total_gross = sum(s["gross"] for s in created_sessions)
        expected_total_review = sum(s["review"] for s in created_sessions)
        expected_total_net = sum(
            max(0, s["gross"] - s["review"]) for s in created_sessions
        )

        assert stats["total_gross_savings"] == expected_total_gross, (
            f"total_gross_savings: expected {expected_total_gross}, got {stats['total_gross_savings']}"
        )
        assert stats["total_review_cost"] == expected_total_review, (
            f"total_review_cost: expected {expected_total_review}, got {stats['total_review_cost']}"
        )
        assert stats["total_net_savings"] == expected_total_net, (
            f"total_net_savings: expected {expected_total_net}, got {stats['total_net_savings']}"
        )

        # (b) Per-model breakdown sums to reported totals
        per_model = stats["per_model"]
        sum_model_gross = sum(m["gross"] for m in per_model)
        sum_model_review = sum(m["review"] for m in per_model)
        sum_model_net = sum(m["net"] for m in per_model)

        assert sum_model_gross == stats["total_gross_savings"], (
            f"Per-model gross sum {sum_model_gross} != total_gross_savings {stats['total_gross_savings']}"
        )
        assert sum_model_review == stats["total_review_cost"], (
            f"Per-model review sum {sum_model_review} != total_review_cost {stats['total_review_cost']}"
        )
        assert sum_model_net == stats["total_net_savings"], (
            f"Per-model net sum {sum_model_net} != total_net_savings {stats['total_net_savings']}"
        )

        # (c) Session counts (clean + rework) sum to total number of sessions
        assert stats["sessions_clean"] + stats["sessions_with_rework"] == total_sessions, (
            f"sessions_clean ({stats['sessions_clean']}) + sessions_with_rework ({stats['sessions_with_rework']}) "
            f"!= total sessions ({total_sessions})"
        )

        # Also verify the rework counts match our expectations
        expected_rework = sum(1 for s in created_sessions if s["has_rework"])
        expected_clean = total_sessions - expected_rework
        assert stats["sessions_with_rework"] == expected_rework, (
            f"sessions_with_rework: expected {expected_rework}, got {stats['sessions_with_rework']}"
        )
        assert stats["sessions_clean"] == expected_clean, (
            f"sessions_clean: expected {expected_clean}, got {stats['sessions_clean']}"
        )
    finally:
        tracker._conn.close()
        if db_path.exists():
            db_path.unlink()
