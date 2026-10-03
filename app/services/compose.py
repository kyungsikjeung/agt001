"""구성 인터뷰 (COMPOSE_INTERVIEW_CONTRACT): 업종을 알면 분위기와 화면 부품을 하나씩 쉬운 말로 묻고 확정한다.

흐름 (live_turn):
  ① 업종을 모르면 "어떤 사이트를 만들고 싶으세요?" → 기존 엔진(prd_engine)이 업종을 알아듣는다.
  ② 분위기(톤앤매너)를 묻는다. 고른 분위기는 색·글꼴·모서리·여백·사진 모양·움직임 토큰 묶음이 되어
     모든 부품에 똑같이 들어간다(부품끼리 디자인이 맞게).
  ③ 업종 원형 청사진(templates/blueprints)의 부품을 첫 화면부터 하나씩 묻는다. 질문 하나 = 부품 하나.
     선택지는 렌더러 부품 종류(type--variant)에 1:1이고, 선택지마다 "어떻게 보이는지" 한 줄 설명과
     지금 분위기로 그린 작은 시안(option_previews)이 붙는다.
  ④ 부품을 정하면 그 부품에 필요한 사실(이름·메뉴·위치·전화·영상 주소)을 바로 잇는다.
  ⑤ 남은 엔진 질문으로 돌아가고, 끝나면 기존 요약·승인 흐름으로 넘긴다.
  모든 질문(①~⑤)은 합쳐서 MAX_TOTAL_QUESTIONS를 넘지 않는다. 넘으면 남은 부품은 추천 모양으로 채운다.

AI는 HTML을 쓰지 않는다. 확정된 부품만 기존 resolve·render_site로 그린다.
"""
import copy
import logging
import re
from typing import Optional

from app.services import prd_engine as E
from app.services import prd_schema as S

log = logging.getLogger(__name__)

FIRST_QUESTION = "어떤 사이트를 만들고 싶으세요? 예: 카페, 미용실, 펜션, 첼로 레슨처럼 말씀해 주세요."
MAX_TOTAL_QUESTIONS = 19  # 대표 결정(10/3): 실시간 대화 질문은 모두 합쳐 20개 미만
SKIP = "빼기"
NO_WORDS = ("빼", "필요없", "필요 없", "안넣", "안 넣", "없어도", "아니", "괜찮아요", "됐어요", "없음")
YES_WORDS = ("네", "예", "응", "좋아", "넣어", "넣을", "그래", "할게", "보여")
LET_AI_WORDS = ("알아서", "모르겠", "몰라", "아무거나", "추천")
LATER_WORDS = ("나중", "없어요", "없음", "아직")
MAX_RETRY = 1  # 못 알아들으면 한 번 다시 묻고, 그다음엔 추천값으로 둔다
VIDEO_STEP = "__video"

# ── 업종별 말투 ──────────────────────────────────────────────────────
# subject: 첫 화면 사진에 담길 것, hero: 첫 화면 질문(무엇인지 설명 포함)
INDUSTRY_COPY = {
    "cafe": {"subject": "매장과 음료",
             "hero": "카페는 첫인상이 중요해요. 손님이 사이트를 열자마자 보는 첫 화면을 어떻게 꾸밀까요?"},
    "restaurant": {"subject": "대표 음식",
                   "hero": "식당은 음식 사진 한 장이 손님을 부르죠. 사이트를 열면 처음 보이는 화면을 어떻게 꾸밀까요?"},
    "salon": {"subject": "스타일과 매장",
              "hero": "미용실은 분위기와 스타일이 첫인상이에요. 손님이 처음 보는 화면을 어떻게 보여 드릴까요?"},
    "pension": {"subject": "풍경과 객실",
                "hero": "펜션은 풍경이 먼저 보여야 예약이 늘어요. 사이트를 열면 처음 보이는 화면을 어떻게 꾸밀까요?"},
    "academy": {"subject": "수업 모습과 교실",
                "hero": "학원은 믿음이 가는 첫인상이 중요해요. 학부모님이 사이트를 처음 열었을 때 어떤 인상을 남기고 싶으세요?"},
    "workshop": {"subject": "작품과 작업 모습",
                 "hero": "공방은 손으로 만든 작품이 보이는 첫 화면이 좋아요. 처음 보이는 화면을 어떻게 꾸밀까요?"},
    "individual": {"subject": "작업과 모습",
                   "hero": "나를 처음 소개하는 화면이에요. 사이트를 열면 처음 보이는 화면을 어떻게 꾸밀까요?"},
    "group": {"subject": "모임 활동",
              "hero": "모임의 분위기가 처음 보이는 화면이에요. 어떻게 꾸밀까요?"},
    "webservice": {"subject": "서비스 화면",
                   "hero": "서비스를 처음 만나는 화면이에요. 무엇을 먼저 보여 드릴까요?"},
}
DEFAULT_COPY = {"subject": "가게",
                "hero": "{name} 사이트를 열면 제일 먼저 보이는 큰 화면이 첫 화면이에요. 어떻게 꾸밀까요?"}

# ── 분위기(톤앤매너) = 디자인 토큰 묶음 ───────────────────────────────
# 하나를 고르면 모든 부품이 같은 색·글꼴·모서리·여백·사진 모양·움직임으로 그려진다.
TONES = (
    {"key": "warm", "label": "따뜻하고 아늑하게", "words": ("따뜻", "아늑", "포근", "편안"),
     "desc": "나무색과 둥근 모서리, 부드러운 명조 제목으로 편안하게 보여요.",
     "tokens": {"font_pair": "serif-warm", "radius": "soft", "density": "comfortable",
                "image_style": "card", "motion": "gentle"},
     "palettes": ("coffee", "espresso", "brick", "moss")},
    {"key": "clean", "label": "깔끔하고 모던하게", "words": ("깔끔", "모던", "심플", "세련", "단정"),
     "desc": "군더더기 없는 글꼴과 반듯한 모서리로 산뜻하게 보여요.",
     "tokens": {"font_pair": "sans-clean", "radius": "sharp", "density": "comfortable",
                "image_style": "full-bleed", "motion": "crisp"},
     "palettes": ("navy", "cobalt", "sage", "evergreen")},
    {"key": "elegant", "label": "고급스럽고 차분하게", "words": ("고급", "차분", "우아", "럭셔리", "품격"),
     "desc": "넉넉한 여백과 우아한 글씨, 천천히 나타나는 움직임으로 여유 있게 보여요.",
     "tokens": {"font_pair": "serif-elegant", "radius": "sharp", "density": "roomy",
                "image_style": "full-bleed", "motion": "slow"},
     "palettes": ("charcoal-gold", "ink-rose", "sage", "plum")},
    {"key": "lively", "label": "밝고 발랄하게", "words": ("밝", "발랄", "귀엽", "활기", "경쾌", "톡톡", "통통"),
     "desc": "선명한 색과 동글동글한 모서리, 통통 튀는 움직임으로 경쾌하게 보여요.",
     "tokens": {"font_pair": "round-soft", "radius": "round", "density": "comfortable",
                "image_style": "card", "motion": "bouncy"},
     "palettes": ("tomato", "evergreen", "plum", "cobalt")},
)
TONE_BY_KEY = {t["key"]: t for t in TONES}
# 원형별 추천 분위기 (첫 번째가 추천)
ARCHETYPE_TONE = {"A": "warm", "B": "elegant", "C": "warm", "D": "clean", "E": "warm",
                  "F": "elegant", "G": "lively", "H": "clean"}

# ── 부품 선택지: label · variant · 알아듣는 말 · 어떻게 보이는지 ─────────────
def _o(label, variant, words, desc):
    return {"label": label, "variant": variant, "words": tuple(words), "desc": desc}


HERO_OPTIONS = {
    "photo-overlay": _o("사진 크게", "photo-overlay", ("크게", "큰 사진", "꽉", "가득", "사진 위"),
                        "{subject} 사진을 화면 가득 깔고 그 위에 이름을 크게 올려요."),
    "photo-side": _o("사진과 소개 글 나란히", "photo-side", ("나란히", "옆에", "반반", "소개 글", "소개글"),
                     "사진과 소개 글을 반반 나란히 놓아요. 설명이 잘 읽혀요."),
    "arch": _o("둥근 액자 감성", "arch", ("액자", "둥근", "아치", "감성"),
               "둥근 액자 안에 사진을 담아 잡지처럼 감성적으로 보여요."),
    "cinematic": _o("영화 포스터처럼", "cinematic", ("영화", "포스터", "어둡", "극적", "멋있"),
                    "어두운 바탕에 큰 글씨로 영화 포스터처럼 강렬하게 보여요."),
    "text-only": _o("글씨만 깔끔하게", "text-only", ("글씨", "글만", "텍스트", "문구만"),
                    "사진 없이 큰 글씨로 시작해요. 사진이 아직 없을 때 좋아요."),
    "video": _o("영상 표지", "video", ("영상", "비디오", "동영상", "유튜브"),
                "영상의 한 장면을 화면 가득 깔고 가운데에 재생 버튼을 올려요. 누르면 영상이 열려요."),
}
# 분위기마다 어울리는 첫 화면 순서 (영상 표지는 늘 마지막에 덧붙인다)
TONE_HERO = {"warm": ("photo-overlay", "arch", "photo-side", "text-only"),
             "clean": ("photo-side", "photo-overlay", "text-only", "arch"),
             "elegant": ("arch", "cinematic", "photo-overlay", "text-only"),
             "lively": ("photo-overlay", "photo-side", "arch", "text-only")}

PART_OPTIONS = {
    "offerings": (_o("분류별 메뉴판", "categories", ("분류", "메뉴판", "카테고리", "나눠"),
                     "종류별로 나눠 메뉴판처럼 이름과 가격을 보여요."),
                  _o("옆으로 넘기는 사진 카드", "cards", ("사진", "카드", "넘기", "캐러셀"),
                     "항목마다 사진·이름·가격 카드를 옆으로 넘겨 봐요(캐러셀). 주문·예약 단추도 이 카드에 붙어요."),
                  _o("이름·가격 목록", "list-price", ("목록", "리스트", "가격표", "간단", "이름"),
                     "사진 없이 이름과 가격만 한 줄씩 깔끔하게 보여요.")),
    "gallery": (_o("옆으로 넘기기", "swipe", ("넘기", "스와이프", "옆으로", "슬라이드"),
                   "손가락으로 옆으로 넘겨 보는 사진첩이에요."),
                _o("흘러가듯 보여주기", "marquee", ("흘러", "자동", "움직"), "사진이 천천히 옆으로 흘러가요."),
                _o("바둑판으로 모아 보기", "grid", ("바둑", "격자", "모아"), "여러 장을 바둑판처럼 한눈에 보여요.")),
    "around": (_o("지도 넣기", "map", ("지도",), "지도와 주소, 길찾기 버튼을 보여요."),
               _o("지도와 주변 안내", "map-list", ("주변", "안내", "목록"), "지도 아래에 주차·주변 안내를 줄로 보여요."),
               _o("교통편 안내", "transit", ("교통", "버스", "지하철", "주차"), "버스·지하철·주차 안내를 먼저 보여요.")),
    "contact": (_o("전화 버튼 크게", "call-first", ("전화",), "누르면 바로 전화가 걸리는 큰 버튼을 둬요."),
                _o("카카오톡 채널", "kakao-channel", ("카톡", "카카오"), "카카오톡 채널로 문의하는 버튼을 둬요."),
                _o("문의 글 남기기 양식", "form", ("양식", "폼", "글로", "남기"),
                   "이름·연락처·내용을 적어 보내는 양식이에요. 오면 알려 드려요."),
                _o("예약 먼저", "booking-first", ("예약",), "예약 버튼을 가장 먼저 보여요.")),
}
# 넣을지만 묻는 부품의 설명
TYPE_DESC = {
    "booking": "손님이 날짜·시간을 골라 예약을 신청해요.", "staff": "선생님·디자이너를 사진과 함께 소개해요.",
    "timetable": "요일별 수업 시간표를 보여요.", "concerns": "자주 묻는 고민과 답을 말풍선으로 보여요.",
    "order": "온라인 주문 버튼 자리를 둬요.", "rooms": "객실 사진·인원·요금을 카드로 보여요.",
    "classes": "수업을 시간·가격과 함께 카드로 보여요.", "video": "영상 카드를 보여요.",
    "offerings": "대표 몇 가지를 따로 크게 보여요.", "gallery": "사진을 모아 보여요.",
    "reviews": "지금은 자리만 두고, 주문·방문 뒤 후기가 쌓이면 여기에 보여요.",
}
ITEM_TYPES = ("offerings", "rooms", "classes")  # 파는 것을 보여 주는 부품 (항목 판단 대상)
PRICES_STEP = "__prices"
TYPE_LABELS = {
    "offerings": "메뉴", "gallery": "사진", "around": "오시는 길", "contact": "문의",
    "booking": "예약", "rooms": "객실", "classes": "수업", "timetable": "시간표",
    "staff": "담당자", "order": "주문", "concerns": "자주 묻는 고민", "video": "영상", "reviews": "후기",
}
_CONTACT_METHOD = {"call-first": "전화", "kakao-channel": "카카오톡 채널"}
# 부품을 정한 뒤 이어 물을 사실 칸
FACTS = {"hero": ("shop_name",), "offerings": ("offerings",), "around": ("location",),
         "contact": ("contact_method",), "rooms": ("offerings",), "classes": ("offerings",),
         "booking": ("hours",), "timetable": ("hours",)}
# 빼면 손님이 행동을 못 하는 부품 (빼기 선택지를 두지 않는다)
REQUIRED_TYPES = frozenset({"hero", "offerings", "contact", "rooms", "classes"})


def _n(text: str) -> str:
    return re.sub(r"[\s.,!?~·]+", "", (text or "").lower())


def _blueprint(card: dict):
    from app.services import archetype as AT
    try:
        return AT.blueprint(card), AT.of(card)[0]
    except Exception:
        return None, ""


def industry_known(card: dict) -> bool:
    if E._slot(card, "business_type")["status"] not in (S.FILLED, S.ASSUMED):
        return False
    if E.industry_of(card).key == "other" and not card.get("kind_asked"):
        return False
    return _blueprint(card)[0] is not None


def state(card: dict) -> dict:
    st = card.setdefault("compose", {})
    for key, default in (("steps", []), ("chosen", {}), ("skipped", []), ("pending", None), ("facts", []),
                         ("retry", 0), ("last", None), ("order", []), ("asked", 0), ("tone", None)):
        st.setdefault(key, copy.deepcopy(default))
    return st


def _copy(card: dict) -> dict:
    c = INDUSTRY_COPY.get(E.industry_of(card).key) or DEFAULT_COPY
    name = str(E._slot(card, "business_type").get("value") or E.industry_of(card).name)
    return {"subject": c["subject"], "hero": c["hero"].format(name=name), "name": name}


def _steps(card: dict) -> list[dict]:
    """물을 순서: 분위기 → 첫 화면 → 1안 구역 순서 → 나머지 후보."""
    bp, _arch = _blueprint(card)
    if bp is None:
        return []
    strategies = bp.get("strategies") or []
    first = strategies[0] if strategies else {}
    out = [{"id": "tone", "type": "tone", "variant": None, "bind": "none"},
           {"id": "hero", "type": "hero", "variant": first.get("hero") or "photo-overlay", "bind": "hero"}]
    seen = {"tone", "hero"}
    nodes = list(first.get("sections") or [])
    for st in strategies[1:]:
        nodes += list(st.get("sections") or [])
    for node in nodes:
        if not isinstance(node, dict) or node.get("id") in seen:
            continue
        seen.add(node["id"])
        step = {k: node[k] for k in ("id", "type", "variant", "bind", "label", "nav", "tone") if node.get(k)}
        step.setdefault("bind", "none")
        out.append(step)
    # 항목 판단(item_plan): 첫 항목 부품 뒤에 손님 행동(주문·예약)과 후기 자리를 둔다.
    from app.services import item_plan
    at = next((i for i, s in enumerate(out) if s["type"] in ITEM_TYPES and s.get("bind") != "signature"), None)
    if at is not None:
        extra = [{"id": "commerce", "type": "commerce", "variant": None, "bind": "none"}]
        if item_plan.decide(card)["reviews"] and _variant_ok("reviews", "slot-only"):
            extra.append({"id": "reviews", "type": "reviews", "variant": "slot-only", "bind": "none", "label": "후기"})
        out[at + 1:at + 1] = extra
    return out


def _step(card: dict, sid: str) -> Optional[dict]:
    return next((s for s in state(card)["steps"] if s["id"] == sid), None)


def _label(step: dict) -> str:
    if step["type"] == "hero":
        return "첫 화면"
    if step["type"] == "tone":
        return "분위기"
    if step["type"] == "commerce":
        return "손님 행동"
    return step.get("label") or step.get("nav") or TYPE_LABELS.get(step["type"], step["type"])


def _variant_ok(section_type: str, variant: Optional[str]) -> bool:
    if variant is None or section_type in ("tone", "commerce"):
        return True
    from app.services import site_render as SR
    try:
        return f"{section_type}--{variant}" in SR.list_variants()
    except Exception:
        return True


def _tone_key(card: dict) -> str:
    st = state(card)
    if st.get("tone") in TONE_BY_KEY:
        return st["tone"]
    return ARCHETYPE_TONE.get(_blueprint(card)[1], "warm")


def _options(step: dict, card: dict) -> list[dict]:
    """선택지 목록(첫 번째가 추천). 설명의 {subject}는 업종 말로 채운다."""
    t = step["type"]
    subject = _copy(card)["subject"]
    if t == "tone":
        rec = ARCHETYPE_TONE.get(_blueprint(card)[1], "warm")
        tones = sorted(TONES, key=lambda x: x["key"] != rec)
        return [_o(x["label"], x["key"], x["words"], x["desc"]) for x in tones]
    if t == "commerce":
        from app.services import item_plan
        rec = item_plan.decide(card)["commerce"]["level"]
        opts = [_o(label, level, words, desc) for level, label, words, desc in item_plan.commerce_options(card)]
        opts.sort(key=lambda o: o["variant"] != rec)
        return opts
    if t == "hero":
        order = list(TONE_HERO.get(_tone_key(card), TONE_HERO["warm"]))
        if step.get("variant") in HERO_OPTIONS and step["variant"] not in order and not state(card).get("tone"):
            order.insert(0, step["variant"])
        order.append("video")
        opts = [dict(HERO_OPTIONS[v]) for v in order]
    elif t in PART_OPTIONS and not (t == "offerings" and step.get("bind") == "signature"):
        opts = [dict(o) for o in PART_OPTIONS[t]]
        rec = step["variant"]
        if t == "offerings":
            # 항목 판단이 고른 모양을 추천으로 (메뉴 수·사진 필요·종류 수를 보고 정한다)
            from app.services import item_plan
            layout = item_plan.decide(card)["layout"]
            if any(o["variant"] == layout for o in opts):
                rec = layout
        base = next((o for o in opts if o["variant"] == rec), None)
        if base is not None:
            opts.remove(base)
            opts.insert(0, base)
        elif _variant_ok(t, rec):
            opts.insert(0, _o("추천 모양", rec, (), "이 업종에 가장 많이 쓰는 모양이에요."))
    else:
        opts = [_o("넣기", step["variant"], YES_WORDS, TYPE_DESC.get(t, "이 부분을 넣어요."))]
    for o in opts:
        o["desc"] = o["desc"].format(subject=subject)
    opts = [o for o in opts if _variant_ok(t, o["variant"])]
    if t not in REQUIRED_TYPES and t != "tone" or (t == "offerings" and step.get("bind") == "signature"):
        opts.append(_o(SKIP, None, NO_WORDS, "이 부분은 넣지 않아요."))
    return opts


def _item_why(card: dict) -> str:
    """항목 판단 이유 중 사진·모양 두 문장 (질문 앞에 붙여 왜 이걸 추천하는지 말한다)."""
    from app.services import item_plan
    plan = item_plan.decide(card)
    if not plan["count"]:
        return ""
    return " ".join(plan["reasons"][:2])


def question(card: dict, step: dict) -> dict:
    """부품 질문 하나: 화면 글·소리 글(선택지마다 한 줄 설명)·선택지."""
    t = step["type"]
    label = _label(step)
    opts = _options(step, card)
    words = _copy(card)
    if t == "tone":
        text = f"어떤 느낌의 {words['name']} 사이트를 원하세요? 고른 느낌으로 색·글씨·움직임을 모든 화면에 맞춰 드려요."
    elif t == "hero":
        text = words["hero"]
    elif t == "offerings" and step.get("bind") == "signature":
        text = f"{label if '메뉴' in label else label + ' 메뉴'} 몇 가지를 따로 크게 보여 드릴까요?"
    elif t == "offerings":
        text = f"{E._josa(label, '은는')} 어떻게 보여 드릴까요?"
        why = _item_why(card)
        if why:
            text = f"{why} {text}"
    elif t == "commerce":
        from app.services import item_plan
        noun = item_plan.decide(card)["noun"]
        text = (f"손님이 {E._josa(noun, '을를')} 보고 나서 무엇을 하게 할까요? "
                "나중에 바꿔도 같은 카드에 단추만 바뀌어요.")
    elif t == "reviews":
        text = "손님 후기 자리를 만들어 둘까요? 지금은 비어 있고, 주문·방문 뒤 후기가 쌓이면 보여요."
    elif t == "gallery":
        text = f"{label} 사진을 넣을까요? 넣는다면 어떻게 보여 드릴까요?"
    elif t == "around":
        text = "오시는 길은 어떻게 안내할까요?"
    elif t == "contact":
        text = "손님 문의는 어떤 모양으로 받을까요?"
    else:
        text = f"{label} 부분을 넣을까요? {TYPE_DESC.get(t, '')}".strip()
    ordinals = ("첫째", "둘째", "셋째", "넷째", "다섯째", "여섯째")
    parts = [text] + [f"{ordinals[i] if i < len(ordinals) else str(i + 1) + '번'}, {o['label']}. {o['desc']}"
                      for i, o in enumerate(opts) if o["variant"] is not None]
    if any(o["variant"] is None for o in opts):
        parts.append("필요 없으면 빼 달라고 하셔도 돼요.")
    out_why = []
    if t in ITEM_TYPES or t in ("commerce", "reviews"):
        from app.services import item_plan
        out_why = item_plan.decide(card)["reasons"]
    return {"slot": None, "kind": "compose", "component": step["id"], "text": text, "why": out_why,
            "speech": " ".join(parts), "speech_parts": parts,
            "options": [o["label"] for o in opts] + [S.LET_AI],
            "option_desc": [o["desc"] for o in opts] + ["추천 모양으로 해 드려요."]}


def _match(text: str, step: dict, card: dict) -> Optional[dict]:
    """답 → 선택지. 못 알아들으면 None."""
    opts = _options(step, card)
    n = _n(text)
    if not n:
        return None
    for o in opts:  # 선택지 글 그대로
        if _n(o["label"]) == n or _n(o["label"]) in n:
            return o
    idx = E._option_index(n, len(opts))
    if idx is not None:
        return opts[idx]
    if any(_n(w) in n for w in LET_AI_WORDS):
        return opts[0]
    for o in opts:
        if any(_n(w) in n for w in o["words"]):
            return o
    if any(n.startswith(_n(w)) for w in YES_WORDS):
        return opts[0]
    return None


def _item_step_id(card: dict) -> Optional[str]:
    st = state(card)
    return next((x["id"] for x in st["steps"] if x["type"] in ITEM_TYPES and x["id"] in st["chosen"]), None)


def _choose(card: dict, step: dict, variant: str, queue_facts: bool = True) -> None:
    st = state(card)
    if step["type"] == "tone":
        st["tone"] = variant
        st["chosen"]["tone"] = variant
        st["last"] = None  # 분위기는 화면 전체가 바뀐다
        return
    if step["type"] == "commerce":
        from app.services import item_plan
        card["commerce"] = variant
        st["chosen"]["commerce"] = variant
        st["last"] = _item_step_id(card)  # 카드에 단추가 붙는 것을 보여 준다
        if variant in ("order", "pay") and item_plan.decide(card)["commerce"]["missing_price"]:
            if PRICES_STEP not in st["facts"]:
                st["facts"].append(PRICES_STEP)
        return
    st["chosen"][step["id"]] = variant
    if step["id"] not in st["order"]:
        st["order"].append(step["id"])
    st["last"] = step["id"]
    if queue_facts:
        _queue_facts(card, step)


def _queue_facts(card: dict, step: dict) -> None:
    st = state(card)
    for slot in FACTS.get(step["type"], ()):
        if slot in S.SLOTS and not E._satisfied(card, slot) and slot not in st["facts"]:
            st["facts"].append(slot)


def _answer(card: dict, text: str, by=None, is_owner=True) -> str:
    """부품·분위기 질문의 답을 처리하고 확인 한마디를 돌려준다."""
    st = state(card)
    step = _step(card, st["pending"])
    if step is None:
        st["pending"] = None
        return ""
    hit = _match(text, step, card)
    note = ""
    if hit is None:
        if st["retry"] < MAX_RETRY:
            st["retry"] += 1
            _absorb_facts(card, text, by, is_owner)
            return "잘 못 알아들었어요. 다시 골라 주세요."
        hit = _options(step, card)[0]
        note = f"우선 {E._josa(hit['label'], '으로', quote=True)} 해 둘게요. 나중에 바꿀 수 있어요."
    st["retry"] = 0
    st["pending"] = None
    if hit["variant"] is None:
        st["skipped"].append(step["id"])
        reply = f"{E._josa(_label(step), '은는')} 뺐어요."
    else:
        _choose(card, step, hit["variant"], queue_facts=False)
        if step["type"] == "tone":
            reply = note or f"좋아요, {E._josa(hit['label'], '으로', quote=True)} 맞출게요. 색과 글씨가 바뀌었어요."
        elif step["type"] == "commerce":
            from app.services import item_plan
            act = item_plan.item_action(card)
            reply = note or (f"{E._josa(hit['label'].split(' (')[0], '으로', quote=True)} 할게요."
                             + (f" 카드마다 '{act['label']}' 단추를 붙였어요." if act else ""))
        else:
            if hit["label"] == "넣기":
                reply = note or f"{_label(step)} 부분을 넣었어요."
            else:
                reply = note or f"{E._josa(_label(step), '은는')} {E._josa(hit['label'], '으로', quote=True)} 할게요."
        if step["type"] == "contact" and hit["variant"] in _CONTACT_METHOD and not E._satisfied(card, "contact_method"):
            # "전화 버튼 크게"를 고른 것은 사장님이 전화로 받겠다고 한 말이다.
            E._put(card, "contact_method", _CONTACT_METHOD[hit["variant"]], S.FILLED, card.get("turn"), by)
        if step["type"] == "contact" and hit["variant"] == "call-first" and not E._satisfied(card, "phone"):
            st["facts"].append("phone")
        if step["type"] == "hero" and hit["variant"] == "video" and not card.get("videos"):
            st["facts"].append(VIDEO_STEP)
        _queue_facts(card, step)
    if len(_n(text)) > 12:
        _absorb_facts(card, text, by, is_owner)  # "사진 크게요, 가게 이름은 바다카페" 같은 말의 사실도 담는다
    return reply


def _absorb_facts(card: dict, text: str, by, is_owner, last_question: Optional[str] = None) -> None:
    try:
        ups, _ok, _ms, _att = E.extract_detail(text, last_question)
        if ups:
            E.apply_updates(card, ups, text, by=by, is_owner=is_owner)
    except Exception as e:  # 추출 실패는 부품 대화를 막지 않는다
        log.info("구성 답 사실 추출 실패: %s", e)


def _take_videos(card: dict, text: str) -> int:
    from app.services.video_links import extract_video_links
    found = extract_video_links(text or "")
    if found:
        card["videos"] = list(dict.fromkeys((card.get("videos") or []) + found))[:3]
    return len(found)


def _ask_fact(card: dict, slot: str) -> dict:
    if slot == VIDEO_STEP:
        state(card)["pending"] = VIDEO_STEP
        card["pending"] = None
        text = "첫 화면에 넣을 영상 주소를 붙여 주세요. 유튜브·인스타그램·네이버TV 주소면 돼요."
        return {"slot": None, "kind": "compose_video", "component": "hero", "text": text,
                "speech": text + " 아직 없으면 나중에 넣는다고 말씀해 주세요.",
                "options": ["나중에 넣을게요"], "option_desc": ["지금은 사진으로 대신 보여요."]}
    ind = E.industry_of(card)
    q = S.question_for(ind, slot)
    pending = {"slot": slot, "kind": "single", "options": list(q.options) + [S.LET_AI], "text": q.ask,
               "budget_free": True}
    card["pending"] = pending
    card["done"] = False
    return pending


def _ask_prices(card: dict, missing: list) -> dict:
    """주문을 켰는데 가격이 빠진 항목 (가격이 있어야 주문 단추가 켜진다)."""
    state(card)["pending"] = PRICES_STEP
    card["pending"] = None
    names = ", ".join(missing[:5]) + (" 등" if len(missing) > 5 else "")
    text = f"주문을 받으려면 가격이 필요해요. {names}의 가격을 알려 주세요. 예: {missing[0]} 5,000원"
    return {"slot": None, "kind": "compose_prices", "component": None, "text": text,
            "speech": text + " 나중에 넣어도 돼요.", "options": ["나중에 넣을게요"],
            "option_desc": ["가격을 넣으면 그때 주문 단추가 켜져요."]}


def _drop_engine_question(card: dict, q: Optional[dict]) -> None:
    """엔진이 낸 질문을 부품 질문으로 바꿀 때 엔진 질문 수를 되돌린다."""
    if q and card.get("pending") is q:
        if E._counts_toward_budget(q):
            card["asked"] = max(0, card.get("asked", 0) - 1)
        card["pending"] = None


def _wrap_up(card: dict) -> None:
    """질문 상한: 정하지 못한 부품은 추천 모양으로 채우고 엔진을 마친다."""
    st = state(card)
    for step in st["steps"]:
        if step["id"] in st["chosen"] or step["id"] in st["skipped"]:
            continue
        first = next((o for o in _options(step, card) if o["variant"]), None)
        if first:
            _choose(card, step, first["variant"], queue_facts=False)
    st["pending"] = None
    st["facts"] = []
    card["pending"] = None
    st["last"] = None
    st.setdefault("notes", []).append("질문이 많아져서 남은 부분은 추천 모양으로 채웠어요. 채팅방에서 언제든 바꿀 수 있어요.")
    E.finalize(card)


def _ask(card: dict, out: dict) -> dict:
    """새 질문을 낼 때마다 센다. 상한이면 마무리한다."""
    st = state(card)
    if out.get("question") and not out.get("done"):
        if st["asked"] >= MAX_TOTAL_QUESTIONS:
            _wrap_up(card)
            return {"question": None, "done": True, "phase": "engine"}
        st["asked"] += 1
    return out


def next_step(card: dict, engine_result: Optional[dict] = None) -> dict:
    """다음에 할 질문. {"question", "done", "phase"}"""
    engine_q = (engine_result or {}).get("question")
    if not industry_known(card):
        if engine_result is None and card.get("pending") is None:
            return _ask(card, {"question": {"slot": "business_type", "kind": "single", "options": [],
                                            "text": FIRST_QUESTION}, "done": False, "phase": "kind"})
        return _ask(card, {"question": engine_q or card.get("pending"),
                           "done": bool((engine_result or {}).get("done")), "phase": "kind"})
    st = state(card)
    if not st["steps"]:
        st["steps"] = _steps(card)
    # ④ 방금 정한 부품의 사실 칸
    while st["facts"]:
        slot = st["facts"][0]
        if slot == VIDEO_STEP and card.get("videos"):
            st["facts"].pop(0)
            continue
        if slot == PRICES_STEP:
            st["facts"].pop(0)
            from app.services import item_plan
            missing = item_plan.decide(card)["commerce"]["missing_price"]
            if not missing:
                continue
            _drop_engine_question(card, engine_q)
            return _ask(card, {"question": _ask_prices(card, missing), "done": False, "phase": "fact"})
        if slot != VIDEO_STEP and E._satisfied(card, slot):
            st["facts"].pop(0)
            continue
        if slot != VIDEO_STEP and (card.get("pending") or {}).get("slot") == slot:
            return {"question": card["pending"], "done": False, "phase": "fact"}
        st["facts"].pop(0)
        _drop_engine_question(card, engine_q)
        return _ask(card, {"question": _ask_fact(card, slot), "done": False, "phase": "fact"})
    # ②③ 아직 정하지 않은 분위기·부품
    for step in st["steps"]:
        if step["id"] in st["chosen"] or step["id"] in st["skipped"]:
            continue
        if step["type"] == "commerce":
            from app.services import item_plan
            plan = item_plan.decide(card)
            if not plan["commerce"]["ask"]:
                # 업종·대화로 이미 알 수 있으면 묻지 않고 정하고 알린다 (미용실=예약, 펜션=예약 …)
                _choose(card, step, plan["commerce"]["level"])
                act = item_plan.item_action(card)
                if act:
                    st.setdefault("notes", []).append(f"{plan['noun']}마다 '{act['label']}' 단추를 붙였어요.")
                return next_step(card, engine_result)
        if (step["type"] == "offerings" and step.get("bind") != "signature"
                and not E._satisfied(card, "offerings") and not st.get("items_asked")):
            # 항목을 먼저 듣고 나서 어떻게 보여 줄지 판단한다 (메뉴 수·가격·사진 필요를 보고 추천)
            st["items_asked"] = True
            st.setdefault("notes", []).append(f"{E._josa(_label(step), '을를')} 먼저 알려 주시면 어떻게 보여 드릴지 판단해 볼게요.")
            _drop_engine_question(card, engine_q)
            return _ask(card, {"question": _ask_fact(card, "offerings"), "done": False, "phase": "fact"})
        opts = _options(step, card)
        if len(opts) == 1 and opts[0]["variant"]:
            # 빼면 안 되고 모양도 하나뿐인 부품(객실·수업 등)은 묻지 않고 넣는다. 내용은 사실 질문으로 잇는다.
            _choose(card, step, opts[0]["variant"])
            st.setdefault("notes", []).append(f"{E._josa(_label(step), '은는')} 꼭 필요해서 넣었어요.")
            return next_step(card, engine_result)
        _drop_engine_question(card, engine_q)
        card["pending"] = None
        st["pending"] = step["id"]
        return _ask(card, {"question": question(card, step), "done": False, "phase": "compose"})
    # ⑤ 남은 엔진 질문
    if engine_result is not None and card.get("pending") is not None and engine_q is card.get("pending"):
        return _ask(card, {"question": engine_q, "done": False, "phase": "engine"})
    if card.get("pending") is not None:
        return {"question": card["pending"], "done": False, "phase": "engine"}
    res = E._ask_next(card, [], {})
    return _ask(card, {"question": res.get("question"), "done": bool(res.get("done")), "phase": "engine"})


def pending_question(card: dict) -> Optional[dict]:
    """지금 걸려 있는 질문(다시 열었을 때 보여 주기용, 세지 않음)."""
    st = state(card)
    if st.get("pending") == VIDEO_STEP:
        q = _ask_fact(card, VIDEO_STEP)
        return q
    if st.get("pending") == PRICES_STEP:
        from app.services import item_plan
        missing = item_plan.decide(card)["commerce"]["missing_price"]
        return _ask_prices(card, missing) if missing else None
    if st.get("pending"):
        step = _step(card, st["pending"])
        return question(card, step) if step else None
    return card.get("pending")


def live_turn(card: dict, text: str, by=None, is_owner=True) -> dict:
    """실시간 대화 한 턴. {"reply", "question", "done", "phase", "last"}"""
    st = state(card)
    st["last"] = None
    ack = ""
    engine_result = None
    got_video = _take_videos(card, text)
    if st.get("pending") == PRICES_STEP:
        card["turn"] = card.get("turn", 0) + 1
        st["pending"] = None
        if any(w in (text or "") for w in LATER_WORDS):
            ack = "가격은 나중에 넣어요. 넣으면 그 항목에 주문 단추가 켜져요."
        else:
            before = dict(card.get("price_pairs") or {})
            # 직전 질문(가격)을 함께 넘겨 "5500원"만 말해도 가격으로 알아듣게 한다
            _absorb_facts(card, text, by, is_owner, last_question="메뉴 가격을 알려 주세요.")
            added = [k for k in (card.get("price_pairs") or {}) if k not in before]
            ack = (f"가격을 넣었어요: {', '.join(added)}. 주문 단추가 켜졌어요." if added
                   else "가격을 알아듣지 못했어요. 채팅방에서 나중에 넣을 수 있어요.")
        st["last"] = _item_step_id(card)
    elif st.get("pending") == VIDEO_STEP:
        card["turn"] = card.get("turn", 0) + 1
        st["pending"] = None
        st["last"] = "hero"
        if got_video:
            ack = "영상을 첫 화면에 넣었어요."
        else:
            ack = "영상은 나중에 넣어요. 그동안은 사진으로 보여 드릴게요."
    elif st.get("pending"):
        card["turn"] = card.get("turn", 0) + 1
        said = card.setdefault("said", [])
        said.append((text or "")[:E.SAID_CHARS])
        ack = _answer(card, text, by, is_owner)
        if st.get("pending"):  # 다시 묻기 (세지 않는다)
            step = _step(card, st["pending"])
            return {"reply": ack, "question": question(card, step), "done": False, "phase": "compose",
                    "last": None}
    else:
        before = {k: copy.deepcopy(v) for k, v in (card.get("slots") or {}).items()}
        engine_result = E.turn(card, text, by=by, is_owner=is_owner)
        if engine_result.get("blocked"):
            return {"reply": f"그 요청은 도와드릴 수 없어요. ({engine_result['blocked']})",
                    "question": card.get("pending"), "done": False, "phase": "engine", "last": None}
        changed = [k for k, v in (card.get("slots") or {}).items() if before.get(k) != v]
        st["last"] = _component_for_slots(card, changed)
        applied = engine_result.get("applied") or []
        ack = E.ack_text(card, applied).strip() if applied else ""
    nxt = next_step(card, engine_result)
    notes = st.pop("notes", None) or []
    reply = " ".join(x for x in [ack, *notes] if x)
    return {"reply": reply, "question": nxt["question"], "done": nxt["done"], "phase": nxt["phase"],
            "last": st.get("last")}


def _component_for_slots(card: dict, slots: list) -> Optional[str]:
    """바뀐 사실 칸이 보이는 부품 id (미리보기 강조용)."""
    st = state(card)
    by_type = {"shop_name": "hero", "detail": "hero", "offerings": "offerings", "price": "offerings",
               "location": "around", "hours": "around", "phone": "contact", "contact_method": "contact"}
    for slot in slots:
        t = by_type.get(slot)
        if not t:
            continue
        for sid in st.get("order") or []:
            step = _step(card, sid)
            if step and step["type"] == t:
                return sid
    return None


def format_text(q: Optional[dict]) -> str:
    if not q:
        return ""
    opts = [o for o in (q.get("options") or []) if o]
    if not opts:
        return q.get("text", "")
    return q.get("text", "") + "\n" + "  ".join(f"{i}) {o}" for i, o in enumerate(opts, 1))


def speech_text(q: Optional[dict]) -> str:
    if not q:
        return ""
    if q.get("speech"):
        return q["speech"]
    opts = [o for o in (q.get("options") or []) if o and o != S.LET_AI]
    return q.get("text", "") + (" " + ", ".join(opts) + " 중에 말씀해 주세요." if opts else "")


def components(card: dict) -> list[dict]:
    """확정된 부품 목록 (화면 목록용). 분위기는 맨 앞에 둔다."""
    st = state(card)
    out = []
    if st.get("tone") in TONE_BY_KEY:
        out.append({"id": "tone", "type": "tone", "variant": st["tone"],
                    "label": TONE_BY_KEY[st["tone"]]["label"]})
    for sid in st.get("order") or []:
        step = _step(card, sid)
        if step:
            out.append({"id": sid, "type": step["type"], "variant": st["chosen"].get(sid), "label": _label(step)})
    if card.get("commerce"):
        from app.services import item_plan
        out.append({"id": "commerce", "type": "commerce", "variant": card["commerce"],
                    "label": item_plan.COMMERCE_LABEL.get(card["commerce"], "")})
    return out


# ── 그리기 ──────────────────────────────────────────────────────────

def tokens_for(card: dict, tone_key: Optional[str] = None) -> dict:
    """분위기 → 디자인 토큰. 분위기를 정하기 전이면 청사진 토큰 + 원형 추천 색."""
    bp, arch = _blueprint(card)
    tone_key = tone_key or state(card).get("tone")
    if tone_key in TONE_BY_KEY:
        tone = TONE_BY_KEY[tone_key]
        tokens = dict(tone["tokens"])
        from app.services import palette as PAL
        row = PAL.ARCHETYPE_PALETTES.get(arch, ())
        # 분위기 색 후보 중 이 업종에도 어울리는 색을 먼저 고른다
        tokens["palette"] = next((p for p in tone["palettes"] if p in row), tone["palettes"][0])
        return tokens
    tokens = dict((bp or {}).get("tokens") or {})
    try:
        from app.services import palette as PAL
        tokens["palette"] = PAL.pick(arch, 1)
    except Exception:
        tokens.setdefault("palette", "espresso")
    tokens.setdefault("motion", "gentle")
    return tokens


def _spec(card: dict, picks: list, tokens: dict) -> Optional[dict]:
    """[(step, variant)] → 채운 명세."""
    bp, arch = _blueprint(card)
    if bp is None:
        return None
    from app.services import card_data as CD
    from app.services import site_data as SD
    sections = []
    for step, variant in picks:
        sec = {"id": step["id"], "type": step["type"], "variant": variant, "bind": step.get("bind", "none"),
               "content": {}}
        for key in ("label", "nav", "tone"):
            if step.get(key):
                sec[key] = step[key]
        sections.append(sec)
    spec = {"version": 3, "locked": [], "tokens": tokens, "sections": sections}
    ids = {s["id"] for s in sections}
    for key in ("primary", "secondary"):
        target = (bp.get(key) or {}).get("target")
        if bp.get(key) and target in ids:
            spec[key] = copy.deepcopy(bp[key])
    if bp.get("actionbar_secondary"):
        spec["actionbar_secondary"] = bp["actionbar_secondary"]
    work = copy.deepcopy(card)
    work["data"] = CD.build(card)
    resolved = SD.resolve(spec, work, archetype=arch)
    videos = card.get("videos") or []
    for sec in resolved.get("sections") or []:
        if sec.get("type") == "video":
            sec["content"] = {"items": [{"url": u, "title": ""} for u in videos]}
        elif sec.get("type") == "hero" and sec.get("variant") == "video" and videos:
            sec.setdefault("content", {})["video_url"] = videos[0]
    return resolved


def preview_spec(card: dict) -> Optional[dict]:
    """확정된 부품만, 청사진 순서대로. 정한 것이 없으면 None."""
    st = state(card)
    if not st.get("chosen"):
        return None
    if not st["steps"]:
        st["steps"] = _steps(card)
    picks = [(s, st["chosen"][s["id"]]) for s in st["steps"]
             if s["type"] not in ("tone", "commerce") and st["chosen"].get(s["id"])]
    if not any(s["type"] == "hero" for s, _v in picks):
        hero = _step(card, "hero") or {"id": "hero", "type": "hero", "bind": "hero"}
        picks.insert(0, (hero, (TONE_HERO.get(_tone_key(card)) or ("photo-overlay",))[0]))
    return _spec(card, picks, tokens_for(card))


def _render(card: dict, spec: Optional[dict], site_key: str = "") -> Optional[str]:
    if spec is None:
        return None
    from app.services import design_variants as DV
    from app.services import site_render as SR
    return SR.render_site(spec, site_key=site_key, title=DV.title_for(card), kind=DV.kind_for(card))


def preview_html(card: dict, site_key: str = "") -> Optional[str]:
    return _render(card, preview_spec(card), site_key)


def option_previews(card: dict) -> list[dict]:
    """지금 질문의 선택지마다 작은 시안 (지금 분위기 토큰으로). 빼기는 html 없음."""
    st = state(card)
    step = _step(card, st.get("pending") or "")
    if step is None:
        return []
    out = []
    for o in _options(step, card):
        html = None
        if o["variant"] is not None:
            try:
                if step["type"] == "commerce":
                    # 손님 행동은 부품이 아니라 카드의 단추다: 항목 부품을 그 행동으로 그려 단추 차이를 보여 준다
                    item = _step(card, _item_step_id(card) or "")
                    if item is not None:
                        work = copy.deepcopy(card)
                        work["commerce"] = o["variant"]
                        picks = [(item, st["chosen"][item["id"]])]
                        contact = next((x for x in st["steps"] if x["type"] == "contact"), None)
                        if contact:
                            picks.append((contact, st["chosen"].get(contact["id"]) or contact["variant"]))
                        html = _render(work, _spec(work, picks, tokens_for(card)))
                elif step["type"] == "tone":
                    hero = _step(card, "hero")
                    first_part = next((s for s in st["steps"] if s["type"] in ("offerings", "rooms", "classes")), None)
                    tone_hero = (TONE_HERO.get(o["variant"]) or ("photo-overlay",))[0]
                    picks = [(hero, st["chosen"].get("hero") or tone_hero)]
                    if first_part:
                        picks.append((first_part, st["chosen"].get(first_part["id"]) or first_part["variant"]))
                    html = _render(card, _spec(card, picks, tokens_for(card, o["variant"])))
                else:
                    html = _render(card, _spec(card, [(step, o["variant"])], tokens_for(card)))
            except Exception as e:  # 시안 하나가 실패해도 질문은 이어 간다
                log.info("선택지 시안 실패 %s/%s: %s", step["id"], o["variant"], e)
        out.append({"label": o["label"], "desc": o["desc"], "variant": o["variant"], "html": html})
    return out
