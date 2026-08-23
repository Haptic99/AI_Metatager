from ai_metatagger.utils.state_manager import init_db
conn = init_db()
c = conn.cursor()
c.execute("SELECT COUNT(*), SUM(CASE WHEN ki_data IS NULL OR ki_data = '' OR ki_data = '{}' THEN 1 ELSE 0 END) FROM media_tracks")
print("Total vs Missing KI Data:", c.fetchone())
