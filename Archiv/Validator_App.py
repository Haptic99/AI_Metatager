import os
import sys
import pandas as pd
import json
import subprocess
from PyQt5 import QtWidgets, QtCore, QtGui
import vlc

MATRIX_PATH = r"F:\Jellyfin_AI_Cockpit\Daten\Inforamtionsmatrix.xlsx"
MKVPROPEDIT = r"C:\Program Files\MKVToolNix\mkvpropedit.exe"
JELLYFIN_DIR = r"F:\Jellyfin"

def find_mkv_path(filename):
    for root, dirs, files in os.walk(JELLYFIN_DIR):
        if filename in files:
            return os.path.join(root, filename)
    return None

class ValidatorApp(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Jellyfin AI Cockpit - Validator")
        self.resize(1200, 700)
        
        # Data
        self.df = pd.DataFrame()
        self.auto_rows = []
        self.current_idx = 0
        self.current_row = None
        self.current_filepath = None
        self.timestamps = []
        
        # VLC
        self.instance = vlc.Instance("--no-xlib")
        self.media_player = self.instance.media_player_new()
        
        self.init_ui()
        self.load_data()
        
    def init_ui(self):
        central_widget = QtWidgets.QWidget(self)
        self.setCentralWidget(central_widget)
        
        main_layout = QtWidgets.QHBoxLayout(central_widget)
        
        # Left: Video Player
        left_layout = QtWidgets.QVBoxLayout()
        self.video_frame = QtWidgets.QFrame()
        self.video_frame.setMinimumSize(800, 600)
        self.video_frame.setStyleSheet("background-color: black;")
        
        # Connect VLC to video frame
        if sys.platform.startswith('linux'):
            self.media_player.set_xwindow(self.video_frame.winId())
        elif sys.platform == "win32":
            self.media_player.set_hwnd(self.video_frame.winId())
        elif sys.platform == "darwin":
            self.media_player.set_nsobject(int(self.video_frame.winId()))
            
        left_layout.addWidget(self.video_frame)
        
        # Video controls
        controls_layout = QtWidgets.QHBoxLayout()
        self.btn_play = QtWidgets.QPushButton("Play / Pause (Space)")
        self.btn_play.clicked.connect(self.toggle_play)
        controls_layout.addWidget(self.btn_play)
        
        self.btn_back = QtWidgets.QPushButton("<< 5s (Left)")
        self.btn_back.clicked.connect(lambda: self.seek(-5000))
        controls_layout.addWidget(self.btn_back)
        
        self.btn_fwd = QtWidgets.QPushButton(">> 5s (Right)")
        self.btn_fwd.clicked.connect(lambda: self.seek(5000))
        controls_layout.addWidget(self.btn_fwd)
        
        left_layout.addLayout(controls_layout)
        main_layout.addLayout(left_layout, stretch=2)
        
        # Right: Validation Form
        right_layout = QtWidgets.QVBoxLayout()
        
        self.lbl_status = QtWidgets.QLabel("Status: Lade Daten...")
        self.lbl_status.setFont(QtGui.QFont("Arial", 14, QtGui.QFont.Bold))
        right_layout.addWidget(self.lbl_status)
        
        self.lbl_film = QtWidgets.QLabel("Film: -")
        right_layout.addWidget(self.lbl_film)
        
        self.lbl_spur = QtWidgets.QLabel("Spur: -")
        self.lbl_spur.setFont(QtGui.QFont("Arial", 12, QtGui.QFont.Bold))
        right_layout.addWidget(self.lbl_spur)
        
        right_layout.addSpacing(20)
        
        # Form
        form_layout = QtWidgets.QFormLayout()
        
        self.cmb_lang = QtWidgets.QComboBox()
        self.cmb_lang.addItems(["de", "eng", "fre", "spa", "ita", "chi", "ko", "jpn", "und"])
        self.cmb_lang.setEditable(True)
        form_layout.addRow("Sprache:", self.cmb_lang)
        
        self.chk_sdh = QtWidgets.QCheckBox("Ja")
        form_layout.addRow("SDH (Schwerhörig):", self.chk_sdh)
        
        self.chk_forced = QtWidgets.QCheckBox("Ja")
        form_layout.addRow("Forced (Erzwungen):", self.chk_forced)
        
        right_layout.addLayout(form_layout)
        
        # Test Buttons
        self.btn_test_sub = QtWidgets.QPushButton("▶ Probe lesen (Springe zu Text)")
        self.btn_test_sub.clicked.connect(lambda: self.jump_to_interesting('text'))
        right_layout.addWidget(self.btn_test_sub)
        
        self.btn_test_sdh = QtWidgets.QPushButton("▶ SDH prüfen (Springe zu Marker)")
        self.btn_test_sdh.clicked.connect(lambda: self.jump_to_interesting('sdh'))
        right_layout.addWidget(self.btn_test_sdh)
        
        right_layout.addStretch()
        
        # Save Button
        self.btn_save = QtWidgets.QPushButton("✓ Spur validieren & Speichern")
        self.btn_save.setFont(QtGui.QFont("Arial", 12, QtGui.QFont.Bold))
        self.btn_save.setStyleSheet("background-color: #4CAF50; color: white; padding: 10px;")
        self.btn_save.clicked.connect(self.save_and_next)
        right_layout.addWidget(self.btn_save)
        
        main_layout.addLayout(right_layout, stretch=1)
        
        # Keyboard shortcuts
        QtWidgets.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key_Space), self, self.toggle_play)
        QtWidgets.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key_Left), self, lambda: self.seek(-5000))
        QtWidgets.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key_Right), self, lambda: self.seek(5000))

    def load_data(self):
        if not os.path.exists(MATRIX_PATH):
            self.lbl_status.setText("Fehler: Matrix nicht gefunden!")
            return
            
        self.df = pd.read_excel(MATRIX_PATH)
        # Find rows where Sonstiges == 'AUTO'
        auto_mask = self.df['Sonstiges'] == 'AUTO'
        
        if not auto_mask.any():
            self.lbl_status.setText("Fertig! Keine 'AUTO' Spuren mehr.")
            self.auto_rows = []
        else:
            self.auto_rows = self.df[auto_mask].index.tolist()
            self.lbl_status.setText(f"{len(self.auto_rows)} Spuren zu validieren.")
            self.current_idx = 0
            self.load_row()
            
    def load_row(self):
        if self.current_idx >= len(self.auto_rows):
            self.lbl_status.setText("Alle validiert! Neustart nötig.")
            return
            
        row_idx = self.auto_rows[self.current_idx]
        self.current_row = self.df.loc[row_idx]
        
        film = self.current_row['Film']
        spur = self.current_row['Spur']
        typ = self.current_row['Typ']
        lang = self.current_row['Sprache']
        is_sdh = self.current_row['SDH']
        is_forced = self.current_row['Forced']
        
        self.lbl_film.setText(f"Film: {film}")
        self.lbl_spur.setText(f"Spur: {spur} ({typ})")
        
        self.cmb_lang.setCurrentText(str(lang))
        self.chk_sdh.setChecked(bool(is_sdh))
        self.chk_forced.setChecked(bool(is_forced))
        
        self.lbl_status.setText(f"Validiere: {self.current_idx + 1} / {len(self.auto_rows)}")
        
        # Load Video
        filepath = find_mkv_path(film)
        if filepath and filepath != self.current_filepath:
            self.current_filepath = filepath
            media = self.instance.media_new(filepath)
            self.media_player.set_media(media)
            self.media_player.play()
            
            # Wait for video to start so we can set subtitle track
            QtCore.QTimer.singleShot(1500, self.set_subtitle_track)
        elif filepath == self.current_filepath:
            self.set_subtitle_track()
            
        # Parse interesting timestamps from Master_Cleanup logs (simulated for now)
        # In a real scenario, Master_Cleanup would save a JSON with timestamps per track
        # We will extract it from the SRT or ffprobe if needed.
        self.find_timestamps(filepath, spur)

    def set_subtitle_track(self):
        # VLC track IDs usually start at 1, but we need to match the stream index.
        # It's tricky with VLC. Usually vlc_player.video_set_spu() sets the subtitle track.
        # We just try setting it to the relative subtitle index.
        spur = int(self.current_row['Spur'])
        # A simple hack: set SPU to spur (often doesn't map 1:1, but close enough for testing)
        self.media_player.video_set_spu(spur)
        
    def find_timestamps(self, filepath, spur):
        # Placeholder for finding interesting timestamps.
        # For text: 10 minutes in.
        # For SDH: 15 minutes in.
        self.timestamps = {'text': 600000, 'sdh': 900000}
        
    def jump_to_interesting(self, kind):
        if kind in self.timestamps:
            ts = self.timestamps[kind]
            self.media_player.set_time(ts)
            self.media_player.play()
            
    def toggle_play(self):
        if self.media_player.is_playing():
            self.media_player.pause()
        else:
            self.media_player.play()
            
    def seek(self, ms):
        current_time = self.media_player.get_time()
        if current_time != -1:
            self.media_player.set_time(current_time + ms)
            
    def save_and_next(self):
        row_idx = self.auto_rows[self.current_idx]
        
        # Update DataFrame
        self.df.at[row_idx, 'Sprache'] = self.cmb_lang.currentText()
        self.df.at[row_idx, 'SDH'] = self.chk_sdh.isChecked()
        self.df.at[row_idx, 'Forced'] = self.chk_forced.isChecked()
        self.df.at[row_idx, 'Sonstiges'] = "" # Remove AUTO
        
        # Save Excel
        self.df.to_excel(MATRIX_PATH, index=False)
        print(f"Saved row {row_idx} to Matrix.")
        
        # (Optional) Update MKV file with mkvpropedit here based on the new tags
        # ...
        
        self.current_idx += 1
        self.load_row()

    def closeEvent(self, event):
        self.media_player.stop()
        event.accept()

if __name__ == '__main__':
    app = QtWidgets.QApplication(sys.argv)
    window = ValidatorApp()
    window.show()
    sys.exit(app.exec_())
