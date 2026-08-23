import os
import subprocess
import whisper
import torch
from collections import defaultdict
from ai_metatagger.config import WHISPER_MODEL_SIZE, TEMP_DIR
from ai_metatagger.core.logger import write_log
from ai_metatagger.core.subtitle_tools import find_dense_audio_spots, map_lang

_WHISPER_MODEL = None


def get_whisper_model():
    """Load and cache the Whisper model. Subsequent calls return the cached instance."""
    global _WHISPER_MODEL
    if _WHISPER_MODEL is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"
        write_log(f"Lade Whisper Modell ({WHISPER_MODEL_SIZE}) auf {device}...", console=False)
        _WHISPER_MODEL = whisper.load_model(WHISPER_MODEL_SIZE, device=device)
    return _WHISPER_MODEL


def unload_whisper_model():
    """Release the cached Whisper model and free VRAM/RAM."""
    global _WHISPER_MODEL
    if _WHISPER_MODEL is not None:
        write_log("Entlade Whisper Modell aus dem Speicher...", console=False)
        del _WHISPER_MODEL
        _WHISPER_MODEL = None
        if torch.cuda.is_available():
            torch.cuda.empty_cache()


def detect_audio_language_whisper(video_path, audio_stream_idx, srt_path):
    num_spots = 6
    duration_sec = 30
    spots = []

    if srt_path and os.path.exists(srt_path):
        spots = find_dense_audio_spots(srt_path, num_spots=num_spots, duration_sec=duration_sec)

    if not spots:
        write_log(f"       -> Kein voller Text-Untertitel gefunden. Nutze {num_spots} mathematische Zeitstempel.", console=False)
        try:
            dur_cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                       "-of", "default=noprint_wrappers=1:nokey=1", video_path]
            total_dur = float(subprocess.check_output(dur_cmd).decode('utf-8').strip())
            safe_dur = total_dur - 600 if total_dur > 600 else total_dur
            start_off = 300 if total_dur > 600 else 0
            interval = safe_dur / num_spots
            spots = [start_off + (i * interval) for i in range(num_spots)]
        except (subprocess.SubprocessError, ValueError) as e:
            write_log(f"Dauer konnte nicht ermittelt werden: {e}")
            spots = [300, 900, 1500, 2100, 2700, 3300]

    try:
        model = get_whisper_model()
    except Exception as e:
        write_log(f'Whisper Model Load Error: {e}')
        return 'und', '0%'

    detected_langs = []

    for spot in spots:
        temp_audio = os.path.join(TEMP_DIR, f"temp_audio_{audio_stream_idx}_{int(spot)}.wav")
        cmd = ["ffmpeg", "-v", "quiet", "-y", "-ss", str(spot), "-i", video_path,
               "-map", f"0:{audio_stream_idx}", "-t", "30",
               "-c:a", "pcm_s16le", "-ar", "16000", "-ac", "1", temp_audio]
        subprocess.run(cmd)

        if os.path.exists(temp_audio):
            try:
                audio = whisper.load_audio(temp_audio)
                audio = whisper.pad_or_trim(audio)
                mel = whisper.log_mel_spectrogram(audio, n_mels=model.dims.n_mels).to(model.device)
                _, probs = model.detect_language(mel)
                lang = max(probs, key=probs.get)
                prob = probs[lang] * 100
                detected_langs.append((map_lang(lang), prob))
                write_log(f"       Whisper KI (Spot {int(spot)}s): {map_lang(lang)} ({prob:.1f}%)", console=False)
            except Exception as e:
                write_log(f"Warnung bei Whisper-Analyse (Spot {int(spot)}s): {e}")
            finally:
                try:
                    os.remove(temp_audio)
                except OSError as e:
                    write_log(f"Temp-Datei konnte nicht gelöscht werden: {temp_audio}: {e}")

    if detected_langs:
        counts = defaultdict(list)
        for l, p in detected_langs:
            counts[l].append(p)
        best_lang = max(counts.keys(), key=lambda k: len(counts[k]))
        if len(counts[best_lang]) >= 2 or (len(counts[best_lang]) == 1 and len(spots) == 1):
            avg_prob = sum(counts[best_lang]) / len(counts[best_lang])
            return best_lang, f"{avg_prob:.1f}%"

    return 'und', '0%'
