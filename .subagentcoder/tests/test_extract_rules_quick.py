"""Quick verification test for extract_rules against the code_examples fixture."""
import sys
sys.path.insert(0, '.kiro/scripts')
from pathlib import Path
from distiller import parse_skill_file, extract_rules, DEFAULT_STOP_WORDS


def test_extract_rules_code_examples():
    """Test extract_rules against the code_examples.md fixture."""
    path = Path(__file__).resolve().parent / 'fixtures' / 'skills' / 'code_examples.md'
    name, tags, sections = parse_skill_file(path)

    assert name == "Error Handling"
    assert tags == ["code"]
    # Preamble + 3 sections: Structured Error Types, Retry Logic, Graceful Degradation
    assert len(sections) == 4

    # Task tokens: simulating a task about "retry error handling backoff"
    task_tokens = {"retry", "error", "handling", "backoff", "transient", "failures"}

    # Test section: "Structured Error Types"
    structured_section = sections[1]
    assert structured_section.heading == "Structured Error Types"
    rules, code_blocks = extract_rules(structured_section, task_tokens)
    # Should extract: verb-initial "Define..." + two bullets
    assert len(rules) == 3
    assert rules[0].startswith("Define explicit error types")
    assert rules[1].startswith("- Group errors by domain")
    assert "MUST" in rules[2]
    # Code block preceding text is "Define explicit error types instead of relying on generic exceptions:"
    # "error" is in task_tokens, but also in stop words? No - "error" is NOT in stop words
    # preceding: "Define explicit error types instead of relying on generic exceptions:"
    # tokens: define, explicit, error, types, instead, relying, generic, exceptions:
    # "error" matches task_tokens => should include
    assert len(code_blocks) == 1
    assert code_blocks[0].language == "python"

    # Test section: "Retry Logic"
    retry_section = sections[2]
    assert retry_section.heading == "Retry Logic"
    rules, code_blocks = extract_rules(retry_section, task_tokens)
    # "Implement exponential backoff..." is verb-initial + 3 bullets
    assert len(rules) == 4
    assert rules[0].startswith("Implement exponential backoff")
    assert any("NEVER" in r for r in rules)
    assert any("ALWAYS" in r for r in rules)
    assert any("Log each retry" in r for r in rules)
    # Code block preceding text: "Implement exponential backoff for transient failures:"
    # "backoff" and "transient" and "failures" are in task_tokens => include
    assert len(code_blocks) == 1
    assert code_blocks[0].language == "python"
    assert "retry_with_backoff" in code_blocks[0].content

    # Test section: "Graceful Degradation"
    graceful_section = sections[3]
    assert graceful_section.heading == "Graceful Degradation"
    rules, code_blocks = extract_rules(graceful_section, task_tokens)
    # "Return partial results..." is verb-initial + 3 bullets (Distinguish is verb-initial in bullet)
    assert len(rules) == 4
    assert any("MUST" in r for r in rules)
    assert any("Distinguish" in r for r in rules)
    # Code block preceding text: "Return partial results when non-critical dependencies fail:"
    # tokens: return, partial, results, when, non-critical, dependencies, fail:
    # None of these are in task_tokens => should NOT include
    assert len(code_blocks) == 0

    # Test with empty task_tokens - no code blocks should be included
    rules, code_blocks = extract_rules(retry_section, set())
    assert len(rules) == 4  # rules still extracted
    assert len(code_blocks) == 0  # no matching tokens

    # Test empty section
    from distiller import Section, CodeBlock
    empty_section = Section(heading="Empty", body="", code_blocks=[], is_preamble=False)
    rules, code_blocks = extract_rules(empty_section, task_tokens)
    assert rules == []
    assert code_blocks == []


def test_extract_rules_numbered_items():
    """Test extraction of numbered items."""
    from distiller import Section, CodeBlock

    section = Section(
        heading="Steps",
        body="1. First step\n2. Second step\n3. Third step\nSome paragraph.",
        code_blocks=[],
        is_preamble=False,
    )
    rules, code_blocks = extract_rules(section, set())
    assert len(rules) == 3
    assert rules[0] == "1. First step"
    assert rules[1] == "2. Second step"
    assert rules[2] == "3. Third step"


def test_extract_rules_verb_initial():
    """Test extraction of verb-initial imperative sentences."""
    from distiller import Section, CodeBlock

    section = Section(
        heading="Guidelines",
        body="Use descriptive names for variables.\nThis is just a paragraph.\nValidate inputs at boundaries.\nAnother plain paragraph.",
        code_blocks=[],
        is_preamble=False,
    )
    rules, code_blocks = extract_rules(section, set())
    assert len(rules) == 2
    assert "Use descriptive names" in rules[0]
    assert "Validate inputs" in rules[1]


if __name__ == "__main__":
    test_extract_rules_code_examples()
    test_extract_rules_numbered_items()
    test_extract_rules_verb_initial()
    print("All tests passed!")
