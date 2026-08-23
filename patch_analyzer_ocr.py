import re
file_path = r'F:\Jellyfin_AI_Cockpit\src\ai_metatagger\core\analyzer.py'
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Find the ThreadPoolExecutor for analyze_pgs_subtitle
old_loop = '''        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            futures = [executor.submit(extract_and_ocr, ts, i) for i, ts in enumerate(sample_timestamps)]
            for future in concurrent.futures.as_completed(futures):
                text = future.result()
                if text:
                    combined_text += " " + text'''

new_loop = '''        total_samples = len(sample_timestamps)
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            futures = [executor.submit(extract_and_ocr, ts, i) for i, ts in enumerate(sample_timestamps)]
            completed = 0
            for future in concurrent.futures.as_completed(futures):
                text = future.result()
                completed += 1
                if progress_callback:
                    progress_callback('subtitle', track_idx, 'step', 'hdmv_pgs_subtitle', completed, total_samples)
                if text:
                    combined_text += " " + text'''

# I need to ensure 	rack_idx is passed, but it's not in nalyze_pgs_subtitle signature!
# Let's check nalyze_pgs_subtitle signature.
