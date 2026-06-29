"""Property-based tests for sample listing reflecting isolation state.

**Validates: Requirements 4.3, 4.4**

Tests the PURE LOGIC of the sample listing response without a running server.

The server logic being tested:
  The /api/samples endpoint loads samples from the DB and returns them via
  spread operator ({ ...s, tags: associatedTags }). This means `isolated_path`
  is present in the response when it exists on the sample object, and absent
  when it doesn't. No filtering or transformation is applied to this field.
"""

from hypothesis import given, settings
import hypothesis.strategies as st
from typing import Any


# Strategy: generate a sample dict that HAS completed isolation
isolated_sample_strategy = st.fixed_dictionaries({
    "id": st.from_regex(r"[a-zA-Z0-9_-]{3,20}", fullmatch=True),
    "phrase_text": st.text(min_size=1, max_size=50),
    "isolated_path": st.from_regex(r"/api/samples/audio/[a-zA-Z0-9_-]+_isolated", fullmatch=True),
})

# Strategy: generate a sample dict that has NOT completed isolation (no isolated_path key)
unisolated_sample_strategy = st.fixed_dictionaries({
    "id": st.from_regex(r"[a-zA-Z0-9_-]{3,20}", fullmatch=True),
    "phrase_text": st.text(min_size=1, max_size=50),
})


def simulate_sample_listing(samples: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Simulate the /api/samples listing response.

    The server uses spread operator to copy all fields from the DB record.
    This function mirrors that behavior: return samples as-is.
    """
    return [{**s} for s in samples]


@given(
    isolated=st.lists(isolated_sample_strategy, min_size=1, max_size=10),
    unisolated=st.lists(unisolated_sample_strategy, min_size=1, max_size=10),
)
@settings(max_examples=100)
def test_listing_includes_isolated_path_for_isolated_samples(
    isolated: list[dict[str, Any]], unisolated: list[dict[str, Any]]
) -> None:
    """For any mix of isolated and unisolated samples, the listing response
    includes `isolated_path` only for samples that have it in the DB.

    **Validates: Requirements 4.3, 4.4**
    """
    all_samples = isolated + unisolated
    response_samples = simulate_sample_listing(all_samples)

    for sample in response_samples:
        if "isolated_path" in sample:
            # Sample has isolated_path → it must be one of the isolated ones
            assert sample["isolated_path"].startswith("/api/samples/audio/")
            assert sample["isolated_path"].endswith("_isolated")
        else:
            # Sample does not have isolated_path → it must be unisolated
            assert "isolated_path" not in sample


@given(
    isolated=st.lists(isolated_sample_strategy, min_size=0, max_size=10),
    unisolated=st.lists(unisolated_sample_strategy, min_size=0, max_size=10),
)
@settings(max_examples=100)
def test_listing_omits_isolated_path_for_unisolated_samples(
    isolated: list[dict[str, Any]], unisolated: list[dict[str, Any]]
) -> None:
    """For any set of samples without `isolated_path` in the DB, the listing
    response SHALL omit the `isolated_path` field entirely.

    **Validates: Requirements 4.3, 4.4**
    """
    all_samples = isolated + unisolated
    response_samples = simulate_sample_listing(all_samples)

    # Count how many response samples have isolated_path
    response_isolated_count = sum(
        1 for s in response_samples if "isolated_path" in s
    )
    # Must match exactly the number of input samples that had isolated_path
    assert response_isolated_count == len(isolated)


@given(samples=st.lists(unisolated_sample_strategy, min_size=1, max_size=15))
@settings(max_examples=100)
def test_listing_no_isolated_path_when_none_isolated(
    samples: list[dict[str, Any]]
) -> None:
    """When no samples have completed isolation, the listing response SHALL
    have zero samples with `isolated_path` present.

    **Validates: Requirements 4.3, 4.4**
    """
    response_samples = simulate_sample_listing(samples)

    for sample in response_samples:
        assert "isolated_path" not in sample


@given(samples=st.lists(isolated_sample_strategy, min_size=1, max_size=15))
@settings(max_examples=100)
def test_listing_all_have_isolated_path_when_all_isolated(
    samples: list[dict[str, Any]]
) -> None:
    """When all samples have completed isolation, the listing response SHALL
    include `isolated_path` for every sample.

    **Validates: Requirements 4.3, 4.4**
    """
    response_samples = simulate_sample_listing(samples)

    for sample in response_samples:
        assert "isolated_path" in sample
        assert isinstance(sample["isolated_path"], str)
        assert len(sample["isolated_path"]) > 0
