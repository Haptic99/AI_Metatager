import os
import subprocess
import shutil
import json
import time
import pandas as pd
from PyQt5 import QtCore
from ai_metatagger.config import DIR_TEST, MKVPROPEDIT, PYTHON_EXE, DB_PATH
from ai_metatagger.utils.state_manager import load_state, save_state, load_matrix, save_matrix
from ai_metatagger.core import processor as analyzer
class AnalysisThread(QtCore.QThread):
    progress_update = QtCore.pyqtSignal(int, int, str)
    movie_ready = QtCore.pyqtSignal()
    finished_analysis = QtCore.pyqtSignal()
    def __init__(self, file_paths):
        super().__init__()
        self.file_paths = file_paths
        self.is_cancelled = False
    def extract_metadata(self, filepath):
        data = getattr(self, 'ffprobe_cache', {}).get(filepath)
        if not data:
            cmd = ["ffprobe", "-v", "error", "-show_streams", "-of", "json", filepath]
            res = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', creationflags=subprocess.CREATE_NO_WINDOW)
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
            codec = s.get('codec_name', '').lower()
            if track_type == "Audio": sub_type = ""
            elif 'pgs' in codec or 'dvd' in codec: sub_type = "PGSSUB"
            else: sub_type = "SRT"
            
            tracks.append({
                "file_name": os.path.basename(filepath),
                "track_id": idx,
                "track_type": track_type,
                "language_iso": lang,
                "track_name": "",
                "is_default": False,
                "subtitle_type": sub_type,
                "is_hearing_impaired": is_sdh,
                "is_forced": is_forced,
                "notes": "AUTO",
                        "is_validated": False
            })
        return tracks
    def stop(self):
        self.is_cancelled = True

    def run(self):
        total = len(self.file_paths)
        if not os.path.exists(DIR_TEST):
            os.makedirs(DIR_TEST)
            
        self.progress_update.emit(0, 100, "Scanne alle Dateien...")
        file_stats = []
        total_points = 0
        w_audio = 2
        prescan_start = time.time()
        w_pgs = 10
        w_srt = 1
        w_mux = 2
        
        for path in self.file_paths:
            if self.is_cancelled:
                self.progress_update.emit(0, 100, "Abgebrochen!")
                return
            
            f_aud = 0
            f_sub = 0
            pts_for_file = 0
            cmd = ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams", path]
            try:
                res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='replace', creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
                data = json.loads(res.stdout)
                if not hasattr(self, 'ffprobe_cache'): self.ffprobe_cache = {}
                self.ffprobe_cache[path] = data
                for s in data.get('streams', []):
                    ctype = s.get('codec_type')
                    if ctype == 'audio':
                        f_aud += 1
                        pts_for_file += w_audio
                    elif ctype == 'subtitle':
                        f_sub += 1
                        codec = s.get('codec_name', '')
                        if codec in ['hdmv_pgs_subtitle', 'dvd_subtitle', 'dvdsub', 'pgssub']: pts_for_file += w_pgs
                        else: pts_for_file += w_srt
            except (subprocess.SubprocessError, json.JSONDecodeError, OSError) as e:
                print(f'Prescan error: {e}')
            
            pts_for_file += w_mux
            total_points += pts_for_file
            file_stats.append({'total_tracks': f_aud + f_sub, 'points': pts_for_file})
            
        prescan_dur = time.time() - prescan_start
        try:
            csv_path = os.path.join(os.path.dirname(DB_PATH), "Performance_Log.csv")
            write_header = not os.path.exists(csv_path)
            with open(csv_path, "a", encoding="utf-8") as f:
                if write_header: f.write("Movie,TrackType,Codec,DurationSec\n")
                f.write(f'"ALL",prescan,ffprobe,{prescan_dur:.2f}\n')
        except OSError as e:
            print(f'Log write error: {e}')
        
        if total_points == 0: total_points = 1
        points_done = 0
        fractional_points = 0.0
        current_movie_idx = 0
        current_track_idx = 0
        start_time = time.time()
        track_start_times = {}
        
        def progress_callback(track_type, idx, status, codec='', step_idx=0, total_steps=1):
            nonlocal points_done, current_track_idx, fractional_points
            
            stat = file_stats[current_movie_idx]
            total_in_file = stat['total_tracks']
            basename = os.path.basename(self.file_paths[current_movie_idx])
            
            if status == 'start':
                if step_idx == 0:
                    track_start_times[f"{track_type}_{idx}"] = time.time()
                fractional_points = 0.0
                if track_type != 'muxing':
                    current_track_idx += 1
                pct = int((points_done / total_points) * 100)
                type_de = 'Audio' if track_type == 'audio' else 'Untertitel' if track_type == 'subtitle' else 'Speichern'
                
                if track_type != 'muxing':
                    msg = f"Film {current_movie_idx+1}/{total}: '{basename}' | Analysiere {type_de} (Spur {current_track_idx}/{total_in_file})"
                else:
                    msg = f"Film {current_movie_idx+1}/{total}: '{basename}' | Speichere Film..."
                self.progress_update.emit(pct, 100, msg)
                
            elif status == 'step':
                if track_type == 'subtitle' and codec in ['hdmv_pgs_subtitle', 'dvd_subtitle', 'dvdsub', 'pgssub']:
                    if total_steps > 0:
                        fractional_points = (step_idx / total_steps) * w_pgs
                        pd_f = points_done + fractional_points
                        pct = int((pd_f / total_points) * 100)
                        
                        elapsed = time.time() - start_time
                        if pd_f > 0:
                            total_est = (elapsed / pd_f) * total_points
                            rem_sec = max(0, total_est - elapsed)
                            mins = int(rem_sec // 60)
                            secs = int(rem_sec % 60)
                            eta_str = f"ca. {mins} Min {secs} Sek verbleibend"
                        else:
                            eta_str = "Berechne Zeit"
                            
                        msg = f"Film {current_movie_idx+1}/{total}: '{basename}' | Analysiere Untertitel (Spur {current_track_idx}/{total_in_file}) | {eta_str}"
                        self.progress_update.emit(pct, 100, msg)
            elif status == 'done':
                dur = time.time() - track_start_times.get(f"{track_type}_{idx}", time.time())
                try:
                    csv_path = os.path.join(os.path.dirname(DB_PATH), "Performance_Log.csv")
                    write_header = not os.path.exists(csv_path)
                    with open(csv_path, "a", encoding="utf-8") as f:
                        if write_header: f.write("Movie,TrackType,Codec,DurationSec\n")
                        f.write(f'"{basename}",{track_type},{codec},{dur:.2f}\n')
                except OSError as e:
                    print(f'Log write error: {e}')
                
                fractional_points = 0.0
                if track_type == 'audio': points_done += w_audio
                elif track_type == 'subtitle':
                    if codec in ['hdmv_pgs_subtitle', 'dvd_subtitle', 'dvdsub', 'pgssub']: points_done += w_pgs
                    else: points_done += w_srt
                elif track_type == 'muxing': points_done += w_mux
                
                pct = int((points_done / total_points) * 100)
                elapsed = time.time() - start_time
                if points_done > 0:
                    total_est = (elapsed / points_done) * total_points
                    rem_sec = max(0, total_est - elapsed)
                    mins = int(rem_sec // 60)
                    secs = int(rem_sec % 60)
                    eta_str = f"ca. {mins} Min {secs} Sek verbleibend"
                else:
                    eta_str = "Berechne Zeit"
                    
                type_de = 'Audio' if track_type == 'audio' else 'Untertitel' if track_type == 'subtitle' else 'Speichern'
                if track_type != 'muxing':
                    msg = f"Film {current_movie_idx+1}/{total}: '{basename}' | Analysiere {type_de} (Spur {current_track_idx}/{total_in_file}) | {eta_str}"
                else:
                    msg = f"Film {current_movie_idx+1}/{total}: '{basename}' | Speichere Film | {eta_str}"
                self.progress_update.emit(pct, 100, msg)
                
            return self.is_cancelled

        for i, src_path in enumerate(self.file_paths):
            current_movie_idx = i
            current_track_idx = 0
            if self.is_cancelled:
                self.progress_update.emit(i, total, "Analyse abgebrochen!")
                break
            basename = os.path.basename(src_path)
            dest_path = os.path.join(DIR_TEST, basename)
            self.progress_update.emit(i, total, f"Kopiere {basename}...")
            if not os.path.exists(dest_path):
                shutil.copy2(src_path, dest_path)
            subprocess.run([MKVPROPEDIT, dest_path, "-d", "title"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
            self.progress_update.emit(i, total, f"Analysiere {basename}...")
            analyzer.process_file(dest_path, progress_callback=progress_callback)
            new_tracks = self.extract_metadata(dest_path)
            if os.path.exists(DB_PATH):
                df = load_matrix()
            else:
                df = pd.DataFrame(columns=['file_name', 'track_id', 'track_type', 'language_iso', 'track_name', 'is_default', 'subtitle_type', 'is_hearing_impaired', 'is_forced', 'notes', 'is_validated'])
            # SCHUTZ VOR ÜBERSCHREIBEN BEREITS VALIDIERTER SPUREN
            other_movies = df[df['file_name'] != basename]
            current_movie = df[df['file_name'] == basename]
            validated_tracks = current_movie[current_movie['is_validated'] == True]
            valid_spur_nums = validated_tracks['track_id'].tolist() if not validated_tracks.empty else []
            filtered_new_tracks = [t for t in new_tracks if t['track_id'] not in valid_spur_nums]
            df = pd.concat([other_movies, validated_tracks, pd.DataFrame(filtered_new_tracks)], ignore_index=True)
            save_matrix(df)
            # STATE UPDATE
            state_data = load_state()
            if basename not in state_data:
                state_data[basename] = {}
            for trk in filtered_new_tracks:
                trk_id = str(trk['track_id'])
                if trk_id not in state_data[basename]:
                    state_data[basename][trk_id] = {
                        'Validated': {
                            'lang': False,
                            'sdh': False,
                            'forced': False,
                            'name': False
                        }
                    }
                # Always overwrite KI data with fresh results
                state_data[basename][trk_id]['KI'] = {
                    'lang': trk['language_iso'],
                    'sdh': trk['is_hearing_impaired'],
                    'forced': trk['is_forced'],
                    'name': ''
                }
            save_state(state_data)
            self.movie_ready.emit()
        self.progress_update.emit(total, total, "Alle Filme analysiert!")
        self.finished_analysis.emit()
