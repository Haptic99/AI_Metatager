import sys
import traceback

def hook(exctype, value, tb):
    with open("F:\\Jellyfin_AI_Cockpit\\global_crash.log", "w") as f:
        traceback.print_exception(exctype, value, tb, file=f)
sys.excepthook = hook

from ai_metatagger.ui.components.video_player import VideoPlayerWidget
from PyQt5 import QtWidgets

app = QtWidgets.QApplication(sys.argv)
vp = VideoPlayerWidget()
vp.show()
vp.play_media(r"F:\Jellyfin_AI_Cockpit\data\Test_Videos\The Witcher (2019) - S01E01.mkv", "subtitle", 4, True)

def check_spu():
    print("CURRENT SPU:", vp.media_player.video_get_spu())
    with open("F:\\Jellyfin_AI_Cockpit\\spu_log.txt", "w") as f:
        f.write("CURRENT SPU: " + str(vp.media_player.video_get_spu()))
    app.quit()

from PyQt5.QtCore import QTimer
QTimer.singleShot(4000, check_spu)
app.exec_()
