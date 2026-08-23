import os
from ai_metatagger.utils.state_manager import load_matrix

validated_movies = set()
auto_movies = set()

df = load_matrix()
for movie in df['file_name'].unique():
    movie_rows = df[df['file_name'] == movie]
    if False not in movie_rows['is_validated'].values:
        validated_movies.add(movie)
    else:
        auto_movies.add(movie)

print("Validated:", validated_movies)
print("Auto:", auto_movies)

files = []
d = "F:\\Jellyfin_AI_Cockpit\\data\\Test_Videos"
for f in os.listdir(d):
    if f.endswith(('.mkv', '.mp4', '.avi')):
        if f not in validated_movies and f not in auto_movies:
            files.append(f)
            print("Added to scan list:", f)
