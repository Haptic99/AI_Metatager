"""FFprobe wrapper for stream information extraction.

Provides a simple interface to query stream metadata from media files.
"""
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
