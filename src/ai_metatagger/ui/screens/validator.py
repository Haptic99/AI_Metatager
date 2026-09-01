import os
import glob
import json
import pandas as pd
from PyQt5 import QtWidgets, QtCore, QtGui
from ai_metatagger.config import DIR_FILME, DIR_SERIEN, DIR_TEST, SUBS_DIR
from ai_metatagger.ui.components.widgets import ClickableSlider
from ai_metatagger.ui.components.video_player import VideoPlayerWidget
from ai_metatagger.ui.components.validator_sidebar import ValidatorSidebarWidget
from ai_metatagger.ui.components.validator_form import ValidatorFormWidget
from ai_metatagger.core.validator_controller import ValidatorController
import threading
import time


class Screen3Validator(QtWidgets.QWidget):
    scan_finished = QtCore.pyqtSignal(list)

    def __init__(self, parent):
        super().__init__()
        self.parent = parent
        self.ctrl = ValidatorController()

        self.auto_rows = []
        self.current_idx = 0
        self.current_film = None
        self.current_row = None
        
        self._film_path_cache = {}

        self._setup_ui()
        self._connect_signals()

        # Timer for UI updates (video timeline)
        self.timer = QtCore.QTimer(self)
        self.timer.setInterval(500)
        self.timer.timeout.connect(self.update_ui)
        self.timer.start()

    def _setup_ui(self):
        main_layout = QtWidgets.QVBoxLayout(self)
        self.splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        main_layout.addWidget(self.splitter, stretch=1)

        # Sidebar
        self.sidebar = ValidatorSidebarWidget()
        self.splitter.addWidget(self.sidebar)

        # Right Panel
        right_panel = QtWidgets.QWidget()
        center_layout = QtWidgets.QHBoxLayout(right_panel)

        # Video Area
        left_layout = QtWidgets.QVBoxLayout()
        header_row = QtWidgets.QHBoxLayout()
        self.btn_toggle_list = QtWidgets.QPushButton("☰ Filmliste")
        self.btn_toggle_list.setMaximumWidth(150)
        self.btn_toggle_list.clicked.connect(
            lambda: self.sidebar.setVisible(not self.sidebar.isVisible()))
        header_row.addWidget(self.btn_toggle_list)

        self.lbl_huge_header = QtWidgets.QLabel("🎬 -")
        self.lbl_huge_header.setFont(
            QtGui.QFont("Segoe UI", 20, QtGui.QFont.Bold))
        self.lbl_huge_header.setStyleSheet("color: #4caf50;")
        header_row.addWidget(self.lbl_huge_header)

        self.lbl_huge_track = QtWidgets.QLabel("Spur: -")
        self.lbl_huge_track.setFont(QtGui.QFont("Segoe UI", 16))
        self.lbl_huge_track.setStyleSheet("color: #ff9800;")
        header_row.addWidget(self.lbl_huge_track)
        header_row.addStretch()
        left_layout.addLayout(header_row)

        self.player_widget = VideoPlayerWidget()
        self.player_widget.setMinimumSize(500, 300)
        left_layout.addWidget(self.player_widget, stretch=1)

        # Player Controls
        controls = QtWidgets.QHBoxLayout()
        self.btn_play = QtWidgets.QPushButton("Play/Pause")
        self.btn_play.clicked.connect(self.player_widget.toggle_play)
        controls.addWidget(self.btn_play)

        self.slider = ClickableSlider(QtCore.Qt.Horizontal)
        self.slider.sliderMoved.connect(self.player_widget.set_position)
        controls.addWidget(self.slider)

        self.lbl_time = QtWidgets.QLabel("00:00 / 00:00")
        controls.addWidget(self.lbl_time)

        self.vol_icon = QtWidgets.QLabel("Vol:")
        controls.addWidget(self.vol_icon)
        self.slider_vol = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.slider_vol.setMaximum(100)
        self.slider_vol.setValue(100)
        self.slider_vol.setMaximumWidth(100)
        self.slider_vol.valueChanged.connect(self.player_widget.set_volume)
        controls.addWidget(self.slider_vol)

        left_layout.addLayout(controls)
        center_layout.addLayout(left_layout, stretch=2)

        # Form Area
        right_layout = QtWidgets.QVBoxLayout()
        self.form_widget = ValidatorFormWidget()
        right_layout.addWidget(self.form_widget)

        self.btn_next_screen = QtWidgets.QPushButton(
            "Validierung abschließen ➔")
        self.btn_next_screen.setMaximumWidth(850)
        self.btn_next_screen.clicked.connect(
            lambda: self.parent.stacked.setCurrentIndex(1))
        right_layout.addWidget(self.btn_next_screen)

        center_layout.addLayout(right_layout, stretch=1)
        self.splitter.addWidget(right_panel)
        self.splitter.setSizes([200, 800])

        # Shortcuts
        QtWidgets.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key_Left), self).activated.connect(
            lambda: self.player_widget.seek(-5000))
        QtWidgets.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key_Right), self).activated.connect(
            lambda: self.player_widget.seek(5000))
        QtWidgets.QShortcut(QtGui.QKeySequence(
            QtCore.Qt.Key_Space), self).activated.connect(self._toggle_play_safe)
        QtWidgets.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key_Up), self).activated.connect(
            lambda: self._change_volume(10))
        QtWidgets.QShortcut(QtGui.QKeySequence(
            QtCore.Qt.Key_Down), self).activated.connect(lambda: self._change_volume(-10))

    def _connect_signals(self):
        self.sidebar.movie_selected.connect(self.on_movie_selected)
        self.sidebar.remove_movie_requested.connect(self.remove_movie)
        self.sidebar.analyze_requested.connect(self.start_new_analysis)
        self.sidebar.cancel_analysis_requested.connect(
            self.parent.cancel_analysis)
            
        self.scan_finished.connect(self.sidebar.set_scan_files)

        self.form_widget.track_selected.connect(self.on_track_selected)
        self.form_widget.field_validated.connect(self.validate_field)
        self.form_widget.save_requested.connect(self.save_and_next)

        self.form_widget.seek_requested.connect(self.player_widget.seek_absolute)
        self.form_widget.pgs_image_double_clicked.connect(lambda path: os.startfile(path))
        self.form_widget.audio_track_changed.connect(self._on_audio_track_changed)

    def _ensure_seek_list(self):
        if not self.current_seek_list and self.current_row is not None:
            film = self.current_row['file_name']
            typ = self.current_row['track_type']
            spur = self.current_row['track_id']
            self.current_seek_list = self._get_all_seek_times(film, typ, spur)
            self.current_seek_idx = 0
            if not self.current_seek_list:
                self.current_seek_list = [300000] # Default 5 mins

    def _test_text_clicked(self):
        self._ensure_seek_list()
        if self.current_seek_list:
            self.player_widget.seek_absolute(self.current_seek_list[self.current_seek_idx])

    def _get_closest_index(self, target_ms):
        if not self.current_seek_list:
            return 0
        return min(range(len(self.current_seek_list)), key=lambda i: abs(self.current_seek_list[i] - target_ms))

    def _test_sdh_clicked(self):
        self._ensure_seek_list()
        if self.current_seek_list:
            self.current_seek_idx = self._get_closest_index(600000)
            self.player_widget.seek_absolute(self.current_seek_list[self.current_seek_idx])
            
    def _test_forced_clicked(self):
        self._ensure_seek_list()
        if self.current_seek_list:
            self.current_seek_idx = self._get_closest_index(900000)
            self.player_widget.seek_absolute(self.current_seek_list[self.current_seek_idx])

    def _test_text_next_clicked(self):
        self._ensure_seek_list()
        if self.current_seek_list:
            self.current_seek_idx = min(len(self.current_seek_list) - 1, self.current_seek_idx + 1)
            self.player_widget.seek_absolute(self.current_seek_list[self.current_seek_idx])

    def _test_text_prev_clicked(self):
        self._ensure_seek_list()
        if self.current_seek_list:
            self.current_seek_idx = max(0, self.current_seek_idx - 1)
            self.player_widget.seek_absolute(self.current_seek_list[self.current_seek_idx])

    def _on_audio_track_changed(self, rel_idx):
        """Switch VLC audio track without disturbing playback."""
        if self.player_widget and self.player_widget.media_player:
            aud_tracks = self.player_widget.media_player.audio_get_track_description()
            if aud_tracks:
                valid_auds = [t[0] for t in aud_tracks if t[0] >= 0]
                if rel_idx - 1 < len(valid_auds):
                    vlc_id = valid_auds[rel_idx - 1]
                    self.player_widget.media_player.audio_set_track(vlc_id)

    def _toggle_play_safe(self):
        focus_widget = QtWidgets.QApplication.focusWidget()
        if isinstance(focus_widget, (QtWidgets.QLineEdit, QtWidgets.QComboBox)):
            return
        self.player_widget.toggle_play()

    def _change_volume(self, delta):
        v = min(100, max(0, self.slider_vol.value() + delta))
        self.slider_vol.setValue(v)

    def showEvent(self, event):
        self.scan_files()
        self.check_for_new_data()
        super().showEvent(event)

    def scan_files(self):
        processed_movies = set()

        try:
            if not self.ctrl.df.empty:
                processed_movies = set(self.ctrl.df['file_name'].unique())
        except Exception as e:
            print(f"Error in scan_files DB read: {e}")

        def _do_scan(processed):
            files = []
            for d in [DIR_FILME, DIR_SERIEN]:
                if os.path.exists(d):
                    for root, _, filenames in os.walk(d):
                        for f in filenames:
                            if f.endswith(('.mkv', '.mp4', '.avi')):
                                # Exclude if exact name is in DB
                                if f in processed:
                                    continue
                                    
                                # Also exclude if we have an .mkv version of this .mp4/.avi in the DB!
                                base_name = os.path.splitext(f)[0]
                                if f"{base_name}.mkv" in processed:
                                    continue
                                    
                                files.append(os.path.join(root, f))
                                
            # Send back to UI safely
            self.scan_finished.emit(files)

        import threading
        threading.Thread(target=_do_scan, args=(processed_movies,), daemon=True).start()

    def check_for_new_data(self):
        self.ctrl.refresh_data()

        df = self.ctrl.df
        if df.empty:
            self.auto_rows = []
        else:
            unvalidated_movies = df[~df['is_validated']]['file_name'].unique()
            auto_mask = df['file_name'].isin(unvalidated_movies)
            self.auto_rows = df[auto_mask].index.tolist(
            ) if auto_mask.any() else []

        self.update_movie_list()
        self.scan_files()

        if len(self.auto_rows) > 0:
            if self.current_idx >= len(self.auto_rows):
                self.current_idx = 0
            self.load_row()
        else:
            self.current_film = None
            self.current_row = None
            self.lbl_huge_header.setText("Alles erledigt!")
            self.lbl_huge_track.setText("")
            self.form_widget.lbl_header.setText("✅ Alles erledigt!")
            self.player_widget.clear_media()
            self.form_widget.track_list.setRowCount(0)
            self.form_widget.clear_ki_data()

    def update_movie_list(self):
        df = self.ctrl.df
        if df.empty:
            self.sidebar.set_movies([])
            return
        movies = df[~df['is_validated']]['file_name'].unique().tolist()
        self.sidebar.set_movies(movies)
        if self.current_film:
            self.sidebar.select_movie(self.current_film)

    def on_movie_selected(self, film):
        for i, row_idx in enumerate(self.auto_rows):
            if self.ctrl.df.loc[row_idx, 'file_name'] == film:
                self.current_idx = i
                self.load_row(autoplay=True)
                break

    def on_target_id_changed(self, row_idx, original_track_id, new_target_id):
        df = self.ctrl.df
        film = df.loc[row_idx, 'file_name']
        old_target_id = str(df.loc[row_idx].get('target_track_id', original_track_id))
        
        if old_target_id == new_target_id:
            return
            
        # Find the row that currently has the new_target_id as its target
        conflict_idx = None
        for idx, r in df.iterrows():
            if r['file_name'] == film and str(r.get('target_track_id', r['track_id'])) == new_target_id and idx != row_idx:
                conflict_idx = idx
                break
                
        # Perform swap in dataframe
        df.at[row_idx, 'target_track_id'] = new_target_id
        if conflict_idx is not None:
            df.at[conflict_idx, 'target_track_id'] = old_target_id
            
        # Save to SQLite
        from ai_metatagger.utils.state_manager import update_track
        update_track(film, original_track_id, {'target_track_id': new_target_id})
        if conflict_idx is not None:
            conflict_track_id = str(df.loc[conflict_idx, 'track_id'])
            update_track(film, conflict_track_id, {'target_track_id': old_target_id})
            
        # Refresh the UI table to show the swapped values
        current_sel = self.current_idx
        self.populate_track_list(film)
        
        # Restore selection
        for i in range(self.form_widget.track_list.rowCount()):
            item = self.form_widget.track_list.item(i, 0)
            if item and item.data(QtCore.Qt.UserRole) == current_sel:
                self.form_widget.track_list.setCurrentItem(item)
                break

    def on_track_selected(self, idx):
        self._save_current_ui_to_memory()
        self.current_idx = idx
        self.load_row(autoplay=True)

    def _save_current_ui_to_memory(self):
        if self.current_row is None: return
        film = self.current_row['file_name']
        trk_id = str(self.current_row['track_id'])
        form_data = self.form_widget.get_form_data()
        
        mask = (self.ctrl.df['file_name'] == film) & (self.ctrl.df['track_id'].astype(str) == trk_id)
        if mask.any():
            self.ctrl.df.loc[mask, 'language_iso'] = form_data['lang']
            self.ctrl.df.loc[mask, 'is_hearing_impaired'] = form_data['sdh']
            self.ctrl.df.loc[mask, 'is_forced'] = form_data['forced']
            self.ctrl.df.loc[mask, 'is_default'] = form_data['default'] # <-- NEU
            self.ctrl.df.loc[mask, 'track_name'] = form_data['title']
            
        self.current_row['language_iso'] = form_data['lang']
        self.current_row['is_hearing_impaired'] = form_data['sdh']
        self.current_row['is_forced'] = form_data['forced']
        self.current_row['is_default'] = form_data['default'] # <-- NEU
        self.current_row['track_name'] = form_data['title']
        
        try:
            import json
            from ai_metatagger.utils.state_manager import DB_LOCK, init_db
            with DB_LOCK:
                conn = init_db()
                cursor = conn.cursor()
                cursor.execute(
                    """UPDATE media_tracks 
                       SET language_iso = ?, 
                           is_hearing_impaired = ?, 
                           is_forced = ?, 
                           is_default = ?, 
                           track_name = ?
                       WHERE file_name = ? AND CAST(track_id AS TEXT) = ?""",
                    (form_data['lang'], form_data['sdh'], form_data['forced'], form_data['default'], form_data['title'], film, trk_id)
                )
                conn.commit()
                conn.close()
        except Exception as e:
            print(f"Fehler beim Zwischenspeichern: {e}")

    def load_row(self, autoplay=False):
        self.current_seek_list = []
        self.current_seek_idx = 0
        if self.current_idx >= len(self.auto_rows) or len(self.auto_rows) == 0:
            return

        row_idx = self.auto_rows[self.current_idx]
        row = self.ctrl.df.loc[row_idx]
        self.current_row = row
        film = row['file_name']

        if self.current_film != film:
            self.current_film = film
            self.populate_track_list(film)
            self.form_widget.cmb_audio_track.clear()

        # Select in track list
        for i in range(self.form_widget.track_list.rowCount()):
            item = self.form_widget.track_list.item(i, 0)
            if item and item.data(QtCore.Qt.UserRole) == self.current_idx:
                self.form_widget.track_list.setCurrentItem(item)
                break

        spur = row['track_id']
        typ = row['track_type']

        self.lbl_huge_header.setText(f"🎬 {film}")
        self.lbl_huge_track.setText(f"Spur: {spur} ({typ})")
        
        self.form_widget.lbl_header.setText(f"🎬 {film}  ·  Spur {spur} ({typ})")

        self.form_widget.set_form_data(row)
        ki_data = self.ctrl.get_ki_data(film, spur)
        self.form_widget.set_ki_data(ki_data)
        
        # Populate audio track dropdown for subtitle tracks
        if typ.lower() != 'audio':
            df = self.ctrl.df
            audio_rows = df[(df['file_name'] == film) & (df['track_type'].str.lower() == 'audio')]
            audio_items = []
            rel_idx = 1
            for _, arow in audio_rows.iterrows():
                lang = str(arow.get('language_iso', '?'))
                name = str(arow.get('track_name', '')) if pd.notna(arow.get('track_name')) else ''
                label = f"🔊 {lang}" + (f" ({name})" if name else "")
                audio_items.append((rel_idx, label))
                rel_idx += 1
            self.form_widget.set_audio_tracks(audio_items)

        self._load_srt_for_current_row()

        self.check_all_fields_validated()
        self.play_movie(film, typ, spur, autoplay)

    def populate_track_list(self, movie_name):
        self.form_widget.track_list.setRowCount(0)
        row_count = 0
        df = self.ctrl.df

        # Hole alle gültigen Track-IDs für diesen Film
        movie_rows = df[df['file_name'] == movie_name]
        valid_track_ids = [str(x) for x in sorted(movie_rows['track_id'].astype(int).tolist())]

        for i, row_idx in enumerate(self.auto_rows):
            row = df.loc[row_idx]
            if row['file_name'] == movie_name:
                self.form_widget.track_list.insertRow(row_count)
                item_spur = QtWidgets.QTableWidgetItem(str(row['track_id']))
                item_spur.setData(QtCore.Qt.UserRole, i)
                item_art = QtWidgets.QTableWidgetItem(str(row['track_type']))
                ctype = str(row.get('subtitle_type', ''))
                if not ctype:
                    ctype = "Audio" if str(
                        row['track_type']).lower() == 'audio' else "SRT"
                item_codec = QtWidgets.QTableWidgetItem(ctype)

                # KI-Vorschläge
                ki_data = self.ctrl.get_ki_data(movie_name, row['track_id'])
                ki_parts = []
                if ki_data.get('lang') and ki_data['lang'] != '-': ki_parts.append(str(ki_data['lang']))
                if ki_data.get('sdh'): ki_parts.append('[SDH]')
                if ki_data.get('forced'): ki_parts.append('[Forced]')
                if ki_data.get('default'): ki_parts.append('[Default]')
                if ki_data.get('name') and ki_data['name'] != '-': ki_parts.append(f'"{ki_data["name"]}"')
                item_ki = QtWidgets.QTableWidgetItem(" ".join(ki_parts))

                # Validierte Einträge
                val_dict = self.ctrl.get_validation_data(movie_name, row['track_id'])
                val_parts = []
                if val_dict.get('lang', False): val_parts.append(str(row.get('language_iso', '')))
                if val_dict.get('sdh', False) and row.get('is_hearing_impaired'): val_parts.append('[SDH]')
                if val_dict.get('forced', False) and row.get('is_forced'): val_parts.append('[Forced]')
                if val_dict.get('default', False) and row.get('is_default'): val_parts.append('[Default]')
                import pandas as pd
                if val_dict.get('name', False) and pd.notna(row.get('track_name')) and row.get('track_name'):
                    val_parts.append(f'"{row["track_name"]}"')
                item_val = QtWidgets.QTableWidgetItem(" ".join(val_parts))

                items = (item_spur, item_art, item_codec, item_ki, item_val)

                if row['is_validated']:
                    for item in items:
                        item.setForeground(QtGui.QColor("#aaaaaa"))
                else:
                    is_audio = str(row['track_type']).lower() == 'audio'
                    if is_audio:
                        all_v = all(val_dict.get(k, False) for k in ['lang', 'default'])
                    else:
                        all_v = all(val_dict.get(k, False)
                                    for k in ['lang', 'sdh', 'forced', 'name', 'default'])
                    if all_v:
                        for item in items:
                            item.setBackground(
                                QtGui.QBrush(QtGui.QColor("#1b5e20")))

                self.form_widget.track_list.setItem(row_count, 0, item_spur)
                self.form_widget.track_list.setItem(row_count, 1, item_art)
                self.form_widget.track_list.setItem(row_count, 2, item_codec)
                self.form_widget.track_list.setItem(row_count, 3, item_ki)
                self.form_widget.track_list.setItem(row_count, 4, item_val)
                
                # Ziel-ID Combobox
                combo = QtWidgets.QComboBox()
                combo.addItems(valid_track_ids)
                target_id = str(row.get('target_track_id', row['track_id']))
                combo.setCurrentText(target_id)
                combo.setStyleSheet("padding: 2px;")
                # Use lambda to bind arguments
                combo.currentTextChanged.connect(lambda text, r=row_idx, t=str(row['track_id']): self.on_target_id_changed(r, t, text))
                self.form_widget.track_list.setCellWidget(row_count, 5, combo)
                
                row_count += 1

    def play_movie(self, film, track_type, track_id, autoplay=False):
        # Prevent playing movies that are currently being analyzed to avoid VLC D3D11 crash
        if hasattr(self.parent, 'analysis_worker') and self.parent.analysis_worker and self.parent.analysis_worker.isRunning():
            for p in self.parent.analysis_worker.file_paths:
                if os.path.basename(p) == film:
                    print(f"[{film}] wird analysiert. VLC Wiedergabe blockiert.")
                    if self.player_widget and self.player_widget.media_player:
                        self.player_widget.media_player.stop()
                        self.player_widget.media_player.set_media(None)
                    return
                    
        if not hasattr(self, '_film_path_cache'):
            self._film_path_cache = {}
            
        if film in self._film_path_cache:
            filepath = self._film_path_cache[film]
        else:
            filepath = os.path.join(DIR_TEST, film)
            if not os.path.exists(filepath):
                found = False
                for d in [DIR_FILME, DIR_SERIEN]:
                    for root, _, files in os.walk(d):
                        if film in files:
                            filepath = os.path.join(root, film)
                            found = True
                            break
                    if found:
                        break
            self._film_path_cache[film] = filepath
            
        if os.path.exists(filepath):
            # Berechne den 1-basierten Index (relative_idx) für VLC!
            df = self.ctrl.df
            movie_rows = df[df['file_name'] == film]
            typ_rows = movie_rows[movie_rows['track_type'].str.lower() == track_type.lower()]
            
            relative_idx = 1
            for _, r in typ_rows.iterrows():
                if int(r['track_id']) == int(track_id):
                    break
                relative_idx += 1
                
            is_new_movie = (filepath != self.player_widget.current_filepath)
            was_playing = self.player_widget.media_player.is_playing() if self.player_widget.media_player else 0
            
            self.player_widget.play_media(
                filepath, track_type.lower(), relative_idx, autoplay)
            
            if autoplay and (is_new_movie or not was_playing):
                seek_time = self._get_smart_seek_time(film, track_type, track_id)
                # Wait 2500ms so VLC has enough time to init D3D11 and set SPU before we jump
                from PyQt5 import QtCore
                QtCore.QTimer.singleShot(2500, lambda: self.player_widget.seek_absolute(seek_time))
                if not is_new_movie and not was_playing:
                    # If it was paused, and we seeked, we should also play so they see the result!
                    QtCore.QTimer.singleShot(2600, lambda: self.player_widget.media_player.play() if self.player_widget.media_player else None)

    def _get_smart_seek_time(self, film, typ, spur):
        times = self._get_all_seek_times(film, typ, spur)
        return times[0] if times else 300000

    def _get_all_seek_times(self, film, typ, spur):
        import os, glob
        from ai_metatagger.config import SUBS_DIR
        
        paths_to_try = []
        if typ.lower() == 'subtitle':
            track_dir = os.path.join(SUBS_DIR, film, f"Spur_{spur}")
            if not os.path.exists(track_dir):
                film_no_ext = os.path.splitext(film)[0]
                fallback_dir = os.path.join(SUBS_DIR, film_no_ext, f"Spur_{spur}")
                if os.path.exists(fallback_dir):
                    track_dir = fallback_dir
                    
            search_srt = os.path.join(glob.escape(track_dir), "*.srt")
            search_txt = os.path.join(glob.escape(track_dir), "*_OCR.txt")
            paths_to_try = glob.glob(search_srt) + glob.glob(search_txt)
        elif typ.lower() == 'audio':
            film_no_ext = os.path.splitext(film)[0]
            for f_name in [film, film_no_ext]:
                search_dir = os.path.join(glob.escape(SUBS_DIR), glob.escape(f_name), "Spur_*")
                paths_to_try.extend(glob.glob(os.path.join(search_dir, "*.srt")))
                paths_to_try.extend(glob.glob(os.path.join(search_dir, "*_OCR.txt")))

        all_times = []
        for path in paths_to_try:
            if os.path.exists(path):
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        lines = f.readlines()
                        for line in lines:
                            if '-->' in line:
                                start_str = line.split('-->')[0].strip()
                                h, m, s_ms = start_str.split(':')
                                s, ms = s_ms.split(',')
                                total_ms = int(h)*3600000 + int(m)*60000 + int(s)*1000 + int(ms)
                                all_times.append(max(0, total_ms - 2000))
                            elif line.startswith('[') and ']' in line:
                                import re
                                m_match = re.match(r'^\[(\d+):(\d+):(\d+)\]', line.strip())
                                if m_match:
                                    h, m, s = m_match.groups()
                                    total_ms = int(h)*3600000 + int(m)*60000 + int(s)*1000
                                    all_times.append(max(0, total_ms - 2000))
                    if all_times:
                        return all_times
                except Exception:
                    pass
        return all_times

    def _cleanup_vlc_and_file(self, film):
        player_ref = None
        if self.current_film == film:
            player_ref = self.player_widget.media_player
            self.current_film = None
            self.player_widget.clear_media()

        def _do_cleanup(vid_path, subs_path):
            import shutil
            max_retries = 3
            
            # 1. Videodatei löschen
            for attempt in range(max_retries):
                if not os.path.exists(vid_path):
                    break
                try:
                    time.sleep(0.5 + (attempt * 1.0))
                    os.remove(vid_path)
                    break
                except OSError as e:
                    print(f"Cleanup retry {attempt+1}/{max_retries} failed for video {vid_path}: {e}")
                    
            # 2. Kompletten extracted_subs Ordner dieses Films löschen
            for attempt in range(max_retries):
                if not os.path.exists(subs_path):
                    break
                try:
                    time.sleep(0.5 + (attempt * 1.0))
                    shutil.rmtree(subs_path)
                    break
                except OSError as e:
                    print(f"Cleanup retry {attempt+1}/{max_retries} failed for folder {subs_path}: {e}")

        # Pfade zusammenbauen
        filepath = os.path.join(DIR_TEST, film)
        subs_folder = os.path.join(SUBS_DIR, film)
        
        # Hintergrund-Thread starten, damit die Benutzeroberfläche nicht einfriert
        threading.Thread(target=_do_cleanup, args=(filepath, subs_folder), daemon=True).start()
        
        return player_ref is not None

    def validate_field(self, field):
        film = self.current_row['file_name']
        trk_id = str(self.current_row['track_id'])

        # Speichert Werte sicher ab (inkl. Dropdowns)
        self._save_current_ui_to_memory()

        val_dict = self.ctrl.get_validation_data(film, trk_id)
        val_dict[field] = not val_dict.get(field, False)

        if film not in self.ctrl.state_data:
            self.ctrl.state_data[film] = {}
        if trk_id not in self.ctrl.state_data[film]:
            self.ctrl.state_data[film][trk_id] = {'Validated': {}, 'KI': {}}
        self.ctrl.state_data[film][trk_id]['Validated'] = val_dict

        # --- Auch Dropdown-Daten in der SQLite-Datenbank sichern ---
        form_data = self.form_widget.get_form_data()
        from ai_metatagger.utils.state_manager import DB_LOCK, init_db
        with DB_LOCK:
            conn = init_db()
            cursor = conn.cursor()
            val_json = json.dumps(val_dict)
            cursor.execute(
                """UPDATE media_tracks 
                   SET validated_fields = ?, language_iso = ?, is_hearing_impaired = ?, is_forced = ?, is_default = ?, track_name = ?
                   WHERE file_name = ? AND CAST(track_id AS TEXT) = ?""",
                (val_json, form_data['lang'], form_data['sdh'], form_data['forced'], form_data['default'], form_data['title'], film, trk_id)
            )
            conn.commit()
            conn.close()

        self.check_all_fields_validated()

    def check_all_fields_validated(self):
        film = self.current_row['file_name']
        trk_id = str(self.current_row['track_id'])
        val_dict = self.ctrl.get_validation_data(film, trk_id)

        is_audio = str(self.current_row['track_type']).lower() == 'audio'
        if is_audio:
            all_valid = all(val_dict.get(k, False) for k in ['lang', 'default'])
        else:
            all_valid = all(val_dict.get(k, False)
                            for k in ['lang', 'sdh', 'forced', 'name', 'default'])

        self.form_widget.update_validation_ui(val_dict, all_valid)
        return all_valid, val_dict

    def save_and_next(self):
        # Aktuelle Ansicht noch schnell speichern
        self._save_current_ui_to_memory()
        
        film = self.current_row['file_name']
        df_film = self.ctrl.df[(self.ctrl.df['file_name'] == film) & (~self.ctrl.df['is_validated'])]
        
        tracks_to_finalize = []
        all_valid = True
        
        # Prüfe ALLE Spuren dieses Films, ob JEDES Häkchen gesetzt ist
        for _, row in df_film.iterrows():
            t_id = str(row['track_id'])
            val_dict = self.ctrl.get_validation_data(film, t_id)
            is_audio = str(row['track_type']).lower() == 'audio'
            
            if is_audio:
                is_track_valid = all(val_dict.get(k, False) for k in ['lang', 'default'])
            else:
                is_track_valid = all(val_dict.get(k, False) for k in ['lang', 'sdh', 'forced', 'name', 'default'])
                
            if not is_track_valid:
                all_valid = False
                break
            
            tracks_to_finalize.append((t_id, row, val_dict))
            
        # Wenn auch nur ein Häkchen im gesamten Film fehlt: Abbruch!
        if not all_valid:
            QtWidgets.QMessageBox.warning(
                self, "Film nicht vollständig geprüft", 
                f"Es wurden noch nicht alle Spuren für diesen Film validiert.\n\nBitte wähle jede Spur in der Liste an und setze alle grünen Häkchen, bevor du den Film abschließt.")
            return

        # Speichere ALLE vollständig geprüften Spuren ab
        for t_id, row, val_dict in tracks_to_finalize:
            self.ctrl.save_validation(film, t_id,
                                      row['language_iso'],
                                      row['is_hearing_impaired'],
                                      row['is_forced'],
                                      row['is_default'],
                                      row['track_name'],
                                      "",  # notes
                                      val_dict)

        self.ctrl.refresh_data()
        df = self.ctrl.df
        remaining = df[(df['file_name'] == film) & (~df['is_validated'])]

        player_ref = None
        if remaining.empty:
            player_ref = self._cleanup_vlc_and_file(film)

        # Da der ganze Film erledigt ist, springen wir sicher auf den ersten Index des nächsten Films
        self.current_idx = 0

        if player_ref:
            QtCore.QTimer.singleShot(600, self.check_for_new_data)
        else:
            self.check_for_new_data()

    def remove_movie(self, film):
        reply = QtWidgets.QMessageBox.question(self, 'Film entfernen', f'Willst du "{film}" wirklich ignorieren?',
                                               QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No)
        if reply == QtWidgets.QMessageBox.Yes:
            had_player = self._cleanup_vlc_and_file(film)
            self.ctrl.remove_movie(film)

            if had_player:
                self.current_idx = 0
                QtCore.QTimer.singleShot(600, self.check_for_new_data)
            else:
                self.check_for_new_data()

    def update_ui(self):
        length = self.player_widget.get_length()
        time_ms = self.player_widget.get_time()
        if length > 0 and time_ms >= 0:
            if not self.slider.isSliderDown():
                self.slider.setMaximum(length)
                self.slider.setValue(time_ms)
            t, l = time_ms // 1000, length // 1000
            self.lbl_time.setText(
                f"{t//60:02d}:{t % 60:02d} / {l//60:02d}:{l % 60:02d}")

    def _load_srt_for_current_row(self):
        if self.current_row is None:
            return
            
        film = self.current_row['file_name']
        typ = self.current_row['track_type']
        spur = self.current_row['track_id']
        
        import os, glob
        from ai_metatagger.config import SUBS_DIR
        
        target_spur = spur
        if typ.lower() == 'audio':
            # find best subtitle track
            audio_lang = self.current_row.get('language_iso', 'ger')
            if not audio_lang or audio_lang == '-': audio_lang = 'ger'
            
            df = self.ctrl.df
            subs = df[(df['file_name'] == film) & (df['track_type'].str.lower() != 'audio') & (df['track_type'] != 'muxing')]
            
            best_spur = None
            if not subs.empty:
                # 1. Match audio lang
                match = subs[subs['language_iso'] == audio_lang]
                if not match.empty:
                    best_spur = match.iloc[0]['track_id']
                else:
                    # 2. Match 'ger'
                    match_ger = subs[subs['language_iso'] == 'ger']
                    if not match_ger.empty:
                        best_spur = match_ger.iloc[0]['track_id']
                    else:
                        # 3. Any
                        best_spur = subs.iloc[0]['track_id']
                        
            if best_spur is not None:
                target_spur = best_spur
            else:
                self.form_widget.toggle_srt_view(None)
                return
                
        # Now load text for target_spur
        track_dir = os.path.join(SUBS_DIR, film, f"Spur_{target_spur}")
        if not os.path.exists(track_dir):
            film_no_ext = os.path.splitext(film)[0]
            fallback_dir = os.path.join(SUBS_DIR, film_no_ext, f"Spur_{target_spur}")
            if os.path.exists(fallback_dir):
                track_dir = fallback_dir

        search_srt = os.path.join(glob.escape(track_dir), "*.srt")
        search_txt = os.path.join(glob.escape(track_dir), "*_OCR.txt")
        files = glob.glob(search_srt) + glob.glob(search_txt)
        
        if files:
            files.sort(key=lambda x: ('_synced' not in x, '_OCR' not in x))
            target_file = files[0]
            try:
                with open(target_file, 'r', encoding='utf-8') as f:
                    self.form_widget.toggle_srt_view(f.read())
            except Exception:
                self.form_widget.toggle_srt_view(None)
        else:
            self.form_widget.toggle_srt_view(None)

    def open_pgs(self):
        if not self.current_row is None:
            film = self.current_row['file_name']
            idx = self.current_row['track_id']
            
            track_dir = os.path.join(SUBS_DIR, film, f"Spur_{idx}")
            if not os.path.exists(track_dir):
                film_no_ext = os.path.splitext(film)[0]
                fallback_dir = os.path.join(SUBS_DIR, film_no_ext, f"Spur_{idx}")
                if os.path.exists(fallback_dir):
                    track_dir = fallback_dir

            # Suchen wir nach .srt UND .txt dateien in diesem Ordner
            search_srt = os.path.join(glob.escape(track_dir), "*.srt")
            search_txt = os.path.join(glob.escape(track_dir), "*_OCR.txt")
            
            files = glob.glob(search_srt) + glob.glob(search_txt)
            
            if files:
                # Priorität: 1. _synced.srt -> 2. normale .srt -> 3. OCR.txt
                files.sort(key=lambda x: ('_synced' not in x, '_OCR' not in x))
                target_file = files[0]
                with open(target_file, 'r', encoding='utf-8') as f:
                    self.form_widget.toggle_srt_view(f.read())
            else:
                self.form_widget.toggle_srt_view()
                QtWidgets.QMessageBox.warning(
                    self, "Nicht gefunden", f"Es wurde weder eine SRT noch ein OCR Text gefunden in:\n{track_dir}")

    def open_pgs(self):
        if not self.current_row is None:
            if self.form_widget.pgs_image_list.isVisible():
                self.form_widget.toggle_pgs_view()
                return
                
            film = self.current_row['file_name']
            idx = self.current_row['track_id']
            
            track_pgs_dir = os.path.join(SUBS_DIR, film, f"Spur_{idx}")
            
            if not os.path.exists(track_pgs_dir):
                film_no_ext = os.path.splitext(film)[0]
                fallback_dir = os.path.join(SUBS_DIR, film_no_ext, f"Spur_{idx}")
                if os.path.exists(fallback_dir):
                    track_pgs_dir = fallback_dir
            
            search = os.path.join(glob.escape(track_pgs_dir), "*.png")
            files = glob.glob(search)
            
            if files:
                files.sort()
                self.form_widget.toggle_pgs_view(files)
            else:
                self.form_widget.toggle_pgs_view()
                QtWidgets.QMessageBox.warning(
                    self, "Nicht gefunden", f"Keine Bilder gefunden in:\n{track_pgs_dir}")

    def start_new_analysis(self, paths):
        if paths:
            # STOP VLC playback before analysis to prevent C++ crashes when mkvpropedit modifies the file
            if self.player_widget and self.player_widget.media_player:
                self.player_widget.media_player.stop()
                self.player_widget.media_player.set_media(None)
            self.parent.start_analysis_and_validation(paths)

    def calculate_accuracy(self):
        return self.ctrl.calculate_accuracy()
