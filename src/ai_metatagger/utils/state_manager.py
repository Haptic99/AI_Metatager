import os
import json
import sqlite3
import pandas as pd
from ai_metatagger.config import DATA_DIR, STATE_PATH, DB_PATH

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
    conn.commit()
    return conn

def load_matrix():
    conn = init_db()
    try:
        df = pd.read_sql_query("SELECT * FROM media_tracks", conn)
        # SQLite stores booleans as 1/0, convert them to bool for pandas
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
            'is_forced', 'notes', 'is_validated'
        ])
    finally:
        conn.close()

def save_matrix(df):
    conn = init_db()
    df.to_sql('media_tracks', conn, if_exists='replace', index=False)
    conn.close()

def load_state():
    if os.path.exists(STATE_PATH):
        try:
            with open(STATE_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        except: pass
    return {}

def save_state(state_data):
    with open(STATE_PATH, 'w', encoding='utf-8') as f:
        json.dump(state_data, f, indent=4)
