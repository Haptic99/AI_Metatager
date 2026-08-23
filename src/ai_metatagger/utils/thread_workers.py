import os
import subprocess
import shutil
import json
import pandas as pd
from PyQt5 import QtCore
from ai_metatagger.config import DIR_TEST, MKVPROPEDIT, PYTHON_EXE, DB_PATH
from ai_metatagger.utils.state_manager import load_state, save_state
from ai_metatagger.core import analyzer

class AnalysisThread(QtCore.QThread):









    progress_update = QtCore.pyqtSignal(int, int, str)









    movie_ready = QtCore.pyqtSignal()









    finished_analysis = QtCore.pyqtSignal()









    









    def __init__(self, file_paths):









        super().__init__()









        self.file_paths = file_paths









        









    def extract_metadata(self, filepath):









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









            tracks.append({









                "file_name": os.path.basename(filepath),









                "track_id": idx,









                "track_type": track_type,









                "language_iso": lang,









                "track_name": "",









                "is_default": False,









                "subtitle_type": "",









                "is_hearing_impaired": is_sdh,









                "is_forced": is_forced,









                "notes": "AUTO",
                        "is_validated": False









            })









        return tracks



















    def run(self):









        total = len(self.file_paths)









        if not os.path.exists(DIR_TEST):









            os.makedirs(DIR_TEST)









            









        for i, src_path in enumerate(self.file_paths):




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









            analyzer.process_file(dest_path)









            









            new_tracks = self.extract_metadata(dest_path)









            









            if os.path.exists(DB_PATH):









                df = pd.read_excel(DB_PATH)









            else:









                df = pd.DataFrame(columns=['file_name', 'track_id', 'track_type', 'language_iso', 'track_name', 'is_default', 'subtitle_type', 'is_hearing_impaired', 'is_forced', 'notes', 'is_validated'])









                









            # SCHUTZ VOR ÜBERSCHREIBEN BEREITS VALIDIERTER SPUREN









            other_movies = df[df['file_name'] != basename]









            current_movie = df[df['file_name'] == basename]









            validated_tracks = current_movie[current_movie['is_validated'] == True]









            valid_spur_nums = validated_tracks['track_id'].tolist() if not validated_tracks.empty else []









            filtered_new_tracks = [t for t in new_tracks if t['track_id'] not in valid_spur_nums]









            









            df = pd.concat([other_movies, validated_tracks, pd.DataFrame(filtered_new_tracks)], ignore_index=True)









            df.to_excel(DB_PATH, index=False)




            




            # STATE UPDATE




            state_data = load_state()




            if basename not in state_data:




                state_data[basename] = {}




            for trk in filtered_new_tracks:




                trk_id = str(trk['track_id'])




                if trk_id not in state_data[basename]:




                    state_data[basename][trk_id] = {




                        'KI': {




                            'lang': trk['language_iso'],




                            'sdh': trk['is_hearing_impaired'],




                            'forced': trk['is_forced'],




                            'name': ''




                        },




                        'Validated': {




                            'lang': False,




                            'sdh': False,




                            'forced': False,




                            'name': False




                        }




                    }




            save_state(state_data)









            









            self.movie_ready.emit()









            









        self.progress_update.emit(total, total, "Alle Filme analysiert!")









        self.finished_analysis.emit()

















