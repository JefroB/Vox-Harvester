"""E2E tests for the Vox Harvester pipeline.

Validates: Requirements 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 5.4, 5.5

Tests the complete audio harvesting and transcription pipeline using Playwright:
1. Navigate to app, enter search term, trigger search (mocked API)
2. Select first result, trigger harvest (mocked API copies fixture WAV)
3. Verify WAV file exists in test output directory
4. Run TranscriptionService on harvested sample
5. Score relevance of transcript against search term
6. Assert Relevance_Score > 0.3

All API responses are mocked via Playwright route interception for
deterministic execution. Pre-recorded audio fixtures are used when
network is unavailable (mock mode).
"""

import json
import shutil
from pathlib import Path

import pytest
from playwright.sync_api import Page, Route, expect

from audio_validation.scorer import RelevanceScorer
from audio_validation.transcriber import TranscriptionService

# Project root is two levels up from tests/e2e/test_pipeline_e2e.py
PROJECT_ROOT = Path(__file__).parent.parent.parent
FIXTURES_DIR = PROJECT_ROOT / "tests" / "fixtures"

# Search terms covering distinct vocal content categories (Req 4.5)
SEARCH_TERMS = [
    ("motivational speech", "speech"),
    ("tech interview", "interview"),
    ("university lecture", "lecture"),
]


def _mock_search_api(route: Route) -> None:
    """Mock /api/search to return a single deterministic result."""
    route.fulfill(
        status=200,
        content_type="application/json",
        body=json.dumps({
            "results": [
                {
                    "id": "test_video_123",
                    "title": "Test Video - Speech Content",
                    "channelName": "TestChannel",
                    "duration": "05:00",
                }
            ]
        }),
    )


def _make_harvest_handler(test_audio_dir: Path):
    """Create a harvest route handler that copies the fixture WAV to test dir.

    The mock simulates a successful harvest by copying the speech_5s.wav
    fixture into the test audio directory. This supports mock mode — no
    network access is required since the fixture is pre-recorded.
    """
    def handler(route: Route) -> None:
        fixture_path = FIXTURES_DIR / "speech_5s.wav"
        destination = test_audio_dir / "test_sample.wav"

        if not fixture_path.exists():
            route.fulfill(
                status=500,
                content_type="application/json",
                body=json.dumps({
                    "success": False,
                    "error": "Fixture speech_5s.wav not found; mock mode unavailable",
                }),
            )
            return

        # Copy fixture to test audio dir (simulates harvest download)
        test_audio_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(fixture_path, destination)

        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({
                "success": True,
                "filename": "test_sample.wav",
            }),
        )

    return handler


def _make_samples_handler(test_audio_dir: Path):
    """Create a samples route handler that lists WAV files in test dir."""
    def handler(route: Route) -> None:
        samples = []
        if test_audio_dir.exists():
            for wav_file in sorted(test_audio_dir.glob("*.wav")):
                samples.append({
                    "filename": wav_file.name,
                    "duration": 5.0,
                    "created": "2024-01-01T00:00:00Z",
                })

        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"samples": samples}),
        )

    return handler


def setup_mock_routes(page: Page, test_audio_dir: Path) -> None:
    """Register all mocked API routes on the Playwright page.

    Args:
        page: Playwright page instance.
        test_audio_dir: Isolated test audio directory from test_env fixture.
    """
    page.route("**/api/search", _mock_search_api)
    page.route("**/api/harvest", _make_harvest_handler(test_audio_dir))
    page.route("**/api/samples", _make_samples_handler(test_audio_dir))


@pytest.fixture
def test_audio_dir(test_env):
    """Extract and ensure test audio directory exists."""
    audio_dir = Path(test_env["TEST_AUDIO_DIR"])
    audio_dir.mkdir(parents=True, exist_ok=True)
    return audio_dir


@pytest.fixture
def screenshot_dir(tmp_path):
    """Directory for failure screenshots."""
    d = tmp_path / "screenshots"
    d.mkdir(exist_ok=True)
    return d


@pytest.mark.timeout(120)
@pytest.mark.parametrize(
    "search_term,category",
    SEARCH_TERMS,
    ids=["speech", "interview", "lecture"],
)
def test_pipeline_end_to_end(
    page: Page,
    test_env,
    test_audio_dir: Path,
    screenshot_dir: Path,
    search_term: str,
    category: str,
):
    """Test full pipeline: search -> harvest -> transcribe -> score relevance.

    Validates Requirements 4.1-4.7, 5.4, 5.5:
    - Mocked API responses ensure deterministic execution (4.1)
    - Selects first result and triggers harvest (4.2)
    - Verifies WAV exists in test output dir (4.3)
    - Runs TranscriptionService, checks >=1 segment with >=1 word (4.4)
    - Parametrized with 3 search terms (4.5)
    - Asserts Relevance_Score > 0.3 (4.6)
    - Captures screenshot on failure with step info (4.7)
    - 120s timeout per test (5.4)
    - Uses pre-recorded fixture for mock mode (5.5)
    """
    current_step = "setup"

    try:
        # Set up mocked API routes
        setup_mock_routes(page, test_audio_dir)

        # Step 1: Navigate to app (Req 4.1)
        current_step = "navigate"
        page.goto("http://localhost:3000")

        # Step 2: Enter search term and trigger search (Req 4.1)
        current_step = "search"
        search_input = page.get_by_placeholder("Search")
        expect(search_input).to_be_visible(timeout=10000)
        search_input.fill(search_term)

        search_button = page.get_by_role("button", name="Search")
        search_button.click()

        # Step 3: Wait for results and select first result (Req 4.2)
        current_step = "select_result"
        result_card = page.locator("[data-testid='search-result']").first
        expect(result_card).to_be_visible(timeout=10000)
        result_card.click()

        # Step 4: Trigger harvest and wait for completion (Req 4.2)
        current_step = "harvest"
        harvest_button = page.get_by_role("button", name="Harvest")
        expect(harvest_button).to_be_visible(timeout=10000)

        # Wait for the harvest API response
        with page.expect_response("**/api/harvest") as response_info:
            harvest_button.click()

        response = response_info.value
        assert response.status == 200, (
            f"Harvest API returned status {response.status}"
        )

        harvest_data = response.json()
        assert harvest_data.get("success") is True, (
            f"Harvest failed: {harvest_data.get('error', 'unknown')}"
        )

        # Step 5: Verify WAV file exists in test output directory (Req 4.3)
        current_step = "verify_wav"
        wav_files = list(test_audio_dir.glob("*.wav"))
        assert len(wav_files) >= 1, (
            f"No WAV files found in test audio directory: {test_audio_dir}"
        )
        sample_path = wav_files[0]

        # Step 6: Run TranscriptionService on harvested sample (Req 4.4)
        current_step = "transcribe"
        cache_dir = test_audio_dir / "_transcription_cache"
        cache_dir.mkdir(exist_ok=True)
        transcriber = TranscriptionService(model_name="tiny", cache_dir=cache_dir)
        transcript = transcriber.transcribe(sample_path)

        # Verify at least 1 segment with at least 1 word
        assert len(transcript.segments) >= 1, (
            "Transcript must contain at least 1 segment"
        )
        has_words = any(len(seg.words) >= 1 for seg in transcript.segments)
        assert has_words, (
            "At least one transcript segment must contain at least 1 word"
        )

        # Step 7: Compare transcript against search term (Req 4.6)
        current_step = "score_relevance"
        scorer = RelevanceScorer(threshold=0.3)
        result = scorer.score(transcript, search_term)

        assert result.score > 0.3, (
            f"Relevance score {result.score:.3f} is not above threshold 0.3 "
            f"for search term '{search_term}'. "
            f"Matched tokens: {result.matched_tokens}, "
            f"Search tokens: {result.search_tokens}"
        )

    except Exception as exc:
        # Capture screenshot on failure (Req 4.7)
        screenshot_name = f"failure_{category}_{current_step}.png"
        screenshot_path = screenshot_dir / screenshot_name

        try:
            page.screenshot(path=str(screenshot_path))
        except Exception:
            pass  # Don't mask the original failure

        # Re-raise with step context
        raise AssertionError(
            f"Pipeline failed at step '{current_step}' for search term "
            f"'{search_term}' (category: {category}): {exc}"
        ) from exc
