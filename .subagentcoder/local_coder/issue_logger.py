"""Issue logger for recording local coder execution outcomes.

Writes structured issue records to docs/local-coder-issues.txt and maintains
running summary statistics for delegation heuristic evaluation.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal


@dataclass
class IssueRecord:
    """A single execution outcome record.

    All string fields are subject to length constraints enforced at write time:
    - task_description: max 200 characters
    - quality_notes: max 500 characters
    - issues_found: max 10 items
    """

    date: str
    """ISO 8601 date-time string."""

    task_description: str
    """Brief description of the task. Max 200 characters."""

    model_used: str
    """Name of the model used for generation."""

    result: Literal["success", "fail"]
    """Outcome of the execution."""

    tokens_generated: int | None
    """Number of tokens generated, or None if unavailable (rendered as 'N/A')."""

    generation_speed: float | None
    """Generation speed in tok/s, or None if unavailable (rendered as 'N/A')."""

    quality_notes: str
    """Free-text quality observations. Max 500 characters."""

    issues_found: list[str] = field(default_factory=list)
    """List of issue categories encountered. Max 10 items."""

    complexity_tier: Literal["simple", "complex", "prose"] = "simple"
    """Complexity classification of the task."""

    review_iterations: int = 0
    """Number of review-fix iterations. 0 if no review was needed."""


class IssueLogWriteError(Exception):
    """Raised when writing to the issue log file fails.

    Preserves the IssueRecord data so the caller can retry or handle
    the record without data loss.
    """

    def __init__(self, reason: str, record: IssueRecord) -> None:
        super().__init__(reason)
        self.reason = reason
        self.record = record


class IssueLogger:
    """Writes structured issue records and maintains summary statistics.

    The log file is located at ``<project_root>/docs/local-coder-issues.txt``.
    """

    # Field order as defined in Requirement 3.1
    _FIELD_ORDER = (
        "date",
        "task_description",
        "model_used",
        "result",
        "tokens",
        "quality_notes",
        "issues_found",
        "complexity_tier",
        "review_iterations",
    )

    def __init__(self, project_root: Path) -> None:
        self.log_path = project_root / "docs" / "local-coder-issues.txt"

    @staticmethod
    def _sanitize_line(value: str) -> str:
        """Remove control characters that would break single-line key-value format.

        Strips all C0/C1 control characters (U+0000-U+001F, U+007F-U+009F)
        and Unicode line/paragraph separators (U+2028, U+2029).
        Replaces them with a space to preserve word boundaries.
        """
        return re.sub(r"[\x00-\x1f\x7f-\x9f\u2028\u2029]", " ", value)

    @staticmethod
    def format_tokens_field(tokens_generated: int | None, generation_speed: float | None) -> str:
        """Format the combined Tokens field as '{count} tokens in {duration}s'.

        Requirement 4.6: The field must never be empty. If no token data is
        available, uses the fallback '0 tokens in 0s'.
        """
        if tokens_generated is None or tokens_generated <= 0:
            return "0 tokens in 0s"

        if generation_speed is not None and generation_speed > 0:
            duration = tokens_generated / generation_speed
            # Format duration: use 1 decimal place
            return f"{tokens_generated} tokens in {duration:.1f}s"
        else:
            # Have token count but no speed/duration info
            return f"{tokens_generated} tokens in 0s"

    def _serialize_record(self, record: IssueRecord) -> str:
        """Serialize a record to markdown format.

        Applies truncation rules:
        - task_description: max 200 characters
        - issues_found: max 10 items

        The 'tokens' field renders in the format '{count} tokens in {duration}s'
        and is never empty (Requirement 4.6).

        Returns the serialized markdown block as a string.
        """
        lines: list[str] = []

        for field_name in self._FIELD_ORDER:
            if field_name == "tokens":
                # Combined field: '{count} tokens in {duration}s' (Req 4.6)
                rendered = self.format_tokens_field(
                    record.tokens_generated, record.generation_speed
                )
                lines.append(f"- **{field_name}:** {rendered}")
                continue

            value = getattr(record, field_name)

            if field_name == "task_description":
                # Truncate to 200 chars, sanitize line-breaking characters
                value = self._sanitize_line(value[:200])
                lines.append(f"- **{field_name}:** {value}")

            elif field_name == "issues_found":
                # Truncate to first 10 items
                items = value[:10]
                if not items:
                    # Empty list: field line with no value, no sub-items
                    lines.append(f"- **{field_name}:**")
                else:
                    # Non-empty list: field line with no value, then sub-items
                    lines.append(f"- **{field_name}:**")
                    for item in items:
                        lines.append(f"  - {self._sanitize_line(item)}")

            else:
                # All other fields: direct value rendering
                rendered = self._sanitize_line(str(value)) if isinstance(value, str) else str(value)
                lines.append(f"- **{field_name}:** {rendered}")

        return "\n".join(lines)

    def _parse_record(self, text: str) -> IssueRecord:
        """Parse a markdown record back into an IssueRecord.

        Expects text in the format produced by _serialize_record:
        - **field_name:** value
        With list fields having sub-items indented as:
          - item

        Handles both the new combined 'tokens' field format
        ('{count} tokens in {duration}s') and legacy separate
        'tokens_generated'/'generation_speed' fields.

        Returns a fully populated IssueRecord.
        """
        fields: dict[str, str | list[str]] = {}
        current_field: str | None = None
        current_list: list[str] | None = None

        # Pattern for field lines: - **field_name:** optional_value
        field_pattern = re.compile(r"^- \*\*(\w+):\*\*(.*)$")
        # Pattern for sub-list items:   - item
        subitem_pattern = re.compile(r"^  - (.+)$")

        for line in text.split("\n"):
            field_match = field_pattern.match(line)
            if field_match:
                # Save any previously accumulated list
                if current_field is not None and current_list is not None:
                    fields[current_field] = current_list

                field_name = field_match.group(1)
                field_value = field_match.group(2).strip()

                if field_name == "issues_found":
                    # Start accumulating list items
                    current_field = field_name
                    current_list = []
                    # If there's a value on the same line (shouldn't happen
                    # per format, but handle gracefully)
                    if field_value:
                        current_list.append(field_value)
                else:
                    # Scalar field
                    current_field = None
                    current_list = None
                    fields[field_name] = field_value
            else:
                subitem_match = subitem_pattern.match(line)
                if subitem_match and current_list is not None:
                    current_list.append(subitem_match.group(1))

        # Save final accumulated list if any
        if current_field is not None and current_list is not None:
            fields[current_field] = current_list

        # Parse token info — handle both new 'tokens' format and legacy fields
        tokens_generated: int | None = None
        generation_speed: float | None = None

        tokens_raw = fields.get("tokens", "")
        if isinstance(tokens_raw, str) and tokens_raw:
            # Parse '{count} tokens in {duration}s' format
            tokens_match = re.match(
                r"(\d+)\s+tokens?\s+in\s+(\d+(?:\.\d+)?)s", tokens_raw
            )
            if tokens_match:
                count = int(tokens_match.group(1))
                duration = float(tokens_match.group(2))
                tokens_generated = count if count > 0 else None
                if tokens_generated and duration > 0:
                    generation_speed = tokens_generated / duration
        else:
            # Legacy format: separate tokens_generated and generation_speed fields
            tg_raw = fields.get("tokens_generated", "N/A")
            if isinstance(tg_raw, str) and tg_raw != "N/A":
                try:
                    tokens_generated = int(tg_raw)
                except ValueError:
                    pass

            speed_raw = fields.get("generation_speed", "N/A")
            if isinstance(speed_raw, str) and speed_raw != "N/A":
                try:
                    generation_speed = float(speed_raw)
                except ValueError:
                    pass

        # Parse issues_found: list field
        issues_raw = fields.get("issues_found", [])
        issues_found: list[str] = issues_raw if isinstance(issues_raw, list) else []

        # Parse review_iterations: int
        review_iterations = int(fields.get("review_iterations", "0"))  # type: ignore[arg-type]

        return IssueRecord(
            date=str(fields.get("date", "")),
            task_description=str(fields.get("task_description", "")),
            model_used=str(fields.get("model_used", "")),
            result=str(fields.get("result", "fail")),  # type: ignore[arg-type]
            tokens_generated=tokens_generated,
            generation_speed=generation_speed,
            quality_notes=str(fields.get("quality_notes", "")),
            issues_found=issues_found,
            complexity_tier=str(fields.get("complexity_tier", "simple")),  # type: ignore[arg-type]
            review_iterations=review_iterations,
        )

    def _parse_all_records(self, content: str) -> list[IssueRecord]:
        """Parse ALL existing records from file content.

        Splits content on the ``\\n\\n---\\n\\n`` separator and parses each block
        that contains record fields. Skips the heading and summary sections.
        """
        records: list[IssueRecord] = []
        # Split on the record separator
        blocks = content.split("\n\n---\n\n")

        for block in blocks:
            block = block.strip()
            # Skip empty blocks, heading-only blocks, and summary sections
            if not block:
                continue
            # A valid record block contains field lines like "- **field_name:**"
            if "- **date:**" in block:
                try:
                    records.append(self._parse_record(block))
                except (ValueError, KeyError):
                    # Skip malformed records
                    continue
        return records

    def _calculate_tier_rate(
        self, records: list[IssueRecord], tier: str
    ) -> tuple[int, int, float]:
        """Calculate success rate using most recent 20 records for the tier.

        Returns (successes, total, percentage).
        """
        tier_records = [r for r in records if r.complexity_tier == tier]
        # Use most recent 20
        recent = tier_records[-20:]
        if not recent:
            return (0, 0, 0.0)
        successes = sum(1 for r in recent if r.result == "success")
        total = len(recent)
        percentage = (successes / total) * 100
        return (successes, total, percentage)

    def _get_top_issues(
        self, records: list[IssueRecord], limit: int = 5
    ) -> list[tuple[str, int]]:
        """Get top N most frequent issue categories from failed records."""
        counter: Counter[str] = Counter()
        for r in records:
            if r.result == "fail":
                for issue in r.issues_found:
                    counter[issue] += 1
        return counter.most_common(limit)

    def _evaluate_warnings(self, records: list[IssueRecord]) -> list[str]:
        """Generate warning notes for tiers below 70% threshold.

        Only evaluates tiers with 10+ records. Returns a list of warning
        strings for tiers that are below the threshold.
        """
        warnings: list[str] = []
        for tier in ("simple", "complex", "prose"):
            tier_records = [r for r in records if r.complexity_tier == tier]
            recent_10 = tier_records[-10:]
            if len(recent_10) < 10:
                continue  # insufficient data, no threshold evaluation
            successes = sum(1 for r in recent_10 if r.result == "success")
            rate = (successes / 10) * 100
            if rate < 70:
                now = datetime.now().isoformat(timespec="seconds")
                warnings.append(
                    f"⚠️ WARNING ({tier}): Below 70% threshold "
                    f"({successes}/10 = {rate:.0f}%) "
                    f"— consider excluding from auto-delegation (generated {now})"
                )
        return warnings

    def _update_summary(self, all_records: list[IssueRecord]) -> str:
        """Recalculate and return the summary section content."""
        lines = ["## Process Improvements Needed", ""]

        for tier in ("simple", "complex", "prose"):
            successes, total, pct = self._calculate_tier_rate(all_records, tier)
            if total == 0:
                lines.append(f"- **{tier}:** 0/0 (0%) — insufficient data")
                continue

            rate_str = f"{successes}/{total} ({pct:.0f}%)"
            tier_records = [r for r in all_records if r.complexity_tier == tier]

            if len(tier_records) < 10:
                lines.append(f"- **{tier}:** {rate_str} — insufficient data")
            else:
                # Evaluate warning threshold using last 10
                recent_10 = tier_records[-10:]
                recent_successes = sum(
                    1 for r in recent_10 if r.result == "success"
                )
                recent_rate = (recent_successes / 10) * 100
                if recent_rate < 70:
                    now = datetime.now().isoformat(timespec="seconds")
                    lines.append(
                        f"- **{tier}:** {rate_str} ⚠️ WARNING: Below 70% threshold "
                        f"— consider excluding from auto-delegation (generated {now})"
                    )
                else:
                    lines.append(f"- **{tier}:** {rate_str}")

        # Top issues
        top_issues = self._get_top_issues(all_records)
        if top_issues:
            lines.append("")
            lines.append("### Top Issue Categories")
            for i, (category, count) in enumerate(top_issues, 1):
                lines.append(f"{i}. {category} ({count})")

        return "\n".join(lines)

    def _ensure_log_file(self) -> None:
        """Create the log file with heading if it doesn't exist.

        Creates the ``docs/`` directory if missing (Req 6.7).
        Creates the log file with '# Local Coder Issues & Successes Log'
        heading if missing (Req 3.6).
        """
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.log_path.exists():
            self.log_path.write_text(
                "# Local Coder Issues & Successes Log\n",
                encoding="utf-8",
                newline="",  # Force LF line endings on all platforms
            )

    def log_execution(self, record: IssueRecord) -> None:
        """Append a record to the log file and update the summary.

        Preserves all existing content (Req 3.5) and appends the new record
        separated by ``\\n\\n---\\n\\n`` (Req 6.3). Uses UTF-8 encoding without
        BOM and LF line endings (Req 6.2). Recalculates the summary section
        on every write (Req 5.1).

        Raises:
            IssueLogWriteError: If the file write fails. The record data is
                preserved in the exception for retry.
        """
        try:
            self._ensure_log_file()
            serialized = self._serialize_record(record)

            # Read existing content (Req 3.5: preserve all existing content)
            content = self.log_path.read_text(encoding="utf-8")

            # Separate heading from the rest
            heading = "# Local Coder Issues & Successes Log"

            # Strip existing summary section if present
            # The summary section starts with "## Process Improvements Needed"
            # and ends before the first record separator or end of non-record content
            records_content = self._strip_summary(content, heading)

            # Append new record with separator (Req 6.3)
            if records_content.rstrip():
                records_content = (
                    records_content.rstrip() + "\n\n---\n\n" + serialized + "\n"
                )
            else:
                records_content = serialized + "\n"

            # Parse all records to compute summary
            all_records = self._parse_all_records(records_content)
            summary = self._update_summary(all_records)

            # Rebuild file: heading + summary + records
            final_content = heading + "\n\n" + summary + "\n\n---\n\n" + records_content

            # Write back with LF line endings (newline="" prevents \n → \r\n
            # on Windows) (Req 6.2)
            with open(self.log_path, "w", encoding="utf-8", newline="") as f:
                f.write(final_content)
        except OSError as e:
            raise IssueLogWriteError(reason=str(e), record=record) from e

    def _strip_summary(self, content: str, heading: str) -> str:
        """Remove the heading and summary section from file content.

        Returns only the records portion of the file (everything after the
        summary section).
        """
        # Remove the heading line
        content = content.replace(heading, "", 1).lstrip("\n")

        # Check if there's a summary section to strip
        summary_marker = "## Process Improvements Needed"
        if content.startswith(summary_marker):
            # Find the first record separator after the summary
            sep_idx = content.find("\n\n---\n\n")
            if sep_idx != -1:
                # Skip past the separator to get to the records
                content = content[sep_idx + len("\n\n---\n\n"):]
            else:
                # No records yet, just the summary
                content = ""

        return content
