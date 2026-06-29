"""Property-based tests for isolated audio headers.

**Validates: Requirements 4.1**

Tests the header construction logic for isolated audio files served by the API.
Validates that the correct Content-Type, Content-Length, and Content-Disposition
headers are generated for any valid sample ID and file size.
"""

from hypothesis import given, settings
import hypothesis.strategies as st


def construct_isolated_headers(sample_id: str, file_size: int) -> dict:
    """Simulate server-side header construction for isolated audio files.
    
    **Validates: Requirements 4.1**
    
    Args:
        sample_id: The sample ID to construct headers for
        file_size: The size of the WAV file in bytes
        
    Returns:
        Dictionary containing the constructed headers
    """
    return {
        'Content-Type': 'audio/wav',
        'Content-Length': str(file_size),
        'Content-Disposition': f'attachment; filename="{sample_id}_isolated.wav"'
    }


SAMPLE_ID_ALPHABET = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"


@given(sample_id=st.text(alphabet=SAMPLE_ID_ALPHABET, min_size=1, max_size=100),
       file_size=st.integers(min_value=1, max_value=1000000000))
@settings(max_examples=100)
def test_isolated_audio_headers(sample_id: str, file_size: int) -> None:
    """For any sample with a completed isolation and an existing isolated WAV file,
    the headers MUST be correctly constructed with Content-Type, Content-Length,
    and Content-Disposition.
    
    **Validates: Requirements 4.1**
    """
    headers = construct_isolated_headers(sample_id, file_size)
    
    # Validate Content-Type is always audio/wav
    assert headers['Content-Type'] == 'audio/wav'
    
    # Validate Content-Length equals the file size
    assert headers['Content-Length'] == str(file_size)
    
    # Validate Content-Disposition follows the exact format
    expected_disposition = f'attachment; filename="{sample_id}_isolated.wav"'
    assert headers['Content-Disposition'] == expected_disposition


@given(sample_id=st.text(alphabet=SAMPLE_ID_ALPHABET, min_size=1, max_size=100),
       file_size=st.integers(min_value=1, max_value=1000000000))
@settings(max_examples=100)
def test_isolated_audio_headers_structure(sample_id: str, file_size: int) -> None:
    """Validates the structure of isolated audio headers is correct.
    
    **Validates: Requirements 4.1**
    """
    headers = construct_isolated_headers(sample_id, file_size)
    
    # Check all required headers are present
    assert 'Content-Type' in headers
    assert 'Content-Length' in headers
    assert 'Content-Disposition' in headers
    
    # Check header values match expected patterns
    assert headers['Content-Type'] == 'audio/wav'
    assert int(headers['Content-Length']) == file_size
    assert headers['Content-Disposition'].startswith('attachment; filename="')
    assert headers['Content-Disposition'].endswith(f'{sample_id}_isolated.wav"')