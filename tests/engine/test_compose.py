"""구성 인터뷰 (COMPOSE_INTERVIEW_CONTRACT): 업종 → 부품 하나씩 묻기 → 사실 잇기 → 미리보기."""
import json

from app import llm
from app.services import compose as C
from app.services import prd_engine as E
from app.services import prd_schema as S


def fake_setup(monkeypatch, table):
    def fake(system, user, **kw):
        if "[사장님 메시지] " not in user:
            return json.dumps({"missing": [], "conflicts": []})
        text = user.split("[사장님 메시지] ", 1)[-1]
        return json.dumps({"updates": table.get(text, [])}, ensure_ascii=False)

    monkeypatch.setattr(llm, "chat_json", fake)


def u(slot, value):
    return {"slot": slot, "value": value}


def _cafe(monkeypatch, extra=None):
    table = {"카페 사이트 만들고 싶어요": [u("business_type", "카페")], "바다카페": [u("shop_name", "바다카페")]}
    table.update(extra or {})
    fake_setup(monkeypatch, table)
    card = E.new_card()
    r = C.live_turn(card, "카페 사이트 만들고 싶어요")
    return card, r


def test_first_question_asks_what_site():
    card = E.new_card()
    out = C.next_step(card)
    assert out["question"]["text"] == C.FIRST_QUESTION and out["phase"] == "kind"


def test_industry_then_hero_question_in_plain_words(monkeypatch):
    card, r = _cafe(monkeypatch)
    assert r["phase"] == "compose"
    q = r["question"]
    assert q["component"] == "hero" and "첫인상" in q["text"]
    assert q["options"][:2] == ["사진 크게", "사진과 소개 글 나란히"] and q["options"][-1] == S.LET_AI
    assert "사진 크게" in C.speech_text(q) and "1)" not in C.speech_text(q)
    assert card["asked"] == 0  # 구성 질문은 질문 한도 밖


def test_choice_by_spoken_words_then_linked_fact(monkeypatch):
    card, _ = _cafe(monkeypatch)
    r = C.live_turn(card, "사진 크게 보여 주세요")
    assert C.state(card)["chosen"]["hero"] == "photo-overlay" and r["last"] == "hero"
    assert r["phase"] == "fact" and r["question"]["slot"] == "shop_name"
    r = C.live_turn(card, "바다카페")
    assert E._slot(card, "shop_name")["value"] == "바다카페"
    assert r["phase"] == "compose" and r["question"]["component"] == "menu"


def test_optional_component_can_be_skipped(monkeypatch):
    card, _ = _cafe(monkeypatch)
    st = C.state(card)
    st["chosen"].update({"hero": "photo-overlay", "menu": "categories"})
    E._put(card, "shop_name", "바다카페", S.FILLED, 1)
    E._put(card, "offerings", ["라떼"], S.FILLED, 1)
    st["pending"] = None
    q = C.next_step(card)["question"]
    assert q["component"] == "space" and "빼기" in q["options"]
    r = C.live_turn(card, "사진은 필요 없어요")
    assert "space" in C.state(card)["skipped"] and "뺐어요" in r["reply"]


def test_unknown_answer_retries_once_then_defaults(monkeypatch):
    card, _ = _cafe(monkeypatch)
    r = C.live_turn(card, "음 글쎄 뭐가 좋을지")
    assert "다시" in r["reply"] and r["question"]["component"] == "hero"
    r = C.live_turn(card, "흠흠")
    assert C.state(card)["chosen"]["hero"] == "photo-overlay" and "우선" in r["reply"]


def test_video_word_adds_video_component(monkeypatch):
    card, _ = _cafe(monkeypatch)
    r = C.live_turn(card, "영상으로 하고 싶어요")
    st = C.state(card)
    assert st["chosen"]["hero"] == "photo-overlay" and st["chosen"]["video"] == "card"
    assert "영상" in r["reply"]


def test_call_button_sets_contact_and_asks_phone(monkeypatch):
    card, _ = _cafe(monkeypatch)
    st = C.state(card)
    for s in st["steps"]:
        if s["type"] != "contact":
            st["skipped"].append(s["id"])
    inquiry = next(s["id"] for s in st["steps"] if s["type"] == "contact")
    st["pending"] = inquiry
    r = C.live_turn(card, "전화 버튼으로요")
    assert E._slot(card, "contact_method")["value"] == "전화"
    assert r["question"]["slot"] == "phone"


def test_preview_shows_only_chosen_components(monkeypatch):
    card, _ = _cafe(monkeypatch)
    assert C.preview_html(card) is None  # 아직 정한 부품 없음
    C.live_turn(card, "사진 크게")
    C.live_turn(card, "바다카페")
    html = C.preview_html(card)
    assert html and "바다카페" in html
    C.live_turn(card, "분류별 메뉴판")
    ids = [c["id"] for c in C.components(card)]
    assert ids == ["hero", "menu"]
    spec = C.preview_spec(card)
    assert [s["type"] for s in spec["sections"]] == ["hero", "offerings"]
    assert spec["sections"][0]["variant"] == "photo-overlay"


def test_every_option_is_a_real_renderer_part(monkeypatch):
    from app.services import site_render as SR
    have = set(SR.list_variants())
    for ind in ("cafe", "restaurant", "salon", "pension", "academy", "workshop"):
        card = E.new_card(ind)
        E._put(card, "business_type", S.INDUSTRIES[ind].name, S.FILLED, 1)
        for step in C._steps(card):
            for _name, variant, _w in C._options(step, card):
                if variant:
                    assert f"{step['type']}--{variant}" in have, (ind, step, variant)


def test_required_single_option_part_is_added_without_asking(monkeypatch):
    # 펜션 객실: 빼면 안 되고 모양도 하나 → 묻지 않고 넣고, 객실 구성을 바로 묻는다
    fake_setup(monkeypatch, {"펜션이요": [u("business_type", "펜션")], "바다소리": [u("shop_name", "바다소리")]})
    card = E.new_card()
    C.live_turn(card, "펜션이요")
    C.live_turn(card, "사진 크게")
    r = C.live_turn(card, "바다소리")
    assert "rooms" in C.state(card)["chosen"] and "꼭 필요해서 넣었어요" in r["reply"]
    assert r["question"]["slot"] == "offerings"
