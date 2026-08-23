import os
import sys

from ai_metatagger.config import DIR_SERIEN
from ai_metatagger.core.logger import write_log
from ai_metatagger.core.ffmpeg_tools import get_streams

from ai_metatagger.core.converters import _convert_container
from ai_metatagger.core.subtitle_extractor import _extract_and_sync_subtitles, _process_subtitles
from ai_metatagger.core.audio_processor import _process_audio
from ai_metatagger.core.muxer import _build_muxing_args, _execute_muxing, _execute_mkvpropedit

MEDIA_DIR = DIR_SERIEN

def process_file(filepath: str, progress_callback=None) -> str:
    """Analyse and process a single media file. Returns the (potentially updated) filepath."""
    write_log(f"\n--- Analysiere V5: {filepath} ---")

    filepath = _convert_container(filepath)
    if not filepath:
        return ""

    streams = get_streams(filepath)
    if not streams:
        return filepath

    duration = 0
    for s in streams:
        if s.get('codec_type') == 'video':
            duration = s.get('duration', s.get('tags', {}).get('DURATION', '0'))
            if ':' in str(duration):
                parts = str(duration).split(':')
                duration = float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2][:2])
            else:
                try:
                    duration = float(duration)
                except ValueError:
                    duration = 0
            break

    audio_streams = []
    sub_streams = []
    track_id_map = {}
    for i, s in enumerate(streams):
        if s.get('codec_type') == 'audio': 
            audio_streams.append((i, s))
        elif s.get('codec_type') == 'subtitle': 
            sub_streams.append((i, s))
            track_id_map[i] = len(sub_streams)

    ffmpeg_args = ["ffmpeg", "-v", "quiet", "-y", "-i", filepath]
    input_files = [filepath]
    
    sync_results = _extract_and_sync_subtitles(filepath, sub_streams, track_id_map)

    mapped_subs, final_subs, synced_srt_paths, needs_muxing_sub, needs_ffmpeg = _process_subtitles(
        filepath, sub_streams, track_id_map, sync_results, duration,
        ffmpeg_args, input_files, progress_callback
    )

    mapped_audios, has_ger_audio, needs_muxing_audio = _process_audio(
        filepath, audio_streams, synced_srt_paths, progress_callback
    )

    needs_remux = needs_muxing_sub or needs_muxing_audio

    needs_muxing_disp = _build_muxing_args(ffmpeg_args, mapped_audios, mapped_subs, audio_streams, has_ger_audio)
    needs_remux = needs_remux or needs_muxing_disp

    if needs_remux:
        _execute_muxing(filepath, ffmpeg_args, mapped_audios, final_subs, needs_ffmpeg, progress_callback)
    else:
        _execute_mkvpropedit(filepath, ffmpeg_args, mapped_audios, final_subs)
        
    return filepath


def main() -> None:
    """CLI entry point for standalone processing."""
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
