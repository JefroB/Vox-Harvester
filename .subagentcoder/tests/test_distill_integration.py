"""Integration tests for distillation fallback behavior in local_coder.py.

Tests that when the distiller raises an error during the --distill path,
local_coder falls back to verbatim skill injection without crashing.

Requirements: 4.9
"""

import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPTS_DIR = WORKSPACE_ROOT / ".kiro" / "scripts"
LOCAL_CODER_SCRIPT = SCRIPTS_DIR / "local_coder.py"


def _make_fake_distiller_file(fake_dir, exception_class, exception_msg):
    """Create a fake distiller.py that raises on distill()."""
    fake_dir.mkdir(exist_ok=True)
    fake_file = fake_dir / "distiller.py"
    content = (
        "from dataclasses import dataclass, field\n"
        "from pathlib import Path\n\n"
        "DEFAULT_STOP_WORDS = frozenset({'a', 'the', 'is', 'in', 'to'})\n\n"
        "@dataclass\n"
        "class CodeBlock:\n"
        "    language: str\n"
        "    content: str\n"
        "    preceding_text: str\n\n"
        "@dataclass\n"
        "class Section:\n"
        "    heading: str\n"
        "    body: str\n"
        "    code_blocks: list\n"
        "    is_preamble: bool = False\n\n"
        "@dataclass\n"
        "class ScoredSection:\n"
        "    section: object\n"
        "    skill_name: str\n"
        "    raw_score: float\n"
        "    normalized_score: float\n\n"
        "@dataclass\n"
        "class DistillConfig:\n"
        "    token_budget: int = 4000\n"
        "    threshold: float = 0.3\n"
        "    stop_words: frozenset = field(default_factory=lambda: DEFAULT_STOP_WORDS)\n\n"
        "@dataclass\n"
        "class DistillResult:\n"
        "    prompt: str = ''\n"
        "    tokens_used: int = 0\n"
        "    tokens_full: int = 0\n"
        "    skills_included: int = 0\n"
        "    sections_included: int = 0\n"
        "    sections_total: int = 0\n\n"
        "def estimate_tokens(text):\n"
        "    return len(text) // 4\n\n"
        "def parse_skill_file(path):\n"
        "    return ('fake', [], [])\n\n"
        "def score_section(task_tokens, section, stop_words):\n"
        "    return 0.0\n\n"
        f"def distill(task_description, skill_paths, config=None):\n"
        f"    raise {exception_class}({repr(exception_msg)})\n"
    )
    fake_file.write_text(content, encoding="utf-8")


def _run_with_broken_distiller(tmp_path, task, exception_class, exception_msg):
    """Run local_coder with a fake distiller that raises on distill()."""
    fake_dir = tmp_path / "fake_modules"
    _make_fake_distiller_file(fake_dir, exception_class, exception_msg)

    # Bootstrap: pre-import fake distiller, then exec local_coder.py
    bootstrap_lines = [
        "import sys",
        "import os",
        "from unittest.mock import patch, MagicMock",
        "",
        f"sys.path.insert(0, r'{fake_dir}')",
        "import distiller",
        "",
        f"scripts_dir = r'{SCRIPTS_DIR}'",
        "if scripts_dir not in sys.path:",
        "    sys.path.append(scripts_dir)",
        "",
        f"workspace = r'{WORKSPACE_ROOT}'",
        "if workspace not in sys.path:",
        "    sys.path.append(workspace)",
        "",
        "os.chdir(workspace)",
        "",
        "mock_response = MagicMock()",
        "mock_response.status_code = 200",
        "mock_response.json.return_value = {",
        '    "response": "def hello(): pass",',
        '    "total_duration": 1000000000,',
        '    "eval_count": 10,',
        "}",
        "mock_response.raise_for_status = lambda: None",
        "",
        f"sys.argv = ['local_coder.py', '--task', {repr(task)}, '--distill']",
        "",
        f"script_path = r'{LOCAL_CODER_SCRIPT}'",
        "with open(script_path, 'r', encoding='utf-8') as f:",
        "    code = f.read()",
        "",
        "with patch('requests.post', return_value=mock_response):",
        "    exec(compile(code, script_path, 'exec'), {'__name__': '__main__', '__file__': script_path})",
    ]
    bootstrap = "\n".join(bootstrap_lines)

    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"

    result = subprocess.run(
        [sys.executable, "-c", bootstrap],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(WORKSPACE_ROOT),
        timeout=30,
        encoding="utf-8",
        errors="replace",
    )
    return result


def test_fallback_on_distiller_runtime_error(tmp_path):
    """When distiller.distill() raises RuntimeError, local_coder falls back.

    Verifies:
    - Script does NOT crash with non-zero exit code
    - stderr contains '[DISTILL] ERROR:' with exception message
    - stderr contains '[DISTILL] Falling back to verbatim injection'
    """
    result = _run_with_broken_distiller(
        tmp_path,
        task="Build a REST API",
        exception_class="RuntimeError",
        exception_msg="Simulated distiller failure for testing",
    )

    assert result.returncode == 0, (
        f"Expected exit code 0 but got {result.returncode}.\n"
        f"stderr: {result.stderr[:500]}"
    )
    assert "[DISTILL] ERROR:" in result.stderr
    assert "Simulated distiller failure for testing" in result.stderr
    assert "[DISTILL] Falling back to verbatim injection" in result.stderr


def test_fallback_stderr_warning_format(tmp_path):
    """Stderr error line format: [DISTILL] ERROR: <message>.

    Verifies:
    - Exactly one '[DISTILL] ERROR:' line with the exception message
    - Exactly one '[DISTILL] Falling back to verbatim injection' line
    """
    result = _run_with_broken_distiller(
        tmp_path,
        task="Write unit tests",
        exception_class="ValueError",
        exception_msg="skill file encoding error: invalid UTF-8",
    )

    assert result.returncode == 0, f"stderr: {result.stderr[:400]}"

    stderr_lines = result.stderr.splitlines()

    error_lines = [l for l in stderr_lines if "[DISTILL] ERROR:" in l]
    assert len(error_lines) == 1, f"Expected 1 error line, got: {error_lines}"
    assert "skill file encoding error: invalid UTF-8" in error_lines[0]

    fallback_lines = [l for l in stderr_lines if "[DISTILL] Falling back to verbatim injection" in l]
    assert len(fallback_lines) == 1


def test_fallback_continues_execution(tmp_path):
    """After fallback, script continues to call Ollama and produce output."""
    result = _run_with_broken_distiller(
        tmp_path,
        task="Implement pagination",
        exception_class="OSError",
        exception_msg="Permission denied reading skill files",
    )

    assert result.returncode == 0, f"stderr: {result.stderr[:400]}"
    # The mocked Ollama response is "def hello(): pass"
    assert "def hello(): pass" in result.stdout


def test_fallback_on_module_not_found_error(tmp_path):
    """ModuleNotFoundError inside distill() triggers graceful fallback."""
    result = _run_with_broken_distiller(
        tmp_path,
        task="Add caching layer",
        exception_class="ModuleNotFoundError",
        exception_msg="No module named 'nonexistent_dependency'",
    )

    assert result.returncode == 0, f"stderr: {result.stderr[:400]}"
    assert "[DISTILL] ERROR:" in result.stderr
    assert "No module named 'nonexistent_dependency'" in result.stderr
    assert "[DISTILL] Falling back to verbatim injection" in result.stderr
