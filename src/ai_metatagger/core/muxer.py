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

def _build_muxing_args(
    ffmpeg_args: list,
    mapped_audios: list,
    mapped_subs: list,
    audio_streams: list,
    has_ger_audio: bool,
) -> bool:
    """Append muxing arguments to ffmpeg_args and check if muxing is needed.

    Returns:
        True if any disposition/metadata change was detected.
    """
    needs_muxing = False

    ger_audio_idx = -1
    eng_audio_idx = -1
    for i, (orig_idx, new_lang) in enumerate(mapped_audios):
        if new_lang == 'ger' and ger_audio_idx == -1:
            ger_audio_idx = i
        if new_lang == 'eng' and eng_audio_idx == -1:
            eng_audio_idx = i

    ger_sub_idx = -1
    ger_forced_idx = -1
    eng_sub_idx = -1
    for _, is_forced_meta, _, new_lang, _, _, out_idx, _ in mapped_subs:
        if new_lang == 'ger':
            if is_forced_meta:
                if ger_forced_idx == -1:
                    ger_forced_idx = out_idx
            else:
                if ger_sub_idx == -1:
                    ger_sub_idx = out_idx
        elif new_lang == 'eng':
            if eng_sub_idx == -1:
                eng_sub_idx = out_idx

    ffmpeg_args.extend(["-map", "0:v:0"])
    ffmpeg_args.extend(["-default_mode", "infer_no_subs"])

    for i, (orig_idx, new_lang) in enumerate(mapped_audios):
        ffmpeg_args.extend(["-map", f"0:{orig_idx}"])
        ffmpeg_args.extend([f"-metadata:s:a:{i}", "title=", f"-metadata:s:a:{i}", f"language={new_lang}"])
        if has_ger_audio:
            is_default = "default" if i == ger_audio_idx else "0"
        else:
            is_default = "default" if i == eng_audio_idx else "0"
        ffmpeg_args.extend([f"-disposition:a:{i}", is_default])

        # Check if anything changed
        s = audio_streams[i][1]
        old_lang = s.get('tags', {}).get('language', 'und')
        old_disp = s.get('disposition', {})
        was_default = old_disp.get('default', 0) == 1
        if new_lang != old_lang or (is_default == "default") != was_default:
            needs_muxing = True

    for orig_idx, is_forced_meta, mapped_input, new_lang, clean_title, s, out_idx, is_hi in mapped_subs:
        ffmpeg_args.extend(["-map", mapped_input])
        ffmpeg_args.extend([f"-metadata:s:s:{out_idx}", f"title={clean_title}", f"-metadata:s:s:{out_idx}", f"language={new_lang}"])

        disp = []
        if is_hi:
            disp.append("hearing_impaired")
        if is_forced_meta:
            disp.append("forced")

        is_default = False
        if has_ger_audio:
            if out_idx == ger_forced_idx:
                is_default = True
        else:
            if ger_sub_idx != -1 or ger_forced_idx != -1:
                if out_idx == (ger_forced_idx if ger_forced_idx != -1 else ger_sub_idx):
                    is_default = True
            elif eng_sub_idx != -1:
                if out_idx == eng_sub_idx:
                    is_default = True

        if is_default:
            disp.append("default")

        disp_str = "+".join(disp) if disp else "0"
        ffmpeg_args.extend([f"-disposition:s:{out_idx}", disp_str])

        old_disp = s.get('disposition', {})
        was_default = old_disp.get('default', 0) == 1
        was_forced = old_disp.get('forced', 0) == 1
        was_hi = old_disp.get('hearing_impaired', 0) == 1
        if (is_default != was_default) or (is_forced_meta != was_forced) or (is_hi != was_hi):
            needs_muxing = True

    return needs_muxing

def _execute_muxing(
    filepath: str,
    ffmpeg_args: list,
    mapped_audios: list,
    final_subs: list,
    needs_ffmpeg: bool,
    progress_callback=None,
) -> None:
    """Execute the final muxing step — either fast mkvpropedit or full ffmpeg remux."""
    if progress_callback:
        progress_callback('muxing', 0, 'start')

    if not needs_ffmpeg:
        _execute_mkvpropedit(filepath, ffmpeg_args, mapped_audios, final_subs)
        return

    ffmpeg_args.extend(["-c", "copy"])
    temp_out = os.path.join(TEMP_DIR, "clean_" + os.path.basename(filepath))
    ffmpeg_args.append(temp_out)

    write_log(f"DEBUG: Running ffmpeg with args: {' '.join(ffmpeg_args)}")
    write_log("  -> Speichere aufgeräumte Datei (FFmpeg Remux)...")
    res = tracked_run(ffmpeg_args)
    if res.returncode == 0 and os.path.exists(temp_out):
        _apply_bcp47_fix(temp_out, mapped_audios, final_subs)

        success = False
        for attempt in range(5):
            try:
                if os.path.exists(filepath):
                    os.remove(filepath)
                shutil.move(temp_out, filepath)
                success = True
                break
            except Exception as e:
                time.sleep(2)

        if success:
            write_log("     Erfolgreich aktualisiert!")
        else:
            write_log(f"     FEHLER beim Ersetzen nach 5 Versuchen. Die Datei wird blockiert!")
        if progress_callback:
            progress_callback('muxing', 0, 'done')
    else:
        write_log("     FEHLER beim Muxen mit ffmpeg.")
        if os.path.exists(temp_out):
            os.remove(temp_out)
        if progress_callback:
            progress_callback('muxing', 0, 'done')

def _execute_mkvpropedit(
    filepath: str,
    ffmpeg_args: list,
    mapped_audios: list,
    final_subs: list,
) -> None:
    """Fast metadata update using mkvpropedit (no remux needed)."""
    write_log("  -> Schnelles Metadaten-Update (mkvpropedit)...")
    mkvprop_args = [MKVPROPEDIT, filepath]

    # Audio Tracks
    for i, (orig_idx, new_lang) in enumerate(mapped_audios):
        track_id = f"a{i+1}"
        try:
            is_default_flag = 1 if ffmpeg_args[ffmpeg_args.index(f"-disposition:a:{i}") + 1] == "default" else 0
        except (ValueError, IndexError):
            is_default_flag = 0
        legacy_lang = ISO_LEGACY_MAP.get(new_lang, new_lang)
        mkvprop_args.extend(["--edit", f"track:{track_id}", "--set", f"language={legacy_lang}", "--set", f"language-ietf={new_lang}", "--set", "name=", "--set", f"flag-default={is_default_flag}"])

    # Subtitle Tracks
    for j, (orig_idx, is_forced_meta, mapped_input, new_lang, clean_title, s, out_idx, is_hi) in enumerate(final_subs):
        track_id = f"s{j+1}"

        try:
            disp_str = ffmpeg_args[ffmpeg_args.index(f"-disposition:s:{out_idx}") + 1]
            is_default = 1 if "default" in disp_str else 0
            is_forced = 1 if "forced" in disp_str else 0
        except Exception:
            is_default = 0
            is_forced = 0

        legacy_lang = ISO_LEGACY_MAP.get(new_lang, new_lang)
        mkvprop_args.extend(["--edit", f"track:{track_id}", "--set", f"language={legacy_lang}", "--set", f"language-ietf={new_lang}", "--set", f"name={clean_title}"])
        mkvprop_args.extend(["--set", f"flag-hearing-impaired={1 if is_hi else 0}"])
        mkvprop_args.extend(["--set", f"flag-default={is_default}"])
        mkvprop_args.extend(["--set", f"flag-forced={is_forced}"])

    res = tracked_run(mkvprop_args, capture_output=True)
    if res.returncode == 0:
        write_log("     Erfolgreich aktualisiert!")
    else:
        write_log("     FEHLER beim Ausführen von mkvpropedit.")

def _apply_bcp47_fix(
    temp_out: str,
    mapped_audios: list,
    final_subs: list,
) -> None:
    """Apply BCP-47 language tags via mkvpropedit after FFmpeg remux."""
    mkvprop_args = [MKVPROPEDIT, temp_out]

    # Audio Tracks
    for i, (orig_idx, new_lang) in enumerate(mapped_audios):
        track_id = f"a{i+1}"
        legacy_lang = ISO_LEGACY_MAP.get(new_lang, new_lang)
        mkvprop_args.extend(["--edit", f"track:{track_id}", "--set", f"language={legacy_lang}", "--set", f"language-ietf={new_lang}", "--set", "name="])

    # Subtitle Tracks
    for j, (orig_idx, is_forced_meta, mapped_input, new_lang, clean_title, s, out_idx, is_hi) in enumerate(final_subs):
        track_id = f"s{j+1}"
        legacy_lang = ISO_LEGACY_MAP.get(new_lang, new_lang)
        mkvprop_args.extend(["--edit", f"track:{track_id}", "--set", f"language={legacy_lang}", "--set", f"language-ietf={new_lang}", "--set", f"name={clean_title}"])
        if is_hi:
            mkvprop_args.extend(["--set", "flag-hearing-impaired=1"])
        else:
            mkvprop_args.extend(["--set", "flag-hearing-impaired=0"])

    tracked_run(mkvprop_args)
