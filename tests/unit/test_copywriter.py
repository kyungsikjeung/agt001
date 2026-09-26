"""AI 문구 초안(방안 3): 원문에 없는 숫자 문장은 버리고, 시안 소개·첫 화면에 들어가며, 실패해도 시안은 만든다."""
import json

from app import llm
from app.services import copywriter, design_variants as DV
from app.services import prd_engine as E
from app.services import prd_schema as S


def _card():
    card = E.new_card()
    E._put(card, "business_type", "첼로 레슨", S.FILLED, 1)
    card["industry"] = "individual"
    E._put(card, "offerings", ["성인 취미반", "입시반"], S.FILLED, 1)
    card["said"] = ["첼로 레슨이에요 성인 취미반이랑 입시반 있어요"]
    return card


def test_invented_numbers_are_dropped(monkeypatch):
    monkeypatch.setattr(llm, "chat_json", lambda *a, **k: json.dumps({
        "tagline": "첼로와 가까워지는 시간",
        "intro": "처음 잡는 분도 편하게 시작해요. 15년 경력으로 가르쳐요. 입시반은 목표에 맞춰 준비해요.",
        "items": {"성인 취미반": "주말에 부담 없이", "입시반": "합격률 90%", "없는 반": "무시"}}, ensure_ascii=False))
    c = copywriter.generate(_card())
    assert c["tagline"] == "첼로와 가까워지는 시간"
    assert "15년" not in c["intro"] and "편하게 시작해요" in c["intro"]
    assert c["items"]["성인 취미반"] == "주말에 부담 없이" and c["items"]["입시반"] == "" and "없는 반" not in c["items"]


def test_copy_used_in_design_but_owner_detail_wins(monkeypatch):
    card = _card()
    card["copy"] = {"tagline": "첼로와 가까워지는 시간", "intro": "편하게 시작해요.", "items": {"입시반": "목표에 맞춰"}, "draft": True}
    spec = DV.base_spec(card)
    hero = next(s for s in spec["sections"] if s["type"] == "hero")
    assert hero["content"]["subtitle"] == "첼로와 가까워지는 시간"
    E._put(card, "detail", "20년째 아이들과 첼로를 해요", S.FILLED, 2)
    hero = next(s for s in DV.base_spec(card)["sections"] if s["type"] == "hero")
    assert hero["content"]["subtitle"] == "20년째 아이들과 첼로를 해요"


def test_failure_returns_none(monkeypatch):
    monkeypatch.setattr(llm, "chat_json", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("down")))
    assert copywriter.generate(_card()) is None
