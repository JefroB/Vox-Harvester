"""Token tracking module for net savings accounting.

Provides session-based tracking of token generation, review costs,
and net savings computation.
"""

import hashlib
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path


class TokenTrackingError(Exception):
    """Base exception for token tracking errors."""

    pass


class SessionNotFoundError(TokenTrackingError):
    """Raised when a session ID doesn't exist."""

    pass


class InvalidReviewCostError(TokenTrackingError):
    """Raised when review cost is out of valid range."""

    pass


class MigrationError(TokenTrackingError):
    """Raised when schema migration fails."""

    pass


class SchemaMigrator:
    """Applies additive-only schema migrations idempotently."""

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def needs_migration(self) -> bool:
        """Check if generation_sessions table exists.

        Returns True if migration is needed (table does NOT exist),
        False if already migrated.
        """
        cursor = self._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='generation_sessions'"
        )
        return cursor.fetchone() is None

    def migrate(self) -> None:
        """Apply migration within a single transaction.

        Creates:
        - generation_sessions table
        - session_generations table (junction)
        - review_costs table

        Does NOT modify project_token_tracking.
        Rolls back on any failure.
        """
        if not self.needs_migration():
            return

        try:
            self._conn.execute("BEGIN")

            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS generation_sessions (
                    session_id TEXT PRIMARY KEY,
                    task_hash TEXT NOT NULL,
                    model TEXT NOT NULL,
                    gross_savings INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)

            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS session_generations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL REFERENCES generation_sessions(session_id),
                    phase TEXT NOT NULL CHECK (phase IN ('initial', 'rework')),
                    token_count INTEGER NOT NULL DEFAULT 0,
                    model TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)

            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS review_costs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL REFERENCES generation_sessions(session_id),
                    tokens INTEGER NOT NULL CHECK (tokens > 0 AND tokens <= 10000000),
                    created_at TEXT NOT NULL
                )
            """)

            self._conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_session_generations_session
                    ON session_generations(session_id)
            """)

            self._conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_review_costs_session
                    ON review_costs(session_id)
            """)

            self._conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_generation_sessions_task_hash
                    ON generation_sessions(task_hash, created_at)
            """)

            # Create unified_savings view for legacy compatibility
            self._create_unified_savings_view()

            self._conn.execute("COMMIT")
        except Exception as e:
            try:
                self._conn.execute("ROLLBACK")
            except Exception:
                pass  # Best-effort rollback; original error is more important
            raise MigrationError(f"Schema migration failed: {e}") from e

    def _create_unified_savings_view(self) -> None:
        """Create the unified_savings view.

        If `project_token_tracking` table exists, unions new session-based
        records with legacy records. Otherwise, creates the view with only
        session-based records.
        """
        # Check if the legacy table exists
        cursor = self._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='project_token_tracking'"
        )
        has_legacy_table = cursor.fetchone() is not None

        if has_legacy_table:
            self._conn.execute("""
                CREATE VIEW IF NOT EXISTS unified_savings AS
                    -- New session-based records
                    SELECT
                        gs.session_id,
                        gs.model,
                        gs.gross_savings,
                        COALESCE((SELECT SUM(tokens) FROM review_costs rc WHERE rc.session_id = gs.session_id), 0) AS total_review_cost,
                        MAX(0, gs.gross_savings - COALESCE((SELECT SUM(tokens) FROM review_costs rc WHERE rc.session_id = gs.session_id), 0)) AS net_savings,
                        EXISTS(SELECT 1 FROM session_generations sg WHERE sg.session_id = gs.session_id AND sg.phase = 'rework') AS has_rework
                    FROM generation_sessions gs
                    UNION ALL
                    -- Legacy records (pre-migration, no session ID)
                    SELECT
                        'legacy_' || CAST(ptt.id AS TEXT) AS session_id,
                        ptt.tool_name AS model,
                        ptt.tokens_full_file AS gross_savings,
                        0 AS total_review_cost,
                        ptt.tokens_full_file AS net_savings,
                        0 AS has_rework
                    FROM project_token_tracking ptt
                    WHERE ptt.tool_name LIKE 'local_coder%'
            """)
        else:
            self._conn.execute("""
                CREATE VIEW IF NOT EXISTS unified_savings AS
                    SELECT
                        gs.session_id,
                        gs.model,
                        gs.gross_savings,
                        COALESCE((SELECT SUM(tokens) FROM review_costs rc WHERE rc.session_id = gs.session_id), 0) AS total_review_cost,
                        MAX(0, gs.gross_savings - COALESCE((SELECT SUM(tokens) FROM review_costs rc WHERE rc.session_id = gs.session_id), 0)) AS net_savings,
                        EXISTS(SELECT 1 FROM session_generations sg WHERE sg.session_id = gs.session_id AND sg.phase = 'rework') AS has_rework
                    FROM generation_sessions gs
            """)


def generate_session_id(task_description: str) -> str:
    """Generate a session ID from task description.

    Format: <sha256_hex[:16]>_<utc_iso_timestamp>
    Example: "a3f8b2c1d4e5f607_2025-01-15T14:30:00Z"
    """
    task_hash = hashlib.sha256(task_description.encode()).hexdigest()[:16]
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return f"{task_hash}_{timestamp}"


def find_recent_session(
    conn: sqlite3.Connection,
    task_description: str,
    within_minutes: int = 60,
) -> str | None:
    """Find an existing session with the same task hash created within N minutes.

    Args:
        conn: SQLite database connection.
        task_description: The task text used to compute the task hash.
        within_minutes: Time window in minutes to search within.

    Returns:
        The session_id of the most recent matching session, or None if no match.
    """
    task_hash = hashlib.sha256(task_description.encode()).hexdigest()[:16]

    cursor = conn.execute(
        """
        SELECT session_id, created_at
        FROM generation_sessions
        WHERE task_hash = ?
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (task_hash,),
    )
    row = cursor.fetchone()
    if row is None:
        return None

    session_id, created_at_str = row
    # Parse the stored timestamp and check if it's within the time window
    created_at = datetime.strptime(created_at_str, "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=timezone.utc
    )
    now = datetime.now(timezone.utc)
    elapsed_minutes = (now - created_at).total_seconds() / 60.0

    if elapsed_minutes <= within_minutes:
        return session_id
    return None


class SessionTracker:
    """Manages generation sessions and token accounting."""

    def __init__(self, db_path: Path):
        """Initialize with path to SQLite database.

        Opens a SQLite connection and triggers auto-migration via SchemaMigrator
        to ensure the schema is up-to-date on first use.
        """
        self._conn = sqlite3.connect(str(db_path))
        migrator = SchemaMigrator(self._conn)
        migrator.migrate()

    def get_or_create_session(
        self,
        session_id: str | None,
        task_description: str,
        model: str,
    ) -> str:
        """Resolve or create a session.

        Args:
            session_id: Explicit session ID from --session-id flag, or None.
            task_description: The task text (used for auto-ID generation).
            model: The model name (e.g., "qwen2.5-coder:7b").

        Returns:
            The resolved session identifier string.
        """
        if session_id is not None:
            # Check if session already exists
            cursor = self._conn.execute(
                "SELECT session_id FROM generation_sessions WHERE session_id = ?",
                (session_id,),
            )
            if cursor.fetchone() is not None:
                return session_id
            # Create new session with the provided ID
            self._create_session(session_id, task_description, model)
            return session_id
        else:
            # Auto-generation logic: look for recent session within 60-minute window
            existing = find_recent_session(self._conn, task_description)
            if existing is not None:
                return existing
            # No recent session found — generate a new one
            new_id = generate_session_id(task_description)
            self._create_session(new_id, task_description, model)
            return new_id

    def _create_session(
        self, session_id: str, task_description: str, model: str
    ) -> None:
        """Insert a new session record into generation_sessions."""
        task_hash = hashlib.sha256(task_description.encode()).hexdigest()[:16]
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        self._conn.execute(
            """
            INSERT INTO generation_sessions (session_id, task_hash, model, gross_savings, created_at, updated_at)
            VALUES (?, ?, ?, 0, ?, ?)
            """,
            (session_id, task_hash, model, now, now),
        )
        self._conn.commit()

    def record_generation(
        self,
        session_id: str,
        eval_count: int | None,
        model: str,
    ) -> None:
        """Record a generation call within a session.

        Determines phase automatically:
        - "initial" if no prior generation exists for this session.
        - "rework" if an initial generation already exists.

        Only records gross_savings for phase="initial" with eval_count > 0.
        """
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        # Check if session exists in generation_sessions
        cursor = self._conn.execute(
            "SELECT session_id, gross_savings FROM generation_sessions WHERE session_id = ?",
            (session_id,),
        )
        session_row = cursor.fetchone()

        # Check if any generation already exists for this session
        cursor = self._conn.execute(
            "SELECT COUNT(*) FROM session_generations WHERE session_id = ?",
            (session_id,),
        )
        generation_count = cursor.fetchone()[0]

        # Determine phase
        if generation_count == 0:
            phase = "initial"
        else:
            phase = "rework"

        # Handle orphaned rework: session doesn't exist in generation_sessions
        if session_row is None:
            print(
                f"[WARN] Orphaned rework: session '{session_id}' not found, creating placeholder session",
                file=sys.stderr,
            )
            # Use a placeholder task_hash (first 16 chars of SHA-256 of session_id)
            task_hash = hashlib.sha256(session_id.encode()).hexdigest()[:16]
            self._conn.execute(
                """
                INSERT INTO generation_sessions (session_id, task_hash, model, gross_savings, created_at, updated_at)
                VALUES (?, ?, ?, 0, ?, ?)
                """,
                (session_id, task_hash, model, now, now),
            )
            self._conn.commit()
            # Orphaned rework is always "rework"
            phase = "rework"

        # For "initial" phase: update gross_savings if eval_count > 0
        if phase == "initial":
            if eval_count is not None and eval_count > 0:
                # Only set gross_savings if not already > 0 (Req 2.4)
                current_gross = session_row[1] if session_row else 0
                if current_gross == 0:
                    self._conn.execute(
                        """
                        UPDATE generation_sessions
                        SET gross_savings = ?, updated_at = ?
                        WHERE session_id = ?
                        """,
                        (eval_count, now, session_id),
                    )
            else:
                print(
                    f"[WARN] Session '{session_id}': eval_count is missing or zero, skipping gross_savings",
                    file=sys.stderr,
                )

        # Always INSERT into session_generations
        token_count = eval_count if eval_count is not None and eval_count > 0 else 0
        self._conn.execute(
            """
            INSERT INTO session_generations (session_id, phase, token_count, model, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (session_id, phase, token_count, model, now),
        )
        self._conn.commit()

    def compute_net_savings(self, session_id: str) -> int:
        """Compute net savings for a session: max(0, gross - sum(reviews)).

        If gross_savings is 0, returns 0 regardless of review costs.
        If session doesn't exist, returns 0.
        """
        cursor = self._conn.execute(
            "SELECT gross_savings FROM generation_sessions WHERE session_id = ?",
            (session_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return 0

        gross_savings = row[0]
        if gross_savings == 0:
            return 0

        cursor = self._conn.execute(
            "SELECT COALESCE(SUM(tokens), 0) FROM review_costs WHERE session_id = ?",
            (session_id,),
        )
        total_review_cost = cursor.fetchone()[0]

        return max(0, gross_savings - total_review_cost)

    def get_session(self, session_id: str) -> dict | None:
        """Retrieve session data including gross_savings, total review cost,
        net savings, and list of generation phases.

        Returns None if session doesn't exist.
        """
        cursor = self._conn.execute(
            "SELECT session_id, task_hash, model, gross_savings, created_at, updated_at "
            "FROM generation_sessions WHERE session_id = ?",
            (session_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return None

        session_id_val, task_hash, model, gross_savings, created_at, updated_at = row

        # Compute total review cost
        cursor = self._conn.execute(
            "SELECT COALESCE(SUM(tokens), 0) FROM review_costs WHERE session_id = ?",
            (session_id,),
        )
        total_review_cost = cursor.fetchone()[0]

        # Compute net savings
        net_savings = self.compute_net_savings(session_id)

        # Get list of generation phases
        cursor = self._conn.execute(
            "SELECT phase, token_count, created_at FROM session_generations "
            "WHERE session_id = ? ORDER BY id",
            (session_id,),
        )
        phases = [
            {"phase": r[0], "token_count": r[1], "created_at": r[2]}
            for r in cursor.fetchall()
        ]

        return {
            "session_id": session_id_val,
            "task_hash": task_hash,
            "model": model,
            "gross_savings": gross_savings,
            "total_review_cost": total_review_cost,
            "net_savings": net_savings,
            "phases": phases,
            "created_at": created_at,
            "updated_at": updated_at,
        }

    def compute_aggregate_stats(self) -> dict:
        """Compute totals across all sessions.

        Returns dict with:
            - total_gross_savings: int
            - total_review_cost: int
            - total_net_savings: int
            - per_model: list[dict] with model, calls, gross, review, net
            - sessions_clean: int (no rework)
            - sessions_with_rework: int
        """
        # Get all sessions
        cursor = self._conn.execute(
            "SELECT session_id, model, gross_savings FROM generation_sessions"
        )
        sessions = cursor.fetchall()

        if not sessions:
            return {
                "total_gross_savings": 0,
                "total_review_cost": 0,
                "total_net_savings": 0,
                "per_model": [],
                "sessions_clean": 0,
                "sessions_with_rework": 0,
            }

        total_gross_savings = 0
        total_review_cost = 0
        total_net_savings = 0
        sessions_clean = 0
        sessions_with_rework = 0

        # Per-model accumulator: model -> {calls, gross, review, net}
        model_stats: dict[str, dict] = {}

        for session_id, model, gross_savings in sessions:
            # Get review cost for this session
            rc_cursor = self._conn.execute(
                "SELECT COALESCE(SUM(tokens), 0) FROM review_costs WHERE session_id = ?",
                (session_id,),
            )
            review_cost = rc_cursor.fetchone()[0]

            # Per-session net savings: max(0, gross - review)
            net_savings = max(0, gross_savings - review_cost)

            # Accumulate totals
            total_gross_savings += gross_savings
            total_review_cost += review_cost
            total_net_savings += net_savings

            # Per-model breakdown
            if model not in model_stats:
                model_stats[model] = {"calls": 0, "gross": 0, "review": 0, "net": 0}
            model_stats[model]["calls"] += 1
            model_stats[model]["gross"] += gross_savings
            model_stats[model]["review"] += review_cost
            model_stats[model]["net"] += net_savings

            # Check if session has rework
            rework_cursor = self._conn.execute(
                "SELECT COUNT(*) FROM session_generations WHERE session_id = ? AND phase = 'rework'",
                (session_id,),
            )
            rework_count = rework_cursor.fetchone()[0]
            if rework_count > 0:
                sessions_with_rework += 1
            else:
                sessions_clean += 1

        # Build per_model list
        per_model = [
            {
                "model": model,
                "calls": stats["calls"],
                "gross": stats["gross"],
                "review": stats["review"],
                "net": stats["net"],
            }
            for model, stats in model_stats.items()
        ]

        return {
            "total_gross_savings": total_gross_savings,
            "total_review_cost": total_review_cost,
            "total_net_savings": total_net_savings,
            "per_model": per_model,
            "sessions_clean": sessions_clean,
            "sessions_with_rework": sessions_with_rework,
        }

    def record_review_cost(
        self,
        session_id: str,
        tokens: int,
    ) -> None:
        """Record cloud tokens consumed by Kiro reviewing this session's output.

        Args:
            session_id: Must reference an existing session.
            tokens: Must be in range [1, 10_000_000].

        Raises:
            InvalidReviewCostError: If tokens out of range.
            SessionNotFoundError: If session doesn't exist.
        """
        if tokens <= 0 or tokens > 10_000_000:
            raise InvalidReviewCostError(
                f"Review cost must be between 1 and 10,000,000, got: {tokens}"
            )

        cursor = self._conn.execute(
            "SELECT session_id FROM generation_sessions WHERE session_id = ?",
            (session_id,),
        )
        if cursor.fetchone() is None:
            raise SessionNotFoundError(f"Session not found: {session_id}")

        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        self._conn.execute(
            """
            INSERT INTO review_costs (session_id, tokens, created_at)
            VALUES (?, ?, ?)
            """,
            (session_id, tokens, now),
        )
        self._conn.commit()


def display_stats(tracker: SessionTracker) -> None:
    """Print net token savings statistics to stdout.

    Output format:
        Net Token Savings
        ==================================================
        Total gross savings:    12,500
        Total review cost:      -2,300
        Total net savings:      10,200
        ==================================================

        Per-Model Breakdown:
          Model                             Calls  Gross    Review    Net
          --------------------------------- ------ -------- --------- --------
          qwen2.5-coder:7b                      12    8,000    -1,200    6,800
          qwen3-coder:30b-a3b-q4_K_M             3    4,500    -1,100    3,400

        Session Summary:
          Clean (no rework):     10
          Required rework:        5
    """
    stats = tracker.compute_aggregate_stats()

    # If no sessions exist, display message and return
    if (
        stats["total_gross_savings"] == 0
        and stats["total_review_cost"] == 0
        and not stats["per_model"]
    ):
        print("No session data recorded.")
        return

    separator = "=" * 50

    # Header and totals
    print("Net Token Savings")
    print(separator)
    print(f"Total gross savings:    {stats['total_gross_savings']:,}")
    print(f"Total review cost:      -{stats['total_review_cost']:,}")
    print(f"Total net savings:      {stats['total_net_savings']:,}")
    print(separator)

    # Per-Model Breakdown
    print()
    print("Per-Model Breakdown:")

    # Column widths
    model_width = 33
    calls_width = 6
    gross_width = 8
    review_width = 9
    net_width = 8

    # Header row
    print(
        f"  {'Model':<{model_width}} {'Calls':>{calls_width}} "
        f"{'Gross':>{gross_width}} {'Review':>{review_width}} {'Net':>{net_width}}"
    )
    # Separator row
    print(
        f"  {'-' * model_width} {'-' * calls_width} "
        f"{'-' * gross_width} {'-' * review_width} {'-' * net_width}"
    )

    # Data rows
    for entry in stats["per_model"]:
        model_name = entry["model"]
        calls_str = str(entry["calls"])
        gross_str = f"{entry['gross']:,}"
        review_str = f"-{entry['review']:,}"
        net_str = f"{entry['net']:,}"

        print(
            f"  {model_name:<{model_width}} {calls_str:>{calls_width}} "
            f"{gross_str:>{gross_width}} {review_str:>{review_width}} {net_str:>{net_width}}"
        )

    # Session Summary
    print()
    print("Session Summary:")
    print(f"  Clean (no rework):     {stats['sessions_clean']}")
    print(f"  Required rework:       {stats['sessions_with_rework']}")
