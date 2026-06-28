"""
Skill Distillation Module

Provides dataclasses, constants, and utilities for the skill distillation
pipeline. The Distiller selects relevant sections from skill files, extracts
actionable rules and code examples, and produces a condensed representation
within a configurable token budget.

This module is importable with no side effects.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_STOP_WORDS: frozenset[str] = frozenset({
    "a", "an", "the", "is", "it", "in", "on", "at", "to", "of",
    "or", "and", "for", "be", "by", "as", "if", "no", "do", "so",
    "up", "he", "she", "we", "my", "me", "us", "am", "are", "was",
    "has", "had", "not", "but", "can", "its", "all", "new", "one",
    "two", "out", "old", "big", "any", "may", "own", "say", "too",
    "use", "her", "him", "his", "how", "man", "our", "way", "who",
    "did", "get", "let", "set", "try", "ask", "few", "got", "run",
    "put", "end", "why", "far", "yet",
})
"""Common English words excluded from keyword matching during relevance scoring."""


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class CodeBlock:
    """A fenced code block within a section."""

    language: str
    content: str
    preceding_text: str  # The bullet/paragraph immediately before this block


@dataclass
class Section:
    """A parsed section from a skill file."""

    heading: str
    body: str
    code_blocks: list[CodeBlock]
    is_preamble: bool = False


@dataclass
class ScoredSection:
    """A section with its computed relevance score."""

    section: Section
    skill_name: str
    raw_score: float
    normalized_score: float  # After per-file normalization


@dataclass
class DistillConfig:
    """Configuration for a distillation run."""

    token_budget: int = 4000
    threshold: float = 0.3
    stop_words: frozenset[str] = field(default_factory=lambda: DEFAULT_STOP_WORDS)


@dataclass
class DistillResult:
    """Output from the distillation process."""

    prompt: str
    tokens_used: int
    tokens_full: int  # What verbatim injection would have cost
    skills_included: int
    sections_included: int
    sections_total: int


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def estimate_tokens(text: str) -> int:
    """Estimate token count using 4 characters per token.

    This matches the existing estimate_tokens function in local_coder.py
    and is used consistently across the system for budget calculations.
    """
    return len(text) // 4


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def _strip_yaml_quotes(value: str) -> str:
    """Remove matching wrapping quotes from a YAML value.

    Only strips quotes if the value starts and ends with the same quote
    character (' or "). This avoids stripping content when the value
    itself is or contains quote characters without matching pairs.
    """
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    return value


def _strip_frontmatter(text: str) -> tuple[str, list[str], str]:
    """Strip YAML frontmatter and extract name + tags.

    Returns (name, tags, remaining_content).
    Frontmatter is the content between opening `---` and closing `---`
    at the start of the file.
    """
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return ("", [], text)

    # Find closing ---
    end_idx = -1
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end_idx = i
            break

    if end_idx == -1:
        # No closing --- found, treat entire content as body
        return ("", [], text)

    # Parse frontmatter with simple string parsing (avoid yaml dependency)
    frontmatter_lines = lines[1:end_idx]
    name = ""
    tags: list[str] = []

    for line in frontmatter_lines:
        stripped = line.strip()
        if stripped.startswith("name:"):
            name = _strip_yaml_quotes(stripped[len("name:"):].strip())
        elif stripped.startswith("tags:"):
            tag_value = stripped[len("tags:"):].strip()
            # Handle [tag1, tag2] format
            if tag_value.startswith("[") and tag_value.endswith("]"):
                inner = tag_value[1:-1]
                tags = [_strip_yaml_quotes(t.strip()) for t in inner.split(",") if t.strip()]
            # Handle bare value (single tag)
            elif tag_value:
                tags = [_strip_yaml_quotes(tag_value)]

    remaining = "\n".join(lines[end_idx + 1:])
    # Strip leading newline from remaining content
    if remaining.startswith("\n"):
        remaining = remaining[1:]

    return (name, tags, remaining)


def _parse_code_blocks(body: str) -> list[CodeBlock]:
    """Parse fenced code blocks from section body text.

    Each code block is associated with the preceding text (the last
    non-empty line or paragraph before the opening fence).
    """
    lines = body.split("\n")
    code_blocks: list[CodeBlock] = []
    i = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if stripped.startswith("```"):
            # Opening fence found
            language = stripped[3:].strip()
            # Find preceding text: walk backward to find last non-empty content
            preceding_text = ""
            for j in range(i - 1, -1, -1):
                if lines[j].strip():
                    preceding_text = lines[j].strip()
                    break

            # Collect code block content
            content_lines: list[str] = []
            i += 1
            while i < len(lines):
                if lines[i].strip().startswith("```"):
                    break
                content_lines.append(lines[i])
                i += 1

            code_blocks.append(CodeBlock(
                language=language,
                content="\n".join(content_lines),
                preceding_text=preceding_text,
            ))
        i += 1

    return code_blocks


def parse_skill_file(path: Path) -> tuple[str, list[str], list[Section]]:
    """Parse a skill file into (name, tags, sections).

    Strips YAML frontmatter, splits on ## headings (outside code fences),
    treats pre-heading content as preamble.
    """
    text = path.read_text(encoding="utf-8")

    # Step 1: Strip frontmatter and extract metadata
    name, tags, content = _strip_frontmatter(text)

    # Step 2: Split on ## headings outside fenced code blocks
    lines = content.split("\n")
    sections: list[Section] = []

    # Track section boundaries: list of (heading, start_line_index)
    # We split on lines starting with "## " that are NOT inside code fences
    in_fence = False
    section_starts: list[tuple[str, int]] = []  # (heading_text, line_index)

    for i, line in enumerate(lines):
        stripped = line.strip()
        # Track fence state
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue

        # Only split on ## headings outside fences
        if not in_fence and line.startswith("## "):
            heading_text = line[3:].strip()
            section_starts.append((heading_text, i))

    # Step 3: Build sections from boundaries
    if not section_starts:
        # No ## headings: entire content is a single preamble section
        body = content.strip()
        code_blocks = _parse_code_blocks(body)
        sections.append(Section(
            heading=name or "Untitled",
            body=body,
            code_blocks=code_blocks,
            is_preamble=True,
        ))
    else:
        # Content before first ## heading is preamble
        first_heading_line = section_starts[0][1]
        preamble_lines = lines[:first_heading_line]
        preamble_body = "\n".join(preamble_lines).strip()

        if preamble_body:
            preamble_code_blocks = _parse_code_blocks(preamble_body)
            sections.append(Section(
                heading=name or "Untitled",
                body=preamble_body,
                code_blocks=preamble_code_blocks,
                is_preamble=True,
            ))

        # Each ## heading starts a section that ends at the next ## heading
        for idx, (heading, start_line) in enumerate(section_starts):
            if idx + 1 < len(section_starts):
                end_line = section_starts[idx + 1][1]
            else:
                end_line = len(lines)

            # Body is everything after the heading line up to next section
            body_lines = lines[start_line + 1:end_line]
            body = "\n".join(body_lines).strip()
            code_blocks = _parse_code_blocks(body)

            sections.append(Section(
                heading=heading,
                body=body,
                code_blocks=code_blocks,
                is_preamble=False,
            ))

    return (name, tags, sections)


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def score_section(task_tokens: set[str], section: Section, stop_words: frozenset[str]) -> float:
    """Compute relevance score for a section against task keywords.

    Score = ratio of shared non-stop words, with 2x multiplier for words in heading.

    Algorithm:
      1. Tokenize section content (heading + body) by whitespace, lowercase all.
      2. Remove stop words to get section_tokens.
      3. Tokenize heading alone by whitespace, lowercase, remove stop words → heading_tokens.
      4. Compute shared = task_tokens ∩ section_tokens.
      5. Weighted numerator: for each shared word, add 2 if in heading_tokens, else 1.
      6. Denominator = total count of non-stop-word tokens in section (heading + body).
      7. Return min(numerator / denominator, 1.0). Return 0.0 if denominator is 0.
    """
    # Combine heading and body text for section tokenization
    full_text = section.heading + " " + section.body

    # Tokenize section content: whitespace-split, lowercase, remove stop words
    section_tokens_list = [w.lower() for w in full_text.split()]
    section_tokens_filtered = [w for w in section_tokens_list if w not in stop_words]

    # Denominator: total non-stop-word tokens in section
    denominator = len(section_tokens_filtered)
    if denominator == 0:
        return 0.0

    # Unique non-stop-word tokens in section (for intersection)
    section_token_set = set(section_tokens_filtered)

    # Heading tokens: whitespace-split, lowercase, remove stop words
    heading_token_set = {w.lower() for w in section.heading.split() if w.lower() not in stop_words}

    # Shared tokens between task and section
    shared = task_tokens & section_token_set

    # Weighted numerator: 2x for words also in heading, 1x otherwise
    numerator = 0
    for word in shared:
        if word in heading_token_set:
            numerator += 2
        else:
            numerator += 1

    score = numerator / denominator
    return min(score, 1.0)


def normalize_scores(scored_sections: list[ScoredSection]) -> list[ScoredSection]:
    """Normalize scores per skill file so highest = 1.0.

    After threshold filtering, normalizes scores within each skill file
    such that the highest-scoring Section receives 1.0 and all others
    are proportionally scaled. Preserves relative ordering.
    """
    # Group sections by skill_name
    groups: dict[str, list[ScoredSection]] = {}
    for ss in scored_sections:
        groups.setdefault(ss.skill_name, []).append(ss)

    # Normalize within each group
    for sections in groups.values():
        max_score = max(ss.raw_score for ss in sections)
        if max_score > 0:
            for ss in sections:
                ss.normalized_score = ss.raw_score / max_score
        else:
            for ss in sections:
                ss.normalized_score = 0.0

    return scored_sections


# ---------------------------------------------------------------------------
# Rule Extraction
# ---------------------------------------------------------------------------

# Common imperative verbs used to detect verb-initial sentences
_IMPERATIVE_VERBS: frozenset[str] = frozenset({
    "use", "add", "create", "return", "check", "ensure", "avoid",
    "implement", "define", "apply", "call", "pass", "set", "run",
    "write", "read", "remove", "delete", "update", "validate",
    "handle", "throw", "raise", "catch", "log", "test", "verify",
    "include", "exclude", "import", "export", "configure", "deploy",
    "build", "install", "enable", "disable", "prefer", "keep",
    "limit", "group", "split", "merge", "wrap", "expose", "hide",
    "override", "extend", "inject", "extract", "transform", "format",
    "parse", "serialize", "deserialize", "encode", "decode", "send",
    "receive", "connect", "disconnect", "initialize", "reset",
    "start", "stop", "retry", "abort", "cancel", "distinguish",
})
"""Known imperative verbs for detecting verb-initial sentences."""

# Imperative keywords that mark a statement as actionable
_IMPERATIVE_KEYWORDS: frozenset[str] = frozenset({
    "shall", "must", "never", "always",
})
"""Keywords that indicate an imperative/mandatory statement."""


_NUMBERED_ITEM_RE = re.compile(r"^\d+\.\s")


def _is_imperative_line(line: str) -> bool:
    """Check if a line is an imperative statement.

    A line is imperative if it contains SHALL/MUST/NEVER/ALWAYS (case-insensitive)
    or starts with a known imperative verb.
    """
    lower = line.lower()

    # Check for imperative keywords anywhere in the line
    for keyword in _IMPERATIVE_KEYWORDS:
        if keyword in lower:
            return True

    # Check if line starts with a known imperative verb
    words = line.split()
    if words:
        first_word = words[0].lower().rstrip(",:;")
        if first_word in _IMPERATIVE_VERBS:
            return True

    return False


def extract_rules(section: Section, task_tokens: set[str]) -> tuple[list[str], list[CodeBlock]]:
    """Extract actionable rules and relevant code examples from a section.

    Extracts: bullet points, numbered items, imperative statements (SHALL/MUST/NEVER/ALWAYS
    or verb-initial sentences), and code blocks whose preceding description shares keywords.

    Args:
        section: The parsed Section to extract rules from.
        task_tokens: Set of lowercase, non-stop-word tokens from the task description.

    Returns:
        Tuple of (rules_list, relevant_code_blocks). Rules are preserved as-is.
        Returns ([], []) if no rules or relevant code blocks are extracted.
    """
    rules: list[str] = []
    relevant_code_blocks: list[CodeBlock] = []

    # Split body into lines, filtering out code block content (handled separately)
    lines = section.body.split("\n")

    # Track which lines are inside code fences so we skip them
    in_fence = False
    for line in lines:
        stripped = line.strip()

        # Track fence boundaries
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue

        # Skip lines inside code fences
        if in_fence:
            continue

        # Skip empty lines
        if not stripped:
            continue

        # Check: bullet point (- or *)
        if stripped.startswith("- ") or stripped.startswith("* "):
            rules.append(stripped)
            continue

        # Check: numbered item (N. )
        if _NUMBERED_ITEM_RE.match(stripped):
            rules.append(stripped)
            continue

        # Check: imperative statement
        if _is_imperative_line(stripped):
            rules.append(stripped)
            continue

        # Otherwise: plain paragraph — omit (adds no new constraints beyond
        # what bullets/numbered items/imperative statements capture)

    # Process code blocks: include those whose preceding_text shares
    # at least one non-stop-word keyword with task_tokens
    for code_block in section.code_blocks:
        preceding_tokens = {
            w.lower() for w in code_block.preceding_text.split()
        } - DEFAULT_STOP_WORDS
        if preceding_tokens & task_tokens:
            relevant_code_blocks.append(code_block)

    return (rules, relevant_code_blocks)


# ---------------------------------------------------------------------------
# Prompt Assembly
# ---------------------------------------------------------------------------

_BUDGET_MIN = 0
_BUDGET_MAX = 16000


def _format_section_text(
    skill_name: str,
    rules: list[str],
    code_blocks: list[CodeBlock],
) -> str:
    """Format a single section's extracted content for inclusion in the prompt.

    Produces markdown bullet points for rules and fenced code blocks for code.
    """
    lines: list[str] = []

    for rule in rules:
        # Normalize to bullet format if not already
        if rule.startswith("- ") or rule.startswith("* "):
            lines.append(f"- {rule[2:]}")
        elif _NUMBERED_ITEM_RE.match(rule):
            # Convert numbered items to bullets for consistency
            # Strip the "N. " prefix
            text = re.sub(r"^\d+\.\s", "", rule)
            lines.append(f"- {text}")
        else:
            # Imperative statement — present as bullet
            lines.append(f"- {rule}")

    for cb in code_blocks:
        lines.append("")
        lines.append(f"```{cb.language}")
        lines.append(cb.content)
        lines.append("```")

    return "\n".join(lines)


def assemble_prompt(
    scored_sections: list[ScoredSection],
    config: DistillConfig,
    always_sections: list[tuple[str, Section]],
) -> tuple[str, int]:
    """Build the final distilled prompt within the token budget.

    Selects sections greedily by descending relevance score, respecting the
    token budget. "Always"-tagged sections are included first (within budget).

    Args:
        scored_sections: Sections with normalized scores (already threshold-filtered).
        config: Distillation configuration including token_budget.
        always_sections: List of (skill_name, section) tuples for "always"-tagged skills.

    Returns:
        Tuple of (prompt_text, tokens_used). prompt_text is the assembled
        formatted output ready for injection. tokens_used is the estimated
        token count of the output.
    """
    # Step 1: Clamp budget to [0, 16000]
    original_budget = config.token_budget
    budget = max(_BUDGET_MIN, min(_BUDGET_MAX, original_budget))
    if budget != original_budget:
        print(
            f"[DISTILL] WARNING: token_budget {original_budget} out of range, "
            f"clamped to {budget} (valid range: [{_BUDGET_MIN}, {_BUDGET_MAX}])",
            file=sys.stderr,
        )

    # Step 2: Handle zero budget
    if budget == 0:
        print(
            "[DISTILL] WARNING: token_budget is 0 — skill guidance is disabled",
            file=sys.stderr,
        )
        return ("", 0)

    # Step 3: Include "always"-tagged sections first (within budget, original order)
    output_parts: list[tuple[str, str]] = []  # (skill_name, formatted_text)
    tokens_used = 0
    included_skills: set[str] = set()
    omitted_always: list[str] = []

    for skill_name, section in always_sections:
        # Extract rules from always section
        # Use empty task_tokens since always sections are included regardless
        rules, code_blocks = extract_rules(section, set())
        # For always sections, include all code blocks regardless of keyword match
        if not rules and not section.code_blocks:
            # If extraction produces nothing useful, include body lines as-is
            rules = [
                line.strip()
                for line in section.body.split("\n")
                if line.strip() and not line.strip().startswith("```")
            ]

        # If still nothing, use all code blocks from the section
        all_code_blocks = code_blocks if code_blocks else section.code_blocks

        formatted = _format_section_text(skill_name, rules, all_code_blocks)

        # Account for skill heading overhead if this is the first section for this skill
        heading_overhead = 0
        if skill_name not in included_skills:
            # Heading line + newline after block separator
            heading_line = f"### {skill_name.upper()}\n"
            heading_overhead = estimate_tokens(heading_line)
            # Add 1 token for the blank separator line between skill blocks
            if output_parts:
                heading_overhead += 1

        section_tokens = estimate_tokens(formatted) + heading_overhead

        if tokens_used + section_tokens <= budget:
            output_parts.append((skill_name, formatted))
            tokens_used += section_tokens
            included_skills.add(skill_name)
        else:
            omitted_always.append(f"{skill_name}::{section.heading}")

    if omitted_always:
        print(
            f"[DISTILL] WARNING: Budget insufficient for always-tagged sections. "
            f"Omitted: {', '.join(omitted_always)}",
            file=sys.stderr,
        )

    # Step 4: Sort remaining scored_sections by normalized_score descending
    # Tie-breaking: prefer skill with higher max section score, then alphabetical
    # Compute max score per skill for tie-breaking
    skill_max_scores: dict[str, float] = {}
    for ss in scored_sections:
        current_max = skill_max_scores.get(ss.skill_name, 0.0)
        if ss.normalized_score > current_max:
            skill_max_scores[ss.skill_name] = ss.normalized_score

    def sort_key(ss: ScoredSection) -> tuple[float, float, str]:
        """Sort key: (-score, -skill_max_score, skill_name alphabetical)."""
        return (
            -ss.normalized_score,
            -skill_max_scores.get(ss.skill_name, 0.0),
            ss.skill_name,
        )

    sorted_sections = sorted(scored_sections, key=sort_key)

    # Step 5: Greedily add sections until budget is exhausted
    # Use a set to track task_tokens for extract_rules (derive from scored sections)
    # Since we don't have task_tokens here, we pass empty set — rules were pre-qualified
    # by threshold filtering. We include all extractable rules.
    for ss in sorted_sections:
        rules, code_blocks = extract_rules(ss.section, set())

        # For scored sections, also include all code blocks (they passed threshold)
        all_code_blocks = code_blocks if code_blocks else ss.section.code_blocks

        # If extraction produces no rules AND no code blocks, skip
        if not rules and not all_code_blocks:
            print(
                f"[DISTILL] Omitting section '{ss.section.heading}' from "
                f"'{ss.skill_name}': no extractable rules or code",
                file=sys.stderr,
            )
            continue

        formatted = _format_section_text(ss.skill_name, rules, all_code_blocks)

        # Account for skill heading overhead if this is the first section for this skill
        heading_overhead = 0
        if ss.skill_name not in included_skills:
            heading_line = f"### {ss.skill_name.upper()}\n"
            heading_overhead = estimate_tokens(heading_line)
            # Add 1 token for the blank separator line between skill blocks
            if output_parts:
                heading_overhead += 1

        section_tokens = estimate_tokens(formatted) + heading_overhead

        # If adding this section would exceed budget, stop
        if tokens_used + section_tokens > budget:
            break

        output_parts.append((ss.skill_name, formatted))
        tokens_used += section_tokens
        included_skills.add(ss.skill_name)

    # Step 6: Assemble final text, ensuring it fits within budget
    # Group parts by skill name, preserving section insertion order within each skill
    # The greedy loop's token tracking may slightly under-count due to join/separator
    # overhead. We verify the assembled result and drop sections if needed.

    # Order skill blocks by their highest section's normalized_score descending.
    # For always-tagged skills that have no scored sections, use score 2.0
    # (higher than any normalized score) so they appear first.
    # Tie-breaking: skill name alphabetical ascending.
    def skill_block_sort_key(skill_name: str) -> tuple[float, str]:
        max_score = skill_max_scores.get(skill_name, 2.0)  # 2.0 for always-only
        return (-max_score, skill_name)

    def _assemble_from_parts(parts: list[tuple[str, str]]) -> str:
        """Assemble final text from (skill_name, formatted_text) parts."""
        blocks: dict[str, list[str]] = {}
        for sn, txt in parts:
            blocks.setdefault(sn, []).append(txt)

        sorted_names = sorted(blocks.keys(), key=skill_block_sort_key)

        lines: list[str] = []
        for sn in sorted_names:
            sn_blocks = blocks[sn]
            lines.append(f"### {sn.upper()}")
            for blk in sn_blocks:
                lines.append(blk)
            lines.append("")  # Blank line between skill blocks

        return "\n".join(lines).rstrip("\n")

    assembled = _assemble_from_parts(output_parts)
    actual_tokens = estimate_tokens(assembled)

    # If assembly overhead pushes over budget, drop last-added sections until within
    while actual_tokens > budget and output_parts:
        output_parts.pop()
        assembled = _assemble_from_parts(output_parts)
        actual_tokens = estimate_tokens(assembled)

    return (assembled, actual_tokens)


# ---------------------------------------------------------------------------
# Main Entry Point
# ---------------------------------------------------------------------------

def distill(
    task_description: str,
    skill_paths: list[Path],
    config: DistillConfig = DistillConfig(),
) -> DistillResult:
    """Main entry point. Produces a distilled prompt from skill files for a given task.

    Parses skill files, scores sections against task, filters by threshold,
    extracts rules, assembles within token budget, and formats the output.

    Never raises — always returns a result (even if empty).
    """
    # Step 1: Pre-process task tokens
    task_tokens: set[str] = {
        w.lower()
        for w in task_description.split()
        if w.lower() not in config.stop_words
    }

    # Step 2: Parse each skill file, track metadata
    parsed_skills: list[tuple[str, list[str], list[Section], Path]] = []
    # (name, tags, sections, path)
    tokens_full = 0
    sections_total = 0

    for path in skill_paths:
        try:
            raw_text = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            print(
                f"[DISTILL] WARNING: Skill file not found: {path}",
                file=sys.stderr,
            )
            continue
        except (UnicodeDecodeError, IOError):
            print(
                f"[DISTILL] WARNING: Could not read skill file: {path}",
                file=sys.stderr,
            )
            continue

        # Compute full verbatim token cost for this file
        tokens_full += estimate_tokens(raw_text)

        try:
            name, tags, sections = parse_skill_file(path)
        except Exception:
            print(
                f"[DISTILL] WARNING: Could not read skill file: {path}",
                file=sys.stderr,
            )
            continue

        sections_total += len(sections)
        parsed_skills.append((name, tags, sections, path))

    # Step 3: Identify "always"-tagged skills and collect their core sections
    always_sections: list[tuple[str, Section]] = []
    always_skill_names: set[str] = set()

    for name, tags, sections, _path in parsed_skills:
        if "always" in tags:
            always_skill_names.add(name)
            # The "always" section is the first ## section (first non-preamble),
            # or preamble if no ## sections exist
            core_section: Section | None = None
            for sec in sections:
                if not sec.is_preamble:
                    core_section = sec
                    break
            # If no non-preamble section found, use preamble
            if core_section is None and sections:
                core_section = sections[0]
            if core_section is not None:
                always_sections.append((name, core_section))

    # Step 4: Score all sections against task tokens
    all_scored: list[ScoredSection] = []
    # Track scores per skill for threshold-based exclusion
    skill_section_scores: dict[str, list[tuple[Section, float]]] = {}

    for name, tags, sections, _path in parsed_skills:
        skill_scores: list[tuple[Section, float]] = []
        for section in sections:
            raw_score = score_section(task_tokens, section, config.stop_words)
            skill_scores.append((section, raw_score))
        skill_section_scores[name] = skill_scores

    # Step 5: Filter by threshold and determine which skills/sections qualify
    # For "always" skills: always sections are handled separately (included regardless)
    # but their other sections still compete on score
    qualifying_scored: list[ScoredSection] = []

    for name, tags, sections, _path in parsed_skills:
        scores = skill_section_scores[name]
        is_always = "always" in tags

        # Check if ANY section passes threshold (for non-always exclusion)
        any_above_threshold = any(score >= config.threshold for _, score in scores)

        if not is_always and not any_above_threshold:
            # Req 1.5: Exclude entire skill if all sections below threshold
            continue

        # Add qualifying sections (those above threshold)
        for section, raw_score in scores:
            if raw_score >= config.threshold:
                # Skip the always-core section from scored list (it's handled separately)
                if is_always:
                    # Check if this is the core always section
                    is_core = False
                    for always_name, always_sec in always_sections:
                        if always_name == name and always_sec is section:
                            is_core = True
                            break
                    if is_core:
                        continue

                qualifying_scored.append(ScoredSection(
                    section=section,
                    skill_name=name,
                    raw_score=raw_score,
                    normalized_score=0.0,
                ))

    # Step 6: Normalize scores among remaining sections
    normalize_scores(qualifying_scored)

    # Step 7: Extract rules and check for omissions
    # Filter out sections that produce no extractable rules
    final_scored: list[ScoredSection] = []
    for ss in qualifying_scored:
        rules, code_blocks = extract_rules(ss.section, task_tokens)
        if not rules and not code_blocks and not ss.section.code_blocks:
            # Req 2.7: log omission when sections produce no rules
            print(
                f"[DISTILL] Omitting section '{ss.section.heading}' from "
                f"'{ss.skill_name}': no extractable rules or code",
                file=sys.stderr,
            )
            continue
        final_scored.append(ss)

    # Step 8: Assemble within budget
    # Check for zero-budget early — assemble_prompt handles it but we need
    # to produce an empty prompt per Req 3.6
    effective_budget = max(_BUDGET_MIN, min(_BUDGET_MAX, config.token_budget))
    if effective_budget == 0:
        # assemble_prompt will emit the zero-budget warning
        assemble_prompt(final_scored, config, always_sections)
        # Report to stderr
        print(
            f"[DISTILL] 0/0 tokens used (0%)",
            file=sys.stderr,
        )
        return DistillResult(
            prompt="",
            tokens_used=0,
            tokens_full=tokens_full,
            skills_included=0,
            sections_included=0,
            sections_total=sections_total,
        )

    assembled_text, assembled_tokens = assemble_prompt(
        final_scored, config, always_sections
    )

    # Step 9: Format the final output
    skills_included_set: set[str] = set()
    for ss in final_scored:
        skills_included_set.add(ss.skill_name)
    for name, _ in always_sections:
        skills_included_set.add(name)

    # Count how many sections ended up in the assembled output
    # (approximate from assembled text — count sections by checking assemble)
    sections_included = 0
    for ss in final_scored:
        # Check if this section could fit (it was passed to assemble_prompt)
        sections_included += 1
    sections_included += len(always_sections)

    # Determine actual skills included by checking assembled text
    skills_in_output: set[str] = set()
    if assembled_text:
        for name in skills_included_set:
            if f"### {name.upper()}" in assembled_text:
                skills_in_output.add(name)
    else:
        skills_in_output = set()

    # Build final formatted output
    output_lines: list[str] = []
    output_lines.append("## SKILLS (Distilled for this task)")
    output_lines.append("")

    if assembled_text:
        output_lines.append(assembled_text)
    else:
        # No content at all
        pass

    # Check if any task-specific skills matched (non-always)
    task_specific_matched = any(
        name not in always_skill_names for name in skills_in_output
    )

    if not task_specific_matched and skills_in_output:
        # Only always-tagged content present
        output_lines.append("")
        output_lines.append("<!-- no task-specific skills matched threshold -->")

    # Compute reduction percentage
    if tokens_full > 0:
        reduction_pct = round(((tokens_full - assembled_tokens) / tokens_full) * 100)
    else:
        reduction_pct = 0

    # Append summary comment (Req 6.4)
    num_skills = len(skills_in_output)
    output_lines.append("")
    output_lines.append(
        f"<!-- distilled: {assembled_tokens} tokens from "
        f"{num_skills} skills, {reduction_pct}% reduction -->"
    )

    final_prompt = "\n".join(output_lines)
    final_tokens = estimate_tokens(final_prompt)

    # Step 10: Report token usage to stderr (Req 3.7)
    budget = max(_BUDGET_MIN, min(_BUDGET_MAX, config.token_budget))
    if budget > 0:
        percentage = round((final_tokens / budget) * 100)
    else:
        percentage = 0
    print(
        f"[DISTILL] {final_tokens}/{budget} tokens used ({percentage}%)",
        file=sys.stderr,
    )

    # Step 11: Return DistillResult
    return DistillResult(
        prompt=final_prompt,
        tokens_used=final_tokens,
        tokens_full=tokens_full,
        skills_included=num_skills,
        sections_included=sections_included,
        sections_total=sections_total,
    )


# ---------------------------------------------------------------------------
# Output Formatting
# ---------------------------------------------------------------------------


def format_distilled_output(
    assembled_body: str,
    tokens_full: int,
    skills_count: int,
    had_task_specific_matches: bool,
) -> str:
    """Add header, summary comment, and finalize the distilled output.

    Wraps the assembled body from `assemble_prompt` with:
    1. The "## SKILLS (Distilled for this task)" header
    2. The summary HTML comment with token count, skills count, and reduction %
    3. A "no task-specific skills matched" note when applicable

    Args:
        assembled_body: The formatted skill content from assemble_prompt.
        tokens_full: Token count of full verbatim injection (for reduction calc).
        skills_count: Number of skill files included in the output.
        had_task_specific_matches: Whether any non-always skills matched the threshold.
            When False, appends the "no task-specific skills matched" note.

    Returns:
        The complete formatted distilled output string ready for injection.
        Returns empty string if assembled_body is empty.
    """
    # Handle empty case (e.g., zero budget produced no content)
    if not assembled_body.strip():
        return ""

    # Build the full output with header
    header = "## SKILLS (Distilled for this task)"
    parts: list[str] = [header, "", assembled_body]

    # Add "no task-specific skills matched" note if applicable
    if not had_task_specific_matches:
        parts.append("")
        parts.append("<!-- no task-specific skills matched threshold -->")

    # Assemble text so far to compute the token count for the summary comment
    # We need to include the summary comment itself in the token count (N),
    # so we estimate the comment size and include it.
    text_before_comment = "\n".join(parts)

    # Compute reduction percentage
    if tokens_full > 0:
        # Estimate the final token count including the comment itself.
        # The comment format is: <!-- distilled: {N} tokens from {M} skills, {P}% reduction -->
        # We compute an estimate, then adjust if needed.
        # First pass: estimate tokens of text_before_comment + approximate comment size
        approx_comment = f"<!-- distilled: 9999 tokens from {skills_count} skills, 99% reduction -->"
        approx_full = text_before_comment + "\n\n" + approx_comment
        estimated_n = estimate_tokens(approx_full)

        # Compute percentage reduction
        reduction_pct = round(((tokens_full - estimated_n) / tokens_full) * 100)

        # Build actual comment with the computed values
        comment = f"<!-- distilled: {estimated_n} tokens from {skills_count} skills, {reduction_pct}% reduction -->"

        # Rebuild with actual comment and recompute token count for accuracy
        final_text = text_before_comment + "\n\n" + comment
        actual_n = estimate_tokens(final_text)

        # If actual differs from estimated (due to digit count changes), recalculate
        if actual_n != estimated_n:
            reduction_pct = round(((tokens_full - actual_n) / tokens_full) * 100)
            comment = f"<!-- distilled: {actual_n} tokens from {skills_count} skills, {reduction_pct}% reduction -->"
            final_text = text_before_comment + "\n\n" + comment
    else:
        # tokens_full is 0 — no reduction possible
        n = estimate_tokens(text_before_comment + "\n\n<!-- distilled: 0 tokens from 0 skills, 0% reduction -->")
        comment = f"<!-- distilled: {n} tokens from {skills_count} skills, 0% reduction -->"
        final_text = text_before_comment + "\n\n" + comment

    return final_text
