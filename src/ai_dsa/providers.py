from abc import ABC, abstractmethod
from typing import AsyncGenerator, List, Dict, Any
import json
import asyncio

class AIProvider(ABC):
    @abstractmethod
    async def stream_hint(
        self, problem_description: str, current_code: str, history: List[Dict[str, str]], level: int = 1, mode: str = "DSA"
    ) -> AsyncGenerator[str, None]:
        pass

    @abstractmethod
    async def review_code(
        self, problem_description: str, code: str, mode: str = "DSA"
    ) -> AsyncGenerator[str, None]:
        pass

    @abstractmethod
    async def generate_problem(
        self, mode: str = "random", topic: str = "Any", difficulty: str = "Medium"
    ) -> Dict[str, Any]:
        pass

    @abstractmethod
    async def generate_sql_problem(
        self, topic: str
    ) -> Dict[str, Any]:
        pass

    @abstractmethod
    async def generate_slop(
        self, statement: str
    ) -> AsyncGenerator[str, None]:
        pass

    @abstractmethod
    async def analyze_slop(
        self, code: str
    ) -> AsyncGenerator[str, None]:
        pass

    @abstractmethod
    async def validate_fix(
        self, original: str, rewrite: str
    ) -> AsyncGenerator[str, None]:
        pass

    @abstractmethod
    async def classify_failure(
        self, code: str, problem_description: str, test_results: str
    ) -> str:
        pass

    @abstractmethod
    async def generate_insight(
        self, code: str, problem_description: str
    ) -> str:
        pass
    
    @abstractmethod
    async def get_available_models(self) -> List[str]:
        """Return a list of model IDs available for this provider."""
        return []

    @abstractmethod
    async def reset_history(self) -> None:
        """Clear the internal conversation history."""
        pass
    
    @abstractmethod
    async def ask_question(
        self, problem_description: str, current_code: str, question: str, mode: str = "DSA"
    ) -> AsyncGenerator[str, None]:
        pass

class GeminiProvider(AIProvider):
    def __init__(self, api_key: str, model_name: str = "gemini-3.5-flash"):
        from google import genai
        from google.genai import types
        self.genai = genai
        self.types = types
        self.client = genai.Client(api_key=api_key)
        self.model_name = model_name

    async def _run_stream(self, stream) -> str:
        """Runs a synchronous Gemini stream in a thread and returns the full text."""
        def collect():
            return "".join(chunk.text for chunk in stream)
        return await asyncio.to_thread(collect)

    async def stream_hint(
        self, problem_description: str, current_code: str, history: List[Dict[str, str]], level: int = 1, mode: str = "DSA"
    ) -> AsyncGenerator[str, None]:
        if mode == "SQL":
            role = "SQL Coach"
            instruction = "Coach on query plans, JOIN logic, and indexing. Be Socratic."
        else:
            role = "DSA Coach (Nudge Mode)" if level == 1 else "DSA Coach (Hint Mode)"
            instruction = "Provide a small, high-level nudge." if level == 1 else "Provide a Socratic hint focusing on the next logical step."
            
        history_text = "\n".join(f"{m['role']}: {m['content']}" for m in history[-10:])
        
        prompt = f"System: You are a {role}. {instruction}\nDo NOT give the full solution.\nProblem: {problem_description}\nCode: {current_code}\nHistory: {history_text}"
        
        stream = self.client.models.generate_content_stream(
            model=self.model_name,
            contents=prompt,
            config=self.types.GenerateContentConfig(max_output_tokens=300)
        )
        full_text = await self._run_stream(stream)
        yield full_text


    async def review_code(self, problem_description: str, code: str, mode: str = "DSA") -> AsyncGenerator[str, None]:
        system = "Senior Database Engineer" if mode == "SQL" else "Senior Software Engineer"
        prompt = f"System: {system}. Review for correctness, complexity, and style.\nProblem: {problem_description}\nCode: {code}"
        stream = self.client.models.generate_content_stream(
            model=self.model_name,
            contents=prompt,
            config=self.types.GenerateContentConfig(max_output_tokens=512)
        )
        full_text = await self._run_stream(stream)
        yield full_text

    async def generate_problem(self, mode: str = "random", topic: str = "Any", difficulty: str = "Medium") -> Dict[str, Any]:
        prompt = f"""Generate a {difficulty} DSA problem on {topic}.

Return ONLY a valid JSON object. No markdown, no explanation, no code fences.

RULES FOR test_cases — this is the most important part:
- "input" contains one line per function parameter, in order, separated by \\n
- "expected" is the return value
- Every value must be valid JSON:
    - Lists:    [1, 2, 3]      NOT  1, 2, 3
    - Strings:  "hello"        NOT  hello
    - Numbers:  42             just the number
    - Booleans: true or false  lowercase

EXAMPLES of correct test_cases for different problem types:

Function takes (nums: List[int], target: int) -> List[int]:
  input = "[2,7,11,15]\\n9"      expected = "[0,1]"

Function takes (s: str) -> int:
  input = "\\"anagram\\""          expected = "7"

Function takes (root: List[int], k: int) -> int:  (tree given as level-order list)
  input = "[3,1,4,null,2]\\n1"   expected = "1"

Function takes (grid: List[List[int]]) -> int:
  input = "[[1,0,1],[0,1,0]]"    expected = "3"

Function takes (a: List[int], b: List[int]) -> List[int]:
  input = "[1,2,3]\\n[4,5,6]"    expected = "[1,2,3,4,5,6]"

Function takes (s: str, t: str) -> bool:
  input = "\\"anagram\\"\\n\\"nagaram\\""  expected = "true"

Function takes (n: int) -> List[int]:
  input = "5"                    expected = "[0,1,1,2,3]"

Follow these rules for every test case you generate, regardless of problem type.
"""
        response = await asyncio.to_thread(
            self.client.models.generate_content,
            model=self.model_name,
            contents=prompt,
            config=self.types.GenerateContentConfig(response_mime_type="application/json", max_output_tokens=2048)
        )
        return json.loads(response.text)

    async def generate_sql_problem(self, topic: str) -> Dict[str, Any]:
        prompt = f"Generate a SQL interview problem on {topic}. Return ONLY a valid JSON object with: id, title, difficulty, category, description, schema_definition (SQLite), and expected_output (JSON string)."
        response = await asyncio.to_thread(
            self.client.models.generate_content,
            model=self.model_name,
            contents=prompt,
            config=self.types.GenerateContentConfig(response_mime_type="application/json", max_output_tokens=2048)
        )
        return json.loads(response.text)

    async def generate_slop(self, statement: str) -> AsyncGenerator[str, None]:
        prompt = f"Generate functionally correct but intentionally 'sloppy' code for: {statement}. No markdown."
        stream = self.client.models.generate_content_stream(
            model=self.model_name,
            contents=prompt,
            config=self.types.GenerateContentConfig(max_output_tokens=1024)
        )
        full_text = await self._run_stream(stream)
        yield full_text

    async def analyze_slop(self, code: str) -> AsyncGenerator[str, None]:
        prompt = f"Analyze this code for 'AI slop'. Return ONLY a JSON list of objects with keys: line, severity ('red', 'yellow', 'green'), and message. Code:\n{code}"
        response = await asyncio.to_thread(
            self.client.models.generate_content,
            model=self.model_name,
            contents=prompt,
            config=self.types.GenerateContentConfig(response_mime_type="application/json", max_output_tokens=2048)
        )
        yield response.text

    async def validate_fix(self, original: str, rewrite: str) -> AsyncGenerator[str, None]:
        prompt = f"Compare original slop code with rewrite. Did the user fix the issues?\nOriginal: {original}\nRewrite: {rewrite}"
        stream = self.client.models.generate_content_stream(
            model=self.model_name,
            contents=prompt,
            config=self.types.GenerateContentConfig(max_output_tokens=1024)
        )
        full_text = await self._run_stream(stream)
        yield full_text

    async def classify_failure(self, code: str, problem_description: str, test_results: str) -> str:
        prompt = f"Classify failure into ONE: wrong_algorithm, edge_case_missed, off_by_one, syntax_error, timeout, unknown.\nProblem: {problem_description}\nCode: {code}\nResults: {test_results}"
        response = await asyncio.to_thread(
            self.client.models.generate_content,
            model=self.model_name,
            contents=prompt,
            config=self.types.GenerateContentConfig(max_output_tokens=20)
        )
        category = response.text.strip().lower()
        valid = {"wrong_algorithm", "edge_case_missed", "off_by_one", "syntax_error", "timeout", "unknown"}
        for v in valid:
            if v in category: return v
        return "unknown"

    async def generate_insight(self, code: str, problem_description: str) -> str:
        prompt = f"Provide ONE concise sentence (max 20 words) takeaway for this solution.\nProblem: {problem_description}\nCode: {code}"
        response = await asyncio.to_thread(
            self.client.models.generate_content,
            model=self.model_name,
            contents=prompt,
            config=self.types.GenerateContentConfig(max_output_tokens=100)
        )
        return response.text.strip()
    
    async def get_available_models(self) -> List[str]:
        """Return a list of model IDs available for this provider."""
        return []

    async def reset_history(self) -> None:
        """Clear the internal conversation history."""
        pass

    async def ask_question(
        self, problem_description: str, current_code: str, question: str, mode: str = "DSA"
    ) -> AsyncGenerator[str, None]:
        prompt = f"Problem: {problem_description}\nCode: {current_code}\nQuestion: {question}"
        stream = self.client.models.generate_content_stream(
            model=self.model_name,
            contents=prompt,
            config=self.types.GenerateContentConfig(max_output_tokens=512)
        )
        full_text = await self._run_stream(stream)
        yield full_text

class AnthropicProvider(AIProvider):
    def __init__(self, api_key: str, model_name: str = "claude-opus-4-8"):
        from anthropic import AsyncAnthropic
        self.client = AsyncAnthropic(api_key=api_key)
        self.model_name = model_name

    async def stream_hint(self, problem_description: str, current_code: str, history: List[Dict[str, str]], level: int = 1, mode: str = "DSA") -> AsyncGenerator[str, None]:
        prompt = f"Mode: {mode}. Level: {level}. Problem: {problem_description}\nUser Code: {current_code}\nGive a Socratic hint. No solution."
        async with self.client.messages.stream(model=self.model_name, max_tokens=300, messages=[{"role": "user", "content": prompt}]) as stream:
            async for text in stream.text_stream: yield text

    async def review_code(self, problem_description: str, code: str, mode: str = "DSA") -> AsyncGenerator[str, None]:
        prompt = f"Mode: {mode}. Problem: {problem_description}\nCode: {code}\nReview for correctness and complexity."
        async with self.client.messages.stream(model=self.model_name, max_tokens=512, messages=[{"role": "user", "content": prompt}]) as stream:
            async for text in stream.text_stream: yield text

    async def generate_problem(self, mode: str = "random", topic: str = "Any", difficulty: str = "Medium") -> Dict[str, Any]:
        prompt = f"""Generate a {difficulty} DSA problem on {topic}.

Return ONLY a valid JSON object. No markdown, no explanation, no code fences.

RULES FOR test_cases — this is the most important part:
- "input" contains one line per function parameter, in order, separated by \\n
- "expected" is the return value
- Every value must be valid JSON:
    - Lists:    [1, 2, 3]      NOT  1, 2, 3
    - Strings:  "hello"        NOT  hello
    - Numbers:  42             just the number
    - Booleans: true or false  lowercase

EXAMPLES of correct test_cases for different problem types:

Function takes (nums: List[int], target: int) -> List[int]:
  input = "[2,7,11,15]\\n9"      expected = "[0,1]"

Function takes (s: str) -> int:
  input = "\\"anagram\\""          expected = "7"

Function takes (root: List[int], k: int) -> int:  (tree given as level-order list)
  input = "[3,1,4,null,2]\\n1"   expected = "1"

Function takes (grid: List[List[int]]) -> int:
  input = "[[1,0,1],[0,1,0]]"    expected = "3"

Function takes (a: List[int], b: List[int]) -> List[int]:
  input = "[1,2,3]\\n[4,5,6]"    expected = "[1,2,3,4,5,6]"

Function takes (s: str, t: str) -> bool:
  input = "\\"anagram\\"\\n\\"nagaram\\""  expected = "true"

Function takes (n: int) -> List[int]:
  input = "5"                    expected = "[0,1,1,2,3]"

Follow these rules for every test case you generate, regardless of problem type.
"""
        message = await self.client.messages.create(model=self.model_name, max_tokens=2048, messages=[{"role": "user", "content": prompt}])
        return json.loads(message.content[0].text)

    async def generate_sql_problem(self, topic: str) -> Dict[str, Any]:
        prompt = f"Generate a SQL interview problem on {topic}. Return ONLY a valid JSON object with: id, title, difficulty, category, description, schema_definition (SQLite), and expected_output (JSON string)."
        message = await self.client.messages.create(model=self.model_name, max_tokens=2048, messages=[{"role": "user", "content": prompt}])
        return json.loads(message.content[0].text)

    async def generate_slop(self, statement: str) -> AsyncGenerator[str, None]:
        prompt = f"Generate functionally correct but intentionally 'sloppy' code for: {statement}. No markdown."
        async with self.client.messages.stream(model=self.model_name, max_tokens=1024, messages=[{"role": "user", "content": prompt}]) as stream:
            async for text in stream.text_stream: yield text

    async def analyze_slop(self, code: str) -> AsyncGenerator[str, None]:
        prompt = f"Analyze this code for 'AI slop'. Return ONLY a JSON list of objects with keys: line, severity, and message. Code:\n{code}"
        message = await self.client.messages.create(model=self.model_name, max_tokens=2048, messages=[{"role": "user", "content": prompt}])
        yield message.content[0].text

    async def validate_fix(self, original: str, rewrite: str) -> AsyncGenerator[str, None]:
        prompt = f"Compare original slop code with rewrite. Did the user fix the issues?\nOriginal: {original}\nRewrite: {rewrite}"
        async with self.client.messages.stream(model=self.model_name, max_tokens=1024, messages=[{"role": "user", "content": prompt}]) as stream:
            async for text in stream.text_stream: yield text

    async def classify_failure(self, code: str, problem_description: str, test_results: str) -> str:
        prompt = f"Classify failure into ONE: wrong_algorithm, edge_case_missed, off_by_one, syntax_error, timeout, unknown.\nProblem: {problem_description}\nCode: {code}\nResults: {test_results}"
        message = await self.client.messages.create(model=self.model_name, max_tokens=20, messages=[{"role": "user", "content": prompt}])
        category = message.content[0].text.strip().lower()
        valid = {"wrong_algorithm", "edge_case_missed", "off_by_one", "syntax_error", "timeout", "unknown"}
        for v in valid:
            if v in category: return v
        return "unknown"

    async def generate_insight(self, code: str, problem_description: str) -> str:
        prompt = f"Provide ONE concise sentence (max 20 words) takeaway for this solution.\nProblem: {problem_description}\nCode: {code}"
        message = await self.client.messages.create(model=self.model_name, max_tokens=100, messages=[{"role": "user", "content": prompt}])
        return message.content[0].text.strip()
    async def get_available_models(self) -> List[str]:
        return []

    async def reset_history(self) -> None:
        pass
    
    async def ask_question(self, problem_description: str, current_code: str, question: str, mode: str = "DSA") -> AsyncGenerator[str, None]:
        prompt = f"Problem: {problem_description}\nCode: {current_code}\nQuestion: {question}"
        stream = self.client.models.generate_content_stream(
            model=self.model_name,
            contents=prompt,
            config=self.types.GenerateContentConfig(max_output_tokens=512)
        )
        full_text = await self._run_stream(stream)
        yield full_text

class OpenAIProvider(AIProvider):
    def __init__(self, api_key: str, model_name: str = "gpt-4.1-mini"):
        from openai import AsyncOpenAI
        self.client = AsyncOpenAI(api_key=api_key)
        self.model_name = model_name

    async def stream_hint(self, problem_description: str, current_code: str, history: List[Dict[str, str]], level: int = 1, mode: str = "DSA") -> AsyncGenerator[str, None]:
        prompt = f"Mode: {mode}. Level: {level}. Problem: {problem_description}\nUser Code: {current_code}\nGive a Socratic hint. No solution."
        stream = await self.client.chat.completions.create(model=self.model_name, messages=[{"role": "user", "content": prompt}], max_tokens=300, stream=True)
        async for chunk in stream:
            if chunk.choices[0].delta.content: yield chunk.choices[0].delta.content

    async def review_code(self, problem_description: str, code: str, mode: str = "DSA") -> AsyncGenerator[str, None]:
        prompt = f"Mode: {mode}. Problem: {problem_description}\nCode: {code}\nReview for correctness and complexity."
        stream = await self.client.chat.completions.create(model=self.model_name, messages=[{"role": "user", "content": prompt}], max_tokens=512, stream=True)
        async for chunk in stream:
            if chunk.choices[0].delta.content: yield chunk.choices[0].delta.content

    async def generate_problem(self, mode: str = "random", topic: str = "Any", difficulty: str = "Medium") -> Dict[str, Any]:
        prompt = f"""Generate a {difficulty} DSA problem on {topic}.

Return ONLY a valid JSON object. No markdown, no explanation, no code fences.

RULES FOR test_cases — this is the most important part:
- "input" contains one line per function parameter, in order, separated by \\n
- "expected" is the return value
- Every value must be valid JSON:
    - Lists:    [1, 2, 3]      NOT  1, 2, 3
    - Strings:  "hello"        NOT  hello
    - Numbers:  42             just the number
    - Booleans: true or false  lowercase

EXAMPLES of correct test_cases for different problem types:

Function takes (nums: List[int], target: int) -> List[int]:
  input = "[2,7,11,15]\\n9"      expected = "[0,1]"

Function takes (s: str) -> int:
  input = "\\"anagram\\""          expected = "7"

Function takes (root: List[int], k: int) -> int:  (tree given as level-order list)
  input = "[3,1,4,null,2]\\n1"   expected = "1"

Function takes (grid: List[List[int]]) -> int:
  input = "[[1,0,1],[0,1,0]]"    expected = "3"

Function takes (a: List[int], b: List[int]) -> List[int]:
  input = "[1,2,3]\\n[4,5,6]"    expected = "[1,2,3,4,5,6]"

Function takes (s: str, t: str) -> bool:
  input = "\\"anagram\\"\\n\\"nagaram\\""  expected = "true"

Function takes (n: int) -> List[int]:
  input = "5"                    expected = "[0,1,1,2,3]"

Follow these rules for every test case you generate, regardless of problem type.
"""
        response = await self.client.chat.completions.create(model=self.model_name, messages=[{"role": "user", "content": prompt}], max_tokens=2048, response_format={"type": "json_object"})
        return json.loads(response.choices[0].message.content)

    async def generate_sql_problem(self, topic: str) -> Dict[str, Any]:
        prompt = f"Generate a SQL interview problem on {topic}. Return ONLY a valid JSON object with: id, title, difficulty, category, description, schema_definition (SQLite), and expected_output (JSON string)."
        response = await self.client.chat.completions.create(model=self.model_name, messages=[{"role": "user", "content": prompt}], max_tokens=2048, response_format={"type": "json_object"})
        return json.loads(response.choices[0].message.content)

    async def generate_slop(self, statement: str) -> AsyncGenerator[str, None]:
        prompt = f"Generate functionally correct but intentionally 'sloppy' code for: {statement}. No markdown."
        stream = await self.client.chat.completions.create(model=self.model_name, messages=[{"role": "user", "content": prompt}], max_tokens=1024, stream=True)
        async for chunk in stream:
            if chunk.choices[0].delta.content: yield chunk.choices[0].delta.content

    async def analyze_slop(self, code: str) -> AsyncGenerator[str, None]:
        prompt = f"Analyze this code for 'AI slop'. Return ONLY a JSON list of objects with keys: line, severity, and message. Code:\n{code}"
        response = await self.client.chat.completions.create(model=self.model_name, messages=[{"role": "user", "content": prompt}], max_tokens=2048, response_format={"type": "json_object"})
        yield response.choices[0].message.content

    async def validate_fix(self, original: str, rewrite: str) -> AsyncGenerator[str, None]:
        prompt = f"Compare original slop code with rewrite. Did the user fix the issues?\nOriginal: {original}\nRewrite: {rewrite}"
        stream = await self.client.chat.completions.create(model=self.model_name, messages=[{"role": "user", "content": prompt}], max_tokens=1024, stream=True)
        async for chunk in stream:
            if chunk.choices[0].delta.content: yield chunk.choices[0].delta.content

    async def classify_failure(self, code: str, problem_description: str, test_results: str) -> str:
        prompt = f"Classify failure into ONE: wrong_algorithm, edge_case_missed, off_by_one, syntax_error, timeout, unknown.\nProblem: {problem_description}\nCode: {code}\nResults: {test_results}"
        response = await self.client.chat.completions.create(model=self.model_name, messages=[{"role": "user", "content": prompt}], max_tokens=20)
        category = response.choices[0].message.content.strip().lower()
        valid = {"wrong_algorithm", "edge_case_missed", "off_by_one", "syntax_error", "timeout", "unknown"}
        for v in valid:
            if v in category: return v
        return "unknown"

    async def generate_insight(self, code: str, problem_description: str) -> str:
        prompt = f"Provide ONE concise sentence (max 20 words) takeaway for this solution.\nProblem: {problem_description}\nCode: {code}"
        response = await self.client.chat.completions.create(model=self.model_name, messages=[{"role": "user", "content": prompt}], max_tokens=100)
        return response.choices[0].message.content.strip()
    
    async def get_available_models(self) -> List[str]:
        return []

    async def reset_history(self) -> None:
        pass
    
    async def ask_question(self, problem_description: str, current_code: str, question: str, mode: str = "DSA") -> AsyncGenerator[str, None]:
        prompt = f"Problem: {problem_description}\nCode: {current_code}\nQuestion: {question}"
        stream = await self.client.chat.completions.create(model=self.model_name, messages=[{"role": "user", "content": prompt}], max_tokens=512, stream=True)
        async for chunk in stream:
            if chunk.choices[0].delta.content: yield chunk.choices[0].delta.content

class OllamaProvider(AIProvider):
    def __init__(self, model_name: str = "llama4-maverick", base_url: str = "http://localhost:11434"):
        self.model_name = model_name
        self.base_url = base_url

    async def _stream_request(self, prompt: str, max_tokens: int = 300) -> AsyncGenerator[str, None]:
        import httpx
        async with httpx.AsyncClient(timeout=30.0) as client:
            async with client.stream("POST", f"{self.base_url}/api/generate", json={"model": self.model_name, "prompt": prompt, "options": {"num_predict": max_tokens}}) as response:
                async for line in response.aiter_lines():
                    if line:
                        data = json.loads(line)
                        yield data.get("response", "")
                        if data.get("done"): break

    async def stream_hint(self, problem_description: str, current_code: str, history: List[Dict[str, str]], level: int = 1, mode: str = "DSA") -> AsyncGenerator[str, None]:
        prompt = f"Mode: {mode}. Level: {level}. Problem: {problem_description}\nUser Code: {current_code}\nGive a Socratic hint. No solution."
        async for chunk in self._stream_request(prompt, max_tokens=300): yield chunk

    async def review_code(self, problem_description: str, code: str, mode: str = "DSA") -> AsyncGenerator[str, None]:
        prompt = f"Mode: {mode}. Problem: {problem_description}\nCode: {code}\nReview for correctness and complexity."
        async for chunk in self._stream_request(prompt, max_tokens=512): yield chunk

    async def generate_problem(self, mode: str = "random", topic: str = "Any", difficulty: str = "Medium") -> Dict[str, Any]:
        import httpx
        prompt = f"""Generate a {difficulty} DSA problem on {topic}.

Return ONLY a valid JSON object. No markdown, no explanation, no code fences.

RULES FOR test_cases — this is the most important part:
- "input" contains one line per function parameter, in order, separated by \\n
- "expected" is the return value
- Every value must be valid JSON:
    - Lists:    [1, 2, 3]      NOT  1, 2, 3
    - Strings:  "hello"        NOT  hello
    - Numbers:  42             just the number
    - Booleans: true or false  lowercase

EXAMPLES of correct test_cases for different problem types:

Function takes (nums: List[int], target: int) -> List[int]:
  input = "[2,7,11,15]\\n9"      expected = "[0,1]"

Function takes (s: str) -> int:
  input = "\\"anagram\\""          expected = "7"

Function takes (root: List[int], k: int) -> int:  (tree given as level-order list)
  input = "[3,1,4,null,2]\\n1"   expected = "1"

Function takes (grid: List[List[int]]) -> int:
  input = "[[1,0,1],[0,1,0]]"    expected = "3"

Function takes (a: List[int], b: List[int]) -> List[int]:
  input = "[1,2,3]\\n[4,5,6]"    expected = "[1,2,3,4,5,6]"

Function takes (s: str, t: str) -> bool:
  input = "\\"anagram\\"\\n\\"nagaram\\""  expected = "true"

Function takes (n: int) -> List[int]:
  input = "5"                    expected = "[0,1,1,2,3]"

Follow these rules for every test case you generate, regardless of problem type.
"""
        async with httpx.AsyncClient() as client:
            res = await client.post(f"{self.base_url}/api/generate", json={"model": self.model_name, "prompt": prompt, "stream": False, "options": {"num_predict": 2048}})
            return json.loads(res.json()["response"])

    async def generate_sql_problem(self, topic: str) -> Dict[str, Any]:
        import httpx
        prompt = f"Generate a SQL interview problem on {topic}. Return ONLY a valid JSON object with: id, title, difficulty, category, description, schema_definition (SQLite), and expected_output (JSON string)."
        async with httpx.AsyncClient() as client:
            res = await client.post(f"{self.base_url}/api/generate", json={"model": self.model_name, "prompt": prompt, "stream": False, "options": {"num_predict": 2048}})
            return json.loads(res.json()["response"])

    async def generate_slop(self, statement: str) -> AsyncGenerator[str, None]:
        prompt = f"Generate functionally correct but intentionally 'sloppy' code for: {statement}. No markdown."
        async for chunk in self._stream_request(prompt, max_tokens=1024): yield chunk

    async def analyze_slop(self, code: str) -> AsyncGenerator[str, None]:
        import httpx
        prompt = f"Analyze this code for 'AI slop'. Return ONLY a JSON list of objects with keys: line, severity, and message. Code:\n{code}"
        async with httpx.AsyncClient() as client:
            res = await client.post(f"{self.base_url}/api/generate", json={"model": self.model_name, "prompt": prompt, "stream": False, "options": {"num_predict": 2048}})
            yield res.json()["response"]

    async def validate_fix(self, original: str, rewrite: str) -> AsyncGenerator[str, None]:
        prompt = f"Compare original slop code with rewrite. Did the user fix the issues?\nOriginal: {original}\nRewrite: {rewrite}"
        async for chunk in self._stream_request(prompt, max_tokens=1024): yield chunk

    async def classify_failure(self, code: str, problem_description: str, test_results: str) -> str:
        import httpx
        prompt = f"Classify failure into ONE: wrong_algorithm, edge_case_missed, off_by_one, syntax_error, timeout, unknown.\nProblem: {problem_description}\nCode: {code}\nResults: {test_results}"
        async with httpx.AsyncClient() as client:
            res = await client.post(f"{self.base_url}/api/generate", json={"model": self.model_name, "prompt": prompt, "stream": False, "options": {"num_predict": 20}})
            category = res.json().get("response", "").strip().lower()
            valid = {"wrong_algorithm", "edge_case_missed", "off_by_one", "syntax_error", "timeout", "unknown"}
            for v in valid:
                if v in category: return v
            return "unknown"

    async def generate_insight(self, code: str, problem_description: str) -> str:
        import httpx
        prompt = f"Provide ONE concise sentence (max 20 words) takeaway for this solution.\nProblem: {problem_description}\nCode: {code}"
        async with httpx.AsyncClient() as client:
            res = await client.post(f"{self.base_url}/api/generate", json={"model": self.model_name, "prompt": prompt, "stream": False, "options": {"num_predict": 100}})
            return res.json().get("response", "").strip()
        
    async def get_available_models(self) -> List[str]:
        return []

    async def reset_history(self) -> None:
        pass
    
    async def ask_question(self, problem_description: str, current_code: str, question: str, mode: str = "DSA") -> AsyncGenerator[str, None]:
        prompt = f"Problem: {problem_description}\nCode: {current_code}\nQuestion: {question}"
        async for chunk in self._stream_request(prompt, max_tokens=512): yield chunk