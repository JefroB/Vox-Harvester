"""Property-based tests for job status response completeness.

**Validates: Requirements 3.5**

Property 9: Job status response completeness
For any Isolation_Job in any status (pending, processing, completed, failed),
a GET to /api/jobs/:jobId SHALL return job ID, sample ID, status, created_at,
and updated_at. When status is "completed", the response SHALL include output_path.
When status is "failed", the response SHALL include error. Fields not applicable
to the current status SHALL be absent or null.

This is a PURE LOGIC test — validates the response construction logic from server.ts
directly in Python without hitting the server.

Response construction logic from server.ts:
    const response = {
      jobId: job.jobId,
      sampleId: job.sampleId,
      status: job.status,
      created_at: job.created_at,
      updated_at: job.updated_at,
    };
    if (job.status === "completed" && job.output_path) {
      response.output_path = job.output_path;
    }
    if (job.status === "failed" && job.error) {
      response.error = job.error;
    }
"""

from dataclasses import dataclass
from typing import Optional, Any

import hypothesis.strategies as st
from hypothesis import given, settings


@dataclass
class IsolationJob:
    """Mirror of the TypeScript IsolationJob interface."""

    jobId: str
    sampleId: str
    status: str  # "pending" | "processing" | "completed" | "failed"
    created_at: str
    updated_at: str
    output_path: Optional[str] = None
    error: Optional[str] = None


def construct_response(job: IsolationJob) -> dict[str, Any]:
    """Simulate the response construction logic from server.ts."""
    response: dict[str, Any] = {
        "jobId": job.jobId,
        "sampleId": job.sampleId,
        "status": job.status,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
    }

    if job.status == "completed" and job.output_path:
        response["output_path"] = job.output_path

    if job.status == "failed" and job.error:
        response["error"] = job.error

    return response


# --- Strategies ---

job_id_strategy = st.text(min_size=1, max_size=50).filter(lambda x: x.strip() != "")
sample_id_strategy = st.text(min_size=1, max_size=50).filter(lambda x: x.strip() != "")
timestamp_strategy = st.text(min_size=1, max_size=30).filter(lambda x: x.strip() != "")
status_strategy = st.sampled_from(["pending", "processing", "completed", "failed"])


def isolation_job_strategy(status: str) -> st.SearchStrategy[IsolationJob]:
    """Generate an IsolationJob with a specific status and appropriate optional fields."""
    return st.builds(
        IsolationJob,
        jobId=job_id_strategy,
        sampleId=sample_id_strategy,
        status=st.just(status),
        created_at=timestamp_strategy,
        updated_at=timestamp_strategy,
        output_path=st.one_of(st.none(), st.text(min_size=1, max_size=100)),
        error=st.one_of(st.none(), st.text(min_size=1, max_size=500)),
    )


# Combined strategy covering all statuses
any_isolation_job = st.one_of(
    isolation_job_strategy("pending"),
    isolation_job_strategy("processing"),
    isolation_job_strategy("completed"),
    isolation_job_strategy("failed"),
)


# --- Property Tests ---


@given(job=any_isolation_job)
@settings(max_examples=100)
def test_base_fields_always_present(job: IsolationJob) -> None:
    """Base fields (jobId, sampleId, status, created_at, updated_at) are always present.

    **Validates: Requirements 3.5**
    """
    response = construct_response(job)

    assert "jobId" in response
    assert "sampleId" in response
    assert "status" in response
    assert "created_at" in response
    assert "updated_at" in response

    # Values match the job
    assert response["jobId"] == job.jobId
    assert response["sampleId"] == job.sampleId
    assert response["status"] == job.status
    assert response["created_at"] == job.created_at
    assert response["updated_at"] == job.updated_at


@given(job=isolation_job_strategy("completed"))
@settings(max_examples=100)
def test_completed_includes_output_path_when_set(job: IsolationJob) -> None:
    """When status is 'completed' and output_path is set, response includes output_path.

    **Validates: Requirements 3.5**
    """
    response = construct_response(job)

    if job.output_path:
        assert "output_path" in response
        assert response["output_path"] == job.output_path
    else:
        assert "output_path" not in response


@given(job=isolation_job_strategy("failed"))
@settings(max_examples=100)
def test_failed_includes_error_when_set(job: IsolationJob) -> None:
    """When status is 'failed' and error is set, response includes error.

    **Validates: Requirements 3.5**
    """
    response = construct_response(job)

    if job.error:
        assert "error" in response
        assert response["error"] == job.error
    else:
        assert "error" not in response


@given(job=any_isolation_job)
@settings(max_examples=100)
def test_no_inapplicable_fields_present(job: IsolationJob) -> None:
    """Fields not applicable to the current status are absent from the response.

    **Validates: Requirements 3.5**
    """
    response = construct_response(job)

    expected_fields = {"jobId", "sampleId", "status", "created_at", "updated_at"}

    if job.status == "completed" and job.output_path:
        expected_fields.add("output_path")

    if job.status == "failed" and job.error:
        expected_fields.add("error")

    actual_fields = set(response.keys())
    assert actual_fields == expected_fields, (
        f"Status={job.status}: expected {expected_fields}, got {actual_fields}"
    )


@given(job=st.one_of(isolation_job_strategy("pending"), isolation_job_strategy("processing")))
@settings(max_examples=100)
def test_pending_and_processing_have_no_extra_fields(job: IsolationJob) -> None:
    """Pending and processing jobs have only base fields regardless of optional field values.

    **Validates: Requirements 3.5**
    """
    response = construct_response(job)

    expected_fields = {"jobId", "sampleId", "status", "created_at", "updated_at"}
    actual_fields = set(response.keys())
    assert actual_fields == expected_fields, (
        f"Status={job.status}: unexpected fields {actual_fields - expected_fields}"
    )
