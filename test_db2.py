from ai_metatagger.utils.state_manager import init_db
conn = init_db()
c = conn.cursor()
c.execute("SELECT validated_fields FROM media_tracks ORDER BY ROWID ASC LIMIT 5")
print(c.fetchall())
