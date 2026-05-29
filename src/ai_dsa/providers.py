from abc import ABC, abstractmethod
from typing import AsyncGenerator, List, Dict, Any
import os
import json

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

class GeminiProvider(AIProvider):
    def __init__(self, api_key: str, model_name: str = "gemini-2.0-flash"):
        from google import genai
        from google.genai import types
        self.genai = genai
        self.types = types
        self.client = genai.Client(api_key=api_key)
        self.model_name = model_name

    async def stream_hint(
        self, problem_description: str, current_code: str, history: List[Dict[str, str]], level: int = 1, mode: str = "DSA"
    ) -> AsyncGenerator[str, None]:
        if mode == "SQL":
            role = "SQL Coach"
            instruction = "Coach on query plans, JOIN logic, and indexing. Be Socratic."
        else:
            role = "DSA Coach (Nudge Mode)" if level == 1 else "DSA Coach (Hint Mode)"
            instruction = "Provide a small, high-level nudge." if level == 1 else "Provide a Socratic hint focusing on the next logical step."
        
        prompt = f"""
System: You are a {role}. {instruction}
Do NOT give the full solution.

Problem/Schema: {problem_description}
Current Solution:
{current_code}

Response:"""
        response = self.client.models.generate_content_stream(
            model=self.model_name,
            contents=prompt,
            config=self.types.GenerateContentConfig(max_output_tokens=300)
        )
        for chunk in response:
            yield chunk.text

    async def review_code(
        self, problem_description: str, code: str, mode: str = "DSA"
    ) -> AsyncGenerator[str, None]:
        if mode == "SQL":
            system = "You are a Senior Database Engineer. Review this SQL query for performance, correctness, and idiomatic style."
        else:
            system = "You are a Senior Engineer. Perform a deep code review. Check for correctness, Big O complexity, and edge cases."

        prompt = f"""
System: {system}

Problem/Schema: {problem_description}
Code to Review:
{code}

Review:"""
        response = self.client.models.generate_content_stream(
            model=self.model_name,
            contents=prompt,
            config=self.types.GenerateContentConfig(max_output_tokens=512)
        )
        for chunk in response:
            yield chunk.text

    async def generate_problem(
        self, mode: str = "random", topic: str = "Any", difficulty: str = "Medium"
    ) -> Dict[str, Any]:
        if mode == "specific":
            goal = f"the specific LeetCode-style problem named: {topic}"
        elif mode == "suggested":
            goal = "a problem you think would be most beneficial for a developer to practice right now, focusing on fundamental patterns like sliding window, DFS, or dynamic programming"
        else:
            goal = f"a random {difficulty} {topic} problem"

        prompt = f"""
Generate a Data Structures and Algorithms (DSA) problem.
The goal is to generate {goal}.

Return ONLY a valid JSON object matching this schema exactly:
{{
    "id": "kebab-case-id",
    "title": "Problem Title",
    "difficulty": "Easy|Medium|Hard",
    "topic": "The Topic",
    "description": "Detailed markdown description",
    "constraints": ["Constraint 1", "Constraint 2"],
    "function": {{
        "name": "functionName",
        "return_type": "int|float|str|bool|List[int]|List[str]",
        "compare": "exact|sorted",
        "params": [
            {{"name": "p1", "type": "List[int]"}},
            {{"name": "p2", "type": "int"}}
        ]
    }},
    "test_cases": [
        {{"input": "param1_val\\nparam2_val", "expected": "result_val"}},
        {{"input": "param1_val\\nparam2_val", "expected": "result_val"}}
    ]
}}
Ensure the test cases are valid and exhaustive.
"""
        response = self.client.models.generate_content(
            model=self.model_name,
            contents=prompt,
            config=self.types.GenerateContentConfig(
                response_mime_type="application/json",
                max_output_tokens=2048
            )
        )
        return json.loads(response.text)

    async def ask_question(
        self, problem_description: str, current_code: str, question: str, mode: str = "DSA"
    ) -> AsyncGenerator[str, None]:
        system = "Answer concisely."
        if mode == "SQL":
            system += " You are a SQL expert focusing on database best practices."
        
        prompt = f"System: {system}\nProblem/Schema: {problem_description}\nSolution: {current_code}\nQuestion: {question}"
        response = self.client.models.generate_content_stream(
            model=self.model_name,
            contents=prompt,
            config=self.types.GenerateContentConfig(max_output_tokens=512)
        )
        for chunk in response:
            yield chunk.text

    async def generate_slop(self, statement: str) -> AsyncGenerator[str, None]:
        prompt = f"""
System: You are an expert at generating "AI slop" code. 
Given a problem statement, generate a solution that is functionally correct but intentionally "sloppy".
Slop includes: redundant comments, overly verbose logic, common AI patterns (like always using 'result = []'), 
unnecessary try/except blocks, and poor naming.

Problem Statement:
{statement}

Generate ONLY the code, no markdown wrappers:"""
        response = self.client.models.generate_content_stream(
            model=self.model_name,
            contents=prompt,
            config=self.types.GenerateContentConfig(max_output_tokens=1024)
        )
        for chunk in response:
            yield chunk.text

    async def generate_sql_problem(self, topic: str) -> Dict[str, Any]:
        prompt = f"""
Generate a SQL interview problem.
Topic/Focus: {topic}

Return ONLY a valid JSON object matching this schema exactly:
{{
    "id": "kebab-case-id",
    "title": "Problem Title",
    "difficulty": "Easy|Medium|Hard",
    "category": "The Category",
    "description": "Detailed markdown problem statement",
    "schema_definition": "SQL CREATE and INSERT statements to setup the environment",
    "expected_output": "JSON string representing the expected list of result dicts"
}}
Ensure the schema_definition is valid SQLite and includes enough seed data to test the query.
"""
        response = self.client.models.generate_content(
            model=self.model_name,
            contents=prompt,
            config=self.types.GenerateContentConfig(
                response_mime_type="application/json",
                max_output_tokens=2048
            )
        )
        return json.loads(response.text)

    async def generate_slop(self, statement: str) -> AsyncGenerator[str, None]:
        yield "# Slop generation not implemented for this provider."

    async def analyze_slop(self, code: str) -> AsyncGenerator[str, None]:
        prompt = f"""
System: You are an expert at identifying "AI slop" in code. 
Analyze the following code and return a JSON list of issues.
Each issue must have:
- line: int (1-indexed)
- severity: "red" (correctness), "yellow" (slop/verbose), or "green" (style)
- message: str (brief description)

Code:
{code}

Return ONLY a valid JSON list of objects:"""
        response = self.client.models.generate_content(
            model=self.model_name,
            contents=prompt,
            config=self.types.GenerateContentConfig(
                response_mime_type="application/json",
                max_output_tokens=2048
            )
        )
        yield response.text

    async def validate_fix(self, original: str, rewrite: str) -> AsyncGenerator[str, None]:
        prompt = f"""
System: Compare the original "slop" code with the user's rewrite. 
Determine if they genuinely fixed the issues (correctness, slop, style) or just "moved the furniture".

Original:
{original}

Rewrite:
{rewrite}

Verdict:"""
        response = self.client.models.generate_content_stream(
            model=self.model_name,
            contents=prompt,
            config=self.types.GenerateContentConfig(max_output_tokens=1024)
        )
        for chunk in response:
            yield chunk.text

    async def classify_failure(self, code: str, problem_description: str, test_results: str) -> str:
        prompt = f"""
System: Classify the following coding failure into exactly ONE of these categories:
- wrong_algorithm
- edge_case_missed
- off_by_one
- syntax_error
- timeout
- unknown

Problem: {problem_description}
Code:
{code}
Results:
{test_results}

Category:"""
        response = self.client.models.generate_content(
            model=self.model_name,
            contents=prompt,
            config=self.types.GenerateContentConfig(max_output_tokens=20)
        )
        category = response.text.strip().lower()
        valid = {"wrong_algorithm", "edge_case_missed", "off_by_one", "syntax_error", "timeout", "unknown"}
        for v in valid:
            if v in category:
                return v
        return "unknown"

    async def generate_insight(self, code: str, problem_description: str) -> str:
        prompt = f"""
System: Analyze the following solution and provide ONE concise sentence (max 20 words) 
highlighting the most important takeaway or pattern demonstrated.

Problem: {problem_description}
Code:
{code}

Insight:"""
        response = self.client.models.generate_content(
            model=self.model_name,
            contents=prompt,
            config=self.types.GenerateContentConfig(max_output_tokens=100)
        )
        return response.text.strip()

class AnthropicProvider(AIProvider):
    def __init__(self, api_key: str, model_name: str = "claude-3-5-sonnet-20241022"):
        from anthropic import AsyncAnthropic
        self.client = AsyncAnthropic(api_key=api_key)
        self.model_name = model_name

    async def stream_hint(
        self, problem_description: str, current_code: str, history: List[Dict[str, str]], level: int = 1, mode: str = "DSA"
    ) -> AsyncGenerator[str, None]:
        prompt = f"Mode: {mode}. Level: {level}. Problem: {problem_description}\nUser Code: {current_code}\nAnalyze progress. Give a Socratic hint on the next step. No solution."
        async with self.client.messages.stream(
            model=self.model_name,
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}]
        ) as stream:
            async for text in stream.text_stream:
                yield text

    async def review_code(
        self, problem_description: str, code: str, mode: str = "DSA"
    ) -> AsyncGenerator[str, None]:
        prompt = f"Mode: {mode}. Problem: {problem_description}\nCode: {code}\nReview for correctness and complexity."
        async with self.client.messages.stream(
            model=self.model_name,
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}]
        ) as stream:
            async for text in stream.text_stream:
                yield text

    async def generate_problem(
        self, topic: str, difficulty: str
    ) -> Dict[str, Any]:
        prompt = f"Generate a DSA problem on {topic} ({difficulty}). Return ONLY valid JSON."
        message = await self.client.messages.create(
            model=self.model_name,
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}]
        )
        return json.loads(message.content[0].text)

    async def generate_sql_problem(self, topic: str) -> Dict[str, Any]:
        return {}

    async def generate_slop(self, statement: str) -> AsyncGenerator[str, None]:
        yield "# Slop generation not implemented for this provider."

    async def analyze_slop(self, code: str) -> AsyncGenerator[str, None]:
        yield "Slop analysis not implemented for this provider."

    async def validate_fix(self, original: str, rewrite: str) -> AsyncGenerator[str, None]:
        yield "Fix validation not implemented for this provider."

    async def classify_failure(self, code: str, problem_description: str, test_results: str) -> str:
        return "unknown"

    async def generate_insight(self, code: str, problem_description: str) -> str:
        return ""

class OpenAIProvider(AIProvider):
    def __init__(self, api_key: str, model_name: str = "gpt-4o"):
        from openai import AsyncOpenAI
        self.client = AsyncOpenAI(api_key=api_key)
        self.model_name = model_name

    async def stream_hint(
        self, problem_description: str, current_code: str, history: List[Dict[str, str]], level: int = 1, mode: str = "DSA"
    ) -> AsyncGenerator[str, None]:
        prompt = f"Mode: {mode}. Level: {level}. Problem: {problem_description}\nUser Code: {current_code}\nGive a specific Socratic hint. No solution."
        stream = await self.client.chat.completions.create(
            model=self.model_name,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=300,
            stream=True,
        )
        async for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    async def review_code(
        self, problem_description: str, code: str, mode: str = "DSA"
    ) -> AsyncGenerator[str, None]:
        prompt = f"Mode: {mode}. Problem: {problem_description}\nCode: {code}\nReview for correctness and complexity."
        stream = await self.client.chat.completions.create(
            model=self.model_name,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=512,
            stream=True,
        )
        async for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    async def generate_problem(
        self, topic: str, difficulty: str
    ) -> Dict[str, Any]:
        prompt = f"Generate a DSA problem on {topic} ({difficulty}). Return ONLY valid JSON."
        response = await self.client.chat.completions.create(
            model=self.model_name,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=2048,
            response_format={"type": "json_object"}
        )
        return json.loads(response.choices[0].message.content)

    async def generate_sql_problem(self, topic: str) -> Dict[str, Any]:
        return {}

    async def generate_slop(self, statement: str) -> AsyncGenerator[str, None]:
        yield "# Slop generation not implemented for this provider."

    async def analyze_slop(self, code: str) -> AsyncGenerator[str, None]:
        yield "Slop analysis not implemented for this provider."

    async def validate_fix(self, original: str, rewrite: str) -> AsyncGenerator[str, None]:
        yield "Fix validation not implemented for this provider."

    async def classify_failure(self, code: str, problem_description: str, test_results: str) -> str:
        return "unknown"

    async def generate_insight(self, code: str, problem_description: str) -> str:
        return ""

class OllamaProvider(AIProvider):
    def __init__(self, model_name: str = "llama3", base_url: str = "http://localhost:11434"):
        self.model_name = model_name
        self.base_url = base_url

    async def _stream_request(self, prompt: str, max_tokens: int = 300) -> AsyncGenerator[str, None]:
        import httpx
        async with httpx.AsyncClient(timeout=30.0) as client:
            async with client.stream(
                "POST", 
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model_name, 
                    "prompt": prompt,
                    "options": {"num_predict": max_tokens}
                }
            ) as response:
                async for line in response.aiter_lines():
                    if line:
                        data = json.loads(line)
                        yield data.get("response", "")
                        if data.get("done"):
                            break

    async def stream_hint(
        self, problem_description: str, current_code: str, history: List[Dict[str, str]], level: int = 1, mode: str = "DSA"
    ) -> AsyncGenerator[str, None]:
        prompt = f"Mode: {mode}. Level: {level}. Problem: {problem_description}\nUser Code: {current_code}\nGive a Socratic hint. No solution."
        async for chunk in self._stream_request(prompt, max_tokens=300):
            yield chunk

    async def review_code(
        self, problem_description: str, code: str, mode: str = "DSA"
    ) -> AsyncGenerator[str, None]:
        prompt = f"Mode: {mode}. Problem: {problem_description}\nCode: {code}\nReview this code."
        async for chunk in self._stream_request(prompt, max_tokens=512):
            yield chunk

    async def generate_problem(
        self, topic: str, difficulty: str
    ) -> Dict[str, Any]:
        import httpx
        prompt = f"Generate a DSA problem on {topic} ({difficulty}). Return ONLY valid JSON."
        
        async with httpx.AsyncClient() as client:
            res = await client.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model_name, 
                    "prompt": prompt, 
                    "stream": False,
                    "options": {"num_predict": 2048}
                }
            )
            data = res.json()
            return json.loads(data["response"])

    async def generate_sql_problem(self, topic: str) -> Dict[str, Any]:
        return {}

    async def generate_slop(self, statement: str) -> AsyncGenerator[str, None]:
        yield "# Slop generation not implemented for this provider."

    async def analyze_slop(self, code: str) -> AsyncGenerator[str, None]:
        yield "Slop analysis not implemented for this provider."

    async def validate_fix(self, original: str, rewrite: str) -> AsyncGenerator[str, None]:
        yield "Fix validation not implemented for this provider."

    async def classify_failure(self, code: str, problem_description: str, test_results: str) -> str:
        return "unknown"

    async def generate_insight(self, code: str, problem_description: str) -> str:
        return ""
