"""Result Database — Persistent SQLite storage for task execution results.

Stores every local coder task execution with complexity, outcome, tokens,
file tags, model used, and timing for long-term trend analysis.

Database location: .codesearch/task_results.db
"""

import json
import sqlite3
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


class ResultDatabaseError(Exception):
    """Raised when the result database cannot be created or accessed."""

    pass


@dataclass
class TaskResult:
    """A single task execution result record."""

    task_id: str  # UUID
    task_description: str
    model_used: str
    complexity_score: int
    outcome: Literal["success", "fail", "escalated"]
    token_count: int
    generation_duration_ms: int
    review_iterations: int
    file_tags: list[dict] = field(default_factory=list)
    error_type: str | None = None
    delegation_method: Literal["local", "cloud", "escalated"] | None = None
    timestamp: str = ""  # ISO 8601


_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS task_results (
    task_id TEXT PRIMARY KEY,
    task_description TEXT NOT NULL,
    model_used TEXT NOT NULL,
    complexity_score INTEGER NOT NULL,
    outcome TEXT NOT NULL CHECK (outcome IN ('success', 'fail', 'escalated')),
    token_count INTEGER NOT NULL DEFAULT 0,
    generation_duration_ms INTEGER NOT NULL DEFAULT 0,
    review_iterations INTEGER NOT NULL DEFAULT 0,
    file_tags TEXT NOT NULL DEFAULT '[]',
    error_type TEXT,
    delegation_method TEXT CHECK (delegation_method IN ('local', 'cloud', 'escalated') OR delegation_method IS NULL),
    timestamp TEXT NOT NULL
);
"""

_MIGRATION_SQL = [
    # Add delegation_method column if it doesn't exist (schema v2)
    """
    ALTER TABLE task_results ADD COLUMN delegation_method TEXT
    CHECK (delegation_method IN ('local', 'cloud', 'escalated') OR delegation_method IS NULL);
    """,
]

_INDEX_SQL = [
    "CREATE INDEX IF NOT EXISTS idx_task_results_model ON task_results(model_used);",
    "CREATE INDEX IF NOT EXISTS idx_task_results_complexity ON task_results(complexity_score);",
    "CREATE INDEX IF NOT EXISTS idx_task_results_outcome ON task_results(outcome);",
    "CREATE INDEX IF NOT EXISTS idx_task_results_timestamp ON task_results(timestamp);",
]

# Valid filter keys for query_results
_VALID_FILTER_KEYS = {"model", "complexity_score", "outcome", "delegation_method", "date_from", "date_to"}


class ResultDatabase:
    """Persistent SQLite database for task execution results.

    Stores results at the specified db_path. Schema creation is idempotent
    using CREATE TABLE IF NOT EXISTS and CREATE INDEX IF NOT EXISTS.
    """

    def __init__(self, db_path: Path):
        """Open or create the SQLite database with idempotent schema creation.

        Args:
            db_path: Path to the SQLite database file.

        Raises:
            ResultDatabaseError: If the database file cannot be created
                (e.g., permissions error, invalid path).
        """
        self._db_path = db_path
        try:
            # Ensure parent directory exists
            db_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(db_path))
            self._conn.row_factory = sqlite3.Row
            self._create_schema()
        except (OSError, sqlite3.Error) as e:
            raise ResultDatabaseError(
                f"Cannot create or open database at {db_path}: {e}"
            ) from e

    def _create_schema(self) -> None:
        """Create tables and indexes idempotently, then run migrations."""
        self._conn.execute(_SCHEMA_SQL)
        for index_sql in _INDEX_SQL:
            self._conn.execute(index_sql)
        self._run_migrations()
        self._conn.commit()

    def _run_migrations(self) -> None:
        """Apply schema migrations idempotently.

        Each migration is attempted and silently ignored if already applied
        (e.g., column already exists).
        """
        for migration in _MIGRATION_SQL:
            try:
                self._conn.execute(migration)
            except sqlite3.OperationalError:
                # Column already exists or migration already applied
                pass

    def insert_result(self, result: TaskResult) -> None:
        """Insert a task result record into the database.

        If the insert fails (disk full, corruption, etc.), logs a warning
        to stderr but does not raise — the generation pipeline must not crash
        due to instrumentation failures.
        """
        try:
            file_tags_json = json.dumps(result.file_tags)
            self._conn.execute(
                """
                INSERT OR REPLACE INTO task_results
                    (task_id, task_description, model_used, complexity_score,
                     outcome, token_count, generation_duration_ms,
                     review_iterations, file_tags, error_type,
                     delegation_method, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    result.task_id,
                    result.task_description,
                    result.model_used,
                    result.complexity_score,
                    result.outcome,
                    result.token_count,
                    result.generation_duration_ms,
                    result.review_iterations,
                    file_tags_json,
                    result.error_type,
                    result.delegation_method,
                    result.timestamp,
                ),
            )
            self._conn.commit()
        except sqlite3.Error as e:
            print(
                f"[RESULT-DB] Write failed: {e}",
                file=sys.stderr,
            )

    def query_results(self, filters: dict) -> list[dict]:
        """Query results with optional filters.

        Supported filter keys:
            - model: str — filter by model_used
            - complexity_score: int — filter by complexity_score
            - outcome: str — filter by outcome
            - date_from: str — ISO date, include results on or after this date
            - date_to: str — ISO date, include results on or before this date

        Args:
            filters: Dictionary of filter key-value pairs.

        Returns:
            List of result dictionaries with all fields.

        Raises:
            ValueError: If an invalid filter key is provided.
        """
        # Validate filter keys
        invalid_keys = set(filters.keys()) - _VALID_FILTER_KEYS
        if invalid_keys:
            raise ValueError(
                f"Invalid filter keys: {invalid_keys}. "
                f"Valid keys are: {_VALID_FILTER_KEYS}"
            )

        query = "SELECT * FROM task_results WHERE 1=1"
        params: list = []

        if "model" in filters:
            query += " AND model_used = ?"
            params.append(filters["model"])

        if "complexity_score" in filters:
            query += " AND complexity_score = ?"
            params.append(filters["complexity_score"])

        if "outcome" in filters:
            query += " AND outcome = ?"
            params.append(filters["outcome"])

        if "delegation_method" in filters:
            query += " AND delegation_method = ?"
            params.append(filters["delegation_method"])

        if "date_from" in filters:
            query += " AND timestamp >= ?"
            params.append(filters["date_from"])

        if "date_to" in filters:
            query += " AND timestamp <= ?"
            params.append(filters["date_to"])

        query += " ORDER BY timestamp DESC"

        cursor = self._conn.execute(query, params)
        rows = cursor.fetchall()

        results = []
        for row in rows:
            record = dict(row)
            # Deserialize file_tags from JSON string
            record["file_tags"] = json.loads(record["file_tags"])
            results.append(record)

        return results

    def compute_success_rate(self, group_by: str) -> dict:
        """Compute success percentages grouped by a field.

        Args:
            group_by: One of "model", "complexity_score", or "error_type".

        Returns:
            Dictionary mapping group values to their success rate percentage.
            Format: {group_value: {"success_rate": float, "total": int, "successes": int}}

        Raises:
            ValueError: If group_by is not a valid grouping field.
        """
        valid_groups = {"model", "complexity_score", "error_type", "delegation_method"}
        if group_by not in valid_groups:
            raise ValueError(
                f"Invalid group_by: '{group_by}'. Must be one of: {valid_groups}"
            )

        # Map group_by parameter to actual column name
        column_map = {
            "model": "model_used",
            "complexity_score": "complexity_score",
            "error_type": "error_type",
            "delegation_method": "delegation_method",
        }
        column = column_map[group_by]

        cursor = self._conn.execute(
            f"""
            SELECT
                {column} AS group_key,
                COUNT(*) AS total,
                SUM(CASE WHEN outcome = 'success' THEN 1 ELSE 0 END) AS successes
            FROM task_results
            GROUP BY {column}
            """,
        )

        results = {}
        for row in cursor.fetchall():
            group_key = row[0]
            total = row[1]
            successes = row[2]
            success_rate = (successes / total * 100) if total > 0 else 0.0
            results[group_key] = {
                "success_rate": success_rate,
                "total": total,
                "successes": successes,
            }

        return results

    def get_complexity_report(self) -> list[dict]:
        """Generate complexity breakdown with success/fail rates, avg tokens, avg iterations.

        Rows with fewer than 3 tasks are marked as 'insufficient data' —
        success_rate, failure_rate, avg_tokens, and avg_iterations will be None.

        Returns:
            List of dicts with keys: complexity_score, total_tasks, success_rate,
            failure_rate, avg_tokens, avg_iterations, insufficient_data.
        """
        cursor = self._conn.execute(
            """
            SELECT
                complexity_score,
                COUNT(*) AS total_tasks,
                SUM(CASE WHEN outcome = 'success' THEN 1 ELSE 0 END) AS successes,
                SUM(CASE WHEN outcome = 'fail' THEN 1 ELSE 0 END) AS failures,
                AVG(token_count) AS avg_tokens,
                AVG(review_iterations) AS avg_iterations
            FROM task_results
            GROUP BY complexity_score
            ORDER BY complexity_score
            """
        )

        report = []
        for row in cursor.fetchall():
            complexity_score = row[0]
            total_tasks = row[1]
            successes = row[2]
            failures = row[3]
            avg_tokens = row[4]
            avg_iterations = row[5]

            insufficient = total_tasks < 3

            if insufficient:
                report.append(
                    {
                        "complexity_score": complexity_score,
                        "total_tasks": total_tasks,
                        "success_rate": None,
                        "failure_rate": None,
                        "avg_tokens": None,
                        "avg_iterations": None,
                        "insufficient_data": True,
                    }
                )
            else:
                report.append(
                    {
                        "complexity_score": complexity_score,
                        "total_tasks": total_tasks,
                        "success_rate": (successes / total_tasks) * 100,
                        "failure_rate": (failures / total_tasks) * 100,
                        "avg_tokens": float(avg_tokens),
                        "avg_iterations": float(avg_iterations),
                        "insufficient_data": False,
                    }
                )

        return report

    def get_detailed_report(self, since_days: int | None = None) -> dict:
        """Generate comprehensive report for --stats --detailed.

        Args:
            since_days: If provided, filter to last N days.

        Returns:
            Dictionary with keys: total_tasks, date_range, outcome_breakdown,
            per_model_rates, per_complexity_rates, top_error_types.
        """
        from datetime import datetime, timedelta, timezone

        # Build date filter clause
        params: list = []
        date_filter = ""
        if since_days is not None:
            cutoff = datetime.now(timezone.utc) - timedelta(days=since_days)
            cutoff_iso = cutoff.isoformat()
            date_filter = " WHERE timestamp >= ?"
            params = [cutoff_iso]

        # Total tasks
        cursor = self._conn.execute(
            f"SELECT COUNT(*) FROM task_results{date_filter}", params
        )
        total_tasks = cursor.fetchone()[0]

        # Date range
        cursor = self._conn.execute(
            f"SELECT MIN(timestamp), MAX(timestamp) FROM task_results{date_filter}",
            params,
        )
        row = cursor.fetchone()
        date_range = {"from": row[0] or "", "to": row[1] or ""}

        # Outcome breakdown
        cursor = self._conn.execute(
            f"""
            SELECT outcome, COUNT(*) FROM task_results{date_filter}
            GROUP BY outcome
            """,
            params,
        )
        outcome_breakdown = {"success": 0, "fail": 0, "escalated": 0}
        for row in cursor.fetchall():
            outcome_breakdown[row[0]] = row[1]

        # Per-model rates
        cursor = self._conn.execute(
            f"""
            SELECT
                model_used,
                COUNT(*) AS total,
                SUM(CASE WHEN outcome = 'success' THEN 1 ELSE 0 END) AS successes
            FROM task_results{date_filter}
            GROUP BY model_used
            """,
            params,
        )
        per_model_rates = {}
        for row in cursor.fetchall():
            model = row[0]
            total = row[1]
            successes = row[2]
            per_model_rates[model] = {
                "success_rate": (successes / total * 100) if total > 0 else 0.0,
                "total": total,
            }

        # Per-complexity rates
        cursor = self._conn.execute(
            f"""
            SELECT
                complexity_score,
                COUNT(*) AS total,
                SUM(CASE WHEN outcome = 'success' THEN 1 ELSE 0 END) AS successes
            FROM task_results{date_filter}
            GROUP BY complexity_score
            ORDER BY complexity_score
            """,
            params,
        )
        per_complexity_rates = {}
        for row in cursor.fetchall():
            score = row[0]
            total = row[1]
            successes = row[2]
            per_complexity_rates[score] = {
                "success_rate": (successes / total * 100) if total > 0 else 0.0,
                "total": total,
            }

        # Top 3 error types
        cursor = self._conn.execute(
            f"""
            SELECT error_type, COUNT(*) AS cnt
            FROM task_results
            {date_filter.replace("WHERE", "WHERE error_type IS NOT NULL AND") if date_filter else "WHERE error_type IS NOT NULL"}
            GROUP BY error_type
            ORDER BY cnt DESC
            LIMIT 3
            """,
            params,
        )
        top_error_types = []
        for row in cursor.fetchall():
            error_type = row[0]
            count = row[1]

            # Find affected complexity levels for this error type
            level_params = [error_type] + params
            level_filter = (
                " AND timestamp >= ?" if date_filter else ""
            )
            level_cursor = self._conn.execute(
                f"""
                SELECT DISTINCT complexity_score
                FROM task_results
                WHERE error_type = ?{level_filter}
                ORDER BY complexity_score
                """,
                level_params,
            )
            affected_levels = [r[0] for r in level_cursor.fetchall()]

            top_error_types.append(
                {
                    "error_type": error_type,
                    "count": count,
                    "affected_levels": affected_levels,
                }
            )

        return {
            "total_tasks": total_tasks,
            "date_range": date_range,
            "outcome_breakdown": outcome_breakdown,
            "per_model_rates": per_model_rates,
            "per_complexity_rates": per_complexity_rates,
            "top_error_types": top_error_types,
        }

    def close(self) -> None:
        """Close the database connection."""
        if self._conn:
            self._conn.close()
