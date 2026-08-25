path = r"F:\Jellyfin_AI_Cockpit\src\ai_metatagger\ui\screens\validator.py"
with open(path, "r", encoding="utf-8") as f:
    content = f.read()

# 1. Update play_movie to use smart seek
old_play = """            self.player_widget.play_media(
                filepath, track_type.lower(), relative_idx, autoplay)"""

new_play = """            self.player_widget.play_media(
                filepath, track_type.lower(), relative_idx, autoplay)
            
            if autoplay:
                seek_time = self._get_smart_seek_time(film, track_type, track_id)
                # Wait 2500ms so VLC has enough time to init D3D11 and set SPU before we jump
                from PyQt5 import QtCore
                QtCore.QTimer.singleShot(2500, lambda: self.player_widget.seek_absolute(seek_time))"""

content = content.replace(old_play, new_play)

# 2. Update _test_text_clicked to use smart seek
old_test = """    def _test_text_clicked(self):
        if not self.current_row is None:
            self.player_widget.seek_absolute(300000)"""

new_test = """    def _test_text_clicked(self):
        if not self.current_row is None:
            film = self.current_row['file_name']
            typ = self.current_row['track_type']
            spur = self.current_row['track_id']
            seek_time = self._get_smart_seek_time(film, typ, spur)
            self.player_widget.seek_absolute(seek_time)"""

content = content.replace(old_test, new_test)

with open(path, "w", encoding="utf-8") as f:
    f.write(content)
