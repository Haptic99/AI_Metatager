from PyQt5 import QtWidgets, QtCore, QtGui
import os

class ValidatorSidebarWidget(QtWidgets.QWidget):
    movie_selected = QtCore.pyqtSignal(str)
    remove_movie_requested = QtCore.pyqtSignal(str)
    analyze_requested = QtCore.pyqtSignal(list)
    cancel_analysis_requested = QtCore.pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        self.lbl_loaded = QtWidgets.QLabel("Zur Validierung bereit:")
        self.lbl_loaded.setFont(QtGui.QFont("Segoe UI", 10, QtGui.QFont.Bold))
        layout.addWidget(self.lbl_loaded)
        
        self.movie_list = QtWidgets.QListWidget()
        self.movie_list.itemClicked.connect(self._on_movie_clicked)
        layout.addWidget(self.movie_list)
        
        self.btn_remove_movie = QtWidgets.QPushButton("X Film ignorieren")
        self.btn_remove_movie.setStyleSheet("background-color: #d32f2f;")
        self.btn_remove_movie.clicked.connect(self._on_remove_clicked)
        layout.addWidget(self.btn_remove_movie)
        
        self.lbl_available = QtWidgets.QLabel("Neue Filme (Auswählen für KI-Analyse):")
        self.lbl_available.setFont(QtGui.QFont("Segoe UI", 10, QtGui.QFont.Bold))
        layout.addWidget(self.lbl_available)
        
        self.scan_list_widget = QtWidgets.QListWidget()
        self.scan_list_widget.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.scan_list_widget.itemSelectionChanged.connect(self._on_scan_selection)
        layout.addWidget(self.scan_list_widget)
        
        self.btn_analyze = QtWidgets.QPushButton("Neu Analysieren ➔")
        self.btn_analyze.setStyleSheet("background-color: #2e7d32; font-weight: bold; padding: 10px;")
        self.btn_analyze.setEnabled(False)
        self.btn_analyze.clicked.connect(self._on_analyze_clicked)
        layout.addWidget(self.btn_analyze)
        
        self.bg_status_frame = QtWidgets.QFrame()
        self.bg_status_frame.setStyleSheet("background-color: #2d2d2d; border-radius: 4px; padding: 5px; margin-top: 5px;")
        bg_layout = QtWidgets.QVBoxLayout(self.bg_status_frame)
        self.lbl_bg_status = QtWidgets.QLabel("KI-Analyse: Initialisiere...")
        self.lbl_bg_status.setWordWrap(True)
        self.bg_progress = QtWidgets.QProgressBar()
        
        self.btn_cancel_analysis = QtWidgets.QPushButton("Stopp")
        self.btn_cancel_analysis.setStyleSheet("background-color: #d32f2f; font-weight: bold; padding: 2px;")
        self.btn_cancel_analysis.clicked.connect(self.cancel_analysis_requested.emit)
        
        bg_layout.addWidget(self.lbl_bg_status)
        bg_layout.addWidget(self.bg_progress)
        bg_layout.addWidget(self.btn_cancel_analysis)
        self.bg_status_frame.hide()
        layout.addWidget(self.bg_status_frame)
        
    def _on_movie_clicked(self, item):
        self.movie_selected.emit(item.text())
        
    def _on_remove_clicked(self):
        item = self.movie_list.currentItem()
        if item:
            self.remove_movie_requested.emit(item.text())
            
    def _on_scan_selection(self):
        self.btn_analyze.setEnabled(len(self.scan_list_widget.selectedItems()) > 0)
        
    def _on_analyze_clicked(self):
        selected_paths = []
        for item in self.scan_list_widget.selectedItems():
            selected_paths.append(item.data(QtCore.Qt.UserRole))
        if selected_paths:
            self.analyze_requested.emit(selected_paths)
            
    def set_movies(self, movies, select_first=False):
        self.movie_list.clear()
        for movie in movies:
            self.movie_list.addItem(movie)
        if select_first and self.movie_list.count() > 0:
            self.movie_list.setCurrentRow(0)
            
    def select_movie(self, film):
        for i in range(self.movie_list.count()):
            if self.movie_list.item(i).text() == film:
                self.movie_list.setCurrentRow(i)
                break
                
    def set_scan_files(self, files):
        self.scan_list_widget.clear()
        for f in files:
            item = QtWidgets.QListWidgetItem(os.path.basename(f))
            item.setData(QtCore.Qt.UserRole, f)
            self.scan_list_widget.addItem(item)
            
    def show_progress(self, show=True):
        self.bg_status_frame.setVisible(show)
        
    def update_progress(self, current, total, text):
        self.bg_progress.setMaximum(total)
        self.bg_progress.setValue(current)
        self.lbl_bg_status.setText(text)
