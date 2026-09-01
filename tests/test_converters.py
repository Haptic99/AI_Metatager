import pytest
from ai_metatagger.core.converters import _convert_container

def test_convert_container_mkv(mocker):
    """Test that MKV files are ignored and returned as-is."""
    result = _convert_container("movie.mkv")
    assert result == "movie.mkv"

def test_convert_container_avi(mocker):
    """Test that AVI files trigger ffmpeg conversion to MKV."""
    mock_run = mocker.patch('ai_metatagger.core.converters.tracked_run')
    mock_run.return_value.returncode = 0
    
    mocker.patch('os.path.exists', return_value=True)
    mocker.patch('os.path.getsize', return_value=1000)
    mock_remove = mocker.patch('os.remove')
    
    result = _convert_container("movie.avi")
    
    # Should run ffmpeg
    assert mock_run.called
    cmd = mock_run.call_args[0][0]
    assert cmd[0] == "ffmpeg"
    assert cmd[-1] == "movie.mkv"
    
    # Should delete the original
    mock_remove.assert_called_once_with("movie.avi")
    
    # Should return the new path
    assert result == "movie.mkv"

def test_convert_container_fails(mocker):
    """Test that if ffmpeg fails, it returns an empty string."""
    mock_run = mocker.patch('ai_metatagger.core.converters.tracked_run')
    mock_run.return_value.returncode = 1  # Fake a crash
    
    result = _convert_container("movie.mp4")
    
    assert result == ""
