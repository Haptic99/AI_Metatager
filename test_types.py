import sqlite3
conn = sqlite3.connect("F:\\Jellyfin_AI_Cockpit\\data\\Jellyfin_AI_Database.sqlite")
cur = conn.cursor()
cur.execute("SELECT DISTINCT track_type FROM media_tracks")
print("Track types in DB:", cur.fetchall())
conn.close()
