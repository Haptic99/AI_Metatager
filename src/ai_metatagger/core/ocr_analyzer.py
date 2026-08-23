"""OCR-based subtitle analysis for PGS/DVD image subtitles.

Extracts subtitle images at sample timestamps, runs Tesseract OCR,
detects the language via langdetect, and identifies SDH markers.
"""
import os
import re
import json
import subprocess
import concurrent.futures
from typing import List, Optional, Tuple

from PIL import Image
import pytesseract
from pytesseract import Output
from langdetect import detect_langs

from ai_metatagger.utils.subprocess_tracker import tracked_run
from ai_metatagger.config import TESSERACT_PATH, CONFIG, TEMP_DIR
from ai_metatagger.core.logger import write_log, write_review
from ai_metatagger.core.subtitle_tools import map_lang, is_hearing_impaired

if os.path.exists(TESSERACT_PATH):
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH


def get_subtitle_timestamps(filepath: str, stream_idx: int) -> List[float]:
    """Get all PTS timestamps for a subtitle stream.

    Args:
        filepath: Path to the media file.
        stream_idx: Stream index of the subtitle track.

    Returns:
        List of timestamps in seconds.
    """
    cmd = ["ffprobe", "-v", "quiet", "-select_streams", str(stream_idx),
           "-show_entries", "packet=pts_time", "-of", "json", filepath]
    try:
        res = tracked_run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          text=True, encoding='utf-8', errors='replace')
        if res.returncode != 0:
            return []
        data = json.loads(res.stdout)
        timestamps = []
        for p in data.get('packets', []):
            pts = p.get('pts_time')
            if pts:
                try:
                    timestamps.append(float(pts))
                except Exception as e:
                    write_log(f"Warnung in {__name__}: {e}")
        return timestamps
    except Exception as e:
        write_log(f'Error in get_subtitle_timestamps: {e}')
        return []


def extract_subtitle_image(filepath: str, stream_idx: int, ts: float, out_img: str) -> bool:
    """Extract a single subtitle frame as a PNG image.

    Args:
        filepath: Path to the media file.
        stream_idx: Stream index of the subtitle track.
        ts: Timestamp in seconds.
        out_img: Output path for the PNG image.

    Returns:
        True if extraction was successful.
    """
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
        tracked_run(cmd, check=True)
        return os.path.exists(out_img)
    except subprocess.CalledProcessError:
        return False


def analyze_subtitle_pgs(
    filepath: str,
    stream_idx: int,
    track_id: int,
    codec_name: str,
    duration: float,
    is_forced_meta: bool,
    old_lang: str = "und",
    old_title: str = "",
    progress_callback=None,
) -> Tuple[str, bool, str, bool]:
    """Analyse a PGS/DVD image subtitle stream using OCR.

    Extracts sample images, runs Tesseract OCR, detects language via langdetect,
    and checks for SDH markers.

    Args:
        filepath: Path to the media file.
        stream_idx: Stream index of the subtitle track.
        track_id: Track number for naming temporary files.
        codec_name: Codec identifier (e.g. 'hdmv_pgs_subtitle').
        duration: Video duration in seconds.
        is_forced_meta: Whether the subtitle was tagged as forced.
        old_lang: Original language tag.
        old_title: Original track title.
        progress_callback: Optional callback for progress reporting.

    Returns:
        Tuple of (detected_language, is_forced, confidence_str, is_hi).
    """
    tess_map = {
        "chi": "chi_sim+chi_tra+eng", "zho": "chi_sim+chi_tra+eng",
        "rus": "rus+eng", "ara": "ara+eng", "heb": "heb+eng",
        "gre": "ell+eng", "ell": "ell+eng", "jpn": "jpn+eng",
        "kor": "kor+eng", "tur": "tur+eng", "pol": "pol+eng",
        "hin": "hin+eng"
    }
    tess_lang = tess_map.get(old_lang, "eng+deu+fra+spa+ita")

    detected_lang = 'und'
    is_forced = is_forced_meta

    if codec_name not in ['hdmv_pgs_subtitle', 'dvd_subtitle'] or not os.path.exists(TESSERACT_PATH):
        return detected_lang, is_forced, '0%', False

    timestamps = get_subtitle_timestamps(filepath, stream_idx)

    if not timestamps:
        write_log("       => Keine Pakete in Bild-Untertitel gefunden. Überspringe OCR.", console=False)
        return detected_lang, is_forced, '0%', False

    # Forced detection by packet count
    packet_count = len(timestamps)
    if packet_count > 500:
        if is_forced:
            write_log(f"     => FAKE FORCED ERKANNT! ({packet_count} Pakete). Entferne Forced-Tag.")
        is_forced = False
    elif 0 < packet_count < 150:
        if not is_forced:
            write_log(f"     => FORCED ERKANNT ({packet_count} Pakete). Setze Forced-Tag.")
        is_forced = True

    # Sample selection
    max_img_setting = CONFIG.get("pgs_image_count", 50)
    sample_count = len(timestamps) if max_img_setting == 0 else min(max_img_setting, len(timestamps))
    indices = [int(i * (len(timestamps) - 1) / max(1, sample_count - 1)) for i in range(sample_count)]
    sample_timestamps = [timestamps[i] for i in set(indices)]

    write_log(f"       Starte Precision-OCR (Modell: {tess_lang}) an {len(sample_timestamps)} exakten Bild-Zeitpunkten...", console=False)

    # Auto-detect best Tesseract language model
    tess_lang = _auto_detect_tess_language(filepath, stream_idx, track_id, sample_timestamps, tess_lang, old_lang)

    # Parallel OCR extraction
    combined_text = _run_parallel_ocr(filepath, stream_idx, track_id, sample_timestamps, tess_lang)

    # Save OCR text for debugging
    movie_base = os.path.basename(filepath)
    ocr_file = os.path.join(TEMP_DIR, f"{movie_base}_sub_{track_id}_OCR.txt")
    with open(ocr_file, "w", encoding="utf-8") as f:
        f.write(combined_text)

    # SDH detection — use shared helper from subtitle_tools
    line_count = len([l for l in combined_text.split('\n') if l.strip()])
    is_hi = is_hearing_impaired(combined_text, line_count)
    if is_hi:
        sdh_markers = len(re.findall(r'\[.*?\]|\(.*?\)|^[A-Z\s]{2,}:', combined_text, flags=re.MULTILINE))
        write_log(f"       => SDH-Erkennung (PGS): {sdh_markers} Marker gefunden. Markiere als Schwerhörig.")

    # Language detection
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
            write_log(f"Warnung bei OCR-Spracherkennung: {e}")

    return detected_lang, is_forced, '0%', False


def _auto_detect_tess_language(
    filepath: str,
    stream_idx: int,
    track_id: int,
    sample_timestamps: List[float],
    default_lang: str,
    old_lang: str,
) -> str:
    """Auto-detect the best Tesseract language model by testing multiple scripts."""
    first_img = None
    movie_base = os.path.basename(filepath)

    for i, ts in enumerate(sample_timestamps[:50]):
        out_img = os.path.join(TEMP_DIR, f"{movie_base}_sub_{track_id}_test.png")
        if extract_subtitle_image(filepath, stream_idx, ts, out_img):
            try:
                with Image.open(out_img) as img:
                    bbox = img.getbbox()
                    if bbox:
                        bbox = (max(0, bbox[0] - 10), max(0, bbox[1] - 10),
                                min(img.width, bbox[2] + 10), min(img.height, bbox[3] + 10))
                        cropped = img.crop(bbox)
                        cropped.save(out_img)
                        first_img = out_img
                        break
            except Exception as e:
                write_log(f"Warnung in {__name__}: {e}")

    if first_img and old_lang == "und":
        best_conf = 0
        best_lang = default_lang
        for g in ["eng+deu+fra+spa+ita", "chi_sim+chi_tra+eng", "kor+eng",
                   "rus+ara+heb+ell+eng", "jpn+eng", "tur+pol+hin+tha"]:
            try:
                data = pytesseract.image_to_data(first_img, lang=g, output_type=Output.DICT)
                confs = [int(c) for c in data['conf'] if int(c) != -1]
                if confs:
                    avg = sum(confs) / len(confs)
                    if avg > best_conf:
                        best_conf = avg
                        best_lang = g
            except Exception as e:
                write_log(f"Warnung in {__name__}: {e}")
        if best_lang != default_lang:
            default_lang = best_lang
            write_log(f"       => Auto-Script erkannt! Benutze Sprachmodell: {default_lang} (Confidence: {best_conf:.1f})")

    if first_img and os.path.exists(first_img):
        os.remove(first_img)

    return default_lang


def _run_parallel_ocr(
    filepath: str,
    stream_idx: int,
    track_id: int,
    sample_timestamps: List[float],
    tess_lang: str,
) -> str:
    """Run OCR on multiple subtitle images in parallel using ThreadPoolExecutor."""
    movie_base = os.path.basename(filepath)

    def extract_and_ocr(ts: float, i: int) -> str:
        out_img = os.path.join(TEMP_DIR, f"{movie_base}_sub_{track_id}_{i:03d}.png")
        if extract_subtitle_image(filepath, stream_idx, ts, out_img):
            try:
                with Image.open(out_img) as img:
                    bbox = img.getbbox()
                    if bbox:
                        bbox = (max(0, bbox[0] - 10), max(0, bbox[1] - 10),
                                min(img.width, bbox[2] + 10), min(img.height, bbox[3] + 10))
                        cropped = img.crop(bbox)
                        cropped.save(out_img)
                return pytesseract.image_to_string(out_img, lang=tess_lang).strip()
            except Exception as e:
                write_log(f"Warnung in OCR extract_and_ocr: {e}")
                return ""
            finally:
                if os.path.exists(out_img):
                    os.remove(out_img)
        return ""

    combined_text = ""
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(extract_and_ocr, ts, i) for i, ts in enumerate(sample_timestamps)]
        for future in concurrent.futures.as_completed(futures):
            text = future.result()
            if text:
                combined_text += text + "\n"

    return combined_text
