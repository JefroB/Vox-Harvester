"""Scaffolding template selector for the local coder.

Discovers, filters, ranks, and selects scaffolding templates from shared
and project-level libraries based on task tags, complexity, and token budget.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml


# Workspace root: two levels up from this file (local_coder/ -> project root)
_WORKSPACE_ROOT = Path(__file__).parent.parent


@dataclass(frozen=True)
class TemplateInfo:
    """Metadata about a scaffolding template.

    Attributes:
        name: Template identifier (from frontmatter, used for override matching).
        path: Absolute path to the template file.
        tags: List of tags for matching against task tags.
        category: Template category (e.g., test-skeleton, strategy-pattern).
        complexity: Complexity level — "simple", "complex", or "any".
        description: Human-readable summary of what the template provides.
        priority: Ranking priority (higher = preferred). Default 0.
        source: Origin — "shared" or "project".
        token_estimate: Estimated token count (len(content) // 4).
    """

    name: str
    path: Path
    tags: list[str]
    category: str
    complexity: str  # "simple" | "complex" | "any"
    description: str
    priority: int
    source: str  # "shared" | "project"
    token_estimate: int


def _resolve_shared_path(override: Path | None = None) -> Path | None:
    """Resolve the shared scaffolding library path.

    Priority: override arg > SCAFFOLDING_LIBRARY_PATH env > ~/.kiro/scaffolding/
    Returns None if no valid path exists.

    Per Requirement 9.2: The path is resolvable via env var, falling back to
    ~/.kiro/scaffolding/ when unset or when the env path doesn't exist.
    """
    # 1. Override argument takes highest priority
    if override is not None and override.is_dir():
        return override

    # 2. Environment variable
    env_path_str = os.environ.get("SCAFFOLDING_LIBRARY_PATH")
    if env_path_str:
        env_path = Path(env_path_str)
        if env_path.is_dir():
            return env_path
        # Env path set but doesn't exist — fall through to fallback (Req 9.4)
        fallback = Path.home() / ".kiro" / "scaffolding"
        if fallback.is_dir():
            print(
                f"[SCAFFOLD WARN] {env_path} not found, using fallback {fallback}",
                file=sys.stderr,
            )
            return fallback
        # Neither env path nor fallback exist — return None (Req 9.3 handled by caller)
        return None

    # 3. Default fallback when no env var is set
    fallback = Path.home() / ".kiro" / "scaffolding"
    if fallback.is_dir():
        return fallback

    return None


def _resolve_project_path(override: Path | None = None) -> Path | None:
    """Resolve the project-level scaffolding library path.

    Returns the path to .kiro/scaffolding/ relative to the workspace root,
    or None if it doesn't exist.
    """
    # 1. Override argument takes priority
    if override is not None and override.is_dir():
        return override

    # 2. Check .kiro/scaffolding/ relative to workspace root
    project_path = _WORKSPACE_ROOT / ".kiro" / "scaffolding"
    if project_path.is_dir():
        return project_path

    return None


def _estimate_tokens(text: str) -> int:
    """Estimate token count for a text string.

    Uses the project convention: len(text) // 4.
    """
    return len(text) // 4


def _parse_template_frontmatter(filepath: Path) -> dict | None:
    """Parse YAML frontmatter from a template file.

    Reads the file and extracts the YAML block between opening and closing
    ``---`` delimiters at the top of the file.

    Returns:
        A dict with keys: name, tags, category, complexity, description, priority.
        Missing optional fields get defaults (complexity="any", priority=0).
        Returns None if frontmatter is completely missing or unparseable.
        Returns a partial dict if some fields are extractable.

    Emits a warning to stderr for malformed YAML including the file path and
    error details.
    """
    try:
        content = filepath.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        print(
            f"[SCAFFOLD WARN] Malformed frontmatter in {filepath}: "
            f"cannot read file: {exc}",
            file=sys.stderr,
        )
        return None

    # Check for opening delimiter
    lines = content.split("\n")
    if not lines or lines[0].strip() != "---":
        # No frontmatter block at all
        return None

    # Find closing delimiter
    closing_idx = None
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            closing_idx = i
            break

    if closing_idx is None:
        # Opening --- but no closing --- — malformed
        print(
            f"[SCAFFOLD WARN] Malformed frontmatter in {filepath}: "
            f"missing closing '---' delimiter",
            file=sys.stderr,
        )
        return None

    yaml_block = "\n".join(lines[1:closing_idx])

    if not yaml_block.strip():
        # Empty frontmatter block
        print(
            f"[SCAFFOLD WARN] Malformed frontmatter in {filepath}: "
            f"empty YAML block",
            file=sys.stderr,
        )
        return None

    try:
        parsed = yaml.safe_load(yaml_block)
    except yaml.YAMLError as exc:
        print(
            f"[SCAFFOLD WARN] Malformed frontmatter in {filepath}: {exc}",
            file=sys.stderr,
        )
        return None

    if not isinstance(parsed, dict):
        print(
            f"[SCAFFOLD WARN] Malformed frontmatter in {filepath}: "
            f"expected mapping, got {type(parsed).__name__}",
            file=sys.stderr,
        )
        return None

    # Extract fields with defaults for optional ones
    result: dict = {}

    if "name" in parsed:
        result["name"] = str(parsed["name"])
    if "tags" in parsed:
        tags_raw = parsed["tags"]
        if isinstance(tags_raw, list):
            result["tags"] = [str(t) for t in tags_raw]
        else:
            result["tags"] = [str(tags_raw)]
    if "category" in parsed:
        result["category"] = str(parsed["category"])
    if "description" in parsed:
        result["description"] = str(parsed["description"])

    # Optional fields with defaults
    complexity_raw = parsed.get("complexity", "any")
    result["complexity"] = str(complexity_raw) if complexity_raw else "any"

    priority_raw = parsed.get("priority", 0)
    try:
        result["priority"] = int(priority_raw)
    except (TypeError, ValueError):
        result["priority"] = 0

    # If we couldn't extract any of the required fields, treat as partial
    # but still return what we have
    if not result:
        return None

    return result


# Supported template file extensions
_SUPPORTED_EXTENSIONS = frozenset({".md", ".py", ".ts", ".js"})


def _apply_overrides(
    shared_templates: list[TemplateInfo],
    project_templates: list[TemplateInfo],
) -> list[TemplateInfo]:
    """Merge shared and project templates with override semantics.

    If a project template has the same ``name`` as a shared template,
    the shared template is excluded. All project templates are always
    included. Shared templates with unique names (not present in the
    project set) are also included.

    Args:
        shared_templates: Templates discovered from the shared library.
        project_templates: Templates discovered from the project library.

    Returns:
        Combined list: filtered shared templates (unique names only)
        followed by all project templates.
    """
    project_names: set[str] = {t.name for t in project_templates}
    filtered_shared = [t for t in shared_templates if t.name not in project_names]
    return filtered_shared + list(project_templates)


def _discover_templates(directory: Path, source: str) -> list[TemplateInfo]:
    """Recursively discover all template files in a directory.

    Walks all subdirectories of *directory*, filtering to files with supported
    extensions (.md, .py, .ts, .js). For each matching file, parses the YAML
    frontmatter and builds a TemplateInfo object.

    Args:
        directory: Root directory to scan (e.g. ~/.kiro/scaffolding/).
        source: Origin label — "shared" or "project".

    Returns:
        List of TemplateInfo objects for all valid template files found.
        Files with completely unparseable frontmatter are skipped (warning
        already emitted by _parse_template_frontmatter).
    """
    templates: list[TemplateInfo] = []

    if not directory.is_dir():
        return templates

    for filepath in sorted(directory.rglob("*")):
        # Skip directories and non-supported extensions
        if not filepath.is_file():
            continue
        if filepath.suffix.lower() not in _SUPPORTED_EXTENSIONS:
            continue

        # Parse frontmatter
        frontmatter = _parse_template_frontmatter(filepath)
        if frontmatter is None:
            # Warning already emitted by _parse_template_frontmatter
            continue

        # Read file content for token estimation
        try:
            content = filepath.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            print(
                f"[SCAFFOLD WARN] Cannot read {filepath} for token estimate: {exc}",
                file=sys.stderr,
            )
            continue

        token_estimate = _estimate_tokens(content)

        # Build TemplateInfo with frontmatter fields + computed fields
        # Use defaults for any missing required fields
        name = frontmatter.get("name", filepath.stem)
        tags = frontmatter.get("tags", [])
        category = frontmatter.get("category", "uncategorized")
        complexity = frontmatter.get("complexity", "any")
        description = frontmatter.get("description", "")
        priority = frontmatter.get("priority", 0)

        template = TemplateInfo(
            name=name,
            path=filepath,
            tags=tags,
            category=category,
            complexity=complexity,
            description=description,
            priority=priority,
            source=source,
            token_estimate=token_estimate,
        )
        templates.append(template)

    return templates


def _rank_candidates(
    candidates: list[TemplateInfo], task_tags: list[str]
) -> list[TemplateInfo]:
    """Rank template candidates based on tag overlap with task tags.

    Filters candidates to only those that have at least one tag overlapping
    with the task tags, then sorts by composite key:
    (-tag_overlap_count, -priority, name)

    Args:
        candidates: List of candidate TemplateInfo objects to rank.
        task_tags: List of tags associated with the current task.

    Returns:
        List of TemplateInfo objects filtered and sorted by tag overlap,
        priority, and name.
    """
    # Convert task_tags to a set for efficient lookup
    task_tags_set = set(task_tags)

    # Filter candidates to only those that have at least one overlapping tag
    filtered_candidates = [
        candidate
        for candidate in candidates
        if len(set(candidate.tags) & task_tags_set) > 0
    ]

    # Sort by composite key: (-tag_overlap_count, -priority, name)
    def sort_key(template: TemplateInfo) -> tuple[int, int, str]:
        tag_overlap_count = len(set(template.tags) & task_tags_set)
        return (-tag_overlap_count, -template.priority, template.name)

    return sorted(filtered_candidates, key=sort_key)


def _filter_by_complexity(
    candidates: list[TemplateInfo], task_complexity: str
) -> list[TemplateInfo]:
    """Filter candidates by complexity compatibility.

    When task_complexity is "any", no filtering is applied (all candidates pass).
    When task_complexity is "simple" or "complex", only templates with matching
    complexity or "any" are kept.

    Args:
        candidates: List of TemplateInfo candidates to filter.
        task_complexity: The task's complexity level ("simple", "complex", or "any").

    Returns:
        Filtered list of TemplateInfo objects.
    """
    if task_complexity == "any":
        return candidates
    return [
        t for t in candidates
        if t.complexity == task_complexity or t.complexity == "any"
    ]


def list_templates(
    tags: list[str] | None = None,
    shared_path: Path | None = None,
    project_path: Path | None = None,
) -> list[TemplateInfo]:
    """List all available templates, optionally filtered by tags.

    Discovers templates from both shared and project directories, applies
    override semantics (project templates with matching names replace shared),
    and optionally filters by tag overlap.

    Unlike ``select_scaffolding``, this function does NOT fatal-error when
    directories are missing — it simply returns whatever is available (or an
    empty list if nothing is found).

    Args:
        tags: If provided and non-empty, only return templates that have at
            least one tag overlapping with the given list. If None, return all.
        shared_path: Override for shared library path resolution.
        project_path: Override for project library path resolution.

    Returns:
        List of TemplateInfo objects after override resolution and optional
        tag filtering.
    """
    # 1. Resolve paths (None means directory doesn't exist — that's fine)
    resolved_shared = _resolve_shared_path(shared_path)
    resolved_project = _resolve_project_path(project_path)

    # 2. Discover templates from each source (skip None, use empty list)
    shared_templates: list[TemplateInfo] = []
    if resolved_shared is not None:
        shared_templates = _discover_templates(resolved_shared, "shared")

    project_templates: list[TemplateInfo] = []
    if resolved_project is not None:
        project_templates = _discover_templates(resolved_project, "project")

    # 3. Apply override semantics (project same-name replaces shared)
    merged = _apply_overrides(shared_templates, project_templates)

    # 4. Filter by tags if provided and non-empty
    if tags is not None and len(tags) > 0:
        tags_set = set(tags)
        merged = [t for t in merged if set(t.tags) & tags_set]

    return merged


def _apply_budget(
    ranked: list[TemplateInfo], budget_tokens: int
) -> list[TemplateInfo]:
    """Greedily include templates until the token budget is exhausted.

    Iterates through the ranked list in order. Includes each template if
    adding its token_estimate keeps the cumulative total <= budget_tokens.
    Stops at the first template that would exceed the budget (no skip-ahead).

    Args:
        ranked: List of TemplateInfo objects in priority order.
        budget_tokens: Maximum token budget for all selected templates.

    Returns:
        List of TemplateInfo objects that fit within the budget, preserving
        input order.
    """
    selected: list[TemplateInfo] = []
    cumulative = 0

    for template in ranked:
        if cumulative + template.token_estimate > budget_tokens:
            break
        selected.append(template)
        cumulative += template.token_estimate

    return selected


def select_scaffolding(
    tags: list[str],
    complexity: str = "any",
    budget_tokens: int = 4000,
    shared_path: Path | None = None,
    project_path: Path | None = None,
) -> list[Path]:
    """Select scaffolding templates matching the given task parameters.

    Resolves shared and project library paths, discovers templates, applies
    override semantics, filters by complexity, ranks by tag overlap, and
    enforces token budget.

    Args:
        tags: Task tags to match against template tags.
        complexity: Task complexity ("simple", "complex", or "any").
        budget_tokens: Maximum token budget for all selected templates combined.
        shared_path: Override for shared library path (default: env or ~/.kiro/scaffolding/).
        project_path: Override for project library path (default: .kiro/scaffolding/).

    Returns:
        Ordered list of Path objects to template files, highest-ranked first.
        Total estimated tokens of returned templates <= budget_tokens.
        Returns empty list silently if no templates match (no error).
    """
    # 1. Resolve paths
    resolved_shared = _resolve_shared_path(shared_path)
    resolved_project = _resolve_project_path(project_path)

    # 2. Handle error/fallback cases per Requirements 9.3, 9.4, 9.5
    if resolved_shared is None and resolved_project is None:
        # Req 9.3: Fatal error — no scaffolding library accessible
        print(
            "[SCAFFOLD ERROR] No scaffolding library found. "
            "Neither shared library (via SCAFFOLDING_LIBRARY_PATH or "
            "~/.kiro/scaffolding/) nor project-level (.kiro/scaffolding/) exist.",
            file=sys.stderr,
        )
        sys.exit(1)

    if resolved_shared is None and resolved_project is not None:
        # Req 9.5: Warn and continue with project-only
        print(
            "[SCAFFOLD WARN] No shared library found, using project-level only",
            file=sys.stderr,
        )

    # 3. Discover templates from both directories (skip None directories)
    shared_templates: list[TemplateInfo] = []
    if resolved_shared is not None:
        shared_templates = _discover_templates(resolved_shared, "shared")

    project_templates: list[TemplateInfo] = []
    if resolved_project is not None:
        project_templates = _discover_templates(resolved_project, "project")

    # 4. Apply override semantics (project overrides shared by name)
    merged = _apply_overrides(shared_templates, project_templates)

    # 5. Filter by complexity
    filtered = _filter_by_complexity(merged, complexity)

    # 6. Rank by tag overlap
    ranked = _rank_candidates(filtered, tags)

    # 7. Apply token budget
    selected = _apply_budget(ranked, budget_tokens)

    # 8. Return just the Path objects (Req 3.5: empty list silently if no match)
    return [t.path for t in selected]
