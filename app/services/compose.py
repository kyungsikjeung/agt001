"""구성 인터뷰 (COMPOSE_INTERVIEW_CONTRACT): 업종을 알면 화면 부품을 하나씩 쉬운 말로 묻고 확정한다.

흐름 (live_turn):
  ① 업종을 모르면 기존 엔진(prd_engine) 질문을 그대로 쓴다 ("어떤 일을 하시나요?").
  ② 업종을 알면 그 원형 청사진(templates/blueprints)의 부품 후보를 순서대로 묻는다.
     질문 하나 = 부품 하나. 선택지는 렌더러에 있는 부품 종류(type--variant)에 1:1로 대응한다.
  ③ 부품이 확정되면 그 부품에 필요한 사실(메뉴→메뉴, 지도→위치)을 엔진 질문으로 바로 잇는다.
  ④ 부품을 다 정하면 남은 엔진 질문으로 돌아가고, 엔진이 끝나면 기존 요약·승인 흐름으로 넘긴다.

AI는 HTML을 쓰지 않는다. 확정된 부품만 기존 resolve·render_site로 그린다(preview_html).
구성 질문은 질문 한도(prd_engine budget) 밖으로 센다.
"""
import copy
import logging
import re
from typing import Optional

from app.services import prd_engine as E
from app.services import prd_schema as S

log = logging.getLogger(__name__)

FIRST_QUESTION = "어떤 사이트를 만들고 싶으세요? 예: 카페, 미용실, 펜션, 첼로 레슨처럼 말씀해 주세요."
SKIP = "빼기"
NO_WORDS = ("빼", "필요없", "필요 없", "안넣", "안 넣", "없어도", "아니", "괜찮아요", "됐어요", "없음")
YES_WORDS = ("네", "예", "응", "좋아", "넣어", "넣을", "그래", "할게", "보여")
LET_AI_WORDS = ("알아서", "모르겠", "몰라", "아무거나", "추천")
VIDEO_WORDS = ("영상", "비디오", "동영상")
MAX_RETRY = 1  # 못 알아들으면 한 번 다시 묻고, 그다음엔 추천값으로 둔다

# 부품 종류별 이름 (청사진 label이 없을 때)
TYPE_LABELS = {
    "offerings": "메뉴", "gallery": "사진", "around": "오시는 길", "contact": "문의",
    "booking": "예약", "rooms": "객실", "classes": "수업", "timetable": "시간표",
    "staff": "담당자", "order": "주문", "concerns": "자주 묻는 고민", "video": "영상",
    "reviews": "후기",
}

# 종류별 선택지: (보일 말, variant, 알아듣는 말). variant None = 빼기.
_HERO = (("사진 크게", "photo-overlay", ("크게", "큰 사진", "꽉", "가득", "사진 위")),
         ("사진과 소개 글 나란히", "photo-side", ("나란히", "옆에", "반반", "소개 글", "소개글")),
         ("둥근 액자 감성", "arch", ("액자", "둥근", "아치", "감성")),
         ("글씨만 깔끔하게", "text-only", ("글씨", "글만", "텍스트", "깔끔", "문구만")))
_OFFERINGS = (("분류별 메뉴판", "categories", ("분류", "메뉴판", "카테고리", "나눠")),
              ("사진 카드", "cards", ("사진", "카드")),
              ("이름·가격 목록", "list-price", ("목록", "리스트", "가격표", "간단", "이름")))
_GALLERY = (("옆으로 넘기기", "swipe", ("넘기", "스와이프", "옆으로", "슬라이드")),
            ("흘러가듯 보여주기", "marquee", ("흘러", "자동", "움직")),
            ("바둑판으로 모아 보기", "grid", ("바둑", "격자", "모아")))
_AROUND = (("지도 넣기", "map", ("지도",)),
           ("지도와 주변 안내", "map-list", ("주변", "안내", "목록")),
           ("교통편 안내", "transit", ("교통", "버스", "지하철", "주차")))
_CONTACT = (("전화 버튼 크게", "call-first", ("전화",)),
            ("카카오톡 채널", "kakao-channel", ("카톡", "카카오")),
            ("문의 글 남기기 양식", "form", ("양식", "폼", "글로", "남기")),
            ("예약 먼저", "booking-first", ("예약",)))
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
    return card.setdefault("compose", {"steps": [], "chosen": {}, "skipped": [], "pending": None,
                                       "facts": [], "retry": 0, "last": None, "order": []})


def _steps(card: dict) -> list[dict]:
    """물을 부품 순서: 첫 화면 → 1안 구역 순서 → 나머지 후보."""
    bp, _arch = _blueprint(card)
    if bp is None:
        return []
    strategies = bp.get("strategies") or []
    first = strategies[0] if strategies else {}
    out = [{"id": "hero", "type": "hero", "variant": first.get("hero") or "photo-overlay", "bind": "hero"}]
    seen = {"hero"}
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
    return out


def _label(step: dict) -> str:
    return step.get("label") or step.get("nav") or TYPE_LABELS.get(step["type"], step["type"])


def _options(step: dict, card: dict) -> list[tuple]:
    """(보일 말, variant, 알아듣는 말). 청사진 기본 variant를 맨 앞(추천)에 둔다."""
    t = step["type"]
    table = {"hero": _HERO, "offerings": _OFFERINGS, "gallery": _GALLERY,
             "around": _AROUND, "contact": _CONTACT}.get(t)
    if table is None:
        opts = [("넣기", step["variant"], YES_WORDS)]
    else:
        opts = list(table)
        base = next((o for o in opts if o[1] == step["variant"]), None)
        if base is not None:
            opts.remove(base)
            opts.insert(0, base)
        elif _variant_ok(t, step["variant"]):
            opts.insert(0, ("추천 모양", step["variant"], ()))
        if t == "offerings" and step.get("bind") == "signature":
            # 대표 메뉴 구역은 넣을지만 묻는다 (메뉴판은 따로 정한다)
            opts = [("넣기", step["variant"], YES_WORDS)]
    opts = [o for o in opts if _variant_ok(t, o[1])]
    if t not in REQUIRED_TYPES or (t == "offerings" and step.get("bind") == "signature"):
        opts.append((SKIP, None, NO_WORDS))
    return opts


def _variant_ok(section_type: str, variant: Optional[str]) -> bool:
    if variant is None:
        return True
    from app.services import site_render as SR
    try:
        return f"{section_type}--{variant}" in SR.list_variants()
    except Exception:
        return True


def question(card: dict, step: dict) -> dict:
    """부품 질문 하나: 화면 글·소리 글·선택지."""
    ind = E.industry_of(card)
    label = _label(step)
    t = step["type"]
    opts = _options(step, card)
    names = [o[0] for o in opts]
    if t == "hero":
        name = (E._slot(card, "business_type").get("value") or ind.name)
        text = (f"{E._josa(str(name), '은는')} 첫인상이 중요해요. 첫 화면을 어떻게 보여 드릴까요? "
                "영상을 넣고 싶으시면 '영상'이라고 말씀해 주세요.")
    elif t == "offerings" and step.get("bind") == "signature":
        text = f"{label if '메뉴' in label else label + ' 메뉴'} 몇 가지를 따로 크게 보여 드릴까요?"
    elif t == "offerings":
        text = f"{E._josa(label, '은는')} 어떻게 보여 드릴까요?"
    elif t == "gallery":
        text = f"{label} 사진을 넣을까요? 넣는다면 어떻게 보여 드릴까요?"
    elif t == "around":
        text = "오시는 길에 지도를 넣을까요?"
    elif t == "contact":
        text = "손님 문의는 어떤 모양으로 받을까요?"
    else:
        text = f"{label} 부분을 넣을까요?"
    speech = text + " " + ", ".join(n for n in names if n != SKIP) + (" 중에 골라 주세요." if len(names) > 1 else "")
    if SKIP in names:
        speech += " 필요 없으면 빼 달라고 하셔도 돼요."
    return {"slot": None, "kind": "compose", "component": step["id"], "text": text, "speech": speech,
            "options": names + [S.LET_AI]}


def _match(text: str, step: dict, card: dict) -> Optional[tuple]:
    """답 → (보일 말, variant). 못 알아들으면 None."""
    opts = _options(step, card)
    n = _n(text)
    if not n:
        return None
    for name, variant, _ in opts:  # 선택지 글 그대로
        if _n(name) == n or _n(name) in n:
            return name, variant
    idx = E._option_index(n, len(opts))
    if idx is not None:
        return opts[idx][:2]
    if any(_n(w) in n for w in LET_AI_WORDS):
        return opts[0][:2]
    for name, variant, words in opts:
        if any(_n(w) in n for w in words):
            return name, variant
    if any(n.startswith(_n(w)) for w in YES_WORDS):
        return opts[0][:2]
    return None


def _answer(card: dict, text: str, by=None, is_owner=True) -> str:
    """부품 질문의 답을 처리하고 확인 한마디를 돌려준다."""
    st = state(card)
    step = next((s for s in st["steps"] if s["id"] == st["pending"]), None)
    if step is None:
        st["pending"] = None
        return ""
    wants_video = step["type"] == "hero" and any(w in text for w in VIDEO_WORDS)
    hit = _match(text, step, card)
    if hit is None and wants_video:
        hit = ("사진 크게", "photo-overlay")
    if hit is None:
        if st["retry"] < MAX_RETRY:
            st["retry"] += 1
            _absorb_facts(card, text, by, is_owner)
            return "잘 못 알아들었어요. 다시 골라 주세요."
        hit = _options(step, card)[0][:2]
        note = f"우선 '{hit[0]}'으로 해 둘게요. 나중에 바꿀 수 있어요."
    else:
        note = ""
    st["retry"] = 0
    st["pending"] = None
    name, variant = hit
    if variant is None:
        st["skipped"].append(step["id"])
        reply = f"{E._josa(_label(step), '은는')} 뺐어요."
    else:
        _choose(card, step, variant, queue_facts=False)
        shown = "첫 화면" if step["type"] == "hero" else _label(step)
        reply = note or f"{E._josa(shown, '은는')} {E._josa(name, '으로', quote=True)} 할게요."
        if step["type"] == "contact" and variant in _CONTACT_METHOD and not E._satisfied(card, "contact_method"):
            # "전화 버튼 크게"를 고른 것은 사장님이 전화로 받겠다고 한 말이다.
            E._put(card, "contact_method", _CONTACT_METHOD[variant], S.FILLED, card.get("turn"), by)
        if step["type"] == "contact" and variant == "call-first" and not E._satisfied(card, "phone"):
            st["facts"].append("phone")
        for slot in FACTS.get(step["type"], ()):
            if slot in S.SLOTS and not E._satisfied(card, slot) and slot not in st["facts"]:
                st["facts"].append(slot)
    if wants_video and "video" not in [s["id"] for s in st["steps"]]:
        idx = next(i for i, s in enumerate(st["steps"]) if s["id"] == "hero") + 1
        st["steps"].insert(idx, {"id": "video", "type": "video", "variant": "card", "bind": "none", "label": "영상"})
        st["chosen"]["video"] = "card"
        st["order"].append("video")
        st["last"] = "video"
        reply += " 영상은 첫 화면 바로 아래 영상 칸으로 넣었어요. 유튜브·인스타 주소를 붙여 주시면 들어가요."
    if len(_n(text)) > 12:
        _absorb_facts(card, text, by, is_owner)  # "사진 크게요, 가게 이름은 바다카페" 같은 말의 사실도 담는다
    return reply


def _choose(card: dict, step: dict, variant: str, queue_facts: bool = True) -> None:
    st = state(card)
    st["chosen"][step["id"]] = variant
    st["order"].append(step["id"])
    st["last"] = step["id"]
    if queue_facts:
        for slot in FACTS.get(step["type"], ()):
            if slot in S.SLOTS and not E._satisfied(card, slot) and slot not in st["facts"]:
                st["facts"].append(slot)


def _absorb_facts(card: dict, text: str, by, is_owner) -> None:
    try:
        ups, _ok, _ms, _att = E.extract_detail(text, None)
        if ups:
            E.apply_updates(card, ups, text, by=by, is_owner=is_owner)
    except Exception as e:  # 추출 실패는 부품 대화를 막지 않는다
        log.info("구성 답 사실 추출 실패: %s", e)


def _ask_fact(card: dict, slot: str) -> dict:
    ind = E.industry_of(card)
    q = S.question_for(ind, slot)
    pending = {"slot": slot, "kind": "single", "options": list(q.options) + [S.LET_AI], "text": q.ask,
               "budget_free": True}
    card["pending"] = pending
    card["done"] = False
    return pending


def _drop_engine_question(card: dict, q: Optional[dict]) -> None:
    """엔진이 낸 질문을 부품 질문으로 바꿀 때 엔진 질문 수를 되돌린다."""
    if q and card.get("pending") is q:
        if E._counts_toward_budget(q):
            card["asked"] = max(0, card.get("asked", 0) - 1)
        card["pending"] = None


def next_step(card: dict, engine_result: Optional[dict] = None) -> dict:
    """다음에 할 질문. {"question", "done", "phase"}"""
    engine_q = (engine_result or {}).get("question")
    if not industry_known(card):
        if engine_result is None and card.get("pending") is None:
            return {"question": {"slot": "business_type", "kind": "single", "options": [],
                                 "text": FIRST_QUESTION}, "done": False, "phase": "kind"}
        return {"question": engine_q or card.get("pending"), "done": bool((engine_result or {}).get("done")),
                "phase": "kind"}
    st = state(card)
    if not st["steps"]:
        st["steps"] = _steps(card)
    # ③ 방금 정한 부품의 사실 칸
    while st["facts"]:
        slot = st["facts"][0]
        if E._satisfied(card, slot):
            st["facts"].pop(0)
            continue
        if (card.get("pending") or {}).get("slot") == slot:
            return {"question": card["pending"], "done": False, "phase": "fact"}
        st["facts"].pop(0)
        _drop_engine_question(card, engine_q)
        return {"question": _ask_fact(card, slot), "done": False, "phase": "fact"}
    # ② 아직 정하지 않은 부품
    for step in st["steps"]:
        if step["id"] in st["chosen"] or step["id"] in st["skipped"]:
            continue
        opts = _options(step, card)
        if len(opts) == 1 and opts[0][1]:
            # 빼면 안 되고 모양도 하나뿐인 부품(객실·수업 등)은 묻지 않고 넣는다. 내용은 사실 질문으로 잇는다.
            _choose(card, step, opts[0][1])
            st.setdefault("notes", []).append(f"{E._josa(_label(step), '은는')} 꼭 필요해서 넣었어요.")
            return next_step(card, engine_result)
        _drop_engine_question(card, engine_q)
        card["pending"] = None
        st["pending"] = step["id"]
        return {"question": question(card, step), "done": False, "phase": "compose"}
    # ④ 남은 엔진 질문
    if engine_result is not None and card.get("pending") is not None and engine_q is card.get("pending"):
        return {"question": engine_q, "done": False, "phase": "engine"}
    if card.get("pending") is not None:
        return {"question": card["pending"], "done": False, "phase": "engine"}
    res = E._ask_next(card, [], {})
    return {"question": res.get("question"), "done": bool(res.get("done")), "phase": "engine"}


def live_turn(card: dict, text: str, by=None, is_owner=True) -> dict:
    """실시간 대화 한 턴. {"reply", "question", "done", "phase", "last"}"""
    st = state(card)
    st["last"] = None
    ack = ""
    engine_result = None
    if st.get("pending"):
        card["turn"] = card.get("turn", 0) + 1
        said = card.setdefault("said", [])
        said.append((text or "")[:E.SAID_CHARS])
        ack = _answer(card, text, by, is_owner)
        if st.get("pending"):  # 다시 묻기
            step = next(s for s in st["steps"] if s["id"] == st["pending"])
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
            step = next((s for s in st["steps"] if s["id"] == sid), None)
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
    """확정된 부품 목록 (화면 목록용)."""
    st = state(card)
    out = []
    for sid in st.get("order") or []:
        step = next((s for s in st["steps"] if s["id"] == sid), None)
        if step:
            out.append({"id": sid, "type": step["type"], "variant": st["chosen"].get(sid),
                        "label": "첫 화면" if step["type"] == "hero" else _label(step)})
    return out


def preview_spec(card: dict) -> Optional[dict]:
    """확정된 부품만으로 명세를 만들고 카드 값으로 채운다. 부품이 없으면 None."""
    st = state(card)
    if not st.get("chosen"):
        return None
    bp, arch = _blueprint(card)
    if bp is None:
        return None
    from app.services import card_data as CD
    from app.services import palette as PAL
    from app.services import site_data as SD
    sections = []
    for step in st["steps"]:  # 질문 순서가 아니라 청사진 순서대로 쌓는다
        variant = st["chosen"].get(step["id"])
        if not variant:
            continue
        sec = {"id": step["id"], "type": step["type"], "variant": variant, "bind": step.get("bind", "none"),
               "content": {}}
        for key in ("label", "nav", "tone"):
            if step.get(key):
                sec[key] = step[key]
        sections.append(sec)
    if not any(s["type"] == "hero" for s in sections):
        sections.insert(0, {"id": "hero", "type": "hero", "variant": "text-only", "bind": "hero", "content": {}})
    tokens = dict(bp.get("tokens") or {})
    try:
        tokens["palette"] = PAL.pick(arch, 1)
    except Exception:
        pass
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
    for sec in resolved.get("sections") or []:
        if sec.get("type") == "video":
            sec["content"] = {"items": [{"url": u, "title": ""} for u in card.get("videos") or []]}
    return resolved


def preview_html(card: dict, site_key: str = "") -> Optional[str]:
    spec = preview_spec(card)
    if spec is None:
        return None
    from app.services import design_variants as DV
    from app.services import site_render as SR
    return SR.render_site(spec, site_key=site_key, title=DV.title_for(card), kind=DV.kind_for(card))
