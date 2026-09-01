import pytest
import sqlite3
import pandas as pd
import os
from ai_metatagger.utils import state_manager

@pytest.fixture(autouse=True)
def mock_db_path(mocker, tmp_path):
    """Automatically mock DB_PATH to use a temporary SQLite file for all tests."""
    temp_db = tmp_path / "test_db.sqlite"
    mocker.patch('ai_metatagger.utils.state_manager.DB_PATH', str(temp_db))
    yield str(temp_db)

def test_init_db(mock_db_path):
    """Test that the database initializes correctly with all expected columns."""
    conn = state_manager.init_db()
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(media_tracks)")
    columns = [row[1] for row in cursor.fetchall()]
    conn.close()
    
    assert "file_name" in columns
    assert "track_id" in columns
    assert "target_track_id" in columns
    assert "ki_data" in columns

def test_append_and_load_tracks(mock_db_path):
    """Test appending tracks and loading them back into a DataFrame."""
    df_input = pd.DataFrame([
        {
            "file_name": "movie1.mkv",
            "track_id": "1",
            "target_track_id": "1",
            "track_type": "Audio",
            "language_iso": "eng",
            "track_name": "",
            "is_default": True,
            "subtitle_type": "",
            "is_hearing_impaired": False,
            "is_forced": False,
            "notes": "AUTO",
            "is_validated": False,
            "ki_data": "{}",
            "validated_fields": "{}"
        }
    ])
    
    # Init DB and append
    state_manager.init_db()
    state_manager.append_tracks(df_input)
    
    # Load back
    df_loaded = state_manager.load_matrix()
    
    assert len(df_loaded) == 1
    assert df_loaded.iloc[0]["file_name"] == "movie1.mkv"
    assert df_loaded.iloc[0]["language_iso"] == "eng"
    assert df_loaded.iloc[0]["is_default"] == True  # Boolean conversion test

def test_update_track(mock_db_path):
    """Test the O(1) track update function."""
    df_input = pd.DataFrame([
        {
            "file_name": "movie1.mkv",
            "track_id": "1",
            "target_track_id": "1",
            "track_type": "Audio",
            "is_validated": False
        }
    ])
    state_manager.init_db()
    state_manager.append_tracks(df_input)
    
    # Update track
    state_manager.update_track("movie1.mkv", "1", {"target_track_id": "2", "is_validated": True})
    
    # Load and verify
    df_loaded = state_manager.load_matrix()
    assert str(df_loaded.iloc[0]["target_track_id"]) == "2"
    assert df_loaded.iloc[0]["is_validated"] == True

def test_delete_movie_tracks(mock_db_path):
    """Test deleting all tracks for a specific movie."""
    df_input = pd.DataFrame([
        {"file_name": "movie1.mkv", "track_id": "1"},
        {"file_name": "movie2.mkv", "track_id": "1"}
    ])
    state_manager.init_db()
    state_manager.append_tracks(df_input)
    
    state_manager.delete_movie_tracks("movie1.mkv")
    
    df_loaded = state_manager.load_matrix()
    assert len(df_loaded) == 1
    assert df_loaded.iloc[0]["file_name"] == "movie2.mkv"
