# Feature: local-coder-task-intelligence, Properties 5, 11–16: Result Database
"""Property-based tests for the task result database.

Tests validate that:
- Property 5: Complexity report computes correct statistics per level
- Property 11: TaskResult round-trip persistence
- Property 12: Query filter returns only matching results
- Property 13: Success rate computation correctness
- Property 14: Schema creation is idempotent
- Property 15: Date filtering returns only records within time window
- Property 16: Detailed report correctly aggregates data
"""

import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from local_coder.result_database import TaskResult, ResultDatabase, ResultDatabaseError


# --- Generators ---

VALID_OUTCOMES = ["success", "fail", "escalated"]
FIBONACCI_SCORES = [1, 2, 3, 5, 8, 13, 21]
MODELS = ["qwen2.5-coder:7b", "qwen3-coder:30b-a3b-q4_K_M", "qwen3:8b"]
ERROR_TYPES = [None, "garbage", "timeout", "empty_response", "syntax_error", "type_error"]


def task_result_records():
    """Generate valid TaskResult instances with random field values."""
    return st.builds(
        TaskResult,
        task_id=st.builds(lambda: str(uuid.uuid4())),
        task_description=st.text(min_size=1, max_size=200),
        model_used=st.sampled_from(MODELS),
        complexity_score=st.sampled_from(FIBONACCI_SCORES),
        outcome=st.sampled_from(VALID_OUTCOMES),
        token_count=st.integers(min_value=0, max_value=100000),
        generation_duration_ms=st.integers(min_value=0, max_value=600000),
        review_iterations=st.integers(min_value=0, max_value=10),
        file_tags=st.lists(
            st.fixed_dictionaries({
                "file_path": st.from_regex(r"[a-z_][a-z0-9_/]{0,20}\.(py|ts|js)", fullmatch=True),
                "line_range": st.one_of(
                    st.none(),
                    st.tuples(
                        st.integers(min_value=1, max_value=500),
                        st.integers(min_value=1, max_value=500),
                    ).map(lambda t: (min(t), max(t))),
                ),
            }),
            min_size=0,
            max_size=5,
        ),
        error_type=st.sampled_from(ERROR_TYPES),
        timestamp=st.builds(
            lambda days_ago: (
                datetime.now(timezone.utc) - timedelta(days=days_ago)
            ).isoformat(),
            days_ago=st.integers(min_value=0, max_value=90),
        ),
    )


def filter_dicts():
    """Generate valid query filter combinations."""
    return st.fixed_dictionaries({}, optional={
        "model": st.sampled_from(MODELS),
        "complexity_score": st.sampled_from(FIBONACCI_SCORES),
        "outcome": st.sampled_from(VALID_OUTCOMES),
    })


# --- Helpers ---


def _make_db():
    """Create a fresh temp database and return (db, path)."""
    tmp = tempfile.mktemp(suffix=".db")
    db = ResultDatabase(Path(tmp))
    return db, tmp


# --- Property Tests ---


@settings(max_examples=100, deadline=None)
@given(records=st.lists(task_result_records(), min_size=3, max_size=20))
def test_property_5_complexity_report_statistics(records):
    """Property 5: Complexity report computes correct statistics per level.

    **Validates: Requirements 2.1, 2.2, 2.3, 2.4**

    For any non-empty set of TaskResult records, get_complexity_report() SHALL
    return rows where (a) success_rate equals actual successes/total for that
    level, (b) avg_tokens equals arithmetic mean of token counts, (c)
    avg_iterations equals arithmetic mean of review_iterations, (d) any level
    with < 3 records has insufficient_data = True.
    """
    db, _ = _make_db()
    try:
        # Ensure unique task_ids
        for i, record in enumerate(records):
            record.task_id = str(uuid.uuid4())
            db.insert_result(record)

        report = db.get_complexity_report()

        # Build expected values per complexity level
        level_records: dict[int, list[TaskResult]] = {}
        for r in records:
            level_records.setdefault(r.complexity_score, []).append(r)

        for row in report:
            level = row["complexity_score"]
            level_recs = level_records[level]
            total = len(level_recs)

            assert row["total_tasks"] == total

            if total < 3:
                assert row["insufficient_data"] is True
                assert row["success_rate"] is None
                assert row["avg_tokens"] is None
                assert row["avg_iterations"] is None
            else:
                assert row["insufficient_data"] is False

                # (a) success_rate = successes / total * 100
                successes = sum(1 for r in level_recs if r.outcome == "success")
                expected_rate = (successes / total) * 100
                assert abs(row["success_rate"] - expected_rate) < 0.01, (
                    f"Expected success_rate {expected_rate}, got {row['success_rate']}"
                )

                # (b) avg_tokens = mean of token_count
                expected_avg_tokens = sum(r.token_count for r in level_recs) / total
                assert abs(row["avg_tokens"] - expected_avg_tokens) < 0.01, (
                    f"Expected avg_tokens {expected_avg_tokens}, got {row['avg_tokens']}"
                )

                # (c) avg_iterations = mean of review_iterations
                expected_avg_iter = sum(r.review_iterations for r in level_recs) / total
                assert abs(row["avg_iterations"] - expected_avg_iter) < 0.01, (
                    f"Expected avg_iterations {expected_avg_iter}, got {row['avg_iterations']}"
                )
    finally:
        db.close()


@settings(max_examples=100, deadline=None)
@given(record=task_result_records())
def test_property_11_round_trip_persistence(record):
    """Property 11: TaskResult round-trip persistence.

    **Validates: Requirements 6.2**

    For any valid TaskResult, inserting and querying by task_id returns a
    record with all fields equal to the original.
    """
    db, _ = _make_db()
    try:
        # Ensure unique task_id
        record.task_id = str(uuid.uuid4())
        db.insert_result(record)

        results = db.query_results({})
        assert len(results) == 1, f"Expected 1 result, got {len(results)}"

        retrieved = results[0]

        assert retrieved["task_id"] == record.task_id
        assert retrieved["task_description"] == record.task_description
        assert retrieved["model_used"] == record.model_used
        assert retrieved["complexity_score"] == record.complexity_score
        assert retrieved["outcome"] == record.outcome
        assert retrieved["token_count"] == record.token_count
        assert retrieved["generation_duration_ms"] == record.generation_duration_ms
        assert retrieved["review_iterations"] == record.review_iterations
        # JSON round-trip converts tuples to lists, so normalize for comparison
        expected_tags = [
            {
                "file_path": t["file_path"],
                "line_range": list(t["line_range"]) if t["line_range"] is not None else None,
            }
            for t in record.file_tags
        ]
        assert retrieved["file_tags"] == expected_tags
        assert retrieved["error_type"] == record.error_type
        assert retrieved["timestamp"] == record.timestamp
    finally:
        db.close()


@settings(max_examples=100, deadline=None)
@given(
    records=st.lists(task_result_records(), min_size=2, max_size=15),
    filters=filter_dicts(),
)
def test_property_12_query_filter_returns_matching_only(records, filters):
    """Property 12: Query filter returns only matching results.

    **Validates: Requirements 6.5**

    For any set of records and any valid filter, query_results() returns
    ONLY records matching all filter criteria.
    """
    db, _ = _make_db()
    try:
        # Ensure unique task_ids
        for record in records:
            record.task_id = str(uuid.uuid4())
            db.insert_result(record)

        results = db.query_results(filters)

        # Verify every returned result matches ALL filters
        for r in results:
            if "model" in filters:
                assert r["model_used"] == filters["model"], (
                    f"Filter model={filters['model']}, got {r['model_used']}"
                )
            if "complexity_score" in filters:
                assert r["complexity_score"] == filters["complexity_score"], (
                    f"Filter complexity={filters['complexity_score']}, got {r['complexity_score']}"
                )
            if "outcome" in filters:
                assert r["outcome"] == filters["outcome"], (
                    f"Filter outcome={filters['outcome']}, got {r['outcome']}"
                )

        # Verify no matching record was omitted
        returned_ids = {r["task_id"] for r in results}
        for record in records:
            matches = True
            if "model" in filters and record.model_used != filters["model"]:
                matches = False
            if "complexity_score" in filters and record.complexity_score != filters["complexity_score"]:
                matches = False
            if "outcome" in filters and record.outcome != filters["outcome"]:
                matches = False
            if matches:
                assert record.task_id in returned_ids, (
                    f"Record {record.task_id} matches filters but was not returned"
                )
    finally:
        db.close()


@settings(max_examples=100, deadline=None)
@given(
    records=st.lists(task_result_records(), min_size=1, max_size=15),
    group_by=st.sampled_from(["model", "complexity_score", "error_type"]),
)
def test_property_13_success_rate_correctness(records, group_by):
    """Property 13: Success rate computation correctness.

    **Validates: Requirements 6.6**

    For any non-empty set of records and valid group_by, compute_success_rate()
    returns percentages where each group's rate = (successes/total)*100.
    """
    db, _ = _make_db()
    try:
        # Ensure unique task_ids
        for record in records:
            record.task_id = str(uuid.uuid4())
            db.insert_result(record)

        result = db.compute_success_rate(group_by)

        # Compute expected grouping manually
        group_field_map = {
            "model": "model_used",
            "complexity_score": "complexity_score",
            "error_type": "error_type",
        }
        field = group_field_map[group_by]

        expected_groups: dict = {}
        for rec in records:
            key = getattr(rec, field)
            if key not in expected_groups:
                expected_groups[key] = {"total": 0, "successes": 0}
            expected_groups[key]["total"] += 1
            if rec.outcome == "success":
                expected_groups[key]["successes"] += 1

        # Check each group
        for group_key, stats in result.items():
            assert group_key in expected_groups, (
                f"Unexpected group key: {group_key}"
            )
            expected = expected_groups[group_key]
            expected_rate = (expected["successes"] / expected["total"]) * 100

            assert abs(stats["success_rate"] - expected_rate) < 0.01, (
                f"Group {group_key}: expected rate {expected_rate}, got {stats['success_rate']}"
            )
            assert stats["total"] == expected["total"]
            assert stats["successes"] == expected["successes"]
    finally:
        db.close()


@settings(max_examples=100, deadline=None)
@given(n_extra_calls=st.integers(min_value=1, max_value=5))
def test_property_14_schema_creation_idempotent(n_extra_calls):
    """Property 14: Schema creation is idempotent.

    **Validates: Requirements 6.8**

    For any existing DB with valid schema, calling schema creation N
    additional times produces no errors.
    """
    tmp = tempfile.mktemp(suffix=".db")
    db_path = Path(tmp)

    # Create initial database
    db = ResultDatabase(db_path)

    try:
        # Insert a record to confirm DB is functional
        record = TaskResult(
            task_id=str(uuid.uuid4()),
            task_description="test task",
            model_used="qwen2.5-coder:7b",
            complexity_score=3,
            outcome="success",
            token_count=100,
            generation_duration_ms=5000,
            review_iterations=1,
            file_tags=[],
            error_type=None,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        db.insert_result(record)
        db.close()

        # Re-open N additional times (each triggers schema creation)
        for _ in range(n_extra_calls):
            db2 = ResultDatabase(db_path)
            # Verify data is still intact
            results = db2.query_results({})
            assert len(results) == 1
            assert results[0]["task_id"] == record.task_id
            db2.close()
    finally:
        try:
            db_path.unlink()
        except OSError:
            pass


@settings(max_examples=100, deadline=None)
@given(
    records=st.lists(task_result_records(), min_size=3, max_size=15),
    since_days=st.integers(min_value=2, max_value=30),
)
def test_property_15_date_filtering_within_window(records, since_days):
    """Property 15: Date filtering returns only records within time window.

    **Validates: Requirements 7.3**

    For records spanning multiple days, querying with since_days=N returns
    only records within last N days.
    """
    db, _ = _make_db()
    try:
        now = datetime.now(timezone.utc)

        # Assign timestamps that are clearly inside or outside the window.
        # Use half-day margins to avoid boundary race conditions between our
        # computation and the method's internal datetime.now() call.
        for i, record in enumerate(records):
            record.task_id = str(uuid.uuid4())
            # Spread records: first half within window (0 to since_days-1 days ago),
            # second half outside window (since_days+1 to since_days+30 days ago)
            if i < len(records) // 2:
                # Clearly within the window (at most since_days - 1 days ago)
                days_ago = (i * max(since_days - 2, 0)) // max(len(records) // 2 - 1, 1)
            else:
                # Clearly outside the window (at least since_days + 1 days ago)
                days_ago = since_days + 1 + (i - len(records) // 2)
            record.timestamp = (now - timedelta(days=days_ago, hours=12)).isoformat()
            db.insert_result(record)

        report = db.get_detailed_report(since_days=since_days)

        # Verify: count records that should be in the window.
        # Use a generous cutoff (since_days + a few seconds) to match
        # the method's internal computation which runs slightly later.
        cutoff = now - timedelta(days=since_days)

        expected_count = 0
        for record in records:
            record_time = datetime.fromisoformat(record.timestamp)
            if record_time >= cutoff:
                expected_count += 1

        assert report["total_tasks"] == expected_count, (
            f"Expected {expected_count} tasks within {since_days} days, "
            f"got {report['total_tasks']}"
        )
    finally:
        db.close()


@settings(max_examples=100, deadline=None)
@given(records=st.lists(task_result_records(), min_size=1, max_size=15))
def test_property_16_detailed_report_aggregation(records):
    """Property 16: Detailed report correctly aggregates data.

    **Validates: Requirements 7.2, 7.4**

    For any non-empty set of records, get_detailed_report() returns:
    (a) total_tasks = actual count, (b) outcome_breakdown sums to total,
    (c) top_error_types has at most 3 entries ordered by descending count.
    """
    db, _ = _make_db()
    try:
        # Ensure unique task_ids
        for record in records:
            record.task_id = str(uuid.uuid4())
            db.insert_result(record)

        report = db.get_detailed_report()

        # (a) total_tasks = actual record count
        assert report["total_tasks"] == len(records), (
            f"Expected total_tasks={len(records)}, got {report['total_tasks']}"
        )

        # (b) outcome_breakdown sums to total_tasks
        outcome_sum = sum(report["outcome_breakdown"].values())
        assert outcome_sum == report["total_tasks"], (
            f"Outcome breakdown sums to {outcome_sum}, expected {report['total_tasks']}"
        )

        # (c) top_error_types has at most 3 entries, ordered by descending count
        top_errors = report["top_error_types"]
        assert len(top_errors) <= 3, (
            f"Expected at most 3 top_error_types, got {len(top_errors)}"
        )

        # Verify descending order
        for i in range(len(top_errors) - 1):
            assert top_errors[i]["count"] >= top_errors[i + 1]["count"], (
                f"Error types not in descending order: "
                f"{top_errors[i]['count']} < {top_errors[i + 1]['count']}"
            )
    finally:
        db.close()
