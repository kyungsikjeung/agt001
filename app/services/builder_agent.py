"""빌더에서 말로 고치기 (docs/product/SAY_CONTRACT.md, B5 S1 서버).

순서: 규칙 먼저(LLM 0번) → 못 읽은 말만 LLM 1번 → 검사 → 공통 함수로 적용.
판단(plan)은 DB·파일을 쓰지 않는다. 적용은 app/api/card.py와 app/api/start.py의
공통 함수로만 한다(카드 직접 수정 경로 없음). 다음 물결의 경로는 say()를 얇게 감싼다.
"""
import copy
import json
import logging
import re
import time

from app import llm
from app.services import card_data, design_concept, funnel, prd_engine

log = logging.getLogger(__name__)

VARIANTS = ("v1", "v2", "v3")
# 되돌리기 스냅샷 유효 시간 (30분, §5)
_UNDO_TTL_SEC = 30 * 60

# §6 응답 모양
_SAY_KEYS = ("reply", "focus", "features", "undo", "rejected", "source")

# 되돌리기 말 (§2 순서 1)
_UNDO_WORDS = ("되돌", "취소", "원래대로", "돌려놔")
# 칩 켜기·끄기 말 (§2 순서 3, 긴 것부터)
_ON_VERBS = ("보여주세요", "보여줘", "보여", "넣어주세요", "넣어줘", "넣어", "넣고", "넣",
             "추가해줘", "추가", "켜줘", "켜")
_OFF_VERBS = ("없애줘", "없애", "지워줘", "지워", "숨겨주세요", "숨겨줘", "숨겨여",
              "숨겨", "빼줘", "빼", "꺼줘", "꺼", "숨")
# 라벨·동사를 뺀 나머지로 둘 수 있는 조사·어미·곁말 (§2 순서 3)
_FILLER_RE = re.compile(
    r"^(?:사진첩|사진|메뉴판|메뉴|갤러리|코너|상담|둘러보기|부분|쪽|표|판|것|거|일단|좀|"
    r"한번|다시|해주세요|주세여|주세요|줘|여|요|도|를|을|은|는|이|가|에|의|로|으로|만|와|과|랑|"
    r"바꿔줘|바꿔|보이게|되게|해줘|해|돌려|선택|그대로|지금|여기|요기|그거|이거|저거)*$")
# 안 바꾸기 (§2 순서 4): N안·앱형/앱처럼만
_VARIANT_RE = re.compile(r"([123])\s*안")
_APP_WORDS = ("앱형", "앱처럼")
# 전화 낱말 (§2 순서 7)
_PHONE_WORDS = ("전화", "번호", "연락처")
# 사실 칸 이름
_FIELD_LABEL = {"shop_name": "가게 이름", "phone": "전화번호", "hours": "영업시간",
                "location": "위치", "detail": "소개", "contact_method": "연락 방법"}
_SET_FIELD_KEYS = ("shop_name", "phone", "hours", "location", "detail", "contact_method")
# LLM이 낼 수 있는 명령 (§3)
# 모양(1~3안) 바꾸기는 말에 이런 근거가 있을 때만 (LLM이 '분위기 있게'에 안을 바꾸던 것)
_VARIANT_HINTS = ("1안", "2안", "3안", "모양", "스타일", "사진", "크게", "기본", "원래", "처음", "간결", "심플", "앱", "v1", "v2", "v3")
_LLM_OPS = ("set_field", "item", "section", "notice", "style", "variant", "feature", "ask")

PUBLISH_REPLY = "위 공개하기를 눌러 주세요."
ASK_AGAIN_REPLY = "다시 한 번 말씀해 주세요."
VAGUE_REPLY = "어느 부분을 어떻게 바꾸면 좋을까요?"

_SYSTEM = (
    "너는 가게 사이트 빌더의 편집 도우미다. HTML·CSS를 쓰지 않는다. 아래 명령만 JSON으로 낸다. "
    "사장님이 이번에 말하지 않은 가격·전화·주소·시간·이름·숫자는 절대 쓰지 않는다. 모르면 ask 하나만 낸다. "
    '출력: {"ops":[...], "reply":"한 줄"}. 명령마다 "op" 칸에 이름을 쓴다. '
    '예: {"ops":[{"op":"item","name":"라떼","price":"5,000원","add":true}],"reply":"라떼를 넣었어요"}. '
    "명령: set_field{key: 가게 이름·전화·영업시간·위치·소개·연락 방법 중 하나를 "
    "shop_name·phone·hours·location·detail·contact_method으로, value}, "
    "item{name, rename?, price?, note?, add?, remove?}, "
    "section{id, action: add·hide·show·up·down}, notice{text, popup?, off?}, style{text}, "
    "variant{variant: v1(기본형, 기본 스타일·원래대로)·v2(사진 강조형, 사진 크게)·v3(간결형, 앱처럼)}, feature{key: stamps·order}, ask{question}."
)


def _spaceless(value) -> str:
    return re.sub(r"\s+", "", str(value or ""))


def _digits(value) -> list:
    return re.findall(r"\d+", str(value or "").replace(",", ""))


def _variant_of(card: dict) -> str:
    choice = (card or {}).get("design_choice")
    return choice if choice in VARIANTS else "v1"


def _ind_key(card: dict) -> str:
    try:
        return prd_engine.industry_of(card).key
    except Exception:
        return str((card or {}).get("industry") or "other")


def _ctx_items(card: dict) -> list:
    """품목 [{name, price}]. 실제 카드(slots)와 작은 평가 카드(offerings)를 둘 다 본다."""
    pairs = card.get("price_pairs") if isinstance(card.get("price_pairs"), dict) else {}
    names: list = []
    slots = card.get("slots") or {}
    raw = (slots.get("offerings") or {}).get("value")
    if isinstance(raw, list):
        names = [str(v) for v in raw if isinstance(v, str) and v]
    elif isinstance(card.get("offerings"), list):
        names = [str(v) for v in card["offerings"] if isinstance(v, str) and v]
    for key in pairs:
        if key and key not in names:
            names.append(key)
    return [{"name": n, "price": pairs.get(n, "")} for n in names]


def _build_ctx(card: dict) -> dict:
    """plan/rules/validate가 함께 쓰는 읽기 전용 맥락. DB·파일을 건드리지 않는다."""
    card = card or {}
    variant = _variant_of(card)
    sections: list = []
    addable: list = []
    if (isinstance(card.get("sections"), list) and card["sections"]
            and isinstance(card["sections"][0], dict) and "on" in card["sections"][0]):
        for s in card["sections"]:
            if isinstance(s, dict) and s.get("id"):
                sections.append({"id": s["id"], "label": s.get("label") or s["id"],
                                 "on": bool(s.get("on"))})
        for s in (card.get("addable") or []):
            if isinstance(s, dict) and s.get("id"):
                addable.append({"id": s["id"], "label": s.get("label") or s["id"]})
    else:
        try:
            from app.api import card as card_api
            from app.services import archetype as AT
            from app.services import layout_edits as LE
            blueprint = AT.blueprint(card)
        except Exception:
            blueprint = None
            card_api = None  # type: ignore[assignment]
            LE = None  # type: ignore[assignment]
        if blueprint is not None:
            try:
                ind = prd_engine.industry_of(card)
                offer_label = prd_engine.S.label_for(ind, "offerings")
            except Exception:
                offer_label = "메뉴"
            pos = VARIANTS.index(variant)
            edits = (card.get("layout_edits") or {}).get(variant)
            for s in LE.sections(blueprint, pos, edits):
                if s["id"] in ("hero", "inquiry"):
                    continue
                node = s.get("node") or {"id": s["id"]}
                try:
                    label = card_api._section_label(node, offer_label)
                except Exception:
                    label = s["id"]
                sections.append({"id": s["id"], "label": label or s["id"],
                                 "on": not s["hidden"]})
            for node in LE.addable(blueprint, pos, edits):
                if not isinstance(node, dict) or not node.get("id"):
                    continue
                try:
                    label = card_api._section_label(node, offer_label)
                except Exception:
                    label = node["id"]
                addable.append({"id": node["id"], "label": label or node["id"]})
    notice = ((card.get("notice") or {}).get("text") or "").strip() if isinstance(
        card.get("notice"), dict) else ""
    return {"industry": _ind_key(card), "variant": variant, "sections": sections,
            "addable": addable, "items": _ctx_items(card),
            "notice": bool(notice)}


def _label_tokens(label: str) -> list:
    """'시술·가격' → ['시술·가격', '시술', '가격']. 두 글자 이상만."""
    out = []
    for part in [label, *re.split(r"[·/,]", label or "")]:
        if isinstance(part, str) and len(part.strip()) >= 2 and part.strip() not in out:
            out.append(part.strip())
    return out


def _strip_once(text: str, words: tuple) -> str:
    out = text
    for w in sorted(words, key=len, reverse=True):
        out = out.replace(w, "")
    return out


def _match_publish(text: str) -> bool:
    """§2 순서 2. '공개 전에 메뉴 바꿔'는 공개가 아니다."""
    from app.services import chat_flow
    if "전에" in text or "말고" in text:
        return False
    return bool(chat_flow._is_publish_request(text)) and len(prd_engine._norm(text)) <= 8


def _single_section(text: str, ctx: dict):
    """칩 이름 + 켜기/끄기. (명령, 시도했으나 빗나감)을 돌린다."""
    entries = list(ctx.get("sections") or []) + [
        {**a, "addable": True} for a in (ctx.get("addable") or [])]
    addable_ids = {a.get("id") for a in (ctx.get("addable") or [])}
    attempted = False
    for entry in entries:
        sid = entry.get("id")
        if not sid:
            continue
        labels = _label_tokens(entry.get("label") or sid)
        hit_label = next((lb for lb in labels if lb and lb in text), None)
        if hit_label is None:
            continue
        on = any(v in text for v in _ON_VERBS)
        off = any(v in text for v in _OFF_VERBS)
        if not on and not off:
            continue
        attempted = True
        rest = _spaceless(_strip_once(_strip_once(text, (hit_label,)),
                                      _ON_VERBS + _OFF_VERBS))
        if re.search(r"\d", rest) or not _FILLER_RE.fullmatch(rest):
            continue
        action = "add" if (on and sid in addable_ids) else ("show" if on else "hide")
        return {"op": "section", "id": sid, "action": action}, False
    return None, attempted


def _single_variant(text: str):
    """§2 순서 4. N안·앱형/앱처럼만."""
    m = _VARIANT_RE.search(text)
    app_hit = any(w in text for w in _APP_WORDS)
    if not m and not app_hit:
        return None, False
    base = f"v{m.group(1)}" if m else "v3"
    rest = _spaceless(_strip_once(text, (m.group(0),) if m else _APP_WORDS))
    rest = _strip_once(rest, _APP_WORDS)
    if not _FILLER_RE.fullmatch(rest):
        return None, True
    return {"op": "variant", "variant": base}, False


def _single_item_no(work: dict, text: str):
    """§2 순서 5. 복사본에 correct_item_row를 불러 비교한다. 원본은 그대로."""
    if not prd_engine._ROW_NO_RE.match(text):
        return None, False
    before_pairs = copy.deepcopy(work.get("price_pairs") or {})
    before_dur = copy.deepcopy(work.get("duration_pairs") or {})
    try:
        prd_engine.correct_item_row(work, text)
    except Exception:
        return None, True
    after_pairs = work.get("price_pairs") or {}
    after_dur = work.get("duration_pairs") or {}
    for name, price in after_pairs.items():
        if before_pairs.get(name) != price:
            return {"op": "item", "name": name, "price": price}, False
    for name in after_dur:
        if before_dur.get(name) != after_dur.get(name):
            return {"op": "item_row", "text": text}, False
    return None, True


def _style_gate(text: str) -> bool:
    """§2 순서 6. is_style_request 중 실제로 바꿀 게 있는 말만 규칙으로."""
    if not design_concept.is_style_request(text):
        return False
    try:
        keyword_adjust = getattr(design_concept, "_keyword_adjust", None)
        if keyword_adjust is None:
            return True
        from app.services.design_concept import rule_concept
        _, msg = keyword_adjust(dict(rule_concept(prd_engine.new_card())), text)
        return bool(msg)
    except Exception:
        return True


def _single_phone(text: str):
    """§2 순서 7. 전화 낱말 + 전화 모양 숫자만."""
    if not any(w in text for w in _PHONE_WORDS):
        return None, False
    m = re.search(r"\d[\d\s\-]*\d", text)
    if m:
        try:
            normed = prd_engine._spoken_phone(m.group(0))
        except Exception:
            normed = m.group(0)
        digits = re.sub(r"\D", "", normed)
        if 9 <= len(digits) <= 11:
            return {"op": "set_field", "key": "phone", "value": normed}, False
    return None, True


def _match_single(text: str, work: dict, ctx: dict):
    """한 토막에 규칙을 순서대로. (명령들, 전체를 LLM으로)."""
    if len(prd_engine._norm(text)) <= 12 and any(w in text for w in _UNDO_WORDS):
        return [{"op": "undo"}], False
    if _match_publish(text):
        return [], False
    ops: list = []
    op, bad = _single_section(text, ctx)
    if bad:
        return None, True
    if op:
        ops.append(op)
    op, bad = _single_variant(text)
    if bad:
        return None, True
    if op:
        ops.append(op)
    op, bad = _single_item_no(work, text)
    if bad:
        return None, True
    if op:
        ops.append(op)
    if _style_gate(text):
        ops.append({"op": "style", "text": text.strip()[:80]})
    op, bad = _single_phone(text)
    if bad:
        return None, True
    if op:
        ops.append(op)
    return ops or None, False


def rules(card: dict, text: str, ctx: dict | None = None) -> list | None:
    """§2 규칙 먼저. LLM을 부르지 않는다. 못 읽으면 None(→ LLM)."""
    text = text or ""
    work = copy.deepcopy(card or {})
    ctx = ctx if ctx is not None else _build_ctx(work)
    clauses = [c.strip() for c in re.split(r"하고 |랑 |고 |,| 그리고 ", text) if c.strip()]
    if len(clauses) <= 1:
        ops, _ = _match_single(text, work, ctx)
        return ops
    out: list = []
    for clause in clauses:
        ops, _ = _match_single(clause, work, ctx)
        if not ops:
            return None
        out.extend(ops)
    return out or None


def ask_llm(ctx: dict, text: str) -> dict:
    """§3 LLM은 명령 JSON만 낸다. 사실 값은 맥락에 넣지 않는다."""
    ctx = ctx or {}
    user_ctx = {"industry": ctx.get("industry"), "variant": ctx.get("variant"),
                "sections": ctx.get("sections"), "addable": ctx.get("addable"),
                "items": ctx.get("items"), "notice": ctx.get("notice")}
    raw = llm.chat_json(_SYSTEM, json.dumps(user_ctx, ensure_ascii=False)
                        + "\n[요청] " + text, timeout_sec=12.0, max_tokens=400)
    data = None
    try:
        data = json.loads(raw)
    except Exception:
        m = re.search(r"\{.*\}", raw or "", re.DOTALL)
        if m:
            try:
                data = json.loads(m.group(0))
            except Exception:
                data = None
    if not isinstance(data, dict) or not isinstance(data.get("ops"), list):
        raise ValueError("LLM 답을 읽지 못했어요.")
    ops = []
    for o in data["ops"]:
        # 모델이 {"item": {...}} 모양으로 내기도 한다 → {"op": "item", ...}로 편다
        if isinstance(o, dict) and "op" not in o and len(o) == 1:
            (name, body), = o.items()
            o = {"op": name, **body} if isinstance(body, dict) else {"op": name}
        if isinstance(o, dict) and o.get("op") == "variant" and "variant" not in o:
            o = {**o, "variant": o.get("value")}  # variant 대신 value에 넣기도 한다
        if isinstance(o, dict) and o.get("op") in _LLM_OPS:
            ops.append(o)
    return {"ops": ops, "reply": str(data.get("reply") or "").strip()}


def _style_changed(card: dict, text: str) -> bool:
    """§4 style 검사. 규칙 대응이면 LLM 없이, 아니면 adjust로."""
    if design_concept._keyword_adjust({}, text)[1]:  # 낱말표로 바뀌면 지금 컨셉을 볼 것 없이 통과(LLM 0번)
        return True
    try:
        current = card.get("concept") if isinstance(
            card.get("concept"), dict) else design_concept.rule_concept(card)
        new, said = design_concept.adjust(dict(current), text)
        return bool(said) or any(new.get(k) != current.get(k)
                                 for k in ("palette", "font_pair", "density", "radius", "lead"))
    except Exception:
        return False


def validate(card: dict, ctx: dict | None, text: str, ops) -> tuple:
    """§4 검사. (지킨 명령, 버린 사유)를 돌린다. 카드를 바꾸지 않는다."""
    card = card or {}
    text = text or ""
    ctx = ctx if ctx is not None else _build_ctx(card)
    kept: list = []
    rejected: list = []
    if not isinstance(ops, list):
        return [], ["다시 한 번 말씀해 주세요."]
    if len(ops) > 5:
        rejected.append("한 번에 다섯 가지까지만 고칠 수 있어요.")
        ops = ops[:5]
    t_nospace = _spaceless(text)
    t_digits = sorted(_digits(text))
    item_names = { _spaceless(i.get("name")) for i in (ctx.get("items") or [])
                   if isinstance(i, dict) and i.get("name")}
    section_ids = {s.get("id") for s in (ctx.get("sections") or []) if isinstance(s, dict)}
    section_ids |= {a.get("id") for a in (ctx.get("addable") or []) if isinstance(a, dict)}
    for op in ops:
        if not isinstance(op, dict):
            rejected.append("못 읽은 명령이 있어서 빼고 진행해요.")
            continue
        kind = op.get("op")
        if kind == "undo":
            kept.append({"op": "undo"})
            continue
        if kind == "item_row":
            if isinstance(op.get("text"), str) and op["text"].strip():
                kept.append({"op": "item_row", "text": op["text"].strip()[:200]})
            else:
                rejected.append("품목 번호 고치기를 읽지 못했어요.")
            continue
        if kind not in _LLM_OPS:
            rejected.append("못 읽은 명령이 있어서 빼고 진행해요.")
            continue
        if kind == "set_field":
            key, value = op.get("key"), str(op.get("value") or "")
            if key not in _SET_FIELD_KEYS or not value.strip() or len(value) > 200:
                rejected.append("사실 칸 고치기를 읽지 못했어요.")
                continue
            v_nospace, v_digits = _spaceless(value), sorted(_digits(value))
            if key == "phone":
                if v_digits and v_digits == t_digits:
                    kept.append({"op": "set_field", "key": key, "value": value.strip()})
                else:
                    rejected.append("말씀하지 않은 전화번호라 넣지 않았어요.")
                continue
            if v_nospace and v_nospace in t_nospace:
                kept.append({"op": "set_field", "key": key, "value": value.strip()})
            elif v_digits and v_digits == t_digits:
                kept.append({"op": "set_field", "key": key, "value": value.strip()})
            else:
                rejected.append(f"말씀하지 않은 {_FIELD_LABEL.get(key, '내용')}이라 넣지 않았어요.")
            continue
        if kind == "item":
            name = str(op.get("name") or "").strip()
            if not name or len(name) > 30:
                rejected.append("품목을 읽지 못했어요.")
                continue
            price = op.get("price")
            if price is not None and (not isinstance(price, str) or len(price) > 20):
                rejected.append("말씀하지 않은 가격이라 넣지 않았어요.")
                continue
            if isinstance(op.get("note"), str) and len(op["note"]) > 80:
                rejected.append("설명이 너무 길어서 넣지 않았어요.")
                continue
            if price is not None:
                try:
                    want = card_data.price_won(price)
                    said = card_data.price_won(text)
                except Exception:
                    want, said = None, None
                if want is None or said is None or want != said:
                    rejected.append("말씀하지 않은 가격이라 넣지 않았어요.")
                    continue
            n_nospace = _spaceless(name)
            is_new = bool(op.get("add")) or bool(str(op.get("rename") or "").strip())
            if is_new:
                new_name = _spaceless(op.get("rename") or name)
                if not new_name or new_name not in t_nospace:
                    rejected.append("새 품목 이름을 말 안에서 찾지 못했어요.")
                    continue
            elif n_nospace not in item_names and n_nospace not in t_nospace:
                rejected.append("품목을 말 안에서 찾지 못했어요.")
                continue
            clean = {"op": "item", "name": name}
            for k in ("rename", "price", "note"):
                if isinstance(op.get(k), str) and op[k].strip():
                    clean[k] = op[k].strip()
            for k in ("add", "remove"):
                if op.get(k) is True:
                    clean[k] = True
            kept.append(clean)
            continue
        if kind == "notice":
            ntext = str(op.get("text") or "")
            if bool(op.get("off")):
                kept.append({"op": "notice", "off": True})
                continue
            if not ntext.strip() or len(ntext) > 200:
                rejected.append("공지 글을 읽지 못했어요.")
                continue
            quoted = re.findall(r"[\"'‘’“”]([^\"'‘’“”]+)[\"'‘’“”]", text)
            if any(_spaceless(ntext) == _spaceless(q) for q in quoted):
                pass
            elif _spaceless(ntext) not in t_nospace:
                rejected.append("말씀하지 않은 공지라 넣지 않았어요.")
                continue
            clean = {"op": "notice", "text": ntext.strip()}
            if bool(op.get("popup")):
                clean["popup"] = True
            kept.append(clean)
            continue
        if kind == "section":
            sid, action = op.get("id"), op.get("action")
            if sid in ("hero", "inquiry"):
                rejected.append("잠긴 구역은 바꿀 수 없어요.")
                continue
            if sid not in section_ids or action not in ("add", "hide", "show", "up", "down"):
                rejected.append("구역을 말 안에서 찾지 못했어요.")
                continue
            kept.append({"op": "section", "id": sid, "action": action})
            continue
        if kind == "style":
            stext = str(op.get("text") or "")
            if _spaceless(stext) not in t_nospace:  # 말에 없는 디자인 지시를 지어내면 사장님 말 그대로 본다
                stext = text
            if not stext.strip():
                rejected.append("느낌을 읽지 못했어요.")
                continue
            if _style_changed(card, stext):
                kept.append({"op": "style", "text": stext.strip()[:80]})
            else:
                rejected.append("말씀하신 느낌을 찾지 못했어요.")
            continue
        if kind == "variant":
            if not any(w in t_nospace for w in _VARIANT_HINTS):
                rejected.append("말씀하지 않은 모양 바꾸기라 하지 않았어요.")
                continue
            if op.get("variant") in VARIANTS:
                kept.append({"op": "variant", "variant": op["variant"]})
            else:
                rejected.append("모양을 읽지 못했어요.")
            continue
        if kind == "feature":
            if op.get("key") in ("stamps", "order"):
                kept.append({"op": "feature", "key": op["key"]})
            else:
                rejected.append("그 기능은 여기서 켤 수 없어요.")
            continue
        if kind == "ask":
            q = re.sub(r"\s*\(예[^)]*\)", "", str(op.get("question") or "")).strip()
            if re.search(r"\d", q):  # 되묻기에 예시 주소·가격을 넣으면 사장님이 따라 쓸 수 있다
                q = VAGUE_REPLY
            if q:
                kept.append({"op": "ask", "question": q[:200]})
            else:
                rejected.append(VAGUE_REPLY)
            continue
        rejected.append("못 읽은 명령이 있어서 빼고 진행해요.")
    return kept, rejected


def _describe(op: dict, ctx: dict) -> str:
    kind = op.get("op")
    if kind == "section":
        label = next((s.get("label") for s in
                      list(ctx.get("sections") or []) + list(ctx.get("addable") or [])
                      if s.get("id") == op.get("id")), op.get("id"))
        return f"{label} {'켬' if op.get('action') in ('add', 'show') else '끔'}"
    if kind == "item":
        suffix = " 추가" if op.get("add") else (" 삭제" if op.get("remove") else " 가격")
        return f"{op.get('name')}{suffix}"
    if kind == "item_row":
        return "품목 표 고침"
    if kind == "set_field":
        return _FIELD_LABEL.get(op.get("key"), "내용")
    if kind == "notice":
        return "공지 끔" if op.get("off") else "공지"
    if kind == "style":
        return "느낌 바꿈"
    if kind == "variant":
        return "모양 바꿈"
    if kind == "feature":
        return "공개한 뒤 사장님 화면에서 켤 수 있어요."
    if kind == "ask":
        return op.get("question", "")
    if kind == "undo":
        return "되돌림"
    return ""


def plan(card: dict, text: str, ctx: dict | None = None) -> dict:
    """§2.5 판단. 복사본으로만 다루고 DB·파일을 쓰지 않는다."""
    if not isinstance(text, str) or not text.strip():
        raise ValueError("말이 비어 있어요.")
    if len(text) > 300:
        raise ValueError("말은 300자까지만 받을 수 있어요.")
    work = copy.deepcopy(card or {})
    ctx = ctx if ctx is not None else _build_ctx(work)
    if _match_publish(text):
        return {"ops": [], "source": "rule", "rejected": [],
                "reply": PUBLISH_REPLY}
    try:
        found = rules(work, text, ctx)
    except Exception:
        log.exception("규칙 판단 실패, LLM으로")
        found = None
    from_rules = found is not None
    source = "rule"
    reply_from_llm = ""
    if not from_rules:
        try:
            made = ask_llm(ctx, text)
        except Exception:
            log.exception("LLM 판단 실패, 되묻기")
            return {"ops": [], "source": "none", "rejected": [],
                    "reply": ASK_AGAIN_REPLY}
        source = "llm"
        found = made.get("ops") or []
        reply_from_llm = made.get("reply") or ""
    kept, rejected = validate(work, ctx, text, found)
    if not kept and rejected:  # §4: 남은 명령이 없으면 버린 사유로 되묻는다
        kept = [{"op": "ask", "question": rejected[0]}]
    if kept:
        asks = [o for o in kept if o.get("op") == "ask"]
        if asks and len(asks) == len(kept):
            reply = asks[0]["question"]
        else:
            descs = [_describe(o, ctx) for o in kept if _describe(o, ctx)]
            reply = "말로 고쳤어요: " + ", ".join(descs) if descs else VAGUE_REPLY
    else:
        reply = rejected[0] if rejected else (reply_from_llm or VAGUE_REPLY)
    if not kept and not from_rules and source == "llm" and not rejected and reply_from_llm:
        reply = reply_from_llm
    return {"ops": kept, "source": source, "rejected": rejected, "reply": reply}


def _move_section(card: dict, variant: str, sid: str, direction: str) -> tuple:
    """up·down 이동. _apply_layout 공통 함수로만 적용한다."""
    from app.api import card as card_api
    from app.services import archetype as AT
    from app.services import layout_edits as LE
    if sid in LE.LOCKED:
        raise ValueError("잠긴 구역은 바꿀 수 없어요")
    blueprint = AT.blueprint(card)
    if blueprint is None:
        raise ValueError("이 시안은 구역 편집이 안 돼요")
    pos = VARIANTS.index(variant)
    edits = (card.get("layout_edits") or {}).get(variant) or {}
    visible = [s["id"] for s in LE.sections(blueprint, pos, edits)
               if not s["hidden"] and s["id"] not in LE.LOCKED]
    if sid not in visible:
        raise ValueError("없는 구역이에요")
    order = [s["id"] for s in LE.sections(blueprint, pos, edits)]
    i = order.index(sid)
    j = i - 1 if direction == "up" else i + 1
    movable = [x for x in order if x not in LE.LOCKED]
    k = movable.index(sid)
    if (direction == "up" and k == 0) or (direction == "down" and k == len(movable) - 1):
        return sid, False
    other = movable[k - 1] if direction == "up" else movable[k + 1]
    a, b = order.index(sid), order.index(other)
    order[a], order[b] = order[b], order[a]
    cleaned_order = [x for x in order if x not in LE.LOCKED]
    changed = card_api._apply_layout(
        card, card_api.LayoutIn(variant=variant, order=cleaned_order,
                                hidden=list(edits.get("hidden") or []),
                                added=list(edits.get("added") or [])))
    return sid, changed


def apply(room: dict, session: dict, safe: str, ops: list) -> dict:
    """§5 적용. 카드 직접 수정 없이 공통 함수로만 바꾼다.

    set_field→PUT /card fields와 같은 _put, item→_apply_items, item_row→correct_item_row,
    section→_toggle_section·_apply_layout, notice→save_notice, style→adjust+apply_lock,
    variant→design_choice. feature·ask는 카드 변경 없음.
    """
    from app.api import card as card_api
    from app.api import start as start_api
    card = session.get("prd")
    if card is None:
        card = session["prd"] = prd_engine.new_card()
    turn = card.get("turn", 0) or 0
    variant = _variant_of(card)
    ctx = _build_ctx(card)
    changed: list = []
    labels: list = []
    focus = None
    kinds: list = []
    for op in ops or []:
        if not isinstance(op, dict):
            continue
        kind = op.get("op")
        if kind == "set_field":
            key = op.get("key")
            if key not in _SET_FIELD_KEYS:
                continue
            value = str(op.get("value") or "").strip()[:200]
            if key == "phone":
                value = prd_engine._spoken_phone(value)
            prd_engine._put(card, key, value, prd_engine.S.FILLED, turn, "say")
            changed.append(key)
            labels.append(_FIELD_LABEL.get(key, key))
            kinds.append("set_field")
        elif kind == "item":
            item = card_api.ItemIn(name=op.get("name") or "",
                                   rename=op.get("rename"),
                                   price=op.get("price"),
                                   note=op.get("note"),
                                   remove=bool(op.get("remove")),
                                   add=bool(op.get("add")))
            if card_api._apply_items(card, [item], turn):
                changed.append("items")
                suffix = " 추가" if op.get("add") else (" 삭제" if op.get("remove") else " 가격")
                labels.append(f"{op.get('name')}{suffix}")
            kinds.append("item")
        elif kind == "item_row":
            try:
                tag = prd_engine.correct_item_row(card, op.get("text") or "")
            except Exception:
                tag = None
            if tag:
                changed.append("items")
                labels.append(tag)
            kinds.append("item_row")
        elif kind == "section":
            sid, action = op.get("id"), op.get("action")
            if action in ("up", "down"):
                _, moved = _move_section(card, variant, sid, action)
                if moved:
                    changed.append("layout")
                    labels.append(f"{sid} 이동")
            else:
                _, did = start_api._toggle_section(card, variant, sid, action != "hide")
                if did:
                    changed.append("layout")
                desc = _describe(op, ctx)
                if desc:
                    labels.append(desc)
                if action in ("add", "show"):
                    focus = sid
            kinds.append("section")
        elif kind == "notice":
            if card_api.save_notice(card, str(op.get("text") or ""),
                                    bool(op.get("popup")) if not op.get("off") else False):
                changed.append("notice")
                labels.append("공지 끔" if op.get("off") else "공지")
            elif op.get("off") and not (card.get("notice") or {}).get("text"):
                pass
            kinds.append("notice")
        elif kind == "style":
            current = card.get("concept") if isinstance(
                card.get("concept"), dict) else design_concept.rule_concept(card)
            new, said = design_concept.adjust(dict(current), str(op.get("text") or ""))
            design_concept.apply_lock(new, card)
            card["concept"] = new
            changed.append("style")
            labels.append(said or "느낌 바꿈")
            kinds.append("style")
        elif kind == "variant":
            if op.get("variant") in VARIANTS and card.get("design_choice") != op["variant"]:
                card["design_choice"] = op["variant"]
                variant = _variant_of(card)
                changed.append("choice")
            labels.append("모양 바꿈")
            kinds.append("variant")
        elif kind in ("feature", "ask", "undo"):
            kinds.append(kind)
    return {"changed": changed, "focus": focus, "labels": labels, "kinds": kinds}


def _same(a, b) -> bool:
    """JSONB를 한 번 오간 값과도 같게 비교한다."""
    return json.dumps(a, sort_keys=True, ensure_ascii=False, default=str) == \
        json.dumps(b, sort_keys=True, ensure_ascii=False, default=str)


def _undo_record(before: dict, card: dict) -> dict:
    """말로 고치기가 바꾼 최상위 칸만 {전, 후}로 남긴다. 없던 칸은 before에 넣지 않는다."""
    keys = [k for k in set(before) | set(card)
            if k != "builder_undo" and not _same(before.get(k), card.get(k))]
    return {"keys": keys,
            "before": {k: copy.deepcopy(before[k]) for k in keys if k in before},
            "after": {k: copy.deepcopy(card[k]) for k in keys if k in card},
            "at": time.time()}


def _fresh_undo(card: dict):
    """카드 안 되돌리기 기록(sessions 열이 고정이라 카드 안에 둔다). 없거나 30분 지났거나,
    그 뒤 다른 길(칩·사진·채팅·공개 등)로 같은 칸이 또 바뀌었으면 None."""
    snap = (card or {}).get("builder_undo")
    if not isinstance(snap, dict) or not isinstance(snap.get("keys"), list):
        return None
    try:
        at = float(snap.get("at") or 0)
    except (TypeError, ValueError):
        return None
    if time.time() - at > _UNDO_TTL_SEC:
        return None
    after = snap.get("after") or {}
    if any((k in card) != (k in after) or not _same(card.get(k), after.get(k)) for k in snap["keys"]):
        return None
    return snap


def _has_undo(card: dict) -> bool:
    return _fresh_undo(card) is not None


def _current_features(session: dict, card: dict) -> list:
    from app.api import start as start_api
    try:
        return start_api._features(session, card, _variant_of(card))
    except Exception:
        return []


def undo(room: dict, session: dict, safe: str) -> dict:
    """§5 되돌리기 (1단계). 없거나 30분 지났으면 안내만."""
    from app.api import card as card_api
    card = session.get("prd") or {}
    snap = _fresh_undo(card)
    if snap is None:
        card.pop("builder_undo", None)
        return {"reply": "되돌릴 게 없어요.",
                "features": _current_features(session, card), "undo": False}
    card.pop("builder_undo", None)
    before = snap.get("before") or {}
    for key in snap["keys"]:  # 바꾼 칸만 되돌린다. 다른 칸(사진·공개 상태 등)은 그대로
        if key in before:
            card[key] = copy.deepcopy(before[key])
        else:
            card.pop(key, None)
    card_api.post_change_followup(room, session, safe, ["undo"], "되돌렸어요.")
    return {"reply": "되돌렸어요.",
            "features": _current_features(session, card), "undo": False}


def say(room: dict, session: dict, safe: str, text: str) -> dict:
    """§6 말로 고치기 한 번. 방 잠금 안에서 부르는 것을 전제로 한다.

    {"reply", "focus", "features", "undo", "rejected", "source"} 모양으로만 돌려주고,
    LLM 실패·시간 초과에도 500 대신 되묻기로 답한다. 300자 초과·빈말은 ValueError.
    """
    from app.api import card as card_api
    if not isinstance(text, str) or not text.strip():
        raise ValueError("말이 비어 있어요.")
    if len(text) > 300:
        raise ValueError("말은 300자까지만 받을 수 있어요.")
    card = session.get("prd")
    if card is None:
        card = session["prd"] = prd_engine.new_card()
    try:
        planned = plan(card, text)
    except ValueError:
        raise
    except Exception:
        log.exception("말로 고치기 판단 실패, 되묻기")
        planned = {"ops": [], "source": "none", "rejected": [],
                   "reply": ASK_AGAIN_REPLY}
    ops = planned.get("ops") or []
    source = planned.get("source") or "none"
    planned_rejected = list(planned.get("rejected") or [])
    ctx = _build_ctx(card)
    try:
        kept, rejected = validate(card, ctx, text, ops)
    except Exception:
        log.exception("말로 고치기 재검사 실패, 되묻기")
        kept, rejected = [], [ASK_AGAIN_REPLY]
    rejected = planned_rejected + [r for r in rejected if r not in planned_rejected]
    if _match_publish(text):
        return {"reply": PUBLISH_REPLY, "focus": None,
                "features": _current_features(session, card),
                "undo": _has_undo(card), "rejected": [], "source": "rule"}
    if kept and all(o.get("op") == "undo" for o in kept):
        done = undo(room, session, safe)
        return {"reply": done["reply"], "focus": None, "features": done["features"],
                "undo": done["undo"], "rejected": [], "source": source}
    changing = [o for o in kept if o.get("op") not in ("ask", "feature")]
    if not changing:
        if kept:
            descs = [_describe(o, ctx) for o in kept if _describe(o, ctx)]
            reply = " ".join(descs) if descs else planned.get("reply")
        else:
            reply = rejected[0] if rejected else (planned.get("reply") or VAGUE_REPLY)
        return {"reply": reply or VAGUE_REPLY, "focus": None,
                "features": _current_features(session, card),
                "undo": _has_undo(card), "rejected": rejected, "source": source}
    before = copy.deepcopy(card)
    card.pop("builder_undo", None)
    result = apply(room, session, safe, changing)
    record = _undo_record(before, card)  # 명령이 바꾼 칸만(후속 처리가 바꾼 공개 상태 등은 빼고)
    changed = result.get("changed") or []
    labels = result.get("labels") or []
    kinds = result.get("kinds") or []
    message = "말로 고쳤어요: " + ", ".join(labels) if labels else "말로 고쳤어요."
    try:
        card_api.post_change_followup(room, session, safe, changed or ["say"], message)
    except Exception:
        log.exception("말로 고치기 후속 처리 실패")
        raise
    record["after"] = {k: copy.deepcopy(card[k]) for k in record["keys"] if k in card}
    if record["keys"]:
        card["builder_undo"] = record
    try:
        funnel.record("builder_say",
                      props={"kind": kinds[0] if kinds else "say", "source": source})
    except Exception:
        pass
    return {"reply": message, "focus": result.get("focus"),
            "features": _current_features(session, card),
            "undo": _has_undo(card), "rejected": rejected, "source": source}
