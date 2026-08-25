import sqlite3
import pandas as pd
conn = sqlite3.connect("F:\\Jellyfin_AI_Cockpit\\data\\Jellyfin_AI_Database.sqlite")
df = pd.read_sql_query("SELECT DISTINCT file_name FROM media_tracks", conn)
print(df)
conn.close()
