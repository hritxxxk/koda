from typing import List, Dict, Any, Optional
from .database import Database

def add_note(db: Database, problem_id: str, mode: str, content: str, source: str) -> None:
    """Adds a note to the database."""
    with db._get_connection() as conn:
        conn.execute(
            "INSERT INTO notes (problem_id, mode, content, source) VALUES (?, ?, ?, ?)",
            (problem_id, mode, content, source)
        )
        conn.commit()

def update_note(db: Database, note_id: int, content: str) -> None:
    """Updates the content of an existing note."""
    with db._get_connection() as conn:
        conn.execute(
            "UPDATE notes SET content = ?, timestamp = CURRENT_TIMESTAMP WHERE id = ?",
            (content, note_id)
        )
        conn.commit()

def get_notes(db: Database, problem_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Retrieves notes from the database, optionally filtered by problem_id."""
    with db._get_connection() as conn:
        if problem_id:
            rows = conn.execute("SELECT * FROM notes WHERE problem_id = ? ORDER BY timestamp DESC", (problem_id,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM notes ORDER BY timestamp DESC").fetchall()
        return [dict(row) for row in rows]
