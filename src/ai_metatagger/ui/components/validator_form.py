from PyQt5 import QtWidgets, QtCore, QtGui
import pandas as pd

class ValidatorFormWidget(QtWidgets.QWidget):
    track_selected = QtCore.pyqtSignal(int)
    field_validated = QtCore.pyqtSignal(str)
    save_requested = QtCore.pyqtSignal()
    test_lang_requested = QtCore.pyqtSignal()
    test_sdh_requested = QtCore.pyqtSignal()
    test_forced_requested = QtCore.pyqtSignal()
    show_srt_requested = QtCore.pyqtSignal()
    show_pgs_requested = QtCore.pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        lbl_title = QtWidgets.QLabel("Feld-für-Feld Validierung")
        lbl_title.setFont(QtGui.QFont("Segoe UI", 16, QtGui.QFont.Bold))
        layout.addWidget(lbl_title)
        
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
        self.track_list.itemClicked.connect(self._on_track_clicked)
        layout.addWidget(self.track_list)
        
        self.form_grid = QtWidgets.QGridLayout()
        self.form_grid.setSpacing(20)
        self.form_grid.setColumnStretch(0, 1)
        self.form_grid.setColumnStretch(1, 2)
        self.form_grid.setColumnStretch(2, 3)
        self.form_grid.setColumnStretch(3, 1)
        self.form_grid.setColumnStretch(4, 1)
        
        self.form_grid.addWidget(QtWidgets.QLabel("<b>Eigenschaft</b>"), 0, 0)
        self.form_grid.addWidget(QtWidgets.QLabel("<b>KI-Vorschlag</b>"), 0, 1)
        self.form_grid.addWidget(QtWidgets.QLabel("<b>Dein Wert</b>"), 0, 2)
        self.form_grid.addWidget(QtWidgets.QLabel("<b>Testen</b>"), 0, 3)
        self.form_grid.addWidget(QtWidgets.QLabel("<b>Geprüft</b>"), 0, 4)
        
        # 1. Sprache
        self.lbl_lang_title = QtWidgets.QLabel("Sprache:")
        self.form_grid.addWidget(self.lbl_lang_title, 1, 0)
        self.lbl_ki_lang = QtWidgets.QLabel("-")
        self.form_grid.addWidget(self.lbl_ki_lang, 1, 1)
        self.cmb_lang = QtWidgets.QComboBox()
        self.cmb_lang.addItems(["de", "eng", "fre", "spa", "ita", "chi", "ko", "jpn", "und"])
        self.cmb_lang.setEditable(True)
        self.form_grid.addWidget(self.cmb_lang, 1, 2)
        self.btn_test_lang = QtWidgets.QPushButton("▶ Text")
        self.btn_test_lang.setStyleSheet('background-color: #555555; color: white;')
        self.btn_test_lang.clicked.connect(self.test_lang_requested.emit)
        self.form_grid.addWidget(self.btn_test_lang, 1, 3)
        self.btn_valid_lang = QtWidgets.QPushButton("✔")
        self.btn_valid_lang.clicked.connect(lambda: self.field_validated.emit('lang'))
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
        self.btn_test_sdh.setStyleSheet('background-color: #555555; color: white;')
        self.btn_test_sdh.clicked.connect(self.test_sdh_requested.emit)
        self.form_grid.addWidget(self.btn_test_sdh, 2, 3)
        self.btn_valid_sdh = QtWidgets.QPushButton("✔")
        self.btn_valid_sdh.clicked.connect(lambda: self.field_validated.emit('sdh'))
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
        self.btn_test_forced.setStyleSheet('background-color: #555555; color: white;')
        self.btn_test_forced.clicked.connect(self.test_forced_requested.emit)
        self.form_grid.addWidget(self.btn_test_forced, 3, 3)
        self.btn_valid_forced = QtWidgets.QPushButton("✔")
        self.btn_valid_forced.clicked.connect(lambda: self.field_validated.emit('forced'))
        self.form_grid.addWidget(self.btn_valid_forced, 3, 4)
        
        
        # 4. Standard
        self.lbl_default_title = QtWidgets.QLabel("Standard:")
        self.form_grid.addWidget(self.lbl_default_title, 4, 0)
        self.lbl_ki_default = QtWidgets.QLabel("-")
        self.form_grid.addWidget(self.lbl_ki_default, 4, 1)
        self.cmb_default = QtWidgets.QComboBox()
        self.cmb_default.addItems(["Nein", "Ja"])
        self.form_grid.addWidget(self.cmb_default, 4, 2)
        
        self.btn_valid_default = QtWidgets.QPushButton("✓")
        self.btn_valid_default.clicked.connect(lambda: self.field_validated.emit('default'))
        self.form_grid.addWidget(self.btn_valid_default, 4, 4)

        # 4. Name
        self.lbl_name_title = QtWidgets.QLabel("Spezial Name:")
        self.form_grid.addWidget(self.lbl_name_title, 5, 0)
        self.lbl_ki_name = QtWidgets.QLabel("-")
        self.form_grid.addWidget(self.lbl_ki_name, 5, 1)
        self.txt_titel = QtWidgets.QLineEdit()
        self.txt_titel.setPlaceholderText("z.B. Director's Commentary")
        self.form_grid.addWidget(self.txt_titel, 4, 2)
        
        # Empty placeholder for layout alignment
        self.form_grid.addWidget(QtWidgets.QLabel(""), 4, 3) 
        
        self.btn_valid_name = QtWidgets.QPushButton("✔")
        self.btn_valid_name.clicked.connect(lambda: self.field_validated.emit('name'))
        self.form_grid.addWidget(self.btn_valid_name, 5, 4)
        
        layout.addLayout(self.form_grid)
        
        # Subtitle Tools
        conv_layout = QtWidgets.QHBoxLayout()
        self.btn_conv_srt = QtWidgets.QPushButton("SRT ansehen")
        self.btn_conv_pgs = QtWidgets.QPushButton("PGS Bilder ansehen")
        self.btn_conv_srt.clicked.connect(self.show_srt_requested.emit)
        self.btn_conv_pgs.clicked.connect(self.show_pgs_requested.emit)
        conv_layout.addWidget(self.btn_conv_srt)
        conv_layout.addWidget(self.btn_conv_pgs)
        self.lbl_conv = QtWidgets.QLabel("Analysematerial einsehen:")
        self.lbl_conv.setFont(QtGui.QFont("Segoe UI", 10, QtGui.QFont.Bold))
        layout.addWidget(self.lbl_conv)
        layout.addLayout(conv_layout)
        
        self.srt_text_edit = QtWidgets.QTextEdit()
        self.srt_text_edit.setReadOnly(True)
        self.srt_text_edit.setVisible(False)
        self.srt_text_edit.setMaximumHeight(200)
        self.srt_text_edit.setStyleSheet("background-color: #1e1e1e; border: 1px solid #555; color: #ddd; font-family: Consolas;")
        layout.addWidget(self.srt_text_edit)
        
        layout.addStretch()
        
        self.btn_save = QtWidgets.QPushButton("✔ Spur bestätigen & Weiter")
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
            'title': self.txt_titel.text()
        }
        
    def set_form_data(self, df_row):
        is_audio = str(df_row['track_type']).lower() == 'audio'
        
        # Hide unneeded fields for audio
        for row_idx in [2, 3, 4]: # SDH, Forced, Name
            for col in range(5):
                item = self.form_grid.itemAtPosition(row_idx, col)
                if item and item.widget():
                    item.widget().setVisible(not is_audio)
                    
        self.btn_conv_srt.setVisible(False)
        self.btn_conv_pgs.setVisible(False)
        self.lbl_conv.setVisible(False)
        self.srt_text_edit.setVisible(False)
        self.btn_conv_srt.setText("SRT ansehen")
        
        if str(df_row['track_type']).lower() == 'untertitel':
            codec = str(df_row.get('subtitle_type', '')).lower()
            self.lbl_conv.setVisible(True)
            if not codec or 'srt' in codec or 'subrip' in codec:
                self.btn_conv_srt.setVisible(True)
            else:
                self.btn_conv_pgs.setVisible(True)
                
        self.cmb_lang.setCurrentText(str(df_row['language_iso']))
        self.cmb_sdh.setCurrentText("Ja" if bool(df_row['is_hearing_impaired']) else "Nein")
        self.cmb_forced.setCurrentText("Ja" if bool(df_row['is_forced']) else "Nein")
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
        
    def update_validation_ui(self, val_data, is_all_valid):
        for field in ['lang', 'sdh', 'forced', 'default', 'name']:
            btn = getattr(self, f"btn_valid_{field}")
            if val_data.get(field):
                btn.setStyleSheet("background-color: #4caf50; color: white;")
            else:
                btn.setStyleSheet("")
                
        if self.track_list.currentRow() >= 0:
            row = self.track_list.currentRow()
            for col in range(3):
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
        if self.srt_text_edit.isVisible() and text_content is None:
            self.srt_text_edit.setVisible(False)
            self.btn_conv_srt.setText("SRT ansehen")
        elif text_content:
            self.srt_text_edit.setPlainText(text_content)
            self.srt_text_edit.setVisible(True)
            self.btn_conv_srt.setText("SRT verbergen")
