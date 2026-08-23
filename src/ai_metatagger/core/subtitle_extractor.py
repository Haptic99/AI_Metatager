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

def _extract_and_sync_subtitles(
    filepath: str,
    sub_streams: list,
    track_id_map: dict,
) -> dict:
    """Extract text subtitles and run ffsubsync in parallel.

    Args:
        filepath: Path to the MKV file.
        sub_streams: List of (stream_index, stream_dict) tuples for subtitles.
        track_id_map: Maps stream index to track number.

    Returns:
        dict mapping stream_index -> (success, offset, scale, duration).
    """
    sync_results = {}
    sync_tasks = []
    for idx, s in sub_streams:
        if s.get('codec_name') in ['subrip', 'ass']:
            movie_base = os.path.basename(filepath)
            out_sub = os.path.join(TEMP_DIR, f"{movie_base}_sub_{track_id_map[idx]}.srt")
            tracked_run(["ffmpeg", "-v", "quiet", "-y", "-i", filepath, "-map", f"0:{idx}", out_sub])
            if os.path.exists(out_sub):
                sync_tasks.append(idx)

    def do_sync(idx):
        movie_base = os.path.basename(filepath)
        out_sub = os.path.join(TEMP_DIR, f"{movie_base}_sub_{track_id_map[idx]}.srt")
        synced_sub = os.path.join(TEMP_DIR, f"{movie_base}_sub_{track_id_map[idx]}_synced.srt")
        start_t = time.time()
        success, offset, scale = auto_sync_subtitle(filepath, out_sub, synced_sub)
        return idx, success, offset, scale, time.time() - start_t

    if sync_tasks:
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(do_sync, idx) for idx in sync_tasks]
            for future in concurrent.futures.as_completed(futures):
                idx, success, offset, scale, dur = future.result()
                sync_results[idx] = (success, offset, scale, dur)

    return sync_results

def _process_subtitles(
    filepath: str,
    sub_streams: list,
    track_id_map: dict,
    sync_results: dict,
    duration: float,
    ffmpeg_args: list,
    input_files: list,
    progress_callback=None,
) -> tuple:
    """Analyse and process all subtitle streams.

    Returns:
        (mapped_subs, final_subs, synced_srt_paths, needs_muxing, needs_ffmpeg)
    """
    mapped_subs = []
    processed_subs = []
    synced_srt_paths = {}
    needs_muxing = False
    needs_ffmpeg = False

    ger_sub_idx = -1
    ger_forced_idx = -1
    eng_sub_idx = -1

    for idx, s in sub_streams:
        if progress_callback:
            progress_callback('subtitle', idx, 'start', s.get('codec_name', ''))
        tags = s.get('tags', {})
        old_lang = tags.get('language', 'und')
        old_title = tags.get('title', '')
        codec = s.get('codec_name')

        is_forced_meta = 'forced' in old_title.lower() or 'erzwungen' in old_title.lower()
        is_hi = False

        write_log(f"  -> Prüfe Untertitel Spur {idx} (Codec: {codec}, Lang: {old_lang}, Titel: '{old_title}')")

        new_lang = map_lang(old_lang, old_title)
        clean_title = get_clean_title(new_lang, codec, is_forced_meta)
        if new_lang != old_lang or clean_title != old_title or new_lang == 'und':
            needs_muxing = True

        extracted_text = ""
        line_count = 0
        mapped_input = f"0:{idx}"

        if codec in ['subrip', 'ass']:
            movie_base = os.path.basename(filepath)
            out_sub = os.path.join(TEMP_DIR, f"{movie_base}_sub_{track_id_map[idx]}.srt")
            synced_sub = os.path.join(TEMP_DIR, f"{movie_base}_sub_{track_id_map[idx]}_synced.srt")

            if idx in sync_results:
                sync_success, sync_offset, sync_scale, dur = sync_results[idx]
                if sync_success:
                    sync_msg = f"     => Auto-Sync erfolgreich! (Verschiebung: {sync_offset}s"
                    if sync_scale != "1.000" and sync_scale != "1.0":
                        sync_msg += f", Speed: {sync_scale}x"
                    sync_msg += f", Dauer: {dur:.1f}s). Ersetze Spur {idx}."
                    write_log(sync_msg, log_type="sync")
                    try:
                        if abs(float(sync_offset)) > CONFIG.get("sync_offset_threshold", 2.0) or (sync_scale != "1.000" and sync_scale != "1.0"):
                            write_review(f"[{os.path.basename(filepath)}] Auto-Sync Spur {idx}: Große Verschiebung ({sync_offset}s, Speed: {sync_scale}x)")
                    except Exception as e:
                        write_log(f"Warnung in {__name__}: {e}")
                    needs_muxing = True
                    needs_ffmpeg = True
                    extracted_text, line_count = read_text_subtitle(synced_sub)
                    is_hi = is_hearing_impaired(extracted_text, line_count)
                    input_idx = len(input_files)
                    input_files.append(synced_sub)
                    ffmpeg_args.extend(["-i", synced_sub])
                    mapped_input = f"{input_idx}:0"
                    synced_srt_paths[idx] = synced_sub
                else:
                    extracted_text, line_count = read_text_subtitle(out_sub)
                    is_hi = is_hearing_impaired(extracted_text, line_count)
                    synced_srt_paths[idx] = out_sub

                if is_forced_meta and line_count > 120:
                    is_forced_meta = False
                    write_log(f"     => FAKE FORCED ERKANNT! ({line_count} Zeilen). Entferne Forced-Tag.", log_type="korrektur")
                    if line_count < CONFIG.get("fake_forced_line_threshold", 500):
                        write_review(f"[{os.path.basename(filepath)}] Spur {idx}: Forced-Tag entfernt ({line_count} Zeilen). Prüfen ob echter Forced (viel Fremdsprache)!")
                elif line_count > 0 and line_count < 60 and not is_forced_meta:
                    write_log(f"     => FORCED ERKANNT ({line_count} Zeilen). Setze Forced-Tag.")
                    is_forced_meta = True

                if extracted_text:
                    _detect_subtitle_language(filepath, idx, extracted_text, old_title, new_lang)
                    # Re-check new_lang after detection (detect may update via side-effect)
                    # NOTE: We re-run detection inline here to get the updated lang
                    start_t = time.time()
                    try:
                        res = detect_langs(extracted_text[:1500].replace("\n", " "))
                        dur = time.time() - start_t
                        if res:
                            det_lang = map_lang(res[0].lang, old_title)
                            conf = res[0].prob * 100
                            if det_lang != 'und':
                                if not is_same_lang_family(det_lang, new_lang):
                                    write_log(f"     => Text KI Korrektur: War '{new_lang}', ist jetzt '{det_lang}' (Sicherheit: {conf:.1f}%, Dauer: {dur:.1f}s)", log_type="korrektur")
                                    new_lang = det_lang
                                else:
                                    write_log(f"     => Text KI Bestätigt: '{det_lang}' (Sicherheit: {conf:.1f}%, Dauer: {dur:.1f}s)", log_type="korrektur")

                                expected = CONFIG.get("expected_langs", [])
                                if conf < CONFIG.get("confidence_threshold", 75.0):
                                    write_review(f"[{os.path.basename(filepath)}] Spur {idx} (Text): KI sehr unsicher ({conf:.1f}% für '{det_lang}')")
                                elif det_lang not in expected and det_lang != 'und':
                                    write_review(f"[{os.path.basename(filepath)}] Spur {idx} (Text): Exotische Sprache erkannt ('{det_lang}')")
                    except Exception as e:
                        write_log(f"Warnung in {__name__}: {e}")

        else:
            start_t = time.time()
            detected_pgs_lang, is_forced_meta, conf, is_hi = analyze_subtitle_pgs(
                filepath, idx, track_id_map[idx], codec, duration, is_forced_meta, old_lang, old_title, progress_callback
            )
            if progress_callback and progress_callback('subtitle', idx, 'step', codec, 0, 1):
                return mapped_subs, [], synced_srt_paths, needs_muxing, needs_ffmpeg
            dur = time.time() - start_t
            if detected_pgs_lang != 'und':
                if not is_same_lang_family(detected_pgs_lang, new_lang):
                    tl = str(old_title).lower()
                    if ('french' in tl or 'fran' in tl) and new_lang == 'fre':
                        write_log(f"     => OCR KI Erkennung '{detected_pgs_lang}' ignoriert, da Titel auf 'fre' hindeutet.", log_type="korrektur")
                    else:
                        write_log(f"     => OCR KI Korrektur: War '{new_lang}', ist jetzt '{detected_pgs_lang}' (Sicherheit: {conf}, Dauer: {dur:.1f}s)", log_type="korrektur")
                        new_lang = detected_pgs_lang
                else:
                    write_log(f"     => OCR KI Bestätigt: '{detected_pgs_lang}' (Sicherheit: {conf}, Dauer: {dur:.1f}s)", log_type="korrektur")

                try:
                    c_val = float(str(conf).replace('%', ''))
                    expected = CONFIG.get("expected_langs", [])
                    if c_val < CONFIG.get("confidence_threshold", 75.0):
                        write_review(f"[{os.path.basename(filepath)}] Spur {idx} (Bild): KI sehr unsicher ({c_val:.1f}% für '{detected_pgs_lang}')")
                    elif detected_pgs_lang not in expected and detected_pgs_lang != 'und':
                        write_review(f"[{os.path.basename(filepath)}] Spur {idx} (Bild): Exotische Sprache erkannt ('{detected_pgs_lang}')")
                except Exception as e:
                    write_log(f"Warnung in {__name__}: {e}")

        # Duplicate detection
        is_dup = False
        for p_lang, p_text in processed_subs:
            if p_lang == new_lang and is_duplicate_text(extracted_text, p_text):
                is_dup = True
                break
        if is_dup:
            write_log(f"     => DUPLIKAT ERKANNT! Spur {idx} ist identisch zu einer vorherigen Spur. (Wird vorerst nicht gelöscht)")
            needs_muxing = True

        processed_subs.append((new_lang, extracted_text))

        clean_title = get_clean_title(new_lang, codec, is_forced_meta)
        if new_lang != old_lang or clean_title != old_title:
            needs_muxing = True

        out_idx = len(mapped_subs)

        if codec in ['hdmv_pgs_subtitle', 'dvd_subtitle']:
            has_text = False
            for p_lang, p_text in processed_subs[:-1]:
                if p_lang == new_lang and len(p_text) > 50:
                    has_text = True
                    break
            if has_text:
                write_log(f"     => BILD-UNTERTITEL (Spur {idx}): Text-Alternative ({new_lang}) vorhanden! (Wird vorerst nicht gelöscht)")
                needs_muxing = True

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

        mapped_subs.append((idx, is_forced_meta, mapped_input, new_lang, clean_title, s, out_idx, is_hi))
        if progress_callback:
            progress_callback('subtitle', idx, 'done', s.get('codec_name', ''))

    # --- Filter image subtitles ---
    final_subs = []
    for sub in mapped_subs:
        orig_idx, is_forced_meta, mapped_input, new_lang, clean_title, s, _, is_hi = sub
        codec = s.get('codec_name')
        is_bild = codec in ['hdmv_pgs_subtitle', 'dvd_subtitle', 'dvdsub', 'pgssub']

        if is_bild:
            has_text = any(
                o_s.get('codec_name') not in ['hdmv_pgs_subtitle', 'dvd_subtitle', 'dvdsub', 'pgssub']
                and o_lang == new_lang
                and o_forced == is_forced_meta
                for (_, o_forced, _, o_lang, _, o_s, _, _) in mapped_subs
            )
            if has_text:
                write_log(f"     => BILD-UNTERTITEL (Spur {orig_idx}): Text-Alternative ({new_lang}) vorhanden! (Wird vorerst nicht gelöscht)")
                needs_muxing = True

        final_subs.append(sub)

    # Rebuild mapped_subs with updated indices
    mapped_subs = []
    ger_sub_idx = -1
    ger_forced_idx = -1
    eng_sub_idx = -1

    for orig_idx, is_forced_meta, mapped_input, new_lang, clean_title, s, _, is_hi in final_subs:
        out_idx = len(mapped_subs)
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

        mapped_subs.append((orig_idx, is_forced_meta, mapped_input, new_lang, clean_title, s, out_idx, is_hi))

    return mapped_subs, final_subs, synced_srt_paths, needs_muxing, needs_ffmpeg

def _detect_subtitle_language(filepath: str, idx: int, text: str, old_title: str, current_lang: str) -> None:
    """Log-only helper for subtitle language detection — actual detection happens inline."""
    # This is a placeholder for future refactoring where detection could be fully
    # extracted. Currently the inline detection in _process_subtitles modifies
    # new_lang directly, so extraction requires more structural changes.
    pass
