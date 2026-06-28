import json
from pathlib import Path

from src.audio_validation.models import TranscriptionResult
from src.audio_validation.serializer import TranscriptionSerializer


def test_empty_segments_serializes_to_valid_json():
    result = TranscriptionResult(
        segments=[],
        language='en',
        duration=5.0,
        model='tiny'
    )
    json_str = TranscriptionSerializer.to_json(result)
    
    assert isinstance(json.loads(json_str), dict)
    parsed_result = json.loads(json_str)
    assert parsed_result['segments'] == []


def test_empty_segments_pretty_print_returns_empty_string():
    result = TranscriptionResult(
        segments=[],
        language='en',
        duration=5.0,
        model='tiny'
    )
    pretty_str = TranscriptionSerializer.pretty_print(result)
    
    assert pretty_str == ''


def test_fixture_deserializes_correctly():
    fixture_path = Path(__file__).parent / 'fixtures' / 'expected_transcript.json'
    with open(fixture_path, 'r') as file:
        json_str = file.read()
    
    result = TranscriptionSerializer.from_json(json_str)
    
    assert isinstance(result, TranscriptionResult)
    assert len(result.segments) == 1
    assert len(result.segments[0].words) == 6
    assert result.language == 'en'
    assert result.duration == 5.0
    assert result.model == 'tiny'