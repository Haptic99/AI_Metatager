from PyQt5 import QtWidgets, QtCore, QtGui
import pandas as pd
import os

class ValidatorFormWidget(QtWidgets.QWidget):
    track_selected = QtCore.pyqtSignal(int)
    seek_requested = QtCore.pyqtSignal(int)
    field_validated = QtCore.pyqtSignal(str)
    save_requested = QtCore.pyqtSignal()
    test_lang_requested = QtCore.pyqtSignal()
    test_lang_next_requested = QtCore.pyqtSignal()
    test_lang_prev_requested = QtCore.pyqtSignal()
    test_sdh_requested = QtCore.pyqtSignal()
    test_sdh_next_requested = QtCore.pyqtSignal()
    test_sdh_prev_requested = QtCore.pyqtSignal()
    test_forced_requested = QtCore.pyqtSignal()
    test_forced_next_requested = QtCore.pyqtSignal()
    test_forced_prev_requested = QtCore.pyqtSignal()
    show_srt_requested = QtCore.pyqtSignal()
    show_pgs_requested = QtCore.pyqtSignal()
    pgs_image_double_clicked = QtCore.pyqtSignal(str)
    audio_track_changed = QtCore.pyqtSignal(int)  # emits VLC relative audio index (1-based)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMaximumWidth(850)
        
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        
        self.lbl_header = QtWidgets.QLabel("🎬 -")
        self.lbl_header.setFont(QtGui.QFont("Segoe UI", 12, QtGui.QFont.Bold))
        self.lbl_header.setStyleSheet("color: #4caf50;")
        self.lbl_header.setWordWrap(True)
        layout.addWidget(self.lbl_header)
        
        self.track_list = QtWidgets.QTableWidget()
        self.track_list.setColumnCount(6)
        self.track_list.setHorizontalHeaderLabels(["Spur", "Art", "Codec", "KI", "Validiert", "Ziel-ID"])
        self.track_list.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.track_list.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.track_list.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.track_list.verticalHeader().setVisible(False)
        
        # Responsive scaling for high-res screens (1440p)
        header = self.track_list.horizontalHeader()
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents) # Spur
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeToContents) # Art
        header.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeToContents) # Codec
        header.setSectionResizeMode(3, QtWidgets.QHeaderView.Stretch)          # KI
        header.setSectionResizeMode(4, QtWidgets.QHeaderView.Stretch)          # Validiert
        header.setSectionResizeMode(5, QtWidgets.QHeaderView.ResizeToContents) # Ziel-ID
        
        self.track_list.setStyleSheet("QTableWidget::item { padding: 2px; }")
        self.track_list.verticalHeader().setDefaultSectionSize(24)
        self.track_list.itemClicked.connect(self._on_track_clicked)
        layout.addWidget(self.track_list, stretch=1)
        
        self.form_grid = QtWidgets.QGridLayout()
        self.form_grid.setVerticalSpacing(8)
        self.form_grid.setHorizontalSpacing(15)
        self.form_grid.setColumnStretch(0, 1)
        self.form_grid.setColumnStretch(1, 2)
        self.form_grid.setColumnStretch(2, 3)
        self.form_grid.setColumnStretch(3, 1)
        
        self.form_grid.addWidget(QtWidgets.QLabel("<b>Eigenschaft</b>"), 0, 0)
        self.form_grid.addWidget(QtWidgets.QLabel("<b>KI-Vorschlag</b>"), 0, 1)
        self.form_grid.addWidget(QtWidgets.QLabel("<b>Dein Wert</b>"), 0, 2)
        self.form_grid.addWidget(QtWidgets.QLabel("<b>Geprüft</b>"), 0, 3)
        
        # 1. Sprache
        self.lbl_lang_title = QtWidgets.QLabel("Sprache:")
        self.form_grid.addWidget(self.lbl_lang_title, 1, 0)
        self.lbl_ki_lang = QtWidgets.QLabel("-")
        self.form_grid.addWidget(self.lbl_ki_lang, 1, 1)
        self.cmb_lang = QtWidgets.QComboBox()
        self.cmb_lang.addItems(["ger", "eng", "fre", "spa", "zh-hans", "zh-hant", "ko", "jpn"])
        self.cmb_lang.setEditable(True)
        self.form_grid.addWidget(self.cmb_lang, 1, 2)
        self.btn_valid_lang = QtWidgets.QPushButton("✔")
        self.btn_valid_lang.clicked.connect(lambda: self.field_validated.emit('lang'))
        self.form_grid.addWidget(self.btn_valid_lang, 1, 3)
        
        # 2. SDH
        self.lbl_sdh_title = QtWidgets.QLabel("SDH:")
        self.form_grid.addWidget(self.lbl_sdh_title, 2, 0)
        self.lbl_ki_sdh = QtWidgets.QLabel("-")
        self.form_grid.addWidget(self.lbl_ki_sdh, 2, 1)
        self.cmb_sdh = QtWidgets.QComboBox()
        self.cmb_sdh.addItems(["Nein", "Ja"])
        self.form_grid.addWidget(self.cmb_sdh, 2, 2)
        self.btn_valid_sdh = QtWidgets.QPushButton("✔")
        self.btn_valid_sdh.clicked.connect(lambda: self.field_validated.emit('sdh'))
        self.form_grid.addWidget(self.btn_valid_sdh, 2, 3)
        
        # 3. Forced
        self.lbl_forced_title = QtWidgets.QLabel("Forced:")
        self.form_grid.addWidget(self.lbl_forced_title, 3, 0)
        self.lbl_ki_forced = QtWidgets.QLabel("-")
        self.form_grid.addWidget(self.lbl_ki_forced, 3, 1)
        self.cmb_forced = QtWidgets.QComboBox()
        self.cmb_forced.addItems(["Nein", "Ja"])
        self.form_grid.addWidget(self.cmb_forced, 3, 2)
        self.btn_valid_forced = QtWidgets.QPushButton("✔")
        self.btn_valid_forced.clicked.connect(lambda: self.field_validated.emit('forced'))
        self.form_grid.addWidget(self.btn_valid_forced, 3, 3)
        
        # 4. Standard
        self.lbl_default_title = QtWidgets.QLabel("Standard:")
        self.form_grid.addWidget(self.lbl_default_title, 4, 0)
        self.lbl_ki_default = QtWidgets.QLabel("-")
        self.form_grid.addWidget(self.lbl_ki_default, 4, 1)
        self.cmb_default = QtWidgets.QComboBox()
        self.cmb_default.addItems(["Nein", "Ja"])
        self.form_grid.addWidget(self.cmb_default, 4, 2)
        self.btn_valid_default = QtWidgets.QPushButton("✔")
        self.btn_valid_default.clicked.connect(lambda: self.field_validated.emit('default'))
        self.form_grid.addWidget(self.btn_valid_default, 4, 3)

        # 5. Name
        self.lbl_name_title = QtWidgets.QLabel("Spezial Name:")
        self.form_grid.addWidget(self.lbl_name_title, 5, 0)
        self.lbl_ki_name = QtWidgets.QLabel("-")
        self.form_grid.addWidget(self.lbl_ki_name, 5, 1)
        self.txt_titel = QtWidgets.QLineEdit()
        self.txt_titel.setPlaceholderText("z.B. Director's Commentary")
        self.form_grid.addWidget(self.txt_titel, 5, 2)
        self.btn_valid_name = QtWidgets.QPushButton("✔")
        self.btn_valid_name.clicked.connect(lambda: self.field_validated.emit('name'))
        self.form_grid.addWidget(self.btn_valid_name, 5, 3)
        
        # Wrap grid in a container with a fixed height so it NEVER jumps when rows are hidden
        self.grid_container = QtWidgets.QFrame()
        self.grid_container.setMinimumHeight(180)
        self.grid_container.setMaximumHeight(180)
        self.grid_container.setLayout(self.form_grid)
        layout.addWidget(self.grid_container)
        
        # --- Textanalyse + Audio-Auswahl ---
        conv_header = QtWidgets.QHBoxLayout()
        self.lbl_conv = QtWidgets.QLabel("Textanalyse:")
        self.lbl_conv.setFont(QtGui.QFont("Segoe UI", 10, QtGui.QFont.Bold))
        conv_header.addWidget(self.lbl_conv)
        
        conv_header.addStretch()
        
        self.lbl_audio_select = QtWidgets.QLabel("🔊 Audio:")
        self.lbl_audio_select.setVisible(False)
        sp_lbl = self.lbl_audio_select.sizePolicy()
        sp_lbl.setRetainSizeWhenHidden(True)
        self.lbl_audio_select.setSizePolicy(sp_lbl)
        conv_header.addWidget(self.lbl_audio_select)
        
        self.cmb_audio_track = QtWidgets.QComboBox()
        self.cmb_audio_track.setMinimumWidth(150)
        self.cmb_audio_track.setVisible(False)
        sp_cmb = self.cmb_audio_track.sizePolicy()
        sp_cmb.setRetainSizeWhenHidden(True)
        self.cmb_audio_track.setSizePolicy(sp_cmb)
        self.cmb_audio_track.currentIndexChanged.connect(self._on_audio_track_changed)
        conv_header.addWidget(self.cmb_audio_track)
        
        layout.addLayout(conv_header)
        
        self.srt_table = QtWidgets.QTableWidget()
        self.srt_table.setColumnCount(3)
        self.srt_table.setHorizontalHeaderLabels(["Zeit", "Text", "Jump"])
        self.srt_table.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)
        self.srt_table.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.Stretch)
        self.srt_table.horizontalHeader().setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeToContents)
        self.srt_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.srt_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.srt_table.verticalHeader().setVisible(False)
        self.srt_table.setStyleSheet("background-color: #1e1e1e; color: #ddd;")
        layout.addWidget(self.srt_table, stretch=2)
        
        self.pgs_image_list = QtWidgets.QListWidget()
        self.pgs_image_list.setVisible(False)
        layout.addWidget(self.pgs_image_list, stretch=2)
        
        self.btn_save = QtWidgets.QPushButton("✔ Film abschließen")
        self.btn_save.setStyleSheet("background-color: #2e7d32; font-size: 14px; padding: 12px;")
        self.btn_save.clicked.connect(self.save_requested.emit)
        layout.addWidget(self.btn_save)
        
    def _on_track_clicked(self, item):
        row = item.row()
        first_item = self.track_list.item(row, 0)
        self.track_selected.emit(first_item.data(QtCore.Qt.UserRole))
        
    def get_form_data(self):
        return {
            'lang': self.cmb_lang.currentText(),
            'sdh': self.cmb_sdh.currentText() == "Ja",
            'forced': self.cmb_forced.currentText() == "Ja",
            'default': self.cmb_default.currentText() == "Ja",  # <-- NEU
            'title': self.txt_titel.text()
        }
        
    def set_form_data(self, df_row):
        is_audio = str(df_row['track_type']).lower() == 'audio'
        
        # Hide unneeded fields for audio (row indices 2=SDH, 3=Forced)
        # Note: Name is row 5, Standard is row 4. Wait, the layout shifted? 
        # No, the grid still uses the same row indices: 1=Lang, 2=SDH, 3=Forced, 4=Default, 5=Name.
        # But we don't hide Name for Audio! We just hide SDH and Forced.
        for row_idx in [2, 3]: 
            for col in range(5):
                item = self.form_grid.itemAtPosition(row_idx, col)
                if item and item.widget():
                    item.widget().setVisible(not is_audio)
                    
        self.lbl_conv.setVisible(True)
        self.srt_table.setVisible(True)
        self.pgs_image_list.setVisible(False)
        
        # Show audio track selector only for subtitle tracks
        self.lbl_audio_select.setVisible(not is_audio)
        self.cmb_audio_track.setVisible(not is_audio)
        
        self.cmb_lang.setCurrentText(str(df_row['language_iso']))
        self.cmb_sdh.setCurrentText("Ja" if bool(df_row['is_hearing_impaired']) else "Nein")
        self.cmb_forced.setCurrentText("Ja" if bool(df_row['is_forced']) else "Nein")
        self.cmb_default.setCurrentText("Ja" if bool(df_row.get('is_default', False)) else "Nein")
        if 'track_name' in df_row and pd.notna(df_row['track_name']):
            self.txt_titel.setText(str(df_row['track_name']))
        else:
            self.txt_titel.setText("")
            
    def set_ki_data(self, ki_data):
        self.lbl_ki_lang.setText(str(ki_data.get('lang', '-')))
        self.lbl_ki_sdh.setText("Ja" if ki_data.get('sdh') else "Nein")
        self.lbl_ki_forced.setText("Ja" if ki_data.get('forced') else "Nein")
        self.lbl_ki_default.setText("Ja" if ki_data.get('default') else "Nein")
        name_val = ki_data.get('name', '')
        self.lbl_ki_name.setText(str(name_val) if name_val else "-")
    
    def set_audio_tracks(self, audio_tracks):
        """Populate the audio dropdown. audio_tracks = list of (relative_idx, label) tuples."""
        # Remember current selection if any
        current_rel_idx = None
        if self.cmb_audio_track.currentIndex() >= 0:
            current_rel_idx = self.cmb_audio_track.itemData(self.cmb_audio_track.currentIndex())

        self.cmb_audio_track.blockSignals(True)
        self.cmb_audio_track.clear()
        
        target_index = 0
        for i, (rel_idx, label) in enumerate(audio_tracks):
            self.cmb_audio_track.addItem(label, rel_idx)
            if current_rel_idx is not None and rel_idx == current_rel_idx:
                target_index = i
                
        if audio_tracks:
            self.cmb_audio_track.setCurrentIndex(target_index)
            
        self.cmb_audio_track.blockSignals(False)
    
    def _on_audio_track_changed(self, index):
        if index >= 0:
            rel_idx = self.cmb_audio_track.itemData(index)
            if rel_idx is not None:
                self.audio_track_changed.emit(rel_idx)
        
    def update_validation_ui(self, val_data, is_all_valid):
        # Mappe die Felder auf ihre jeweiligen Eingabe-Widgets
        widget_map = {
            'lang': self.cmb_lang,
            'sdh': self.cmb_sdh,
            'forced': self.cmb_forced,
            'default': self.cmb_default,
            'name': self.txt_titel
        }
        
        for field in ['lang', 'sdh', 'forced', 'default', 'name']:
            btn = getattr(self, f"btn_valid_{field}")
            input_widget = widget_map.get(field)
            
            if val_data.get(field):
                btn.setStyleSheet("background-color: #4caf50; color: white;")
                if input_widget:
                    input_widget.setEnabled(False)  # Feld ausgrauen/sperren
            else:
                btn.setStyleSheet("")
                if input_widget:
                    input_widget.setEnabled(True)   # Feld wieder freigeben
                
        if self.track_list.currentRow() >= 0:
            row = self.track_list.currentRow()
            
            # Update Validiert column text (Column 4)
            val_parts = []
            if val_data.get('lang', False): val_parts.append(self.cmb_lang.currentText())
            if val_data.get('sdh', False) and self.cmb_sdh.currentText() == "Ja": val_parts.append('[SDH]')
            if val_data.get('forced', False) and self.cmb_forced.currentText() == "Ja": val_parts.append('[Forced]')
            if val_data.get('default', False) and self.cmb_default.currentText() == "Ja": val_parts.append('[Default]')
            if val_data.get('name', False) and self.txt_titel.text().strip(): val_parts.append(f'"{self.txt_titel.text().strip()}"')
            val_text = " ".join(val_parts)
            
            item_val = self.track_list.item(row, 4)
            if item_val:
                item_val.setText(val_text)
            
            for col in range(5):
                item = self.track_list.item(row, col)
                if item:
                    if is_all_valid:
                        item.setBackground(QtGui.QBrush(QtGui.QColor("#1b5e20")))
                    else:
                        item.setBackground(QtGui.QBrush(QtGui.QColor(0,0,0,0)))
                        
    def clear_ki_data(self):
        self.set_ki_data({})
        self.update_validation_ui({}, False)
        
    def toggle_srt_view(self, text_content=None):
        self.srt_table.setRowCount(0)
        self._srt_entries = []
        self._srt_loaded_count = 0
        
        if not text_content:
            return
        
        # Parse all entries into a lightweight list first (no widgets yet)
        import re
        blocks = text_content.strip().split('\n\n')
        for block in blocks:
            lines = block.split('\n')
            if len(lines) >= 3:
                time_line = lines[1]
                text_lines = " ".join(lines[2:])
                
                m = re.search(r"(\d{2}:\d{2}:\d{2}),(\d{3})", time_line)
                if m:
                    ts_str = m.group(1)
                    h, m_m, s = ts_str.split(':')
                    ms = m.group(2)
                    total_ms = int(h)*3600000 + int(m_m)*60000 + int(s)*1000 + int(ms)
                    target_ms = max(0, total_ms - 500)
                    self._srt_entries.append((ts_str, text_lines, target_ms))
        
        # Render only the first batch
        self._load_srt_batch(80)
        
        # Connect scroll event for lazy loading
        scrollbar = self.srt_table.verticalScrollBar()
        try: scrollbar.valueChanged.disconnect(self._on_srt_scroll)
        except TypeError: pass
        scrollbar.valueChanged.connect(self._on_srt_scroll)
    
    def _on_srt_scroll(self, value):
        scrollbar = self.srt_table.verticalScrollBar()
        if value >= scrollbar.maximum() - 20:
            self._load_srt_batch(80)
    
    def _load_srt_batch(self, count):
        if self._srt_loaded_count >= len(self._srt_entries):
            return
        
        end = min(self._srt_loaded_count + count, len(self._srt_entries))
        
        self.srt_table.setUpdatesEnabled(False)
        for i in range(self._srt_loaded_count, end):
            ts_str, text_lines, target_ms = self._srt_entries[i]
            row = self.srt_table.rowCount()
            self.srt_table.insertRow(row)
            self.srt_table.setItem(row, 0, QtWidgets.QTableWidgetItem(ts_str))
            
            txt_item = QtWidgets.QTableWidgetItem(text_lines)
            txt_item.setToolTip(text_lines)
            self.srt_table.setItem(row, 1, txt_item)
            
            btn = QtWidgets.QPushButton("▶")
            btn.setFixedWidth(40)
            btn.setStyleSheet("background-color: #2196F3; color: white; border-radius: 2px;")
            btn.clicked.connect(lambda checked, t=target_ms: self.seek_requested.emit(t))
            self.srt_table.setCellWidget(row, 2, btn)
        
        self._srt_loaded_count = end
        self.srt_table.setUpdatesEnabled(True)
        self.srt_table.resizeRowsToContents()

    def _on_pgs_item_double_clicked(self, item):
        filepath = item.data(QtCore.Qt.UserRole)
        if filepath:
            self.pgs_image_double_clicked.emit(filepath)

    def toggle_pgs_view(self, image_paths=None):
        if self.pgs_image_list.isVisible() and image_paths is None:
            self.pgs_image_list.setVisible(False)
            self.btn_conv_pgs.setText("PGS Bilder ansehen")
        elif image_paths:
            self.srt_table.setVisible(False)
            self.btn_conv_srt.setText("SRT ansehen")
            
            self.pgs_image_list.clear()
            for path in image_paths:
                icon = QtGui.QIcon(path)
                item = QtWidgets.QListWidgetItem(icon, os.path.basename(path))
                item.setData(QtCore.Qt.UserRole, path)
                self.pgs_image_list.addItem(item)
                
            self.pgs_image_list.setVisible(True)
            self.btn_conv_pgs.setText("PGS Bilder verbergen")
