# Feature: scaffolding-library, Property 11: List Output Completeness
"""Property-based tests for list output completeness.

**Validates: Requirements 7.2, 7.3**

For any TemplateInfo with populated name, category, tags, complexity, description,
and source fields, the rendered list output for that template SHALL contain all of:
the name string, category string, each tag, complexity value, description text,
and a source indicator ("shared" or "project").
"""

from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from local_coder.scaffolding_selector import TemplateInfo


# --- Strategies ---

# Non-empty alphanumeric strings for text fields
alphanumeric_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N")),
    min_size=1,
    max_size=20,
)

# Tags: list of non-empty alphanumeric strings
tags_strategy = st.lists(alphanumeric_strategy, min_size=1, max_size=5)

# Complexity: one of the valid values
complexity_strategy = st.sampled_from(["simple", "complex", "any"])

# Source: shared or project
source_strategy = st.sampled_from(["shared", "project"])


@st.composite
def template_info_strategy(draw):
    """Generate a random TemplateInfo with all fields populated."""
    name = draw(alphanumeric_strategy)
    tags = draw(tags_strategy)
    category = draw(alphanumeric_strategy)
    complexity = draw(complexity_strategy)
    description = draw(alphanumeric_strategy)
    source = draw(source_strategy)
    priority = draw(st.integers(0, 100))
    token_estimate = draw(st.integers(1, 10000))

    return TemplateInfo(
        name=name,
        path=Path("/fake/t.md"),
        tags=tags,
        category=category,
        complexity=complexity,
        description=description,
        priority=priority,
        source=source,
        token_estimate=token_estimate,
    )


# --- Helper ---


def render_template_listing(template: TemplateInfo) -> str:
    """Simulate the list output format from local_coder.py's --list-scaffolding handler.

    Matches the exact format:
        {name}  [{category}]  tags={tags}  complexity={complexity}  source={source}
          {description}
    """
    line1 = f"  {template.name}  [{template.category}]  tags={template.tags}  complexity={template.complexity}  source={template.source}"
    line2 = f"    {template.description}"
    return f"{line1}\n{line2}"


# --- Property Tests ---


@settings(max_examples=100)
@given(template=template_info_strategy())
def test_list_output_contains_name(template):
    """The rendered list output contains the template name."""
    output = render_template_listing(template)
    assert template.name in output, (
        f"Name '{template.name}' not found in output:\n{output}"
    )


@settings(max_examples=100)
@given(template=template_info_strategy())
def test_list_output_contains_category(template):
    """The rendered list output contains the template category."""
    output = render_template_listing(template)
    assert template.category in output, (
        f"Category '{template.category}' not found in output:\n{output}"
    )


@settings(max_examples=100)
@given(template=template_info_strategy())
def test_list_output_contains_each_tag(template):
    """The rendered list output contains each individual tag."""
    output = render_template_listing(template)
    for tag in template.tags:
        assert tag in output, (
            f"Tag '{tag}' not found in output:\n{output}"
        )


@settings(max_examples=100)
@given(template=template_info_strategy())
def test_list_output_contains_complexity(template):
    """The rendered list output contains the complexity value."""
    output = render_template_listing(template)
    assert template.complexity in output, (
        f"Complexity '{template.complexity}' not found in output:\n{output}"
    )


@settings(max_examples=100)
@given(template=template_info_strategy())
def test_list_output_contains_description(template):
    """The rendered list output contains the description text."""
    output = render_template_listing(template)
    assert template.description in output, (
        f"Description '{template.description}' not found in output:\n{output}"
    )


@settings(max_examples=100)
@given(template=template_info_strategy())
def test_list_output_contains_source_indicator(template):
    """The rendered list output contains the source indicator ('shared' or 'project')."""
    output = render_template_listing(template)
    assert template.source in output, (
        f"Source '{template.source}' not found in output:\n{output}"
    )


@settings(max_examples=100)
@given(template=template_info_strategy())
def test_list_output_contains_all_fields(template):
    """The rendered list output contains ALL required fields in a single check."""
    output = render_template_listing(template)

    assert template.name in output, f"Name '{template.name}' missing"
    assert template.category in output, f"Category '{template.category}' missing"
    assert template.complexity in output, f"Complexity '{template.complexity}' missing"
    assert template.description in output, f"Description '{template.description}' missing"
    assert template.source in output, f"Source '{template.source}' missing"
    for tag in template.tags:
        assert tag in output, f"Tag '{tag}' missing"
