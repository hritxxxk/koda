import re
from typing import List, Dict, Tuple, Any

class IndentEngine:
    """Detects and calculates code indentation patterns."""
    
    @staticmethod
    def detect_indent(text: str) -> Tuple[str, int]:
        """Detects the indentation style (spaces/tabs) and size."""
        if not text:
            return (" ", 4)
            
        lines = text.splitlines()
        for line in lines:
            match = re.match(r'^(\s+)', line)
            if match:
                indent = match.group(1)
                char = indent[0]
                size = len(indent)
                return (char, size)
        return (" ", 4)

class LanguageRules:
    """Defines auto-indentation rules for different programming languages."""
    
    INDENT_TRIGGER = {
        "python": [":", "[", "{", "("],
        "javascript": ["{", "[", "("],
        "sql": ["SELECT", "FROM", "WHERE", "JOIN", "HAVING"]
    }
    
    @staticmethod
    def should_indent(line: str, language: str) -> bool:
        """Determines if the next line should be indented based on the current line's content."""
        # 1. Strip comments and whitespace
        clean_line = line.strip()
        if language == "python":
            clean_line = clean_line.split("#")[0].strip()
        elif language == "sql":
            clean_line = clean_line.split("--")[0].strip()
            
        if not clean_line:
            return False
            
        # 2. Check triggers
        triggers = LanguageRules.INDENT_TRIGGER.get(language, [])
        for trigger in triggers:
            if clean_line.endswith(trigger):
                return True
        return False

    @staticmethod
    def get_next_indent(language: str, line: str, current_indent: str, indent_unit: str) -> str:
        """Calculates the indentation string for the next line."""
        if LanguageRules.should_indent(line, language):
            return current_indent + indent_unit
        return current_indent

class BracketEngine:
    """Handles bracket auto-pairing and selection wrapping."""
    
    PAIRS = {"(": ")", "[": "]", "{": "}", "'": "'", '"': '"'}
    
    @staticmethod
    def get_closing(char: str) -> str:
        """Returns the closing bracket for a given opening bracket."""
        return BracketEngine.PAIRS.get(char, "")

def deserialize(value: str, target_type: str) -> Any:
    """Converts a string representation to a Python type using JSON logic for robustness."""
    if not value or value.strip() == "":
        return None
        
    value = value.strip()
    
    # Try parsing as JSON for lists and booleans
    try:
        import json
        if target_type.startswith("List") or target_type in ("bool", "int", "float"):
            # Handle Python booleans if they appear in TOML string format
            if value.lower() == "true": return True
            if value.lower() == "false": return False
            return json.loads(value)
    except:
        pass
        
    if target_type == "int":
        try: return int(value)
        except: return 0
    if target_type == "float":
        try: return float(value)
        except: return 0.0
    if target_type == "str":
        return value.strip("'").strip('"')
    if target_type == "bool":
        return value.lower() in ("true", "1", "yes")
        
    return value

def compare(actual: Any, expected: Any, mode: str = "exact") -> bool:
    """Compares two values based on the specified comparison mode."""
    if mode == "sorted":
        try:
            return sorted(actual) == sorted(expected)
        except:
            return actual == expected
    return actual == expected
