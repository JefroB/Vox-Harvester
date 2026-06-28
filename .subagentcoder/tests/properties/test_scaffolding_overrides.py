# Feature: scaffolding-library, Property 7: Override Semantics
"""Property-based tests for override semantics in scaffolding selection.

**Validates: Requirements 5.2, 5.3, 5.4**

For any set of shared templates and project templates, after applying
_apply_overrides: (a) for every name that appears in both sets, only the
project version is present in the merged result; (b) all templates with
unique names (appearing in only one set) are present in the merged result.
The merged list contains exactly len(unique_shared_names) + len(project_templates)
entries where unique_shared_names are shared names not overridden.
"""

from pathlib import Path

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from local_coder.scaffolding_selector import _apply_overrides, TemplateInfo


# --- Strategies ---

# Generate template names: short alphanumeric strings
name_strategy = st.text(
    alphabet="abcdefghij",
    min_size=1,
    max_size=8,
)

# Generate a pool of unique names to split between shared and project sets
name_pool_strategy = st.lists(
    name_strategy,
    min_size=2,
    max_size=10,
    unique=True,
)


def _make_template(name: str, source: str) -> TemplateInfo:
    """Build a TemplateInfo with given name and source."""
    return TemplateInfo(
        name=name,
        path=Path(f"/tmp/{source}/{name}.md"),
        tags=["test"],
        category="test",
        complexity="any",
        description=f"{source} template {name}",
        priority=0,
        source=source,
        token_estimate=100,
    )


@st.composite
def overlapping_template_sets(draw):
    """Generate shared and project template lists with some overlapping names.

    Splits a pool of unique names into three groups:
    - shared_only: names that appear only in shared set
    - project_only: names that appear only in project set
    - both: names that appear in both sets (overlap)

    Ensures at least one name exists in total. The overlap group may be empty.
    """
    pool = draw(name_pool_strategy)
    assume(len(pool) >= 2)

    # Split pool indices into three groups using random boolean masks
    # Each name can be: shared_only, project_only, or both
    assignments = draw(st.lists(
        st.sampled_from(["shared_only", "project_only", "both"]),
        min_size=len(pool),
        max_size=len(pool),
    ))

    shared_only_names = [pool[i] for i, a in enumerate(assignments) if a == "shared_only"]
    project_only_names = [pool[i] for i, a in enumerate(assignments) if a == "project_only"]
    both_names = [pool[i] for i, a in enumerate(assignments) if a == "both"]

    # Ensure we have at least one template total
    assume(len(shared_only_names) + len(project_only_names) + len(both_names) > 0)

    # Build TemplateInfo objects
    shared_templates = (
        [_make_template(n, "shared") for n in shared_only_names]
        + [_make_template(n, "shared") for n in both_names]
    )
    project_templates = (
        [_make_template(n, "project") for n in project_only_names]
        + [_make_template(n, "project") for n in both_names]
    )

    return shared_templates, project_templates, shared_only_names, project_only_names, both_names


# --- Property Tests ---


@settings(max_examples=100)
@given(data=overlapping_template_sets())
def test_overridden_shared_templates_excluded(data):
    """For every name in both shared and project sets, only the project version is in the result."""
    shared_templates, project_templates, shared_only, project_only, both_names = data

    result = _apply_overrides(shared_templates, project_templates)
    result_by_name = {t.name: t for t in result}

    for name in both_names:
        assert name in result_by_name, (
            f"Name '{name}' appears in both sets but is missing from merged result"
        )
        assert result_by_name[name].source == "project", (
            f"Name '{name}' appears in both sets but merged result has "
            f"source='{result_by_name[name].source}' instead of 'project'"
        )


@settings(max_examples=100)
@given(data=overlapping_template_sets())
def test_all_project_templates_included(data):
    """All project templates appear in the merged result."""
    shared_templates, project_templates, shared_only, project_only, both_names = data

    result = _apply_overrides(shared_templates, project_templates)
    result_sources = [(t.name, t.source) for t in result]

    for pt in project_templates:
        assert (pt.name, "project") in result_sources, (
            f"Project template '{pt.name}' not found in merged result"
        )


@settings(max_examples=100)
@given(data=overlapping_template_sets())
def test_unique_shared_templates_included(data):
    """Shared templates with unique names (not in project set) appear in the result."""
    shared_templates, project_templates, shared_only, project_only, both_names = data

    result = _apply_overrides(shared_templates, project_templates)
    result_names = {t.name for t in result}

    for name in shared_only:
        assert name in result_names, (
            f"Shared-only template '{name}' missing from merged result"
        )


@settings(max_examples=100)
@given(data=overlapping_template_sets())
def test_merged_count_equals_unique_shared_plus_all_project(data):
    """Merged list has exactly len(unique_shared) + len(project_templates) entries."""
    shared_templates, project_templates, shared_only, project_only, both_names = data

    result = _apply_overrides(shared_templates, project_templates)

    # unique_shared_names = shared names NOT present in project set
    project_names = {t.name for t in project_templates}
    unique_shared_count = len([t for t in shared_templates if t.name not in project_names])
    expected_count = unique_shared_count + len(project_templates)

    assert len(result) == expected_count, (
        f"Expected {expected_count} templates "
        f"(unique_shared={unique_shared_count} + project={len(project_templates)}), "
        f"got {len(result)}.\n"
        f"shared_only={shared_only}, project_only={project_only}, both={both_names}"
    )
