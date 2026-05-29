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
    """Detailed results of a code execution run."""
    success: bool
    actual_value: Any
    stdout: str
    stderr: str
    runtime_ms: float
    timeout: bool = False
    memory_limit: bool = False

class Sandbox:
    """Executes Python code in a restricted environment."""
    def __init__(self, timeout_sec: int = 2, memory_mb: int = 128):
        self.timeout_sec = timeout_sec
        self.memory_limit = memory_mb * 1024 * 1024

    def run_code(self, code: str, func_name: str, args: List[Any]) -> ExecutionResult:
        """Runs the provided code with arguments and captures the result with robust error detection."""
        harness = f"""
import json
import sys

{code}

def main():
    try:
        args = {json.dumps(args)}
        res = {func_name}(*args)
        # Unique marker to identify the result line
        print("___RESULT_START___")
        print(json.dumps({{"result": res}}))
    except Exception as e:
        import traceback
        print(json.dumps({{"error": str(e), "traceback": traceback.format_exc()}}), file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
"""
        start = time.perf_counter()
        
        def preexec():
            # Memory limit
            resource.setrlimit(resource.RLIMIT_AS, (self.memory_limit, self.memory_limit))
            # CPU time limit
            signal.alarm(self.timeout_sec)

        try:
            proc = subprocess.Popen(
                [sys.executable, "-c", harness],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                preexec_fn=preexec
            )
            stdout, stderr = proc.communicate()
            end = time.perf_counter()
            
            runtime = (end - start) * 1000
            
            # Check for timeout/signals
            timeout = False
            memory_limit = False
            
            # SIGALRM is 14. If killed by signal, returncode is -signal
            if proc.returncode == -signal.SIGALRM:
                timeout = True
            elif proc.returncode != 0:
                # Basic heuristic for memory limit (often returns 1 on OOM in subprocess)
                # or check for specific segments in stderr
                if "MemoryError" in stderr or "MemoryError" in stdout:
                    memory_limit = True

            if proc.returncode == 0:
                # Find result after marker
                lines = stdout.splitlines()
                try:
                    marker_idx = lines.index("___RESULT_START___")
                    data = json.loads(lines[marker_idx + 1])
                    return ExecutionResult(True, data["result"], stdout, stderr, runtime)
                except (ValueError, IndexError, json.JSONDecodeError):
                    return ExecutionResult(False, None, stdout, "Internal Error: Result marker not found or invalid JSON", runtime)
            else:
                return ExecutionResult(False, None, stdout, stderr, runtime, timeout=timeout, memory_limit=memory_limit)
                
        except Exception as e:
            return ExecutionResult(False, None, "", str(e), 0.0)

    def run_test_cases(self, code: str, problem: Any) -> List[Dict[str, Any]]:
        """Runs user code against all test cases for a specific problem with detailed error reporting."""
        results = []
        for tc in problem.test_cases:
            # Parse inputs based on contract
            raw_args = tc.input.splitlines()
            parsed_args = []
            for i, arg in enumerate(raw_args):
                if i < len(problem.function.params):
                    parsed_args.append(deserialize(arg, problem.function.params[i].type))
            
            res = self.run_code(code, problem.function.name, parsed_args)
            
            expected_val = deserialize(tc.expected, problem.function.return_type)
            passed = compare(res.actual_value, expected_val, problem.function.compare)
            
            error_msg = res.stderr if not res.success else None
            if res.timeout:
                error_msg = f"Time Limit Exceeded (> {self.timeout_sec}s)"
            elif res.memory_limit:
                error_msg = "Memory Limit Exceeded"
            
            results.append({
                "input": tc.input,
                "expected": tc.expected,
                "actual": res.actual_value,
                "passed": passed,
                "error": error_msg,
                "runtime_ms": res.runtime_ms
            })
        return results
