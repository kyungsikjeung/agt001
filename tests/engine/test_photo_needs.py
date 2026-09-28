"""항목 사진 필요 판단 (BETA_FLOW_PLAN §2.7). DB 없이 돌아간다."""
from app import llm
from app.services import chat_flow
from app.services import photo_needs
from app.services import prd_engine as E
from app.services import prd_schema as S


def _salon_card():
    card = E.new_card("salon")
    E._put(card, "offerings", ["컷", "펌", "염색"], S.FILLED, 1)
    return card


def test_items_are_style_for_salon():
    card = _salon_card()
    assert photo_needs.items(card) == [
        {"name": "컷", "kind": "style"},
        {"name": "펌", "kind": "style"},
        {"name": "염색", "kind": "style"},
    ]


def test_judge_keeps_only_candidates_and_caches(monkeypatch):
    card = _salon_card()
    calls = []

    def fake_chat_json(system, user, **kwargs):
        calls.append((system, user))
        return '{"need": ["펌", "염색", "없는항목"]}'  # 후보 밖 이름은 버린다

    monkeypatch.setattr(llm, "chat_json", fake_chat_json)
    assert photo_needs.judge(card) == ["펌", "염색"]
    assert len(calls) == 1
    assert photo_needs.judge(card) == ["펌", "염색"]  # sig가 같으면 다시 묻지 않는다
    assert len(calls) == 1


def test_judge_falls_back_to_rule_on_llm_error(monkeypatch):
    card = _salon_card()

    def boom(system, user, **kwargs):
        raise RuntimeError("끊김")

    monkeypatch.setattr(llm, "chat_json", boom)
    assert photo_needs.judge(card) == ["컷", "펌", "염색"]  # style은 모두 필요


def test_valid_tag_and_photo_tags():
    card = _salon_card()
    card["photo_needs"] = {"sig": "컷|펌|염색", "need": ["펌", "염색"]}
    assert photo_needs.valid_tag(card, "item:펌") is True
    assert photo_needs.valid_tag(card, "item:없음") is False
    assert photo_needs.valid_tag(card, "space") is True
    tags = photo_needs.photo_tags(card)
    assert tags[-1] == {"tag": "space", "label": "가게·공간"}
    assert {"tag": "item:펌", "label": "펌"} in tags


def test_photo_choice_text_lists_needed_items(monkeypatch):
    card = _salon_card()
    monkeypatch.setattr(llm, "chat_json",
                        lambda system, user, **kwargs: '{"need": ["펌", "염색"]}')
    photo_needs.judge(card)
    text = chat_flow.photo_choice_text(card)
    assert "사진이 있으면 좋은 항목: 펌, 염색" in text
