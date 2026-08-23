from ai_metatagger.ui.styles import DARK_STYLESHEET
import os
import sys
import vlc
import json
import pandas as pd
from PyQt5 import QtWidgets, QtCore, QtGui
from PyQt5.QtCore import Qt
from ai_metatagger.config import DIR_FILME, DIR_SERIEN, DB_PATH, CONFIG_PATH, save_config, CONFIG
from ai_metatagger.utils.state_manager import load_matrix, save_matrix, load_state, save_state
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









        accuracy_file = r"F:\Jellyfin_AI_Cockpit\data\KI_Accuracy.json"









        if os.path.exists(accuracy_file):









            try:









                with open(accuracy_file, 'r', encoding='utf-8') as f:









                    s = json.load(f)









                t = s.get("total", 1)









                if t == 0: t = 1









                









                text = (









                    "ðŸ† Validierte Spuren gesamt: " + str(s.get('total', 0)) + "\\n\\n" +









                    "✔️ï¸ Sprache korrekt: " + str(s.get('correct_lang', 0)) + " (" + str(int(s.get('correct_lang',0)/t*100)) + "%)\\n" +









                    "✔️ï¸ SDH korrekt: " + str(s.get('correct_sdh', 0)) + " (" + str(int(s.get('correct_sdh',0)/t*100)) + "%)\\n" +









                    "✔️ï¸ Forced korrekt: " + str(s.get('correct_forced', 0)) + " (" + str(int(s.get('correct_forced',0)/t*100)) + "%)\\n\\n" +









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

















