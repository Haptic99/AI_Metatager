import sys
import traceback
from PyQt5 import QtWidgets, QtCore
from ai_metatagger.ui.main_window import CockpitWizard

def main():
    try:
        app = QtWidgets.QApplication(sys.argv)
        app.setStyle('Fusion')
        window = CockpitWizard()
        window.showMaximized()
        sys.exit(app.exec_())
    except Exception as e:
        traceback.print_exc()
        input("Press Enter to exit...")

if __name__ == '__main__':
    main()
