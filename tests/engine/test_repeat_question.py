"""질문 다시 해 주세요 (VOICE_QA_REQUIREMENTS FR-6): 같은 질문, 예산 안 씀, 칸 안 채움."""
import json

import pytest

from app import llm
from app.services import prd_engine as E


@pytest.fixture(autouse=True)
def no_extract(monkeypatch):
    monkeypatch.setattr(llm, "chat_json", lambda system, user, **kw: json.dumps({"updates": []}))


def pending_goal():
    card = E.new_card("cafe")
    card["pending"] = {"slot": "goal", "kind": "single", "options": ["가게 알리기", "알아서 해주세요"], "text": "목적은?"}
    card["asked"] = 3
    return card


@pytest.mark.parametrize("said", ["다시요", "뭐라고요?", "다시 말해 주세요", "잘 못 들었어요", "한 번 더"])
def test_repeat_keeps_question_and_budget(said):
    card = pending_goal()
    r = E.turn(card, said)
    assert r["question"]["slot"] == "goal" and r["trace"].get("repeat")
    assert card["asked"] == 3
    assert "goal" not in card["slots"]
    assert card.get("chatter", 0) == 0


def test_sentence_with_dasi_is_an_answer_not_repeat(monkeypatch):
    card = pending_goal()
    r = E.turn(card, "다시 생각해보니 가게 알리기요")
    assert not r["trace"].get("repeat")


def test_repeat_without_question_is_normal_turn():
    card = E.new_card("cafe")
    r = E.turn(card, "다시요")
    assert not r["trace"].get("repeat")
