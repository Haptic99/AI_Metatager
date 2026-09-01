"""FFprobe wrapper for stream information extraction.

Provides a simple interface to query stream metadata from media files.
"""
import os
import json
import subprocess
from typing import Dict, List

from ai_metatagger.utils.subprocess_tracker import tracked_run
from ai_metatagger.core.logger import write_log


def get_streams(filepath: str) -> List[Dict]:
    """Get all stream information from a media file using ffprobe.

    Args:
        filepath: Path to the media file.

    Returns:
        List of stream dictionaries, or empty list on error.
    """
    cmd = ['ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_streams', filepath]
    try:
        res = tracked_run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='replace')
        if res.returncode != 0:
            return []
        data = json.loads(res.stdout)
        return data.get('streams', [])
    except Exception as e:
        write_log(f'Error in get_streams: {e}')
        return []

def generate_track_metadata(filepath: str) -> list:
    """Uses ffprobe to extract stream metadata and formats it for the database."""
    cmd = ["ffprobe", "-v", "error", "-show_streams", "-of", "json", filepath]
    res = tracked_run(cmd, capture_output=True, text=True, encoding='utf-8')
    if res.returncode != 0:
        return []
        
    try:
        data = json.loads(res.stdout)
    except json.JSONDecodeError:
        return []

    tracks = []
    streams = [s for s in data.get('streams', []) if s.get('codec_type') != 'video']
    for idx, s in enumerate(streams, start=1):
        lang = s.get('tags', {}).get('language', 'und')
        title = s.get('tags', {}).get('title', '')
        disp = s.get('disposition', {})
        is_sdh = disp.get('hearing_impaired', 0) == 1 or 'SDH' in title.upper()
        is_forced = disp.get('forced', 0) == 1 or 'FORCED' in title.upper()
        is_default = disp.get('default', 0) == 1
        track_type = "Audio" if s.get('codec_type') == 'audio' else "Untertitel"
        codec = s.get('codec_name', '').lower()
        
        if track_type == "Audio":
            sub_type = ""
        elif 'pgs' in codec or 'dvd' in codec:
            sub_type = "PGSSUB"
        else:
            sub_type = "SRT"

        tracks.append({
            "file_name": os.path.basename(filepath),
            "track_id": idx,
            "target_track_id": idx,
            "track_type": track_type,
            "language_iso": lang,
            "track_name": "",
            "is_default": is_default,
            "subtitle_type": sub_type,
            "is_hearing_impaired": is_sdh,
            "is_forced": is_forced,
            "notes": "AUTO",
            "is_validated": False
        })
    return tracks