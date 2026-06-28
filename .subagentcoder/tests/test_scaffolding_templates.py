"""Unit tests for scaffolding template content validation.

Validates: Requirements 1.1, 1.2, 1.3, 1.4, 2.1, 2.2, 2.4, 3.1, 3.2, 3.5, 4.1, 4.2, 4.3
"""

import yaml
from pathlib import Path

BASE_PATH = Path('.kiro/scaffolding')


def parse_frontmatter(filepath: Path) -> dict | None:
    """Parse YAML frontmatter from a file delimited by --- markers."""
    content = filepath.read_text(encoding='utf-8')
    parts = content.split('---')
    if len(parts) < 3:
        return None
    return yaml.safe_load(parts[1])


def read_content(filepath: Path) -> str:
    """Read file content as UTF-8."""
    return filepath.read_text(encoding='utf-8')


class TestHypothesisAdvancedStrategies:
    """Tests for hypothesis-advanced-strategies.md template."""

    filepath = BASE_PATH / 'test-patterns' / 'hypothesis-advanced-strategies.md'

    def test_file_exists(self):
        assert self.filepath.exists()

    def test_frontmatter_tags(self):
        frontmatter = parse_frontmatter(self.filepath)
        assert frontmatter['tags'] == ['test', 'property', 'hypothesis', 'strategy']

    def test_frontmatter_priority(self):
        frontmatter = parse_frontmatter(self.filepath)
        assert frontmatter['priority'] == 15

    def test_frontmatter_complexity(self):
        frontmatter = parse_frontmatter(self.filepath)
        assert frontmatter['complexity'] == 'any'

    def test_contains_strategy_sections(self):
        content = read_content(self.filepath)
        for strategy in [
            'st.from_regex', 'st.composite', 'st.builds', 'st.one_of',
            'st.just', 'st.none', 'st.fixed_dictionaries', 'st.from_type',
        ]:
            assert strategy in content, f"Missing strategy section: {strategy}"

    def test_contains_anti_patterns_section(self):
        content = read_content(self.filepath)
        assert 'Anti-Pattern' in content

    def test_contains_composition_methods(self):
        content = read_content(self.filepath)
        for method in ['.map()', '.filter()', '.flatmap()']:
            assert method in content, f"Missing composition method: {method}"


class TestHypothesisStatefulTesting:
    """Tests for hypothesis-stateful-testing.md template."""

    filepath = BASE_PATH / 'test-patterns' / 'hypothesis-stateful-testing.md'

    def test_file_exists(self):
        assert self.filepath.exists()

    def test_frontmatter_tags(self):
        frontmatter = parse_frontmatter(self.filepath)
        assert frontmatter['tags'] == ['test', 'property', 'hypothesis', 'stateful']

    def test_frontmatter_priority(self):
        frontmatter = parse_frontmatter(self.filepath)
        assert frontmatter['priority'] == 12

    def test_frontmatter_complexity(self):
        frontmatter = parse_frontmatter(self.filepath)
        assert frontmatter['complexity'] == 'complex'

    def test_contains_rule_based_state_machine(self):
        content = read_content(self.filepath)
        assert 'RuleBasedStateMachine' in content

    def test_contains_deterministic_prefix(self):
        content = read_content(self.filepath)
        assert 'deterministic prefix' in content


class TestFallbackChainPattern:
    """Tests for fallback-chain-pattern.md template."""

    filepath = BASE_PATH / 'strategy-libraries' / 'fallback-chain-pattern.md'

    def test_file_exists(self):
        assert self.filepath.exists()

    def test_frontmatter_tags(self):
        frontmatter = parse_frontmatter(self.filepath)
        assert frontmatter['tags'] == ['code', 'error', 'fallback', 'strategy']

    def test_frontmatter_priority(self):
        frontmatter = parse_frontmatter(self.filepath)
        assert frontmatter['priority'] == 8

    def test_frontmatter_complexity(self):
        frontmatter = parse_frontmatter(self.filepath)
        assert frontmatter['complexity'] == 'any'

    def test_contains_anti_pattern_section(self):
        content = read_content(self.filepath)
        assert 'Anti-Pattern' in content

    def test_contains_warning_mechanism(self):
        content = read_content(self.filepath)
        assert 'warnings.warn' in content or 'file=sys.stderr' in content


class TestPropertyTestSkeleton:
    """Tests for property-test-skeleton.md template."""

    filepath = BASE_PATH / 'test-patterns' / 'property-test-skeleton.md'

    def test_file_exists(self):
        assert self.filepath.exists()

    def test_contains_common_pitfalls(self):
        content = read_content(self.filepath)
        assert 'Common Pitfalls' in content

    def test_contains_tempfile_workaround(self):
        content = read_content(self.filepath)
        assert 'tempfile.TemporaryDirectory' in content

    def test_contains_tmp_path_reference(self):
        content = read_content(self.filepath)
        assert 'tmp_path' in content
