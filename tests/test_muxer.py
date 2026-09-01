import pytest
from ai_metatagger.core.muxer import _build_muxing_args

def test_build_muxing_args_ger_audio_and_forced_sub():
    """Test that default flags are set correctly for German audio and forced subs."""
    
    ffmpeg_args = []
    
    # Format: (orig_idx, new_lang)
    mapped_audios = [
        (1, 'eng'),
        (2, 'ger')
    ]
    
    # Format: (orig_idx, is_forced_meta, mapped_input, new_lang, clean_title, s, out_idx, is_hi)
    # Let's say out_idx 0 is eng sub, out_idx 1 is ger forced sub
    mapped_subs = [
        (3, False, "0:s:0", 'eng', '', {}, 0, False),
        (4, True, "0:s:1", 'ger', 'Forced', {}, 1, False)
    ]
    
    # Format for audio_streams: list of (orig_idx, stream_dict)
    audio_streams = [
        (1, {"tags": {"language": "und"}, "disposition": {"default": 0}}),
        (2, {"tags": {"language": "ger"}, "disposition": {"default": 1}})
    ]
    
    # Call the function
    needs_muxing = _build_muxing_args(
        ffmpeg_args=ffmpeg_args,
        mapped_audios=mapped_audios,
        mapped_subs=mapped_subs,
        audio_streams=audio_streams,
        has_ger_audio=True
    )
    
    # Verify outputs
    # German audio should be default if present
    # German forced sub should be default if present
    # Needs muxing should be True since dispositions are set
    
    assert "-disposition:a:1" in ffmpeg_args  # Second audio track (ger)
    # Find what it was set to
    idx = ffmpeg_args.index("-disposition:a:1")
    assert ffmpeg_args[idx + 1] == "default"
    
    assert "-disposition:s:1" in ffmpeg_args  # Second sub track (ger forced)
    idx_sub = ffmpeg_args.index("-disposition:s:1")
    assert ffmpeg_args[idx_sub + 1] == "forced+default"
    
    assert needs_muxing is True

def test_build_muxing_args_no_ger_audio_sets_eng_default():
    """Test that if no German audio is present, English audio and German normal sub are set as default."""
    
    ffmpeg_args = []
    
    mapped_audios = [
        (1, 'eng')
    ]
    
    mapped_subs = [
        (2, False, "0:s:0", 'ger', '', {}, 0, False)
    ]
    
    needs_muxing = _build_muxing_args(
        ffmpeg_args=ffmpeg_args,
        mapped_audios=mapped_audios,
        mapped_subs=mapped_subs,
        audio_streams=[(1, {"tags": {}, "disposition": {}})],
        has_ger_audio=False
    )
    
    assert "-disposition:a:0" in ffmpeg_args
    idx = ffmpeg_args.index("-disposition:a:0")
    assert ffmpeg_args[idx + 1] == "default"
    
    assert "-disposition:s:0" in ffmpeg_args
    idx_sub = ffmpeg_args.index("-disposition:s:0")
    assert ffmpeg_args[idx_sub + 1] == "default"
