import sqlite3
import pandas as pd
conn = sqlite3.connect("F:\\Jellyfin_AI_Cockpit\\data\\Jellyfin_AI_Database.sqlite")
df = pd.read_sql_query("SELECT track_id, track_type, language_iso FROM media_tracks WHERE file_name LIKE '%Witcher%'", conn)
print(df)
conn.close()
