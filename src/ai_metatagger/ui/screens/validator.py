from ai_metatagger.ui.components.widgets import ClickableSlider
from ai_metatagger.ui.styles import DARK_STYLESHEET
import os
import sys
import vlc
import json
import pandas as pd
from PyQt5 import QtWidgets, QtCore, QtGui
from PyQt5.QtCore import Qt
from ai_metatagger.config import DIR_FILME, DIR_SERIEN, DIR_TEST, DB_PATH, CONFIG_PATH, save_config, CONFIG
from ai_metatagger.utils.state_manager import load_matrix, save_matrix, load_state, save_state
class Screen3Validator(QtWidgets.QWidget):
    def __init__(self, parent):
        super().__init__()
        self.parent = parent
        self.df = pd.DataFrame()
        self.auto_rows = []
        self.current_idx = 0
        self.current_filepath = None
        self.current_row = None
        self.vlc_instance = None
        self.media_player = None
        main_layout = QtWidgets.QVBoxLayout(self)
        # Splitter for whole center area
        self.splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        main_layout.addWidget(self.splitter, stretch=1)
        # Left Panel (Movie Lists)
        self.left_panel = QtWidgets.QWidget()
        left_panel_layout = QtWidgets.QVBoxLayout(self.left_panel)
        left_panel_layout.setContentsMargins(0, 0, 0, 0)
        self.lbl_loaded = QtWidgets.QLabel("Zur Validierung bereit:")
        self.lbl_loaded.setFont(QtGui.QFont("Segoe UI", 10, QtGui.QFont.Bold))
        left_panel_layout.addWidget(self.lbl_loaded)
        self.movie_list = QtWidgets.QListWidget()
        self.movie_list.itemClicked.connect(self.on_movie_selected)
        left_panel_layout.addWidget(self.movie_list)
        
        self.btn_remove_movie = QtWidgets.QPushButton("X Film ignorieren")
        self.btn_remove_movie.setStyleSheet("background-color: #d32f2f;")
        self.btn_remove_movie.clicked.connect(self.remove_movie)
        left_panel_layout.addWidget(self.btn_remove_movie)
        self.lbl_available = QtWidgets.QLabel("Neue Filme (Auswählen für KI-Analyse):")
        self.lbl_available.setFont(QtGui.QFont("Segoe UI", 10, QtGui.QFont.Bold))
        left_panel_layout.addWidget(self.lbl_available)
        self.scan_list_widget = QtWidgets.QListWidget()
        self.scan_list_widget.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.scan_list_widget.itemSelectionChanged.connect(self.on_scan_selection_changed)
        left_panel_layout.addWidget(self.scan_list_widget)
        self.btn_analyze = QtWidgets.QPushButton("Neu Analysieren \u27a1")
        self.btn_analyze.setStyleSheet("background-color: #2e7d32; font-weight: bold; padding: 10px;")
        self.btn_analyze.setEnabled(False)
        self.btn_analyze.clicked.connect(self.start_new_analysis)
        left_panel_layout.addWidget(self.btn_analyze)
        self.bg_status_frame = QtWidgets.QFrame()
        self.bg_status_frame.setStyleSheet("background-color: #2d2d2d; border-radius: 4px; padding: 5px; margin-top: 5px;")
        bg_layout = QtWidgets.QVBoxLayout(self.bg_status_frame)
        self.lbl_bg_status = QtWidgets.QLabel("KI-Analyse: Initialisiere...")
        self.lbl_bg_status.setWordWrap(True)
        self.bg_progress = QtWidgets.QProgressBar()
        self.btn_cancel_analysis = QtWidgets.QPushButton("Stopp")
        self.btn_cancel_analysis.setStyleSheet("background-color: #d32f2f; font-weight: bold; padding: 2px;")
        self.btn_cancel_analysis.clicked.connect(self.parent.cancel_analysis)
        bg_layout.addWidget(self.lbl_bg_status)
        bg_layout.addWidget(self.bg_progress)
        bg_layout.addWidget(self.btn_cancel_analysis)
        self.bg_status_frame.hide()
        left_panel_layout.addWidget(self.bg_status_frame)
        self.splitter.addWidget(self.left_panel)
        # Right Panel (Video + Form)
        right_panel = QtWidgets.QWidget()
        center_layout = QtWidgets.QHBoxLayout(right_panel)
        # Video Area
        left_layout = QtWidgets.QVBoxLayout()
        # Big Headers
        header_row = QtWidgets.QHBoxLayout()
        self.btn_toggle_list = QtWidgets.QPushButton("☰ Filmliste")
        self.btn_toggle_list.setMaximumWidth(150)
        self.btn_toggle_list.clicked.connect(lambda: self.left_panel.setVisible(not self.left_panel.isVisible()))
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
        
        self.vol_icon = QtWidgets.QLabel("Vol:")
        controls.addWidget(self.vol_icon)
        self.slider_vol = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.slider_vol.setMaximum(100)
        self.slider_vol.setValue(100)
        self.slider_vol.setMaximumWidth(100)
        self.slider_vol.valueChanged.connect(self.set_volume)
        controls.addWidget(self.slider_vol)
        
        left_layout.addLayout(controls)
        center_layout.addLayout(left_layout, stretch=2)
        # Form Area
        right_layout = QtWidgets.QVBoxLayout()
        lbl_title = QtWidgets.QLabel("Feld-für-Feld Validierung")
        lbl_title.setFont(QtGui.QFont("Segoe UI", 16, QtGui.QFont.Bold))
        right_layout.addWidget(lbl_title)
        self.track_list = QtWidgets.QTableWidget()
        self.track_list.setColumnCount(3)
        self.track_list.setHorizontalHeaderLabels(["Spur", "Art", "Codec"])
        self.track_list.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.track_list.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.track_list.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.track_list.verticalHeader().setVisible(False)
        self.track_list.horizontalHeader().setStretchLastSection(True)
        self.track_list.setMaximumHeight(250)
        self.track_list.setStyleSheet("QTableWidget::item { padding: 2px; }")
        self.track_list.verticalHeader().setDefaultSectionSize(24)
        self.track_list.itemClicked.connect(self.on_track_selected)
        right_layout.addWidget(self.track_list)
        self.form_grid = QtWidgets.QGridLayout()
        self.form_grid.setSpacing(20)
        self.form_grid.setColumnStretch(0, 1)
        self.form_grid.setColumnStretch(1, 2)
        self.form_grid.setColumnStretch(2, 3)
        self.form_grid.setColumnStretch(3, 1)
        self.form_grid.setColumnStretch(4, 1)
        # Labels for Headers
        self.form_grid.addWidget(QtWidgets.QLabel("<b>Eigenschaft</b>"), 0, 0)
        self.form_grid.addWidget(QtWidgets.QLabel("<b>KI-Vorschlag</b>"), 0, 1)
        self.form_grid.addWidget(QtWidgets.QLabel("<b>Dein Wert</b>"), 0, 2)
        self.form_grid.addWidget(QtWidgets.QLabel("<b>Testen</b>"), 0, 3)
        self.form_grid.addWidget(QtWidgets.QLabel("<b>Geprüft</b>"), 0, 4)
        # 1. Sprache
        self.form_grid.addWidget(QtWidgets.QLabel("Sprache:"), 1, 0)
        self.lbl_ki_lang = QtWidgets.QLabel("-")
        self.form_grid.addWidget(self.lbl_ki_lang, 1, 1)
        self.cmb_lang = QtWidgets.QComboBox()
        self.cmb_lang.addItems(["de", "eng", "fre", "spa", "ita", "chi", "ko", "jpn", "und"])
        self.cmb_lang.setEditable(True)
        self.form_grid.addWidget(self.cmb_lang, 1, 2)
        self.btn_test_lang = QtWidgets.QPushButton("▶ Text")
        self.btn_test_lang.clicked.connect(lambda: self.seek_absolute(300000))
        self.form_grid.addWidget(self.btn_test_lang, 1, 3)
        self.btn_valid_lang = QtWidgets.QPushButton("✔")
        self.btn_valid_lang.clicked.connect(lambda: self.validate_field('lang'))
        self.form_grid.addWidget(self.btn_valid_lang, 1, 4)
        # 2. SDH
        self.lbl_sdh_title = QtWidgets.QLabel("SDH:")
        self.form_grid.addWidget(self.lbl_sdh_title, 2, 0)
        self.lbl_ki_sdh = QtWidgets.QLabel("-")
        self.form_grid.addWidget(self.lbl_ki_sdh, 2, 1)
        self.cmb_sdh = QtWidgets.QComboBox()
        self.cmb_sdh.addItems(["Nein", "Ja"])
        self.form_grid.addWidget(self.cmb_sdh, 2, 2)
        self.btn_test_sdh = QtWidgets.QPushButton("▶ Marker")
        self.btn_test_sdh.clicked.connect(lambda: self.seek_absolute(600000))
        self.form_grid.addWidget(self.btn_test_sdh, 2, 3)
        self.btn_valid_sdh = QtWidgets.QPushButton("✔")
        self.btn_valid_sdh.clicked.connect(lambda: self.validate_field('sdh'))
        self.form_grid.addWidget(self.btn_valid_sdh, 2, 4)
        # 3. Forced
        self.lbl_forced_title = QtWidgets.QLabel("Forced:")
        self.form_grid.addWidget(self.lbl_forced_title, 3, 0)
        self.lbl_ki_forced = QtWidgets.QLabel("-")
        self.form_grid.addWidget(self.lbl_ki_forced, 3, 1)
        self.cmb_forced = QtWidgets.QComboBox()
        self.cmb_forced.addItems(["Nein", "Ja"])
        self.form_grid.addWidget(self.cmb_forced, 3, 2)
        self.btn_test_forced = QtWidgets.QPushButton("▶ Forced")
        self.btn_test_forced.clicked.connect(lambda: self.seek_absolute(900000))
        self.form_grid.addWidget(self.btn_test_forced, 3, 3)
        self.btn_valid_forced = QtWidgets.QPushButton("✔")
        self.btn_valid_forced.clicked.connect(lambda: self.validate_field('forced'))
        self.form_grid.addWidget(self.btn_valid_forced, 3, 4)
        # 4. Name
        self.lbl_name_title = QtWidgets.QLabel("Spezial Name:")
        self.form_grid.addWidget(self.lbl_name_title, 4, 0)
        self.lbl_ki_name = QtWidgets.QLabel("-")
        self.form_grid.addWidget(self.lbl_ki_name, 4, 1)
        self.txt_titel = QtWidgets.QLineEdit()
        self.txt_titel.setPlaceholderText("z.B. Director's Commentary")
        self.form_grid.addWidget(self.txt_titel, 4, 2)
        self.btn_valid_name = QtWidgets.QPushButton("✔")
        self.btn_valid_name.clicked.connect(lambda: self.validate_field('name'))
        self.form_grid.addWidget(self.btn_valid_name, 4, 4)
        right_layout.addLayout(self.form_grid)
        conv_layout = QtWidgets.QHBoxLayout()
        self.btn_conv_srt = QtWidgets.QPushButton("SRT ansehen")
        self.btn_conv_pgs = QtWidgets.QPushButton("PGS Bilder ansehen")
        self.btn_conv_srt.clicked.connect(self.open_srt)
        self.btn_conv_pgs.clicked.connect(self.open_pgs)
        conv_layout.addWidget(self.btn_conv_srt)
        conv_layout.addWidget(self.btn_conv_pgs)
        self.lbl_conv = QtWidgets.QLabel("Analysematerial einsehen:")
        self.lbl_conv.setFont(QtGui.QFont("Segoe UI", 10, QtGui.QFont.Bold))
        right_layout.addWidget(self.lbl_conv)
        right_layout.addLayout(conv_layout)
        right_layout.addStretch()
        self.btn_save = QtWidgets.QPushButton("✔ Spur bestätigen & Weiter")
        self.btn_save.setStyleSheet("background-color: #2e7d32; font-size: 14px; padding: 12px;")
        self.btn_save.clicked.connect(self.save_and_next)
        self.btn_save.setEnabled(False)
        right_layout.addWidget(self.btn_save)
        self.btn_next_screen = QtWidgets.QPushButton("Validierung abschließen ➔")
        self.btn_next_screen.clicked.connect(lambda: self.parent.stacked.setCurrentIndex(1))
        right_layout.addWidget(self.btn_next_screen)
        center_layout.addLayout(right_layout, stretch=1)
        self.splitter.addWidget(right_panel)
        # Set splitter proportions (1:4 ratio)
        self.splitter.setSizes([200, 800])
        # Keyboard Shortcuts
        QtWidgets.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key_Left), self).activated.connect(lambda: self.seek(-5000))
        QtWidgets.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key_Right), self).activated.connect(lambda: self.seek(5000))
        QtWidgets.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key_Space), self).activated.connect(self.toggle_play)
        QtWidgets.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key_Up), self).activated.connect(lambda: self.change_volume(10))
        QtWidgets.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key_Down), self).activated.connect(lambda: self.change_volume(-10))
        # Timer for UI updates
        self.timer = QtCore.QTimer(self)
        self.timer.setInterval(500)
        self.timer.timeout.connect(self.update_ui)
        self.timer.start()
    def showEvent(self, event):
        self.scan_files()
        self.check_for_new_data()
        super().showEvent(event)
    def on_scan_selection_changed(self):
        self.btn_analyze.setEnabled(len(self.scan_list_widget.selectedItems()) > 0)
    def start_new_analysis(self):
        selected_items = self.scan_list_widget.selectedItems()
        if not selected_items: return
        selected_paths = [item.data(QtCore.Qt.UserRole) for item in selected_items]
        self.parent.start_analysis_and_validation(selected_paths)
    def scan_files(self):
        self.scan_list_widget.clear()
        validated_movies = set()
        auto_movies_in_matrix = set()
        if True:
            try:
                df = load_matrix()
                for movie in df['file_name'].unique():
                    movie_rows = df[df['file_name'] == movie]
                    if False not in movie_rows['is_validated'].values:
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
                    item = QtWidgets.QListWidgetItem(f"\u26a0\ufe0f {basename} (Fehlt noch)")
                    item.setForeground(QtGui.QColor("#ff9800"))
                else:
                    item = QtWidgets.QListWidgetItem(f"✨ {basename} (KOMPLETT NEU)")
                    item.setForeground(QtGui.QColor("#4caf50"))
                item.setData(QtCore.Qt.UserRole, mkv)
                self.scan_list_widget.addItem(item)
                count += 1
    def update_movie_list(self):
        self.movie_list.clear()
        movies = []
        for idx in self.auto_rows:
            m = self.df.at[idx, 'file_name']
            if m not in movies: movies.append(m)
        for m in movies:
            self.movie_list.addItem(m)
    def on_movie_selected(self, item):
        movie_name = item.text()
        for i, row_idx in enumerate(self.auto_rows):
            if self.df.at[row_idx, 'file_name'] == movie_name:
                self.current_idx = i
                self.load_row()
                break
    def check_for_new_data(self):
        if not os.path.exists(DB_PATH): return
        self.df = load_matrix()
        auto_mask = self.df['is_validated'] == False
        if auto_mask.any():
            self.auto_rows = self.df[auto_mask].index.tolist()
            self.update_movie_list()
            if getattr(self, 'current_film', None) is None:
                self.current_idx = 0
                self.load_row()
        else:
            self.auto_rows = []
            self.update_movie_list()
            self.current_film = None
            self.current_idx = 0
            self.track_list.setRowCount(0)
            if hasattr(self, 'lbl_huge_header'):
                self.lbl_huge_header.setText("Alles erledigt!")
            if hasattr(self, 'lbl_huge_track'):
                self.lbl_huge_track.setText("")
            if hasattr(self, 'btn_save'):
                self.btn_save.setEnabled(False)
    def switch_vlc_track(self, typ, spur_index):
        if str(typ).lower() == "untertitel":
            all_rows_for_film = self.df[self.df['file_name'] == self.current_row['file_name']]
            sub_rows = all_rows_for_film[all_rows_for_film['track_type'] == 'Untertitel']
            relative_idx = 1
            for idx, r in sub_rows.iterrows():
                if r['track_id'] == spur_index: break
                relative_idx += 1
            spu_tracks = self.media_player.video_get_spu_description()
            if spu_tracks:
                valid_spus = [t[0] for t in spu_tracks if t[0] >= 0]
                if relative_idx - 1 < len(valid_spus):
                    vlc_id = valid_spus[relative_idx - 1]
                    self.media_player.video_set_spu(vlc_id)
            target_lang = "eng" if "eng" in str(self.current_row['language_iso']).lower() else "ger"
            aud_rows = all_rows_for_film[all_rows_for_film['track_type'] == 'Audio']
            found_audio_idx = 0
            rel = 0
            for idx, r in aud_rows.iterrows():
                if target_lang in str(r['language_iso']).lower():
                    found_audio_idx = rel
                    break
                if target_lang == "ger" and "de" in str(r['language_iso']).lower():
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
            all_rows_for_film = self.df[self.df['file_name'] == self.current_row['file_name']]
            aud_rows = all_rows_for_film[all_rows_for_film['track_type'] == 'Audio']
            relative_idx = 1
            for idx, r in aud_rows.iterrows():
                if r['track_id'] == spur_index: break
                relative_idx += 1
            aud_tracks = self.media_player.audio_get_track_description()
            if aud_tracks:
                valid_auds = [t[0] for t in aud_tracks if t[0] >= 0]
                if relative_idx - 1 < len(valid_auds):
                    vlc_id = valid_auds[relative_idx - 1]
                    self.media_player.audio_set_track(vlc_id)
            self.media_player.video_set_spu(-1)
    def populate_track_list(self, movie_name):
        self.track_list.setRowCount(0)
        row_count = 0
        for i, row_idx in enumerate(self.auto_rows):
            row = self.df.loc[row_idx]
            if row['file_name'] == movie_name:
                self.track_list.insertRow(row_count)
                
                item_spur = QtWidgets.QTableWidgetItem(str(row['track_id']))
                item_spur.setData(QtCore.Qt.UserRole, i)
                item_art = QtWidgets.QTableWidgetItem(str(row['track_type']))
                ctype = str(row.get('subtitle_type', ''))
                if not ctype: ctype = "Audio" if str(row['track_type']).lower() == 'audio' else "SRT"
                item_codec = QtWidgets.QTableWidgetItem(ctype)
                
                if row['is_validated'] == True:
                    item_spur.setForeground(QtGui.QColor("#aaaaaa"))
                    item_art.setForeground(QtGui.QColor("#aaaaaa"))
                    item_codec.setForeground(QtGui.QColor("#aaaaaa"))
                    
                self.track_list.setItem(row_count, 0, item_spur)
                self.track_list.setItem(row_count, 1, item_art)
                self.track_list.setItem(row_count, 2, item_codec)
                row_count += 1
    def on_track_selected(self, item):
        # We might click column 1 or 2, get row and then column 0
        row = item.row()
        first_item = self.track_list.item(row, 0)
        self.current_idx = first_item.data(QtCore.Qt.UserRole)
        self.load_row()
    def validate_field(self, field):
        film = self.current_row['file_name']
        trk_id = str(self.current_row['track_id'])
        state_file = os.path.join(os.path.dirname(DB_PATH), 'validation_state.json')
        if os.path.exists(state_file):
            try:
                import json
                state_data = load_state()
                state_data[film][trk_id]['Validated'][field] = True
                save_state(state_data)
            except: pass
        # UI Update
        btn = getattr(self, f"btn_valid_{field}")
        btn.setStyleSheet("background-color: #4caf50; color: white;")
        self.check_all_fields_validated()
    def check_all_fields_validated(self):
        film = self.current_row['file_name']
        trk_id = str(self.current_row['track_id'])
        state_file = os.path.join(os.path.dirname(DB_PATH), 'validation_state.json')
        all_valid = False
        if os.path.exists(state_file):
            try:
                import json
                state_data = load_state()
                val_dict = state_data[film][trk_id]['Validated']
                
                is_audio = str(self.current_row['track_type']).lower() == 'audio'
                if is_audio:
                    # For audio, only 'lang' needs to be validated
                    all_valid = val_dict.get('lang', False)
                else:
                    all_valid = all(val_dict.values())
            except: pass
        self.btn_save.setEnabled(all_valid)
        
        # Color the current track row in track_list
        for i in range(self.track_list.rowCount()):
            item = self.track_list.item(i, 0)
            if item and item.data(QtCore.Qt.UserRole) == self.current_idx:
                for col in range(3):
                    it = self.track_list.item(i, col)
                    if it:
                        if all_valid:
                            it.setBackground(QtGui.QColor("#1b5e20"))
                        else:
                            it.setBackground(QtGui.QColor(0,0,0,0))
                break
    def load_row(self):
        if self.current_idx >= len(self.auto_rows) or len(self.auto_rows) == 0:
            self.btn_save.setEnabled(False)
            if len(self.auto_rows) == 0:
                self.current_film = None
                self.track_list.setRowCount(0)
                if hasattr(self, 'lbl_huge_header'):
                    self.lbl_huge_header.setText("Alles erledigt!")
                if hasattr(self, 'lbl_huge_track'):
                    self.lbl_huge_track.setText("")
                if self.media_player:
                    self.media_player.stop()
            return
        row_idx = self.auto_rows[self.current_idx]
        row = self.df.loc[row_idx]
        self.current_row = row
        film = row['file_name']
        if getattr(self, 'current_film', None) != film:
            self.current_film = film
            self.populate_track_list(film)
        # Highlight in track list
        for i in range(self.track_list.rowCount()):
            item = self.track_list.item(i, 0)
            if item and item.data(QtCore.Qt.UserRole) == self.current_idx:
                self.track_list.setCurrentItem(item)
                break
        spur = row['track_id']
        typ = row['track_type']
        
        is_audio = str(row['track_type']).lower() == 'audio'
        for i in range(self.form_grid.count()):
            widget_item = self.form_grid.itemAt(i)
            if widget_item and widget_item.widget():
                r_idx, c_idx, rSpan, cSpan = self.form_grid.getItemPosition(i)
                if r_idx in [2, 3, 4]:
                    widget_item.widget().setVisible(not is_audio)
        # Highlight in list
        for i in range(self.movie_list.count()):
            if self.movie_list.item(i).text() == film:
                self.movie_list.setCurrentRow(i)
                break
        # Show/Hide Analysematerial buttons
        self.btn_conv_srt.setVisible(False)
        self.btn_conv_pgs.setVisible(False)
        self.lbl_conv.setVisible(False)
        if str(row['track_type']).lower() == 'untertitel':
            codec = str(row.get('subtitle_type', '')).lower()
            if not codec or 'srt' in codec or 'subrip' in codec:
                self.btn_conv_srt.setVisible(True)
                self.lbl_conv.setVisible(True)
            else:
                self.btn_conv_pgs.setVisible(True)
                self.lbl_conv.setVisible(True)

        self.cmb_lang.setCurrentText(str(row['language_iso']))
        self.cmb_sdh.setCurrentText("Ja" if bool(row['is_hearing_impaired']) else "Nein")
        self.cmb_forced.setCurrentText("Ja" if bool(row['is_forced']) else "Nein")
        if 'track_name' in row and pd.notna(row['track_name']):
            self.txt_titel.setText(str(row['track_name']))
        else:
            self.txt_titel.setText("")
            
        try:
            state_data = load_state()
            trk_id = str(row['track_id'])
            film = row['file_name']
            ki_data = state_data.get(film, {}).get(trk_id, {}).get('KI', {})
            
            self.lbl_ki_lang.setText(str(ki_data.get('lang', '-')))
            self.lbl_ki_sdh.setText("Ja" if ki_data.get('sdh') else "Nein")
            self.lbl_ki_forced.setText("Ja" if ki_data.get('forced') else "Nein")
            name_val = ki_data.get('name', '')
            self.lbl_ki_name.setText(str(name_val) if name_val else "-")
        
            # Reset Button colors based on state
            val_data = state_data.get(film, {}).get(trk_id, {}).get('Validated', {})
            for field in ['lang', 'sdh', 'forced', 'name']:
                btn = getattr(self, f"btn_valid_{field}")
                if val_data.get(field):
                    btn.setStyleSheet("background-color: #4caf50; color: white;")
                else:
                    btn.setStyleSheet("")
            self.check_all_fields_validated()
        except Exception as e:
            self.lbl_ki_lang.setText("-")
            self.lbl_ki_sdh.setText("-")
            self.lbl_ki_forced.setText("-")
            self.lbl_ki_name.setText("-")
            for field in ['lang', 'sdh', 'forced', 'name']:
                getattr(self, f"btn_valid_{field}").setStyleSheet("")
            self.check_all_fields_validated()
        filepath = os.path.join(DIR_TEST, film)
        if not os.path.exists(filepath):
            for d in [DIR_FILME, DIR_SERIEN]:
                for root, _, files in os.walk(d):
                    if film in files:
                        filepath = os.path.join(root, film)
                        break
        if os.path.exists(filepath) and filepath != self.current_filepath:
            self.current_filepath = filepath
            if self.vlc_instance is None:
                self.vlc_instance = vlc.Instance("--no-xlib")
                self.media_player = self.vlc_instance.media_player_new()
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
        original_lang = str(self.df.at[row_idx, 'language_iso'])
        original_sdh = bool(self.df.at[row_idx, 'is_hearing_impaired'])
        original_forced = bool(self.df.at[row_idx, 'is_forced'])
        new_lang = self.cmb_lang.currentText()
        new_sdh = self.cmb_sdh.currentText() == "Ja"
        new_forced = self.cmb_forced.currentText() == "Ja"
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
        self.df.at[row_idx, 'language_iso'] = new_lang
        self.df.at[row_idx, 'is_hearing_impaired'] = new_sdh
        self.df.at[row_idx, 'is_forced'] = new_forced
        self.df.at[row_idx, 'track_name'] = new_titel
        self.df.at[row_idx, 'is_validated'] = True
        self.df.to_excel(DB_PATH, index=False)
        
        # Check if the movie is completely validated
        film = self.df.at[row_idx, 'file_name']
        remaining_for_film = self.df[(self.df['file_name'] == film) & (self.df['is_validated'] == False)]
        if remaining_for_film.empty:
            # Stop media player if it is playing this film
            if getattr(self, 'current_film', None) == film:
                if self.media_player:
                    self.media_player.stop()
            # Delete file
            filepath = os.path.join(DIR_TEST, film)
            if os.path.exists(filepath):
                try:
                    os.remove(filepath)
                except Exception as e:
                    print(f"Konnte Datei nicht lschen: {e}")
                    
        for i in range(self.track_list.rowCount()):
            item = self.track_list.item(i, 0)
            if item and item.data(QtCore.Qt.UserRole) == self.current_idx:
                for col in range(3):
                    self.track_list.item(i, col).setForeground(QtGui.QColor("#aaaaaa"))
                    self.track_list.item(i, col).setBackground(QtGui.QColor(0,0,0,0))
                break
        self.current_idx += 1
        # Refresh auto rows
        self.df = load_matrix()
        auto_mask = self.df['is_validated'] == False
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
        if not self.media_player: return
        if self.media_player.is_playing(): self.media_player.pause()
        else: self.media_player.play()
    def update_ui(self):
        if not self.media_player: return
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

    def open_srt(self):
        import glob
        if self.current_row is None: return
        film = self.current_row['file_name']
        idx = self.current_row['track_id']
        temp_dir = os.path.join(DIR_TEST, "..", "temp_cleanup")
        path = os.path.join(temp_dir, f"{film}_sub_{idx}.srt")
        if os.path.exists(path):
            os.startfile(path)
        else:
            QtWidgets.QMessageBox.warning(self, "Nicht gefunden", "Das SRT File wurde nach der Analyse nicht gefunden.")

    def open_pgs(self):
        import glob
        if self.current_row is None: return
        film = self.current_row['file_name']
        idx = self.current_row['track_id']
        temp_dir = os.path.join(DIR_TEST, "..", "temp_cleanup")
        search = os.path.join(temp_dir, f"{film}_sub_{idx}_*.png")
        files = glob.glob(search)
        if files:
            files.sort()
            os.startfile(files[0])
        else:
            QtWidgets.QMessageBox.warning(self, "Nicht gefunden", "Die extrahierten PGS Bilder wurden nicht gefunden.")

    def remove_movie(self):
        item = self.movie_list.currentItem()
        if not item: return
        film = item.text()
        
        reply = QtWidgets.QMessageBox.question(self, 'Film entfernen', f'Willst du "{film}" wirklich aus der Validierungsliste entfernen? Die KI-Werte werden dann nicht übernommen.', QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No, QtWidgets.QMessageBox.No)
        if reply == QtWidgets.QMessageBox.Yes:
            # Stop playback if it's playing
            if getattr(self, 'current_film', None) == film:
                if self.media_player:
                    self.media_player.stop()
                    
            # Delete file from Test_Videos
            import glob
            filepath = os.path.join(DIR_TEST, film)
            if os.path.exists(filepath):
                try:
                    os.remove(filepath)
                except Exception as e:
                    print(f"Konnte Datei nicht löschen: {e}")
                    
            # Set is_validated to True for all tracks of this film to hide it
            self.df.loc[self.df['file_name'] == film, 'is_validated'] = True
            save_matrix(self.df)
            
            # Clear UI if it's the current film
            if getattr(self, 'current_film', None) == film:
                self.current_film = None
                self.current_idx = 0
                self.track_list.setRowCount(0)
            
            # Refresh
            self.check_for_new_data()

    def set_volume(self, val):
        if self.media_player:
            self.media_player.audio_set_volume(val)
            
    def change_volume(self, delta):
        new_vol = max(0, min(100, self.slider_vol.value() + delta))
        self.slider_vol.setValue(new_vol)
