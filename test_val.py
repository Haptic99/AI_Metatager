import pandas as pd
df = pd.DataFrame({
    "file_name": ["Ali G Indahouse.mkv", "Ali G Indahouse.mkv"],
    "is_validated": [1, 1]
})
validated = set()
for movie in df['file_name'].unique():
    movie_rows = df[df['file_name'] == movie]
    if False not in movie_rows['is_validated'].values:
        validated.add(movie)
print("1/1:", validated)

df2 = pd.DataFrame({
    "file_name": ["Ali G Indahouse.mkv", "Ali G Indahouse.mkv"],
    "is_validated": [1, 0]
})
validated2 = set()
for movie in df2['file_name'].unique():
    movie_rows = df2[df2['file_name'] == movie]
    if False not in movie_rows['is_validated'].values:
        validated2.add(movie)
print("1/0:", validated2)
