import os
import sys
import json

# Absolute path to the project root directory (two levels up from this file)
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))

# Data paths
DATA_DIR = os.path.join(BASE_DIR, 'data')
TEMP_DIR = os.path.join(DATA_DIR, 'temp_cleanup')
CONFIG_PATH = os.path.join(DATA_DIR, 'config.json')
DB_PATH = os.path.join(DATA_DIR, 'Jellyfin_AI_Database.sqlite')

try:
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(TEMP_DIR, exist_ok=True)
except OSError as e:
    print(f"FEHLER: Verzeichnisse konnten nicht angelegt werden ({DATA_DIR}): {e}")
    print("Bitte stellen Sie sicher, dass das Programm Schreibrechte hat.")

def load_config():
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading config.json: {e}")
    return {}

def save_config(config_dict):
    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump(config_dict, f, indent=4)

CONFIG = load_config()

DIR_FILME = CONFIG.get("Verzeichnis_Filme", "")
DIR_SERIEN = CONFIG.get("Verzeichnis_Serien", "")
DIR_TEST = CONFIG.get("Verzeichnis_Test", "")

PYTHON_EXE = CONFIG.get("Pfad_Python", sys.executable)
MKVPROPEDIT = CONFIG.get("Pfad_mkvpropedit", "mkvpropedit")
TESSERACT_PATH = CONFIG.get("Pfad_Tesseract", r"C:\Users\dmart\AppData\Local\Programs\Tesseract-OCR\tesseract.exe")
FFSUBSYNC_PATH = CONFIG.get("Pfad_ffsubsync", r"C:\Users\dmart\AppData\Roaming\Python\Python313\Scripts\ffsubsync.exe")
WHISPER_MODEL_SIZE = CONFIG.get("Whisper_Model", "tiny")
