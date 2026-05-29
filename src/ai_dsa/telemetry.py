import json
from typing import Optional, Dict, Any
from .database import Database

def log_event(db: Database, event_type: str, problem_id: str, mode: str, metadata: Optional[Dict[str, Any]] = None) -> int:
    """Logs a user event to the database and returns the event ID."""
    metadata_json = json.dumps(metadata) if metadata else None
    with db._get_connection() as conn:
        cursor = conn.execute(
            "INSERT INTO user_events (event_type, problem_id, mode, metadata) VALUES (?, ?, ?, ?)",
            (event_type, problem_id, mode, metadata_json)
        )
        conn.commit()
        return cursor.lastrowid

def update_event_metadata(db: Database, event_id: int, metadata: Dict[str, Any]) -> None:
    """Updates the metadata of an existing event."""
    with db._get_connection() as conn:
        # Get existing metadata
        row = conn.execute("SELECT metadata FROM user_events WHERE id = ?", (event_id,)).fetchone()
        existing = json.loads(row["metadata"]) if row and row["metadata"] else {}
        
        # Merge
        existing.update(metadata)
        
        conn.execute(
            "UPDATE user_events SET metadata = ? WHERE id = ?",
            (json.dumps(existing), event_id)
        )
        conn.commit()
