import json

import pytest

from app import llm
from app.services import quote
from app.services.quote import (
    STATIC_QUOTE_FALLBACK,
    build_quote,
    format_quote_text,
    parse_quote,
)

from conftest import VALID_QUOTE_JSON


def test_parse_quote_valid_json():
    q = parse_quote(VALID_QUOTE_JSON)
    assert q["ok"] is True
    assert q["recommended"] == "B"
    assert [o["id"] for o in q["options"]] == ["A", "B", "C"]
    assert q["raw"] == VALID_QUOTE_JSON


def test_parse_quote_codeblock_wrapped():
    raw = "```json\n" + VALID_QUOTE_JSON + "\n```"
    q = parse_quote(raw)
    assert q["ok"] is True
    assert q["recommended"] == "B"


def test_parse_quote_recommended_not_in_options():
    raw = json.dumps(
        {
            "options": [{"id": "A", "weeks": 1, "amount": 100, "desc": "x"}],
            "recommended": "Z",
        }
    )
    q = parse_quote(raw)
    assert q["ok"] is False
    assert q["raw"] == raw


def test_parse_quote_broken_json():
    raw = "{not json"
    q = parse_quote(raw)
    assert q["ok"] is False
    assert q["raw"] == raw


def test_build_quote_llm_failure_returns_static_fallback_copy(monkeypatch):
    def boom(messages):
        raise RuntimeError("nim down")

    monkeypatch.setattr(llm, "chat", boom)
    q = build_quote("쇼핑몰 만들어줘")
    assert q == STATIC_QUOTE_FALLBACK
    assert q is not STATIC_QUOTE_FALLBACK


def test_build_quote_fallback_is_deep_copy(monkeypatch):
    def boom(messages):
        raise RuntimeError("nim down")

    monkeypatch.setattr(llm, "chat", boom)
    q = build_quote("x")
    q["options"][0]["amount"] = -1
    q["raw"] = "mutated"
    assert STATIC_QUOTE_FALLBACK["options"][0]["amount"] == 3500000
    assert "기본 견적" in STATIC_QUOTE_FALLBACK["raw"]


def test_build_quote_success(monkeypatch):
    monkeypatch.setattr(llm, "chat", lambda messages: VALID_QUOTE_JSON)
    q = build_quote("카페 예약")
    assert q["ok"] is True
    assert q["recommended"] == "B"


def test_format_quote_text_ok():
    q = parse_quote(VALID_QUOTE_JSON)
    text = format_quote_text(q)
    assert "1,000,000원" in text
    assert "추천: B" in text


def test_format_quote_text_not_ok_returns_raw():
    q = {"ok": False, "raw": "자유 텍스트 견적"}
    assert format_quote_text(q) == "자유 텍스트 견적"
