import json
import subprocess
from ai_metatagger.core.logger import write_log

def get_streams(filepath):
    cmd = ['ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_streams', filepath]
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='replace')
        if res.returncode != 0: return []
        data = json.loads(res.stdout)
        return data.get('streams', [])
    except Exception as e:
        write_log(f'Error in get_streams: {e}')
        return []
