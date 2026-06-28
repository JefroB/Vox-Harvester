"""Task annotation module for enriching task descriptions with file targets and delegation hints.

Queries CodeSearch to resolve target file paths and symbol locations, then produces
HTML comment annotations and delegation hints for the local coder orchestrator.
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

# Tag keyword mappings — used by _determine_tags to match task descriptions to tags.
_TAG_KEYWORDS: dict[str, list[str]] = {
    "code": ["implement", "function", "class", "module", "method", "write", "create", "add", "build"],
    "test": ["test", "spec", "hypothesis", "pytest", "assert", "verify", "validate"],
    "api": ["endpoint", "route", "handler", "rest", "graphql", "request", "response"],
    "security": ["auth", "authentication", "authorization", "jwt", "token", "encrypt", "password", "csrf", "xss", "injection", "validate input"],
    "refactor": ["refactor", "restructure", "extract", "rename", "simplify", "decouple"],
    "optimization": ["performance", "optimize", "cache", "speed", "memory", "profile"],
    "docs": ["document", "readme", "docstring", "comment", "explain"],
    "git": ["commit", "branch", "merge", "push", "pull", "rebase"],
    "release": ["version", "changelog", "release", "tag", "bump"],
    "new-project": ["scaffold", "initialize", "setup", "new project", "boilerplate"],
    "review": ["review", "inspect", "audit", "check"],
}

# Keywords that indicate complex tier.
_COMPLEX_KEYWORDS: list[str] = [
    "architecture", "auth", "security", "database", "module", "middleware",
    "migration", "concurrent", "async", "cryptography", "validation",
]

# Keywords that indicate prose tier.
_PROSE_KEYWORDS: list[str] = [
    "document", "readme", "explanation", "tutorial", "guide",
    "blog", "description", "summary",
]


@dataclass
class CodeSearchResult:
    """Normalized result from a CodeSearch query."""

    file_path: str  # Relative path from project root
    start_line: int | None  # Line range start (None if not found)
    end_line: int | None  # Line range end (None if not found)
    found: bool  # Whether the symbol/path was resolved


@dataclass
class AnnotationResult:
    """Result of annotating a single task."""

    annotations: list[str] = field(default_factory=list)  # List of `<!-- target: ... -->` lines
    delegation_hint: str | None = None  # `[local-coder: ...]` or `[cloud-only: ...]` or None
    warnings: list[str] = field(default_factory=list)  # Warnings emitted to stderr


class TaskAnnotator:
    """Enriches task descriptions with file targets and delegation hints."""

    def __init__(self, project_root: Path, context_window: int = 32768):
        """Initialize the TaskAnnotator.

        Args:
            project_root: Root directory of the project for resolving relative paths
                and running CodeSearch queries.
            context_window: Maximum token budget for the local model context.
                Used to determine when to omit delegation hints (80% threshold).
                Defaults to 32768 tokens.
        """
        self.project_root = project_root
        self.context_window = context_window

    def annotate_task(self, task_description: str, target_symbols: list[str]) -> AnnotationResult:
        """Query CodeSearch for each target and produce annotations.

        Queries CodeSearch for each symbol in target_symbols, produces
        formatted annotation lines, caps at 50 annotations max per task,
        and collects any warnings.

        Args:
            task_description: The task text (used later for delegation hints).
            target_symbols: List of symbol names or file paths to resolve.

        Returns:
            AnnotationResult with annotations, warnings, and (eventually)
            a delegation hint.
        """
        result = AnnotationResult()

        for symbol in target_symbols[:50]:  # Cap at 50 annotations per task
            cs_result = self._query_codesearch(symbol)
            annotation = self._format_annotation(cs_result)
            result.annotations.append(annotation)

            if not cs_result.found:
                warning = f"CodeSearch returned no results for '{symbol}'"
                result.warnings.append(warning)

        return result

    def _query_codesearch(self, symbol_or_path: str) -> CodeSearchResult:
        """Run CodeSearch CLI and parse the result.

        Tries three strategies in order:
        1. `codesearch get-definition` — returns file path + line range for symbols
        2. `codesearch search-files` — finds files by name pattern
        3. `codesearch search` — general symbol search

        Returns a CodeSearchResult with found=False if all queries return nothing.
        Emits a warning to stderr when no results are found.
        """
        # Strategy 1: get-definition (best — gives file + line range)
        result = self._run_get_definition(symbol_or_path)
        if result is not None:
            return result

        # Strategy 2: search-files (finds files by name)
        result = self._run_search_files(symbol_or_path)
        if result is not None:
            return result

        # Strategy 3: search (general symbol search)
        result = self._run_search(symbol_or_path)
        if result is not None:
            return result

        # All strategies failed — emit warning to stderr
        print(
            f"WARNING: CodeSearch returned no results for '{symbol_or_path}'",
            file=sys.stderr,
        )
        return CodeSearchResult(
            file_path=symbol_or_path,
            start_line=None,
            end_line=None,
            found=False,
        )

    def _run_codesearch_command(self, args: list[str]) -> subprocess.CompletedProcess[str]:
        """Run a codesearch CLI command and return the CompletedProcess."""
        return subprocess.run(
            ["codesearch", *args],
            capture_output=True,
            text=True,
            cwd=str(self.project_root),
        )

    def _run_get_definition(self, symbol_or_path: str) -> CodeSearchResult | None:
        """Try `codesearch get-definition` and parse JSON output."""
        proc = self._run_codesearch_command(["get-definition", symbol_or_path, "--json"])
        if proc.returncode != 0:
            return None

        stdout = proc.stdout.strip()
        if not stdout or stdout == "null":
            return None

        try:
            data = json.loads(stdout)
        except json.JSONDecodeError:
            return None

        if data is None:
            return None

        file_path = data.get("file", "")
        if not file_path:
            return None

        start_line = data.get("start_line")
        end_line = data.get("end_line")

        # Validate line range: both must be positive integers with start <= end
        if start_line is not None and end_line is not None:
            if (
                isinstance(start_line, int)
                and isinstance(end_line, int)
                and start_line > 0
                and end_line > 0
                and start_line <= end_line
            ):
                return CodeSearchResult(
                    file_path=file_path,
                    start_line=start_line,
                    end_line=end_line,
                    found=True,
                )

        # File found but no valid line range (Req 1.6: symbol not found in file)
        return CodeSearchResult(
            file_path=file_path,
            start_line=None,
            end_line=None,
            found=True,
        )

    def _run_search_files(self, symbol_or_path: str) -> CodeSearchResult | None:
        """Try `codesearch search-files` and parse JSON output."""
        proc = self._run_codesearch_command(["search-files", symbol_or_path, "--json"])
        if proc.returncode != 0:
            return None

        stdout = proc.stdout.strip()
        if not stdout or stdout == "[]":
            return None

        try:
            data = json.loads(stdout)
        except json.JSONDecodeError:
            return None

        if not isinstance(data, list) or len(data) == 0:
            return None

        # Use the first matching file
        file_path = data[0].get("path", "")
        if not file_path:
            return None

        # search-files doesn't return line ranges
        return CodeSearchResult(
            file_path=file_path,
            start_line=None,
            end_line=None,
            found=True,
        )

    def _run_search(self, symbol_or_path: str) -> CodeSearchResult | None:
        """Try `codesearch search` and parse JSON output."""
        proc = self._run_codesearch_command(["search", symbol_or_path, "--json"])
        if proc.returncode != 0:
            return None

        stdout = proc.stdout.strip()
        if not stdout or stdout == "[]":
            return None

        try:
            data = json.loads(stdout)
        except json.JSONDecodeError:
            return None

        if not isinstance(data, list) or len(data) == 0:
            return None

        # Use the highest-score result (first in list)
        best = data[0]
        file_path = best.get("file_path", "")
        if not file_path:
            return None

        start_line = best.get("start_line")
        end_line = best.get("end_line")

        # Validate line range
        if start_line is not None and end_line is not None:
            if (
                isinstance(start_line, int)
                and isinstance(end_line, int)
                and start_line > 0
                and end_line > 0
                and start_line <= end_line
            ):
                return CodeSearchResult(
                    file_path=file_path,
                    start_line=start_line,
                    end_line=end_line,
                    found=True,
                )

        # File found but no valid line range
        return CodeSearchResult(
            file_path=file_path,
            start_line=None,
            end_line=None,
            found=True,
        )

    def _format_annotation(self, result: CodeSearchResult) -> str:
        """Format a single annotation line.

        If result has valid start_line and end_line:
            <!-- target: <file_path> lines: <start_line>-<end_line> -->
        Otherwise:
            <!-- target: <file_path> -->
        """
        if result.start_line is not None and result.end_line is not None:
            return f"<!-- target: {result.file_path} lines: {result.start_line}-{result.end_line} -->"
        return f"<!-- target: {result.file_path} -->"

    def _determine_tags(self, task_description: str) -> list[str]:
        """Match task keywords to the defined tag set.

        Scans the task description for keywords associated with each tag.
        Returns between 1 and 4 tags. Defaults to ["code"] if no keywords match.

        Args:
            task_description: The task text to analyze.

        Returns:
            List of 1-4 tag strings from the defined tag set.
        """
        desc_lower = task_description.lower()
        matched: list[str] = []
        for tag, keywords in _TAG_KEYWORDS.items():
            if any(kw in desc_lower for kw in keywords):
                matched.append(tag)
        # Ensure at least 1 tag, cap at 4
        if not matched:
            matched = ["code"]
        return matched[:4]

    def _determine_complexity(self, task_description: str, target_count: int) -> str:
        """Classify task into simple/complex/prose tier.

        Priority ordering: complex > prose > simple (Req 2.7).
        A task is complex if it touches 2+ targets, contains complexity keywords,
        or has a description longer than 200 characters.
        A task is prose if it contains prose keywords and no code-generation keywords.

        Args:
            task_description: The task text to analyze.
            target_count: Number of target files/symbols the task touches.

        Returns:
            One of "simple", "complex", or "prose".
        """
        desc_lower = task_description.lower()

        is_complex = (
            target_count >= 2
            or any(kw in desc_lower for kw in _COMPLEX_KEYWORDS)
            or len(task_description) > 200
        )

        is_prose = (
            any(kw in desc_lower for kw in _PROSE_KEYWORDS)
            and not any(kw in desc_lower for kw in ["implement", "function", "class", "code"])
        )

        # Priority: complex > prose > simple
        if is_complex:
            return "complex"
        if is_prose:
            return "prose"
        return "simple"

    def _estimate_prompt_tokens(self, task_description: str, context_files: list[str]) -> int:
        """Estimate total token cost of task description + context file contents.

        Uses a rough heuristic of ~4 characters per token. Reads actual file sizes
        from disk for context files that exist.

        Args:
            task_description: The task text (contributes to token count).
            context_files: List of relative file paths whose content would be
                included in the prompt.

        Returns:
            Estimated number of tokens (integer).
        """
        total_chars = len(task_description)
        for file_path in context_files:
            full_path = self.project_root / file_path
            if full_path.exists():
                total_chars += full_path.stat().st_size
        return total_chars // 4

    def _build_delegation_hint(
        self, tags: list[str], tier: str, context_files: list[str]
    ) -> str | None:
        """Build the delegation hint string, or None/cloud-only annotation.

        Cloud-only criteria (hint omitted entirely):
        - More than 5 context files (Req 2.4: 3+ files means cloud-only)

        Cloud-only annotation returned:
        - Estimated prompt exceeds 80% of context_window (Req 2.6)

        Otherwise builds: [local-coder: --tags <T> --complexity <tier>]
        With optional --context field when ≤5 context files (Req 2.5).

        Args:
            tags: List of 1-4 tags to include.
            tier: Complexity tier ("simple", "complex", or "prose").
            context_files: List of context file paths.

        Returns:
            The hint string, "[cloud-only: context exceeds local budget]",
            or None if the task should be cloud-only (no annotation needed).
        """
        # Check cloud-only: too many files → omit hint entirely
        if len(context_files) > 5:
            return None

        # Check cloud-only: estimated prompt exceeds 80% of context window
        estimated_tokens = self._estimate_prompt_tokens("", context_files)
        if estimated_tokens > self.context_window * 0.8:
            return "[cloud-only: context exceeds local budget]"

        # Build the hint string
        hint = f"[local-coder: --tags {' '.join(tags)} --complexity {tier}"
        if context_files and len(context_files) <= 5:
            hint += f" --context {' '.join(context_files)}"
        hint += "]"
        return hint
