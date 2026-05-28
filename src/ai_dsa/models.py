import tomllib
import tomli_w
import os
from dataclasses import dataclass, asdict, field
from typing import List, Dict, Optional, Any

@dataclass
class TestCase:
    input: str
    expected: str

@dataclass
class FunctionParam:
    name: str
    type: str

@dataclass
class FunctionContract:
    name: str
    params: List[FunctionParam]
    return_type: str
    compare: str = "exact"

@dataclass
class Problem:
    id: str
    title: str
    difficulty: str
    topic: str
    description: str
    constraints: List[str]
    test_cases: List[TestCase]
    function: FunctionContract

    @classmethod
    def from_dict(cls, data: Dict) -> 'Problem':
        test_cases = [TestCase(**tc) for tc in data.get('test_cases', [])]
        func_data = data['function']
        params = [FunctionParam(**p) for p in func_data.get('params', [])]
        contract = FunctionContract(
            name=func_data['name'],
            params=params,
            return_type=func_data['return_type'],
            compare=func_data.get('compare', 'exact')
        )
        return cls(
            id=data['id'],
            title=data['title'],
            difficulty=data['difficulty'],
            topic=data['topic'],
            description=data['description'],
            constraints=data.get('constraints', []),
            test_cases=test_cases,
            function=contract
        )

@dataclass
class SQLProblem:
    id: str
    title: str
    difficulty: str
    category: str
    schema_definition: str
    description: str
    expected_output: str

    @classmethod
    def from_dict(cls, data: Dict) -> 'SQLProblem':
        return cls(**data)

class ProblemBank:
    def __init__(self, data_dir: str = "data/problems"):
        self.data_dir = data_dir
        self.problems: List[Problem] = []
        self._load_all()

    def _load_all(self):
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir, exist_ok=True)
            return

        for filename in os.listdir(self.data_dir):
            if filename.endswith(".toml"):
                with open(os.path.join(self.data_dir, filename), "rb") as f:
                    try:
                        data = tomllib.load(f)
                        self.problems.append(Problem.from_dict(data))
                    except Exception as e:
                        print(f"Error loading {filename}: {e}")

    def get_problem(self, problem_id: str) -> Optional[Problem]:
        return next((p for p in self.problems if p.id == problem_id), None)

    def filter_by_topic(self, topic: str) -> List[Problem]:
        return [p for p in self.problems if p.topic.lower() == topic.lower()]

    def save_problem(self, problem: Problem):
        filename = f"{problem.id}.toml"
        path = os.path.join(self.data_dir, filename)
        with open(path, "wb") as f:
            tomli_w.dump(asdict(problem), f)
        self.problems.append(problem)

    def sync_to_db(self, db):
        """Placeholder if DSA problems need DB sync as well."""
        pass

class SQLProblemBank:
    def __init__(self, data_dir: str = "data/sql"):
        self.data_dir = data_dir
        self.problems: List[SQLProblem] = []
        self._load_all()

    def _load_all(self):
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir, exist_ok=True)
            return

        for filename in os.listdir(self.data_dir):
            if filename.endswith(".toml"):
                with open(os.path.join(self.data_dir, filename), "rb") as f:
                    try:
                        data = tomllib.load(f)
                        self.problems.append(SQLProblem.from_dict(data))
                    except Exception as e:
                        print(f"Error loading {filename}: {e}")

    def get_problem(self, problem_id: str) -> Optional[SQLProblem]:
        return next((p for p in self.problems if p.id == problem_id), None)

    def save_problem(self, problem: SQLProblem):
        filename = f"{problem.id}.toml"
        path = os.path.join(self.data_dir, filename)
        with open(path, "wb") as f:
            tomli_w.dump(asdict(problem), f)
        if not any(p.id == problem.id for p in self.problems):
            self.problems.append(problem)

    def sync_to_db(self, db):
        for problem in self.problems:
            db.add_sql_problem(problem)
