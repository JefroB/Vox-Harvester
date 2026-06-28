"""Unit tests for token_tracker helper functions."""

import hashlib
import re
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path
import tempfile

from local_coder.token_tracker import (
    generate_session_id,
    find_recent_session,
    SchemaMigrator,
    SessionTracker,
)


class TestGenerateSessionId:
    """Tests for generate_session_id()."""

    def test_format_matches_hash_underscore_timestamp(self):
        result = generate_session_id("build the auth module")
        # Format: 16 hex chars _ ISO timestamp
        pattern = r"^[0-9a-f]{16}_\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$"
        assert re.match(pattern, result), f"Session ID format invalid: {result}"

    def test_hash_prefix_matches_sha256(self):
        task = "implement user login"
        result = generate_session_id(task)
        expected_hash = hashlib.sha256(task.encode()).hexdigest()[:16]
        assert result.startswith(expected_hash)

    def test_different_tasks_produce_different_hashes(self):
        id1 = generate_session_id("task alpha")
        id2 = generate_session_id("task beta")
        # Hash portions should differ
        assert id1.split("_")[0] != id2.split("_")[0]

    def test_same_task_produces_same_hash_prefix(self):
        id1 = generate_session_id("consistent task")
        id2 = generate_session_id("consistent task")
        assert id1.split("_")[0] == id2.split("_")[0]

    def test_timestamp_is_utc_iso_format(self):
        result = generate_session_id("any task")
        timestamp_part = result.split("_", 1)[1]
        # Should parse as valid datetime
        parsed = datetime.strptime(timestamp_part, "%Y-%m-%dT%H:%M:%SZ")
        assert parsed is not None


class TestFindRecentSession:
    """Tests for find_recent_session()."""

    def _setup_db(self):
        """Create an in-memory DB with the schema migrated."""
        conn = sqlite3.connect(":memory:")
        migrator = SchemaMigrator(conn)
        migrator.migrate()
        return conn

    def test_returns_none_when_no_sessions_exist(self):
        conn = self._setup_db()
        result = find_recent_session(conn, "some task")
        assert result is None

    def test_returns_session_id_for_recent_matching_session(self):
        conn = self._setup_db()
        task = "build the parser"
        task_hash = hashlib.sha256(task.encode()).hexdigest()[:16]
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        session_id = f"{task_hash}_{now}"

        conn.execute(
            """
            INSERT INTO generation_sessions (session_id, task_hash, model, gross_savings, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (session_id, task_hash, "qwen2.5-coder:7b", 0, now, now),
        )
        conn.commit()

        result = find_recent_session(conn, task)
        assert result == session_id

    def test_returns_none_for_session_outside_time_window(self):
        conn = self._setup_db()
        task = "old task"
        task_hash = hashlib.sha256(task.encode()).hexdigest()[:16]
        # Create a session 90 minutes ago
        old_time = (datetime.now(timezone.utc) - timedelta(minutes=90)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        session_id = f"{task_hash}_{old_time}"

        conn.execute(
            """
            INSERT INTO generation_sessions (session_id, task_hash, model, gross_savings, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (session_id, task_hash, "qwen2.5-coder:7b", 0, old_time, old_time),
        )
        conn.commit()

        result = find_recent_session(conn, task, within_minutes=60)
        assert result is None

    def test_returns_none_for_different_task_hash(self):
        conn = self._setup_db()
        task_hash = hashlib.sha256("other task".encode()).hexdigest()[:16]
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        session_id = f"{task_hash}_{now}"

        conn.execute(
            """
            INSERT INTO generation_sessions (session_id, task_hash, model, gross_savings, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (session_id, task_hash, "qwen2.5-coder:7b", 0, now, now),
        )
        conn.commit()

        # Search with a different task description
        result = find_recent_session(conn, "my different task")
        assert result is None

    def test_returns_most_recent_session_when_multiple_exist(self):
        conn = self._setup_db()
        task = "repeated task"
        task_hash = hashlib.sha256(task.encode()).hexdigest()[:16]

        # Older session (30 min ago)
        older_time = (datetime.now(timezone.utc) - timedelta(minutes=30)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        older_id = f"{task_hash}_{older_time}"
        conn.execute(
            """
            INSERT INTO generation_sessions (session_id, task_hash, model, gross_savings, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (older_id, task_hash, "qwen2.5-coder:7b", 0, older_time, older_time),
        )

        # Newer session (5 min ago)
        newer_time = (datetime.now(timezone.utc) - timedelta(minutes=5)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        newer_id = f"{task_hash}_{newer_time}"
        conn.execute(
            """
            INSERT INTO generation_sessions (session_id, task_hash, model, gross_savings, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (newer_id, task_hash, "qwen2.5-coder:7b", 0, newer_time, newer_time),
        )
        conn.commit()

        result = find_recent_session(conn, task)
        assert result == newer_id

    def test_custom_time_window(self):
        conn = self._setup_db()
        task = "window test"
        task_hash = hashlib.sha256(task.encode()).hexdigest()[:16]

        # Session 10 minutes ago
        recent_time = (datetime.now(timezone.utc) - timedelta(minutes=10)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        session_id = f"{task_hash}_{recent_time}"
        conn.execute(
            """
            INSERT INTO generation_sessions (session_id, task_hash, model, gross_savings, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (session_id, task_hash, "qwen2.5-coder:7b", 0, recent_time, recent_time),
        )
        conn.commit()

        # Within 15 minutes → found
        assert find_recent_session(conn, task, within_minutes=15) == session_id
        # Within 5 minutes → not found
        assert find_recent_session(conn, task, within_minutes=5) is None


class TestSessionTrackerInit:
    """Tests for SessionTracker.__init__."""

    def test_creates_schema_on_new_database(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = Path(f.name)
        tracker = SessionTracker(db_path)
        # Verify tables were created
        cursor = tracker._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = [row[0] for row in cursor.fetchall()]
        assert "generation_sessions" in tables
        assert "session_generations" in tables
        assert "review_costs" in tables

    def test_does_not_fail_on_already_migrated_db(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = Path(f.name)
        # First init migrates
        SessionTracker(db_path)
        # Second init should be a no-op (idempotent)
        tracker2 = SessionTracker(db_path)
        cursor = tracker2._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='generation_sessions'"
        )
        assert cursor.fetchone() is not None


class TestGetOrCreateSession:
    """Tests for SessionTracker.get_or_create_session()."""

    def _make_tracker(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = Path(f.name)
        return SessionTracker(db_path)

    def test_explicit_session_id_creates_new_session(self):
        tracker = self._make_tracker()
        result = tracker.get_or_create_session("my-session-1", "build auth", "qwen2.5-coder:7b")
        assert result == "my-session-1"
        # Verify it exists in DB
        cursor = tracker._conn.execute(
            "SELECT session_id, model FROM generation_sessions WHERE session_id = ?",
            ("my-session-1",),
        )
        row = cursor.fetchone()
        assert row is not None
        assert row[0] == "my-session-1"
        assert row[1] == "qwen2.5-coder:7b"

    def test_explicit_session_id_returns_existing(self):
        tracker = self._make_tracker()
        # Create first
        tracker.get_or_create_session("existing-session", "task A", "model-a")
        # Call again with same session_id
        result = tracker.get_or_create_session("existing-session", "task B", "model-b")
        assert result == "existing-session"
        # Should still have original data (only one record)
        cursor = tracker._conn.execute(
            "SELECT COUNT(*) FROM generation_sessions WHERE session_id = ?",
            ("existing-session",),
        )
        assert cursor.fetchone()[0] == 1

    def test_none_session_id_generates_new_session(self):
        tracker = self._make_tracker()
        result = tracker.get_or_create_session(None, "implement parser", "qwen2.5-coder:7b")
        # Should match the format: 16 hex chars _ ISO timestamp
        pattern = r"^[0-9a-f]{16}_\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$"
        assert re.match(pattern, result)
        # Hash portion matches task description
        expected_hash = hashlib.sha256("implement parser".encode()).hexdigest()[:16]
        assert result.startswith(expected_hash)

    def test_none_session_id_associates_with_recent_session(self):
        tracker = self._make_tracker()
        task = "build the API"
        # Create a session for this task
        first_id = tracker.get_or_create_session(None, task, "qwen2.5-coder:7b")
        # Call again within 60 minutes (immediately) — should return same session
        second_id = tracker.get_or_create_session(None, task, "qwen2.5-coder:7b")
        assert first_id == second_id

    def test_none_session_id_different_task_creates_new(self):
        tracker = self._make_tracker()
        id1 = tracker.get_or_create_session(None, "task alpha", "qwen2.5-coder:7b")
        id2 = tracker.get_or_create_session(None, "task beta", "qwen2.5-coder:7b")
        assert id1 != id2

    def test_created_session_has_correct_fields(self):
        tracker = self._make_tracker()
        task = "validate emails"
        tracker.get_or_create_session("test-fields", task, "qwen3-coder:30b")
        cursor = tracker._conn.execute(
            "SELECT session_id, task_hash, model, gross_savings, created_at, updated_at FROM generation_sessions WHERE session_id = ?",
            ("test-fields",),
        )
        row = cursor.fetchone()
        assert row[0] == "test-fields"
        assert row[1] == hashlib.sha256(task.encode()).hexdigest()[:16]
        assert row[2] == "qwen3-coder:30b"
        assert row[3] == 0  # gross_savings starts at 0
        # Timestamps are valid ISO format
        datetime.strptime(row[4], "%Y-%m-%dT%H:%M:%SZ")
        datetime.strptime(row[5], "%Y-%m-%dT%H:%M:%SZ")


class TestRecordGeneration:
    """Tests for SessionTracker.record_generation()."""

    def _make_tracker(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = Path(f.name)
        return SessionTracker(db_path)

    def test_first_generation_is_initial_phase(self):
        tracker = self._make_tracker()
        tracker.get_or_create_session("sess-1", "build auth", "qwen2.5-coder:7b")
        tracker.record_generation("sess-1", 500, "qwen2.5-coder:7b")

        cursor = tracker._conn.execute(
            "SELECT phase, token_count FROM session_generations WHERE session_id = ?",
            ("sess-1",),
        )
        row = cursor.fetchone()
        assert row[0] == "initial"
        assert row[1] == 500

    def test_initial_generation_sets_gross_savings(self):
        tracker = self._make_tracker()
        tracker.get_or_create_session("sess-2", "build parser", "qwen2.5-coder:7b")
        tracker.record_generation("sess-2", 1200, "qwen2.5-coder:7b")

        cursor = tracker._conn.execute(
            "SELECT gross_savings FROM generation_sessions WHERE session_id = ?",
            ("sess-2",),
        )
        assert cursor.fetchone()[0] == 1200

    def test_second_generation_is_rework_phase(self):
        tracker = self._make_tracker()
        tracker.get_or_create_session("sess-3", "task X", "qwen2.5-coder:7b")
        tracker.record_generation("sess-3", 800, "qwen2.5-coder:7b")
        tracker.record_generation("sess-3", 300, "qwen2.5-coder:7b")

        cursor = tracker._conn.execute(
            "SELECT phase, token_count FROM session_generations WHERE session_id = ? ORDER BY id",
            ("sess-3",),
        )
        rows = cursor.fetchall()
        assert rows[0][0] == "initial"
        assert rows[1][0] == "rework"
        assert rows[1][1] == 300

    def test_rework_does_not_update_gross_savings(self):
        tracker = self._make_tracker()
        tracker.get_or_create_session("sess-4", "task Y", "qwen2.5-coder:7b")
        tracker.record_generation("sess-4", 1000, "qwen2.5-coder:7b")
        tracker.record_generation("sess-4", 500, "qwen2.5-coder:7b")

        cursor = tracker._conn.execute(
            "SELECT gross_savings FROM generation_sessions WHERE session_id = ?",
            ("sess-4",),
        )
        assert cursor.fetchone()[0] == 1000  # Unchanged

    def test_initial_with_zero_eval_count_skips_gross_savings(self, capsys):
        tracker = self._make_tracker()
        tracker.get_or_create_session("sess-5", "task Z", "qwen2.5-coder:7b")
        tracker.record_generation("sess-5", 0, "qwen2.5-coder:7b")

        cursor = tracker._conn.execute(
            "SELECT gross_savings FROM generation_sessions WHERE session_id = ?",
            ("sess-5",),
        )
        assert cursor.fetchone()[0] == 0
        captured = capsys.readouterr()
        assert "[WARN]" in captured.err
        assert "eval_count is missing or zero" in captured.err

    def test_initial_with_none_eval_count_skips_gross_savings(self, capsys):
        tracker = self._make_tracker()
        tracker.get_or_create_session("sess-6", "task W", "qwen2.5-coder:7b")
        tracker.record_generation("sess-6", None, "qwen2.5-coder:7b")

        cursor = tracker._conn.execute(
            "SELECT gross_savings FROM generation_sessions WHERE session_id = ?",
            ("sess-6",),
        )
        assert cursor.fetchone()[0] == 0
        captured = capsys.readouterr()
        assert "[WARN]" in captured.err

    def test_does_not_overwrite_existing_gross_savings(self):
        tracker = self._make_tracker()
        tracker.get_or_create_session("sess-7", "task V", "qwen2.5-coder:7b")
        # Manually set gross_savings to simulate already-recorded initial
        tracker._conn.execute(
            "UPDATE generation_sessions SET gross_savings = 999 WHERE session_id = ?",
            ("sess-7",),
        )
        tracker._conn.commit()
        # Now record initial generation — should NOT overwrite
        tracker.record_generation("sess-7", 2000, "qwen2.5-coder:7b")

        cursor = tracker._conn.execute(
            "SELECT gross_savings FROM generation_sessions WHERE session_id = ?",
            ("sess-7",),
        )
        assert cursor.fetchone()[0] == 999

    def test_orphaned_rework_creates_session(self, capsys):
        tracker = self._make_tracker()
        # Don't create session first — call record_generation directly
        tracker.record_generation("orphan-sess", 400, "qwen2.5-coder:7b")

        # Session should now exist
        cursor = tracker._conn.execute(
            "SELECT session_id, task_hash FROM generation_sessions WHERE session_id = ?",
            ("orphan-sess",),
        )
        row = cursor.fetchone()
        assert row is not None
        # task_hash should be SHA-256 of session_id itself
        import hashlib as hl
        expected_hash = hl.sha256("orphan-sess".encode()).hexdigest()[:16]
        assert row[1] == expected_hash

        # Phase should be "rework"
        cursor = tracker._conn.execute(
            "SELECT phase FROM session_generations WHERE session_id = ?",
            ("orphan-sess",),
        )
        assert cursor.fetchone()[0] == "rework"

        # Warning logged
        captured = capsys.readouterr()
        assert "[WARN] Orphaned rework" in captured.err

    def test_orphaned_rework_does_not_set_gross_savings(self, capsys):
        tracker = self._make_tracker()
        tracker.record_generation("orphan-2", 800, "qwen2.5-coder:7b")

        cursor = tracker._conn.execute(
            "SELECT gross_savings FROM generation_sessions WHERE session_id = ?",
            ("orphan-2",),
        )
        assert cursor.fetchone()[0] == 0
        # consume stderr
        capsys.readouterr()

    def test_generation_record_has_correct_model(self):
        tracker = self._make_tracker()
        tracker.get_or_create_session("sess-model", "task M", "qwen3-coder:30b")
        tracker.record_generation("sess-model", 600, "qwen3-coder:30b")

        cursor = tracker._conn.execute(
            "SELECT model FROM session_generations WHERE session_id = ?",
            ("sess-model",),
        )
        assert cursor.fetchone()[0] == "qwen3-coder:30b"

    def test_generation_record_has_timestamp(self):
        tracker = self._make_tracker()
        tracker.get_or_create_session("sess-ts", "task T", "qwen2.5-coder:7b")
        tracker.record_generation("sess-ts", 100, "qwen2.5-coder:7b")

        cursor = tracker._conn.execute(
            "SELECT created_at FROM session_generations WHERE session_id = ?",
            ("sess-ts",),
        )
        ts = cursor.fetchone()[0]
        # Should parse as valid datetime
        parsed = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ")
        assert parsed is not None


class TestRecordReviewCost:
    """Tests for SessionTracker.record_review_cost()."""

    def _make_tracker(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = Path(f.name)
        return SessionTracker(db_path)

    def test_valid_review_cost_inserts_into_review_costs_table(self):
        tracker = self._make_tracker()
        tracker.get_or_create_session("rc-sess-1", "task A", "qwen2.5-coder:7b")
        tracker.record_review_cost("rc-sess-1", 500)

        cursor = tracker._conn.execute(
            "SELECT session_id, tokens FROM review_costs WHERE session_id = ?",
            ("rc-sess-1",),
        )
        row = cursor.fetchone()
        assert row is not None
        assert row[0] == "rc-sess-1"
        assert row[1] == 500

    def test_review_cost_has_created_at_timestamp(self):
        tracker = self._make_tracker()
        tracker.get_or_create_session("rc-sess-ts", "task B", "qwen2.5-coder:7b")
        tracker.record_review_cost("rc-sess-ts", 100)

        cursor = tracker._conn.execute(
            "SELECT created_at FROM review_costs WHERE session_id = ?",
            ("rc-sess-ts",),
        )
        ts = cursor.fetchone()[0]
        parsed = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ")
        assert parsed is not None

    def test_multiple_reviews_accumulate(self):
        tracker = self._make_tracker()
        tracker.get_or_create_session("rc-sess-multi", "task C", "qwen2.5-coder:7b")
        tracker.record_review_cost("rc-sess-multi", 200)
        tracker.record_review_cost("rc-sess-multi", 300)
        tracker.record_review_cost("rc-sess-multi", 150)

        cursor = tracker._conn.execute(
            "SELECT SUM(tokens) FROM review_costs WHERE session_id = ?",
            ("rc-sess-multi",),
        )
        assert cursor.fetchone()[0] == 650

    def test_zero_tokens_raises_invalid_review_cost_error(self):
        from local_coder.token_tracker import InvalidReviewCostError

        tracker = self._make_tracker()
        tracker.get_or_create_session("rc-sess-zero", "task D", "qwen2.5-coder:7b")
        try:
            tracker.record_review_cost("rc-sess-zero", 0)
            assert False, "Should have raised InvalidReviewCostError"
        except InvalidReviewCostError as e:
            assert "between 1 and 10,000,000" in str(e)
            assert "got: 0" in str(e)

    def test_negative_tokens_raises_invalid_review_cost_error(self):
        from local_coder.token_tracker import InvalidReviewCostError

        tracker = self._make_tracker()
        tracker.get_or_create_session("rc-sess-neg", "task E", "qwen2.5-coder:7b")
        try:
            tracker.record_review_cost("rc-sess-neg", -5)
            assert False, "Should have raised InvalidReviewCostError"
        except InvalidReviewCostError as e:
            assert "between 1 and 10,000,000" in str(e)
            assert "got: -5" in str(e)

    def test_tokens_exceeding_max_raises_invalid_review_cost_error(self):
        from local_coder.token_tracker import InvalidReviewCostError

        tracker = self._make_tracker()
        tracker.get_or_create_session("rc-sess-max", "task F", "qwen2.5-coder:7b")
        try:
            tracker.record_review_cost("rc-sess-max", 10_000_001)
            assert False, "Should have raised InvalidReviewCostError"
        except InvalidReviewCostError as e:
            assert "between 1 and 10,000,000" in str(e)
            assert "got: 10000001" in str(e)

    def test_nonexistent_session_raises_session_not_found_error(self):
        from local_coder.token_tracker import SessionNotFoundError

        tracker = self._make_tracker()
        try:
            tracker.record_review_cost("no-such-session", 100)
            assert False, "Should have raised SessionNotFoundError"
        except SessionNotFoundError as e:
            assert "Session not found: no-such-session" in str(e)

    def test_boundary_value_1_is_accepted(self):
        tracker = self._make_tracker()
        tracker.get_or_create_session("rc-sess-min", "task G", "qwen2.5-coder:7b")
        tracker.record_review_cost("rc-sess-min", 1)

        cursor = tracker._conn.execute(
            "SELECT tokens FROM review_costs WHERE session_id = ?",
            ("rc-sess-min",),
        )
        assert cursor.fetchone()[0] == 1

    def test_boundary_value_10_million_is_accepted(self):
        tracker = self._make_tracker()
        tracker.get_or_create_session("rc-sess-maxval", "task H", "qwen2.5-coder:7b")
        tracker.record_review_cost("rc-sess-maxval", 10_000_000)

        cursor = tracker._conn.execute(
            "SELECT tokens FROM review_costs WHERE session_id = ?",
            ("rc-sess-maxval",),
        )
        assert cursor.fetchone()[0] == 10_000_000

    def test_validation_happens_before_session_check(self):
        """Token validation should run before session existence check."""
        from local_coder.token_tracker import InvalidReviewCostError

        tracker = self._make_tracker()
        # Don't create any session — but pass invalid tokens
        # Should get InvalidReviewCostError, not SessionNotFoundError
        try:
            tracker.record_review_cost("nonexistent", 0)
            assert False, "Should have raised InvalidReviewCostError"
        except InvalidReviewCostError:
            pass  # Correct: validation first


class TestComputeNetSavings:
    """Tests for SessionTracker.compute_net_savings()."""

    def _make_tracker(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = Path(f.name)
        return SessionTracker(db_path)

    def test_returns_zero_for_nonexistent_session(self):
        tracker = self._make_tracker()
        assert tracker.compute_net_savings("no-such-session") == 0

    def test_returns_gross_savings_when_no_review_costs(self):
        tracker = self._make_tracker()
        tracker.get_or_create_session("net-1", "task A", "qwen2.5-coder:7b")
        tracker.record_generation("net-1", 1000, "qwen2.5-coder:7b")
        assert tracker.compute_net_savings("net-1") == 1000

    def test_deducts_review_costs_from_gross(self):
        tracker = self._make_tracker()
        tracker.get_or_create_session("net-2", "task B", "qwen2.5-coder:7b")
        tracker.record_generation("net-2", 1000, "qwen2.5-coder:7b")
        tracker.record_review_cost("net-2", 300)
        assert tracker.compute_net_savings("net-2") == 700

    def test_accumulates_multiple_review_costs(self):
        tracker = self._make_tracker()
        tracker.get_or_create_session("net-3", "task C", "qwen2.5-coder:7b")
        tracker.record_generation("net-3", 1000, "qwen2.5-coder:7b")
        tracker.record_review_cost("net-3", 200)
        tracker.record_review_cost("net-3", 300)
        assert tracker.compute_net_savings("net-3") == 500

    def test_floors_at_zero_when_review_exceeds_gross(self):
        tracker = self._make_tracker()
        tracker.get_or_create_session("net-4", "task D", "qwen2.5-coder:7b")
        tracker.record_generation("net-4", 500, "qwen2.5-coder:7b")
        tracker.record_review_cost("net-4", 800)
        assert tracker.compute_net_savings("net-4") == 0

    def test_returns_zero_when_gross_savings_is_zero(self):
        tracker = self._make_tracker()
        tracker.get_or_create_session("net-5", "task E", "qwen2.5-coder:7b")
        # No generation recorded, gross_savings stays at 0
        assert tracker.compute_net_savings("net-5") == 0

    def test_returns_zero_when_gross_is_zero_even_with_review_costs(self):
        """Req 5.4: If gross_savings is 0, net_savings is 0 regardless of review costs."""
        tracker = self._make_tracker()
        tracker.get_or_create_session("net-6", "task F", "qwen2.5-coder:7b")
        # Manually insert a review cost without having any gross_savings
        # This requires direct DB manipulation since record_review_cost
        # needs an existing session (which we have) but gross is 0
        tracker._conn.execute(
            "INSERT INTO review_costs (session_id, tokens, created_at) VALUES (?, ?, ?)",
            ("net-6", 500, "2025-01-01T00:00:00Z"),
        )
        tracker._conn.commit()
        assert tracker.compute_net_savings("net-6") == 0


class TestGetSession:
    """Tests for SessionTracker.get_session()."""

    def _make_tracker(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = Path(f.name)
        return SessionTracker(db_path)

    def test_returns_none_for_nonexistent_session(self):
        tracker = self._make_tracker()
        assert tracker.get_session("no-such-session") is None

    def test_returns_dict_with_all_expected_keys(self):
        tracker = self._make_tracker()
        tracker.get_or_create_session("gs-1", "task A", "qwen2.5-coder:7b")
        result = tracker.get_session("gs-1")
        assert result is not None
        expected_keys = {
            "session_id", "task_hash", "model", "gross_savings",
            "total_review_cost", "net_savings", "phases",
            "created_at", "updated_at",
        }
        assert set(result.keys()) == expected_keys

    def test_returns_correct_session_data(self):
        tracker = self._make_tracker()
        tracker.get_or_create_session("gs-2", "task B", "qwen3-coder:30b")
        tracker.record_generation("gs-2", 1500, "qwen3-coder:30b")
        tracker.record_review_cost("gs-2", 400)

        result = tracker.get_session("gs-2")
        assert result["session_id"] == "gs-2"
        assert result["model"] == "qwen3-coder:30b"
        assert result["gross_savings"] == 1500
        assert result["total_review_cost"] == 400
        assert result["net_savings"] == 1100

    def test_phases_list_contains_generation_records(self):
        tracker = self._make_tracker()
        tracker.get_or_create_session("gs-3", "task C", "qwen2.5-coder:7b")
        tracker.record_generation("gs-3", 1000, "qwen2.5-coder:7b")
        tracker.record_generation("gs-3", 300, "qwen2.5-coder:7b")

        result = tracker.get_session("gs-3")
        phases = result["phases"]
        assert len(phases) == 2
        assert phases[0]["phase"] == "initial"
        assert phases[0]["token_count"] == 1000
        assert phases[1]["phase"] == "rework"
        assert phases[1]["token_count"] == 300

    def test_phases_list_empty_when_no_generations(self):
        tracker = self._make_tracker()
        tracker.get_or_create_session("gs-4", "task D", "qwen2.5-coder:7b")
        result = tracker.get_session("gs-4")
        assert result["phases"] == []

    def test_total_review_cost_sums_all_entries(self):
        tracker = self._make_tracker()
        tracker.get_or_create_session("gs-5", "task E", "qwen2.5-coder:7b")
        tracker.record_generation("gs-5", 2000, "qwen2.5-coder:7b")
        tracker.record_review_cost("gs-5", 100)
        tracker.record_review_cost("gs-5", 200)
        tracker.record_review_cost("gs-5", 300)

        result = tracker.get_session("gs-5")
        assert result["total_review_cost"] == 600
        assert result["net_savings"] == 1400

    def test_net_savings_floors_at_zero(self):
        tracker = self._make_tracker()
        tracker.get_or_create_session("gs-6", "task F", "qwen2.5-coder:7b")
        tracker.record_generation("gs-6", 100, "qwen2.5-coder:7b")
        tracker.record_review_cost("gs-6", 500)

        result = tracker.get_session("gs-6")
        assert result["net_savings"] == 0
        assert result["gross_savings"] == 100
        assert result["total_review_cost"] == 500

    def test_task_hash_is_correct(self):
        tracker = self._make_tracker()
        task = "validate user input"
        tracker.get_or_create_session("gs-7", task, "qwen2.5-coder:7b")
        result = tracker.get_session("gs-7")
        expected_hash = hashlib.sha256(task.encode()).hexdigest()[:16]
        assert result["task_hash"] == expected_hash


class TestDisplayStats:
    """Tests for display_stats()."""

    def _make_tracker(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = Path(f.name)
        return SessionTracker(db_path)

    def test_no_sessions_displays_no_data_message(self, capsys):
        from local_coder.token_tracker import display_stats

        tracker = self._make_tracker()
        display_stats(tracker)
        captured = capsys.readouterr()
        assert "No session data recorded." in captured.out

    def test_no_sessions_does_not_display_breakdown(self, capsys):
        from local_coder.token_tracker import display_stats

        tracker = self._make_tracker()
        display_stats(tracker)
        captured = capsys.readouterr()
        assert "Per-Model Breakdown" not in captured.out
        assert "Session Summary" not in captured.out

    def test_displays_totals_with_comma_formatting(self, capsys):
        from local_coder.token_tracker import display_stats

        tracker = self._make_tracker()
        tracker.get_or_create_session("ds-1", "task A", "qwen2.5-coder:7b")
        tracker.record_generation("ds-1", 12500, "qwen2.5-coder:7b")
        tracker.record_review_cost("ds-1", 2300)

        display_stats(tracker)
        captured = capsys.readouterr()
        assert "12,500" in captured.out
        assert "-2,300" in captured.out
        assert "10,200" in captured.out

    def test_displays_header_and_separator(self, capsys):
        from local_coder.token_tracker import display_stats

        tracker = self._make_tracker()
        tracker.get_or_create_session("ds-2", "task B", "qwen2.5-coder:7b")
        tracker.record_generation("ds-2", 1000, "qwen2.5-coder:7b")

        display_stats(tracker)
        captured = capsys.readouterr()
        assert "Net Token Savings" in captured.out
        assert "=" * 50 in captured.out

    def test_displays_per_model_breakdown(self, capsys):
        from local_coder.token_tracker import display_stats

        tracker = self._make_tracker()
        tracker.get_or_create_session("ds-3", "task C", "qwen2.5-coder:7b")
        tracker.record_generation("ds-3", 8000, "qwen2.5-coder:7b")
        tracker.record_review_cost("ds-3", 1200)

        tracker.get_or_create_session("ds-4", "task D", "qwen3-coder:30b")
        tracker.record_generation("ds-4", 4500, "qwen3-coder:30b")
        tracker.record_review_cost("ds-4", 1100)

        display_stats(tracker)
        captured = capsys.readouterr()
        assert "Per-Model Breakdown:" in captured.out
        assert "qwen2.5-coder:7b" in captured.out
        assert "qwen3-coder:30b" in captured.out

    def test_displays_session_summary(self, capsys):
        from local_coder.token_tracker import display_stats

        tracker = self._make_tracker()
        # Clean session (no rework)
        tracker.get_or_create_session("ds-5", "task E", "qwen2.5-coder:7b")
        tracker.record_generation("ds-5", 1000, "qwen2.5-coder:7b")

        # Session with rework
        tracker.get_or_create_session("ds-6", "task F", "qwen2.5-coder:7b")
        tracker.record_generation("ds-6", 800, "qwen2.5-coder:7b")
        tracker.record_generation("ds-6", 200, "qwen2.5-coder:7b")  # rework

        display_stats(tracker)
        captured = capsys.readouterr()
        assert "Session Summary:" in captured.out
        assert "Clean (no rework):" in captured.out
        assert "Required rework:" in captured.out

    def test_displays_labeled_totals(self, capsys):
        from local_coder.token_tracker import display_stats

        tracker = self._make_tracker()
        tracker.get_or_create_session("ds-7", "task G", "qwen2.5-coder:7b")
        tracker.record_generation("ds-7", 5000, "qwen2.5-coder:7b")
        tracker.record_review_cost("ds-7", 1000)

        display_stats(tracker)
        captured = capsys.readouterr()
        assert "Total gross savings:" in captured.out
        assert "Total review cost:" in captured.out
        assert "Total net savings:" in captured.out


class TestEdgeCases:
    """Edge case unit tests for net-token-savings feature."""

    def _make_tracker(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = Path(f.name)
        return SessionTracker(db_path)

    def test_empty_stats_shows_no_data_message(self, capsys):
        """Req 6.4: If no sessions exist, display 'No session data recorded'."""
        from local_coder.token_tracker import display_stats

        tracker = self._make_tracker()
        display_stats(tracker)
        captured = capsys.readouterr()
        assert "No session data recorded" in captured.out

    def test_orphaned_rework_creates_session_with_warning(self, capsys):
        """Req 4.3: Orphaned rework creates session, marks as rework, logs warning."""
        tracker = self._make_tracker()
        # Call record_generation for a session that doesn't exist
        tracker.record_generation("nonexistent_session", 1000, "qwen2.5-coder:7b")

        # Verify session was created in generation_sessions
        cursor = tracker._conn.execute(
            "SELECT session_id FROM generation_sessions WHERE session_id = ?",
            ("nonexistent_session",),
        )
        assert cursor.fetchone() is not None

        # Verify the generation is marked as "rework"
        cursor = tracker._conn.execute(
            "SELECT phase FROM session_generations WHERE session_id = ?",
            ("nonexistent_session",),
        )
        row = cursor.fetchone()
        assert row is not None
        assert row[0] == "rework"

        # Verify warning message was logged to stderr
        captured = capsys.readouterr()
        assert "Orphaned rework" in captured.err
        assert "nonexistent_session" in captured.err

    def test_zero_eval_count_logs_warning(self, capsys):
        """Req 2.3: Zero eval_count logs warning, gross_savings remains 0."""
        tracker = self._make_tracker()
        session_id = tracker.get_or_create_session(
            "zero-eval-sess", "test task", "qwen2.5-coder:7b"
        )
        tracker.record_generation(session_id, 0, "qwen2.5-coder:7b")

        # gross_savings should remain 0
        cursor = tracker._conn.execute(
            "SELECT gross_savings FROM generation_sessions WHERE session_id = ?",
            (session_id,),
        )
        assert cursor.fetchone()[0] == 0

        # Warning should be logged to stderr
        captured = capsys.readouterr()
        assert "eval_count is missing or zero" in captured.err

    def test_negative_review_cost_rejected(self):
        """Req 3.5: Zero or negative review cost raises InvalidReviewCostError."""
        from local_coder.token_tracker import InvalidReviewCostError

        tracker = self._make_tracker()
        tracker.get_or_create_session("neg-cost-sess", "test task", "qwen2.5-coder:7b")

        # Negative value should raise
        import pytest

        with pytest.raises(InvalidReviewCostError):
            tracker.record_review_cost("neg-cost-sess", -1)

        # Zero should also raise
        with pytest.raises(InvalidReviewCostError):
            tracker.record_review_cost("neg-cost-sess", 0)

    def test_migration_rollback_on_failure(self):
        """Req 7.5: Migration rolls back on failure, no partial tables created."""
        from local_coder.token_tracker import SchemaMigrator, MigrationError
        from unittest.mock import patch
        import pytest

        conn = sqlite3.connect(":memory:")

        migrator = SchemaMigrator(conn)

        # Patch the internal method to raise an error mid-migration
        original_create_view = migrator._create_unified_savings_view

        def failing_view():
            raise RuntimeError("Simulated failure during view creation")

        migrator._create_unified_savings_view = failing_view

        with pytest.raises(MigrationError):
            migrator.migrate()

        # Verify no partial tables were created (rollback worked)
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='generation_sessions'"
        )
        assert cursor.fetchone() is None

        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='session_generations'"
        )
        assert cursor.fetchone() is None

        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='review_costs'"
        )
        assert cursor.fetchone() is None

    def test_auto_migration_on_first_use(self):
        """Req 7.3: SessionTracker constructor auto-migrates on first use."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = Path(f.name)

        # Verify the fresh DB has no schema
        conn = sqlite3.connect(str(db_path))
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='generation_sessions'"
        )
        assert cursor.fetchone() is None
        conn.close()

        # Creating a SessionTracker should auto-migrate
        tracker = SessionTracker(db_path)

        # Verify generation_sessions table now exists
        cursor = tracker._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='generation_sessions'"
        )
        assert cursor.fetchone() is not None


# ============================================================================
# Integration Tests
# ============================================================================


class TestMigrationPreservesExistingSchema:
    """Integration test: Req 7.2 - migration is non-destructive to legacy table."""

    def test_migration_preserves_existing_schema(self):
        """Create a DB with legacy project_token_tracking table, trigger migration,
        verify legacy table and data remain untouched alongside new tables."""
        import os

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = Path(f.name)

        try:
            # Step 1: Create legacy DB with project_token_tracking table (full schema)
            conn = sqlite3.connect(str(db_path))
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

            # Insert legacy data
            conn.execute(
                """
                INSERT INTO project_token_tracking (interface_type, tool_name, tokens_returned, tokens_full_file)
                VALUES (?, ?, ?, ?)
                """,
                ("cli", "local_coder_patch", 500, 1200),
            )
            conn.execute(
                """
                INSERT INTO project_token_tracking (interface_type, tool_name, tokens_returned, tokens_full_file)
                VALUES (?, ?, ?, ?)
                """,
                ("cli", "local_coder_full", 300, 800),
            )
            conn.commit()
            conn.close()

            # Step 2: Create SessionTracker — this triggers migration
            tracker = SessionTracker(db_path)

            # Step 3: Verify legacy table still exists with all original columns
            cursor = tracker._conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='project_token_tracking'"
            )
            assert cursor.fetchone() is not None, "Legacy table should still exist"

            # Check columns of legacy table are unchanged
            cursor = tracker._conn.execute("PRAGMA table_info(project_token_tracking)")
            columns = {row[1] for row in cursor.fetchall()}
            expected_columns = {
                "id",
                "interface_type",
                "tool_name",
                "tokens_returned",
                "tokens_full_file",
                "timestamp",
            }
            assert columns == expected_columns, f"Legacy columns changed: {columns}"

            # Step 4: Verify legacy data is unchanged
            cursor = tracker._conn.execute(
                "SELECT interface_type, tool_name, tokens_returned, tokens_full_file "
                "FROM project_token_tracking ORDER BY id"
            )
            rows = cursor.fetchall()
            assert len(rows) == 2
            assert rows[0] == ("cli", "local_coder_patch", 500, 1200)
            assert rows[1] == ("cli", "local_coder_full", 300, 800)

            # Step 5: Verify new tables were created alongside
            cursor = tracker._conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
            all_tables = {row[0] for row in cursor.fetchall()}
            assert "generation_sessions" in all_tables
            assert "session_generations" in all_tables
            assert "review_costs" in all_tables
            assert "project_token_tracking" in all_tables
        finally:
            tracker._conn.close()
            os.unlink(db_path)


class TestFullWorkflowGenerationReviewStats:
    """Integration test: End-to-end workflow of generation, review, and stats."""

    def test_full_workflow_generation_review_stats(self):
        """Create session, record initial generation, review cost, rework,
        then verify net savings and aggregate stats are all correct."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = Path(f.name)

        import os

        try:
            # Step 1: Create a SessionTracker
            tracker = SessionTracker(db_path)

            # Step 2: Create a session
            session_id = tracker.get_or_create_session(
                "e2e-session", "implement user auth", "qwen2.5-coder:7b"
            )
            assert session_id == "e2e-session"

            # Step 3: Record initial generation (eval_count=10000)
            tracker.record_generation("e2e-session", 10000, "qwen2.5-coder:7b")

            # Step 4: Record review cost (tokens=2000)
            tracker.record_review_cost("e2e-session", 2000)

            # Step 5: Record a rework generation (eval_count=8000)
            tracker.record_generation("e2e-session", 8000, "qwen2.5-coder:7b")

            # Step 6: Compute net savings → should be max(0, 10000 - 2000) = 8000
            net = tracker.compute_net_savings("e2e-session")
            assert net == 8000, f"Expected net_savings=8000, got {net}"

            # Step 7: get_session() → verify all data is correct
            session_data = tracker.get_session("e2e-session")
            assert session_data is not None
            assert session_data["session_id"] == "e2e-session"
            assert session_data["gross_savings"] == 10000
            assert session_data["total_review_cost"] == 2000
            assert session_data["net_savings"] == 8000
            assert session_data["model"] == "qwen2.5-coder:7b"
            assert len(session_data["phases"]) == 2
            assert session_data["phases"][0]["phase"] == "initial"
            assert session_data["phases"][0]["token_count"] == 10000
            assert session_data["phases"][1]["phase"] == "rework"
            assert session_data["phases"][1]["token_count"] == 8000

            # Step 8: compute_aggregate_stats() → verify totals
            stats = tracker.compute_aggregate_stats()
            assert stats["total_gross_savings"] == 10000
            assert stats["total_review_cost"] == 2000
            assert stats["total_net_savings"] == 8000
            assert stats["sessions_with_rework"] == 1
            assert stats["sessions_clean"] == 0
            assert len(stats["per_model"]) == 1
            assert stats["per_model"][0]["model"] == "qwen2.5-coder:7b"
            assert stats["per_model"][0]["gross"] == 10000
            assert stats["per_model"][0]["review"] == 2000
            assert stats["per_model"][0]["net"] == 8000
            assert stats["per_model"][0]["calls"] == 1
        finally:
            tracker._conn.close()
            os.unlink(db_path)


class TestStatsWithLegacyAndNewRecords:
    """Integration test: Req 7.1 + 6.1 - unified_savings view combines legacy + new."""

    def test_stats_with_legacy_and_new_records(self):
        """Create DB with legacy data, trigger migration, add new session data,
        query unified_savings view, verify both legacy and new records appear."""
        import os

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = Path(f.name)

        try:
            # Step 1: Create legacy DB with project_token_tracking table and data
            conn = sqlite3.connect(str(db_path))
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
            conn.execute(
                """
                INSERT INTO project_token_tracking (interface_type, tool_name, tokens_returned, tokens_full_file)
                VALUES (?, ?, ?, ?)
                """,
                ("cli", "local_coder_patch", 400, 5000),
            )
            conn.execute(
                """
                INSERT INTO project_token_tracking (interface_type, tool_name, tokens_returned, tokens_full_file)
                VALUES (?, ?, ?, ?)
                """,
                ("cli", "local_coder_full", 200, 3000),
            )
            conn.commit()
            conn.close()

            # Step 2: Create SessionTracker (triggers migration + creates unified_savings view)
            tracker = SessionTracker(db_path)

            # Step 3: Add new session-based data
            tracker.get_or_create_session(
                "new-sess-1", "build parser", "qwen2.5-coder:7b"
            )
            tracker.record_generation("new-sess-1", 7000, "qwen2.5-coder:7b")
            tracker.record_review_cost("new-sess-1", 1000)

            # Step 4: Query unified_savings view
            cursor = tracker._conn.execute(
                "SELECT session_id, model, gross_savings, total_review_cost, net_savings "
                "FROM unified_savings ORDER BY session_id"
            )
            rows = cursor.fetchall()

            # Step 5: Verify both legacy records and new session records appear
            # Collect into dict by session_id for easier assertion
            records = {row[0]: row for row in rows}

            # Legacy records should have session_id with 'legacy_' prefix
            assert "legacy_1" in records, f"Missing legacy_1 in {list(records.keys())}"
            assert "legacy_2" in records, f"Missing legacy_2 in {list(records.keys())}"

            # New session record
            assert "new-sess-1" in records, f"Missing new-sess-1 in {list(records.keys())}"

            # Step 6: Verify legacy records have review_cost=0 and net_savings=gross_savings
            legacy_1 = records["legacy_1"]
            assert legacy_1[1] == "local_coder_patch"  # model
            assert legacy_1[2] == 5000  # gross_savings = tokens_full_file
            assert legacy_1[3] == 0  # total_review_cost = 0
            assert legacy_1[4] == 5000  # net_savings = gross_savings

            legacy_2 = records["legacy_2"]
            assert legacy_2[1] == "local_coder_full"  # model
            assert legacy_2[2] == 3000  # gross_savings = tokens_full_file
            assert legacy_2[3] == 0  # total_review_cost = 0
            assert legacy_2[4] == 3000  # net_savings = gross_savings

            # Verify new session record
            new_sess = records["new-sess-1"]
            assert new_sess[1] == "qwen2.5-coder:7b"  # model
            assert new_sess[2] == 7000  # gross_savings
            assert new_sess[3] == 1000  # total_review_cost
            assert new_sess[4] == 6000  # net_savings = 7000 - 1000
        finally:
            tracker._conn.close()
            os.unlink(db_path)
