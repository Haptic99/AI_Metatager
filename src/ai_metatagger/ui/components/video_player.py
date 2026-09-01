import sys
import os
import time
import threading
from PyQt5 import QtWidgets, QtCore
import vlc

class VideoPlayerWidget(QtWidgets.QWidget):
    """
    A reusable widget that wraps the VLC media player and handles all 
    platform-specific windowing, track switching, and safe cleanup.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.vlc_instance = None
        self.media_player = None
        self.current_filepath = None
        self._stopping = False
        
        self._layout = QtWidgets.QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        
        # Frame for VLC rendering
        if sys.platform == "darwin":
            self.video_frame = QtWidgets.QMacCocoaViewContainer(0)
        else:
            self.video_frame = QtWidgets.QFrame()
            self.video_frame.setPalette(self.palette())
            self.video_frame.setAutoFillBackground(True)
            self.video_frame.setStyleSheet("background-color: black;")
            
        self._layout.addWidget(self.video_frame)
        
    def _init_vlc(self):
        if self.vlc_instance is None:
            self.vlc_instance = vlc.Instance("--no-xlib", "--quiet")
            self.media_player = self.vlc_instance.media_player_new()
            self._stopping = False
            
    def play_media(self, filepath, track_type, track_id, autoplay=False):
        # Re-init if previously released
        self._init_vlc()
        self._stopping = False
        
        # Make sure the frame is visible when playing
        self.video_frame.show()
        
        if filepath != self.current_filepath:
            self.current_filepath = filepath
            media = self.vlc_instance.media_new(filepath)
            self.media_player.set_media(media)
            
            # Platform specific window handle
            if sys.platform.startswith('linux'):
                self.media_player.set_xwindow(self.video_frame.winId())
            elif sys.platform == "win32":
                self.media_player.set_hwnd(self.video_frame.winId())
            elif sys.platform == "darwin":
                self.media_player.set_nsobject(int(self.video_frame.winId()))
                
            self.media_player.play()
            QtCore.QTimer.singleShot(1500, lambda: self.switch_track(track_type, track_id, autoplay, is_new_media=True))
        else:
            self.switch_track(track_type, track_id, autoplay, is_new_media=False)
            
    def switch_track(self, typ, spur_id, autoplay=False, is_new_media=False):
            if not self.media_player or self._stopping:
                return

            typ_lower = str(typ).lower()
                
            if typ_lower == 'audio':
                aud_tracks = self.media_player.audio_get_track_description()
                if aud_tracks:
                    valid_auds = [t[0] for t in aud_tracks if t[0] >= 0]
                    if spur_id - 1 < len(valid_auds):
                        vlc_id = valid_auds[spur_id - 1]
                        self.media_player.audio_set_track(vlc_id)
                self.media_player.video_set_spu(-1)
                
            elif typ_lower in ['untertitel', 'subtitle']:
                # 1. Spuren vom Player abfragen
                spu_tracks = self.media_player.video_get_spu_description()
                
                if spu_tracks:
                    # 2. Filtere alle "echten" Spuren (VLC nutzt oft -1 für "Deaktiviert")
                    valid_spus = [t[0] for t in spu_tracks if t[0] >= 0]
                    
                    # 3. Mappe die 1-basierte spur_id aus deiner UI auf die tatsächliche VLC SPU ID
                    if spur_id - 1 < len(valid_spus):
                        vlc_spu_id = valid_spus[spur_id - 1]
                        self.media_player.video_set_spu(vlc_spu_id)
                    else:
                        print(f"Warnung: Untertitel-Index {spur_id} ausserhalb der verfügbaren SPU-Spuren.")
                else:
                    # Fallback, falls keine Spuren im Header gefunden wurden (oder das Video noch nicht weit genug geladen ist)
                    self.media_player.video_set_spu(spur_id)

                # Audio auf Spur 1 fixieren (wie in deinem originalen Code)
                audio_count = self.media_player.audio_get_track_count()
                if audio_count > 1:
                    self.media_player.audio_set_track(1)
                    
            # Only control play/pause state when loading a new movie
            if is_new_media:
                if autoplay:
                    self.media_player.play()
                else:
                    self.media_player.set_pause(1)
        
    def stop(self):
        if self.media_player and not self._stopping:
            self._stopping = True
            self.media_player.stop()

    def clear_media(self):
        """Stop playback, hide the render surface, and fully release VLC.
        
        Hiding the QFrame BEFORE stopping is critical: it tells D3D11 to
        stop rendering, preventing the segfault that occurs when VLC's
        renderer thread writes to a surface that is being torn down.
        """
        if self._stopping:
            return
        self._stopping = True
        
        # 1. Hide the render frame FIRST so D3D11 stops drawing
        self.video_frame.hide()
        
        if self.media_player:
            # 2. Stop playback
            self.media_player.stop()
            
            # 3. Release in background thread to avoid blocking UI
            player = self.media_player
            instance = self.vlc_instance
            self.media_player = None
            self.vlc_instance = None
            self.current_filepath = None
            
            def _release(p, inst):
                time.sleep(1.0)
                try:
                    p.release()
                except Exception:
                    pass
                try:
                    inst.release()
                except Exception:
                    pass
            threading.Thread(target=_release, args=(player, instance), daemon=True).start()
        else:
            self.current_filepath = None

    def release_safe(self):
        """Alias for clear_media, used on app shutdown."""
        self.clear_media()

    def set_position(self, ms):
        if self.media_player and not self._stopping:
            self.media_player.set_time(ms)

    def seek(self, ms):
        if self.media_player and not self._stopping:
            t = self.media_player.get_time()
            if t != -1:
                self.media_player.set_time(t + ms)

    def seek_absolute(self, ms):
        if self.media_player and not self._stopping:
            self.media_player.set_time(ms)
            self.media_player.play()

    def toggle_play(self):
        if not self.media_player or self._stopping:
            return
        if self.media_player.is_playing():
            self.media_player.pause()
        else:
            self.media_player.play()

    def set_volume(self, vol):
        if self.media_player and not self._stopping:
            self.media_player.audio_set_volume(vol)
            
    def get_time(self):
        if self.media_player and not self._stopping:
            return self.media_player.get_time()
        return -1
        
    def get_length(self):
        if self.media_player and not self._stopping:
            return self.media_player.get_length()
        return -1
