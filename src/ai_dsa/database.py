import sqlite3
import os
from datetime import datetime
from typing import Optional, List, Dict, Any

class Database:
    def __init__(self, db_path: str = "dsa.db"):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS submissions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    problem_id TEXT NOT NULL,
                    code TEXT NOT NULL,
                    passed INTEGER NOT NULL,
                    runtime_ms REAL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS hint_usage (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    problem_id TEXT NOT NULL,
                    hint_content TEXT NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS topic_stats (
                    topic TEXT PRIMARY KEY,
                    solved_count INTEGER DEFAULT 0,
                    total_attempts INTEGER DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS ai_cache (
                    cache_key TEXT PRIMARY KEY,
                    response_text TEXT NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS drafts (
                    problem_id TEXT PRIMARY KEY,
                    code TEXT NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS problem_sessions (
                    problem_id TEXT PRIMARY KEY,
                    start_time DATETIME DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS sql_problems (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    difficulty TEXT NOT NULL,
                    category TEXT NOT NULL,
                    schema_definition TEXT NOT NULL,
                    description TEXT NOT NULL,
                    expected_output TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS sql_attempts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    problem_id TEXT NOT NULL,
                    query TEXT NOT NULL,
                    passed INTEGER NOT NULL,
                    runtime_ms REAL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS user_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    mode TEXT NOT NULL,
                    problem_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    metadata TEXT -- JSON blob
                );

                CREATE TABLE IF NOT EXISTS user_profile (
                    topic TEXT PRIMARY KEY,
                    attempts INTEGER DEFAULT 0,
                    passes INTEGER DEFAULT 0,
                    avg_hints_used REAL DEFAULT 0,
                    avg_time_to_first_keystroke_seconds REAL DEFAULT 0,
                    failure_types TEXT, -- JSON blob
                    last_seen DATETIME DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS notes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    problem_id TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    content TEXT NOT NULL,
                    source TEXT NOT NULL -- manual or ai_generated
                );

                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
            """)
            conn.commit()

    def set_setting(self, key: str, value: str):
        with self._get_connection() as conn:
            conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
            conn.commit()

    def get_setting(self, key: str, default: Optional[str] = None) -> Optional[str]:
        with self._get_connection() as conn:
            row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
            return row["value"] if row else default

    def save_draft(self, problem_id: str, code: str):
        with self._get_connection() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO drafts (problem_id, code, timestamp) VALUES (?, ?, CURRENT_TIMESTAMP)",
                (problem_id, code)
            )
            conn.commit()

    def get_draft(self, problem_id: str) -> Optional[str]:
        with self._get_connection() as conn:
            row = conn.execute("SELECT code FROM drafts WHERE problem_id = ?", (problem_id,)).fetchone()
            return row["code"] if row else None

    def start_session(self, problem_id: str):
        with self._get_connection() as conn:
            # Only insert if it doesn't exist, to keep the ORIGINAL start time
            conn.execute(
                "INSERT OR IGNORE INTO problem_sessions (problem_id, start_time) VALUES (?, CURRENT_TIMESTAMP)",
                (problem_id,)
            )
            conn.commit()

    def get_start_time(self, problem_id: str) -> Optional[datetime]:
        with self._get_connection() as conn:
            row = conn.execute("SELECT start_time FROM problem_sessions WHERE problem_id = ?", (problem_id,)).fetchone()
            if row:
                return datetime.strptime(row["start_time"], "%Y-%m-%d %H:%M:%S")
            return None

    def add_submission(self, problem_id: str, topic: str, code: str, passed: bool, runtime_ms: float):
        with self._get_connection() as conn:
            conn.execute(
                "INSERT INTO submissions (problem_id, code, passed, runtime_ms) VALUES (?, ?, ?, ?)",
                (problem_id, code, int(passed), runtime_ms)
            )
            
            # Update topic stats
            conn.execute("""
                INSERT INTO topic_stats (topic, solved_count, total_attempts)
                VALUES (?, ?, 1)
                ON CONFLICT(topic) DO UPDATE SET
                    solved_count = solved_count + excluded.solved_count,
                    total_attempts = total_attempts + 1
            """, (topic, 1 if passed else 0))
            
            conn.commit()

    def log_hint(self, problem_id: str, hint_content: str):
        with self._get_connection() as conn:
            conn.execute(
                "INSERT INTO hint_usage (problem_id, hint_content) VALUES (?, ?)",
                (problem_id, hint_content)
            )
            conn.commit()

    def get_cache(self, cache_key: str) -> Optional[str]:
        with self._get_connection() as conn:
            row = conn.execute("SELECT response_text FROM ai_cache WHERE cache_key = ?", (cache_key,)).fetchone()
            return row["response_text"] if row else None

    def set_cache(self, cache_key: str, response_text: str):
        with self._get_connection() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO ai_cache (cache_key, response_text) VALUES (?, ?)",
                (cache_key, response_text)
            )
            conn.commit()

    def get_stats(self) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            rows = conn.execute("SELECT * FROM topic_stats").fetchall()
            return [dict(row) for row in rows]

    def add_sql_problem(self, problem):
        with self._get_connection() as conn:
            conn.execute(
                """INSERT OR IGNORE INTO sql_problems 
                   (id, title, difficulty, category, schema_definition, description, expected_output) 
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (problem.id, problem.title, problem.difficulty, problem.category, 
                 problem.schema_definition, problem.description, problem.expected_output)
            )
            conn.commit()

    def run_maintenance(self):
        """Prunes old events and maintains DB size."""
        import logging
        logger = logging.getLogger("maintenance")
        if not logger.handlers:
            handler = logging.FileHandler("maintenance.log")
            handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)
            
        pruned_count = 0
        with self._get_connection() as conn:
            # 1. Delete keystroke_first older than 90 days
            res = conn.execute(
                "DELETE FROM user_events WHERE event_type = 'keystroke_first' AND timestamp < date('now', '-90 days')"
            )
            pruned_count += res.rowcount
            
            # 2. Delete test_passed/failed older than 30 days (simplified)
            # Metadata summary could be complex, for now let's just prune old high-volume events
            res = conn.execute(
                "DELETE FROM user_events WHERE event_type IN ('test_passed', 'test_failed') AND timestamp < date('now', '-30 days')"
            )
            pruned_count += res.rowcount
            
            # 3. Cap table at 10,000 rows
            row = conn.execute("SELECT COUNT(*) as count FROM user_events").fetchone()
            if row["count"] > 10000:
                to_delete = row["count"] - 10000
                conn.execute(
                    "DELETE FROM user_events WHERE id IN (SELECT id FROM user_events ORDER BY timestamp ASC LIMIT ?)",
                    (to_delete,)
                )
                pruned_count += to_delete
            
            conn.commit()
            
        if pruned_count > 0:
            logger.info(f"Pruned {pruned_count} rows from user_events.")
