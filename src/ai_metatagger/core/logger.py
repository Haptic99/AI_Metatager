"""Thread-safe logging module for AI Metatagger.

Provides functions to write to the main log, review log, correction log,
and sync log. All file writes are protected by a threading.Lock.
"""
import os
import sys
import datetime
import threading
from ai_metatagger.config import DATA_DIR

LOG_LOCK = threading.Lock()

LOG_PATH = os.path.join(DATA_DIR, 'Master_Cleanup_Log.txt')
REVIEW_LOG = os.path.join(DATA_DIR, 'Bitte_Pruefen.txt')
KORREKTUR_LOG = os.path.join(DATA_DIR, 'Master_Korrektur_Log.txt')
SYNC_LOG = os.path.join(DATA_DIR, 'Master_Sync_Log.txt')


def write_review(msg: str) -> None:
    """Write a message to the review log (items requiring manual review).

    Args:
        msg: The review message to log.
    """
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    formatted_msg = f'[{timestamp}] {msg}'
    try:
        with LOG_LOCK:
            with open(REVIEW_LOG, 'a', encoding='utf-8') as f:
                f.write(formatted_msg + '\n')
    except Exception as e:
        print(f'Error writing to review log: {e}')


def write_log(msg: str, console: bool = True, log_type: str = 'cleanup') -> None:
    """Write a message to the main analysis log.

    Args:
        msg: The log message.
        console: If True, also print to stdout.
        log_type: Log category ('cleanup', 'sync', 'korrektur').
    """
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    formatted_msg = f'[{timestamp}] {msg}' if log_type != 'cleanup' else msg

    try:
        with LOG_LOCK:
            with open(LOG_PATH, 'a', encoding='utf-8') as f:
                f.write(formatted_msg + '\n')
    except Exception:
        # Intentionally silent: logging errors must not cause recursion or crashes
        pass

    if console:
        print(str(msg).encode(sys.stdout.encoding, errors='replace').decode(sys.stdout.encoding))
