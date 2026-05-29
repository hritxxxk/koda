import sqlite3
import json
import logging
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
                    historical_event_counts TEXT, -- JSON blob
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

                CREATE INDEX IF NOT EXISTS idx_user_events_timestamp ON user_events(timestamp);
                CREATE INDEX IF NOT EXISTS idx_user_events_etype ON user_events(event_type);
                CREATE INDEX IF NOT EXISTS idx_notes_prob ON notes(problem_id);
            """)
            
            # Migration: Add historical_event_counts to user_profile if missing
            try:
                conn.execute("ALTER TABLE user_profile ADD COLUMN historical_event_counts TEXT")
            except sqlite3.OperationalError:
                pass # Already exists
                
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

    def run_maintenance(self, bank=None, sql_bank=None):
        """Prunes old events and maintains DB size, rolling up counts to user_profile."""
        logger = logging.getLogger("maintenance")
        if not logger.handlers:
            handler = logging.FileHandler("maintenance.log")
            handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)
            
        pruned_count = 0
        with self._get_connection() as conn:
            # 1. Identify rows to prune (older than 30 days)
            # We rollup ALL events older than 30 days before deleting.
            rollup_query = """
                SELECT problem_id, event_type, COUNT(*) as count 
                FROM user_events 
                WHERE timestamp < date('now', '-30 days')
                GROUP BY problem_id, event_type
            """
            rows_to_rollup = conn.execute(rollup_query).fetchall()
            
            if rows_to_rollup:
                # Build problem -> topic map
                prob_to_topic = {}
                # From SQL problems in DB
                sql_probs = conn.execute("SELECT id, category FROM sql_problems").fetchall()
                for p in sql_probs:
                    prob_to_topic[p["id"]] = p["category"]
                
                # From DSA bank if provided
                if bank:
                    for p in bank.problems:
                        prob_to_topic[p.id] = p.topic
                
                # Aggregate by topic and event_type
                topic_rollups = {} # topic -> {event_type: total_count}
                for row in rows_to_rollup:
                    topic = prob_to_topic.get(row["problem_id"], "Unknown")
                    if topic not in topic_rollups:
                        topic_rollups[topic] = {}
                    topic_rollups[topic][row["event_type"]] = topic_rollups[topic].get(row["event_type"], 0) + row["count"]
                
                # Update user_profile
                for topic, counts in topic_rollups.items():
                    # Get current historical_event_counts
                    profile = conn.execute("SELECT historical_event_counts FROM user_profile WHERE topic = ?", (topic,)).fetchone()
                    
                    if profile:
                        existing = json.loads(profile["historical_event_counts"]) if profile["historical_event_counts"] else {}
                        # Merge
                        for etype, count in counts.items():
                            existing[etype] = existing.get(etype, 0) + count
                        
                        conn.execute(
                            "UPDATE user_profile SET historical_event_counts = ? WHERE topic = ?",
                            (json.dumps(existing), topic)
                        )
                    else:
                        # Create minimal profile if it doesn't exist
                        conn.execute(
                            "INSERT INTO user_profile (topic, historical_event_counts) VALUES (?, ?)",
                            (topic, json.dumps(counts))
                        )
            
            # 2. Delete rows older than 30 days
            res = conn.execute("DELETE FROM user_events WHERE timestamp < date('now', '-30 days')")
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
            logger.info(f"Pruned {pruned_count} rows from user_events after rolling up history.")
