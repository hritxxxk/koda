from typing import List, Dict, Any, Optional

def add_note(db, problem_id: str, mode: str, content: str, source: str):
    """Adds a note to the database."""
    with db._get_connection() as conn:
        conn.execute(
            "INSERT INTO notes (problem_id, mode, content, source) VALUES (?, ?, ?, ?)",
            (problem_id, mode, content, source)
        )
        conn.commit()

def get_notes(db, problem_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Retrieves notes from the database, optionally filtered by problem_id."""
    with db._get_connection() as conn:
        if problem_id:
            rows = conn.execute("SELECT * FROM notes WHERE problem_id = ? ORDER BY timestamp DESC", (problem_id,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM notes ORDER BY timestamp DESC").fetchall()
        return [dict(row) for row in rows]
