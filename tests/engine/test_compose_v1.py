"""시안 1안 = 말로 고른 안 (COMPOSE_INTERVIEW_CONTRACT §11): 분위기·부품·모양·손님 행동이 시안·공개본까지."""
import copy

from app.services import archetype as AT
from app.services import compose as C
from app.services import design_variants as DV
from app.services import layout_edits as LE
from app.services import prd_engine as E
from app.services import prd_schema as S
from app.services import publish_check
from app.services import site_render as SR
from app.services import youtube_embed as Y


def _card(with_choices=True):
    card = E.new_card("cafe")
    E._put(card, "business_type", "카페", S.FILLED, 1)
    E._put(card, "shop_name", "바다카페", S.FILLED, 1)
    E._put(card, "offerings", ["아메리카노", "라떼"], S.FILLED, 1)
    card["price_pairs"] = {"아메리카노": "4500원", "라떼": "5000원"}
    if with_choices:
        card["videos"] = ["https://www.youtube.com/watch?v=dQw4w9WgXcQ"]
        card["commerce"] = "order"
        st = C.state(card)
        st["steps"] = C._steps(card)
        st["tone"] = "lively"
        st["chosen"] = {"tone": "lively", "hero": "video", "menu": "cards", "commerce": "order",
                        "reviews": "slot-only", "inquiry": "call-first"}
        st["skipped"] = ["space", "around", "sign"]
        st["order"] = ["hero", "menu", "reviews", "inquiry"]
    return card


def test_v1_is_spoken_choice_and_others_stay_alternatives():
    v = DV.variants(_card())
    assert v[0]["name"] == DV.SPOKEN_NAME
    assert [(s["id"], s["variant"]) for s in v[0]["spec"]["sections"]] == [
        ("hero", "video"), ("menu", "cards"), ("reviews", "slot-only"), ("inquiry", "call-first")]
    t = v[0]["spec"]["tokens"]
    assert (t["font_pair"], t["radius"], t["motion"]) == ("round-soft", "round", "bouncy")
    assert v[1]["name"] != DV.SPOKEN_NAME and v[2]["name"] == DV.APP_NAME


def test_without_live_choices_v1_is_unchanged():
    assert DV.variants(_card(with_choices=False))[0]["name"] != DV.SPOKEN_NAME


def test_published_v1_plays_youtube_and_has_order_buttons():
    card = _card()
    v1 = DV.variants(card)[0]
    html = SR.render_site(v1["spec"], site_key="k", title=DV.title_for(card), kind=DV.kind_for(card), public=True)
    assert publish_check.check_html(html) == [] and Y.page_uses_youtube(html)
    assert html.count('data-action="order"') == 2 and "s-reviews" in html


def test_seed_makes_editor_see_spoken_layout_once():
    card = _card()
    assert C.seed_v1_edits(card)
    seeded = copy.deepcopy(card["layout_edits"]["v1"])
    bp = AT.blueprint(card)
    seen = {x["id"]: x["hidden"] for x in LE.sections(bp, 0, seeded)}
    assert seen["space"] and seen["around"] and not seen["menu"]
    assert not C.seed_v1_edits(card) and card["layout_edits"]["v1"] == seeded  # 두 번 심지 않는다
    # 심은 뒤에도 1안은 같은 구성 (청사진에 없는 후기는 이어 붙인다)
    v1 = DV.variants(card)[0]
    assert [s["id"] for s in v1["spec"]["sections"]] == ["hero", "menu", "reviews", "inquiry"]


def test_owner_editor_changes_win_over_spoken_structure():
    card = _card()
    C.seed_v1_edits(card)
    edits = card["layout_edits"]["v1"]
    edits["hidden"] = [i for i in edits["hidden"] if i != "space"]  # 편집기에서 공간 사진을 다시 켬
    v1 = DV.variants(card)[0]
    ids = [s["id"] for s in v1["spec"]["sections"]]
    assert "space" in ids and dict((s["id"], s["variant"]) for s in v1["spec"]["sections"])["menu"] == "cards"


def test_owner_shape_pick_wins_over_spoken_shape():
    """빌더에서 고른 구역 모양(COMPONENT_ENGINE_PLAN §6)이 대화에서 고른 모양보다 나중이라 이긴다."""
    card = _card()
    C.seed_v1_edits(card)
    card["layout_edits"]["v1"]["variants"] = {"menu": "compact"}  # 대화는 cards, 빌더에서 두 줄 메뉴판
    shapes = {s["id"]: s["variant"] for s in DV.variants(card)[0]["spec"]["sections"]}
    assert shapes["menu"] == "compact"
    assert shapes["hero"] == "video"  # 고르지 않은 구역은 대화 모양 그대로


def test_polish_agent_cannot_change_spoken_v1(monkeypatch):
    card = _card()

    def scramble(card_, items):
        out = copy.deepcopy(items)
        for it in out:
            it["spec"]["tokens"]["palette"] = "navy"
        return out

    monkeypatch.setattr(DV, "_agent_apply", scramble)
    v = DV.variants(card)
    assert v[0]["spec"]["tokens"]["palette"] != "navy" and v[1]["spec"]["tokens"]["palette"] == "navy"


def test_concept_follows_spoken_tone():
    from app.services import design_concept as DC
    card = _card()
    c = DC.from_tone(card)
    assert c["source"] == "tone" and c["palette"] == DV.variants(card)[0]["spec"]["tokens"]["palette"]
    assert c["mood"] == ["밝은", "발랄한", "경쾌한"] and "밝고 발랄하게" in c["reason"]
    assert "디자인 컨셉" in DC.summary_line(c)
    assert DC.from_tone(_card(with_choices=False)) is None


def test_restyle_after_design_changes_spoken_v1_tokens():
    card = _card()
    card["concept"] = {"palette": "charcoal-gold", "font_pair": "serif-elegant", "density": "roomy", "radius": "sharp"}
    assert DV.variants(card)[0]["spec"]["tokens"]["palette"] != "charcoal-gold"  # 아직 말로 고치기 전
    C.state(card)["restyled"] = True
    t = DV.variants(card)[0]["spec"]["tokens"]
    assert (t["palette"], t["font_pair"], t["motion"]) == ("charcoal-gold", "serif-elegant", "bouncy")
