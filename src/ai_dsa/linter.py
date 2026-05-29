import subprocess
import json
import tempfile
import os
from typing import List, Dict, Any

class Linter:
    """Wrapper for running Ruff in the background for real-time linting."""
    
    @staticmethod
    def lint_code(code: str) -> List[Dict[str, Any]]:
        """Runs ruff on the provided code string and returns a list of issues."""
        if not code.strip():
            return []
            
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as tf:
            tf.write(code)
            temp_path = tf.name
            
        issues = []
        try:
            # Run ruff check --format json
            # We use --select ALL to find everything, or just defaults.
            # 2026 ruff might have different flags, but this is the standard.
            result = subprocess.run(
                ["ruff", "check", "--format", "json", temp_path],
                capture_output=True,
                text=True
            )
            
            if result.stdout:
                raw_issues = json.loads(result.stdout)
                for issue in raw_issues:
                    # Ruff returns 'location' with row/column
                    issues.append({
                        "line": issue["location"]["row"],
                        "column": issue["location"]["column"],
                        "code": issue["code"],
                        "message": issue["message"],
                        "severity": "yellow" if issue["code"].startswith("W") else "red"
                    })
        except Exception:
            pass
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)
                
        return issues
