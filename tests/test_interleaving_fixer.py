import pytest
import json
from unittest.mock import Mock
from ai_metatagger.utils.interleaving_fixer import InterleavingFixer

@pytest.fixture
def mock_tracked_run(mocker):
    """Fixture to mock tracked_run in interleaving_fixer."""
    return mocker.patch('ai_metatagger.utils.interleaving_fixer.tracked_run')

@pytest.fixture
def mock_os_exists(mocker):
    """Fixture to mock os.path.exists so it doesn't fail on fake paths."""
    return mocker.patch('ai_metatagger.utils.interleaving_fixer.os.path.exists', return_value=True)

def test_needs_interleaving_fix_perfect_file(mock_tracked_run, mock_os_exists):
    """Test that a perfectly interleaved file returns False."""
    
    # 1. Mock streams (Video + 1 Audio)
    streams_json = json.dumps({
        "streams": [
            {"index": 0, "codec_type": "video"},
            {"index": 1, "codec_type": "audio"}
        ]
    })
    
    # 2. Mock packets (Video at pos 1000, Audio at pos 1500)
    # The delta is 500 bytes (well below 50MB threshold)
    packets_json = json.dumps({
        "packets": [
            {"stream_index": 0, "pos": "1000"},
            {"stream_index": 1, "pos": "1500"}
        ]
    })
    
    # Set the return values for the two tracked_run calls
    mock_tracked_run.side_effect = [
        Mock(stdout=streams_json, returncode=0),
        Mock(stdout=packets_json, returncode=0)
    ]
    
    result = InterleavingFixer.needs_interleaving_fix("perfect_movie.mkv")
    
    assert result is False
    assert mock_tracked_run.call_count == 2

def test_needs_interleaving_fix_extreme_offset(mock_tracked_run, mock_os_exists):
    """Test that a file with >50MB offset returns True."""
    
    streams_json = json.dumps({
        "streams": [
            {"index": 0, "codec_type": "video"},
            {"index": 1, "codec_type": "audio"}
        ]
    })
    
    # Video at pos 1,000,000. Audio at pos 60,000,000. Delta = 59MB.
    packets_json = json.dumps({
        "packets": [
            {"stream_index": 0, "pos": "1000000"},
            {"stream_index": 1, "pos": "60000000"}
        ]
    })
    
    mock_tracked_run.side_effect = [
        Mock(stdout=streams_json, returncode=0),
        Mock(stdout=packets_json, returncode=0)
    ]
    
    result = InterleavingFixer.needs_interleaving_fix("bad_movie.mkv")
    
    assert result is True

def test_needs_interleaving_fix_missing_audio_stream(mock_tracked_run, mock_os_exists):
    """Test that if an expected audio stream is physically missing from the cluster, it returns True."""
    
    # We expect 2 audio streams (Index 1 and 2)
    streams_json = json.dumps({
        "streams": [
            {"index": 0, "codec_type": "video"},
            {"index": 1, "codec_type": "audio"},
            {"index": 2, "codec_type": "audio"}
        ]
    })
    
    # But ffprobe only finds Video and Audio 2 in this 1-second read block.
    # Audio 1 is completely missing (like in Schindler's List).
    packets_json = json.dumps({
        "packets": [
            {"stream_index": 0, "pos": "1000"},
            {"stream_index": 2, "pos": "1500"}
        ]
    })
    
    mock_tracked_run.side_effect = [
        Mock(stdout=streams_json, returncode=0),
        Mock(stdout=packets_json, returncode=0)
    ]
    
    result = InterleavingFixer.needs_interleaving_fix("schindlers_liste_bad.mkv")
    
    # Should trigger extreme interleaving fix
    assert result is True

def test_fix_interleaving_success(mock_tracked_run, mocker):
    """Test that fix_interleaving runs the correct ffmpeg command and handles files."""
    
    # Mock os functions to simulate file replacement
    mock_exists = mocker.patch('ai_metatagger.utils.interleaving_fixer.os.path.exists', return_value=True)
    mock_remove = mocker.patch('ai_metatagger.utils.interleaving_fixer.os.remove')
    mock_move = mocker.patch('ai_metatagger.utils.interleaving_fixer.shutil.move')
    
    # tracked_run succeeds (return code 0)
    mock_tracked_run.return_value = Mock(returncode=0)
    
    result = InterleavingFixer.fix_interleaving("movie.mkv")
    
    assert result is True
    mock_remove.assert_called_once_with("movie.mkv")
    mock_move.assert_called_once_with("movie_fixed.mkv", "movie.mkv")
    
    # Check that ffmpeg command was constructed correctly
    expected_cmd = [
        "ffmpeg", "-y",
        "-i", "movie.mkv",
        "-i", "movie.mkv",
        "-i", "movie.mkv",
        "-map", "0:v?",     
        "-map", "1:a?",     
        "-map", "2:s?",     
        "-c", "copy",       
        "movie_fixed.mkv"
    ]
    mock_tracked_run.assert_called_once_with(expected_cmd, capture_output=True, text=True)
