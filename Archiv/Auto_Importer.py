import os
import sys
import json
import subprocess
import pandas as pd
import time

# Paths
JELLYFIN_DIR = r"F:\Jellyfin"
MATRIX_PATH = r"F:\Jellyfin_AI_Cockpit\Daten\Inforamtionsmatrix.xlsx"
MASTER_CLEANUP = r"F:\Jellyfin_AI_Cockpit\Master_Cleanup.py"
MKVPROPEDIT = r"C:\Program Files\MKVToolNix\mkvpropedit.exe"
PYTHON_EXE = sys.executable

def find_mkv_path(filename):
    for root, dirs, files in os.walk(JELLYFIN_DIR):
        if filename in files:
            return os.path.join(root, filename)
    return None

def wipe_cleanup_tag(filepath):
    cmd = [MKVPROPEDIT, filepath, "-d", "title"]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(f"  [+] Tag wiped for: {os.path.basename(filepath)}")

def run_master_cleanup(filepath):
    print(f"  [+] Running Master_Cleanup on: {os.path.basename(filepath)}...")
    cmd = [PYTHON_EXE, "-c", f"import sys; sys.path.append(r'F:\\Jellyfin_AI_Cockpit'); from Master_Cleanup import process_file; process_file(r'{filepath}')"]
    res = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')
    if res.returncode != 0:
        print(f"  [!] Error running Master_Cleanup!")

def extract_metadata(filepath):
    cmd = ["ffprobe", "-v", "error", "-show_streams", "-of", "json", filepath]
    res = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')
    if res.returncode != 0: return []
    data = json.loads(res.stdout)
    
    tracks = []
    streams = [s for s in data.get('streams', []) if s.get('codec_type') != 'video']
    for idx, s in enumerate(streams, start=1):
        lang = s.get('tags', {}).get('language', 'und')
        title = s.get('tags', {}).get('title', '')
        
        is_sdh = 'SDH' in title.upper()
        is_forced = 'FORCED' in title.upper()
        track_type = "Audio" if s.get('codec_type') == 'audio' else "Untertitel"
        
        tracks.append({
            "Film": os.path.basename(filepath),
            "Typ": track_type,
            "Spur": idx,
            "Sprache": lang,
            "SDH": is_sdh,
            "Forced": is_forced,
            "Sonstiges": "AUTO"
        })
    return tracks

def main():
    print("=========================================")
    print("       AUTO-IMPORTER & REPROCESSOR       ")
    print("=========================================")
    
    if not os.path.exists(MATRIX_PATH):
        print(f"[!] Matrix not found at {MATRIX_PATH}")
        return
        
    df = pd.read_excel(MATRIX_PATH)
    
    auto_rows = df[df['Sonstiges'] == 'AUTO']
    auto_movies = auto_rows['Film'].unique()
    
    if len(auto_movies) > 0:
        print(f"[*] Gefunden: {len(auto_movies)} Filme mit 'AUTO' Flag. Starte Reprozessierung...")
        
        for movie in auto_movies:
            print(f"\n-> {movie}")
            filepath = find_mkv_path(movie)
            if not filepath:
                print(f"  [!] Konnte Datei nicht im F:\\Jellyfin Ordner finden!")
                continue
                
            wipe_cleanup_tag(filepath)
            run_master_cleanup(filepath)
            
            new_tracks = extract_metadata(filepath)
            df = df[df['Film'] != movie]
            df = pd.concat([df, pd.DataFrame(new_tracks)], ignore_index=True)
            df.to_excel(MATRIX_PATH, index=False)
            print("  [+] Excel-Matrix aktualisiert.")
    else:
        print("[*] Keine existierenden 'AUTO' Filme gefunden.")

    test_dir = r"F:\Jellyfin_AI_Cockpit\Daten\Test_Videos"
    print(f"\n[*] Prüfe Ordner auf neue Filme: {test_dir}")
    if os.path.exists(test_dir):
        new_files = [f for f in os.listdir(test_dir) if f.endswith('.mkv')]
        for f in new_files:
            if f not in df['Film'].values:
                print(f"\n-> NEUER FILM: {f}")
                filepath = os.path.join(test_dir, f)
                wipe_cleanup_tag(filepath)
                run_master_cleanup(filepath)
                new_tracks = extract_metadata(filepath)
                df = pd.concat([df, pd.DataFrame(new_tracks)], ignore_index=True)
                df.to_excel(MATRIX_PATH, index=False)
                print("  [+] Als 'AUTO' in Excel-Matrix eingetragen.")
            
    print("\n=========================================")
    print("           IMPORT ABGESCHLOSSEN          ")
    print("=========================================")

if __name__ == "__main__":
    main()
