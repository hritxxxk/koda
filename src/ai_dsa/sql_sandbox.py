import sqlite3
import time
import json
from typing import List, Dict, Any, Optional

class SQLSandbox:
    """Executes SQL queries against an in-memory SQLite database."""
    def __init__(self, timeout_sec: int = 5):
        self.timeout_sec = timeout_sec

    def run_query(self, query: str, schema_definition: str, expected_output: str) -> Dict[str, Any]:
        """Runs a SQL query and compares the result with the expected output."""
        start_time = time.perf_counter()
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        
        success = False
        error = None
        actual_value = None
        passed = False
        
        try:
            # Initialize schema and data
            conn.executescript(schema_definition)
            
            # Run user query
            cursor = conn.execute(query)
            rows = cursor.fetchall()
            actual_value = [dict(row) for row in rows]
            
            # Compare with expected
            expected_value = json.loads(expected_output)
            
            # Simple list comparison
            passed = (actual_value == expected_value)
            success = True
        except sqlite3.Error as e:
            error = f"SQLite Error: {str(e)}"
        except Exception as e:
            error = f"Runtime Error: {str(e)}"
        finally:
            conn.close()
            
        runtime_ms = (time.perf_counter() - start_time) * 1000
        
        return {
            "passed": passed,
            "actual": json.dumps(actual_value) if actual_value is not None else None,
            "expected": expected_output,
            "error": error,
            "runtime_ms": runtime_ms
        }

    def run_test_cases(self, query: str, problem: Any) -> List[Dict[str, Any]]:
        """Runs the query against the problem schema."""
        res = self.run_query(query, problem.schema_definition, problem.expected_output)
        return [res]
