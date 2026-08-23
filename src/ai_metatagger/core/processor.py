import os
import sys
import time
import datetime
import shutil
import re
import subprocess
import json
import concurrent.futures

from ai_metatagger.core.logger import write_log, write_review
from ai_metatagger.core.ffmpeg_tools import get_streams
from ai_metatagger.core.subtitle_tools import is_same_lang_family, is_hearing_impaired, map_lang, get_clean_title, is_duplicate_text, read_text_subtitle, auto_sync_subtitle
from ai_metatagger.core.audio_analyzer import detect_audio_language_whisper
import ai_metatagger.core.audio_analyzer as audio_analyzer
from ai_metatagger.core.ocr_analyzer import analyze_subtitle_pgs
import ai_metatagger.core.ocr_analyzer as ocr_analyzer


from ai_metatagger.config import DATA_DIR, DIR_SERIEN, TESSERACT_PATH, FFSUBSYNC_PATH, MKVPROPEDIT, CONFIG, TEMP_DIR

if os.name == 'nt':
    class NoWindowPopen(subprocess.Popen):
        def __init__(self, *args, **kwargs):
            kwargs.setdefault('creationflags', 0x08000000)
            super().__init__(*args, **kwargs)
    subprocess.Popen = NoWindowPopen

import pytesseract
from langdetect import detect, detect_langs, DetectorFactory
import difflib
import whisper
import srt
from collections import Counter
import warnings

warnings.filterwarnings("ignore")

DetectorFactory.seed = 0

if os.path.exists(TESSERACT_PATH):
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH

MEDIA_DIR = DIR_SERIEN

LOG_PATH = os.path.join(DATA_DIR, "Master_Cleanup_Log.txt")
REVIEW_LOG = os.path.join(DATA_DIR, "Bitte_Pruefen.txt")

def process_file(filepath, progress_callback=None):
    write_log(f"\n--- Analysiere V5: {filepath} ---")
    
    base, ext = os.path.splitext(filepath)
    ext = ext.lower()
    
    if ext in ['.mp4', '.avi', '.m4v']:
        write_log(f"  -> Konvertiere {ext} in .mkv Container...")
        new_filepath = base + ".mkv"
        cmd = ["ffmpeg", "-v", "quiet", "-y", "-i", filepath, "-c", "copy", "-map", "0", new_filepath]
        res = subprocess.run(cmd)
        if res.returncode == 0 and os.path.exists(new_filepath):
            os.remove(filepath)
            filepath = new_filepath
            write_log("     Erfolgreich konvertiert.")
        else: return

    streams = get_streams(filepath)
    if not streams: return

    duration = 0
    for s in streams:
        if s.get('codec_type') == 'video':
            duration = s.get('duration', s.get('tags', {}).get('DURATION', '0'))
            if ':' in str(duration): 
                parts = str(duration).split(':')
                duration = float(parts[0])*3600 + float(parts[1])*60 + float(parts[2][:2])
            else:
                try: duration = float(duration)
                except ValueError: duration = 0
            break

    non_video_streams = [s for s in streams if s.get('codec_type') != 'video']
    track_id_map = {s.get('index'): tid for tid, s in enumerate(non_video_streams, start=1)}

    audio_streams = []
    sub_streams = []
    for i, s in enumerate(streams):
        if s.get('codec_type') == 'audio': audio_streams.append((i, s))
        elif s.get('codec_type') == 'subtitle': sub_streams.append((i, s))

    ffmpeg_args = ["ffmpeg", "-v", "quiet", "-y", "-i", filepath]
    input_files = [filepath]
    needs_muxing = False
    needs_ffmpeg = False
    
    mapped_subs = []
    processed_subs = []
    synced_srt_paths = {}
    
    ger_sub_idx = -1
    ger_forced_idx = -1
    eng_sub_idx = -1


    # PRE-PASS: Parallel extraction and sync
    sync_results = {}
    sync_tasks = []
    for idx, s in sub_streams:
        if s.get('codec_name') in ['subrip', 'ass']:
            movie_base = os.path.basename(filepath)
            out_sub = os.path.join(TEMP_DIR, f"{movie_base}_sub_{track_id_map[idx]}.srt")
            subprocess.run(["ffmpeg", "-v", "quiet", "-y", "-i", filepath, "-map", f"0:{idx}", out_sub])
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

    # 1. PROCESS SUBTITLES FIRST
    for idx, s in sub_streams:
        if progress_callback: progress_callback('subtitle', idx, 'start', s.get('codec_name', ''))
        tags = s.get('tags', {})
        old_lang = tags.get('language', 'und')
        old_title = tags.get('title', '')
        codec = s.get('codec_name')
        
        is_forced_meta = 'forced' in old_title.lower() or 'erzwungen' in old_title.lower()
        is_hi = False
        
        write_log(f"  -> PrÃ¼fe Untertitel Spur {idx} (Codec: {codec}, Lang: {old_lang}, Titel: '{old_title}')")
        
        new_lang = map_lang(old_lang, old_title)
        clean_title = get_clean_title(new_lang, codec, is_forced_meta)
        if new_lang != old_lang or clean_title != old_title or new_lang == 'und': needs_muxing = True
        
        extracted_text = ""
        mapped_input = f"0:{idx}"
        
        if codec in ['subrip', 'ass']:
            movie_base = os.path.basename(filepath)
            out_sub = os.path.join(TEMP_DIR, f"{movie_base}_sub_{track_id_map[idx]}.srt")
            movie_base = os.path.basename(filepath)
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
                            write_review(f"[{os.path.basename(filepath)}] Auto-Sync Spur {idx}: GroÃŸe Verschiebung ({sync_offset}s, Speed: {sync_scale}x)")
                    except Exception as e: write_log(f"Warnung in {__name__}: {e}")
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
                        write_review(f"[{os.path.basename(filepath)}] Spur {idx}: Forced-Tag entfernt ({line_count} Zeilen). PrÃ¼fen ob echter Forced (viel Fremdsprache)!")
                elif line_count > 0 and line_count < 60 and not is_forced_meta:
                    write_log(f"     => FORCED ERKANNT ({line_count} Zeilen). Setze Forced-Tag.")
                    is_forced_meta = True
                    
                if extracted_text:
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
                                    write_log(f"     => Text KI BestÃ¤tigt: '{det_lang}' (Sicherheit: {conf:.1f}%, Dauer: {dur:.1f}s)", log_type="korrektur")
                                
                                expected = CONFIG.get("expected_langs", [])
                                if conf < CONFIG.get("confidence_threshold", 75.0):
                                    write_review(f"[{os.path.basename(filepath)}] Spur {idx} (Text): KI sehr unsicher ({conf:.1f}% fÃ¼r '{det_lang}')")
                                elif det_lang not in expected and det_lang != 'und':
                                    write_review(f"[{os.path.basename(filepath)}] Spur {idx} (Text): Exotische Sprache erkannt ('{det_lang}')")
                    except Exception as e: write_log(f"Warnung in {__name__}: {e}")
                    
        else:
            start_t = time.time()
            detected_pgs_lang, is_forced_meta, conf, is_hi = analyze_subtitle_pgs(filepath, idx, track_id_map[idx], codec, duration, is_forced_meta, old_lang, old_title, progress_callback)
            if progress_callback and progress_callback('subtitle', idx, 'step', codec, 0, 1): return
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
                    write_log(f"     => OCR KI BestÃ¤tigt: '{detected_pgs_lang}' (Sicherheit: {conf}, Dauer: {dur:.1f}s)", log_type="korrektur")
                
                try:
                    c_val = float(str(conf).replace('%',''))
                    expected = CONFIG.get("expected_langs", [])
                    if c_val < CONFIG.get("confidence_threshold", 75.0):
                        write_review(f"[{os.path.basename(filepath)}] Spur {idx} (Bild): KI sehr unsicher ({c_val:.1f}% fÃ¼r '{detected_pgs_lang}')")
                    elif detected_pgs_lang not in expected and detected_pgs_lang != 'und':
                        write_review(f"[{os.path.basename(filepath)}] Spur {idx} (Bild): Exotische Sprache erkannt ('{detected_pgs_lang}')")
                except Exception as e: write_log(f"Warnung in {__name__}: {e}")
                    
        is_dup = False
        for p_lang, p_text in processed_subs:
            if p_lang == new_lang and is_duplicate_text(extracted_text, p_text):
                is_dup = True
                break
        if is_dup:
            write_log(f"     => DUPLIKAT ERKANNT! Spur {idx} ist identisch zu einer vorherigen Spur. (Wird vorerst nicht gelÃ¶scht)")
            needs_muxing = True
            # continue 
            
        processed_subs.append((new_lang, extracted_text))
        
        clean_title = get_clean_title(new_lang, codec, is_forced_meta)
        if new_lang != old_lang or clean_title != old_title: needs_muxing = True
        
        out_idx = len(mapped_subs)
        
        if codec in ['hdmv_pgs_subtitle', 'dvd_subtitle']:
            has_text = False
            for p_lang, p_text in processed_subs[:-1]:
                if p_lang == new_lang and len(p_text) > 50:
                    has_text = True
                    break
            if has_text:
                write_log(f"     => BILD-UNTERTITEL (Spur {idx}): Text-Alternative ({new_lang}) vorhanden! (Wird vorerst nicht gelÃ¶scht)")
                needs_muxing = True
                # continue
                
        if new_lang == 'ger':
            if is_forced_meta:
                if ger_forced_idx == -1: ger_forced_idx = out_idx
            else:
                if ger_sub_idx == -1: ger_sub_idx = out_idx
        elif new_lang == 'eng':
            if eng_sub_idx == -1: eng_sub_idx = out_idx
            
        mapped_subs.append((idx, is_forced_meta, mapped_input, new_lang, clean_title, s, out_idx, is_hi))
        if progress_callback: progress_callback('subtitle', idx, 'done', s.get('codec_name', ''))

    # --- BILD-UNTERTITEL FILTERN ---
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
                write_log(f"     => BILD-UNTERTITEL (Spur {orig_idx}): Text-Alternative ({new_lang}) vorhanden! (Wird vorerst nicht gelÃ¶scht)")
                needs_muxing = True
                # Heuristik: PGS mit Text-Alternative in gleicher Sprache = SDH
                
        final_subs.append(sub)

    mapped_subs = []
    ger_sub_idx = -1
    ger_forced_idx = -1
    eng_sub_idx = -1
    
    for orig_idx, is_forced_meta, mapped_input, new_lang, clean_title, s, _, is_hi in final_subs:
        out_idx = len(mapped_subs)
        if new_lang == 'ger':
            if is_forced_meta:
                if ger_forced_idx == -1: ger_forced_idx = out_idx
            else:
                if ger_sub_idx == -1: ger_sub_idx = out_idx
        elif new_lang == 'eng':
            if eng_sub_idx == -1: eng_sub_idx = out_idx
            
        mapped_subs.append((orig_idx, is_forced_meta, mapped_input, new_lang, clean_title, s, out_idx, is_hi))

    # 2. PROCESS AUDIO
    mapped_audios = []
    ger_audio_idx = -1
    eng_audio_idx = -1
    has_ger_audio = False
    
    best_srt = None
    if synced_srt_paths:
        largest_srt = max(synced_srt_paths.values(), key=lambda p: os.path.getsize(p) if os.path.exists(p) else 0)
        if os.path.exists(largest_srt) and os.path.getsize(largest_srt) > 20000:
            best_srt = largest_srt
        
    for idx, s in audio_streams:
        if progress_callback: progress_callback('audio', idx, 'start')
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
                write_log(f"     => Audio KI BestÃ¤tigt: '{detected}' (Sicherheit: {conf}, Dauer: {dur:.1f}s)", log_type="korrektur")
            
            try:
                c_val = float(str(conf).replace('%',''))
                expected = CONFIG.get("expected_langs", [])
                if c_val < CONFIG.get("confidence_threshold", 75.0):
                    write_review(f"[{os.path.basename(filepath)}] Spur {idx} (Audio): KI sehr unsicher ({c_val:.1f}% fÃ¼r '{detected}')")
                elif detected not in expected and detected != 'und':
                    write_review(f"[{os.path.basename(filepath)}] Spur {idx} (Audio): Exotische Sprache erkannt ('{detected}')")
            except Exception as e: write_log(f"Warnung in {__name__}: {e}")
                
        if new_lang != old_lang or old_title: needs_muxing = True
            
        if new_lang == 'ger': has_ger_audio = True
            
        mapped_audios.append((idx, new_lang))
        if progress_callback: progress_callback('audio', idx, 'done')
        
    for i, (orig_idx, new_lang) in enumerate(mapped_audios):
        if new_lang == 'ger' and ger_audio_idx == -1: ger_audio_idx = i
        if new_lang == 'eng' and eng_audio_idx == -1: eng_audio_idx = i

    # 3. MUXING SETUP
    ffmpeg_args.extend(["-map", "0:v:0"])
    ffmpeg_args.extend(["-default_mode", "infer_no_subs"])
    
    for i, (orig_idx, new_lang) in enumerate(mapped_audios):
        ffmpeg_args.extend(["-map", f"0:{orig_idx}"])
        ffmpeg_args.extend([f"-metadata:s:a:{i}", "title=", f"-metadata:s:a:{i}", f"language={new_lang}"])
        if has_ger_audio: is_default = "default" if i == ger_audio_idx else "0"
        else: is_default = "default" if i == eng_audio_idx else "0"
        ffmpeg_args.extend([f"-disposition:a:{i}", is_default])
        
        # Check if anything changed
        s = audio_streams[i][1]
        old_lang = s.get('tags', {}).get('language', 'und')
        old_disp = s.get('disposition', {})
        was_default = old_disp.get('default', 0) == 1
        if new_lang != old_lang or (is_default == "default") != was_default:
            needs_muxing = True
        print(f"DEBUG: new_lang={new_lang}, old_lang={old_lang}, is_default={is_default}, was_default={was_default}, needs_muxing={needs_muxing}")
        
    for orig_idx, is_forced_meta, mapped_input, new_lang, clean_title, s, out_idx, is_hi in mapped_subs:
        ffmpeg_args.extend(["-map", mapped_input])
        ffmpeg_args.extend([f"-metadata:s:s:{out_idx}", f"title={clean_title}", f"-metadata:s:s:{out_idx}", f"language={new_lang}"])
        
        disp = []
        if is_hi: disp.append("hearing_impaired")
        if is_forced_meta: disp.append("forced")
            
        is_default = False
        if has_ger_audio:
            if out_idx == ger_forced_idx: is_default = True
        else:
            if ger_sub_idx != -1 or ger_forced_idx != -1:
                if out_idx == (ger_forced_idx if ger_forced_idx != -1 else ger_sub_idx): is_default = True
            elif eng_sub_idx != -1:
                if out_idx == eng_sub_idx: is_default = True
                    
        if is_default: disp.append("default")
        
        disp_str = "+".join(disp) if disp else "0"
        ffmpeg_args.extend([f"-disposition:s:{out_idx}", disp_str])
        
        old_disp = s.get('disposition', {})
        was_default = old_disp.get('default', 0) == 1
        was_forced = old_disp.get('forced', 0) == 1
        was_hi = old_disp.get('hearing_impaired', 0) == 1
        if (is_default != was_default) or (is_forced_meta != was_forced) or (is_hi != was_hi):
            needs_muxing = True

    if not needs_muxing:
        write_log("  -> Datei ist bereits perfekt aufgerÃ¤umt und formatiert.")
        return

    if progress_callback: progress_callback('muxing', 0, 'start')
    if not needs_ffmpeg:
        write_log("  -> Schnelles Metadaten-Update (mkvpropedit)...")
        mkvprop_args = [MKVPROPEDIT, filepath]
        
        # Audio Tracks
        for i, (orig_idx, new_lang) in enumerate(mapped_audios):
            track_id = f"a{i+1}"
            try:
                is_default_flag = 1 if ffmpeg_args[ffmpeg_args.index(f"-disposition:a:{i}")+1] == "default" else 0
            except (ValueError, IndexError):
                is_default_flag = 0
            iso_map = {'zh-Hans': 'chi', 'zh-Hant': 'chi', 'pt-BR': 'por', 'pt-PT': 'por', 'es-ES': 'spa', 'es-419': 'spa', 'fr-CA': 'fre'}
            legacy_lang = iso_map.get(new_lang, new_lang)
            mkvprop_args.extend(["--edit", f"track:{track_id}", "--set", f"language={legacy_lang}", "--set", f"language-ietf={new_lang}", "--set", "name=", "--set", f"flag-default={is_default_flag}"])
            
        # Subtitle Tracks
        for j, (orig_idx, is_forced_meta, mapped_input, new_lang, clean_title, s, out_idx, is_hi) in enumerate(final_subs):
            track_id = f"s{j+1}"
            
            try:
                disp_str = ffmpeg_args[ffmpeg_args.index(f"-disposition:s:{out_idx}")+1]
                is_default = 1 if "default" in disp_str else 0
                is_forced = 1 if "forced" in disp_str else 0
            except Exception:
                is_default = 0
                is_forced = 0
            
            iso_map = {'zh-Hans': 'chi', 'zh-Hant': 'chi', 'pt-BR': 'por', 'pt-PT': 'por', 'es-ES': 'spa', 'es-419': 'spa', 'fr-CA': 'fre'}
            legacy_lang = iso_map.get(new_lang, new_lang)
            mkvprop_args.extend(["--edit", f"track:{track_id}", "--set", f"language={legacy_lang}", "--set", f"language-ietf={new_lang}", "--set", f"name={clean_title}"])
            mkvprop_args.extend(["--set", f"flag-hearing-impaired={1 if is_hi else 0}"])
            mkvprop_args.extend(["--set", f"flag-default={is_default}"])
            mkvprop_args.extend(["--set", f"flag-forced={is_forced}"])
            
        res = subprocess.run(mkvprop_args, capture_output=True)
        if res.returncode == 0:
            write_log("     Erfolgreich aktualisiert!")
        else:
            write_log("     FEHLER beim AusfÃ¼hren von mkvpropedit.")
        return

    ffmpeg_args.extend(["-c", "copy"])
    
    temp_out = os.path.join(TEMP_DIR, "clean_" + os.path.basename(filepath))
    ffmpeg_args.append(temp_out)
    
    write_log(f"DEBUG: Running ffmpeg with args: {' '.join(ffmpeg_args)}")
    write_log("  -> Speichere aufgerÃ¤umte Datei (FFmpeg Remux)...")
    res = subprocess.run(ffmpeg_args)
    if res.returncode == 0 and os.path.exists(temp_out):
        
        # --- MKVPROPEDIT BCP-47 FIX ---
        mkvprop_args = [MKVPROPEDIT, temp_out]
        
        # Audio Tracks
        for i, (orig_idx, new_lang) in enumerate(mapped_audios):
            track_id = f"a{i+1}"
            iso_map = {'zh-Hans': 'chi', 'zh-Hant': 'chi', 'pt-BR': 'por', 'pt-PT': 'por', 'es-ES': 'spa', 'es-419': 'spa', 'fr-CA': 'fre'}
            legacy_lang = iso_map.get(new_lang, new_lang)
            mkvprop_args.extend(["--edit", f"track:{track_id}", "--set", f"language={legacy_lang}", "--set", f"language-ietf={new_lang}", "--set", "name="])
            
        # Subtitle Tracks
        for j, (orig_idx, is_forced_meta, mapped_input, new_lang, clean_title, s, out_idx, is_hi) in enumerate(final_subs):
            track_id = f"s{j+1}"
            iso_map = {'zh-Hans': 'chi', 'zh-Hant': 'chi', 'pt-BR': 'por', 'pt-PT': 'por', 'es-ES': 'spa', 'es-419': 'spa', 'fr-CA': 'fre'}
            legacy_lang = iso_map.get(new_lang, new_lang)
            mkvprop_args.extend(["--edit", f"track:{track_id}", "--set", f"language={legacy_lang}", "--set", f"language-ietf={new_lang}", "--set", f"name={clean_title}"])
            if is_hi:
                mkvprop_args.extend(["--set", "flag-hearing-impaired=1"])
            else:
                mkvprop_args.extend(["--set", "flag-hearing-impaired=0"])
            
        subprocess.run(mkvprop_args)
        # ------------------------------

        success = False
        for attempt in range(5):
            try:
                if os.path.exists(filepath): os.remove(filepath)
                shutil.move(temp_out, filepath)
                success = True
                break
            except Exception as e:
                 time.sleep(2)
                
        if success:
            write_log("     Erfolgreich aktualisiert!")
        else:
            write_log(f"     FEHLER beim Ersetzen nach 5 Versuchen. Die Datei wird blockiert!")
        if progress_callback: progress_callback('muxing', 0, 'done')
    else:
        write_log("     FEHLER beim Muxen mit ffmpeg.")
        if os.path.exists(temp_out): os.remove(temp_out)
        if progress_callback: progress_callback('muxing', 0, 'done')

def main():
    target_dir = sys.argv[1] if len(sys.argv) > 1 else MEDIA_DIR
    
    write_log("=========================================")
    write_log(f"STARTE MASTER CLEANUP V5 (Ziel: {target_dir})")
    write_log("=========================================")
    
    for root, dirs, files in os.walk(target_dir):
        for f in files:
            if f.endswith(('.mp4', '.mkv', '.avi', '.m4v')):
                process_file(os.path.join(root, f))
                
    write_log("=========================================")
    write_log("MASTER CLEANUP V5 BEENDET")
    write_log("=========================================")

if __name__ == "__main__":
    main()
