import pytest
import json
from unittest.mock import Mock
from ai_metatagger.core.ffmpeg_tools import generate_track_metadata

@pytest.fixture
def mock_tracked_run(mocker):
    return mocker.patch('ai_metatagger.core.ffmpeg_tools.tracked_run')

def test_generate_track_metadata_audio_and_subs(mock_tracked_run):
    """Test parsing of ffprobe output into database track dictionaries."""
    
    # Fake ffprobe output
    ffprobe_output = json.dumps({
        "streams": [
            {
                "index": 0,
                "codec_type": "video"
            },
            {
                "index": 1,
                "codec_type": "audio",
                "codec_name": "aac",
                "tags": {"language": "ger"},
                "disposition": {"default": 1}
            },
            {
                "index": 2,
                "codec_type": "subtitle",
                "codec_name": "hdmv_pgs_subtitle",
                "tags": {"language": "eng", "title": "Forced"},
                "disposition": {"forced": 1, "hearing_impaired": 0}
            },
            {
                "index": 3,
                "codec_type": "subtitle",
                "codec_name": "subrip",
                "tags": {"language": "spa", "title": "SDH"},
                "disposition": {"forced": 0, "hearing_impaired": 1}
            }
        ]
    })
    
    mock_tracked_run.return_value = Mock(stdout=ffprobe_output, returncode=0)
    
    # Run function
    tracks = generate_track_metadata("test_movie.mkv")
    
    # Assertions
    assert len(tracks) == 3  # Video stream should be ignored!
    
    # Check Audio Track
    assert tracks[0]["track_type"] == "Audio"
    assert tracks[0]["language_iso"] == "ger"
    assert tracks[0]["is_default"] is True
    assert tracks[0]["target_track_id"] == 1
    
    # Check PGS Forced Subtitle
    assert tracks[1]["track_type"] == "Untertitel"
    assert tracks[1]["language_iso"] == "eng"
    assert tracks[1]["subtitle_type"] == "PGSSUB"
    assert tracks[1]["is_forced"] is True
    assert tracks[1]["is_hearing_impaired"] is False
    
    # Check SRT SDH Subtitle
    assert tracks[2]["track_type"] == "Untertitel"
    assert tracks[2]["language_iso"] == "spa"
    assert tracks[2]["subtitle_type"] == "SRT"
    assert tracks[2]["is_hearing_impaired"] is True
