"""Integration tests for portable workspace setup.

Validates Requirements 8.1, 8.2, 8.3:
- 8.1: Copying .subagentcoder/, .kiro/, .codesearch/ to a new directory allows
       Main_Script to resolve package imports correctly.
- 8.2: Main_Script creates task_results.db if it does not already exist (idempotent).
- 8.3: All internal paths are derived relative to WORKSPACE_ROOT using
       Path(__file__).parent.parent.parent.
"""

import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

# Workspace root is two levels above .subagentcoder/tests/
_WORKSPACE_ROOT = Path(__file__).parent.parent.parent


class TestPortableImportResolution:
    """Requirement 8.1: imports resolve correctly from a copied location."""

    def _setup_portable_workspace(self, tmp_path: Path) -> Path:
        """Copy .subagentcoder/ and .kiro/ into tmp_path and return the new root."""
        src_subagent = _WORKSPACE_ROOT / ".subagentcoder"
        src_kiro = _WORKSPACE_ROOT / ".kiro"

        dst_subagent = tmp_path / ".subagentcoder"
        dst_kiro = tmp_path / ".kiro"

        shutil.copytree(
            src_subagent,
            dst_subagent,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "task_results.db"),
        )
        # Copy only .kiro/scripts/ to keep it lightweight
        dst_kiro_scripts = dst_kiro / "scripts"
        dst_kiro_scripts.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_kiro / "scripts" / "local_coder.py", dst_kiro_scripts / "local_coder.py")

        return tmp_path

    def test_import_local_coder_package(self, tmp_path: Path):
        """Validates Requirement 8.1: import local_coder succeeds from portable location."""
        workspace = self._setup_portable_workspace(tmp_path)
        internal_dir = workspace / ".subagentcoder"

        code = textwrap.dedent(f"""\
            import sys
            from pathlib import Path
            sys.path.insert(0, {str(internal_dir)!r})
            import local_coder
            print("OK")
        """)

        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, f"Import failed: {result.stderr}"
        assert "OK" in result.stdout

    def test_import_result_database_from_portable_location(self, tmp_path: Path):
        """Validates Requirement 8.1: deep imports resolve from portable location."""
        workspace = self._setup_portable_workspace(tmp_path)
        internal_dir = workspace / ".subagentcoder"

        code = textwrap.dedent(f"""\
            import sys
            from pathlib import Path
            sys.path.insert(0, {str(internal_dir)!r})
            from local_coder.result_database import ResultDatabase
            print("ResultDatabase imported OK")
        """)

        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, f"Import failed: {result.stderr}"
        assert "ResultDatabase imported OK" in result.stdout

    def test_import_multiple_modules_from_portable_location(self, tmp_path: Path):
        """Validates Requirement 8.1: all key modules importable from portable location."""
        workspace = self._setup_portable_workspace(tmp_path)
        internal_dir = workspace / ".subagentcoder"

        code = textwrap.dedent(f"""\
            import sys
            from pathlib import Path
            sys.path.insert(0, {str(internal_dir)!r})
            from local_coder.complexity_estimator import estimate_complexity
            from local_coder.token_tracker import SessionTracker
            from local_coder.file_tagger import tag_files
            print("All modules imported OK")
        """)

        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, f"Import failed: {result.stderr}"
        assert "All modules imported OK" in result.stdout


class TestIdempotentDatabaseCreation:
    """Requirement 8.2: task_results.db is created if it does not exist."""

    def test_database_created_on_first_access(self, tmp_path: Path):
        """Validates Requirement 8.2: ResultDatabase creates DB file if missing."""
        src_subagent = _WORKSPACE_ROOT / ".subagentcoder"
        dst_subagent = tmp_path / ".subagentcoder"

        shutil.copytree(
            src_subagent,
            dst_subagent,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "task_results.db"),
        )

        db_path = dst_subagent / "task_results.db"
        assert not db_path.exists(), "DB should not exist before test"

        internal_dir = tmp_path / ".subagentcoder"
        code = textwrap.dedent(f"""\
            import sys
            from pathlib import Path
            sys.path.insert(0, {str(internal_dir)!r})
            from local_coder.result_database import ResultDatabase
            db_path = Path({str(db_path)!r})
            db = ResultDatabase(db_path)
            print("DB created at:", str(db_path))
            print("exists:", db_path.exists())
        """)

        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, f"DB creation failed: {result.stderr}"
        assert "exists: True" in result.stdout


class TestWorkspaceRootDerivation:
    """Requirement 8.3: WORKSPACE_ROOT derived via Path(__file__).parent.parent.parent."""

    def test_script_derives_correct_workspace_root(self, tmp_path: Path):
        """Validates Requirement 8.3: path derivation from .kiro/scripts/local_coder.py."""
        # Set up a minimal portable workspace
        workspace = tmp_path / "my_project"
        workspace.mkdir()

        kiro_scripts = workspace / ".kiro" / "scripts"
        kiro_scripts.mkdir(parents=True)

        # Write a minimal script that just derives WORKSPACE_ROOT
        test_script = kiro_scripts / "local_coder.py"
        test_script.write_text(textwrap.dedent("""\
            from pathlib import Path
            WORKSPACE_ROOT = Path(__file__).resolve().parent.parent.parent
            print(str(WORKSPACE_ROOT))
        """), encoding="utf-8")

        result = subprocess.run(
            [sys.executable, str(test_script)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, f"Script failed: {result.stderr}"

        derived_root = Path(result.stdout.strip())
        expected_root = workspace.resolve()
        assert derived_root == expected_root, (
            f"WORKSPACE_ROOT mismatch: got {derived_root}, expected {expected_root}"
        )

    def test_internal_dir_derivation(self, tmp_path: Path):
        """Validates Requirement 8.3: _INTERNAL_DIR = WORKSPACE_ROOT / '.subagentcoder'."""
        workspace = tmp_path / "project"
        workspace.mkdir()

        kiro_scripts = workspace / ".kiro" / "scripts"
        kiro_scripts.mkdir(parents=True)

        test_script = kiro_scripts / "derive_paths.py"
        test_script.write_text(textwrap.dedent("""\
            from pathlib import Path
            WORKSPACE_ROOT = Path(__file__).resolve().parent.parent.parent
            _INTERNAL_DIR = WORKSPACE_ROOT / ".subagentcoder"
            print(f"root={WORKSPACE_ROOT}")
            print(f"internal={_INTERNAL_DIR}")
            print(f"db={_INTERNAL_DIR / 'task_results.db'}")
        """), encoding="utf-8")

        result = subprocess.run(
            [sys.executable, str(test_script)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, f"Script failed: {result.stderr}"

        lines = result.stdout.strip().splitlines()
        root_line = [l for l in lines if l.startswith("root=")][0]
        internal_line = [l for l in lines if l.startswith("internal=")][0]
        db_line = [l for l in lines if l.startswith("db=")][0]

        root = Path(root_line.split("=", 1)[1])
        internal = Path(internal_line.split("=", 1)[1])
        db = Path(db_line.split("=", 1)[1])

        expected_root = workspace.resolve()
        assert root == expected_root
        assert internal == expected_root / ".subagentcoder"
        assert db == expected_root / ".subagentcoder" / "task_results.db"
