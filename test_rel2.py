from ai_metatagger.utils.state_manager import load_matrix
df = load_matrix()
film = "The Witcher (2019) - S01E01.mkv"
movie_rows = df[df['file_name'] == film]
typ_rows = movie_rows[movie_rows['track_type'].str.lower() == 'subtitle']
print(typ_rows[['track_id', 'track_type']])
