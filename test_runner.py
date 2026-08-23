import os
import json
import shutil
import subprocess
import pandas as pd
import sys
import glob
import time

LOG_OUT_FILE = r"F:\Jellyfin_AI_Cockpit\Daten\Test_Runner_Log.txt"
if os.path.exists(LOG_OUT_FILE):
    try: os.remove(LOG_OUT_FILE)
    except: pass

def tprint(msg, end='\n'):
    print(msg, end=end)
    try:
        with open(LOG_OUT_FILE, "a", encoding="utf-8") as lf:
            lf.write(msg + end)
    except:
        pass

MATRIX_PATH = r"F:\Jellyfin_AI_Cockpit\Informationsmatrix.xlsx"
TEST_DATEN_LIST = r"F:\Jellyfin_AI_Cockpit\Daten\test_daten.txt"
TEST_VIDEOS_DIR = r"F:\Jellyfin_AI_Cockpit\Daten\Test_Videos"
MASTER_CLEANUP = r"F:\Jellyfin_AI_Cockpit\Master_Cleanup.py"
LOG_FILE = r"F:\Jellyfin_AI_Cockpit\Daten\Master_Cleanup_Log.txt"
LOG_FILE_OLD = r"F:\Jellyfin_AI_Cockpit\Daten\Master_Cleanup_Log.old.txt"
PYTHON_EXE = sys.executable
sys.stdout.reconfigure(encoding='utf-8')

def rotate_log():
    if os.path.exists(LOG_FILE):
        try:
            if os.path.exists(LOG_FILE_OLD):
                os.remove(LOG_FILE_OLD)
            os.rename(LOG_FILE, LOG_FILE_OLD)
        except Exception as e:
            pass

def read_matrix():
    df = pd.read_excel(MATRIX_PATH)
    if 'Name' not in df.columns:
        df.columns = df.iloc[0]
        df = df.iloc[1:].copy()
    df['Name'] = df['Name'].ffill()
    df = df.dropna(subset=['ID'])
    return df

def find_source_file(filename):
    with open(TEST_DATEN_LIST, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            line = line.strip()
            if not line: continue
            if os.path.basename(line) == filename:
                return line
            if os.path.splitext(os.path.basename(line))[0] == os.path.splitext(filename)[0]:
                return line
    return None

def run_test_for_movie(movie_name, expected_tracks_df, i, total):
    tprint(f"[{i}/{total}] Teste: {movie_name}")
    
    # Filter if ALL tracks for this movie are AUTO
    is_auto = True
    for _, row in expected_tracks_df.iterrows():
        s = str(row.get('Sonstiges', '')).strip().upper()
        if s != 'AUTO':
            is_auto = False
            break
            
    if is_auto:
        tprint("  -> ÜBERSPRUNGEN: (AUTO generierte Einträge)")
        return True, []
    
    src_path = find_source_file(movie_name)
    if not src_path or not os.path.exists(src_path):
        err = f"ERROR: Quelldatei nicht in test_daten.txt gefunden"
        tprint(f"  -> FEHLER: {err}")
        return False, [err]
        
    if os.path.exists(TEST_VIDEOS_DIR):
        for f in os.listdir(TEST_VIDEOS_DIR):
            try: os.remove(os.path.join(TEST_VIDEOS_DIR, f))
            except: pass
    else:
        os.makedirs(TEST_VIDEOS_DIR)
        
    dest_path = os.path.join(TEST_VIDEOS_DIR, os.path.basename(src_path))
    shutil.copy2(src_path, dest_path)
    
    start_t = time.time()
    cmd = [PYTHON_EXE, "-u", MASTER_CLEANUP, TEST_VIDEOS_DIR]
    res = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')
    dur = time.time() - start_t
    
    tprint(f"  -> Cleanup abgeschlossen in {dur:.1f}s.")
    
    out_files = glob.glob(os.path.join(TEST_VIDEOS_DIR, "*.mkv"))
    if not out_files:
        err = "ERROR: Keine saubere MKV generiert!"
        tprint(f"  -> FEHLER: {err}")
        return False, [err]
    out_file = out_files[0]
    
    cmd_probe = ["ffprobe", "-v", "error", "-show_streams", "-of", "json", out_file]
    probe_res = subprocess.run(cmd_probe, capture_output=True, text=True, encoding='utf-8')
    data = json.loads(probe_res.stdout)
    streams = [s for s in data.get('streams', []) if s.get('codec_type') != 'video']
    
    errors = []
    
    # Validation
    if len(streams) != len(expected_tracks_df):
        err = f"Spurenanzahl - Erwartet {len(expected_tracks_df)}, Gefunden {len(streams)}"
        errors.append(err)
        tprint(f"  -> FEHLER: {err}")
        return False, errors
        
    for idx_loop, s in enumerate(streams):
        expected = expected_tracks_df.iloc[idx_loop]
        
        idx = s.get('index')
        ctype = s.get('codec_type')
        tags = s.get('tags', {})
        lang = tags.get('language', 'und')
        title = tags.get('title', '')
        disp = s.get('disposition', {})
        is_default = disp.get('default', 0) == 1
        is_forced = disp.get('forced', 0) == 1
        is_hi = disp.get('hearing_impaired', 0) == 1
        
        # Check Language
        expected_lang = str(expected.get('Effektive Sprache (ISO-Code)', '')).strip()
        if pd.isna(expected.get('Effektive Sprache (ISO-Code)')) or expected_lang == 'nan' or expected_lang == '':
            expected_lang = 'und'
            
        # ISO 639-2 translation map for testing BCP-47 expected tags
        iso_map = {'zh-Hans': 'chi', 'zh-Hant': 'chi', 'pt-BR': 'por', 'pt-PT': 'por', 'es-ES': 'spa', 'es-419': 'spa', 'fr-CA': 'fre', 'fra': 'fre', 'hr': 'hrv'}
        mapped_expected = iso_map.get(expected_lang, expected_lang)
        mapped_lang = iso_map.get(lang, lang)
        
        if mapped_lang != mapped_expected:
            errors.append(f"Spur {idx} Sprache - Erwartet: '{expected_lang}', Gefunden: '{lang}'")
        
        exp_default = str(expected.get('Standardspur', '')).strip() == 'Ja'
        exp_forced = str(expected.get('Anzeige erzwingen-Schalter', '')).strip() == 'Ja'
        # Fix encoding issue for "Schwerhörig"
        hi_val = str(expected.get('Schwerhrig-Schalter', str(expected.get('Schwerhörig-Schalter', '')))).strip()
        exp_hi = hi_val == 'Ja'
            
        if is_default != exp_default:
            errors.append(f"Spur {idx} Standardspur - Erwartet: {exp_default}, Gefunden: {is_default}")
            
        if is_forced != exp_forced:
            errors.append(f"Spur {idx} Forced - Erwartet: {exp_forced}, Gefunden: {is_forced}")
            
        if is_hi != exp_hi:
            errors.append(f"Spur {idx} SDH (Schwerhörig) - Erwartet: {exp_hi}, Gefunden: {is_hi}")
            
        # Check Title (Name)
        exp_title = str(expected.get('Effektiver Name', '')).strip()
        if pd.isna(expected.get('Effektiver Name')) or exp_title == 'nan':
            exp_title = ''
            
        title = tags.get('title', '').strip() if tags else ''
        if title != exp_title:
            errors.append(f"Spur {idx} Titel - Erwartet: '{exp_title}', Gefunden: '{title}'")
            
    if errors:
        for e in errors:
            tprint(f"  -> FEHLER: {e}")
        return False, errors
        
    tprint("  -> OK: Stimmt exakt mit Matrix überein.")
    return True, []

if __name__ == "__main__":
    rotate_log()
    df = read_matrix()
    movies = df['Name'].unique()
    
    all_results = {}
    total_passed = 0
    total_failed = 0
    total_errors = 0
    total_skipped = 0
    
    tprint(f"=== STARTE TESTLAUF ({len(movies)} Filme) ===")
    
    for i, movie in enumerate(movies, 1):
        if pd.isna(movie): continue
        expected = df[df['Name'] == movie]
        
        # Check if all AUTO
        is_auto = True
        for _, row in expected.iterrows():
            s = str(row.get('Sonstiges', '')).strip().upper()
            if s != 'AUTO':
                is_auto = False
                break
                
        if is_auto:
            total_skipped += 1
            continue
            
        success, errors = run_test_for_movie(movie, expected, i, len(movies))
        all_results[movie] = errors
        if success:
            total_passed += 1
        else:
            total_failed += 1
            
    tprint(f"\n{'='*50}")
    tprint("TESTLAUF BEENDET")
    tprint(f"Gefundene Fehler (Falsche Übereinstimmungen): {total_errors}")
    tprint(f"Log gespeichert in: {LOG_OUT_FILE}")
    tprint(f"Erfolgreich: {total_passed}")
    tprint(f"Fehlgeschlagen: {total_failed}")
    tprint(f"Übersprungen (AUTO): {total_skipped}")
    tprint(f"{'='*50}")
    
    if total_failed > 0:
        sys.exit(1)
    else:
        sys.exit(0)
