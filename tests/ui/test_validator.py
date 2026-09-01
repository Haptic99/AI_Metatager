import pytest
from PyQt5.QtWidgets import QApplication
from ai_metatagger.ui.screens.validator import Screen3Validator
from ai_metatagger.utils.state_manager import init_db

@pytest.fixture
def mock_db_path(mocker, tmp_path):
    """Automatically mock DB_PATH to use a temporary SQLite file for all tests."""
    temp_db = tmp_path / "test_db.sqlite"
    mocker.patch('ai_metatagger.utils.state_manager.DB_PATH', str(temp_db))
    # Initialize DB so it's not empty
    init_db()
    yield str(temp_db)

@pytest.fixture
def validator_screen(qtbot, mock_db_path, mocker):
    """Fixture to create and return the ValidatorScreen."""
    # Mock the Vlc player widget so it doesn't try to load libvlc
    mocker.patch('ai_metatagger.ui.components.video_player.VideoPlayerWidget')
    
    # Needs a parent
    parent = mocker.MagicMock()
    screen = Screen3Validator(parent)
    qtbot.addWidget(screen)
    return screen

def test_scan_files_emits_signal(qtbot, validator_screen, mocker):
    """Test that scan_files runs successfully and emits the scan_finished signal with a list."""
    
    # We mock os.walk to return a fake movie list so it doesn't actually scan the real NAS
    fake_walk = [
        ("F:/Jellyfin/Filme", [], ["Test Movie 1.mkv", "Test Movie 2.mp4", "ignore.txt"])
    ]
    mocker.patch('os.walk', return_value=fake_walk)
    mocker.patch('os.path.exists', return_value=True)
    
    # We want to wait for the scan_finished signal to be emitted
    with qtbot.waitSignal(validator_screen.scan_finished, timeout=2000) as blocker:
        validator_screen.scan_files()
        
    # Check that the signal was emitted with the correctly filtered list
    emitted_files = blocker.args[0]
    
    # Should only contain .mkv and .mp4, but not .txt
    assert len(emitted_files) == 4
    assert "F:/Jellyfin/Filme\\Test Movie 1.mkv" in emitted_files or "F:/Jellyfin/Filme/Test Movie 1.mkv" in emitted_files
