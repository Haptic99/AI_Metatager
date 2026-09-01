import pytest
from unittest.mock import Mock
from ai_metatagger.core.ocr_analyzer import _auto_detect_tess_language

@pytest.fixture
def mock_extract(mocker):
    return mocker.patch('ai_metatagger.core.ocr_analyzer.extract_subtitle_image', return_value=True)

@pytest.fixture
def mock_image(mocker):
    # Mock PIL.Image.open to return a dummy object that pytesseract can consume
    img_mock = mocker.MagicMock()
    img_mock.__enter__.return_value = img_mock
    img_mock.width = 100
    img_mock.height = 100
    img_mock.getbbox.return_value = (10, 10, 90, 90)
    return mocker.patch('ai_metatagger.core.ocr_analyzer.Image.open', return_value=img_mock)

@pytest.fixture
def mock_tesseract(mocker):
    # Mock pytesseract image_to_string
    return mocker.patch('ai_metatagger.core.ocr_analyzer.pytesseract.image_to_string')

@pytest.fixture
def mock_image_to_data(mocker):
    # Mock pytesseract image_to_data
    return mocker.patch('ai_metatagger.core.ocr_analyzer.pytesseract.image_to_data')

def test_auto_detect_tess_language_picks_best_confidence(mock_extract, mock_image, mock_image_to_data, mocker):
    """Test that the script group with the highest Tesseract confidence is selected."""
    
    # We will simulate that "kor+eng" gets 95 confidence, and others get 50.
    def mock_data(first_img, lang, output_type):
        if lang == "kor+eng":
            return {'conf': ['-1', '95', '95']}
        else:
            return {'conf': ['-1', '50', '50']}
            
    mock_image_to_data.side_effect = mock_data
    
    mocker.patch('ai_metatagger.core.ocr_analyzer.os.path.exists', return_value=True)
    mocker.patch('ai_metatagger.core.ocr_analyzer.os.remove')
    
    result = _auto_detect_tess_language(
        filepath="fake.mkv",
        stream_idx=0,
        track_id=1,
        sample_timestamps=[10.0],
        default_lang="eng+deu+fra+spa+ita",
        old_lang="und"
    )
    
    assert result == "kor+eng"

def test_extract_subtitle_image_uses_temp_mkv(mocker):
    """Test that extract_subtitle_image uses the temp.mkv with slow seek if it exists."""
    from ai_metatagger.core.ocr_analyzer import extract_subtitle_image
    
    mock_run = mocker.patch('ai_metatagger.core.ocr_analyzer.tracked_run')
    mock_exists = mocker.patch('os.path.exists', side_effect=lambda x: True) # temp.mkv exists, and out_img exists
    
    result = extract_subtitle_image("movie.mkv", 3, 10.5, "out.png")
    
    assert result is True
    cmd = mock_run.call_args[0][0]
    
    # Verify slow seek syntax (input before -ss) and map 0:0
    assert "-i" in cmd
    i_idx = cmd.index("-i")
    ss_idx = cmd.index("-ss")
    assert i_idx < ss_idx  # -i comes before -ss
    
    assert "temp.mkv" in cmd[i_idx + 1]
    assert "[0:0]scale=" in cmd[cmd.index("-filter_complex") + 1]

def test_extract_subtitle_image_no_temp_mkv(mocker):
    """Test that extract_subtitle_image falls back to fast seek if temp.mkv does not exist."""
    from ai_metatagger.core.ocr_analyzer import extract_subtitle_image
    
    mock_run = mocker.patch('ai_metatagger.core.ocr_analyzer.tracked_run')
    # temp.mkv does not exist, out_img exists
    def fake_exists(path):
        return "out.png" in path
    mocker.patch('os.path.exists', side_effect=fake_exists)
    
    result = extract_subtitle_image("movie.mkv", 3, 10.5, "out.png")
    
    assert result is True
    cmd = mock_run.call_args[0][0]
    
    # Verify fast seek syntax (-ss before input) and original stream_idx
    assert "-i" in cmd
    i_idx = cmd.index("-i")
    ss_idx = cmd.index("-ss")
    assert ss_idx < i_idx  # -ss comes before -i
    
    assert "movie.mkv" in cmd[i_idx + 1]
    assert "[0:3]scale=" in cmd[cmd.index("-filter_complex") + 1]
