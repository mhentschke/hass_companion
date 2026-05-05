"""Unit tests for core.parsers — all parser types, chaining, edge cases."""

import pytest

from core.parsers import (
    BoolResultParser,
    CompareResultParser,
    FloatResultParser,
    IntResultParser,
    RegexResultParser,
    StateMapResultParser,
    StringResultParser,
)


# --- IntResultParser ---

class TestIntResultParser:
    def setup_method(self):
        self.parser = IntResultParser()

    def test_valid_int_string(self):
        assert self.parser.parse("42") == 42

    def test_float_string_raises(self):
        with pytest.raises(ValueError):
            self.parser.parse("3.9")

    def test_negative_int(self):
        assert self.parser.parse("-7") == -7

    def test_invalid_input_raises(self):
        with pytest.raises(ValueError):
            self.parser.parse("not_a_number")


# --- FloatResultParser ---

class TestFloatResultParser:
    def setup_method(self):
        self.parser = FloatResultParser()

    def test_valid_float(self):
        assert self.parser.parse("3.14") == pytest.approx(3.14)

    def test_int_input(self):
        assert self.parser.parse("5") == 5.0

    def test_invalid_input_raises(self):
        with pytest.raises(ValueError):
            self.parser.parse("abc")


# --- BoolResultParser ---

class TestBoolResultParser:
    def setup_method(self):
        self.parser = BoolResultParser()

    @pytest.mark.parametrize("value", ["true", "True", "1", "t", "y", "yes", "YES"])
    def test_truthy_values(self, value):
        assert self.parser.parse(value) is True

    @pytest.mark.parametrize("value", ["false", "False", "0", "f", "n", "no", "NO"])
    def test_falsy_values(self, value):
        assert self.parser.parse(value) is False

    def test_unknown_defaults_to_false(self):
        assert self.parser.parse("maybe") is False


# --- StringResultParser ---

class TestStringResultParser:
    def setup_method(self):
        self.parser = StringResultParser()

    def test_string_passthrough(self):
        assert self.parser.parse("hello") == "hello"

    def test_int_to_string(self):
        assert self.parser.parse(42) == "42"

    def test_none_to_string(self):
        assert self.parser.parse(None) == "None"


# --- RegexResultParser ---

class TestRegexResultParser:
    def test_match_with_group(self):
        parser = RegexResultParser(r"temp=(\d+)", group=1)
        assert parser.parse("temp=72 humidity=50") == "72"

    def test_match_without_group(self):
        parser = RegexResultParser(r"\d+")
        assert parser.parse("value is 99") == "99"

    def test_no_match_returns_none(self):
        parser = RegexResultParser(r"xyz")
        assert parser.parse("no match here") is None


# --- CompareResultParser ---

class TestCompareResultParser:
    def test_less_than(self):
        parser = CompareResultParser(10, "<")
        assert parser.parse(5) is True
        assert parser.parse(10) is False

    def test_greater_than(self):
        parser = CompareResultParser(10, ">")
        assert parser.parse(15) is True
        assert parser.parse(10) is False

    def test_less_equal(self):
        parser = CompareResultParser(10, "<=")
        assert parser.parse(10) is True
        assert parser.parse(11) is False

    def test_greater_equal(self):
        parser = CompareResultParser(10, ">=")
        assert parser.parse(10) is True
        assert parser.parse(9) is False

    def test_equal(self):
        parser = CompareResultParser(10, "==")
        assert parser.parse(10) is True
        assert parser.parse(11) is False

    def test_not_equal(self):
        parser = CompareResultParser(10, "!=")
        assert parser.parse(11) is True
        assert parser.parse(10) is False

    def test_invalid_operator_raises(self):
        with pytest.raises(ValueError):
            CompareResultParser(10, "~")


# --- StateMapResultParser ---

class TestStateMapResultParser:
    def setup_method(self):
        self.parser = StateMapResultParser({"on": "running", "off": "stopped"})

    def test_known_key_mapped(self):
        assert self.parser.parse("on") == "running"
        assert self.parser.parse("off") == "stopped"

    def test_unknown_key_passed_through(self):
        assert self.parser.parse("unknown") == "unknown"


# --- Parser chaining ---

class TestParserChaining:
    def test_regex_float_compare_pipeline(self):
        """Simulate a pipeline: regex extracts number, float converts, compare checks threshold."""
        regex_parser = RegexResultParser(r"temp=(\d+\.?\d*)", group=1)
        float_parser = FloatResultParser()
        compare_parser = CompareResultParser(30.0, ">")

        raw = "temp=35.5 humidity=60"
        result = regex_parser.parse(raw)
        result = float_parser.parse(result)
        result = compare_parser.parse(result)
        assert result is True

    def test_regex_int_pipeline(self):
        regex_parser = RegexResultParser(r"count: (\d+)", group=1)
        int_parser = IntResultParser()

        result = regex_parser.parse("count: 7")
        result = int_parser.parse(result)
        assert result == 7
