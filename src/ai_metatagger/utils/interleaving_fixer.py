import os
import json
import shutil
import subprocess
from ai_metatagger.utils.subprocess_tracker import tracked_run

class InterleavingFixer:
    """
    Prüft und repariert MKV-Dateien mit schlechtem Interleaving.
    Schlechtes Interleaving führt zu langen Lade- und Seek-Zeiten in Videoplayern wie VLC,
    da Audio- und Video-Pakete physisch sehr weit voneinander entfernt in der Datei liegen.
    """

    @staticmethod
    def needs_interleaving_fix(filepath, threshold_bytes=50_000_000):
        """
        Prüft per Stichprobe (bei 3 Minuten), ob die Byte-Positionen von Audio und Video 
        zu weit auseinander liegen.
        """
        if not os.path.exists(filepath):
            return False

        try:
            # 1. Stream-Typen (Video/Audio) ermitteln
            stream_cmd = [
                "ffprobe", "-v", "error", 
                "-show_streams", 
                "-show_entries", "stream=index,codec_type", 
                "-of", "json", 
                filepath
            ]
            res_streams = tracked_run(stream_cmd, capture_output=True, text=True, check=True)
            streams_data = json.loads(res_streams.stdout)
            
            stream_types = {}
            for s in streams_data.get("streams", []):
                stream_types[s.get("index")] = s.get("codec_type")
                
            # 2. Pakete bei ca. Minute 3 (180s) auslesen
            pkt_cmd = [
                "ffprobe", "-v", "error",
                "-show_packets",
                "-show_entries", "packet=stream_index,pts_time,pos",
                "-read_intervals", "180%+1",
                "-print_format", "json",
                filepath
            ]
            res_pkts = tracked_run(pkt_cmd, capture_output=True, text=True, check=True)
            pkts_data = json.loads(res_pkts.stdout)
            
            video_pos = None
            audio_positions = {}
            
            for p in pkts_data.get("packets", []):
                idx = p.get("stream_index")
                pos_str = p.get("pos")
                
                # Manche kaputten Dateien haben keine 'pos' in ffprobe
                if pos_str is None:
                    continue
                pos = int(pos_str)
                
                stype = stream_types.get(idx)
                if stype == "video" and video_pos is None:
                    video_pos = pos
                elif stype == "audio" and idx not in audio_positions:
                    audio_positions[idx] = pos
                    
            # Wenn Datei zu kurz ist oder keine Pakete gefunden wurden
            if video_pos is None or not audio_positions:
                return False
                
            # 3. Delta berechnen und auf fehlende Streams prüfen
            expected_audio_indices = [idx for idx, stype in stream_types.items() if stype == "audio"]
            
            for aidx in expected_audio_indices:
                if aidx not in audio_positions:
                    print(f"[InterleavingFixer] Schlechtes Interleaving in {os.path.basename(filepath)}")
                    print(f" -> Audio-Stream {aidx} fehlt komplett im Video-Cluster (extremes Interleaving)!")
                    return True

            for aidx, apos in audio_positions.items():
                delta = abs(video_pos - apos)
                if delta > threshold_bytes:
                    print(f"[InterleavingFixer] Schlechtes Interleaving entdeckt in {os.path.basename(filepath)}")
                    print(f" -> Delta: {delta / 1_000_000:.2f} MB (Threshold: {threshold_bytes / 1_000_000:.2f} MB)")
                    return True
                    
            return False
            
        except subprocess.CalledProcessError as e:
            print(f"[InterleavingFixer] FFprobe Fehler bei {os.path.basename(filepath)}: {e}")
            return False
        except Exception as e:
            print(f"[InterleavingFixer] Unerwarteter Fehler bei {os.path.basename(filepath)}: {e}")
            return False

    @staticmethod
    def fix_interleaving(filepath):
        """
        Kopiert alle Streams (Video, Audio, Subtitles, Attachments) in einen neuen MKV-Container.
        FFmpeg muxt dabei standardmäßig korrekt interleaved.
        Ersetzt danach das Original.
        """
        base, ext = os.path.splitext(filepath)
        fixed_path = f"{base}_fixed{ext}"
        
        try:
            print(f"[InterleavingFixer] Repariere {os.path.basename(filepath)}...")
            cmd = [
                "ffmpeg", "-y",
                "-i", filepath,
                "-i", filepath,
                "-i", filepath,
                "-map", "0:v?",     # Video aus Input 1
                "-map", "1:a?",     # Audio aus Input 2
                "-map", "2:s?",     # Untertitel aus Input 3
                "-c", "copy",       # Kein Re-Encoding
                fixed_path
            ]
            
            # Kein capture_output, damit man in der Konsole evtl. Fortschritt sieht, falls gewünscht
            # Da es asynchron oder im Hintergrund laufen soll, nutzen wir run mit capture_output, 
            # damit die UI nicht mit Output zugemüllt wird.
            res = tracked_run(cmd, capture_output=True, text=True)
            
            if res.returncode == 0 and os.path.exists(fixed_path):
                # Wenn erfolgreich, Original löschen und neue Datei umbenennen
                os.remove(filepath)
                shutil.move(fixed_path, filepath)
                print(f"[InterleavingFixer] Reparatur erfolgreich!")
                return True
            else:
                print(f"[InterleavingFixer] Fehler beim Reparieren (Return Code {res.returncode})")
                if os.path.exists(fixed_path):
                    os.remove(fixed_path)
                return False
                
        except Exception as e:
            print(f"[InterleavingFixer] Exception beim Reparieren von {os.path.basename(filepath)}: {e}")
            if os.path.exists(fixed_path):
                os.remove(fixed_path)
            return False
