"""Tests for FastAPI main module helpers."""

import json

from main import _sse


class TestSSEHelper:

    def test_sse_format(self):
        result = _sse({"type": "token", "content": "hello"})
        assert result.startswith("data: ")
        assert result.endswith("\n\n")

    def test_sse_valid_json(self):
        result = _sse({"type": "done", "conversation_id": "abc-123"})
        # Strip the "data: " prefix and trailing newlines
        json_str = result[len("data: "):].strip()
        parsed = json.loads(json_str)
        assert parsed["type"] == "done"
        assert parsed["conversation_id"] == "abc-123"

    def test_sse_special_characters(self):
        result = _sse({"type": "token", "content": 'He said "hello" & <goodbye>'})
        json_str = result[len("data: "):].strip()
        parsed = json.loads(json_str)
        assert parsed["content"] == 'He said "hello" & <goodbye>'

    def test_sse_unicode(self):
        result = _sse({"type": "token", "content": "日本語テスト"})
        json_str = result[len("data: "):].strip()
        parsed = json.loads(json_str)
        assert parsed["content"] == "日本語テスト"

    def test_sse_empty_content(self):
        result = _sse({"type": "token", "content": ""})
        json_str = result[len("data: "):].strip()
        parsed = json.loads(json_str)
        assert parsed["content"] == ""
