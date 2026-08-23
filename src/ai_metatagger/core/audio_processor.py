import os
import sys
import time
import datetime
import shutil
import re
import subprocess
import json
import concurrent.futures

from ai_metatagger.utils.subprocess_tracker import tracked_run
from ai_metatagger.core.logger import write_log, write_review
from ai_metatagger.core.ffmpeg_tools import get_streams
from ai_metatagger.core.subtitle_tools import (
    is_same_lang_family, is_hearing_impaired, map_lang,
    get_clean_title, is_duplicate_text, read_text_subtitle,
    auto_sync_subtitle, ISO_LEGACY_MAP
)
from ai_metatagger.core.audio_analyzer import detect_audio_language_whisper
from ai_metatagger.core.ocr_analyzer import analyze_subtitle_pgs
from ai_metatagger.config import DATA_DIR, DIR_SERIEN, FFSUBSYNC_PATH, MKVPROPEDIT, CONFIG, TEMP_DIR
from langdetect import detect_langs, DetectorFactory

if os.name == 'nt':
    class NoWindowPopen(subprocess.Popen):
        def __init__(self, *args, **kwargs):
            kwargs.setdefault('creationflags', 0x08000000)
            super().__init__(*args, **kwargs)
    subprocess.Popen = NoWindowPopen

DetectorFactory.seed = 0
MEDIA_DIR = DIR_SERIEN

def _process_audio(
    filepath: str,
    audio_streams: list,
    synced_srt_paths: dict,
    progress_callback=None,
) -> tuple:
    """Analyse all audio streams with Whisper.

    Returns:
        (mapped_audios, has_ger_audio, needs_muxing)
    """
    mapped_audios = []
    has_ger_audio = False
    needs_muxing = False

    best_srt = None
    if synced_srt_paths:
        largest_srt = max(synced_srt_paths.values(), key=lambda p: os.path.getsize(p) if os.path.exists(p) else 0)
        if os.path.exists(largest_srt) and os.path.getsize(largest_srt) > 20000:
            best_srt = largest_srt

    for idx, s in audio_streams:
        if progress_callback:
            progress_callback('audio', idx, 'start')
        tags = s.get('tags', {})
        old_lang = tags.get('language', 'und')
        old_title = tags.get('title', '')

        new_lang = map_lang(old_lang, old_title)

        write_log(f"  -> Audio Spur {idx} (Bisher: '{new_lang}'). Starte Whisper Analyse...")
        start_t = time.time()
        detected, conf = detect_audio_language_whisper(filepath, idx, best_srt)
        dur = time.time() - start_t
        if detected != 'und':
            if not is_same_lang_family(detected, new_lang):
                write_log(f"     => Audio KI Korrektur: War '{new_lang}', ist jetzt '{detected}' (Sicherheit: {conf}, Dauer: {dur:.1f}s)", log_type="korrektur")
                new_lang = detected
            else:
                write_log(f"     => Audio KI Bestätigt: '{detected}' (Sicherheit: {conf}, Dauer: {dur:.1f}s)", log_type="korrektur")

            try:
                c_val = float(str(conf).replace('%', ''))
                expected = CONFIG.get("expected_langs", [])
                if c_val < CONFIG.get("confidence_threshold", 75.0):
                    write_review(f"[{os.path.basename(filepath)}] Spur {idx} (Audio): KI sehr unsicher ({c_val:.1f}% für '{detected}')")
                elif detected not in expected and detected != 'und':
                    write_review(f"[{os.path.basename(filepath)}] Spur {idx} (Audio): Exotische Sprache erkannt ('{detected}')")
            except Exception as e:
                write_log(f"Warnung in {__name__}: {e}")

        if new_lang != old_lang or old_title:
            needs_muxing = True

        if new_lang == 'ger':
            has_ger_audio = True

        mapped_audios.append((idx, new_lang))
        if progress_callback:
            progress_callback('audio', idx, 'done')

    return mapped_audios, has_ger_audio, needs_muxing
