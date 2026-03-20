"""Tests for extraction/validator.py — no Ollama required."""

import pytest

from schema_extract.extraction.validator import validate_extraction
from schema_extract.models.results import ExtractionResult
from schema_extract.models.schemas import ExtractionSchema


def make_schema(fields: list[dict]) -> ExtractionSchema:
    """Build a minimal ExtractionSchema from a list of field dicts."""
    return ExtractionSchema(
        name="test",
        description="test schema",
        fields=[
            {
                "name": f["name"],
                "type": f["type"],
                "description": f.get("description", ""),
                "required": f.get("required", True),
            }
            for f in fields
        ],
    )


class TestValidateExtraction:
    # --- basic pass cases ---

    def test_all_correct_types(self):
        schema = make_schema([
            {"name": "title", "type": "str"},
            {"name": "count", "type": "int"},
            {"name": "score", "type": "float"},
            {"name": "active", "type": "bool"},
            {"name": "tags", "type": "list"},
        ])
        parsed = {"title": "foo", "count": 3, "score": 1.5, "active": True, "tags": ["a", "b"]}
        result, hard_errors = validate_extraction(parsed, schema)
        assert hard_errors == []
        assert result.extracted["title"] == "foo"
        assert result.extracted["count"] == 3
        assert result.is_partial is False
        assert result.confidence == pytest.approx(1.0, abs=0.01)

    def test_extra_fields_in_parsed_are_ignored(self):
        schema = make_schema([{"name": "title", "type": "str"}])
        parsed = {"title": "foo", "unexpected": "bar"}
        result, hard_errors = validate_extraction(parsed, schema)
        assert hard_errors == []
        assert "unexpected" not in result.extracted

    # --- type coercion ---

    def test_string_int_coerced(self):
        schema = make_schema([{"name": "salary", "type": "int"}])
        parsed = {"salary": "150000"}
        result, hard_errors = validate_extraction(parsed, schema)
        assert hard_errors == []
        assert result.extracted["salary"] == 150000

    def test_string_float_coerced(self):
        schema = make_schema([{"name": "score", "type": "float"}])
        parsed = {"score": "3.14"}
        result, hard_errors = validate_extraction(parsed, schema)
        assert hard_errors == []
        assert result.extracted["score"] == pytest.approx(3.14)

    def test_string_bool_true_coerced(self):
        schema = make_schema([{"name": "flag", "type": "bool"}])
        for val in ("true", "True", "yes", "1"):
            result, hard_errors = validate_extraction({"flag": val}, schema)
            assert hard_errors == [], f"Expected coercion success for {val!r}"
            assert result.extracted["flag"] is True

    def test_string_bool_false_coerced(self):
        schema = make_schema([{"name": "flag", "type": "bool"}])
        for val in ("false", "False", "no", "0"):
            result, hard_errors = validate_extraction({"flag": val}, schema)
            assert hard_errors == [], f"Expected coercion success for {val!r}"
            assert result.extracted["flag"] is False

    def test_bool_on_int_field_is_hard_error(self):
        # bool is a subclass of int in Python; isinstance(True, int) is True.
        # Without an explicit guard, True would silently pass as 1.
        schema = make_schema([{"name": "count", "type": "int"}])
        result, hard_errors = validate_extraction({"count": True}, schema)
        assert len(hard_errors) == 1
        assert result.extracted["count"] is None

    def test_non_coercible_type_is_hard_error(self):
        schema = make_schema([{"name": "count", "type": "int"}])
        parsed = {"count": "five"}
        result, hard_errors = validate_extraction(parsed, schema)
        assert len(hard_errors) == 1
        assert "count" in hard_errors[0]
        assert result.extracted["count"] is None

    # --- null / empty handling ---

    def test_null_required_field_is_soft_failure(self):
        schema = make_schema([{"name": "title", "type": "str", "required": True}])
        parsed = {"title": None}
        result, hard_errors = validate_extraction(parsed, schema)
        assert hard_errors == []          # no retry triggered
        assert result.is_partial is True
        assert result.confidence < 1.0
        assert len(result.validation_errors) == 1

    def test_empty_string_counts_as_null(self):
        schema = make_schema([{"name": "title", "type": "str", "required": True}])
        parsed = {"title": ""}
        result, hard_errors = validate_extraction(parsed, schema)
        assert result.is_partial is True

    def test_empty_list_counts_as_null(self):
        schema = make_schema([{"name": "tags", "type": "list", "required": True}])
        parsed = {"tags": []}
        result, hard_errors = validate_extraction(parsed, schema)
        assert result.is_partial is True

    def test_null_optional_field_not_partial(self):
        schema = make_schema([
            {"name": "title", "type": "str", "required": True},
            {"name": "salary", "type": "int", "required": False},
        ])
        parsed = {"title": "Engineer", "salary": None}
        result, hard_errors = validate_extraction(parsed, schema)
        assert hard_errors == []
        assert result.is_partial is False

    def test_missing_field_treated_as_null(self):
        schema = make_schema([{"name": "title", "type": "str", "required": True}])
        parsed = {}  # field absent
        result, hard_errors = validate_extraction(parsed, schema)
        assert result.is_partial is True

    # --- non-dict input ---

    def test_non_dict_is_hard_error(self):
        schema = make_schema([{"name": "title", "type": "str"}])
        for bad in (None, [], "text", 42):
            result, hard_errors = validate_extraction(bad, schema)
            assert len(hard_errors) == 1
            assert result.confidence == 0.0

    # --- confidence formula ---

    def test_confidence_all_required_nonnull(self):
        schema = make_schema([
            {"name": "a", "type": "str", "required": True},
            {"name": "b", "type": "str", "required": True},
        ])
        parsed = {"a": "x", "b": "y"}
        result, _ = validate_extraction(parsed, schema)
        assert result.confidence == pytest.approx(1.0, abs=0.01)

    def test_confidence_half_required_nonnull(self):
        schema = make_schema([
            {"name": "a", "type": "str", "required": True},
            {"name": "b", "type": "str", "required": True},
        ])
        parsed = {"a": "x", "b": None}
        result, _ = validate_extraction(parsed, schema)
        # required_nonnull=1/2 → 0.5*0.7=0.35; all_nonnull=1/2 → 0.5*0.3=0.15; total=0.5
        assert result.confidence == pytest.approx(0.5, abs=0.01)

    def test_confidence_zero_required_fields(self):
        schema = make_schema([{"name": "a", "type": "str", "required": False}])
        parsed = {"a": "x"}
        result, _ = validate_extraction(parsed, schema)
        # required_count=0 → clamped to 1 in formula; required_nonnull=0 → 0*0.7=0
        # all_nonnull=1/1 → 1*0.3=0.3
        assert result.confidence == pytest.approx(0.3, abs=0.01)
