"""Audio language detection using faster-whisper and Silero VAD for the AI Metatagger.
Provides model lifecycle management (load/unload with VRAM cleanup) and 
multi-spot language detection with smart silence skipping.
"""
import os

import subprocess
import warnings
from collections import defaultdict
from typing import List, Optional, Tuple

import torch

# --- NEUER FIX FÜR DEN LAUTLOSEN ABSTURZ (CUDA DLLs) ---
# faster-whisper (CTranslate2) findet die Windows-NVIDIA-Dateien oft nicht. 
# Wir binden hier die mitgelieferten Dateien von PyTorch in den Systempfad ein:
if os.name == 'nt':
    paths_to_add = []
    
    # 1. PyTorch lib (für ältere Modelle / CUDA 11)
    paths_to_add.append(os.path.join(os.path.dirname(torch.__file__), "lib"))
    
    # 2. Nvidia CUDA 12 packages (für ctranslate2 v4+)
    import site
    for base in site.getsitepackages() + [site.getusersitepackages()]:
        paths_to_add.append(os.path.join(base, "nvidia", "cublas", "bin"))
        paths_to_add.append(os.path.join(base, "nvidia", "cudnn", "bin"))
        
    for p in paths_to_add:
        if os.path.exists(p):
            os.environ["PATH"] = p + os.pathsep + os.environ.get("PATH", "")
            if hasattr(os, 'add_dll_directory'):
                try:
                    os.add_dll_directory(p)
                except Exception:
                    pass
from faster_whisper import WhisperModel

from ai_metatagger.utils.subprocess_tracker import tracked_run
from ai_metatagger.config import WHISPER_MODEL_SIZE, TEMP_DIR
from ai_metatagger.core.logger import write_log
from ai_metatagger.core.subtitle_tools import find_dense_audio_spots, map_lang

_WHISPER_MODEL = None
_VAD_MODEL = None
_VAD_UTILS = None

def get_whisper_model():
    """Load and cache the faster-whisper model."""
    global _WHISPER_MODEL
    if _WHISPER_MODEL is None:
        # CUDA wieder aktivieren
        device = "cuda" if torch.cuda.is_available() else "cpu"
        compute_type = "float16" if device == "cuda" else "int8"
        write_log(f"Lade faster-whisper Modell ({WHISPER_MODEL_SIZE}) auf {device} ({compute_type})...", console=False)
        
        # cpu_threads=1 verhindert, dass der PyQt-Thread bei der CUDA-Initialisierung abstürzt
        _WHISPER_MODEL = WhisperModel(WHISPER_MODEL_SIZE, device=device, compute_type=compute_type, cpu_threads=1)
    return _WHISPER_MODEL

def get_vad_model():
    """Load and cache the Silero VAD model."""
    global _VAD_MODEL, _VAD_UTILS
    if _VAD_MODEL is None:
        write_log("Lade Silero VAD Modell zur Vorprüfung...", console=False)
        warnings.filterwarnings("ignore", category=UserWarning)
        _VAD_MODEL, _VAD_UTILS = torch.hub.load(repo_or_dir='snakers4/silero-vad',
                                                model='silero_vad',
                                                force_reload=False,
                                                trust_repo=True)
    return _VAD_MODEL, _VAD_UTILS

def unload_whisper_model() -> None:
    """Release the cached models and free VRAM/RAM."""
    global _WHISPER_MODEL, _VAD_MODEL, _VAD_UTILS
    if _WHISPER_MODEL is not None or _VAD_MODEL is not None:
        write_log("Entlade KI-Modelle aus dem Speicher...", console=False)
        del _WHISPER_MODEL
        del _VAD_MODEL
        del _VAD_UTILS
        _WHISPER_MODEL = None
        _VAD_MODEL = None
        _VAD_UTILS = None
        # torch.cuda.empty_cache() removed to prevent QThread segfault on Windows

def detect_audio_language_whisper(
    video_path: str,
    audio_stream_idx: int,
    srt_path: Optional[str],
) -> Tuple[str, str]:
    """Detect the language of an audio stream using VAD + Faster-Whisper."""
    num_spots = 6
    duration_sec = 30
    spots: List[float] = []

    if srt_path and os.path.exists(srt_path):
        spots = find_dense_audio_spots(srt_path, num_spots=num_spots, duration_sec=duration_sec)

    if not spots:
        write_log(f"       -> Kein voller Text-Untertitel gefunden. Nutze {num_spots} mathematische Zeitstempel.", console=False)
        try:
            dur_cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                       "-of", "default=noprint_wrappers=1:nokey=1", video_path]
            res = tracked_run(dur_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            total_dur = float(res.stdout.strip())
            safe_dur = total_dur - 600 if total_dur > 600 else total_dur
            start_off = 300 if total_dur > 600 else 0
            interval = safe_dur / num_spots
            spots = [start_off + (i * interval) for i in range(num_spots)]
        except (subprocess.SubprocessError, ValueError) as e:
            write_log(f"Dauer konnte nicht ermittelt werden: {e}")
            spots = [300, 900, 1500, 2100, 2700, 3300]

    try:
        model = get_whisper_model()
        vad_model, vad_utils = get_vad_model()
        get_speech_timestamps = vad_utils[0]
        import torchaudio
    except Exception as e:
        write_log(f'Whisper/VAD Model Load Error: {e}')
        return 'und', '0%'

    detected_langs: List[Tuple[str, float]] = []

    for base_spot in spots:
        current_spot = base_spot
        spot_success = False
        
        for attempt in range(4):  # Maximal 4 Versuche (+0s, +15s, +30s, +45s)
            temp_audio = os.path.join(TEMP_DIR, f"temp_audio_{audio_stream_idx}_{int(current_spot)}.wav")
            cmd = ["ffmpeg", "-v", "quiet", "-y", "-ss", str(current_spot), "-i", video_path,
                   "-map", f"0:{audio_stream_idx}", "-t", "30",
                   "-c:a", "pcm_s16le", "-ar", "16000", "-ac", "1", temp_audio]
            tracked_run(cmd)

            if os.path.exists(temp_audio):
                try:
                    # 1. Silero VAD Check (Gibt es hier überhaupt Sprache?)
                    wav, sr = torchaudio.load(temp_audio)
                    if sr != 16000:
                        import torchaudio.transforms as T
                        resampler = T.Resample(sr, 16000)
                        wav = resampler(wav)
                    wav = wav.squeeze(0)
                    speech_timestamps = get_speech_timestamps(wav, vad_model, sampling_rate=16000)
                    
                    if not speech_timestamps:
                        write_log(f"       VAD: Keine Sprache bei {int(current_spot)}s. Springe 15s vor...", console=False)
                        current_spot += 15
                        continue
                        
                    # 2. Faster-Whisper Analyse (da echte Sprache gefunden wurde)
                    segments, info = model.transcribe(temp_audio, beam_size=1)
                    
                    lang = info.language
                    prob = info.language_probability * 100
                    
                    detected_langs.append((map_lang(lang), prob))
                    write_log(f"       Whisper KI (Spot {int(current_spot)}s): {map_lang(lang)} ({prob:.1f}%)", console=False)
                    spot_success = True
                    break  # Spot erfolgreich, verlasse die Skip-Schleife
                    
                except Exception as e:
                    write_log(f"Warnung bei Analyse (Spot {int(current_spot)}s): {e}")
                    break  # Bei echten Systemfehlern die Schleife verlassen
                finally:
                    try:
                        os.remove(temp_audio)
                    except OSError:
                        pass
                        
        if not spot_success:
            write_log(f"       VAD: Auch nach 4 Versuchen keine Sprache um {int(base_spot)}s gefunden.", console=False)

    if detected_langs:
        counts: defaultdict = defaultdict(list)
        for l, p in detected_langs:
            counts[l].append(p)
        best_lang = max(counts.keys(), key=lambda k: len(counts[k]))
        if len(counts[best_lang]) >= 2 or (len(counts[best_lang]) == 1 and len(spots) == 1):
            avg_prob = sum(counts[best_lang]) / len(counts[best_lang])
            return best_lang, f"{avg_prob:.1f}%"

    return 'und', '0%'