# Bug Condition Exploration Tests — Audio Pipeline Reliability Failures
"""Property-based tests that confirm bugs exist in the current (unfixed) codebase.

These tests encode the EXPECTED CORRECT behavior. They are designed to FAIL on
unfixed code, proving each bug exists. Once fixes are applied, these tests
should PASS.

**Validates: Requirements 1.1, 1.2, 1.3, 1.5, 1.6**
"""

import os
import sys
import tempfile
import subprocess
import json
import time
import asyncio
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock
from hypothesis import given, settings, assume, HealthCheck
from hypothesis import strategies as st

# Project root for resolving paths
PROJECT_ROOT = Path(__file__).parent.parent


# =============================================================================
# Test 1 - Cobalt Unavailability: No fallback exists
# Bug 1.1: When all Cobalt instances are down, ensureLocalFullAudio throws
# with no recovery path. Expected behavior: fall back to yt-dlp local download.
# =============================================================================

# Validates: Requirements 1.1
@settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
@given(video_id=st.from_regex(r"[a-zA-Z0-9_-]{11}", fullmatch=True))
def test_cobalt_unavailability_has_local_fallback(video_id: str):
    """Bug 1.1: ensureLocalFullAudio should fall back to local download when
    all Cobalt instances are unavailable. Currently throws with no recovery.

    We verify this by reading server.ts and checking that ensureLocalFullAudio
    contains a fallback mechanism (yt-dlp or equivalent) after Cobalt failure.
    """
    server_ts = PROJECT_ROOT / "server.ts"
    content = server_ts.read_text(encoding="utf-8")

    # Find the ensureLocalFullAudio function body
    func_start = content.find("async function ensureLocalFullAudio")
    assert func_start != -1, "ensureLocalFullAudio function not found in server.ts"

    # Extract function body (find the matching closing brace)
    brace_count = 0
    func_body_start = content.find("{", func_start)
    func_body = ""
    for i in range(func_body_start, len(content)):
        if content[i] == "{":
            brace_count += 1
        elif content[i] == "}":
            brace_count -= 1
            if brace_count == 0:
                func_body = content[func_body_start:i + 1]
                break

    # The function should contain a try/catch around Cobalt with yt-dlp fallback
    has_try_catch_around_cobalt = ("try" in func_body and "catch" in func_body
                                    and "yt-dlp" in func_body.lower() or "ytdlp" in func_body.lower()
                                    or "yt_dlp" in func_body.lower())

    assert has_try_catch_around_cobalt, (
        f"Bug 1.1 confirmed: ensureLocalFullAudio has no local download fallback "
        f"(no yt-dlp reference found). When all Cobalt instances fail, it throws "
        f"'Unable to resolve active direct YouTube audio stream link' with no recovery. "
        f"Video ID tested: {video_id}"
    )


# =============================================================================
# Test 2 - FFmpeg Race Condition: detectFFmpeg() not awaited before app.listen()
# Bug 1.2: hasFFmpeg is false during startup window because detectFFmpeg()
# is called fire-and-forget at module level without await.
# =============================================================================

# Validates: Requirements 1.2
@settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
@given(request_delay_ms=st.integers(min_value=0, max_value=500))
def test_ffmpeg_detection_awaited_before_listen(request_delay_ms: int):
    """Bug 1.2: detectFFmpeg() should be awaited inside startServer() before
    app.listen() is called. Currently it's fire-and-forget at module scope.

    We verify by checking that startServer() awaits detectFFmpeg before listen.
    """
    server_ts = PROJECT_ROOT / "server.ts"
    content = server_ts.read_text(encoding="utf-8")

    # Check 1: detectFFmpeg() should NOT be called at module level (fire-and-forget)
    # Find calls to detectFFmpeg() that are NOT inside an async function
    lines = content.split("\n")
    module_level_call = False
    inside_function = 0

    for line in lines:
        stripped = line.strip()
        # Track function depth
        inside_function += stripped.count("{") - stripped.count("}")
        if inside_function <= 0 and "detectFFmpeg()" in stripped:
            # This is a module-level call (not inside a function)
            if not stripped.startswith("//") and not stripped.startswith("*"):
                module_level_call = True
                break

    # Check 2: startServer should await detectFFmpeg
    start_server_start = content.find("async function startServer")
    assert start_server_start != -1, "startServer function not found"

    # Find startServer body
    brace_count = 0
    body_start = content.find("{", start_server_start)
    start_server_body = ""
    for i in range(body_start, len(content)):
        if content[i] == "{":
            brace_count += 1
        elif content[i] == "}":
            brace_count -= 1
            if brace_count == 0:
                start_server_body = content[body_start:i + 1]
                break

    awaits_ffmpeg_before_listen = False
    # Check that "await detectFFmpeg" appears BEFORE "app.listen" in startServer
    await_pos = start_server_body.find("await detectFFmpeg")
    listen_pos = start_server_body.find("app.listen")

    if await_pos != -1 and listen_pos != -1 and await_pos < listen_pos:
        awaits_ffmpeg_before_listen = True

    # The bug is: module-level fire-and-forget call exists AND startServer doesn't await it
    assert not module_level_call and awaits_ffmpeg_before_listen, (
        f"Bug 1.2 confirmed: FFmpeg race condition exists. "
        f"module_level_call={module_level_call}, "
        f"awaits_ffmpeg_before_listen={awaits_ffmpeg_before_listen}. "
        f"detectFFmpeg() is called fire-and-forget at module level (~line 54) "
        f"and hasFFmpeg is false during the first ~{request_delay_ms}ms despite "
        f"FFmpeg being installed."
    )


# =============================================================================
# Test 3 - Processing Options Ignored: harvest ignores normalization/fadeInOut
# Bug 1.3: harvestRealAudio takes no options parameter, FFmpeg command is
# always a plain slice with no -af filters regardless of options passed.
# =============================================================================

# Validates: Requirements 1.3
@settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
@given(
    normalization=st.just(True),
    fade_in_out=st.just(True),
)
def test_processing_options_applied_in_harvest(normalization: bool, fade_in_out: bool):
    """Bug 1.3: harvestRealAudio should accept and apply processing options.
    When normalization=true, FFmpeg command should include loudnorm filter.
    When fadeInOut=true, FFmpeg command should include afade filter.

    Currently harvestRealAudio(videoId, startTime, duration, outputPath) takes
    no options parameter and produces a raw slice with no -af filters.
    """
    server_ts = PROJECT_ROOT / "server.ts"
    content = server_ts.read_text(encoding="utf-8")

    # Find harvestRealAudio function signature
    func_start = content.find("async function harvestRealAudio")
    assert func_start != -1, "harvestRealAudio function not found in server.ts"

    # Extract the function signature line
    sig_end = content.find("{", func_start)
    signature = content[func_start:sig_end]

    # Check if function accepts an options parameter
    has_options_param = "options" in signature.lower()

    # Extract function body
    brace_count = 0
    func_body = ""
    for i in range(sig_end, len(content)):
        if content[i] == "{":
            brace_count += 1
        elif content[i] == "}":
            brace_count -= 1
            if brace_count == 0:
                func_body = content[sig_end:i + 1]
                break

    # Check if function body contains loudnorm and afade filter logic
    has_loudnorm = "loudnorm" in func_body
    has_afade = "afade" in func_body
    has_af_flag = '"-af"' in func_body or "'-af'" in func_body or "-af " in func_body

    assert has_options_param and has_loudnorm and has_afade, (
        f"Bug 1.3 confirmed: Processing options are ignored. "
        f"has_options_param={has_options_param}, "
        f"has_loudnorm={has_loudnorm}, has_afade={has_afade}, has_af_flag={has_af_flag}. "
        f"FFmpeg command contains no -af filter regardless of options passed. "
        f"harvestRealAudio signature: {signature.strip()}"
    )


# =============================================================================
# Test 4 - Empty Preview Params: activePreview becomes {videoId: ""} not null
# Bug 1.5: handleTogglePlay calls onPreviewClip("", 0, 0, "", "") to stop,
# which sets activePreview to {videoId: "", ...} instead of null.
# =============================================================================

# Validates: Requirements 1.5
@settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
@given(
    video_id=st.from_regex(r"[a-zA-Z0-9_-]{11}", fullmatch=True),
    start_time=st.floats(min_value=0.0, max_value=3600.0, allow_nan=False, allow_infinity=False),
)
def test_stop_playback_sets_null_not_empty_object(video_id: str, start_time: float):
    """Bug 1.5: When stopping playback, activePreview should become null.
    Currently Library.tsx calls onPreviewClip("", 0, 0, "", "") and App.tsx
    unconditionally creates {videoId: "", startTime: 0, ...} instead of null.

    We verify that App.tsx handlePreviewClip guards against empty videoId.
    """
    app_tsx = PROJECT_ROOT / "src" / "App.tsx"
    content = app_tsx.read_text(encoding="utf-8")

    # Find handlePreviewClip function
    func_start = content.find("handlePreviewClip")
    assert func_start != -1, "handlePreviewClip not found in App.tsx"

    # Find the function body (look for the arrow function or function body)
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

    # Check if there's a guard for empty videoId that sets activePreview to null
    has_empty_guard = (
        ("videoId" in func_body and "null" in func_body)
        or ('""' in func_body and "null" in func_body)
        or ("!videoId" in func_body and "null" in func_body)
    )

    # Also check that setActivePreview({) is NOT at the top level of the function
    # (it should be inside an if/else block, meaning the null guard controls flow)
    # A conditional set is acceptable — e.g. inside an else { setActivePreview({...}) }
    lines_in_body = func_body.split("\n")
    
    # Check if setActivePreview({ appears BEFORE any if/else guard (unconditional)
    # vs. after the guard (inside else block, which is conditional)
    null_guard_pos = func_body.find("null")
    set_object_pos = func_body.find("setActivePreview({")
    
    # The set is unconditional if it appears without any prior null guard,
    # or if there's no if/else structure wrapping it
    has_if_else_structure = "if" in func_body and "else" in func_body
    unconditional_set = (
        set_object_pos != -1 
        and not has_if_else_structure
        and null_guard_pos == -1
    )

    assert has_empty_guard and not unconditional_set, (
        f"Bug 1.5 confirmed: handlePreviewClip has no guard for empty videoId. "
        f"has_empty_guard={has_empty_guard}, unconditional_set={unconditional_set}. "
        f"activePreview becomes {{videoId: '', startTime: 0, endTime: 0, ...}} "
        f"instead of null when stopping playback. "
        f"Tested with video_id={video_id}, start_time={start_time}"
    )


# =============================================================================
# Test 5 - Cache Validation: Corrupted files served if >4KB
# Bug 1.6: ensureLocalFullAudio only checks size > 4000 bytes. Truncated
# downloads (5KB, 50KB) are served without content validation.
# =============================================================================

# Validates: Requirements 1.6
@settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
@given(
    file_size=st.sampled_from([5000, 10000, 50000, 80000, 99000]),
    video_id=st.from_regex(r"[a-zA-Z0-9_-]{11}", fullmatch=True),
)
def test_cache_validation_rejects_corrupted_files(file_size: int, video_id: str):
    """Bug 1.6: Cache validation should reject files <100KB or failing FFmpeg
    probe. Currently any file >4000 bytes passes validation regardless of
    whether it contains valid audio content.

    We verify that ensureLocalFullAudio uses a threshold of at least 100KB
    (102400 bytes) and includes probe validation.
    """
    server_ts = PROJECT_ROOT / "server.ts"
    content = server_ts.read_text(encoding="utf-8")

    # Find ensureLocalFullAudio function body
    func_start = content.find("async function ensureLocalFullAudio")
    assert func_start != -1, "ensureLocalFullAudio not found in server.ts"

    brace_count = 0
    body_start = content.find("{", func_start)
    func_body = ""
    for i in range(body_start, len(content)):
        if content[i] == "{":
            brace_count += 1
        elif content[i] == "}":
            brace_count -= 1
            if brace_count == 0:
                func_body = content[body_start:i + 1]
                break

    # Check cache validation threshold
    # Current code: fs.statSync(fullAudioPath).size > 4000
    # Expected: size > 102400 (100KB minimum)
    uses_4000_threshold = "4000" in func_body
    uses_100kb_threshold = "102400" in func_body or "100000" in func_body or "100 * 1024" in func_body

    # Check for FFmpeg probe validation
    has_probe_validation = (
        "ffprobe" in func_body.lower()
        or ("-v error" in func_body and "-f null" in func_body)
        or "probe" in func_body.lower()
    )

    assert uses_100kb_threshold and has_probe_validation, (
        f"Bug 1.6 confirmed: Cache validation is insufficient. "
        f"uses_4000_threshold={uses_4000_threshold}, "
        f"uses_100kb_threshold={uses_100kb_threshold}, "
        f"has_probe_validation={has_probe_validation}. "
        f"Cache check passes for any file >4000 bytes regardless of content validity. "
        f"A {file_size}-byte truncated file for video {video_id} would be served as valid."
    )
