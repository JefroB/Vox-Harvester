"""
Local Coder - Ollama Subagent Orchestrator

Sends coding tasks to a local Ollama model with relevant skill context.
Designed to be called by Kiro (who selects the skills) or directly from CLI.

Usage:
    # Kiro calls with explicit skill selection:
    python local_coder.py --task "Build a REST API handler" --skills software-engineering api-design security error-handling

    # Include all skills:
    python local_coder.py --task "Refactor the config loader" --all-skills

    # Output to file:
    python local_coder.py --task "Write a parser" --skills software-engineering --output src/parser.py

    # With extra context (existing code to reference):
    python local_coder.py --task "Add error handling to this function" --context src/utils.py --skills software-engineering error-handling
"""

import argparse
import json
import os
import re
import sys
import uuid
import requests
from datetime import datetime, timezone
from pathlib import Path

# Ensure .subagentcoder/ is importable for local_coder package
WORKSPACE_ROOT = Path(__file__).parent.parent.parent
_INTERNAL_DIR = WORKSPACE_ROOT / ".subagentcoder"
_INTERNAL_DIR_STR = str(_INTERNAL_DIR)
if _INTERNAL_DIR_STR not in sys.path:
    sys.path.insert(0, _INTERNAL_DIR_STR)

from local_coder.token_tracker import SessionTracker, display_stats
from local_coder.two_pass_router import detect_two_pass, format_routing_log
from local_coder.two_pass import execute_two_pass
from local_coder.complexity_estimator import estimate_complexity
from local_coder.file_tagger import tag_files
from local_coder.result_database import TaskResult, ResultDatabase

# --- Configuration ---
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
DEFAULT_MODEL = os.environ.get("OLLAMA_MODEL", "qwen3-coder:30b-a3b-q4_K_M")
FAST_MODEL = os.environ.get("OLLAMA_FAST_MODEL", "qwen2.5-coder:7b")
HEAVY_MODEL = os.environ.get("OLLAMA_HEAVY_MODEL", "qwen3-coder:30b-a3b-q4_K_M")
PROSE_MODEL = os.environ.get("OLLAMA_PROSE_MODEL", "qwen3:8b")
SKILLS_DIR = Path(__file__).parent.parent / "skills"

# Context window: qwen3-coder supports up to 256K.
# We use 32K by default — enough for skills + task + substantial output.
DEFAULT_CTX = int(os.environ.get("OLLAMA_CTX", "32768"))

# Complexity keywords for auto-routing
COMPLEX_KEYWORDS = [
    "architecture", "design", "multiple files", "module", "refactor",
    "auth", "security", "database", "migration", "API", "system",
    "integration", "service", "middleware", "pipeline", "orchestrat",
    "complex", "multi-step", "full implementation", "entire", "complete module"
]

# Prose keywords for auto-routing to the prose model
# NOTE: Only for CREATIVE writing, user-facing copy, and non-technical prose.
# Technical docs (READMEs, architecture docs, API docs) should use the code model
# because they need factual accuracy about the codebase.
PROSE_KEYWORDS = [
    "creative writing", "marketing copy", "user-facing copy",
    "blog post", "article", "announcement", "press release",
    "story", "narrative", "dialogue", "slogan", "tagline",
    "translate", "i18n", "localization",
    "email template", "notification text", "onboarding copy",
    "help text", "tooltip text", "error message copy"
]

# Skills tagged 'always' are auto-included. This is read from frontmatter at runtime.
MANDATORY_SKILLS = []  # Populated dynamically from tags


def deduplicate_skills(skills: list[str]) -> list[str]:
    """Ensure 'always' tagged skills are present, deduplicate, preserve order."""
    # Get mandatory skills from tags
    always_skills = get_skills_by_tags([])  # Returns only 'always' tagged
    
    seen = set()
    result = []
    for skill in always_skills + skills:
        normalized = skill.replace(".md", "")
        if normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result


# --- Language auto-detection ---

# Map file extensions to language skill names (without .md)
EXTENSION_TO_LANG = {
    ".ts": "lang-typescript",
    ".tsx": "lang-typescript",
    ".js": "lang-javascript",
    ".jsx": "lang-javascript",
    ".mjs": "lang-javascript",
    ".py": "lang-python",
    ".pyw": "lang-python",
    ".rs": "lang-rust",
    ".go": "lang-go",
    ".java": "lang-java",
    ".kt": "lang-kotlin",
    ".kts": "lang-kotlin",
    ".cs": "lang-csharp",
    ".rb": "lang-ruby",
    ".php": "lang-php",
    ".swift": "lang-swift",
    ".c": "lang-c",
    ".h": "lang-c",
    ".cpp": "lang-cpp",
    ".cxx": "lang-cpp",
    ".cc": "lang-cpp",
    ".hpp": "lang-cpp",
    ".zig": "lang-zig",
    ".lua": "lang-lua",
    ".ex": "lang-elixir",
    ".exs": "lang-elixir",
    ".dart": "lang-dart",
    ".scala": "lang-scala",
    ".hs": "lang-haskell",
    ".vue": "lang-typescript",
    ".svelte": "lang-typescript",
}


def detect_language_skill(output_path: str | None, context_files: list[str] | None) -> str | None:
    """Detect the target language from --output extension or --context file extensions.
    
    Priority: --output extension wins (it's the target). If no --output, majority
    vote from context file extensions. Returns a lang-* skill name if a matching
    skill file exists in SKILLS_DIR, otherwise None.
    """
    detected_lang = None

    # 1. Check --output extension first (strongest signal)
    if output_path:
        ext = Path(output_path).suffix.lower()
        detected_lang = EXTENSION_TO_LANG.get(ext)

    # 2. Fallback: majority vote from context files
    if not detected_lang and context_files:
        from collections import Counter
        lang_votes = Counter()
        for cf in context_files:
            ext = Path(cf).suffix.lower()
            lang = EXTENSION_TO_LANG.get(ext)
            if lang:
                lang_votes[lang] += 1
        if lang_votes:
            detected_lang = lang_votes.most_common(1)[0][0]

    # 3. Only return if the skill file actually exists
    if detected_lang:
        skill_path = SKILLS_DIR / f"{detected_lang}.md"
        if skill_path.exists():
            return detected_lang
        else:
            print(
                f"[LANG] Detected '{detected_lang}' but no skill file found at {skill_path}. "
                f"Create it for language-specific guidance.",
                file=sys.stderr,
            )
            return None

    return None

SYSTEM_PROMPT_BASE = """\
You are a local coding subagent running on dedicated hardware. Your job is to generate \
high-quality, production-ready code.

## Output Rules

1. Output ONLY code unless the task explicitly asks for explanation or analysis.
2. Wrap each file in a markdown code block with the language specified:
   ```python
   # code here
   ```
3. If multiple files are needed, prefix each block with a filepath comment:
   ```
   // --- src/auth/handler.ts ---
   ```
4. Write COMPLETE implementations. No placeholders, no TODOs, no "implement here".
5. Include all necessary imports at the top of each file.
6. Follow the coding standards provided in the SKILLS section below — they are non-negotiable.

## Quality Rules

- Every public function/method MUST have a docstring.
- Handle errors explicitly — never swallow exceptions.
- Validate inputs at function boundaries.
- Use descriptive names. If a name needs a comment to explain it, rename it.
- Prefer simplicity. Don't add abstractions unless the task requires them.
"""


def load_skill(skill_name: str) -> str:
    """Load a skill file by name (with or without .md extension).
    
    Strips frontmatter and returns the raw markdown content.
    Returns empty string if the skill file doesn't exist.
    """
    if not skill_name.endswith(".md"):
        skill_name += ".md"
    
    skill_path = SKILLS_DIR / skill_name
    if not skill_path.exists():
        print(f"[WARN] Skill '{skill_name}' not found at {skill_path}", file=sys.stderr)
        return ""
    
    content = skill_path.read_text(encoding="utf-8")
    # Strip YAML frontmatter if present
    if content.startswith("---"):
        end = content.find("---", 3)
        if end != -1:
            content = content[end + 3:].strip()
    
    return content


def parse_frontmatter(filepath: Path) -> dict:
    """Parse YAML-like frontmatter from a skill file.
    
    Returns dict with keys: name, tags, description.
    Returns empty dict if no frontmatter found.
    """
    content = filepath.read_text(encoding="utf-8")
    if not content.startswith("---"):
        return {}
    
    end = content.find("---", 3)
    if end == -1:
        return {}
    
    frontmatter_text = content[3:end].strip()
    result = {}
    for line in frontmatter_text.split("\n"):
        if ":" in line:
            key, value = line.split(":", 1)
            key = key.strip()
            value = value.strip()
            if key == "tags":
                # Parse [tag1, tag2] format
                value = value.strip("[]")
                result[key] = [t.strip() for t in value.split(",")]
            else:
                result[key] = value
    return result


def get_skills_by_tags(requested_tags: list[str]) -> list[str]:
    """Select skill files that match any of the requested tags.
    
    Always includes skills tagged with 'always'.
    Returns list of skill names (without .md).
    """
    if not SKILLS_DIR.exists():
        return []
    
    selected = []
    requested_set = set(requested_tags)
    
    for skill_file in sorted(SKILLS_DIR.glob("*.md")):
        meta = parse_frontmatter(skill_file)
        tags = meta.get("tags", [])
        
        # Always include 'always' tagged skills
        if "always" in tags:
            selected.append(skill_file.stem)
        elif requested_set.intersection(set(tags)):
            selected.append(skill_file.stem)
    
    return selected

def load_context_file(filepath: str) -> str:
    """Load an existing source file to include as reference context."""
    path = Path(filepath)
    if not path.is_absolute():
        path = WORKSPACE_ROOT / path
    
    if not path.exists():
        print(f"[WARN] Context file '{filepath}' not found", file=sys.stderr)
        return ""
    
    content = path.read_text(encoding="utf-8")
    return f"\n{'='*60}\nEXISTING FILE: {filepath}\n{'='*60}\n```\n{content}\n```"


def get_all_skills() -> list[str]:
    """Get all available skill names (without .md extension)."""
    if not SKILLS_DIR.exists():
        return []
    return sorted([f.stem for f in SKILLS_DIR.glob("*.md")])


def build_system_prompt(skills: list[str], context_files: list[str] = None) -> str:
    """Build the full system prompt with skills and optional context files injected."""
    parts = [SYSTEM_PROMPT_BASE]
    
    # Inject skills
    parts.append(f"\n{'='*60}\n## SKILLS (Follow these standards)\n{'='*60}")
    
    loaded_count = 0
    for skill_name in skills:
        skill_content = load_skill(skill_name)
        if skill_content:
            parts.append(f"\n### {skill_name.upper()}\n{skill_content}")
            loaded_count += 1
    
    if loaded_count == 0:
        print("[WARN] No skills were loaded. Output quality may be lower.", file=sys.stderr)
    else:
        print(f"[INFO] Loaded {loaded_count} skill(s): {', '.join(skills)}", file=sys.stderr)
    
    # Inject context files (existing code for reference)
    if context_files:
        parts.append(f"\n{'='*60}\n## REFERENCE CODE (Existing files for context)\n{'='*60}")
        for cf in context_files:
            context_content = load_context_file(cf)
            if context_content:
                parts.append(context_content)
    
    return "\n".join(parts)


def estimate_tokens(text: str) -> int:
    """Rough token estimate (~4 chars per token for English/code)."""
    return len(text) // 4


def resolve_model(task: str, complexity: str, explicit_model: str = None) -> str:
    """Determine which model to use based on task complexity.
    
    Priority: explicit --model flag > --complexity flag > auto-detection from task text.
    
    Routing:
        simple  → qwen2.5-coder:7b (fast, code)
        complex → qwen3-coder:30b-a3b (heavy, code)
        prose   → qwen3:8b (general, writing)
        auto    → detect from keywords and task length
    """
    if explicit_model and explicit_model != DEFAULT_MODEL:
        return explicit_model
    
    if complexity == "simple":
        return FAST_MODEL
    elif complexity == "complex":
        return HEAVY_MODEL
    elif complexity == "prose":
        return PROSE_MODEL
    elif complexity == "auto":
        task_lower = task.lower()
        
        # Check prose keywords first
        for keyword in PROSE_KEYWORDS:
            if keyword.lower() in task_lower:
                return PROSE_MODEL
        
        # Check complexity keywords
        for keyword in COMPLEX_KEYWORDS:
            if keyword.lower() in task_lower:
                return HEAVY_MODEL
        
        # Short tasks → fast model, longer/detailed tasks → heavy model
        if len(task) < 100:
            return FAST_MODEL
        return HEAVY_MODEL
    
    return DEFAULT_MODEL


def _get_fallback_chain(primary_model: str) -> list[str]:
    """Get the ordered list of models to try, starting with primary.
    
    Fallback logic:
        - Heavy model fails → try fast model
        - Fast model fails → try heavy model  
        - Prose model fails → try fast model (at least get something)
        - If primary is already the last resort, just return it alone
    """
    if primary_model == HEAVY_MODEL:
        return [HEAVY_MODEL, FAST_MODEL]
    elif primary_model == FAST_MODEL:
        return [FAST_MODEL, HEAVY_MODEL]
    elif primary_model == PROSE_MODEL:
        return [PROSE_MODEL, FAST_MODEL]
    else:
        # Unknown/custom model — try it, then fall back to fast
        return [primary_model, FAST_MODEL]


def call_ollama(model: str, system_prompt: str, task: str, 
                temperature: float = 0.2, ctx_size: int = DEFAULT_CTX) -> dict:
    """Call the Ollama API and return the response with metadata.
    
    Returns dict with 'response', 'total_duration', 'eval_count' etc.
    Timeout is auto-scaled based on context size (Req 6.8):
        60s base + 3s per 100 tokens, capped at 600s.
    Raises OllamaError on failure (connection, timeout, HTTP error).
    """
    # Import calculate_timeout for dynamic timeout scaling (Req 6.8)
    sys.path.insert(0, _INTERNAL_DIR_STR)
    from local_coder.patch_mode import calculate_timeout

    url = f"{OLLAMA_BASE_URL}/api/generate"
    
    payload = {
        "model": model,
        "prompt": task,
        "system": system_prompt,
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_ctx": ctx_size,
        }
    }
    
    # Estimate prompt size and warn if it's eating most of the context
    prompt_tokens = estimate_tokens(system_prompt + task)
    if prompt_tokens > ctx_size * 0.7:
        print(f"[WARN] Prompt uses ~{prompt_tokens} tokens ({prompt_tokens*100//ctx_size}% of {ctx_size} ctx). "
              f"Response may be truncated. Consider using fewer skills or increasing context.", 
              file=sys.stderr)
    
    # Auto-scale timeout based on context size (Req 6.8)
    timeout_seconds = calculate_timeout(prompt_tokens)
    
    try:
        print(f"[INFO] Calling {model} (ctx={ctx_size}, temp={temperature}, timeout={timeout_seconds}s)...", file=sys.stderr)
        response = requests.post(url, json=payload, timeout=timeout_seconds)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.ConnectionError:
        raise OllamaError(f"Cannot connect to Ollama at {OLLAMA_BASE_URL}. Make sure Ollama is running.")
    except requests.exceptions.Timeout:
        raise OllamaError(f"Ollama request timed out ({timeout_seconds}s limit) for model {model}")
    except requests.exceptions.HTTPError as e:
        raise OllamaError(f"Ollama returned {e.response.status_code}: {e.response.text}")


class OllamaError(Exception):
    """Raised when Ollama API call fails."""
    pass


def log_token_savings(tokens_generated: int, model: str) -> None:
    """Log token savings to codesearch's SQLite DB.
    
    Records that the local model generated N tokens that would have otherwise
    been consumed as cloud output tokens. The 'tokens_returned' is 0 (Kiro
    reviews the diff, not the full output) and 'tokens_full_file' is what
    the cloud would have spent generating the same code.
    """
    db_path = WORKSPACE_ROOT / ".codesearch" / "index.db"
    if not db_path.exists():
        return
    
    try:
        import sqlite3
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            "INSERT INTO project_token_tracking (interface_type, tool_name, tokens_returned, tokens_full_file) "
            "VALUES (?, ?, ?, ?)",
            ("cli", f"local_coder.{model}", 0, tokens_generated)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[WARN] Could not log token savings: {e}", file=sys.stderr)


def _show_stats() -> None:
    """Display token savings statistics using the new session-based tracker."""
    db_path = WORKSPACE_ROOT / ".codesearch" / "index.db"
    if not db_path.exists():
        print("No codesearch database found. Run 'codesearch init .' first.")
        return
    
    tracker = SessionTracker(db_path)
    display_stats(tracker)


def _show_detailed_stats(detailed: bool, since: str | None) -> None:
    """Display detailed task result statistics from the Result Database."""
    result_db_path = WORKSPACE_ROOT / ".subagentcoder" / "task_results.db"
    if not result_db_path.exists():
        print("\nNo task result database found. Results will be logged after task executions.")
        return

    from local_coder.result_database import ResultDatabase
    db = ResultDatabase(result_db_path)

    # Parse since_days
    since_days = None
    if since:
        match = re.match(r"(\d+)d", since)
        if match:
            since_days = int(match.group(1))
        else:
            print(f"[ERROR] Invalid --since format: '{since}'. Use format: 7d, 30d, etc.", file=sys.stderr)
            db.close()
            return

    # Show complexity report (always when detailed or since is used)
    print("\n--- Complexity Report ---")
    report = db.get_complexity_report()
    if not report:
        print("  No task results logged yet.")
    else:
        # Table header
        print(f"  {'Score':<8}{'Total':<8}{'Success%':<12}{'Fail%':<10}{'Avg Tokens':<12}{'Avg Iter':<10}")
        print(f"  {'-'*60}")
        for row in report:
            if row["insufficient_data"]:
                print(f"  {row['complexity_score']:<8}{row['total_tasks']:<8}{'insufficient data'}")
            else:
                print(f"  {row['complexity_score']:<8}{row['total_tasks']:<8}{row['success_rate']:<12.1f}{row['failure_rate']:<10.1f}{row['avg_tokens']:<12.0f}{row['avg_iterations']:<10.1f}")

    # Show full detailed report
    if detailed:
        print("\n--- Detailed Report ---")
        detail = db.get_detailed_report(since_days=since_days)
        print(f"  Total tasks: {detail['total_tasks']}")
        if detail['date_range']['from'] and detail['date_range']['to']:
            print(f"  Date range: {detail['date_range']['from'][:10]} to {detail['date_range']['to'][:10]}")
        else:
            print("  Date range: N/A")
        print(f"  Outcomes: success={detail['outcome_breakdown']['success']}, "
              f"fail={detail['outcome_breakdown']['fail']}, "
              f"escalated={detail['outcome_breakdown']['escalated']}")

        # Per-model rates
        if detail.get("per_model_rates"):
            print("\n  Per-model success rates:")
            for model, stats in detail["per_model_rates"].items():
                print(f"    {model}: {stats['success_rate']:.1f}% ({stats['total']} tasks)")

        # Top error types
        if detail.get("top_error_types"):
            print("\n  Top error types:")
            for err in detail["top_error_types"]:
                levels = ", ".join(str(l) for l in err.get("affected_levels", []))
                print(f"    {err['error_type']}: {err['count']} occurrences (levels: {levels})")

    db.close()


def extract_code_blocks(text: str) -> str:
    """Extract code from markdown code blocks, stripping the fences.
    
    DEPRECATED: Use strip_markdown_fences() from fence_strip module instead.
    This function is kept for backward compatibility only.
    
    If no code blocks are found, returns the original text.
    If multiple blocks exist, joins them with file separator comments.
    """
    from fence_strip import strip_markdown_fences, FenceStripError
    try:
        result, was_stripped = strip_markdown_fences(text)
        return result
    except FenceStripError:
        # Original function didn't raise on empty — return empty string
        return ""


def main():
    parser = argparse.ArgumentParser(
        description="Local Coder - Ollama Subagent Orchestrator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Skills are always prepended with 'software-engineering' as a baseline."
    )
    parser.add_argument("--task", "-t", help="The coding task to perform")
    parser.add_argument("--skills", "-s", nargs="*", default=[],
                        help="Explicit skill files to include by name")
    parser.add_argument("--tags", nargs="*", default=[],
                        help="Select skills by tag (e.g., --tags code api security)")
    parser.add_argument("--all-skills", action="store_true",
                        help="Include ALL available skills")
    parser.add_argument("--context", "-c", nargs="*", default=[],
                        help="Existing source files to include as reference context")
    parser.add_argument("--model", "-m", default=DEFAULT_MODEL, 
                        help=f"Ollama model (default: {DEFAULT_MODEL})")
    parser.add_argument("--complexity", choices=["simple", "complex", "prose", "auto"], default="auto",
                        help="Route to fast model (simple), heavy model (complex), prose model (prose). Default: auto-detect.")
    parser.add_argument("--temperature", type=float, default=0.2, 
                        help="Generation temperature (default: 0.2)")
    parser.add_argument("--ctx-size", type=int, default=DEFAULT_CTX,
                        help=f"Context window size (default: {DEFAULT_CTX})")
    parser.add_argument("--output", "-o", help="Write output to file instead of stdout")
    parser.add_argument("--raw", action="store_true",
                        help="Output raw response (don't strip markdown fences)")
    parser.add_argument("--mode", choices=["full", "patch"], default="full",
                        help="Generation mode. 'full' outputs complete file, 'patch' outputs edit operations.")
    parser.add_argument("--symbol", type=str, default=None,
                        help="Extract specific symbol via CodeSearch for context instead of full file.")
    parser.add_argument("--scope", type=str, default=None,
                        help="Modification boundary constraint (comma-separated symbols, line ranges, or descriptions). Max 500 chars.")
    parser.add_argument("--list-skills", action="store_true", 
                        help="List available skills and exit")
    parser.add_argument("--stats", action="store_true",
                        help="Show token savings statistics and exit")
    parser.add_argument("--detailed", action="store_true",
                        help="Show detailed task result report (requires --stats)")
    parser.add_argument("--since", type=str, default=None,
                        help="Filter stats to last N days (e.g., --since 7d). Requires --stats.")
    parser.add_argument("--task-id", default=None,
                        help="Explicit task ID for result database (e.g., spec task ID like '1.1'). "
                             "Uses uuid4() if not provided.")
    parser.add_argument("--session-id", default=None,
                        help="Explicit session ID for token tracking (auto-generated if not provided)")
    parser.add_argument("--minimal-prompt", action="store_true",
                        help="Strip skill injection from prompt. Use for tasks where the output "
                             "is fully specified in the task description (e.g., exact JSON content).")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print the system prompt that would be sent, without calling Ollama")
    parser.add_argument("--distill", action="store_true",
                        help="Enable skill distillation instead of verbatim skill injection")
    parser.add_argument("--token-budget", type=int, default=None,
                        help="Token budget for distillation (range: 500-16000, default: 4000). Requires --distill.")
    parser.add_argument("--distill-threshold", type=float, default=None,
                        help="Relevance threshold for distillation (range: 0.0-1.0, default: 0.3). Requires --distill.")
    parser.add_argument("--scaffolding", nargs="*", default=None,
                        help="Enable scaffolding. No args = auto-select; "
                             "with args = inject those template names directly.")
    parser.add_argument("--scaffolding-budget", type=int, default=None,
                        help="Token budget for scaffolding injection (default: 4000 or env)")
    parser.add_argument("--list-scaffolding", action="store_true",
                        help="List available scaffolding templates and exit")
    
    args = parser.parse_args()

    # --- Validate distillation flags ---
    if args.token_budget is not None:
        if args.token_budget < 500 or args.token_budget > 16000:
            print(
                f"[ERROR] --token-budget must be in range [500, 16000], got {args.token_budget}",
                file=sys.stderr,
            )
            sys.exit(1)
        if not args.distill:
            print("[WARN] --token-budget requires --distill; ignoring", file=sys.stderr)

    if args.distill_threshold is not None:
        if args.distill_threshold < 0.0 or args.distill_threshold > 1.0:
            print(
                f"[ERROR] --distill-threshold must be in range [0.0, 1.0], got {args.distill_threshold}",
                file=sys.stderr,
            )
            sys.exit(1)
        if not args.distill:
            print("[WARN] --distill-threshold requires --distill; ignoring", file=sys.stderr)
    
    # --- List skills mode ---
    if args.list_skills:
        skills = get_all_skills()
        print("Available skills:")
        for s in skills:
            meta = parse_frontmatter(SKILLS_DIR / f"{s}.md")
            tags = meta.get("tags", [])
            tag_str = f" [{', '.join(tags)}]" if tags else ""
            mandatory = " ← always included" if "always" in tags else ""
            print(f"  - {s}{tag_str}{mandatory}")
        return
    
    # --- Stats mode ---
    if args.stats:
        _show_stats()
        # Show detailed report if requested
        if args.detailed or args.since:
            _show_detailed_stats(args.detailed, args.since)
        return
    
    # --- List scaffolding mode ---
    if args.list_scaffolding:
        from local_coder.scaffolding_selector import list_templates
        tags_filter = args.tags if hasattr(args, 'tags') and args.tags else None
        templates = list_templates(tags=tags_filter)
        if not templates:
            print("No scaffolding templates found.")
        else:
            print("Available scaffolding templates:")
            for t in templates:
                print(f"  {t.name}  [{t.category}]  tags={t.tags}  complexity={t.complexity}  source={t.source}")
                print(f"    {t.description}")
        sys.exit(0)
    
    # --- Require task for generation ---
    if not args.task:
        parser.error("--task/-t is required unless using --list-skills, --stats, or --list-scaffolding")

    # --- Validate --scope length ---
    if args.scope and len(args.scope) > 500:
        print(
            f"[ERROR] scope: --scope value exceeds 500 characters ({len(args.scope)} given)",
            file=sys.stderr,
        )
        sys.exit(1)
    
    # --- Resolve skills ---
    if args.all_skills:
        skills = get_all_skills()
    elif args.tags:
        skills = get_skills_by_tags(args.tags)
        # Also include any explicitly named skills
        for s in args.skills:
            if s not in skills:
                skills.append(s)
    elif args.skills:
        skills = args.skills
    else:
        # Default: just mandatory skills (tagged 'always')
        skills = get_skills_by_tags([])
    
    skills = deduplicate_skills(skills)

    # --- Language auto-detection (inject lang-* skill if available) ---
    lang_skill = detect_language_skill(args.output, args.context)
    if lang_skill and lang_skill not in skills:
        skills.append(lang_skill)
        print(f"[LANG] Auto-detected language skill: {lang_skill}", file=sys.stderr)
    
    # --- Scaffolding injection (after skill resolution, before prompt build) ---
    if args.scaffolding is not None:
        from local_coder.scaffolding_selector import select_scaffolding, list_templates

        budget = args.scaffolding_budget or int(os.environ.get("SCAFFOLDING_TOKEN_BUDGET", "4000"))

        if args.scaffolding:  # Explicit template names provided
            # Resolve explicit names to paths
            all_templates = list_templates()
            name_to_path = {t.name: t.path for t in all_templates}
            scaffolding_paths = []
            for name in args.scaffolding:
                if name in name_to_path:
                    scaffolding_paths.append(name_to_path[name])
                else:
                    print(f"[SCAFFOLD ERROR] Template not found: {name}", file=sys.stderr)
                    sys.exit(1)
        else:  # Auto-select
            scaffolding_paths = select_scaffolding(
                tags=args.tags or [],
                complexity=getattr(args, 'complexity', 'any') or 'any',
                budget_tokens=budget,
            )

        if scaffolding_paths:
            names = [p.stem for p in scaffolding_paths]
            print(f"[SCAFFOLD] Selected {len(names)} template(s): {', '.join(names)}",
                  file=sys.stderr)
            # Prepend scaffolding to context (before project-specific files)
            args.context = [str(p) for p in scaffolding_paths] + (args.context or [])
    
    # --- Detect if --mode was explicitly specified ---
    mode_explicitly_set = "--mode" in sys.argv

    # --- Emit warning for large context files without --mode specified ---
    if args.context and not mode_explicitly_set:
        for cf in args.context:
            cf_path = Path(cf)
            if not cf_path.is_absolute():
                cf_path = WORKSPACE_ROOT / cf_path
            if cf_path.exists():
                line_count = len(cf_path.read_text(encoding="utf-8").splitlines())
                if line_count > 500:
                    print(
                        "[WARN] local-coder: Context file exceeds 500 lines, "
                        "consider using --mode patch or --symbol",
                        file=sys.stderr,
                    )
                    break  # Only warn once

    # --- Symbol extraction (replaces context with symbol-specific content) ---
    symbol_context_info = None  # Will hold (source, start_line, end_line) if --symbol used
    if args.symbol:
        sys.path.insert(0, _INTERNAL_DIR_STR)
        from local_coder.patch_mode import extract_symbol_context, SymbolNotFoundError
        try:
            source_code, start_line, end_line = extract_symbol_context(args.symbol)
            symbol_context_info = (source_code, start_line, end_line)
            # Store for later splice use
            args._symbol_start_line = start_line
            args._symbol_end_line = end_line
            print(
                f"[INFO] Extracted symbol '{args.symbol}' (lines {start_line}-{end_line})",
                file=sys.stderr,
            )
            # Replace context with symbol source
            args.context = []  # Clear file-level context
        except SymbolNotFoundError as e:
            print(f"[ERROR] symbol: {e}", file=sys.stderr)
            sys.exit(1)

    # --- File tagging (Req 5.4, 5.7) ---
    try:
        file_tags = tag_files(args.task, WORKSPACE_ROOT)
        if file_tags:
            for tag in file_tags:
                # Append file paths to context
                if tag.file_path not in (args.context or []):
                    if args.context is None:
                        args.context = []
                    args.context.append(tag.file_path)
            print(f"[FILE-TAG] Added {len(file_tags)} file(s) to context", file=sys.stderr)
    except Exception as e:
        # Never crash pipeline for instrumentation
        file_tags = []
        print(f"[WARN] File tagging failed: {e}", file=sys.stderr)

    # --- Build prompt ---
    if args.distill:
        # Distillation path: condense skills instead of verbatim injection
        try:
            from distiller import distill as distill_skills, DistillConfig

            # Derive config values
            budget = args.token_budget if args.token_budget else 4000
            threshold = args.distill_threshold if args.distill_threshold else 0.3

            # Collect skill file paths
            skill_paths = []
            for skill_name in skills:
                fname = skill_name if skill_name.endswith(".md") else f"{skill_name}.md"
                skill_path = SKILLS_DIR / fname
                if skill_path.exists():
                    skill_paths.append(skill_path)

            # Run distillation
            distill_result = distill_skills(
                task_description=args.task,
                skill_paths=skill_paths,
                config=DistillConfig(token_budget=budget, threshold=threshold),
            )

            # Build system prompt with distilled content in place of full skills
            parts = [SYSTEM_PROMPT_BASE]
            parts.append(f"\n{'='*60}")
            if distill_result.prompt:
                parts.append(distill_result.prompt)
            else:
                parts.append("## SKILLS (Distilled for this task)\n")
                parts.append("<!-- no skills matched -->\n")
            parts.append(f"{'='*60}")

            # Inject context files (same as build_system_prompt)
            context_files = args.context if args.context else None
            if context_files:
                parts.append(f"\n{'='*60}\n## REFERENCE CODE (Existing files for context)\n{'='*60}")
                for cf in context_files:
                    context_content = load_context_file(cf)
                    if context_content:
                        parts.append(context_content)

            system_prompt = "\n".join(parts)

            # Report token savings to stderr (Req 4.3)
            full_tokens = distill_result.tokens_full
            distilled_tokens = distill_result.tokens_used
            saved = full_tokens - distilled_tokens
            if full_tokens > 0:
                pct = round((saved / full_tokens) * 100)
            else:
                pct = 0
            print(
                f"[DISTILL] Saved {saved} tokens ({pct}% reduction) "
                f"\u2014 {full_tokens} full \u2192 {distilled_tokens} distilled",
                file=sys.stderr,
            )
            print(
                f"[INFO] Distilled {distill_result.skills_included} skill(s), "
                f"{distill_result.sections_included}/{distill_result.sections_total} sections",
                file=sys.stderr,
            )

        except Exception as e:
            # Fallback: on any distiller error, use verbatim injection (Req 4.9)
            print(f"[DISTILL] ERROR: {e}", file=sys.stderr)
            print("[DISTILL] Falling back to verbatim injection", file=sys.stderr)
            system_prompt = build_system_prompt(skills, args.context if args.context else None)
    elif args.minimal_prompt:
        # Minimal prompt mode: skip skill injection entirely, just use base + context
        # For tasks where the output is fully specified (e.g., "create this exact JSON")
        parts = [SYSTEM_PROMPT_BASE]
        context_files = args.context if args.context else None
        if context_files:
            parts.append(f"\n{'='*60}\n## REFERENCE CODE (Existing files for context)\n{'='*60}")
            for cf in context_files:
                context_content = load_context_file(cf)
                if context_content:
                    parts.append(context_content)
        system_prompt = "\n".join(parts)
        print("[INFO] Minimal prompt mode: skill injection skipped", file=sys.stderr)
    else:
        system_prompt = build_system_prompt(skills, args.context if args.context else None)

    # If symbol context was extracted, append it to the system prompt
    if symbol_context_info:
        source_code, start_line, end_line = symbol_context_info
        system_prompt += (
            f"\n{'='*60}\n"
            f"## SYMBOL CONTEXT: {args.symbol} (lines {start_line}-{end_line})\n"
            f"{'='*60}\n"
            f"```\n{source_code}\n```"
        )

    # If patch mode, augment system prompt with edit format instructions
    if args.mode == "patch":
        system_prompt += (
            f"\n{'='*60}\n"
            "## OUTPUT FORMAT: PATCH MODE\n"
            f"{'='*60}\n"
            "You MUST output your changes as edit operations in this exact format:\n\n"
            "<<<<<<< SEARCH\n"
            "<exact old text to find>\n"
            "=======\n"
            "<replacement new text>\n"
            ">>>>>>> REPLACE\n\n"
            "Rules:\n"
            "- Each edit has a SEARCH section (exact text to find) and REPLACE section (new text).\n"
            "- The SEARCH text must match the target file character-for-character (whitespace-sensitive).\n"
            "- You may include multiple edit operations sequentially.\n"
            "- Do NOT output the entire file. Only output the specific edits needed.\n"
        )

    # If --scope specified, append scope constraint to system prompt (Req 7.2)
    if args.scope:
        system_prompt += (
            f"\n{'='*60}\n"
            "## SCOPE CONSTRAINT\n"
            f"{'='*60}\n"
            "You MUST limit your changes to the scope described. "
            "Do NOT modify, remove, or add anything outside this scope.\n"
            f"Allowed scope: {args.scope}\n"
        )
    
    # --- Complexity estimation (Req 3.1, 3.3) ---
    try:
        complexity_score = estimate_complexity(
            args.task,
            context_files=args.context if args.context else [],
            output_path=args.output,
        )
        print(f"[COMPLEXITY] Score: {complexity_score}", file=sys.stderr)
    except Exception as e:
        # Never crash pipeline for instrumentation (Req 3.2)
        complexity_score = 1
        print(f"[WARN] Complexity estimation failed: {e}", file=sys.stderr)

    # --- Resolve task ID for result database ---
    # Use explicit --task-id if provided, otherwise fall back to random UUID
    _resolved_task_id = args.task_id if args.task_id else str(uuid.uuid4())

    # --- Resolve model ---
    model = resolve_model(args.task, args.complexity, 
                          args.model if args.model != DEFAULT_MODEL else None)
    print(f"[INFO] Model: {model} (complexity={args.complexity})", file=sys.stderr)
    
    # --- Dry run mode ---
    if args.dry_run:
        if args.distill:
            # Dry-run + distill: print distilled prompt to stdout with diagnostics to stderr
            from distiller import (
                parse_skill_file,
                score_section,
                estimate_tokens as distill_estimate_tokens,
                DistillConfig,
                DEFAULT_STOP_WORDS,
                distill as distill_skills,
            )

            # Derive config values
            budget = args.token_budget if args.token_budget else 4000
            threshold = args.distill_threshold if args.distill_threshold is not None else 0.3

            # Collect skill file paths
            skill_paths = []
            for skill_name in skills:
                fname = skill_name if skill_name.endswith(".md") else f"{skill_name}.md"
                skill_path = SKILLS_DIR / fname
                if skill_path.exists():
                    skill_paths.append(skill_path)

            # Run distillation to get the prompt
            distill_result = distill_skills(
                task_description=args.task,
                skill_paths=skill_paths,
                config=DistillConfig(token_budget=budget, threshold=threshold),
            )

            # Print the distilled prompt to stdout
            print(distill_result.prompt)

            # Compute per-section diagnostics for stderr
            task_tokens: set[str] = {
                w.lower()
                for w in args.task.split()
                if w.lower() not in DEFAULT_STOP_WORDS
            }

            sections_total = 0
            sections_included = 0

            for skill_path in skill_paths:
                name, tags, sections = parse_skill_file(skill_path)
                is_always = "always" in tags
                print(f"[DISTILL-DIAG] Skill: {name or skill_path.stem}", file=sys.stderr)
                for idx, section in enumerate(sections):
                    sections_total += 1
                    raw_score = score_section(task_tokens, section, DEFAULT_STOP_WORDS)
                    token_count = distill_estimate_tokens(section.heading + " " + section.body)

                    # Determine inclusion status:
                    # - "always"-tagged skill's first non-preamble section (or preamble
                    #   if no non-preamble) is always included
                    # - Other sections included if score >= threshold
                    is_always_core = False
                    if is_always:
                        # Core section: first non-preamble, or preamble if none exist
                        non_preamble = [s for s in sections if not s.is_preamble]
                        if non_preamble:
                            is_always_core = (section is non_preamble[0])
                        elif sections:
                            is_always_core = (section is sections[0])

                    if is_always_core or raw_score >= threshold:
                        status = "INCLUDED"
                        sections_included += 1
                    else:
                        status = "EXCLUDED"
                    print(
                        f"[DISTILL-DIAG]   {section.heading} — {status} "
                        f"(score: {raw_score:.2f}, ~{token_count} tokens)",
                        file=sys.stderr,
                    )

            # Print summary line to stderr
            print(
                f"[DISTILL-DIAG] Summary: {distill_result.tokens_used} tokens, "
                f"{sections_included}/{sections_total} sections, threshold={threshold}",
                file=sys.stderr,
            )
            return
        else:
            # Standard dry-run: print full prompt to stdout
            print("=" * 60)
            print("SYSTEM PROMPT (would be sent to Ollama)")
            print("=" * 60)
            print(system_prompt)
            print("\n" + "=" * 60)
            print("TASK PROMPT")
            print("=" * 60)
            print(args.task)
            print(f"\n[Token estimate: ~{estimate_tokens(system_prompt + args.task)} tokens]")
            return
    
    # --- Two-pass routing detection (Req 8.5) ---
    two_pass_decision = detect_two_pass(args.task, args.output)
    if two_pass_decision.is_two_pass:
        print(format_routing_log(two_pass_decision), file=sys.stderr)
        two_pass_result = execute_two_pass(
            task=args.task,
            context_files=args.context if args.context else [],
            output_path=args.output,
            code_complexity=args.complexity if args.complexity != "auto" else "simple",
        )
        if two_pass_result.escalated:
            print(
                f"[TWO-PASS] Escalated: {two_pass_result.escalation_reason}",
                file=sys.stderr,
            )
            print("[ERROR] Two-pass pipeline failed — escalating to cloud", file=sys.stderr)
            # --- Record escalation in result database (Req 6.4) ---
            try:
                result_db_path = WORKSPACE_ROOT / ".subagentcoder" / "task_results.db"
                result_db = ResultDatabase(result_db_path)
                task_result = TaskResult(
                    task_id=_resolved_task_id,
                    task_description=args.task[:200],
                    model_used=model,
                    complexity_score=complexity_score,
                    outcome="escalated",
                    token_count=0,
                    generation_duration_ms=0,
                    review_iterations=0,
                    file_tags=[],
                    error_type="two_pass_escalation",
                    timestamp=datetime.now(timezone.utc).isoformat(),
                )
                result_db.insert_result(task_result)
                result_db.close()
            except Exception:
                pass
            sys.exit(1)
        response_text = two_pass_result.final_output
    else:
        # --- Call Ollama (with fallback) ---
        fallback_chain = _get_fallback_chain(model)
        result = None

        for attempt_model in fallback_chain:
            try:
                result = call_ollama(attempt_model, system_prompt, args.task, args.temperature, args.ctx_size)
                if attempt_model != model:
                    print(f"[INFO] Fell back from {model} → {attempt_model}", file=sys.stderr)
                model = attempt_model  # Update for stats logging
                break
            except OllamaError as e:
                print(f"[WARN] {attempt_model} failed: {e}", file=sys.stderr)
                if attempt_model == fallback_chain[-1]:
                    print("[ERROR] All models failed. Is Ollama running?", file=sys.stderr)
                    sys.exit(1)
                print(f"[INFO] Trying fallback...", file=sys.stderr)

        response_text = result.get("response", "")
        if not response_text:
            print("[ERROR] Empty response from Ollama", file=sys.stderr)
            sys.exit(1)

        # --- Garbage detection and auto-retry (Req 6.1–6.5) ---
        from local_coder.garbage_detector import check_garbage, format_garbage_log, format_escalation_warning

        garbage_result = check_garbage(response_text, attempt=1)
        if garbage_result.is_garbage:
            print(format_garbage_log(garbage_result), file=sys.stderr)
            # Retry with bumped temperature (0.4) — low temp can cause degenerate loops
            retry_temp = min(args.temperature + 0.2, 0.4)
            print(f"[INFO] Garbage detected, retrying with temperature={retry_temp}", file=sys.stderr)
            retry_result = None
            try:
                retry_result = call_ollama(model, system_prompt, args.task, retry_temp, args.ctx_size)
            except OllamaError as e:
                print(f"[WARN] Garbage retry failed with error: {e}", file=sys.stderr)

            if retry_result:
                retry_text = retry_result.get("response", "")
                retry_garbage = check_garbage(retry_text, attempt=2)
                if retry_garbage.is_garbage:
                    # Retry also garbage — escalate to cloud
                    print(format_garbage_log(retry_garbage), file=sys.stderr)
                    task_id = args.output if args.output else args.task[:60]
                    print(format_escalation_warning(task_id), file=sys.stderr)
                    # --- Record garbage escalation in result database (Req 6.4) ---
                    try:
                        result_db_path = WORKSPACE_ROOT / ".subagentcoder" / "task_results.db"
                        result_db = ResultDatabase(result_db_path)
                        _task_result = TaskResult(
                            task_id=_resolved_task_id,
                            task_description=args.task[:200],
                            model_used=model,
                            complexity_score=complexity_score,
                            outcome="escalated",
                            token_count=0,
                            generation_duration_ms=0,
                            review_iterations=0,
                            file_tags=[],
                            error_type="garbage_detection",
                            timestamp=datetime.now(timezone.utc).isoformat(),
                        )
                        result_db.insert_result(_task_result)
                        result_db.close()
                    except Exception:
                        pass
                    sys.exit(2)  # Exit code 2 signals cloud escalation needed
                else:
                    # Retry succeeded — use the retry output
                    response_text = retry_text
                    result = retry_result
                    print("[INFO] Garbage retry succeeded, proceeding with retry output", file=sys.stderr)
            else:
                # Retry raised OllamaError — escalate to cloud
                task_id = args.output if args.output else args.task[:60]
                print(format_escalation_warning(task_id), file=sys.stderr)
                # --- Record garbage escalation in result database (Req 6.4) ---
                try:
                    result_db_path = WORKSPACE_ROOT / ".subagentcoder" / "task_results.db"
                    result_db = ResultDatabase(result_db_path)
                    _task_result = TaskResult(
                        task_id=_resolved_task_id,
                        task_description=args.task[:200],
                        model_used=model,
                        complexity_score=complexity_score,
                        outcome="escalated",
                        token_count=0,
                        generation_duration_ms=0,
                        review_iterations=0,
                        file_tags=[],
                        error_type="garbage_detection",
                        timestamp=datetime.now(timezone.utc).isoformat(),
                    )
                    result_db.insert_result(_task_result)
                    result_db.close()
                except Exception:
                    pass
                sys.exit(2)  # Exit code 2 signals cloud escalation needed

    # --- Report stats (only for normal single-pass path) ---
    if not two_pass_decision.is_two_pass:
        total_ms = result.get("total_duration", 0) / 1_000_000  # ns to ms
        eval_count = result.get("eval_count")
        if eval_count is None or eval_count == 0:
            # Fallback estimation when Ollama doesn't report eval_count
            estimated = len(response_text) // 4
            print(f"[TOKEN] eval_count missing, using estimate: {estimated}", file=sys.stderr)
            eval_count = estimated
        if total_ms > 0 and eval_count > 0:
            tokens_per_sec = eval_count / (total_ms / 1000)
            print(f"[INFO] Generated {eval_count} tokens in {total_ms/1000:.1f}s ({tokens_per_sec:.1f} tok/s)", 
                  file=sys.stderr)
    
        # --- Log token savings to codesearch DB ---
        log_token_savings(eval_count, model)
    
        # --- Record generation in session tracker ---
        try:
            db_path = WORKSPACE_ROOT / ".codesearch" / "index.db"
            if db_path.exists():
                tracker = SessionTracker(db_path)
                session_id = tracker.get_or_create_session(args.session_id, args.task, model)
                tracker.record_generation(session_id, eval_count, model)
                print(f"[INFO] Session: {session_id}", file=sys.stderr)
        except Exception as e:
            print(f"[WARN] Could not record session: {e}", file=sys.stderr)
    else:
        # --- Two-pass token tracking (Req 4.5) ---
        # Record Pass 1 (prose) and Pass 2 (code) separately
        pass1_tokens = two_pass_result.pass1_eval_count
        pass2_tokens = two_pass_result.pass2_eval_count
        total_tokens = pass1_tokens + pass2_tokens

        print(
            f"[INFO] Two-pass tokens: Pass 1={pass1_tokens}, Pass 2={pass2_tokens}, Total={total_tokens}",
            file=sys.stderr,
        )

        # Log combined token savings to codesearch DB
        if total_tokens > 0:
            log_token_savings(total_tokens, two_pass_result.pass2_model)

        # Record separate generation entries in session tracker
        try:
            db_path = WORKSPACE_ROOT / ".codesearch" / "index.db"
            if db_path.exists():
                tracker = SessionTracker(db_path)
                session_id = tracker.get_or_create_session(
                    args.session_id, args.task, two_pass_result.pass1_model
                )
                # Record Pass 1 (prose) generation
                tracker.record_generation(
                    session_id, pass1_tokens, two_pass_result.pass1_model
                )
                # Record Pass 2 (code) generation
                tracker.record_generation(
                    session_id, pass2_tokens, two_pass_result.pass2_model
                )
                print(f"[INFO] Session: {session_id} (two-pass)", file=sys.stderr)
        except Exception as e:
            print(f"[WARN] Could not record two-pass session: {e}", file=sys.stderr)
    
    # --- Process output ---
    if not args.raw:
        from fence_strip import strip_markdown_fences, FenceStripError
        try:
            response_text, was_stripped = strip_markdown_fences(response_text)
            if was_stripped:
                print("[INFO] Stripped markdown fences from output", file=sys.stderr)
        except FenceStripError as e:
            print(f"[ERROR] fence-strip: {e.message}", file=sys.stderr)
            sys.exit(1)

    # --- Patch mode handling ---
    if args.mode == "patch" and args.output:
        sys.path.insert(0, _INTERNAL_DIR_STR)
        from local_coder.patch_mode import (
            parse_edit_operations,
            apply_edit_operations,
            extract_symbol_context,
        )

        operations = parse_edit_operations(response_text)
        output_path = Path(args.output)
        if not output_path.is_absolute():
            output_path = WORKSPACE_ROOT / output_path

        if operations:
            # --- Scope enforcement in patch mode (Req 7.3, 7.4) ---
            if args.scope and output_path.exists():
                from local_coder.scope_enforcer import parse_scope, validate_edits_against_scope
                scope_entries = parse_scope(args.scope)
                file_content = output_path.read_text(encoding="utf-8")
                operations, rejected = validate_edits_against_scope(
                    operations, scope_entries, file_content
                )
                if rejected:
                    print(
                        f"[INFO] scope: {len(rejected)} edit(s) rejected, "
                        f"{len(operations)} edit(s) allowed",
                        file=sys.stderr,
                    )

            # Apply edit operations to the target file
            if not output_path.exists():
                print(
                    "[WARN] patch: Target file does not exist, writing full response",
                    file=sys.stderr,
                )
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_text(response_text, encoding="utf-8")
            else:
                applied, skipped = apply_edit_operations(output_path, operations)
                print(
                    f"[INFO] patch: Applied {applied} edit(s), skipped {skipped}",
                    file=sys.stderr,
                )

                # If --symbol was used, splice the output back at the original line range
                if args.symbol and hasattr(args, '_symbol_start_line'):
                    # Symbol splice is handled by apply_edit_operations on the full file
                    pass
        else:
            # No edit markers found — fallback to full-file write with warning
            print(
                "[WARN] patch: No edit markers found in patch mode response, "
                "falling back to full-file write",
                file=sys.stderr,
            )
            output_path.parent.mkdir(parents=True, exist_ok=True)
            if args.symbol and hasattr(args, '_symbol_start_line') and output_path.exists():
                # Splice model output back at the original symbol line range
                file_lines = output_path.read_text(encoding="utf-8").splitlines(keepends=True)
                start_idx = args._symbol_start_line - 1  # 0-based
                end_idx = args._symbol_end_line  # exclusive
                new_content_lines = response_text.splitlines(keepends=True)
                # Ensure trailing newline
                if new_content_lines and not new_content_lines[-1].endswith("\n"):
                    new_content_lines[-1] += "\n"
                spliced = file_lines[:start_idx] + new_content_lines + file_lines[end_idx:]
                output_path.write_text("".join(spliced), encoding="utf-8")
                print(
                    f"[INFO] patch: Spliced output at lines {args._symbol_start_line}-{args._symbol_end_line}",
                    file=sys.stderr,
                )
            else:
                output_path.write_text(response_text, encoding="utf-8")
            print(f"[INFO] Output written to {output_path}", file=sys.stderr)
    else:
        # --- Standard write output ---
        if args.output:
            output_path = Path(args.output)
            if not output_path.is_absolute():
                output_path = WORKSPACE_ROOT / output_path
            output_path.parent.mkdir(parents=True, exist_ok=True)

            # --- Advisory scope detection in non-patch mode (Req 7.6, 7.7) ---
            if args.scope and output_path.exists():
                sys.path.insert(0, _INTERNAL_DIR_STR)
                from local_coder.scope_enforcer import parse_scope, detect_out_of_scope_changes
                scope_entries = parse_scope(args.scope)
                original_content = output_path.read_text(encoding="utf-8")
                violations = detect_out_of_scope_changes(
                    original_content, response_text, scope_entries
                )
                for warning in violations:
                    print(f"[WARN] scope: {warning}", file=sys.stderr)

            output_path.write_text(response_text, encoding="utf-8")
            print(f"[INFO] Output written to {output_path}", file=sys.stderr)
        else:
            print(response_text)

    # --- Record task result in database (Req 6.3) ---
    try:
        result_db_path = WORKSPACE_ROOT / ".subagentcoder" / "task_results.db"
        result_db = ResultDatabase(result_db_path)
        # Determine token count based on generation path
        if two_pass_decision.is_two_pass:
            _token_count = two_pass_result.pass1_eval_count + two_pass_result.pass2_eval_count
            _duration_ms = 0
        else:
            _token_count = eval_count
            _duration_ms = int(total_ms) if total_ms > 0 else 0
        # Build file_tags list safely (file tagger may not be integrated yet)
        _file_tags_list = []
        if 'file_tags' in locals() and file_tags:
            _file_tags_list = [{"file_path": t.file_path, "line_range": t.line_range} for t in file_tags]
        task_result = TaskResult(
            task_id=_resolved_task_id,
            task_description=args.task[:200],
            model_used=model,
            complexity_score=complexity_score,
            outcome="success",
            token_count=_token_count,
            generation_duration_ms=_duration_ms,
            review_iterations=0,
            file_tags=_file_tags_list,
            error_type=None,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        result_db.insert_result(task_result)
        result_db.close()
    except Exception as e:
        print(f"[WARN] Could not record task result: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
