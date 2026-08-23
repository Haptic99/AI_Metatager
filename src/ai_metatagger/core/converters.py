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

def _convert_container(filepath: str) -> str:
    """Convert non-MKV containers (.mp4, .avi, .m4v) to MKV.

    Args:
        filepath: Path to the media file.

    Returns:
        The (potentially updated) filepath pointing to an MKV file,
        or empty string if conversion failed.
    """
    base, ext = os.path.splitext(filepath)
    ext = ext.lower()

    if ext in ['.mp4', '.avi', '.m4v']:
        write_log(f"  -> Konvertiere {ext} in .mkv Container...")
        new_filepath = base + ".mkv"
        cmd = ["ffmpeg", "-v", "quiet", "-y", "-i", filepath, "-c", "copy", "-map", "0", new_filepath]
        res = tracked_run(cmd)
        if res.returncode == 0 and os.path.exists(new_filepath):
            os.remove(filepath)
            write_log("     Erfolgreich konvertiert.")
            return new_filepath
        else:
            return ""
    return filepath
