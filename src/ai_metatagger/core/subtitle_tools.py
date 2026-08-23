import os
import re
import difflib
import srt
import subprocess
from ai_metatagger.config import FFSUBSYNC_PATH, CONFIG
from ai_metatagger.core.logger import write_log

def is_same_lang_family(lang1, lang2):
    if not lang1 or not lang2: return False
    l1 = lang1.lower()
    l2 = lang2.lower()
    if l1 == l2: return True
    
    m1 = map_lang(l1)
    m2 = map_lang(l2)
    if m1 == m2: return True
    
    macros = {
        'pt': 'por', 'es': 'spa', 'zh': 'chi', 'en': 'eng', 'de': 'ger', 'fr': 'fre', 'zh-hans': 'chi', 'zh-hant': 'chi'
    }
    
    for prefix, macro in macros.items():
        if (l1.startswith(prefix) and l2 == macro) or (l2.startswith(prefix) and l1 == macro):
            return True
            
    if lang1.startswith(lang2[:2]) or lang2.startswith(lang1[:2]): 
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
        except Exception as e:
            write_log(f"Fehler beim Lesen von Untertitel {filepath}: {e}")
    return full_text, line_count

def auto_sync_subtitle(video_path, sub_path, out_path):
    if not os.path.exists(FFSUBSYNC_PATH):
        return False, "0.0", "1.0"
    cmd = [FFSUBSYNC_PATH, video_path, "-i", sub_path, "-o", out_path]
    try:
        write_log("       Starte ffsubsync (KI-AutoSync) fÃ¼r Spur...", console=False)
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='replace')
        if res.returncode == 0 and os.path.exists(out_path) and os.path.getsize(out_path) > 0:
            out_text = res.stdout + res.stderr
            offset_match = re.search(r"offset seconds:\s*([\-\d\.]+)", out_text)
            scale_match = re.search(r"scale factor:\s*([\-\d\.]+)", out_text)
            offset = offset_match.group(1) if offset_match else "0.0"
            scale = scale_match.group(1) if scale_match else "1.0"
            return True, offset, scale
    except Exception as e:
        write_log(f"Fehler bei ffsubsync: {e}")
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
    except Exception as e:
        write_log(f'Error in find_dense_audio_spots: {e}')
        return []
