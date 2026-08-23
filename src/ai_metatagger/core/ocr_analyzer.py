import os
import re
import json
import subprocess
import pytesseract
from langdetect import detect_langs
from ai_metatagger.config import TESSERACT_PATH, CONFIG
from ai_metatagger.core.logger import write_log, write_review
from ai_metatagger.core.subtitle_tools import map_lang

if os.path.exists(TESSERACT_PATH):
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH

TEMP_DIR = None

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
                except Exception: pass
        return timestamps
    except Exception as e:
        write_log(f'Error in get_subtitle_timestamps: {e}')
        return []

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
    except subprocess.CalledProcessError:
        return False

def analyze_subtitle_pgs(filepath, stream_idx, track_id, codec_name, duration, is_forced_meta, old_lang="und", old_title="", progress_callback=None):
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
            movie_base = os.path.basename(filepath)
            out_img = os.path.join(TEMP_DIR, f"{movie_base}_sub_{track_id}_test.png")
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
                except Exception: pass
                
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
                except Exception: pass
            if best_lang:
                tess_lang = best_lang
                write_log(f"       => Auto-Script erkannt! Benutze Sprachmodell: {tess_lang} (Confidence: {best_conf:.1f})")
        if first_img and os.path.exists(first_img): os.remove(first_img)

        def extract_and_ocr(ts, i):
            movie_base = os.path.basename(filepath)
            out_img = os.path.join(TEMP_DIR, f"{movie_base}_sub_{track_id}_{i:03d}.png")
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
                except Exception: return ""
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
                
        movie_base = os.path.basename(filepath)
        ocr_file = os.path.join(TEMP_DIR, f"{movie_base}_sub_{track_id}_OCR.txt")
        with open(ocr_file, "w", encoding="utf-8") as f:
            f.write(combined_text)
            
        is_hi = False
        sdh_markers = len(re.findall(r'\[.*?\]|\(.*?\)|^[A-Z\s]{2,}:', combined_text, flags=re.MULTILINE))
        min_sdh = max(2, int(duration / 3600))  
        if sdh_markers >= min_sdh:
            is_hi = True
            write_log(f"       => SDH-Erkennung (PGS): {sdh_markers} Marker gefunden (Limit: {min_sdh}). Markiere als SchwerhÃ¶rig.")
            
        if len(combined_text.strip()) > 10:
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
                pass
            
    return detected_lang, is_forced, '0%', False
