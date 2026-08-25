from ai_metatagger.ui.styles import DARK_STYLESHEET
import os
import sys
from PyQt5 import QtWidgets, QtCore, QtGui
from ai_metatagger.ui.screens.validator import Screen3Validator
from ai_metatagger.ui.screens.trainer import Screen4Trainer
from ai_metatagger.utils.thread_workers import AnalysisThread
class CockpitWizard(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Jellyfin AI Cockpit 2.0")
        self.resize(1200, 750)
        self.setStyleSheet(DARK_STYLESHEET)
        self.stacked = QtWidgets.QStackedWidget()
        self.setCentralWidget(self.stacked)
        self.screen3 = Screen3Validator(self)
        self.screen4 = Screen4Trainer(self)
        self.stacked.addWidget(self.screen3)
        self.stacked.addWidget(self.screen4)
    def start_analysis_and_validation(self, file_paths):
        self.screen3.sidebar.bg_status_frame.show()
        self.screen3.sidebar.btn_cancel_analysis.setEnabled(True)
        self.screen3.sidebar.bg_progress.setMaximum(100)
        self.screen3.sidebar.bg_progress.setValue(0)
        self.screen3.sidebar.lbl_bg_status.setText(f"KI-Analyse läuft: 0/{len(file_paths)}")
        self.analysis_worker = AnalysisThread(file_paths)
        self.analysis_worker.progress_update.connect(self.update_bg_progress)
        self.analysis_worker.movie_ready.connect(self.screen3.check_for_new_data)
        self.analysis_worker.finished_analysis.connect(self.analysis_done)
        self.analysis_worker.start()
        self.screen3.check_for_new_data()
    def update_bg_progress(self, current, total, msg):
        self.screen3.sidebar.bg_progress.setMaximum(total)
        self.screen3.sidebar.bg_progress.setValue(current)
        num_files = len(self.analysis_worker.file_paths) if hasattr(self, 'analysis_worker') else 1
        if num_files == 1:
            msg = msg.replace("Film 1/1: ", "")
            self.screen3.sidebar.lbl_bg_status.setText(msg)
        else:
            self.screen3.sidebar.lbl_bg_status.setText(msg)
    def cancel_analysis(self):
        if hasattr(self, 'analysis_worker') and self.analysis_worker.isRunning():
            self.analysis_worker.stop()
            self.screen3.sidebar.btn_cancel_analysis.setEnabled(False)
            self.screen3.sidebar.lbl_bg_status.setText("KI-Analyse wird abgebrochen...")
    def analysis_done(self):
        if hasattr(self, 'analysis_worker') and self.analysis_worker.is_cancelled:
            self.screen3.sidebar.lbl_bg_status.setText("Analyse abgebrochen. Daten bereinigt.")
        else:
            self.screen3.sidebar.lbl_bg_status.setText("KI-Analyse vollständig abgeschlossen!")
            
        self.screen3.sidebar.bg_progress.setValue(self.screen3.sidebar.bg_progress.maximum())
        
        # WICHTIG: Liste sofort aktualisieren, damit abgebrochene Filme verschwinden
        self.screen3.scan_files()
        self.screen3.check_for_new_data()
        
        # Blendet das Fenster nach 2,5 Sekunden aus, damit man die Meldung noch lesen kann
        QtCore.QTimer.singleShot(2500, self.screen3.sidebar.bg_status_frame.hide)
    def closeEvent(self, event):
        self.screen3.player_widget.release_safe()
        # Stop any running analysis thread and its subprocesses
        if hasattr(self, 'analysis_worker') and self.analysis_worker.isRunning():
            self.analysis_worker.stop()
            self.analysis_worker.wait(5000)  # Wait up to 5s for thread to finish
        # Release Whisper VRAM
        try:
            from ai_metatagger.core.audio_analyzer import unload_whisper_model
            unload_whisper_model()
        except Exception:
            pass
        event.accept()

