import pandas as pd
from ai_metatagger.utils.state_manager import load_matrix, update_track, load_state

class ValidatorController:
    """
    Handles the business logic for the validation screen.
    Maintains the state of the media tracks, calculates accuracy, and updates the database.
    """
    def __init__(self):
        self.df = pd.DataFrame()
        self.state_data = {}
        
    def refresh_data(self):
        self.df = load_matrix()
        self.state_data = load_state()
        
    def get_tracks_to_validate(self):
        """Return a list of unvalidated tracks."""
        if self.df.empty:
            return []
        
        # Filter for unvalidated tracks (exclude muxing)
        mask = (self.df['is_validated'] == False) & (self.df['track_type'] != 'muxing')
        return self.df[mask].to_dict('records')
        
    def get_ki_data(self, film, track_id):
        return self.state_data.get(film, {}).get(str(track_id), {}).get('KI', {})
        
    def get_validation_data(self, film, track_id):
        return self.state_data.get(film, {}).get(str(track_id), {}).get('Validated', {})
        
    def save_validation(self, film, track_id, lang, sdh, forced, track_name, notes, validation_flags):
        """
        Save user validation to the database (O(1) update).
        """
        updates = {
            'language_iso': lang,
            'is_hearing_impaired': sdh,
            'is_forced': forced,
            'track_name': track_name,
            'notes': notes,
            'is_validated': True
        }
        update_track(film, track_id, updates)
        
        # Also update KI validation flags (state_data)
        if film not in self.state_data:
            self.state_data[film] = {}
        if str(track_id) not in self.state_data[film]:
            self.state_data[film][str(track_id)] = {"KI": {}, "Validated": {}}
            
        self.state_data[film][str(track_id)]['Validated'] = validation_flags
        
        # In the new architecture, saving the state is done implicitly by update_track if we updated it to support JSON.
        # Wait, update_track in state_manager only updates top-level columns. 
        # I need to also write the updated validation_flags into the SQLite row.
        
        import json
        from ai_metatagger.utils.state_manager import DB_LOCK, init_db
        with DB_LOCK:
            conn = init_db()
            cursor = conn.cursor()
            val_json = json.dumps(validation_flags)
            cursor.execute("UPDATE media_tracks SET validated_fields = ? WHERE file_name = ? AND track_id = ?",
                          (val_json, film, track_id))
            conn.commit()
            conn.close()
            
    def remove_movie(self, film):
        """Remove all tracks for a specific movie from the database."""
        from ai_metatagger.utils.state_manager import DB_LOCK, init_db
        with DB_LOCK:
            conn = init_db()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM media_tracks WHERE file_name = ?", (film,))
            conn.commit()
            conn.close()
        self.refresh_data()
        
    def calculate_accuracy(self):
        """Calculate KI accuracy compared to user validation."""
        total = 0
        correct = 0
        fields = ['lang', 'sdh', 'forced', 'name']
        
        for film, tracks in self.state_data.items():
            for trk_id, data in tracks.items():
                ki = data.get('KI', {})
                if not ki:
                    continue
                    
                val = data.get('Validated', {})
                
                # Only check if all fields were validated by the user
                if not all(val.get(f) for f in fields):
                    continue
                    
                # We need the user's actual saved data from the DB to compare against KI
                # Since the old code compared KI against the UI inputs, we compare KI against DB
                if self.df.empty:
                    continue
                    
                mask = (self.df['file_name'] == film) & (self.df['track_id'] == str(trk_id))
                if not mask.any():
                    continue
                    
                db_row = self.df[mask].iloc[0]
                
                # Compare Lang
                total += 1
                if ki.get('lang') == db_row['language_iso']:
                    correct += 1
                    
                # Compare SDH
                total += 1
                if bool(ki.get('sdh')) == bool(db_row['is_hearing_impaired']):
                    correct += 1
                    
                # Compare Forced
                total += 1
                if bool(ki.get('forced')) == bool(db_row['is_forced']):
                    correct += 1
                    
                # Compare Name
                total += 1
                # Simplified name comparison (just if both are populated or both empty in a similar way)
                # We don't want to penalize if KI left it empty and user left it empty
                if str(ki.get('name', '')) == str(db_row['track_name']):
                    correct += 1
                    
        if total == 0:
            return 0
        return int((correct / total) * 100)
