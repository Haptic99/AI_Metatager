import os
import sys
import pandas as pd
import shutil

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
OLD_MATRIX_PATH = os.path.join(ROOT_DIR, 'Informationsmatrix.xlsx')
NEW_MATRIX_PATH = os.path.join(ROOT_DIR, 'data', 'Jellyfin_AI_Matrix.xlsx')

def main():
    if not os.path.exists(OLD_MATRIX_PATH):
        print(f"FEHLER: Die Datei '{OLD_MATRIX_PATH}' wurde nicht gefunden.")
        print("Bitte lege deine alte 'Informationsmatrix.xlsx' direkt in den Hauptordner (F:\Jellyfin_AI_Cockpit) und starte dieses Skript erneut.")
        input("Drücke Enter zum Beenden...")
        sys.exit(1)
        
    try:
        # Lese alte Matrix
        print("Lese alte Informationsmatrix.xlsx...")
        df_old = pd.read_excel(OLD_MATRIX_PATH)
        
        # Stelle sicher, dass die Spalten korrekt sind (das neue Format)
        expected_columns = [
            'Name', 'ID', 'Art', 'Effektive Sprache (ISO-Code)', 'Effektiver Name', 
            'Standardspur', 'Untertitelart', 'Schwerhörig-Schalter', 
            'Anzeige erzwingen-Schalter', 'Sonstiges'
        ]
        
        # Falls alte Spalten leicht abweichen, hier anpassen. Aber wir gehen davon aus, dass sie passen.
        for col in expected_columns:
            if col not in df_old.columns:
                print(f"Warnung: Spalte '{col}' fehlt in der alten Matrix. Sie wird leer hinzugefügt.")
                df_old[col] = ""
                
        # Behalte nur die erwarteten Spalten in der richtigen Reihenfolge
        df_new = df_old[expected_columns]
        
        # Speichere im neuen Format ab
        print(f"Speichere in das neue Format: {NEW_MATRIX_PATH}")
        os.makedirs(os.path.dirname(NEW_MATRIX_PATH), exist_ok=True)
        df_new.to_excel(NEW_MATRIX_PATH, index=False)
        
        print("\nERFOLG! Deine alten Daten wurden erfolgreich importiert.")
        print("Du kannst das Programm nun normal über 'Start Cockpit.bat' starten.")
        input("Drücke Enter zum Beenden...")
        
    except Exception as e:
        print(f"Ein Fehler ist aufgetreten: {e}")
        input("Drücke Enter zum Beenden...")

if __name__ == '__main__':
    main()
