import re
file_path = r'F:\Jellyfin_AI_Cockpit\src\ai_metatagger\utils\thread_workers.py'
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Update weights
old_weights = '''        w_audio = 2
        w_pgs = 10
        w_srt = 1
        w_mux = 2'''

new_weights = '''        w_audio = 20
        w_pgs = 100
        w_srt = 1
        w_mux = 250'''
content = content.replace(old_weights, new_weights)

# 2. Add 'points_in_file' to file_stats
old_stat_append = '''            total_points += w_mux
            file_stats.append({'total_tracks': f_aud + f_sub})'''

new_stat_append = '''            total_points += w_mux
            pts_for_file = (f_aud * w_audio) + (f_pgs * w_pgs) + (f_srt * w_srt) + w_mux
            file_stats.append({'total_tracks': f_aud + f_sub + f_pgs + f_srt, 'points': pts_for_file})'''
            
# Wait, I don't have f_pgs and f_srt separated in the pre-scan currently! Let's check the pre-scan loop.
