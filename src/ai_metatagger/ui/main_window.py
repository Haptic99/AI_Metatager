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
        self.screen3.bg_status_frame.show()
        self.screen3.btn_cancel_analysis.setEnabled(True)
        self.screen3.bg_progress.setMaximum(100)
        self.screen3.bg_progress.setValue(0)
        self.screen3.lbl_bg_status.setText(f"KI-Analyse läuft: 0/{len(file_paths)}")
        self.thread = AnalysisThread(file_paths)
        self.thread.progress_update.connect(self.update_bg_progress)
        self.thread.movie_ready.connect(self.screen3.check_for_new_data)
        self.thread.finished_analysis.connect(self.analysis_done)
        self.thread.start()
        self.screen3.check_for_new_data()
    def update_bg_progress(self, current, total, msg):
        self.screen3.bg_progress.setMaximum(total)
        self.screen3.bg_progress.setValue(current)
        num_files = len(self.thread.file_paths) if hasattr(self, 'thread') else 1
        if num_files == 1:
            msg = msg.replace("Film 1/1: ", "")
            self.screen3.lbl_bg_status.setText(msg)
        else:
            self.screen3.lbl_bg_status.setText(msg)
    def cancel_analysis(self):
        if hasattr(self, 'thread') and self.thread.isRunning():
            self.thread.stop()
            self.screen3.btn_cancel_analysis.setEnabled(False)
            self.screen3.lbl_bg_status.setText("KI-Analyse wird abgebrochen...")
    def analysis_done(self):
        self.screen3.lbl_bg_status.setText("KI-Analyse vollständig abgeschlossen!")
        self.screen3.bg_progress.setValue(self.screen3.bg_progress.maximum())
        self.screen3.scan_files()
        self.screen3.bg_status_frame.hide()
    def closeEvent(self, event):
        # Stop any running analysis thread and its subprocesses
        if hasattr(self, 'thread') and self.thread.isRunning():
            self.thread.stop()
            self.thread.wait(5000)  # Wait up to 5s for thread to finish
        # Release Whisper VRAM
        try:
            from ai_metatagger.core.audio_analyzer import unload_whisper_model
            unload_whisper_model()
        except Exception:
            pass
        self.screen3.stop()
        event.accept()

