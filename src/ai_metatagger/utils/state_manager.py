import os
import json
import sqlite3
import threading
import pandas as pd
from ai_metatagger.config import DATA_DIR, DB_PATH

DB_LOCK = threading.Lock()

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS media_tracks (
            file_name TEXT,
            track_id TEXT,
            track_type TEXT,
            language_iso TEXT,
            track_name TEXT,
            is_default BOOLEAN,
            subtitle_type TEXT,
            is_hearing_impaired BOOLEAN,
            is_forced BOOLEAN,
            notes TEXT,
            is_validated BOOLEAN
        )
    ''')
    
    # Migrate to include state data directly in DB
    try:
        cursor.execute("ALTER TABLE media_tracks ADD COLUMN ki_data TEXT")
    except sqlite3.OperationalError:
        pass
        
    try:
        cursor.execute("ALTER TABLE media_tracks ADD COLUMN validated_fields TEXT")
    except sqlite3.OperationalError:
        pass
        
    # Migrate target_track_id
    try:
        cursor.execute("ALTER TABLE media_tracks ADD COLUMN target_track_id TEXT")
        # Update existing rows to default to track_id
        cursor.execute("UPDATE media_tracks SET target_track_id = track_id WHERE target_track_id IS NULL")
    except sqlite3.OperationalError:
        pass
        
    conn.commit()
    return conn

def load_matrix():
    with DB_LOCK:
        conn = init_db()
        try:
            df = pd.read_sql_query("SELECT * FROM media_tracks", conn)
            bool_cols = ['is_default', 'is_hearing_impaired', 'is_forced', 'is_validated']
            for col in bool_cols:
                if col in df.columns:
                    df[col] = df[col].astype(bool)
            return df
        except Exception as e:
            print("Fehler beim Laden der DB:", e)
            return pd.DataFrame(columns=[
                'file_name', 'track_id', 'track_type', 'language_iso', 'track_name', 
                'is_default', 'subtitle_type', 'is_hearing_impaired', 
                'is_forced', 'notes', 'is_validated', 'ki_data', 'validated_fields'
            ])
        finally:
            conn.close()

def save_matrix(df):
    """
    Deprecated: Should not be used for frequent updates. Use update_track() instead.
    Replaces the entire table.
    """
    with DB_LOCK:
        conn = init_db()
        df.to_sql('media_tracks', conn, if_exists='replace', index=False)
        conn.close()

def append_tracks(df):
    """Append new tracks to the DB without replacing existing ones."""
    with DB_LOCK:
        conn = init_db()
        df.to_sql('media_tracks', conn, if_exists='append', index=False)
        conn.close()

def delete_unvalidated_tracks(file_name: str):
    """Delete unvalidated tracks for a specific movie before appending fresh ones."""
    with DB_LOCK:
        conn = init_db()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM media_tracks WHERE file_name = ? AND is_validated = 0", (file_name,))
        conn.commit()
        conn.close()

def delete_movie_tracks(file_name: str):
    """Delete all tracks for a specific movie (e.g., on restart or abort)."""
    with DB_LOCK:
        conn = init_db()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM media_tracks WHERE file_name = ?", (file_name,))
        conn.commit()
        conn.close()

def update_track(file_name, track_id, updates: dict):
    """
    Update specific fields for a track. O(1) operation instead of rewriting the entire DB.
    """
    with DB_LOCK:
        conn = init_db()
        cursor = conn.cursor()
        
        set_clauses = []
        values = []
        for k, v in updates.items():
            set_clauses.append(f"{k} = ?")
            values.append(v)
            
        values.extend([file_name, track_id])
        query = f"UPDATE media_tracks SET {', '.join(set_clauses)} WHERE file_name = ? AND track_id = ?"
        
        cursor.execute(query, values)
        conn.commit()
        conn.close()

def load_state():
    """
    Adapter: Generates the old dictionary structure from the SQLite DB.
    Format: { "film": { "track_id": { "KI": {...}, "Validated": {...} } } }
    """
    state_dict = {}
    with DB_LOCK:
        conn = init_db()
        cursor = conn.cursor()
        cursor.execute("SELECT file_name, track_id, ki_data, validated_fields FROM media_tracks")
        for row in cursor.fetchall():
            film, tid, ki, val = row
            tid = str(tid)
            if film not in state_dict:
                state_dict[film] = {}
            if tid not in state_dict[film]:
                state_dict[film][tid] = {"KI": {}, "Validated": {}}
                
            if ki:
                try:
                    state_dict[film][tid]["KI"] = json.loads(ki)
                except:
                    pass
            if val:
                try:
                    state_dict[film][tid]["Validated"] = json.loads(val)
                except:
                    pass
        conn.close()
    return state_dict

def save_state(state_data):
    """
    Adapter: Writes the old dictionary structure into the SQLite DB.
    """
    with DB_LOCK:
        conn = init_db()
        cursor = conn.cursor()
        for film, tracks in state_data.items():
            for tid, data in tracks.items():
                ki = json.dumps(data.get("KI", {}))
                val = json.dumps(data.get("Validated", {}))
                cursor.execute(
                    "UPDATE media_tracks SET ki_data = ?, validated_fields = ? WHERE file_name = ? AND track_id = ?",
                    (ki, val, film, tid)
                )
        conn.commit()
        conn.close()