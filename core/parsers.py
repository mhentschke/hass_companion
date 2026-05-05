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