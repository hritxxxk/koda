import random
from typing import Optional, Dict, Any, List

def get_next_problem(db, bank, sql_bank, mode: str, current_problem_id: str) -> Optional[Any]:
    """Recommends the next problem based on user performance."""
    with db._get_connection() as conn:
        # 1. Identify weak point: highest avg_hints_used and lowest pass rate
        # We can combine these into a 'struggle_score'
        # struggle_score = avg_hints_used * (1 - (passes / attempts))
        row = conn.execute("""
            SELECT topic, 
            (avg_hints_used * (1.0 - (CAST(passes AS REAL) / attempts))) as struggle_score
            FROM user_profile 
            ORDER BY struggle_score DESC 
            LIMIT 1
        """).fetchone()
        
        if row:
            weak_topic = row["topic"]
            # 2. Find an unsolved problem in that topic
            # First, get solved problem IDs
            solved_rows = conn.execute("SELECT DISTINCT problem_id FROM submissions WHERE passed = 1").fetchall()
            solved_ids = {r["problem_id"] for r in solved_rows}
            
            if mode == "DSA":
                problems = [p for p in bank.problems if p.topic == weak_topic and p.id not in solved_ids and p.id != current_problem_id]
                if problems:
                    return random.choice(problems)
            elif mode == "SQL":
                problems = [p for p in sql_bank.problems if p.category == weak_topic and p.id not in solved_ids and p.id != current_problem_id]
                if problems:
                    return random.choice(problems)
                    
        # 3. Cold start or no unsolved problems in weak topic: return random easy problem
        solved_rows = conn.execute("SELECT DISTINCT problem_id FROM submissions WHERE passed = 1").fetchall()
        solved_ids = {r["problem_id"] for r in solved_rows}
        
        if mode == "DSA":
            easy_probs = [p for p in bank.problems if p.difficulty == "Easy" and p.id not in solved_ids and p.id != current_problem_id]
            if not easy_probs: # If all easy solved
                easy_probs = [p for p in bank.problems if p.id != current_problem_id]
            return random.choice(easy_probs) if easy_probs else None
        elif mode == "SQL":
            easy_probs = [p for p in sql_bank.problems if p.difficulty == "Easy" and p.id not in solved_ids and p.id != current_problem_id]
            if not easy_probs:
                easy_probs = [p for p in sql_bank.problems if p.id != current_problem_id]
            return random.choice(easy_probs) if easy_probs else None
            
    return None

def get_review_problem(db, bank, sql_bank, mode: str) -> Optional[Any]:
    """Implements spaced repetition: returns oldest unresolved failure if > 3 days old."""
    from datetime import datetime, timedelta
    
    with db._get_connection() as conn:
        # Find problems with failures and NO subsequent passes
        # Sort by oldest failure first
        query = """
            SELECT problem_id, MAX(timestamp) as last_fail
            FROM user_events
            WHERE event_type = 'test_failed' AND mode = ?
            GROUP BY problem_id
            HAVING problem_id NOT IN (
                SELECT DISTINCT problem_id FROM user_events WHERE event_type = 'test_passed'
            )
            ORDER BY last_fail ASC
        """
        rows = conn.execute(query, (mode,)).fetchall()
        
        for row in rows:
            last_fail_dt = datetime.strptime(row["last_fail"], "%Y-%m-%d %H:%M:%S")
            if datetime.now() - last_fail_dt > timedelta(days=3):
                # Found an overdue review
                prob_id = row["problem_id"]
                if mode == "DSA":
                    return bank.get_problem(prob_id)
                elif mode == "SQL":
                    return sql_bank.get_problem(prob_id)
                    
    return None
