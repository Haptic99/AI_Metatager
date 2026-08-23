import os
import datetime
from ai_metatagger.config import DATA_DIR

LOG_PATH = os.path.join(DATA_DIR, 'Master_Cleanup_Log.txt')
REVIEW_LOG = os.path.join(DATA_DIR, 'Bitte_Pruefen.txt')
KORREKTUR_LOG = os.path.join(DATA_DIR, 'Master_Korrektur_Log.txt')
SYNC_LOG = os.path.join(DATA_DIR, 'Master_Sync_Log.txt')

def write_review(msg):
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    formatted_msg = f'[{timestamp}] {msg}'
    try:
        with open(REVIEW_LOG, 'a', encoding='utf-8') as f:
            f.write(formatted_msg + '\n')
    except Exception as e:
        print(f'Error writing to review log: {e}')

def write_log(msg, console=True, log_type='cleanup'):
    import sys
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    formatted_msg = f'[{timestamp}] {msg}' if log_type != 'cleanup' else msg
    
    try:
        with open(LOG_PATH, 'a', encoding='utf-8') as f:
            f.write(formatted_msg + '\n')
    except Exception: pass
        
    if console:
        print(str(msg).encode(sys.stdout.encoding, errors='replace').decode(sys.stdout.encoding))
