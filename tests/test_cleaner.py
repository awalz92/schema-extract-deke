"""Tests for extraction/cleaner.py — no Ollama required."""

import pytest

from schema_extract.extraction.cleaner import clean_response


class TestCleanResponse:
    def test_fenced_with_json_tag(self):
        raw = '```json\n{"company": "Acme"}\n```'
        assert clean_response(raw) == '{"company": "Acme"}'

    def test_fenced_without_tag(self):
        raw = '```\n{"company": "Acme"}\n```'
        assert clean_response(raw) == '{"company": "Acme"}'

    def test_unfenced_returned_as_is(self):
        raw = '{"company": "Acme"}'
        assert clean_response(raw) == '{"company": "Acme"}'

    def test_trailing_prose_discarded(self):
        raw = '```json\n{"company": "Acme"}\n```\nNote: salary not listed.'
        assert clean_response(raw) == '{"company": "Acme"}'

    def test_leading_and_trailing_whitespace_stripped(self):
        raw = '  \n  {"company": "Acme"}  \n  '
        assert clean_response(raw) == '{"company": "Acme"}'

    def test_fenced_with_surrounding_whitespace(self):
        raw = '\n```json\n{"x": 1}\n```\n'
        assert clean_response(raw) == '{"x": 1}'

    def test_multiline_json_preserved(self):
        raw = '```json\n{\n  "a": 1,\n  "b": 2\n}\n```'
        result = clean_response(raw)
        assert result == '{\n  "a": 1,\n  "b": 2\n}'

    def test_empty_fenced_block(self):
        raw = "```json\n```"
        assert clean_response(raw) == ""

    def test_empty_string(self):
        assert clean_response("") == ""

    def test_whitespace_only(self):
        assert clean_response("   \n   ") == ""
