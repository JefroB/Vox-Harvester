# Requirements Document

## Introduction

End-to-end audio validation for the Vox Harvester pipeline. This feature adds a speech-to-text (STT) transcription component using Whisper locally, a full Playwright E2E test suite that validates the entire search-harvest-transcribe pipeline, and test harnesses (unit/integration) for the audio analysis subsystem. The goal is to prove that searched-for vocal content actually appears in the audio the app harvests.

## Glossary

- **Transcription_Service**: The Node.js/Python integration layer that accepts a WAV audio file and returns structured transcription output (text, word timestamps, confidence scores) by invoking Whisper locally.
- **Whisper**: The openai-whisper Python package performing local speech-to-text inference on audio files.
- **E2E_Test_Suite**: The Playwright-based end-to-end test suite exercising the full Vox Harvester pipeline from UI search through harvest to transcription validation.
- **Audio_Preprocessor**: The FFmpeg-based component that converts harvested WAV files (44.1kHz mono 16-bit) to Whisper-compatible format (16kHz mono WAV).
- **Search_Term**: A text query used to search YouTube for vocal content via the application UI.
- **Harvested_Sample**: A WAV audio file (44.1kHz mono 16-bit) sliced from a YouTube video and stored in the `harvested_samples/` directory.
- **Transcript**: The structured text output from running STT on a Harvested_Sample, containing words, timestamps, and confidence scores.
- **Relevance_Score**: A numeric measure (0.0–1.0) indicating how closely a Transcript matches the original Search_Term, computed via normalized token overlap.
- **Test_Harness**: Unit and integration test infrastructure for the Transcription_Service and Audio_Preprocessor components.
- **Pipeline**: The full sequence: UI search → API call → YouTube download → FFmpeg slice → WAV storage → transcription → text comparison.

## Requirements

### Requirement 1: Audio Preprocessing for STT

**User Story:** As a developer, I want harvested audio samples to be converted to Whisper-compatible format before transcription, so that STT inference runs efficiently and accurately.

#### Acceptance Criteria

1. WHEN a Harvested_Sample at 48kHz is provided, THE Audio_Preprocessor SHALL produce a 16kHz mono 16-bit PCM WAV output file.
2. WHEN a Harvested_Sample at any other sample rate (e.g., 44.1kHz, 22.05kHz) is provided, THE Audio_Preprocessor SHALL still produce a valid 16kHz mono 16-bit PCM WAV output file.
3. WHEN the source Harvested_Sample is shorter than 0.5 seconds, THE Audio_Preprocessor SHALL return the converted file without error.
4. WHEN the source Harvested_Sample is longer than 300 seconds, THE Audio_Preprocessor SHALL segment the audio into sequential chunks of no more than 300 seconds with 5 seconds of overlap between adjacent chunks, producing one output file per chunk and returning the list of output file paths in chronological order.
5. IF the source file does not exist or is unreadable, THEN THE Audio_Preprocessor SHALL return a descriptive error including the file path.
6. IF the source file exists but contains invalid or corrupt audio data that cannot be decoded, THEN THE Audio_Preprocessor SHALL return a descriptive error indicating the file could not be decoded.
7. THE Audio_Preprocessor SHALL preserve the original Harvested_Sample file and write the preprocessed output to a separate path.

### Requirement 2: Local Speech-to-Text Transcription

**User Story:** As a developer, I want to transcribe harvested audio samples to text locally using Whisper, so that I can validate that the audio content matches the search intent without relying on cloud services.

#### Acceptance Criteria

1. WHEN a preprocessed 16kHz WAV file is provided, THE Transcription_Service SHALL invoke Whisper with the `tiny` model for test workloads and return a Transcript containing segments with word-level timestamps.
2. THE Transcription_Service SHALL produce output conforming to the TranscriptionResult interface (segments, language, duration, model fields).
3. WHEN Whisper produces word-level timestamps, THE Transcription_Service SHALL include each word's start time, end time, and confidence score (ranging from 0.0 to 1.0) in the output.
4. IF Whisper is not installed or fails to load, THEN THE Transcription_Service SHALL return an error indicating the dependency name ("openai-whisper") and the reason for the load failure.
5. IF the input audio file contains no detectable speech, THEN THE Transcription_Service SHALL return an empty segments array with duration set to the file length.
6. THE Transcription_Service SHALL cache Transcript results keyed by a SHA-256 hash of the audio file contents, and return cached results when the same file is transcribed again.
7. IF the input file is not a valid WAV file or cannot be decoded, THEN THE Transcription_Service SHALL return an error indicating the file path and the nature of the format problem without invoking Whisper.
8. IF Whisper does not return a result within 120 seconds, THEN THE Transcription_Service SHALL abort the transcription and return a timeout error indicating the elapsed duration and input file path.

### Requirement 3: Transcript-to-Search-Term Relevance Comparison

**User Story:** As a developer, I want to compare transcription output against the original search terms, so that I can programmatically verify the harvested audio contains relevant vocal content.

#### Acceptance Criteria

1. WHEN a Transcript and a Search_Term are provided, THE Transcription_Service SHALL compute a Relevance_Score as the ratio of matching stemmed tokens to total Search_Term tokens (|search_term_tokens ∩ transcript_tokens| / |search_term_tokens|), producing a value between 0.0 and 1.0 inclusive.
2. THE Transcription_Service SHALL normalize both inputs by lowercasing, removing all non-alphanumeric characters, splitting on whitespace, and applying Porter stemming before comparison.
3. WHEN the Relevance_Score exceeds a configurable threshold (default 0.3, valid range 0.0 to 1.0), THE Transcription_Service SHALL return a boolean `is_relevant` field set to true alongside the Relevance_Score.
4. WHEN no stemmed tokens from the Search_Term appear in the Transcript, THE Transcription_Service SHALL return a Relevance_Score of 0.0 and `is_relevant` set to false.
5. THE Transcription_Service SHALL produce an identical Relevance_Score when the same Search_Term and Transcript inputs are provided multiple times (deterministic output).
6. IF the Search_Term is empty or contains no alphanumeric characters after normalization, THEN THE Transcription_Service SHALL return an error indicating that the search term produced no valid tokens for comparison.

### Requirement 4: Playwright E2E Pipeline Validation

**User Story:** As a developer, I want a Playwright test suite that exercises the full Vox Harvester pipeline from search through harvest to transcription, so that I can verify end-to-end correctness in CI and locally.

#### Acceptance Criteria

1. THE E2E_Test_Suite SHALL use Playwright to navigate to the application at localhost:3000, enter a Search_Term, and trigger a search via the UI, using mocked API responses for `/api/search`, `/api/harvest`, and `/api/samples` to ensure deterministic test execution.
2. WHEN search results are displayed, THE E2E_Test_Suite SHALL select the first result card and trigger the harvest action, then wait for the `/api/harvest` response to confirm completion before proceeding.
3. WHEN a harvest completes, THE E2E_Test_Suite SHALL verify that a Harvested_Sample WAV file exists in the test output directory.
4. WHEN a Harvested_Sample is confirmed, THE E2E_Test_Suite SHALL run the Transcription_Service on the sample and verify the Transcript contains at least 1 segment with at least 1 word.
5. THE E2E_Test_Suite SHALL execute the pipeline with at least 3 different Search_Terms covering distinct vocal content categories (speech, interview, lecture).
6. WHEN a Transcript is obtained, THE E2E_Test_Suite SHALL compare the extracted text against the original Search_Term and assert a Relevance_Score above the configured threshold (default 0.3).
7. IF any pipeline step fails (search returns no results, harvest exceeds the 120-second timeout, or transcription errors), THEN THE E2E_Test_Suite SHALL produce a failure message identifying which step failed and the triggering condition, and capture a screenshot of the current page state.

### Requirement 5: E2E Test Configuration and Isolation

**User Story:** As a developer, I want E2E tests to be configurable and isolated from production data, so that tests are repeatable and do not corrupt the sample library.

#### Acceptance Criteria

1. THE E2E_Test_Suite SHALL set environment variables `TEST_DB_FILE` and `TEST_AUDIO_DIR` to override the production `vocal_harvester_db.json` and `harvested_samples/` paths, using a dedicated test database file and test output directory.
2. THE server SHALL read `TEST_DB_FILE` and `TEST_AUDIO_DIR` environment variables when present and use them in place of the default paths, ensuring test isolation without code modifications.
3. WHEN all tests in a run complete (whether passing or failing), THE E2E_Test_Suite SHALL clean up all test-generated audio files and the test database file.
4. THE E2E_Test_Suite SHALL configure a timeout of 120 seconds per test to account for download and transcription latency.
5. WHERE network access is unavailable, THE E2E_Test_Suite SHALL support a mock mode that stubs YouTube API responses and uses pre-recorded audio fixtures.
6. AFTER each test run, THE E2E_Test_Suite SHALL verify that the production `vocal_harvester_db.json` and `harvested_samples/` directory remain unmodified.

### Requirement 6: Unit Tests for Transcription Service

**User Story:** As a developer, I want unit tests for the transcription components, so that I can verify preprocessing, transcription, and relevance scoring work correctly in isolation.

#### Acceptance Criteria

1. THE Test_Harness SHALL include unit tests verifying that the Audio_Preprocessor, given a 48kHz mono 16-bit WAV fixture, produces an output file with a sample rate of 16kHz, mono channel, 16-bit depth, and a duration within 0.01 seconds of the input duration.
2. THE Test_Harness SHALL include unit tests verifying that the Relevance_Score computation returns 0.0 when no Search_Term tokens appear in the Transcript, returns 1.0 when all normalized tokens match exactly, and returns a value between 0.0 and 1.0 exclusive for partial overlap with at least one known expected value asserted to 2 decimal places.
3. THE Test_Harness SHALL include unit tests verifying that the Transcription_Service, given a known speech audio fixture, returns a TranscriptionResult containing non-empty segments, a language field, a duration greater than 0, a model field, and at least one word-level timestamp with start, end, and confidence fields.
4. THE Test_Harness SHALL include unit tests verifying that when the same audio file is transcribed twice, the second call returns an identical TranscriptionResult and the Whisper inference function is invoked exactly once (verified via mock or call-count spy).
5. THE Test_Harness SHALL include unit tests verifying that the Transcription_Service raises a defined error indicating the file path when the input file does not exist, raises a defined error indicating a format problem when the file is corrupt or zero-length, and raises a defined error indicating the unsupported format when a non-WAV file is provided.

### Requirement 7: Integration Tests for STT Pipeline

**User Story:** As a developer, I want integration tests that exercise the full STT pipeline (preprocess → transcribe → compare), so that I can verify the components work together correctly.

#### Acceptance Criteria

1. THE Test_Harness SHALL include integration tests that pass a known speech audio fixture (duration between 5 and 30 seconds) through Audio_Preprocessor then Transcription_Service and verify the Transcript contains at least 3 words from the fixture's ground-truth word list.
2. THE Test_Harness SHALL include integration tests verifying that the Relevance_Score for a fixture transcribed from a known speech matches the expected ground-truth value within a tolerance of 0.1.
3. THE Test_Harness SHALL include integration tests verifying the full pipeline handles an audio fixture with background noise (speech mixed with ambient sound) and produces a Transcript containing at least 1 segment with at least 1 word.
4. THE Test_Harness SHALL include integration tests verifying that segmented audio (from a fixture longer than 300 seconds) produces a stitched Transcript where words from overlap regions are not duplicated and segments appear in chronological order with no time gap exceeding 5 seconds between consecutive segment boundaries.
5. IF Whisper is not installed or fails to load in the test environment, THEN THE Test_Harness integration tests SHALL report pytest skip status with a message identifying the missing Whisper dependency rather than reporting error or failure status.
6. THE Test_Harness integration tests SHALL each complete within 120 seconds; IF a test exceeds this duration, THEN it SHALL be marked as failed with a timeout indication.

### Requirement 8: Transcription Result Pretty-Printing and Round-Trip

**User Story:** As a developer, I want to serialize and deserialize TranscriptionResult objects to/from JSON, so that cached transcripts can be stored and loaded reliably.

#### Acceptance Criteria

1. THE Transcription_Service SHALL serialize a TranscriptionResult to JSON format preserving all fields (segments, words, timestamps, confidence, language, duration, model), representing floating-point values with at most 6 decimal places of precision.
2. WHEN a JSON string containing all required TranscriptionResult fields with correct types is provided, THE Transcription_Service SHALL deserialize it into a valid TranscriptionResult object with all nested structures (segments containing words) reconstructed.
3. FOR ALL valid TranscriptionResult objects, serializing then deserializing SHALL produce an object where all string and integer fields are identical, and all floating-point fields (timestamps, confidence, duration) match within a tolerance of 1e-6.
4. WHEN a JSON string is malformed or missing required fields, THE Transcription_Service SHALL return a parse error that includes the name of the first missing or invalid field and whether the failure is due to absence, wrong type, or invalid value.
5. THE Transcription_Service SHALL format TranscriptionResult objects as human-readable text with one line per segment in the format `[<start>s-<end>s] <text>` where start and end are timestamps with 1 decimal place, and segments are separated by newline characters.
6. IF a TranscriptionResult contains an empty segments array, THEN THE Transcription_Service SHALL serialize it to valid JSON with an empty segments list, and the pretty-print output SHALL be an empty string.
