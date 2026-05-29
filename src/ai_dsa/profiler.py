import json
from typing import Optional, Dict, Any
from .database import Database

class UserProfiler:
    """Manages and updates the user topic performance profiles."""
    def __init__(self, db: Database):
        self.db = db

    def record_submission(self, topic: str, passed: bool, hints_used: int, time_to_first_keystroke: float, failure_type: Optional[str] = None) -> None:
        """Upserts user profile data for a specific topic."""
        with self.db._get_connection() as conn:
            # Get existing data
            row = conn.execute("SELECT * FROM user_profile WHERE topic = ?", (topic,)).fetchone()
            
            if row:
                attempts = row["attempts"] + 1
                passes = row["passes"] + (1 if passed else 0)
                
                # Update moving averages
                new_avg_hints = (row["avg_hints_used"] * row["attempts"] + hints_used) / attempts
                new_avg_time = (row["avg_time_to_first_keystroke_seconds"] * row["attempts"] + time_to_first_keystroke) / attempts
                
                # Update failure types
                failure_types = json.loads(row["failure_types"]) if row["failure_types"] else {}
                if failure_type:
                    failure_types[failure_type] = failure_types.get(failure_type, 0) + 1
                
                conn.execute(
                    """UPDATE user_profile SET 
                       attempts = ?, passes = ?, avg_hints_used = ?, 
                       avg_time_to_first_keystroke_seconds = ?, failure_types = ?, 
                       last_seen = CURRENT_TIMESTAMP 
                       WHERE topic = ?""",
                    (attempts, passes, new_avg_hints, new_avg_time, json.dumps(failure_types), topic)
                )
            else:
                failure_types = {failure_type: 1} if failure_type else {}
                conn.execute(
                    """INSERT INTO user_profile 
                       (topic, attempts, passes, avg_hints_used, avg_time_to_first_keystroke_seconds, failure_types) 
                       VALUES (?, 1, ?, ?, ?, ?)""",
                    (topic, 1 if passed else 0, float(hints_used), float(time_to_first_keystroke), json.dumps(failure_types))
                )
            conn.commit()
