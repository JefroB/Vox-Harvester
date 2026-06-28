"""E2E test environment configuration for Vox Harvester pipeline tests.

Provides isolated test environments that override production database and
audio directory paths, with cleanup and production integrity verification.

Validates: Requirements 5.1, 5.2, 5.3, 5.6
"""

import hashlib
import os
import shutil
from pathlib import Path

import pytest

# Project root is two levels up from tests/e2e/conftest.py
PROJECT_ROOT = Path(__file__).parent.parent.parent
PRODUCTION_DB_PATH = PROJECT_ROOT / "vocal_harvester_db.json"
PRODUCTION_SAMPLES_DIR = PROJECT_ROOT / "harvested_samples"


def _hash_file(file_path: Path) -> str:
    """Compute SHA-256 hash of a file's contents."""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _hash_directory(dir_path: Path) -> dict[str, str]:
    """Compute SHA-256 hashes for all files in a directory (non-recursive)."""
    if not dir_path.exists():
        return {}
    return {
        file.name: _hash_file(file)
        for file in sorted(dir_path.iterdir())
        if file.is_file()
    }


@pytest.fixture
def test_env(tmp_path):
    """Configure isolated test environment with temporary DB and audio dir.

    Returns a dict with TEST_DB_FILE and TEST_AUDIO_DIR paths, and sets
    corresponding environment variables for the server to read.
    """
    test_db_file = tmp_path / "test_db.json"
    test_audio_dir = tmp_path / "test_audio"
    test_audio_dir.mkdir(parents=True, exist_ok=True)

    # Set env vars so the server uses test paths instead of production
    os.environ["TEST_DB_FILE"] = str(test_db_file)
    os.environ["TEST_AUDIO_DIR"] = str(test_audio_dir)

    yield {
        "TEST_DB_FILE": str(test_db_file),
        "TEST_AUDIO_DIR": str(test_audio_dir),
    }

    # Clean up env vars after test
    os.environ.pop("TEST_DB_FILE", None)
    os.environ.pop("TEST_AUDIO_DIR", None)


@pytest.fixture(autouse=True)
def auto_cleanup(test_env):
    """Autouse fixture that cleans up test-generated files after each test.

    Removes the test database file and test audio directory regardless of
    whether the test passed or failed.
    """
    yield

    test_db_path = Path(test_env["TEST_DB_FILE"])
    test_audio_dir = Path(test_env["TEST_AUDIO_DIR"])

    if test_db_path.exists():
        test_db_path.unlink()

    if test_audio_dir.exists():
        shutil.rmtree(test_audio_dir)


@pytest.fixture(scope="session", autouse=True)
def verify_production_unmodified():
    """Session-scoped fixture verifying production data is never modified.

    Records SHA-256 hashes of the production database and harvested_samples
    directory before tests run, then asserts they are unchanged after all
    tests complete.
    """
    # Record state before tests
    db_hash_before = None
    if PRODUCTION_DB_PATH.exists():
        db_hash_before = _hash_file(PRODUCTION_DB_PATH)

    samples_hashes_before = _hash_directory(PRODUCTION_SAMPLES_DIR)

    yield

    # Verify state after tests
    if db_hash_before is not None:
        assert PRODUCTION_DB_PATH.exists(), (
            f"Production database was deleted: {PRODUCTION_DB_PATH}"
        )
        db_hash_after = _hash_file(PRODUCTION_DB_PATH)
        assert db_hash_after == db_hash_before, (
            f"Production database was modified: {PRODUCTION_DB_PATH}"
        )

    samples_hashes_after = _hash_directory(PRODUCTION_SAMPLES_DIR)
    assert samples_hashes_after == samples_hashes_before, (
        "Production harvested_samples/ directory contents were modified"
    )
