path = r"F:\Jellyfin_AI_Cockpit\src\ai_metatagger\ui\screens\validator.py"
with open(path, "r", encoding="utf-8") as f:
    content = f.read()

old_play = """        if os.path.exists(filepath):
            self.player_widget.play_media(
                filepath, track_type.lower(), int(track_id), autoplay)"""

new_play = """        if os.path.exists(filepath):
            # Berechne den 1-basierten Index (relative_idx) für VLC!
            df = self.ctrl.df
            movie_rows = df[df['file_name'] == film]
            typ_rows = movie_rows[movie_rows['track_type'].str.lower() == track_type.lower()]
            
            relative_idx = 1
            for _, r in typ_rows.iterrows():
                if int(r['track_id']) == int(track_id):
                    break
                relative_idx += 1
                
            self.player_widget.play_media(
                filepath, track_type.lower(), relative_idx, autoplay)"""

content = content.replace(old_play, new_play)
with open(path, "w", encoding="utf-8") as f:
    f.write(content)
