from ai_metatagger.utils.state_manager import init_db
import pandas as pd
conn = init_db()
df = pd.read_sql("SELECT file_name, track_id, is_validated FROM media_tracks", conn)
print("All rows:")
print(df)
