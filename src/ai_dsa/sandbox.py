import subprocess
import sys
import os
import signal
import resource
import time
import json
from dataclasses import dataclass, asdict
from typing import Dict, Any, List, Optional
from .codec import deserialize, compare

@dataclass
class ExecutionResult:
    success: bool
    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool
    runtime_ms: float
    actual_value: Any = None

class Sandbox:
    def __init__(self, timeout_sec: int = 5, memory_limit_mb: int = 128):
        self.timeout_sec = timeout_sec
        self.memory_limit_mb = memory_limit_mb

    def _set_limits(self):
        bytes_limit = self.memory_limit_mb * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (bytes_limit, bytes_limit))
        signal.alarm(self.timeout_sec)

    def run_code(self, code: str, problem: Any, test_input: str) -> ExecutionResult:
        import tempfile
        
        # Build Universal Harness
        contract = problem.function
        
        harness_code = f"""
import json
import sys
import re

# Inlined deserializers for the sandbox environment
def parse_list_int(s):
    # Handle brackets, commas, spaces
    s = s.strip().strip("[]")
    if not s: return []
    return [int(x) for x in re.split(r"[,\\\\s]+", s) if x]

DESERIALIZERS = {{
    "int": int,
    "float": float,
    "bool": lambda s: s.strip().lower() == "true",
    "str": lambda s: s.strip().strip("\\"'"),
    "List[int]": parse_list_int,
    "List[str]": lambda s: [x.strip().strip("\\"'") for x in re.split(r"[,\\\\s]+", s.strip().strip("[]")) if x],
}}

def deserialize(value_str, type_hint):
    parser = DESERIALIZERS.get(type_hint)
    return parser(value_str) if parser else value_str

def solve():
    try:
        # Read lines from stdin
        input_data = sys.stdin.read().splitlines()
        params = []
        param_configs = {json.dumps([asdict(p) for p in contract.params])}
        
        for i, config in enumerate(param_configs):
            params.append(deserialize(input_data[i], config['type']))
            
        # Call user function
        result = {contract.name}(*params)
        
        # Print JSON output for precise parsing
        print(json.dumps(result))
    except Exception as e:
        print(f"Runtime Error: {{e}}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    solve()
"""
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as tf:
            tf.write(code + "\n" + harness_code)
            temp_path = tf.name

        start_time = time.perf_counter()
        timed_out = False
        
        try:
            process = subprocess.Popen(
                [sys.executable, temp_path],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                preexec_fn=self._set_limits if os.name != "nt" else None
            )

            try:
                stdout, stderr = process.communicate(input=test_input, timeout=self.timeout_sec)
                exit_code = process.returncode
            except subprocess.TimeoutExpired:
                process.kill()
                stdout, stderr = process.communicate()
                exit_code = -1
                timed_out = True

        except Exception as e:
            stdout = ""
            stderr = str(e)
            exit_code = -1
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)
        
        end_time = time.perf_counter()
        runtime_ms = (end_time - start_time) * 1000

        actual_value = None
        if exit_code == 0 and not timed_out:
            try:
                actual_value = json.loads(stdout.strip())
            except:
                actual_value = stdout.strip()

        return ExecutionResult(
            success=(exit_code == 0 and not timed_out),
            stdout=stdout,
            stderr=stderr,
            exit_code=exit_code,
            timed_out=timed_out,
            runtime_ms=runtime_ms,
            actual_value=actual_value
        )

    def run_test_cases(self, code: str, problem: Any) -> List[Dict[str, Any]]:
        results = []
        for tc in problem.test_cases:
            res = self.run_code(code, problem, tc.input)
            
            # Deserialized comparison
            expected_val = deserialize(tc.expected, problem.function.return_type)
            passed = res.success and compare(res.actual_value, expected_val, problem.function.compare)
            
            results.append({
                "input": tc.input,
                "expected": expected_val,
                "actual": res.actual_value,
                "passed": passed,
                "error": res.stderr if not res.success else None,
                "runtime_ms": res.runtime_ms
            })
        return results
