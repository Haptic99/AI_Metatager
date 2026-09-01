import sys
import traceback
def hook(extype, value, tb):
    with open("F:\Jellyfin_AI_Cockpit\gui_crash.log", "w") as f:
        traceback.print_exception(extype, value, tb, file=f)
sys.excepthook = hook

import os

os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
os.environ["OMP_NUM_THREADS"] = "1"

import sys
import traceback

# --- NEUER FIX FÜR CUDA 12 DLLs ---
import torch
if os.name == 'nt':
    paths_to_add = []
    paths_to_add.append(os.path.join(os.path.dirname(torch.__file__), "lib"))
    import site
    for base in site.getsitepackages() + [site.getusersitepackages()]:
        paths_to_add.append(os.path.join(base, "nvidia", "cublas", "bin"))
        paths_to_add.append(os.path.join(base, "nvidia", "cudnn", "bin"))
    for p in paths_to_add:
        if os.path.exists(p):
            os.environ["PATH"] = p + os.pathsep + os.environ.get("PATH", "")
            if hasattr(os, 'add_dll_directory'):
                try: os.add_dll_directory(p)
                except Exception: pass

# --- NEUER FIX FÜR CTRANSLATE2 / PYQT5 ABSTURZ ---
# faster_whisper/ctranslate2 MUSS importiert werden, BEVOR PyQt5.QtWidgets.QApplication
# aufgerufen wird, da es sonst zu einem C++ DLL/Threading-Crash kommt!
import ctranslate2
import faster_whisper

from PyQt5 import QtWidgets, QtCore
from ai_metatagger.ui.main_window import CockpitWizard

def main():
    try:
        app = QtWidgets.QApplication(sys.argv)
        app.setStyle('Fusion')
        window = CockpitWizard()
        screen = app.primaryScreen()
        if screen:
            window.move(screen.geometry().topLeft())
        window.showMaximized()
        sys.exit(app.exec_())
    except Exception as e:
        traceback.print_exc()
        input("Press Enter to exit...")

if __name__ == '__main__':
    main()
