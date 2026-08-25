import sys
from ai_metatagger.utils.state_manager import load_matrix
import pandas as pd

df = load_matrix()
film = "The Witcher (2019) - S01E01.mkv"
track_type = "subtitle"
track_id = 13

movie_rows = df[df['file_name'] == film]
typ_rows = movie_rows[movie_rows['track_type'].str.lower() == track_type.lower()]

relative_idx = 1
for _, r in typ_rows.iterrows():
    if int(r['track_id']) == int(track_id):
        break
    relative_idx += 1
    
print("Relative Index for Track 13:", relative_idx)
