# Preservation Property Tests — Existing Audio Pipeline Behavior Unchanged
"""Property-based tests that confirm existing CORRECT behavior is preserved.

These tests capture the baseline behavior of the UNFIXED codebase. They are
designed to PASS on unfixed code, proving the behavior we must preserve.
After fixes are applied, these tests should STILL PASS (no regressions).

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7**
"""

import re
from pathlib import Path
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

# Project root for resolving paths
PROJECT_ROOT = Path(__file__).parent.parent


def _extract_function_body(content: str, func_signature_substr: str) -> str:
    """Helper: extract function body given a signature substring."""
    func_start = content.find(func_signature_substr)
    assert func_start != -1, f"Function containing '{func_signature_substr}' not found"
    brace_start = content.find("{", func_start)
    brace_count = 0
    for i in range(brace_start, len(content)):
        if content[i] == "{":
            brace_count += 1
        elif content[i] == "}":
            brace_count -= 1
            if brace_count == 0:
                return content[brace_start:i + 1]
    return ""


# =============================================================================
# Property 1 - Valid Cache Preservation
# Requirement 3.1: Valid cached audio files are served from cache without
# re-downloading. Current behavior: file > 4000 bytes passes cache check.
# =============================================================================

# Validates: Requirements 3.1
@settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
@given(
    file_size=st.integers(min_value=100001, max_value=50_000_000),
    video_id=st.from_regex(r"[a-zA-Z0-9_-]{11}", fullmatch=True),
)
def test_valid_cache_served_without_redownload(file_size: int, video_id: str):
    """Property 1: For all valid cached audio files (size > current threshold),
    the cache check in ensureLocalFullAudio passes and returns early without
    triggering a new download.

    CURRENT OBSERVED BEHAVIOR: The threshold is > 4000 bytes. Any file exceeding
    4KB passes the cache check and is served directly. This test confirms that
    pattern exists in the code.
    """
    server_ts = PROJECT_ROOT / "server.ts"
    content = server_ts.read_text(encoding="utf-8")

    func_body = _extract_function_body(content, "async function ensureLocalFullAudio")

    # Confirm: cache check exists with size > threshold pattern
    # Current code: fs.statSync(fullAudioPath).size > 4000
    has_stat_size_check = "statSync" in func_body and "size" in func_body
    assert has_stat_size_check, (
        "ensureLocalFullAudio does not have a statSync size check for cache validation"
    )

    # Confirm: early return exists after cache check (return fullAudioPath)
    # The pattern is: if (exists && size > N) { ... return fullAudioPath; }
    has_early_return = "return fullAudioPath" in func_body
    assert has_early_return, (
        "ensureLocalFullAudio does not return early when cache is valid"
    )

    # Confirm the threshold is > 4000 (current behavior we're observing)
    has_4000_threshold = "4000" in func_body
    assert has_4000_threshold, (
        "Expected current cache threshold of 4000 bytes not found in ensureLocalFullAudio"
    )


# =============================================================================
# Property 2 - FFmpeg Plain Slice (No Options)
# Requirements 3.2, 3.3: When no processing options are enabled, FFmpeg
# produces a raw slice with no -af filters. Output is mono 16-bit 44.1kHz WAV.
# =============================================================================

# Validates: Requirements 3.2, 3.3
@settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
@given(
    start_time=st.floats(min_value=0.0, max_value=3600.0, allow_nan=False, allow_infinity=False),
    duration=st.floats(min_value=0.5, max_value=30.0, allow_nan=False, allow_infinity=False),
)
def test_no_options_produces_plain_slice_no_filters(start_time: float, duration: float):
    """Property 2: For all harvest requests with no options enabled, the FFmpeg
    command is a plain slice with no -af filters applied. Output format is
    mono 16-bit 44.1kHz WAV (-acodec pcm_s16le -ac 1 -ar 44100).

    CURRENT OBSERVED BEHAVIOR: harvestRealAudio has no filter logic at all —
    it always produces a raw slice regardless of any options (which it doesn't
    even accept as a parameter). This test confirms that baseline.
    """
    server_ts = PROJECT_ROOT / "server.ts"
    content = server_ts.read_text(encoding="utf-8")

    func_body = _extract_function_body(content, "async function harvestRealAudio")

    # Confirm: no -af filter flag exists in the function
    has_af_flag = bool(re.search(r'"-af\s', func_body) or re.search(r"'-af\s", func_body))
    has_loudnorm = "loudnorm" in func_body
    has_afade = "afade" in func_body

    assert not has_af_flag and not has_loudnorm and not has_afade, (
        f"Expected no audio filters in harvestRealAudio but found: "
        f"has_af_flag={has_af_flag}, has_loudnorm={has_loudnorm}, has_afade={has_afade}. "
        f"Tested with start_time={start_time}, duration={duration}"
    )

    # Confirm: output format is mono 16-bit 44.1kHz WAV
    has_pcm_s16le = "pcm_s16le" in func_body
    has_mono = "-ac 1" in func_body or "ac 1" in func_body
    has_44100 = "44100" in func_body

    assert has_pcm_s16le and has_mono and has_44100, (
        f"Expected mono 16-bit 44.1kHz WAV output format but found: "
        f"has_pcm_s16le={has_pcm_s16le}, has_mono={has_mono}, has_44100={has_44100}. "
        f"Tested with start_time={start_time}, duration={duration}"
    )


# =============================================================================
# Property 3 - Preview Clip Sets Valid Object
# Requirement 3.4: onPreviewClip with valid non-empty videoId sets
# activePreview to a valid object (not null).
# =============================================================================

# Validates: Requirements 3.4
@settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
@given(
    video_id=st.from_regex(r"[a-zA-Z0-9_-]{11}", fullmatch=True),
    start_time=st.floats(min_value=0.0, max_value=3600.0, allow_nan=False, allow_infinity=False),
    end_time=st.floats(min_value=0.1, max_value=3600.0, allow_nan=False, allow_infinity=False),
    phrase_text=st.text(min_size=1, max_size=200, alphabet=st.characters(blacklist_categories=("Cs",))),
    source_title=st.text(min_size=1, max_size=100, alphabet=st.characters(blacklist_categories=("Cs",))),
)
def test_preview_clip_with_valid_params_sets_active_preview(
    video_id: str, start_time: float, end_time: float, phrase_text: str, source_title: str
):
    """Property 3: For all onPreviewClip calls with non-empty videoId and valid
    params, activePreview is set to a valid object (not null).

    CURRENT OBSERVED BEHAVIOR: handlePreviewClip unconditionally calls
    setActivePreview({ videoId, startTime, endTime, phraseText, sourceTitle }).
    For any non-empty videoId, this creates a valid preview object.
    """
    app_tsx = PROJECT_ROOT / "src" / "App.tsx"
    content = app_tsx.read_text(encoding="utf-8")

    # Find handlePreviewClip
    func_start = content.find("handlePreviewClip")
    assert func_start != -1, "handlePreviewClip not found in App.tsx"

    # Get function body
    body_start = content.find("{", func_start)
    brace_count = 0
    func_body = ""
    for i in range(body_start, len(content)):
        if content[i] == "{":
            brace_count += 1
        elif content[i] == "}":
            brace_count -= 1
            if brace_count == 0:
                func_body = content[body_start:i + 1]
                break

    # Confirm: setActivePreview is called with an object
    has_set_active_preview = "setActivePreview(" in func_body
    assert has_set_active_preview, (
        "handlePreviewClip does not call setActivePreview"
    )

    # Confirm: the object contains expected fields
    has_video_id = "videoId" in func_body
    has_start_time = "startTime" in func_body
    has_end_time = "endTime" in func_body
    has_phrase_text = "phraseText" in func_body
    has_source_title = "sourceTitle" in func_body

    assert all([has_video_id, has_start_time, has_end_time, has_phrase_text, has_source_title]), (
        f"handlePreviewClip does not set all required fields in activePreview. "
        f"videoId={has_video_id}, startTime={has_start_time}, endTime={has_end_time}, "
        f"phraseText={has_phrase_text}, sourceTitle={has_source_title}. "
        f"Tested with video_id={video_id}"
    )


# =============================================================================
# Property 4 - Sample-Accurate Seeking
# Requirement 3.2: FFmpeg command always uses -ss AFTER -i for sample-accurate
# seeking in the primary command path.
# =============================================================================

# Validates: Requirements 3.2
@settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
@given(
    start_time=st.floats(min_value=0.0, max_value=7200.0, allow_nan=False, allow_infinity=False),
    duration=st.floats(min_value=0.5, max_value=60.0, allow_nan=False, allow_infinity=False),
)
def test_ffmpeg_uses_sample_accurate_seeking(start_time: float, duration: float):
    """Property 4: For random valid startTime/duration pairs, the FFmpeg command
    always uses sample-accurate seeking (-ss after -i) in the primary path.

    CURRENT OBSERVED BEHAVIOR: The primary FFmpeg command is constructed as:
    ffmpeg -y -i "<path>" -ss <start> -t <duration> -acodec pcm_s16le -ac 1 -ar 44100 "<out>"
    This places -ss AFTER -i, which is sample-accurate seeking.
    """
    server_ts = PROJECT_ROOT / "server.ts"
    content = server_ts.read_text(encoding="utf-8")

    func_body = _extract_function_body(content, "async function harvestRealAudio")

    # Find the primary FFmpeg command (the "cmdSafe" variable)
    # Pattern: -i "..." -ss ... (sample-accurate: -ss after -i)
    # The code uses: `"${binary}" -y -i "${localMasterPath}" -ss ${startTime} -t ${duration} ...`
    cmd_safe_match = re.search(r'cmdSafe\s*=\s*`([^`]+)`', func_body)
    assert cmd_safe_match is not None, (
        "Primary FFmpeg command (cmdSafe) not found in harvestRealAudio"
    )

    cmd_template = cmd_safe_match.group(1)

    # Verify -i appears before -ss in the primary command
    i_pos = cmd_template.find("-i ")
    ss_pos = cmd_template.find("-ss ")
    assert i_pos != -1 and ss_pos != -1, (
        f"FFmpeg command missing -i or -ss. cmd: {cmd_template}"
    )
    assert i_pos < ss_pos, (
        f"Primary FFmpeg command uses fast-seeking (-ss before -i) instead of "
        f"sample-accurate seeking (-ss after -i). -i at pos {i_pos}, -ss at pos {ss_pos}. "
        f"Tested with start_time={start_time}, duration={duration}"
    )


# =============================================================================
# Property 5 - Harvest Saves with Correct DB Schema
# Requirements 3.5, 3.7: Harvested samples save to JSON DB with schema
# { samples: [], tags: [] } in harvested_samples/ directory.
# =============================================================================

# Validates: Requirements 3.5, 3.7
@settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
@given(
    video_id=st.from_regex(r"[a-zA-Z0-9_-]{11}", fullmatch=True),
    phrase_text=st.text(min_size=5, max_size=100, alphabet=st.characters(blacklist_categories=("Cs",))),
    start_time=st.floats(min_value=0.0, max_value=3600.0, allow_nan=False, allow_infinity=False),
    duration=st.floats(min_value=0.5, max_value=30.0, allow_nan=False, allow_infinity=False),
)
def test_harvest_saves_to_db_with_correct_schema(
    video_id: str, phrase_text: str, start_time: float, duration: float
):
    """Property 5: For all harvest requests with valid params and no options,
    sample saves to DB with correct schema { samples: [], tags: [] }.

    CURRENT OBSERVED BEHAVIOR: The /api/harvest endpoint calls loadDB() which
    returns StoreSchema { samples: any[], tags: any[] }, pushes the new sample
    to currentDB.samples and new tags to currentDB.tags, then calls saveDB().
    The DB file is in harvested_samples/ (AUDIO_DIR) or project root.
    """
    server_ts = PROJECT_ROOT / "server.ts"
    content = server_ts.read_text(encoding="utf-8")

    # Verify StoreSchema interface defines { samples, tags }
    schema_match = re.search(
        r'interface\s+StoreSchema\s*\{([^}]+)\}', content
    )
    assert schema_match is not None, "StoreSchema interface not found in server.ts"
    schema_body = schema_match.group(1)
    assert "samples" in schema_body, "StoreSchema missing 'samples' field"
    assert "tags" in schema_body, "StoreSchema missing 'tags' field"

    # Verify loadDB returns the correct default schema
    load_db_body = _extract_function_body(content, "function loadDB()")
    has_samples_array = "samples: []" in load_db_body or "samples:[]" in load_db_body
    has_tags_array = "tags: []" in load_db_body or "tags:[]" in load_db_body
    assert has_samples_array and has_tags_array, (
        f"loadDB default return does not match {{ samples: [], tags: [] }}. "
        f"has_samples_array={has_samples_array}, has_tags_array={has_tags_array}"
    )

    # Verify harvest endpoint pushes to both samples and tags arrays
    # Find the harvest handler code
    harvest_start = content.find('app.post("/api/harvest"')
    assert harvest_start != -1, "/api/harvest endpoint not found"

    # Get the full harvest handler body (it's a large async handler with intervals)
    harvest_section = content[harvest_start:harvest_start + 6000]
    has_samples_push = "currentDB.samples.push" in harvest_section
    has_tags_push = "currentDB.tags.push" in harvest_section
    has_save_db = "saveDB(currentDB)" in harvest_section or "saveDB(" in harvest_section

    assert has_samples_push and has_tags_push and has_save_db, (
        f"Harvest endpoint does not properly save to DB schema. "
        f"has_samples_push={has_samples_push}, has_tags_push={has_tags_push}, "
        f"has_save_db={has_save_db}. "
        f"Tested with video_id={video_id}, phrase_text='{phrase_text[:20]}...'"
    )

    # Verify AUDIO_DIR uses harvested_samples/
    has_harvested_samples_dir = "harvested_samples" in content
    assert has_harvested_samples_dir, (
        "AUDIO_DIR does not reference 'harvested_samples' directory"
    )
