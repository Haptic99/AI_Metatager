import os
import sys
import time
import datetime
import shutil
import re
import subprocess
import json

# Lade Konfiguration
CONFIG_PATH = r"F:\Jellyfin_AI_Cockpit\config.json"
try:
    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        CONFIG = json.load(f)
except:
    CONFIG = {}

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

TESSERACT_PATH = r"C:\Users\dmart\AppData\Local\Programs\Tesseract-OCR\tesseract.exe"
if os.path.exists(TESSERACT_PATH):
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH

MEDIA_DIR = r"F:\Jellyfin\Serien"
TEMP_DIR = r"F:\Jellyfin_AI_Cockpit\temp_cleanup"
if not os.path.exists(TEMP_DIR):
    os.makedirs(TEMP_DIR)

LOG_PATH = r"F:\Jellyfin_AI_Cockpit\Daten\Master_Cleanup_Log.txt"
REVIEW_LOG = r"F:\Jellyfin_AI_Cockpit\Daten\Bitte_Pruefen.txt"

def write_review(msg):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    formatted_msg = f"[{timestamp}] {msg}"
    try:
        with open(REVIEW_LOG, 'a', encoding='utf-8') as f:
            f.write(formatted_msg + "\n")
    except: pass
KORREKTUR_LOG = r"F:\Jellyfin_AI_Cockpit\Daten\Master_Korrektur_Log.txt"
SYNC_LOG = r"F:\Jellyfin_AI_Cockpit\Daten\Master_Sync_Log.txt"
FFSUBSYNC_PATH = r"C:\Users\dmart\AppData\Roaming\Python\Python313\Scripts\ffsubsync.exe"

def write_log(msg, console=True, log_type="cleanup"):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    formatted_msg = f"[{timestamp}] {msg}" if log_type != "cleanup" else msg
    
    try:
        with open(LOG_PATH, 'a', encoding='utf-8') as f:
            f.write(formatted_msg + "\n")
    except: pass
        
    if console:
        print(str(msg).encode(sys.stdout.encoding, errors='replace').decode(sys.stdout.encoding))

def get_streams(filepath):
    cmd = ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams", filepath]
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='replace')
        if res.returncode != 0: return []
        data = json.loads(res.stdout)
        return data.get('streams', [])
    except: return []

def is_same_lang_family(lang1, lang2):
    if not lang1 or not lang2: return False
    l1 = lang1.lower()
    l2 = lang2.lower()
    if l1 == l2: return True
    
    # Check map_lang equality
    m1 = map_lang(l1)
    m2 = map_lang(l2)
    if m1 == m2: return True
    
    # Hardcoded macro-language mappings
    macros = {
        'pt': 'por',
        'es': 'spa',
        'zh': 'chi',
        'en': 'eng',
        'de': 'ger',
        'fr': 'fre',
        'zh-hans': 'chi',
        'zh-hant': 'chi',
    }
    
    # If one starts with a prefix and the other is the macro
    for prefix, macro in macros.items():
        if (l1.startswith(prefix) and l2 == macro) or (l2.startswith(prefix) and l1 == macro):
            return True
            
    return False

def is_same_lang_family(lang1, lang2):
    if lang1 == lang2: return True
    # If one is a dialect of the other (e.g., pt-br vs por)
    # lang1 = pt-br, lang2 = por
    # map_lang('pt-br') -> 'por' ?
    # Let's map both to 3 letters
    m1 = map_lang(lang1)
    m2 = map_lang(lang2)
    if m1 == m2: return True
    
    if lang1.startswith(lang2[:2]) or lang2.startswith(lang1[:2]): 
        # pt-br vs pt
        if lang1[:2] in ['pt', 'es', 'zh', 'en', 'de', 'fr']:
            return True
            
    return False

def map_lang(lang_str, title_str=""):
    if not lang_str: return 'und'
    lang_str = lang_str.lower()
    title_str = title_str.lower()
    
    if title_str == 'chs' or 'simplified' in title_str or 'vereinfacht' in title_str or 'zh-cn' in lang_str:
        return 'zh-Hans'
    if title_str == 'cht' or 'traditional' in title_str or 'traditionell' in title_str or 'zh-tw' in lang_str:
        return 'zh-Hant'
        
    if 'ger' in lang_str or 'deu' in lang_str or 'de' == lang_str: return 'ger'
    if 'eng' in lang_str or 'en' == lang_str: return 'eng'
    if 'spa' in lang_str or 'es' == lang_str or 'ca' == lang_str: return 'spa'
    if 'fre' in lang_str or 'fra' in lang_str or 'fr' == lang_str: return 'fre'
    if 'chi' in lang_str or 'zho' in lang_str: return 'chi'
    
    # 2-letter to 3-letter mappings for KI outputs
    map_2_to_3 = CONFIG.get('map_2_to_3', {})
    if lang_str in map_2_to_3: return map_2_to_3[lang_str]
    
    return lang_str

def get_clean_title(new_lang, codec, is_forced):
    if new_lang == 'zh-Hans': return "Vereinfachtes Chinesisch"
    if new_lang == 'zh-Hant': return "Traditionelles Chinesisch"
    return ""

def is_duplicate_text(text1, text2):
    if not text1 or not text2: return False
    if len(text1) == 0 or len(text2) == 0: return False
    ratio = difflib.SequenceMatcher(None, text1[:2000], text2[:2000]).ratio()
    return ratio > 0.90

def read_text_subtitle(filepath):
    full_text = ""
    line_count = 0
    if os.path.exists(filepath):
        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
            text_lines = [l.strip() for l in lines if l.strip() and not l.strip().isdigit() and '-->' not in l]
            full_text = "\n".join(text_lines)
            line_count = len(text_lines)
        except: pass
    return full_text, line_count

def auto_sync_subtitle(video_path, sub_path, out_path):
    if not os.path.exists(FFSUBSYNC_PATH):
        return False, "0.0", "1.0"
    cmd = [FFSUBSYNC_PATH, video_path, "-i", sub_path, "-o", out_path]
    try:
        write_log(f"       Starte ffsubsync (KI-AutoSync) fÃ¼r Spur...", console=False)
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='replace')
        if res.returncode == 0 and os.path.exists(out_path) and os.path.getsize(out_path) > 0:
            out_text = res.stdout + res.stderr
            offset_match = re.search(r"offset seconds:\s*([\-\d\.]+)", out_text)
            scale_match = re.search(r"scale factor:\s*([\-\d\.]+)", out_text)
            offset = offset_match.group(1) if offset_match else "0.0"
            scale = scale_match.group(1) if scale_match else "1.0"
            return True, offset, scale
    except Exception as e:
        pass
    return False, "0.0", "1.0"

def find_dense_audio_spots(srt_path, num_spots=3, duration_sec=30):
    try:
        with open(srt_path, 'r', encoding='utf-8', errors='ignore') as f:
            subs = list(srt.parse(f.read()))
            
        if not subs: return []
        
        blocks = {}
        for sub in subs:
            start = sub.start.total_seconds()
            block_idx = int(start // duration_sec)
            blocks[block_idx] = blocks.get(block_idx, 0) + len(sub.content)
            
        top_blocks = sorted(blocks.items(), key=lambda x: x[1], reverse=True)[:num_spots]
        return [block_idx * duration_sec for block_idx, count in top_blocks]
    except:
        return []

def detect_audio_language_whisper(video_path, audio_stream_idx, srt_path):
    num_spots = 6
    duration_sec = 30
    spots = []
    
    if srt_path and os.path.exists(srt_path):
        spots = find_dense_audio_spots(srt_path, num_spots=num_spots, duration_sec=duration_sec)
        
    if not spots:
        write_log(f"       -> Kein voller Text-Untertitel gefunden. Nutze {num_spots} mathematische Zeitstempel fÃ¼r Audio-Analyse.", console=False)
        try:
            dur_cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", video_path]
            total_dur = float(subprocess.check_output(dur_cmd).decode('utf-8').strip())
            safe_dur = total_dur - 600 if total_dur > 600 else total_dur
            start_off = 300 if total_dur > 600 else 0
            interval = safe_dur / num_spots
            spots = [start_off + (i * interval) for i in range(num_spots)]
        except:
            spots = [300, 900, 1500, 2100, 2700, 3300]
        
    try:
        import torch
        device = "cuda" if torch.cuda.is_available() else "cpu"
        model = whisper.load_model("tiny", device=device)
    except:
        return 'und', '0%'
        
    detected_langs = []
    
    for spot in spots:
        temp_audio = os.path.join(TEMP_DIR, f"temp_audio_{audio_stream_idx}_{int(spot)}.wav")
        cmd = ["ffmpeg", "-v", "quiet", "-y", "-ss", str(spot), "-i", video_path, "-map", f"0:{audio_stream_idx}", "-t", "30", "-c:a", "pcm_s16le", "-ar", "16000", "-ac", "1", temp_audio]
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
            except: pass
            finally:
                if os.path.exists(temp_audio): os.remove(temp_audio)
                
    if detected_langs:
        from collections import defaultdict
        counts = defaultdict(list)
        for l, p in detected_langs:
            counts[l].append(p)
        best_lang = max(counts.keys(), key=lambda k: len(counts[k]))
        if len(counts[best_lang]) >= 2 or (len(counts[best_lang]) == 1 and len(spots) == 1):
            avg_prob = sum(counts[best_lang]) / len(counts[best_lang])
            return best_lang, f"{avg_prob:.1f}%"
            
    return 'und', '0%'

def get_subtitle_timestamps(filepath, stream_idx):
    cmd = ["ffprobe", "-v", "quiet", "-select_streams", str(stream_idx), "-show_entries", "packet=pts_time", "-of", "json", filepath]
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='replace')
        if res.returncode != 0: return []
        data = json.loads(res.stdout)
        timestamps = []
        for p in data.get('packets', []):
            pts = p.get('pts_time')
            if pts:
                try: timestamps.append(float(pts))
                except: pass
        return timestamps
    except: return []

def extract_subtitle_image(filepath, stream_idx, ts, out_img):
    try:
        cmd = [
            "ffmpeg", "-v", "quiet", "-y",
            "-ss", str(ts + 0.1),
            "-i", filepath,
            "-filter_complex", f"[0:{stream_idx}]scale=1920:1080[v]",
            "-map", "[v]",
            "-vframes", "1",
            out_img
        ]
        subprocess.run(cmd, check=True)
        return True
    except:
        return False

def analyze_subtitle_pgs(filepath, stream_idx, codec_name, duration, is_forced_meta, old_lang="und", old_title=""):
    tess_map = {"chi":"chi_sim+chi_tra+eng", "zho":"chi_sim+chi_tra+eng", "rus":"rus+eng", "ara":"ara+eng", "heb":"heb+eng", "gre":"ell+eng", "ell":"ell+eng", "jpn":"jpn+eng", "kor":"kor+eng", "tur":"tur+eng", "pol":"pol+eng", "hin":"hin+eng"}
    tess_lang = tess_map.get(old_lang, "eng+deu+fra+spa+ita")
    
    detected_lang = 'und'
    is_forced = is_forced_meta
    
    if codec_name in ['hdmv_pgs_subtitle', 'dvd_subtitle'] and os.path.exists(TESSERACT_PATH):
        timestamps = get_subtitle_timestamps(filepath, stream_idx)
        
        if not timestamps:
            write_log("       => Keine Pakete in Bild-Untertitel gefunden. ?Ãœberspringe OCR.", console=False)
            return detected_lang, is_forced, '0%', False
            
        packet_count = len(timestamps)
        if packet_count > 500:
            if is_forced: write_log(f"     => FAKE FORCED ERKANNT! ({packet_count} Pakete). Entferne Forced-Tag.")
            is_forced = False
        elif packet_count < 150 and packet_count > 0:
            if not is_forced: write_log(f"     => FORCED ERKANNT ({packet_count} Pakete). Setze Forced-Tag.")
            is_forced = True
            
        max_img_setting = CONFIG.get("pgs_image_count", 50)
        sample_count = len(timestamps) if max_img_setting == 0 else min(max_img_setting, len(timestamps))
        
        indices = [int(i * (len(timestamps)-1) / max(1, sample_count-1)) for i in range(sample_count)]
        sample_timestamps = [timestamps[i] for i in set(indices)]
        
        write_log(f"       Starte Precision-OCR (Modell: {tess_lang}) an {len(sample_timestamps)} exakten Bild-Zeitpunkten...", console=False)
        

        first_img = None
        for i, ts in enumerate(sample_timestamps[:50]):
            out_img = os.path.join(TEMP_DIR, f"sub_{stream_idx}_test.png")
            if extract_subtitle_image(filepath, stream_idx, ts, out_img):
                try:
                    from PIL import Image
                    with Image.open(out_img) as img:
                        bbox = img.getbbox()
                        if bbox:
                            bbox = (max(0, bbox[0]-10), max(0, bbox[1]-10), min(img.width, bbox[2]+10), min(img.height, bbox[3]+10))
                            cropped = img.crop(bbox)
                            cropped.save(out_img)
                            first_img = out_img
                            break
                except: pass
                
        if first_img and old_lang == "und":
            best_conf = 0
            best_lang = tess_lang
            from pytesseract import Output
            for g in ["eng+deu+fra+spa+ita", "chi_sim+chi_tra+eng", "kor+eng", "rus+ara+heb+ell+eng", "jpn+eng", "tur+pol+hin+tha"]:
                try:
                    data = pytesseract.image_to_data(first_img, lang=g, output_type=Output.DICT)
                    confs = [int(c) for c in data['conf'] if int(c) != -1]
                    if confs:
                        avg = sum(confs) / len(confs)
                        if avg > best_conf:
                            best_conf = avg
                            best_lang = g
                except: pass
            if best_lang:
                tess_lang = best_lang
                write_log(f"       => Auto-Script erkannt! Benutze Sprachmodell: {tess_lang} (Confidence: {best_conf:.1f})")
        if first_img and os.path.exists(first_img): os.remove(first_img)

        def extract_and_ocr(ts, i):
            out_img = os.path.join(TEMP_DIR, f"sub_{stream_idx}_{i:03d}.png")
            if extract_subtitle_image(filepath, stream_idx, ts, out_img):
                try:
                    from PIL import Image
                    with Image.open(out_img) as img:
                        bbox = img.getbbox()
                        if bbox:
                            bbox = (max(0, bbox[0]-10), max(0, bbox[1]-10), min(img.width, bbox[2]+10), min(img.height, bbox[3]+10))
                            cropped = img.crop(bbox)
                            cropped.save(out_img)
                    return pytesseract.image_to_string(out_img, lang=tess_lang).strip()
                except: return ""
                finally:
                    if os.path.exists(out_img): os.remove(out_img)
            return ""
            
        combined_text = ""
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            futures = [executor.submit(extract_and_ocr, ts, i) for i, ts in enumerate(sample_timestamps)]
            for future in concurrent.futures.as_completed(futures):
                text = future.result()
                if text: combined_text += text + "\n"
                
        # Schreibe alles in eine Textdatei fÃ¼r spÃ¤tere ÃœberprÃ¼fungen
        ocr_file = os.path.join(TEMP_DIR, f"sub_{stream_idx}_OCR.txt")
        with open(ocr_file, "w", encoding="utf-8") as f:
            f.write(combined_text)
            
        is_hi = False
        sdh_markers = len(re.findall(r'\[.*?\]|\(.*?\)|^[A-Z\s]{2,}:', combined_text, flags=re.MULTILINE))
        min_sdh = max(2, int(duration / 3600))  # 1 marker per hour of runtime
        if sdh_markers >= min_sdh:
            is_hi = True
            write_log(f"       => SDH-Erkennung (PGS): {sdh_markers} Marker gefunden (Limit: {min_sdh}). Markiere als SchwerhÃ¶rig.")
            
        if len(combined_text.strip()) > 10:
            # Heuristic fallback for bad OCR
            if "Me refiero a" in combined_text or "manera de ver" in combined_text or "Djame ver" in combined_text:
                return 'spa', is_forced_meta, 80.0, is_hi
            
            try:
                res = detect_langs(combined_text)
                if res:
                    guess = map_lang(res[0].lang, old_title)
                    conf = res[0].prob * 100
                    write_log(f"       => OCR KI Gesamtergebnis: '{guess}' (Sicherheit: {conf:.1f}%)", console=False)
                    return guess, is_forced, f"{conf:.1f}%", is_hi
            except Exception as e:
                write_log(f"DEBUG: detect_langs crashed: {e}")
                pass
        else:
            write_log(f"DEBUG: combined_text was too short or empty: '{combined_text}'")
            
    return detected_lang, is_forced, '0%', False

def process_file(filepath):
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
                except: duration = 0
            break

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
    import concurrent.futures
    import time
    for idx, s in sub_streams:
        if s.get('codec_name') in ['subrip', 'ass']:
            out_sub = os.path.join(TEMP_DIR, f"sub_{idx}.srt")
            subprocess.run(["ffmpeg", "-v", "quiet", "-y", "-i", filepath, "-map", f"0:{idx}", out_sub])
            if os.path.exists(out_sub):
                sync_tasks.append(idx)
                
    def do_sync(idx):
        out_sub = os.path.join(TEMP_DIR, f"sub_{idx}.srt")
        synced_sub = os.path.join(TEMP_DIR, f"sub_{idx}_synced.srt")
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
            out_sub = os.path.join(TEMP_DIR, f"sub_{idx}.srt")
            synced_sub = os.path.join(TEMP_DIR, f"sub_{idx}_synced.srt")
            
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
                    except: pass
                    needs_muxing = True
                    needs_ffmpeg = True
                    extracted_text, line_count = read_text_subtitle(synced_sub)
                    if extracted_text:
                        sdh_markers = len(re.findall(r'\[.*?\]|\(.*?\)|^[A-Z\s]{2,}:', extracted_text, flags=re.MULTILINE))
                        is_hi = sdh_markers >= max(8, line_count * 0.015)
                    input_idx = len(input_files)
                    input_files.append(synced_sub)
                    ffmpeg_args.extend(["-i", synced_sub])
                    mapped_input = f"{input_idx}:0"
                    synced_srt_paths[idx] = synced_sub
                else:
                    extracted_text, line_count = read_text_subtitle(out_sub)
                    if extracted_text:
                        sdh_markers = len(re.findall(r'\[.*?\]|\(.*?\)|^[A-Z\s]{2,}:', extracted_text, flags=re.MULTILINE))
                        is_hi = sdh_markers >= max(8, line_count * 0.015)
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
                    import time
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
                    except: pass
                    
        else:
            import time
            start_t = time.time()
            detected_pgs_lang, is_forced_meta, conf, is_hi = analyze_subtitle_pgs(filepath, idx, codec, duration, is_forced_meta, old_lang, old_title)
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
                except: pass
                    
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
        tags = s.get('tags', {})
        old_lang = tags.get('language', 'und')
        old_title = tags.get('title', '')
        
        new_lang = map_lang(old_lang, old_title)
        
        write_log(f"  -> Audio Spur {idx} (Bisher: '{new_lang}'). Starte Whisper Analyse...")
        import time
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
            except: pass
                
        if new_lang != old_lang or old_title: needs_muxing = True
            
        if new_lang == 'ger': has_ger_audio = True
            
        mapped_audios.append((idx, new_lang))
        
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

    if not needs_ffmpeg:
        write_log("  -> Schnelles Metadaten-Update (mkvpropedit)...")
        mkvprop_args = [r"C:\Program Files\MKVToolNix\mkvpropedit.exe", filepath]
        
        # Audio Tracks
        for i, (orig_idx, new_lang) in enumerate(mapped_audios):
            track_id = f"a{i+1}"
            try:
                is_default_flag = 1 if ffmpeg_args[ffmpeg_args.index(f"-disposition:a:{i}")+1] == "default" else 0
            except:
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
            except:
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
        mkvprop_args = [r"C:\Program Files\MKVToolNix\mkvpropedit.exe", temp_out]
        
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
                import shutil
                shutil.move(temp_out, filepath)
                success = True
                break
            except Exception as e:
                import time
                time.sleep(2)
                
        if success:
            write_log("     Erfolgreich aktualisiert!")
        else:
            write_log(f"     FEHLER beim Ersetzen nach 5 Versuchen. Die Datei wird blockiert!")
    else:
        write_log("     FEHLER beim Muxen mit ffmpeg.")
        if os.path.exists(temp_out): os.remove(temp_out)

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
