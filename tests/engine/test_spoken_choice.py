"""말로 선택지 고르기 (VOICE_QA_REQUIREMENTS FR-2)."""
import json

import pytest

from app import llm
from app.services import prd_engine as E
from app.services import prd_schema as S

OPTS = ["예약·문의 늘리기", "가게 알리기", "메뉴·가격 안내", S.LET_AI]


@pytest.mark.parametrize("said,expected", [
    ("2", 1), ("2번", 1), ("2번이요", 1), ("이 번", 1), ("이번이요", 1), ("이 번으로 할게요", 1),
    ("두 번째", 1), ("두번째 거요", 1), ("두 번째 걸로", 1), ("첫 번째요", 0), ("일 번", 0), ("세 번째 거", 2),
    ("삼번", 2), ("네 번째", 3), ("마지막 거요", 3), ("맨 마지막", 3),
    # 고르기가 아닌 말
    ("5번", None), ("다섯 번째", None), ("둘", None), ("하나요", None), ("이번 주부터 열어요", None),
    ("두 번째 가게예요", None), ("가게 알리기", None),
])
def test_option_index(said, expected):
    assert E._option_index(E._norm(said), len(OPTS)) == expected


def test_spoken_choice_fills_slot(monkeypatch):
    monkeypatch.setattr(llm, "chat_json", lambda system, user, **kw: json.dumps({"updates": []}))
    card = E.new_card("cafe")
    card["pending"] = {"slot": "goal", "kind": "single", "options": OPTS, "text": "?"}
    E.turn(card, "두 번째 거요")
    assert card["slots"]["goal"]["value"] == "가게 알리기"
