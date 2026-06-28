# TDD — Test-Driven Development

This project follows strict RED-GREEN-REFACTOR test-driven development. No exceptions.

## Cycle

1. **RED**: Write a failing test first. Run it. Verify it fails for the right reason.
2. **GREEN**: Write MINIMAL code to make the test pass. Nothing extra.
3. **REFACTOR**: Improve code while keeping tests green. Never skip this step.

## Commands

```bash
# Run all tests
.venv/bin/python -m pytest tests/ --no-header -q

# Run single test file
.venv/bin/python -m pytest tests/test_parser.py -v

# Run single test function
.venv/bin/python -m pytest tests/test_parser.py::test_parse_python -v

# Run with coverage
.venv/bin/python -m pytest tests/ --cov=src/codesearch --cov-report=term-missing
```

## Test Patterns

- Use `tempfile.TemporaryDirectory()` for isolated test databases
- Naming: `test_<what>_<condition>` (e.g., `test_validate_path_rejects_traversal`)
- AAA pattern: Arrange, Act, Assert
- Phase tests: `tests/test_p<N>_<name>.py`
- Module tests: `tests/test_<module>.py`
- Property-based tests use Hypothesis with `@settings(max_examples=100)`

## Rules

- Coverage minimum: 75% (enforced in pyproject.toml)
- Tests must be independent and idempotent — run in any order
- Integration tests use real SQLite, real files, real parsers — NO mocks for these
- When adding MCP tools, update tool count in `tests/test_mcp_all_tools.py` and `tests/test_mcp_protocol.py` (currently 40)

## Current Stats

- 2431 tests passing
- 88% coverage
