import re
from typing import List, Dict, Tuple, Any

class IndentEngine:
    """Core logic for detecting and calculating indentation."""
    
    @staticmethod
    def detect_indent(text: str) -> Tuple[str, int]:
        """Infers indentation style (tabs vs spaces) and width."""
        if not text.strip():
            return "spaces", 4
            
        lines = text.splitlines()[:100]  # Scan first 100 lines
        spaces_counts = []
        tabs_count = 0
        
        for line in lines:
            if not line.strip(): continue
            leading = line[:len(line) - len(line.lstrip())]
            if "\t" in leading:
                tabs_count += 1
            elif leading.startswith(" "):
                spaces_counts.append(len(leading))
        
        if tabs_count > len(spaces_counts):
            return "tabs", 4
            
        # Find most common non-zero difference between indentation levels
        if not spaces_counts:
            return "spaces", 4
            
        diffs = [spaces_counts[i] - spaces_counts[i-1] for i in range(1, len(spaces_counts)) 
                 if spaces_counts[i] > spaces_counts[i-1]]
        
        if not diffs:
            return "spaces", spaces_counts[0] if spaces_counts[0] > 0 else 4
            
        return "spaces", max(set(diffs), key=diffs.count)

class LanguageRules:
    """Language-specific indentation heuristics."""
    
    RULES = {
        "python": {
            "increase": [r":\s*$", r"\[\s*$", r"\{\s*$", r"\(\s*$"],
            "decrease": [r"^\s*(return|break|continue|pass|raise)\b"],
            "dedent_next": [r"^\s*(elif|else|except|finally)\b"]
        },
        "javascript": {
            "increase": [r"\{\s*$", r"\[\s*$", r"\(\s*$"],
            "decrease": [r"^\s*\}", r"^\s*\]", r"^\s*\)"]
        }
    }
    
    @classmethod
    def get_next_indent(cls, lang: str, current_line: str, current_indent: str, indent_unit: str) -> str:
        rules = cls.RULES.get(lang, {})
        stripped = current_line.strip()
        
        # Check for increase
        if any(re.search(pat, current_line) for pat in rules.get("increase", [])):
            return current_indent + indent_unit
            
        # Check for decrease (current line signals the NEXT line should be dedented)
        if any(re.search(pat, stripped) for pat in rules.get("decrease", [])):
            if current_indent.startswith(indent_unit):
                return current_indent[:-len(indent_unit)]
                
        return current_indent

class BracketEngine:
    """Handles auto-pairing and selection wrapping."""
    
    PAIRS = {
        "(": ")",
        "[": "]",
        "{": "}",
        "'": "'",
        '"': '"',
    }
    
    @classmethod
    def get_closing(cls, char: str) -> str:
        return cls.PAIRS.get(char)

def deserialize(value: str, type_str: str) -> Any:
    """Deserializes a string value into a specific Python type."""
    value = value.strip()
    if type_str == "int":
        return int(value)
    if type_str == "float":
        return float(value)
    if type_str == "bool":
        return value.lower() == "true"
    if type_str == "str":
        return value.strip("'\"")
    if type_str == "List[int]":
        return [int(x.strip()) for x in value.strip("[]").split(",") if x.strip()]
    if type_str == "List[str]":
        return [x.strip().strip("'\"") for x in value.strip("[]").split(",") if x.strip()]
    return value

def compare(actual: Any, expected: Any, mode: str = "exact") -> bool:
    """Compares two values based on the specified mode."""
    if mode == "sorted":
        try:
            return sorted(actual) == sorted(expected)
        except:
            return actual == expected
    return actual == expected
