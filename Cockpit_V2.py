import os
import sys

# sys.stdout override removed

import json
import shutil
import subprocess
import time
import pandas as pd
from PyQt5 import QtWidgets, QtCore, QtGui
import vlc

DIR_FILME = r"F:\Jellyfin\Filme"
DIR_SERIEN = r"F:\Jellyfin\Serien"
DIR_TEST = r"F:\Jellyfin_AI_Cockpit\Daten\Test_Videos"
MATRIX_PATH = r"F:\Jellyfin_AI_Cockpit\Daten\Informationsmatrix.xlsx"
PYTHON_EXE = sys.executable
MKVPROPEDIT = r"C:\Program Files\MKVToolNix\mkvpropedit.exe"

DARK_STYLESHEET = """
QWidget { background-color: #1e1e1e; color: #e0e0e0; font-family: 'Segoe UI', Arial, sans-serif; }
QPushButton { background-color: #0d47a1; color: white; border: none; padding: 8px 16px; border-radius: 4px; font-weight: bold; }
QPushButton:hover { background-color: #1565c0; }
QPushButton:disabled { background-color: #424242; color: #757575; }
QListWidget { background-color: #2d2d2d; border: 1px solid #424242; border-radius: 4px; }
QListWidget::item:selected { background-color: #1565c0; }
QLabel { font-size: 14px; }
QProgressBar { border: 1px solid #424242; border-radius: 4px; text-align: center; }
QProgressBar::chunk { background-color: #4caf50; }
QComboBox, QLineEdit { background-color: #2d2d2d; border: 1px solid #424242; padding: 4px; border-radius: 4px; }
QCheckBox { font-size: 14px; }
QSplitter::handle { background-color: #424242; }
QSlider::groove:horizontal { border: 1px solid #999999; height: 8px; background: #2d2d2d; margin: 2px 0; border-radius: 4px; }
QSlider::handle:horizontal { background: #0d47a1; border: 1px solid #0d47a1; width: 18px; margin: -2px 0; border-radius: 3px; }
"""

class ClickableSlider(QtWidgets.QSlider):
    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        if event.button() == QtCore.Qt.LeftButton:
            val = self.pixelPosToRangeValue(event.pos())
            self.setValue(val)
            self.sliderMoved.emit(val)
            
    def pixelPosToRangeValue(self, pos):
        opt = QtWidgets.QStyleOptionSlider()
        self.initStyleOption(opt)
        gr = self.style().subControlRect(QtWidgets.QStyle.CC_Slider, opt, QtWidgets.QStyle.SC_SliderGroove, self)
        sr = self.style().subControlRect(QtWidgets.QStyle.CC_Slider, opt, QtWidgets.QStyle.SC_SliderHandle, self)
        
        if self.orientation() == QtCore.Qt.Horizontal:
            sliderLength = sr.width()
            sliderMin = gr.x()
            sliderMax = gr.right() - sliderLength + 1
            pos = pos.x() - sliderLength / 2
        else:
            sliderLength = sr.height()
            sliderMin = gr.y()
            sliderMax = gr.bottom() - sliderLength + 1
            pos = pos.y() - sliderLength / 2
            
        span = sliderMax - sliderMin
        if span == 0: return self.minimum()
        
        # calculate value
        val = QtWidgets.QStyle.sliderValueFromPosition(self.minimum(), self.maximum(), int(pos - sliderMin), span, opt.upsideDown)
        return val

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
                "Name": os.path.basename(filepath),
                "ID": idx,
                "Art": track_type,
                "Effektive Sprache (ISO-Code)": lang,
                "Effektiver Name": "",
                "Standardspur": False,
                "Untertitelart": "",
                "Schwerhörig-Schalter": is_sdh,
                "Anzeige erzwingen-Schalter": is_forced,
                "Sonstiges": "AUTO"
            })
        return tracks

    def run(self):
        total = len(self.file_paths)
        if not os.path.exists(DIR_TEST):
            os.makedirs(DIR_TEST)
            
        for i, src_path in enumerate(self.file_paths):
            basename = os.path.basename(src_path)
            dest_path = os.path.join(DIR_TEST, basename)
            
            self.progress_update.emit(i, total, f"Kopiere {basename}...")
            if not os.path.exists(dest_path):
                shutil.copy2(src_path, dest_path)
                
            subprocess.run([MKVPROPEDIT, dest_path, "-d", "title"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
            
            self.progress_update.emit(i, total, f"Analysiere {basename}...")
            cmd = [PYTHON_EXE, "-c", f"import sys; sys.path.append(r'F:\\Jellyfin_AI_Cockpit'); from Master_Cleanup import process_file; process_file(r'{dest_path}')"]
            subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace', creationflags=subprocess.CREATE_NO_WINDOW)
            
            new_tracks = self.extract_metadata(dest_path)
            
            if os.path.exists(MATRIX_PATH):
                df = pd.read_excel(MATRIX_PATH)
            else:
                df = pd.DataFrame(columns=['Name', 'ID', 'Art', 'Effektive Sprache (ISO-Code)', 'Effektiver Name', 'Standardspur', 'Untertitelart', 'Schwerhörig-Schalter', 'Anzeige erzwingen-Schalter', 'Sonstiges'])
                
            # SCHUTZ VOR ÜBERSCHREIBEN BEREITS VALIDIERTER SPUREN
            other_movies = df[df['Name'] != basename]
            current_movie = df[df['Name'] == basename]
            validated_tracks = current_movie[current_movie['Sonstiges'] != 'AUTO']
            valid_spur_nums = validated_tracks['ID'].tolist() if not validated_tracks.empty else []
            filtered_new_tracks = [t for t in new_tracks if t['ID'] not in valid_spur_nums]
            
            df = pd.concat([other_movies, validated_tracks, pd.DataFrame(filtered_new_tracks)], ignore_index=True)
            df.to_excel(MATRIX_PATH, index=False)
            
            self.movie_ready.emit()
            
        self.progress_update.emit(total, total, "Alle Filme analysiert!")
        self.finished_analysis.emit()

class Screen1Selection(QtWidgets.QWidget):
    def __init__(self, parent):
        super().__init__()
        self.parent = parent
        layout = QtWidgets.QVBoxLayout(self)
        
        lbl_title = QtWidgets.QLabel("Schritt 1: Filme & Serien auswählen")
        lbl_title.setFont(QtGui.QFont("Segoe UI", 18, QtGui.QFont.Bold))
        layout.addWidget(lbl_title)
        
        self.lbl_desc = QtWidgets.QLabel("Lade Filme...")
        layout.addWidget(self.lbl_desc)
        
        self.list_widget = QtWidgets.QListWidget()
        self.list_widget.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        layout.addWidget(self.list_widget)
        
        bottom_layout = QtWidgets.QHBoxLayout()
        bottom_layout.addStretch()
        
        self.btn_jump_validator = QtWidgets.QPushButton("Direkt zum Validator (0 Filme warten) ➔")
        self.btn_jump_validator.setStyleSheet("background-color: #2e7d32;")
        self.btn_jump_validator.setEnabled(False)
        self.btn_jump_validator.clicked.connect(self.jump_to_validator)
        bottom_layout.addWidget(self.btn_jump_validator)
        
        self.btn_next = QtWidgets.QPushButton("Neu Analysieren & Validieren ➔")
        self.btn_next.setEnabled(False)
        self.btn_next.clicked.connect(self.go_next)
        bottom_layout.addWidget(self.btn_next)
        
        layout.addLayout(bottom_layout)
        
    def showEvent(self, event):
        self.scan_files()
        super().showEvent(event)

    def scan_files(self):
        self.list_widget.clear()
        self.lbl_desc.setText("Scanne Verzeichnisse...")
        QtWidgets.QApplication.processEvents()
        
        validated_movies = set()
        auto_movies_in_matrix = set()
        
        if os.path.exists(MATRIX_PATH):
            try:
                df = pd.read_excel(MATRIX_PATH)
                for movie in df['Name'].unique():
                    movie_rows = df[df['Name'] == movie]
                    if 'AUTO' not in movie_rows['Sonstiges'].values:
                        validated_movies.add(movie)
                    else:
                        auto_movies_in_matrix.add(movie)
            except:
                pass
                
        all_mkvs = []
        for d in [DIR_FILME, DIR_SERIEN]:
            if os.path.exists(d):
                for root, _, files in os.walk(d):
                    for f in files:
                        if f.endswith('.mkv'):
                            all_mkvs.append(os.path.join(root, f))
                            
        count = 0
        for mkv in all_mkvs:
            basename = os.path.basename(mkv)
            if basename not in validated_movies:
                if basename in auto_movies_in_matrix:
                    item = QtWidgets.QListWidgetItem(f"⚠️ {basename} (Fehlt noch, wird erneut gescannt)")
                    item.setForeground(QtGui.QColor("#ff9800"))
                else:
                    item = QtWidgets.QListWidgetItem(f"✨ {basename} (KOMPLETT NEU)")
                    item.setForeground(QtGui.QColor("#4caf50"))
                    
                item.setData(QtCore.Qt.UserRole, mkv)
                self.list_widget.addItem(item)
                count += 1
                
        self.btn_next.setEnabled(count > 0)
        self.lbl_desc.setText(f"Scan abgeschlossen ({count} Filme gefunden). Wähle Filme aus und drücke auf Analysieren.")
        if count > 0:
            self.list_widget.setCurrentRow(0)
        
        if len(auto_movies_in_matrix) > 0:
            self.btn_jump_validator.setText(f"Direkt zum Validator ({len(auto_movies_in_matrix)} Filme warten) ➔")
            self.btn_jump_validator.setEnabled(True)
        else:
            self.btn_jump_validator.setText("Direkt zum Validator (0 Filme warten) ➔")
            self.btn_jump_validator.setEnabled(False)

    def go_next(self):
        selected_items = self.list_widget.selectedItems()
        if not selected_items: return
        selected_paths = [item.data(QtCore.Qt.UserRole) for item in selected_items]
        self.parent.start_analysis_and_validation(selected_paths)
        
    def jump_to_validator(self):
        self.parent.stacked.setCurrentIndex(1)
        self.parent.screen3.lbl_bg_status.setText("KI-Analyse übersprungen. Lade bestehende Daten...")
        self.parent.screen3.bg_progress.setValue(self.parent.screen3.bg_progress.maximum())
        self.parent.screen3.check_for_new_data()

class Screen3Validator(QtWidgets.QWidget):
    def __init__(self, parent):
        super().__init__()
        self.parent = parent
        
        self.df = pd.DataFrame()
        self.auto_rows = []
        self.current_idx = 0
        self.current_filepath = None
        self.current_row = None
        
        self.vlc_instance = vlc.Instance("--no-xlib")
        self.media_player = self.vlc_instance.media_player_new()
        
        main_layout = QtWidgets.QVBoxLayout(self)
        
        # Header Status
        header_layout = QtWidgets.QHBoxLayout()
        self.btn_back_to_scan = QtWidgets.QPushButton("⬅ Zurück zur Dateiauswahl")
        self.btn_back_to_scan.clicked.connect(self.go_back)
        header_layout.addWidget(self.btn_back_to_scan)
        
        self.bg_status_frame = QtWidgets.QFrame()
        self.bg_status_frame.setStyleSheet("background-color: #2d2d2d; border-radius: 4px; padding: 5px;")
        bg_layout = QtWidgets.QHBoxLayout(self.bg_status_frame)
        self.lbl_bg_status = QtWidgets.QLabel("KI-Analyse: Initialisiere...")
        self.bg_progress = QtWidgets.QProgressBar()
        self.bg_progress.setMaximumWidth(300)
        bg_layout.addWidget(self.lbl_bg_status)
        bg_layout.addWidget(self.bg_progress)
        
        header_layout.addWidget(self.bg_status_frame)
        main_layout.addLayout(header_layout)
        
        # Splitter for whole center area
        self.splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        main_layout.addWidget(self.splitter, stretch=1)
        
        # Left Panel (Movie List)
        self.movie_list = QtWidgets.QListWidget()
        self.movie_list.itemClicked.connect(self.on_movie_selected)
        self.splitter.addWidget(self.movie_list)
        
        # Right Panel (Video + Form)
        right_panel = QtWidgets.QWidget()
        center_layout = QtWidgets.QHBoxLayout(right_panel)
        
        # Video Area
        left_layout = QtWidgets.QVBoxLayout()
        
        # Big Headers
        header_row = QtWidgets.QHBoxLayout()
        self.btn_toggle_list = QtWidgets.QPushButton("☰ Filmliste")
        self.btn_toggle_list.setMaximumWidth(150)
        self.btn_toggle_list.clicked.connect(lambda: self.movie_list.setVisible(not self.movie_list.isVisible()))
        header_row.addWidget(self.btn_toggle_list)
        
        self.lbl_huge_header = QtWidgets.QLabel("🎬 -")
        self.lbl_huge_header.setFont(QtGui.QFont("Segoe UI", 20, QtGui.QFont.Bold))
        self.lbl_huge_header.setStyleSheet("color: #4caf50;")
        header_row.addWidget(self.lbl_huge_header)
        
        self.lbl_huge_track = QtWidgets.QLabel("Spur: -")
        self.lbl_huge_track.setFont(QtGui.QFont("Segoe UI", 16))
        self.lbl_huge_track.setStyleSheet("color: #ff9800;")
        header_row.addWidget(self.lbl_huge_track)
        header_row.addStretch()
        
        left_layout.addLayout(header_row)
        
        self.video_frame = QtWidgets.QFrame()
        self.video_frame.setStyleSheet("background-color: black;")
        self.video_frame.setMinimumSize(500, 300)
        

            
        left_layout.addWidget(self.video_frame, stretch=1)
        
        # Controls
        controls = QtWidgets.QHBoxLayout()
        self.btn_play = QtWidgets.QPushButton("Play/Pause")
        self.btn_play.clicked.connect(self.toggle_play)
        controls.addWidget(self.btn_play)
        
        self.slider = ClickableSlider(QtCore.Qt.Horizontal)
        self.slider.setToolTip("Zeitleiste")
        self.slider.sliderMoved.connect(self.set_position)
        controls.addWidget(self.slider)
        
        self.lbl_time = QtWidgets.QLabel("00:00 / 00:00")
        controls.addWidget(self.lbl_time)
        
        left_layout.addLayout(controls)
        center_layout.addLayout(left_layout, stretch=2)
        
        # Form Area
        right_layout = QtWidgets.QVBoxLayout()
        lbl_title = QtWidgets.QLabel("Feld-für-Feld Validierung")
        lbl_title.setFont(QtGui.QFont("Segoe UI", 16, QtGui.QFont.Bold))
        right_layout.addWidget(lbl_title)
        
        self.lbl_info = QtWidgets.QLabel("Film: -\\nSpur: -")
        right_layout.addWidget(self.lbl_info)
        
        form = QtWidgets.QFormLayout()
        
        lang_layout = QtWidgets.QHBoxLayout()
        self.cmb_lang = QtWidgets.QComboBox()
        self.cmb_lang.addItems(["de", "eng", "fre", "spa", "ita", "chi", "ko", "jpn", "und"])
        self.cmb_lang.setEditable(True)
        lang_layout.addWidget(self.cmb_lang)
        self.btn_test_lang = QtWidgets.QPushButton("▶ Zeige Text")
        self.btn_test_lang.clicked.connect(lambda: self.seek_absolute(300000))
        lang_layout.addWidget(self.btn_test_lang)
        form.addRow("Sprache:", lang_layout)
        
        sdh_layout = QtWidgets.QHBoxLayout()
        self.chk_sdh = QtWidgets.QCheckBox("Ja")
        sdh_layout.addWidget(self.chk_sdh)
        self.btn_test_sdh = QtWidgets.QPushButton("▶ SDH-Marker")
        self.btn_test_sdh.clicked.connect(lambda: self.seek_absolute(600000))
        sdh_layout.addWidget(self.btn_test_sdh)
        form.addRow("SDH:", sdh_layout)
        
        forced_layout = QtWidgets.QHBoxLayout()
        self.chk_forced = QtWidgets.QCheckBox("Ja")
        forced_layout.addWidget(self.chk_forced)
        self.btn_test_forced = QtWidgets.QPushButton("▶ Forced-Stelle")
        self.btn_test_forced.clicked.connect(lambda: self.seek_absolute(900000))
        forced_layout.addWidget(self.btn_test_forced)
        form.addRow("Forced:", forced_layout)
        
        self.txt_titel = QtWidgets.QLineEdit()
        self.txt_titel.setPlaceholderText("Z.B. Director's Commentary")
        form.addRow("Spezial Name:", self.txt_titel)
        
        right_layout.addLayout(form)
        
        conv_layout = QtWidgets.QHBoxLayout()
        self.btn_conv_srt = QtWidgets.QPushButton("SRT ansehen")
        self.btn_conv_pgs = QtWidgets.QPushButton("PGS Bilder ansehen")
        conv_layout.addWidget(self.btn_conv_srt)
        conv_layout.addWidget(self.btn_conv_pgs)
        right_layout.addWidget(QtWidgets.QLabel("Convenience Tools:"))
        right_layout.addLayout(conv_layout)
        
        right_layout.addStretch()
        
        self.btn_save = QtWidgets.QPushButton("✓ Spur bestätigen & Weiter")
        self.btn_save.setStyleSheet("background-color: #2e7d32; font-size: 14px; padding: 12px;")
        self.btn_save.clicked.connect(self.save_and_next)
        self.btn_save.setEnabled(False)
        right_layout.addWidget(self.btn_save)
        
        self.btn_next_screen = QtWidgets.QPushButton("Validierung abschließen ➔")
        self.btn_next_screen.clicked.connect(lambda: self.parent.stacked.setCurrentIndex(2))
        right_layout.addWidget(self.btn_next_screen)
        
        center_layout.addLayout(right_layout, stretch=1)
        self.splitter.addWidget(right_panel)
        
        # Set splitter proportions (1:4 ratio)
        self.splitter.setSizes([200, 800])
        
        # Keyboard Shortcuts
        QtWidgets.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key_Left), self).activated.connect(lambda: self.seek(-5000))
        QtWidgets.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key_Right), self).activated.connect(lambda: self.seek(5000))
        QtWidgets.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key_Space), self).activated.connect(self.toggle_play)
        
        # Timer for UI updates
        self.timer = QtCore.QTimer(self)
        self.timer.setInterval(500)
        self.timer.timeout.connect(self.update_ui)
        self.timer.start()

    def go_back(self):
        try:
            self.media_player.pause()
        except:
            pass
        self.parent.stacked.setCurrentIndex(0)

    def update_movie_list(self):
        self.movie_list.clear()
        movies = []
        for idx in self.auto_rows:
            m = self.df.at[idx, 'Name']
            if m not in movies: movies.append(m)
        for m in movies:
            self.movie_list.addItem(m)
            
    def on_movie_selected(self, item):
        movie_name = item.text()
        for i, row_idx in enumerate(self.auto_rows):
            if self.df.at[row_idx, 'Name'] == movie_name:
                self.current_idx = i
                self.load_row()
                break

    def check_for_new_data(self):
        if not os.path.exists(MATRIX_PATH): return
        
        self.df = pd.read_excel(MATRIX_PATH)
        auto_mask = self.df['Sonstiges'] == 'AUTO'
        
        if auto_mask.any():
            self.auto_rows = self.df[auto_mask].index.tolist()
            self.update_movie_list()
            if self.lbl_info.text() == "Film: -\\nSpur: -":
                self.current_idx = 0
                self.load_row()

    def switch_vlc_track(self, typ, spur_index):
        if str(typ).lower() == "untertitel":
            all_rows_for_film = self.df[self.df['Name'] == self.current_row['Name']]
            sub_rows = all_rows_for_film[all_rows_for_film['Art'] == 'Untertitel']
            relative_idx = 1
            for idx, r in sub_rows.iterrows():
                if r['ID'] == spur_index: break
                relative_idx += 1
                
            spu_tracks = self.media_player.video_get_spu_description()
            if spu_tracks:
                valid_spus = [t[0] for t in spu_tracks if t[0] >= 0]
                if relative_idx - 1 < len(valid_spus):
                    vlc_id = valid_spus[relative_idx - 1]
                    self.media_player.video_set_spu(vlc_id)
                    
            target_lang = "eng" if "eng" in str(self.current_row['Effektive Sprache (ISO-Code)']).lower() else "ger"
            aud_rows = all_rows_for_film[all_rows_for_film['Art'] == 'Audio']
            
            found_audio_idx = 0
            rel = 0
            for idx, r in aud_rows.iterrows():
                if target_lang in str(r['Effektive Sprache (ISO-Code)']).lower():
                    found_audio_idx = rel
                    break
                if target_lang == "ger" and "de" in str(r['Effektive Sprache (ISO-Code)']).lower():
                    found_audio_idx = rel
                    break
                rel += 1
                
            aud_tracks = self.media_player.audio_get_track_description()
            if aud_tracks:
                valid_auds = [t[0] for t in aud_tracks if t[0] >= 0]
                if found_audio_idx < len(valid_auds):
                    self.media_player.audio_set_track(valid_auds[found_audio_idx])
                elif len(valid_auds) > 0:
                    self.media_player.audio_set_track(valid_auds[0])
            
        elif str(typ).lower() == "audio":
            all_rows_for_film = self.df[self.df['Name'] == self.current_row['Name']]
            aud_rows = all_rows_for_film[all_rows_for_film['Art'] == 'Audio']
            relative_idx = 1
            for idx, r in aud_rows.iterrows():
                if r['ID'] == spur_index: break
                relative_idx += 1
                
            aud_tracks = self.media_player.audio_get_track_description()
            if aud_tracks:
                valid_auds = [t[0] for t in aud_tracks if t[0] >= 0]
                if relative_idx - 1 < len(valid_auds):
                    vlc_id = valid_auds[relative_idx - 1]
                    self.media_player.audio_set_track(vlc_id)
                    
            self.media_player.video_set_spu(-1)

    def load_row(self):
        if self.current_idx >= len(self.auto_rows):
            self.lbl_info.setText("Warte auf weitere Analyse...")
            self.btn_save.setEnabled(False)
            return
            
        row_idx = self.auto_rows[self.current_idx]
        row = self.df.loc[row_idx]
        self.current_row = row
        
        film = row['Name']
        spur = row['ID']
        typ = row['Art']
        
        self.lbl_info.setText(f"Film: {film}\\nSpur: {spur} ({typ})\\nFortschritt: {self.current_idx + 1} von {len(self.auto_rows)} geladenen Spuren")
        self.btn_save.setEnabled(True)
        
        # Highlight in list
        for i in range(self.movie_list.count()):
            if self.movie_list.item(i).text() == film:
                self.movie_list.setCurrentRow(i)
                break
        
        self.cmb_lang.setCurrentText(str(row['Effektive Sprache (ISO-Code)']))
        self.chk_sdh.setChecked(bool(row['Schwerhörig-Schalter']))
        self.chk_forced.setChecked(bool(row['Anzeige erzwingen-Schalter']))
        if 'Effektiver Name' in row and pd.notna(row['Effektiver Name']):
            self.txt_titel.setText(str(row['Effektiver Name']))
        else:
            self.txt_titel.setText("")
        
        filepath = os.path.join(DIR_TEST, film)
        if not os.path.exists(filepath):
            for d in [DIR_FILME, DIR_SERIEN]:
                for root, _, files in os.walk(d):
                    if film in files:
                        filepath = os.path.join(root, film)
                        break
                        
        if os.path.exists(filepath) and filepath != self.current_filepath:
            self.current_filepath = filepath
            media = self.vlc_instance.media_new(filepath)
            self.media_player.set_media(media)
            if sys.platform.startswith('linux'):
                self.media_player.set_xwindow(self.video_frame.winId())
            elif sys.platform == "win32":
                self.media_player.set_hwnd(self.video_frame.winId())
            elif sys.platform == "darwin":
                self.media_player.set_nsobject(int(self.video_frame.winId()))
            self.media_player.play()
            QtCore.QTimer.singleShot(1500, lambda: self.switch_vlc_track(typ, int(spur)))
        elif filepath == self.current_filepath:
            self.switch_vlc_track(typ, int(spur))

    def save_and_next(self):
        row_idx = self.auto_rows[self.current_idx]
        
        original_lang = str(self.df.at[row_idx, 'Effektive Sprache (ISO-Code)'])
        original_sdh = bool(self.df.at[row_idx, 'Schwerhörig-Schalter'])
        original_forced = bool(self.df.at[row_idx, 'Anzeige erzwingen-Schalter'])
        
        new_lang = self.cmb_lang.currentText()
        new_sdh = self.chk_sdh.isChecked()
        new_forced = self.chk_forced.isChecked()
        new_titel = self.txt_titel.text()
        
        accuracy_file = r"F:\Jellyfin_AI_Cockpit\Daten\KI_Accuracy.json"
        
        stats = {"total": 0, "correct_lang": 0, "correct_sdh": 0, "correct_forced": 0, "perfect_tracks": 0}
        if os.path.exists(accuracy_file):
            try:
                with open(accuracy_file, 'r', encoding='utf-8') as af:
                    stats = json.load(af)
            except: pass
            
        stats["total"] += 1
        perfect = True
        
        if original_lang == new_lang: stats["correct_lang"] += 1
        else: perfect = False
        
        if original_sdh == new_sdh: stats["correct_sdh"] += 1
        else: perfect = False
        
        if original_forced == new_forced: stats["correct_forced"] += 1
        else: perfect = False
        
        if perfect: stats["perfect_tracks"] += 1
        
        with open(accuracy_file, 'w', encoding='utf-8') as af:
            json.dump(stats, af, indent=4)
            
        self.df.at[row_idx, 'Effektive Sprache (ISO-Code)'] = new_lang
        self.df.at[row_idx, 'Schwerhörig-Schalter'] = new_sdh
        self.df.at[row_idx, 'Anzeige erzwingen-Schalter'] = new_forced
        self.df.at[row_idx, 'Effektiver Name'] = new_titel
        self.df.at[row_idx, 'Sonstiges'] = ""
        
        self.df.to_excel(MATRIX_PATH, index=False)
        self.current_idx += 1
        
        # Refresh auto rows
        self.df = pd.read_excel(MATRIX_PATH)
        auto_mask = self.df['Sonstiges'] == 'AUTO'
        self.auto_rows = self.df[auto_mask].index.tolist() if auto_mask.any() else []
        self.update_movie_list()
        
        if self.current_idx >= len(self.auto_rows):
            self.current_idx = 0
            
        self.load_row()

    def set_position(self, position):
        self.media_player.set_time(position)
        
    def seek(self, ms):
        t = self.media_player.get_time()
        if t != -1: self.media_player.set_time(t + ms)
        
    def seek_absolute(self, ms):
        self.media_player.set_time(ms)
        self.media_player.play()

    def toggle_play(self):
        # Ignore if user is typing in a text field
        focus_widget = QtWidgets.QApplication.focusWidget()
        if isinstance(focus_widget, (QtWidgets.QLineEdit, QtWidgets.QComboBox)):
            return
            
        if self.media_player.is_playing(): self.media_player.pause()
        else: self.media_player.play()
            
    def update_ui(self):
        length = self.media_player.get_length()
        time_ms = self.media_player.get_time()
        
        if length > 0 and time_ms >= 0:
            if not self.slider.isSliderDown():
                self.slider.setMaximum(length)
                self.slider.setValue(time_ms)
                
            t = time_ms // 1000
            l = length // 1000
            self.lbl_time.setText(f"{t//60:02d}:{t%60:02d} / {l//60:02d}:{l%60:02d}")
            
    def stop(self):
        try:
            self.media_player.pause()
        except:
            pass

class Screen4Trainer(QtWidgets.QWidget):
    def __init__(self, parent):
        super().__init__()
        self.parent = parent
        layout = QtWidgets.QVBoxLayout(self)
        
        lbl_title = QtWidgets.QLabel("Schritt 3: KI Leaderboard & Trainer")
        lbl_title.setFont(QtGui.QFont("Segoe UI", 18, QtGui.QFont.Bold))
        layout.addWidget(lbl_title)
        
        layout.addWidget(QtWidgets.QLabel("Glückwunsch! Du hast Spuren erfolgreich validiert."))
        
        self.dash_frame = QtWidgets.QFrame()
        self.dash_frame.setStyleSheet("background-color: #2d2d2d; border-radius: 8px; padding: 20px;")
        dash_layout = QtWidgets.QVBoxLayout(self.dash_frame)
        self.lbl_dash = QtWidgets.QLabel("Lade Statistiken...")
        self.lbl_dash.setFont(QtGui.QFont("Segoe UI", 14))
        dash_layout.addWidget(self.lbl_dash)
        layout.addWidget(self.dash_frame)
        
        self.btn_refresh = QtWidgets.QPushButton("Statistiken aktualisieren")
        self.btn_refresh.clicked.connect(self.load_stats)
        layout.addWidget(self.btn_refresh)
        
        layout.addSpacing(20)
        self.btn_runner = QtWidgets.QPushButton("Test-Runner starten (Erstellt Bericht für Antigravity)")
        self.btn_runner.setStyleSheet("background-color: #e65100; font-size: 16px; padding: 20px;")
        layout.addWidget(self.btn_runner)
        layout.addStretch()
        
    def load_stats(self):
        accuracy_file = r"F:\Jellyfin_AI_Cockpit\Daten\KI_Accuracy.json"
        if os.path.exists(accuracy_file):
            try:
                with open(accuracy_file, 'r', encoding='utf-8') as f:
                    s = json.load(f)
                t = s.get("total", 1)
                if t == 0: t = 1
                
                text = (
                    "🏆 Validierte Spuren gesamt: " + str(s.get('total', 0)) + "\\n\\n" +
                    "✔️ Sprache korrekt: " + str(s.get('correct_lang', 0)) + " (" + str(int(s.get('correct_lang',0)/t*100)) + "%)\\n" +
                    "✔️ SDH korrekt: " + str(s.get('correct_sdh', 0)) + " (" + str(int(s.get('correct_sdh',0)/t*100)) + "%)\\n" +
                    "✔️ Forced korrekt: " + str(s.get('correct_forced', 0)) + " (" + str(int(s.get('correct_forced',0)/t*100)) + "%)\\n\\n" +
                    "🚀 Makellose Spuren (100% KI-Treffer): " + str(s.get('perfect_tracks', 0)) + " (" + str(int(s.get('perfect_tracks',0)/t*100)) + "%)"
                )
                text = text.replace("\\n", "\n")
                self.lbl_dash.setText(text)
            except Exception as e:
                self.lbl_dash.setText(f"Fehler beim Laden der Statistiken: {e}")
        else:
            self.lbl_dash.setText("Noch keine Statistiken vorhanden. Validiere eine Spur!")
            
    def showEvent(self, event):
        self.load_stats()
        super().showEvent(event)

class CockpitWizard(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Jellyfin AI Cockpit 2.0")
        self.resize(1200, 750)
        self.setStyleSheet(DARK_STYLESHEET)
        
        self.stacked = QtWidgets.QStackedWidget()
        self.setCentralWidget(self.stacked)
        
        self.screen1 = Screen1Selection(self)
        self.screen3 = Screen3Validator(self)
        self.screen4 = Screen4Trainer(self)
        
        self.stacked.addWidget(self.screen1)
        self.stacked.addWidget(self.screen3)
        self.stacked.addWidget(self.screen4)
        
    def start_analysis_and_validation(self, file_paths):
        self.stacked.setCurrentIndex(1)
        
        self.screen3.bg_progress.setMaximum(len(file_paths))
        self.screen3.bg_progress.setValue(0)
        self.screen3.lbl_bg_status.setText(f"KI-Analyse läuft: 0/{len(file_paths)}")
        
        self.thread = AnalysisThread(file_paths)
        self.thread.progress_update.connect(self.update_bg_progress)
        self.thread.movie_ready.connect(self.screen3.check_for_new_data)
        self.thread.finished_analysis.connect(self.analysis_done)
        self.thread.start()
        
        self.screen3.check_for_new_data()
        
    def update_bg_progress(self, current, total, msg):
        self.screen3.bg_progress.setValue(current)
        self.screen3.lbl_bg_status.setText(f"KI-Analyse ({current}/{total}): {msg}")
        
    def analysis_done(self):
        self.screen3.lbl_bg_status.setText("KI-Analyse vollständig abgeschlossen!")
        self.screen3.bg_progress.setValue(self.screen3.bg_progress.maximum())

    def closeEvent(self, event):
        self.screen3.stop()
        event.accept()
        
if __name__ == '__main__':
    app = QtWidgets.QApplication(sys.argv)
    app.setStyle("Fusion")
    window = CockpitWizard()
    window.show()
    sys.exit(app.exec_())
