"""구성 인터뷰 (COMPOSE_INTERVIEW_CONTRACT): 업종 → 분위기 → 부품 하나씩 묻기 → 사실 잇기 → 미리보기."""
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


def _cafe(monkeypatch, extra=None, tone=True):
    table = {"카페 사이트 만들고 싶어요": [u("business_type", "카페")], "바다카페": [u("shop_name", "바다카페")]}
    table.update(extra or {})
    fake_setup(monkeypatch, table)
    card = E.new_card()
    r = C.live_turn(card, "카페 사이트 만들고 싶어요")
    if tone:
        r = C.live_turn(card, "따뜻하고 아늑하게")
    return card, r


def test_first_question_asks_what_site():
    card = E.new_card()
    out = C.next_step(card)
    assert out["question"]["text"] == C.FIRST_QUESTION and out["phase"] == "kind"


def test_tone_is_asked_first_and_sets_shared_tokens(monkeypatch):
    card, r = _cafe(monkeypatch, tone=False)
    q = r["question"]
    assert q["component"] == "tone" and "카페 사이트" in q["text"]
    assert q["options"][0] == "따뜻하고 아늑하게"  # 카페(원형 A) 추천
    assert len(q["option_desc"]) == len(q["options"])
    r = C.live_turn(card, "깔끔하고 모던하게요")
    assert C.state(card)["tone"] == "clean" and "맞출게요" in r["reply"]
    tokens = C.tokens_for(card)
    assert tokens["font_pair"] == "sans-clean" and tokens["motion"] == "crisp" and tokens["radius"] == "sharp"
    assert C.preview_spec(card)["tokens"] == tokens  # 모든 부품이 같은 토큰


def test_hero_question_speaks_industry_words_and_explains_options(monkeypatch):
    card, r = _cafe(monkeypatch)
    q = r["question"]
    assert q["component"] == "hero" and "카페는 첫인상이 중요해요" in q["text"]
    assert q["options"][0] == "사진 크게" and "영상 표지" in q["options"]
    assert "매장과 음료 사진을 화면 가득" in q["option_desc"][0]
    assert q["speech_parts"][0] == q["text"] and q["speech_parts"][1].startswith("첫째, 사진 크게")
    assert card["asked"] == 0  # 구성 질문은 엔진 질문 한도 밖


def test_academy_hero_talks_to_parents(monkeypatch):
    fake_setup(monkeypatch, {"영어 학원이요": [u("business_type", "영어 학원")]})
    card = E.new_card()
    C.live_turn(card, "영어 학원이요")
    r = C.live_turn(card, "알아서 해주세요")
    assert C.state(card)["tone"] == "clean"  # 학원(원형 D) 추천
    assert "학부모님" in r["question"]["text"]
    assert "수업 모습과 교실" in r["question"]["option_desc"][1] or "수업 모습과 교실" in " ".join(r["question"]["option_desc"])


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


def test_video_cover_hero_asks_link_and_renders_play_button(monkeypatch):
    card, _ = _cafe(monkeypatch)
    r = C.live_turn(card, "영상으로 하고 싶어요")
    assert C.state(card)["chosen"]["hero"] == "video"
    assert r["question"]["kind"] == "compose_video" and "영상 주소" in r["question"]["text"]
    r = C.live_turn(card, "https://www.youtube.com/watch?v=dQw4w9WgXcQ 이거요")
    assert card["videos"] and "영상을 첫 화면에 넣었어요" in r["reply"]
    html = C.preview_html(card)
    assert "s-hero--video" in html and "s-hero__play" in html and "ytimg" in html


def test_video_link_later_falls_back_to_photo(monkeypatch):
    card, _ = _cafe(monkeypatch)
    C.live_turn(card, "영상 표지")
    r = C.live_turn(card, "나중에 넣을게요")
    assert "나중에" in r["reply"] and r["question"]["slot"] == "shop_name"


def test_call_button_sets_contact_and_asks_phone(monkeypatch):
    card, _ = _cafe(monkeypatch)
    st = C.state(card)
    for s in st["steps"]:
        if s["type"] not in ("contact", "tone"):
            st["skipped"].append(s["id"])
    inquiry = next(s["id"] for s in st["steps"] if s["type"] == "contact")
    st["pending"] = inquiry
    r = C.live_turn(card, "전화 버튼으로요")
    assert E._slot(card, "contact_method")["value"] == "전화"
    assert r["question"]["slot"] == "phone"


def test_preview_shows_only_chosen_components(monkeypatch):
    card, _ = _cafe(monkeypatch)
    spec = C.preview_spec(card)
    assert [s["type"] for s in spec["sections"]] == ["hero"]  # 분위기만 정해도 첫 화면 자리가 보인다
    C.live_turn(card, "사진 크게")
    C.live_turn(card, "바다카페")
    assert "바다카페" in C.preview_html(card)
    C.live_turn(card, "분류별 메뉴판")
    assert [c["id"] for c in C.components(card)] == ["tone", "hero", "menu"]
    spec = C.preview_spec(card)
    assert [s["type"] for s in spec["sections"]] == ["hero", "offerings"]
    assert spec["sections"][0]["variant"] == "photo-overlay" and spec["tokens"]["motion"] == "gentle"
    assert "--m-dur" in C.preview_html(card)  # 움직임 토큰이 화면에 들어간다


def test_option_previews_render_each_choice_with_current_tone(monkeypatch):
    card, r = _cafe(monkeypatch)
    previews = C.option_previews(card)
    assert [p["label"] for p in previews] == r["question"]["options"][:-1]
    assert all(p["html"] and "s-hero" in p["html"] for p in previews)
    assert 'data-section-id="hero"' in previews[0]["html"]
    assert "Noto Serif KR" in previews[0]["html"]  # 따뜻한 분위기 글꼴


def test_tone_previews_differ_by_tokens(monkeypatch):
    card, _ = _cafe(monkeypatch, tone=False)
    previews = C.option_previews(card)
    assert len(previews) == 4 and len({p["html"] for p in previews}) == 4
    assert "Gowun Batang" in next(p["html"] for p in previews if p["variant"] == "elegant")


def test_required_single_option_part_is_added_without_asking(monkeypatch):
    # 펜션 객실: 빼면 안 되고 모양도 하나 → 묻지 않고 넣고, 객실 구성을 바로 묻는다
    fake_setup(monkeypatch, {"펜션이요": [u("business_type", "펜션")], "바다소리": [u("shop_name", "바다소리")]})
    card = E.new_card()
    C.live_turn(card, "펜션이요")
    C.live_turn(card, "알아서")
    C.live_turn(card, "사진 크게")
    r = C.live_turn(card, "바다소리")
    assert "rooms" in C.state(card)["chosen"] and "꼭 필요해서 넣었어요" in r["reply"]
    assert r["question"]["slot"] == "offerings"


def test_total_questions_capped_below_20(monkeypatch):
    card, _ = _cafe(monkeypatch)
    asked = 2  # 업종·분위기
    done = False
    for _ in range(40):
        r = C.live_turn(card, "알아서 해주세요")
        if r["done"]:
            done = True
            break
        asked += 1
    assert done and asked <= C.MAX_TOTAL_QUESTIONS
    assert C.state(card)["asked"] <= C.MAX_TOTAL_QUESTIONS


def test_cap_fills_remaining_parts_with_recommended(monkeypatch):
    card, _ = _cafe(monkeypatch)
    C.state(card)["asked"] = C.MAX_TOTAL_QUESTIONS
    r = C.live_turn(card, "사진 크게")
    st = C.state(card)
    assert r["done"] and "추천 모양으로 채웠어요" in r["reply"]
    assert {"hero", "menu", "around", "inquiry"} <= set(st["chosen"])


def test_every_option_is_a_real_renderer_part(monkeypatch):
    from app.services import site_render as SR
    have = set(SR.list_variants())
    for ind in ("cafe", "restaurant", "salon", "pension", "academy", "workshop"):
        card = E.new_card(ind)
        E._put(card, "business_type", S.INDUSTRIES[ind].name, S.FILLED, 1)
        for step in C._steps(card):
            for o in C._options(step, card):
                if o["variant"] and step["type"] != "tone":
                    assert f"{step['type']}--{o['variant']}" in have, (ind, step, o)


def test_every_tone_uses_real_tokens():
    from app.services import palette as PAL
    from app.services import site_render as SR
    bundle = SR._bundle()
    for tone in C.TONES:
        t = tone["tokens"]
        assert t["font_pair"] in bundle["font_pairs"] and t["radius"] in bundle["radius"]
        assert t["density"] in bundle["density"] and t["motion"] in bundle["motion"]
        assert t["image_style"] in SR._IMAGE_STYLES
        assert all(not PAL.check(p) for p in tone["palettes"])
