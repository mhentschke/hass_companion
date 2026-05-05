from __future__ import annotations

from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from core.config import ParserConfig


class ResultParser:
    def __init__(self):
        pass
    def parse(self, text):
        return text

class IntResultParser(ResultParser):
    def parse(self, text):
        return int(text)

class FloatResultParser(ResultParser):
    def parse(self, text):
        return float(text)

class BoolResultParser(ResultParser):
    def parse(self, text):
        if str(text).lower() in ['true', '1', 't', 'y', 'yes']:
            return True
        elif str(text).lower() in ['false', '0', 'f', 'n', 'no']:
            return False
        else:
            return False

class StringResultParser(ResultParser):
    def parse(self, text):
        return str(text)

class CompareResultParser(ResultParser):
    def __init__(self, compare_value, operator):
        self.compare_value = compare_value
        self.operator = operator
        # Check operator validity:
        if operator not in ['<', '>', '<=', '>=', '==', '!=']:
            raise ValueError("Invalid operator")
        
    def parse(self, value):
        
        if self.operator == '<':
            return value < self.compare_value
        elif self.operator == '>':
            return value > self.compare_value
        elif self.operator == '<=':
            return value <= self.compare_value
        elif self.operator == '>=':
            return value >= self.compare_value
        elif self.operator == '==':
            return value == self.compare_value
        elif self.operator == '!=':
            return value != self.compare_value


class RegexResultParser(ResultParser):
    def __init__(self, regex, group = None):
        self.regex = regex
        self.group = group
    def parse(self, text):
        import re
        match = re.search(self.regex, str(text))
        if match:
            if self.group is not None:
                return match.group(self.group)
            else:
                return match.group(0)
        else:
            return None

class StateMapResultParser(ResultParser):
    def __init__(self, mapping):
        self.mapping = mapping
    def parse(self, text):
        return self.mapping.get(text, text)

# --- Parser Factory ---

_PARSER_REGISTRY: dict[str, type | Callable] = {
    "int": IntResultParser,
    "float": FloatResultParser,
    "bool": BoolResultParser,
    "string": StringResultParser,
    "regex": lambda cfg: RegexResultParser(cfg.regex, cfg.group),
    "compare": lambda cfg: CompareResultParser(cfg.value, cfg.operator),
    "state_map": lambda cfg: StateMapResultParser(cfg.map),
}


def build_pipeline(parser_configs: list[ParserConfig]) -> list[ResultParser]:
    """Build an ordered list of parser instances from config objects.

    Args:
        parser_configs: List of ParserConfig objects specifying parser type and params.

    Returns:
        Ordered list of instantiated ResultParser objects.

    Raises:
        ValueError: If a parser config specifies an unrecognized type.
    """
    pipeline: list[ResultParser] = []
    for cfg in parser_configs:
        factory = _PARSER_REGISTRY.get(cfg.type)
        if factory is None:
            raise ValueError(f"Unknown parser type: '{cfg.type}'")
        # Simple types (int, float, bool, string) are classes with no-arg constructors.
        # Complex types (regex, compare, state_map) are lambdas that accept cfg.
        if callable(factory) and isinstance(factory, type):
            pipeline.append(factory())
        else:
            pipeline.append(factory(cfg))
    return pipeline
