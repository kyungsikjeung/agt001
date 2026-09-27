"""대화 상태머신. 1:1 `/chat`과 공유방 `/room/{id}/chat`이 같은 본체를 공유한다.

상태: GREETING → GATHERING → AWAIT_APPROVAL → QUOTED → GENERATING → DONE
room을 넘기면 주요 전이마다 room["ai_status"]를 갱신해 다른 참여자가 AI 진행 상황을 보게 한다.
"""
import logging
import re
import uuid
from typing import Optional

from app import store
from app.services import codegen, deploy, design, design_concept, design_log, funnel, prd_engine, prd_schema, quote, rag

log = logging.getLogger(__name__)


# 짧은 대답의 뜻(B-6·BACKLOG S-1): "승인할게요", "진행해 주세요", "좋아요!"도 알아듣는다.
# 정확일치 + 앞머리 + 자연문 포함(30자까지). 거절·부정은 승인보다 먼저 본다.
_INTENT_EXACT = {
    "approve": ("승인", "네", "예", "yes", "approve", "좋아요", "좋습니다", "찬성", "ok", "오케이", "넵", "응",
                "확인", "확정", "확정합니다", "좋습니다진행", "맘에들어", "마음에들어"),
    "reject": ("거절", "아니오", "아니요", "no", "reject", "반대", "싫어요", "별로예요", "별로", "다시", "고쳐"),
    "proceed": ("진행", "네", "예", "yes", "proceed", "좋아요", "시작", "만들어주세요", "넵", "응",
                "만들어줘", "시안만들어", "시안보여줘", "계속", "다음", "넘어가"),
}
_INTENT_PREFIX = {"approve": ("승인", "찬성", "좋아", "확인했", "확정"),
                  "reject": ("거절", "반대"),
                  "proceed": ("진행", "만들어", "시작해")}
# 자연문 안에 들어있어도 뜻으로 보는 말 (30자까지). "승인할게요, 진행해줘" 같은 합친 말도 잡는다.
_INTENT_CONTAINS = {
    "approve": ("승인할게", "승인해", "확인했어", "확정할게", "좋아요진행", "맘에들어"),
    "reject": ("고쳐줘", "바꿔줘", "별로야", "아니야"),
    "proceed": ("진행해", "만들어줘", "시안만들어", "공개전시", "다음으로"),
}
_NEGATION = ("안할", "안해", "말고", "취소", "그만")


def intent(text: str, kind: str) -> bool:
    """kind('approve'·'reject'·'proceed') 뜻의 대답인지. 짧은 답 + 구체적인 자연문만 본다."""
    n = prd_engine._norm(text)
    if not n:
        return False
    if kind != "reject" and any(w in n for w in _NEGATION):
        return False
    exact = {prd_engine._norm(w) for w in _INTENT_EXACT[kind]}
    if n in exact:
        return True
    # 앞머리 매칭은 짧은 답에만 쓴다 ("승인 조건이 뭐예요" 같은 긴 질문 오인 방지).
    if len(n) <= 12 and n.startswith(_INTENT_PREFIX[kind]):
        return True
    # 자연문: 구체적인 합친 말만 본다 ("승인 조건이 뭐예요" 같은 질문은 제외).
    # bare "승인·진행" 포함만으로는 인정하지 않는다.
    if len(n) <= 30 and any(w in n for w in _INTENT_CONTAINS[kind]):
        return True
    return False


def new_session(template_id: Optional[str] = None) -> dict:
    session = {"state": "GREETING", "requirement_id": str(uuid.uuid4())[:8]}
    if template_id in prd_engine.S.INDUSTRIES and template_id != "other":
        # B-15·D26: 랜딩에서 업종 템플릿을 골랐으면 업종과 구성만 가정으로 채운 카드로 시작한다.
        session["prd"] = prd_engine.new_card(template_id)
    return session


def _set_room_status(room: Optional[dict], status: str, persist: bool = False) -> None:
    if room is None:
        return
    room["ai_status"] = status
    if persist:
        # 긴 NIM 호출 전에 바로 커밋해 두어야 폴링하는 다른 참여자가 진행 상태를 볼 수 있다.
        store.set_room_ai_status(room["room_id"], status)


# 상태 전이 → 유입 단계 이벤트 (DECISIONS.md D16). 같은 트랜잭션에 기록되므로 전이가 롤백되면 함께 사라진다.
_TRANSITION_EVENTS = {
    ("GATHERING", "AWAIT_APPROVAL"): "request_submitted",
    ("GREETING", "AWAIT_APPROVAL"): "request_submitted",
    ("AWAIT_APPROVAL", "QUOTED"): "requirement_approved",
    ("QUOTED", "GENERATING"): "generate_start",
    ("GENERATING", "DONE"): "generate_done",
}


def _record_transition(session_id: str, before: str, after: str) -> None:
    event = _TRANSITION_EVENTS.get((before, after))
    if event:
        funnel.record(event, session_id=session_id)


APPROVAL_ASK = "이 내용으로 참고 견적을 만들어 볼까요? (승인/거절로 답해주세요)"


def _gate_or_summary(session: dict, card: dict, room, engine_trace, again: bool = False) -> str:
    """질문을 마친 카드를 승인으로 보내기 전의 게이트(D34 보완, 2026-09-26 대표 지적).

    검토(리뷰어)는 한 번만 돌고, 검토가 넣은 기능의 확인·방장 확인·어긋난 값이 남아 있으면 먼저 묻는다.
    모두 닫혀야 요약과 승인 질문(승인 버튼)이 나온다 — 승인 뒤에 "빠진 게 있다"가 나오지 않게."""
    gate = prd_engine.close_gate(card)
    rv = gate["review"]
    if engine_trace is not None and rv is not None:
        engine_trace["review"] = {"ok": rv["ok"], "added": rv["added"], "conflicts": len(rv["conflicts"]), "ms": rv["ms"]}
    note = prd_engine.review_text(card) if rv is not None else ""
    if gate["question"]:
        session["state"] = "GATHERING"
        return (f"{note}\n\n" if note else "") + prd_engine.format_question(card, gate["question"])
    spec = prd_engine.spec_text(card)
    session["last_request"] = spec
    session["state"] = "AWAIT_APPROVAL"
    if again:
        return f"{prd_engine.summary_text(card)}\n\n{APPROVAL_ASK}"
    # 사진 선택지는 요약 때 1회만. 일찍 물어봤으면 다시 붙이지 않는다(D48).
    photo_note = ""
    if room is not None and _photo_choice_available(card):
        card["photo_asked"] = True
        photo_note = photo_choice_text(card) + "\n\n"
    return (f"정리했어요.\n{prd_engine.summary_text(card)}\n\n" + (f"{note}\n\n" if note else "")
            + photo_note
            + f"{_rag_note(spec)}\n\n{APPROVAL_ASK}")


def _rag_note(spec: str) -> str:
    """비슷한 사례를 사람 말로. 이름만 나열하지 않고 어떻게 쓰는지 1줄로 말한다."""
    names = rag.similar(spec)
    log.info("비슷한 사례: %s", names)
    if names:
        # 기능 사례집의 '어떻게 만드는지(how)'까지 보여줘야 신뢰가 생긴다.
        try:
            from app.services import intake as _intake
            hows = []
            for nm in names:
                it = next((x for x in _intake._catalog() if x.get("name") == nm), None)
                if it and it.get("how"):
                    hows.append(f"{nm}({it['how'][:24]})")
                else:
                    hows.append(nm)
            return "비슷한 사례를 참고해 설계할게요: " + ", ".join(hows)
        except Exception:
            return "비슷한 사례를 참고해 설계할게요: " + ", ".join(names)
    return "말씀하신 내용과 업종 기본 구성에 맞춰 설계할게요."


NEW_PROJECT_WORDS = ("새 프로젝트", "처음부터", "새로 만들", "다른 사이트")
# 시안 뒤 고치기는 사이트에 바로 보이는 칸만 받는다(구성·기능 변경은 새 시안이 필요해 채팅 흐름 밖).
_EDITABLE = ("shop_name", "phone", "hours", "location", "price", "offerings", "detail", "target", "contact_method", "booking_url", "staff")


def _edit_after_design(session: dict, text: str, by, is_owner: bool) -> Optional[str]:
    """시안·공개 뒤 가게 정보 고치기. 반영했으면 답을, 고칠 내용이 없으면 None."""
    card = session["prd"]
    ups = [u for u in prd_engine.extract(text, None) if u["slot"] in _EDITABLE]
    for u in ups:
        # 한 칸 값은 새 말로 바꾼다(여러 값 칸은 apply_updates가 덧붙인다).
        if not prd_engine.S.SLOTS[u["slot"]].multi:
            card["slots"].pop(u["slot"], None)
    applied = prd_engine.apply_updates(card, ups, text, by, is_owner) if ups else []
    if not applied:
        return None
    ind = prd_engine.industry_of(card)
    labels = ", ".join(dict.fromkeys(prd_engine.S.label_for(ind, k) for k in applied))
    if card.get("published"):
        from app.services.publish_check import PublishBlockedError
        try:
            design.publish_choice(session["requirement_id"], card, card["published"])
        except PublishBlockedError as e:
            return (f"반영했어요({labels}). 그런데 공개 전에 걸렀어요: " + "; ".join(e.reasons) + ". "
                    "공개 사이트는 그대로 뒀어요.")
        return f"반영했어요({labels}). 사이트에도 바로 바꿨어요: {session.get('deploy_url')}"
    return f"반영했어요({labels}). 공개할 때 이 내용으로 열게요."


_KAKAO_CHANNEL = re.compile(
    r"(?:https?://)?((?:pf\.kakao\.com/(?:_[A-Za-z0-9]+|[A-Za-z0-9._-]+)(?:/chat)?)|"
    r"(?:open\.kakao\.com/[A-Za-z0-9]+)|(?:pf\.kakao\.com/[A-Za-z0-9._-]+))"
)
# 채널 ID만 붙여넣은 경우 ("_abc123", "@내가게"): pf 주소로 바꿔준다.
_KAKAO_ID_ONLY = re.compile(r"^[@_]?([A-Za-z0-9._-]{4,40})$")
# D48: 사진은 안내 글이 아니라 선택지 질문으로 한 번만 묻는다. 질문 예산을 쓰지 않고,
# 승인 게이트도 아니다. 식당·카페·펜션은 가게 이름 직후(D36), 나머지는 요약 직전.
# "지금"은 대화를 멈추지 않고 다음 질문으로, "나중에"는 시안 때 한 번만 다시 알림, "없어요"는 다시 묻지 않음.
PHOTO_FIRST_INDUSTRIES = ("restaurant", "cafe", "pension")
PHOTO_CHOICE_TEXT = ("가게 사진이 있으면 사이트가 확 달라져요. 아래 '사진' 버튼으로 올려 주세요. "
                     "휴대폰으로 지금 찍어도 돼요.\n"
                     "1) 지금 올릴게요  2) 나중에 올릴게요  3) 사진이 없어요(예시 그림으로)\n\n"
                     "(사진 질문이에요 · 답하지 않아도 넘어가요)")
_PHOTO_WHAT = {"restaurant": "대표 메뉴", "cafe": "대표 메뉴", "pension": "객실"}


def photo_choice_text(card: dict) -> str:
    """D48 사진 선택지 본문. 식당·카페·펜션은 무엇을 찍을지 한 줄 덧붙인다."""
    what = _PHOTO_WHAT.get(prd_engine.industry_of(card).key)
    head = f"가게 사진이 있으면 사이트가 확 달라져요. 아래 '사진' 버튼으로 가게 대표 사진 1장과 {what} 사진을 올려 주세요. " if what else None
    if head:
        return (head + "휴대폰으로 지금 찍어도 돼요.\n"
                "1) 지금 올릴게요  2) 나중에 올릴게요  3) 사진이 없어요(예시 그림으로)\n\n"
                "(사진 질문이에요 · 답하지 않아도 넘어가요)")
    return PHOTO_CHOICE_TEXT


def _photo_choice_available(card: dict) -> bool:
    """사진 선택지를 물을 수 있는지: 한 번만, 올렸거나 '없어요'면 다시 묻지 않는다."""
    return not card.get("photos") and not card.get("photo_asked") and card.get("photo_choice") != "none"


def _early_photo_ask(card: dict, room) -> str:
    if room is None or not _photo_choice_available(card):
        return ""
    ind = prd_engine.industry_of(card).key
    shop = (card.get("slots", {}).get("shop_name") or {}).get("status")
    if ind not in PHOTO_FIRST_INDUSTRIES or shop != prd_schema.FILLED:
        return ""
    card["photo_asked"] = True
    return photo_choice_text(card) + "\n\n"


def photo_answer(text: str) -> Optional[str]:
    """사진 선택지 답이면 'now'·'later'·'none', 아니면 None.

    번호만('2')은 엔진 선택지 답과 겹치므로 받지 않는다. '올릴게요'·'사진이 없어요'처럼
    사진 말이 분명할 때만 가로챈다(짧은 답에만, 20자 이내).
    """
    t = (text or "").strip()
    if not t or len(t) > 20:
        return None
    n = prd_engine._norm(t)
    if "사진이없" in n or "사진없" in n or "예시그림" in n or ("사진" in t and "없" in t):
        return "none"
    if "올릴" not in t:
        return None
    if "지금" in t or "바로" in t:
        return "now"
    if "나중" in n:
        return "later"
    return None


def _photo_ack(choice: str) -> str:
    if choice == "now":
        return "사진을 기다릴게요. 아래 '사진' 버튼으로 올려 주세요. 먼저 다음 질문을 드릴게요.\n\n"
    if choice == "later":
        return "나중에 올려 주세요. 시안 때 한 번만 다시 알려 드릴게요.\n\n"
    return "예시 그림으로 먼저 만들게요. 나중에 사진을 올리시면 바로 바꿔 드려요.\n\n"


def _photo_later_reminder(card: Optional[dict]) -> str:
    """D48: '나중에 올릴게요'면 시안 때 한 번만 다시 알린다. '없어요'면 조용히."""
    if not card or card.get("photos") or card.get("photo_reminded"):
        return ""
    if card.get("photo_choice") != "later":
        return ("지금은 사진 대신 예시 그림이 들어가 있어요. 아래 '사진' 버튼으로 가게 사진을 올리면 "
                "시안에 바로 넣어 드려요.\n" if card.get("photo_choice") != "none" else "")
    card["photo_reminded"] = True
    return ("사진을 '나중에 올릴게요'라고 하셨어요. 아래 '사진' 버튼으로 지금 올려 주시면 "
            "시안에 바로 넣어 드려요.\n")


PHOTO_ASK = PHOTO_CHOICE_TEXT + "\n\n"


def _apply_correction(session: dict, text: str, by, is_owner: bool) -> Optional[str]:
    """요약 뒤 고치는 말. 바뀐 칸 이름들을, 고칠 내용이 없으면 None."""
    card = session.get("prd")
    if not card or not text:
        return None
    ups = [u for u in prd_engine.extract(text, None) if u["slot"] != "exclude"]
    for u in ups:
        if not prd_engine.S.SLOTS[u["slot"]].multi:
            card["slots"].pop(u["slot"], None)  # 한 칸 값은 새 말로 바꾼다
        elif prd_engine.S.SLOTS[u["slot"]].multi and "고쳐" in text:
            card["slots"].pop(u["slot"], None)  # "고쳐 주세요"면 여러 값 칸도 새로 쓴다
    applied = prd_engine.apply_updates(card, ups, text, by, is_owner) if ups else []
    if not applied:
        return None
    ind = prd_engine.industry_of(card)
    return ", ".join(dict.fromkeys(prd_engine.S.label_for(ind, k) for k in applied))


VARIANT_NAMES = {"v1": "기본형", "v2": "사진 강조형", "v3": "간결형"}
# 공개 뜻으로 보는 말: 정확일치가 아니라 포함으로 본다 ("2안이 마음에 들어요, 공개할게요"도 잡는다).
PUBLISH_WORDS = ("공개", "그대로공개", "사이트열어", "사이트오픈", "열어줘", "오픈해줘")
PUBLISH_NEGATION = ("공개안", "공개하지", "공개말고")


def _restyle(session: dict, text: str) -> str:
    card = session["prd"]
    current = card.get("concept") or design_concept.rule_concept(card)
    new, said = design_concept.adjust(current, text)
    if not said:
        return "어떤 느낌으로 바꿀까요? 예: '더 고급스럽게', '더 따뜻한 색으로', '사진 먼저 보여 줘'"
    card["concept"] = new
    design_log.restyled(session["requirement_id"], card, current, new)  # D45
    design.render_variants(session["requirement_id"], card)
    if card.get("published"):
        from app.services.publish_check import PublishBlockedError
        try:
            design.publish_choice(session["requirement_id"], card, card["published"])
        except PublishBlockedError as e:
            return (f"{said}\n{design_concept.summary_line(new)}\n\n다시 그린 컨셉 보드와 시안: {session['design_url']}"
                    "\n공개 전에 걸려서 공개 사이트는 그대로 뒀어요: " + "; ".join(e.reasons))
    return (f"{said}\n{design_concept.summary_line(new)}\n\n다시 그린 컨셉 보드와 시안: {session['design_url']}"
            + ("\n공개 사이트에도 바로 반영했어요." if card.get("published") else ""))


def _publish(session: dict, base_url: str, force: bool) -> str:
    """고른 시안을 공개한다. [입력 필요] 자리가 남았으면 먼저 알리고 한 번 더 확인받는다(⑱ 사람 최종 확인)."""
    card = session["prd"]
    choice = card.get("design_choice")
    if not choice:
        return "먼저 1안·2안·3안 중 하나를 골라 주세요. 예: '2안으로 할게요'"
    ind = prd_engine.industry_of(card)
    missing = [prd_engine.S.label_for(ind, k) for k, v in card["slots"].items() if v.get("status") == prd_engine.S.PLACEHOLDER]
    if missing and not force:
        return ("공개 전에 확인해 주세요. 아직 비어 있는 곳이 있어요: " + ", ".join(missing) + "\n"
                "사이트에는 빈 곳을 빼고 보여 드려요. 빼려면 '○○은 빼주세요', "
                "그대로 열려면 '그대로 공개'라고 보내 주세요.")
    from app.services.publish_check import PublishBlockedError
    try:
        design.publish_choice(session["requirement_id"], card, choice)
    except PublishBlockedError as e:
        # S-5: 외부 스크립트·폼 등이 들어 있으면 게시하지 않고 사장님께 알린다.
        return ("공개 전에 걸렀어요: " + "; ".join(e.reasons) + ". "
                "시안은 그대로 볼 수 있어요. 어디서 들어온 건지 확인해 드릴게요.")
    url = deploy.site_url(session["requirement_id"], base_url)
    session["deploy_url"] = url
    card["published"] = choice
    design_log.published(session["requirement_id"], card, choice)  # D45
    return (f"사이트를 열었어요: {url}\n"
            f"{choice[1]}안({VARIANT_NAMES[choice]}) 그대로예요. 문의 양식으로 온 글은 이 채팅방에 알려 드릴게요.")


_CHOICE = re.compile(r"(?<!\d)([1-3])\s*(?:안|번)")
_CHOICE_WORD = {"첫번째": "v1", "첫째": "v1", "두번째": "v2", "둘째": "v2", "세번째": "v3", "셋째": "v3",
                "1번으로": "v1", "2번으로": "v2", "3번으로": "v3"}


def _design_choice(text: str) -> Optional[str]:
    """ "2안으로 할게요", "3번" → v2, v3. 50자까지 자연문에서도 본다."""
    t = (text or "").strip()
    if not t:
        return None
    # "첫 번째가 좋아요" 같은 말도 잡는다.
    n = prd_engine._norm(t)
    for w, v in _CHOICE_WORD.items():
        if prd_engine._norm(w) in n:
            return v
    m = _CHOICE.search(t) if len(t) <= 50 else None
    if m:
        return f"v{m.group(1)}"
    # "기본형으로", "사진 강조형으로", "간결형으로"
    if "기본형" in t:
        return "v1"
    if "사진강조" in n or "사진강조형" in n:
        return "v2"
    if "간결형" in t:
        return "v3"
    return None


def _is_publish_request(text: str) -> bool:
    """공개 요청인지. 부정(공개 말고)은 제외한다."""
    n = prd_engine._norm(text or "")
    if not n or any(w in n for w in PUBLISH_NEGATION):
        return False
    return any(w in n for w in PUBLISH_WORDS)


def _is_force_publish(text: str) -> bool:
    """빈칸이 있어도 열라는 뜻인지."""
    n = prd_engine._norm(text or "")
    return "그대로공개" in n or "그대로열어" in n or "빈칸있어도" in n


def process_turn(session_id: str, session: dict, user_text: str, base_url: str, room: Optional[dict] = None,
                 by: Optional[str] = None, is_owner: bool = True) -> str:
    state = session["state"]
    engine_trace = None

    channel = _KAKAO_CHANNEL.search(user_text or "")
    if channel and session.get("prd") is not None:
        # "채널이 있나요?"에 주소까지 받는다(워크플로 검토 9/26). 시안·공개본의 채널 버튼에 들어간다.
        url = channel.group(1)
        url = url if url.startswith("http") else "https://" + url
        # /chat 접미사는 버튼 링크에 불필요하므로 뗀다 (기존 테스트와 동일).
        if url.endswith("/chat"):
            url = url[: -len("/chat")]
        session["prd"]["kakao_channel_url"] = url
    from app.services.video_links import extract_video_links
    videos = extract_video_links(user_text or "")
    if videos and session.get("prd") is not None:
        # 방안 5: 유튜브·인스타·네이버TV 링크를 붙이면 소개 뒤 영상 카드로 넣는다(시안이 있으면 뒤에서 다시 만든다).
        card_v = session["prd"]
        before = len(card_v.get("videos") or [])
        card_v["videos"] = list(dict.fromkeys((card_v.get("videos") or []) + videos))[:3]
        if len(card_v["videos"]) >= 3 and before + len(videos) > 3:
            # 3개 제한을 넘기면 조용히 자르지 않고 알린다.
            card_v["video_note"] = "영상은 3개까지만 담을 수 있어요. 먼저 온 3개를 넣었어요."
        if session.get("design_url") and room is not None:
            from app.services import photos
            rid, req = room["room_id"], session["requirement_id"]
            store.after_commit(lambda: photos._refresh_designs_async(rid, req))
    has_design = bool(session.get("design_url") and session.get("prd"))
    choice = _design_choice(user_text) if has_design else None
    publish_cmd = has_design and state in ("GENERATING", "DONE") and _is_publish_request(user_text)
    if choice and state in ("GENERATING", "DONE") and publish_cmd:
        # "2안이 마음에 들어요, 공개할게요"처럼 고르기+공개를 한 번에 말하면 두 단계를 한 번에 끝낸다.
        session["prd"]["design_choice"] = choice
        design_log.chosen(session["requirement_id"], session["prd"], choice)  # D45
        name = VARIANT_NAMES[choice]
        pub = _publish(session, base_url, force=_is_force_publish(user_text))
        if pub.startswith("사이트를 열었어요"):
            reply = f"{choice[1]}안({name})으로 정했어요.\n{pub}"
        else:
            # 빈칸 확인이 남았으면 선택은 저장하고 확인 메시지를 보여준다.
            reply = f"{choice[1]}안({name})으로 정했어요.\n{pub}"
    elif choice and state in ("GENERATING", "DONE"):
        # 시안 3안 고르기 (C7): 카드에 남긴다. 제작 상태는 그대로 둔다.
        session["prd"]["design_choice"] = choice
        design_log.chosen(session["requirement_id"], session["prd"], choice)  # D45
        name = VARIANT_NAMES[choice]
        reply = (f"{choice[1]}안({name})으로 정했어요. {session['design_url']}/{choice}/ 에서 크게 볼 수 있어요.\n"
                 "이대로 사이트를 열려면 '공개'라고 보내 주세요. 바꾸고 싶으면 다른 번호를 보내 주세요.")
    elif publish_cmd:
        reply = _publish(session, base_url, force=_is_force_publish(user_text))
    elif has_design and state in ("GENERATING", "DONE") and design_concept.is_style_request(user_text):
        # 말로 디자인 고치기: 컨셉을 바꿔 시안 3안(공개했으면 공개본도)을 다시 그린다
        reply = _restyle(session, user_text)
    elif state == "GENERATING" and session.get("codegen") is None and user_text and session.get("prd"):
        # 제작 중에도 가게 정보를 고칠 수 있다(시안 공개 전후 모두).
        reply = (_edit_after_design(session, user_text, by, is_owner)
                 or f"시안은 여기서 보고 고를 수 있어요: {session.get('design_url', '(준비 중)')}\n"
                     "사이트 파일도 뒤에서 만들고 있어요(1~2분). 끝나면 알려 드릴게요. 기다리지 않으셔도 돼요.")
    elif state == "GENERATING":
        cg = session.get("codegen")
        if cg is None:
            reply = (f"시안은 여기서 보고 고를 수 있어요: {session.get('design_url', '(준비 중)')}\n"
                     "사이트 파일도 뒤에서 만들고 있어요(1~2분). 끝나면 알려 드릴게요. 기다리지 않으셔도 돼요.")
        elif cg["status"] == "done":
            deploy_url = deploy.site_url(session["requirement_id"], base_url)
            session["state"] = "DONE"
            session["deploy_url"] = deploy_url
            published = (session.get("prd") or {}).get("published")
            if published:
                reply = f"사이트 파일 만들기도 끝났어요. 열린 사이트({deploy_url})는 고르신 {published[1]}안 그대로예요."
            elif session.get("prd"):
                # 공개 전에는 코드생성 결과 주소를 보이지 않는다(고른 시안과 다른 화면이라 헷갈림, 9/26 점검)
                reply = ("사이트 파일 만들기도 끝났어요. 시안에서 번호를 고르고 '공개'라고 보내 주시면 "
                         "그 시안으로 사이트를 열어 드려요.")
            else:
                reply = f"사이트 파일 만들기가 끝났어요: {deploy_url}"
            # 완료를 알리는 턴에 사장님이 고칠 말을 보냈으면 그것도 반영한다(말이 묻히지 않게).
            if user_text and session.get("prd"):
                edit = _edit_after_design(session, user_text, by, is_owner)
                if edit:
                    reply += "\n\n" + edit
        elif cg["status"] == "unavailable":
            # docker/키가 없어 생성을 못 돌린 경우 — 배포할 산출물도 없다.
            session["state"] = "DONE"
            reply = (
                f"시안은 여기서 볼 수 있어요: {session.get('design_url', '(없음)')}\n"
                "사이트 파일은 이번에는 만들지 못했어요. 시안에서 번호를 고르고 '공개'라고 보내 주세요."
            )
        else:  # timeout / error / no_files_created
            session["state"] = "QUOTED"
            detail = ""
            if isinstance(cg, dict):
                if cg.get("status") == "timeout":
                    detail = " (시간이 오래 걸려 멈췄어요)"
                elif cg.get("status") == "error":
                    detail = " (만드는 중에 오류가 났어요)"
                elif cg.get("status") == "no_files_created":
                    detail = " (파일이 만들어지지 않았어요)"
            reply = (f"사이트 파일을 만들다가 실패했어요{detail}. 시안은 그대로 볼 수 있어요: {session.get('design_url', '(없음)')}\n"
                     "다시 '진행'이라고 보내 주시면 파일 만들기를 다시 시작할게요.")

    elif not user_text:
        # B-1: 빈 메시지가 승인 대기·견적·완료 상태를 날리지 않게 상태별로 유지한다.
        # 방 폴링·입장 확인용 빈 호출은 대화를 진전시키지 않는다.
        if state == "GREETING":
            reply = "안녕하세요! 어떤 프로젝트를 원하시나요? (예: 예산, 원하는 기능을 알려주세요)"
            session["state"] = "GATHERING"
        elif state == "GATHERING":
            card = session.get("prd") or prd_engine.new_card()
            result = prd_engine.turn(card, "", by=by, is_owner=is_owner)
            engine_trace = result.get("trace")
            session["prd"] = card
            if result["done"]:
                _set_room_status(room, "RAG_SEARCHING", persist=True)
                reply = _gate_or_summary(session, card, room, engine_trace)
            else:
                reply = prd_engine.format_question(card, result["question"])
                session["state"] = "GATHERING"
            _set_room_status(room, "IDLE")
        elif state == "AWAIT_APPROVAL":
            reply = "승인 또는 거절로 답해주세요."
        elif state == "QUOTED":
            reply = "이 견적으로 진행할까요? (진행/취소)"
        else:  # DONE: 빈 메시지로 재시작하지 않고 완료 상태를 유지한다
            reply = "이미 완료된 요청입니다. 새 프로젝트를 원하시면 다시 말씀해 주세요."

    elif state in ("GREETING", "GATHERING"):
        # 요구사항 엔진 (REQUIREMENTS_ENGINE_PLAN.md): 빠진 정보를 선택지와 함께 하나씩 묻고, 다 모이면 요약한다.
        _set_room_status(room, "THINKING", persist=True)
        card = session.get("prd") or prd_engine.new_card()
        pending_photo = (card.get("photo_asked") and not card.get("photos")
                         and card.get("photo_choice") is None and card.get("pending"))
        choice = photo_answer(user_text) if pending_photo else None
        if choice:
            # D48: 사진 답은 요구사항 엔진으로 보내지 않는다 ("나중에"가 칸을 비우지 않게).
            # 질문 예산도 쓰지 않고, 하던 질문을 그대로 다시 보인다. 답은 D45 기록에 남긴다.
            card["photo_choice"] = choice
            log.info("사진 선택지 답: %s", choice)
            funnel.record("photo_answered", session_id=session_id, props={"choice": choice})
            session["prd"] = card
            reply = _photo_ack(choice) + prd_engine.format_question(card, card["pending"])
            session["state"] = "GATHERING"
            _set_room_status(room, "IDLE")
        else:
            result = prd_engine.turn(card, user_text, by=by, is_owner=is_owner)
            engine_trace = result.get("trace")
            session["prd"] = card
            if result.get("blocked"):
                # 입구 게이트 §2 ④: 금지 요청은 이유를 밝혀 거절하고, 하던 질문이 있으면 이어서 묻는다.
                reply = f"죄송하지만 이 요청은 만들어 드릴 수 없어요. ({result['blocked']})"
                if result.get("question"):
                    reply += "\n\n" + prd_engine.format_question(card, result["question"])
                session["state"] = "GATHERING"
            elif result["done"]:
                _set_room_status(room, "RAG_SEARCHING", persist=True)
                reply = _gate_or_summary(session, card, room, engine_trace)
            else:
                nudge = "사이트 이야기로 돌아가 볼까요?\n" if result.get("nudge") else ""
                if (engine_trace or {}).get("repeat"):
                    nudge = "다시 말씀드릴게요.\n"  # VOICE FR-6: "다시요"·"뭐라고요"
                reply = (nudge + prd_engine.ack_text(card, result["applied"]) + _early_photo_ask(card, room)
                         + prd_engine.format_question(card, result["question"]))
                session["state"] = "GATHERING"
            _set_room_status(room, "IDLE")

    elif state == "AWAIT_APPROVAL":
        if intent(user_text, "reject"):
            session["state"] = "GATHERING"
            reply = "알겠습니다. 무엇을 고칠까요? 바꿀 내용을 말씀해 주세요."
        elif intent(user_text, "approve"):
            _set_room_status(room, "QUOTING", persist=True)
            # D25: 카드가 있으면 규칙 참고 견적 한 줄(AI가 금액을 만들지 않음). 예전 1:1 흐름만 AI 견적.
            card = session.get("prd")
            q = quote.rule_quote(card) if card and card.get("slots") else quote.build_quote(session.get("last_request", ""))
            session["quote"] = q
            session["state"] = "QUOTED"
            if q.get("rule"):
                reply = f"{quote.format_quote_text(q)}\n\n이대로 시안을 만들까요? (진행/취소)"
            else:
                reply = f"승인 감사합니다. 견적안입니다:\n\n{quote.format_quote_text(q)}\n\n이 견적으로 진행할까요? (진행/취소)"
            _set_room_status(room, "IDLE")
        else:
            # T3 분석 G1·G5: 요약을 보고 "반 구성은 ○○예요, 고쳐 주세요"라고 하면 고쳐서 요약을 다시 보인다.
            fixed = _apply_correction(session, user_text, by, is_owner)
            if fixed:
                reply = f"고쳤어요: {fixed}\n" + _gate_or_summary(session, session["prd"], room, None, again=True)
            else:
                reply = "승인 또는 거절로 답해주세요. 고칠 것이 있으면 '가게 이름은 ○○예요'처럼 말씀해 주세요."

    elif state == "QUOTED":
        # QUOTED에서는 "취소·처음부터"만 리셋한다. 고치는 말은 요구사항으로 돌려준다.
        _CANCEL_N = prd_engine._norm(user_text or "")
        _is_cancel = any(w in _CANCEL_N for w in ("취소", "처음부터", "리셋", "그만"))
        if _is_cancel and not intent(user_text, "proceed"):
            session["state"] = "GATHERING"
            reply = "알겠어요. 무엇을 고칠까요? 바꿀 내용을 말씀해 주세요. (예: '전화번호는 010-…이에요')"
        elif intent(user_text, "proceed"):
            # 시안을 코드생성보다 먼저 만들어 고객이 먼저 확인하게 한다 (시안 → 최종 순서 보장).
            amount, basis = quote.recommended_option(session.get("quote") or {"ok": False, "raw": ""})
            card = session.get("prd")
            if card and card.get("slots") and not card.get("copy"):
                # 방안 3: 빈 소개·첫 화면 문구를 AI 초안으로(사실은 지어내지 않음). 실패하면 초안 없이 만든다.
                from app.services import copywriter
                card["copy"] = copywriter.generate(card)
            if card and card.get("slots") and not card.get("concept"):
                # 디자인 컨셉 잡기: NIM이 색·글꼴·구성을 정하고(목록 안에서만), 그 컨셉으로 3안을 그린다
                card["concept"] = design_concept.make(card)
                design_log.unmet(session["requirement_id"], card)  # D44: 부품으로 못 담은 요구를 센다
            d = design.render_design(session["requirement_id"], "web", [session.get("last_request", "")], amount, basis,
                                     card=card)
            session["design_url"] = d["design_url"]
            session["design_preview_url"] = d["preview_url"]
            session["design_url_unsent"] = True

            session["codegen"] = None
            session["state"] = "GENERATING"
            _set_room_status(room, "GENERATING")
            codegen.start(session_id, session["requirement_id"], session.get("last_request", ""))
            concept_note = (f"디자인 컨셉을 잡았어요.\n{design_concept.summary_line(card['concept'])}\n\n"
                            if card and card.get("concept") else "")
            reply = (
                concept_note +
                f"컨셉 보드와 시안 3안: {d['design_url']}\n"
                + ("1안 기본형 · 2안 사진 강조형 · 3안 간결형 중 마음에 드는 번호를 보내 주세요. 예: '2안으로 할게요'\n\n"
                   if len(d.get("design_variants", [])) >= 3 else "\n") +
                ("'더 고급스럽게'처럼 말로 디자인을 고칠 수도 있어요.\n" if card and card.get("concept") else "") +
                ("소개·첫 화면 문구는 AI 초안이에요. 방장은 '직접 고치기'에서 바꿀 수 있어요.\n"
                   if (card or {}).get("copy") else "") +
                (_photo_later_reminder(card) +
                 "뒤에서 사이트 파일도 함께 만들고 있어요(선택). "
                 "다 되면 알려 드릴게요. 잠시 후 아무 말이나 보내 주시면 진행 상황을 알려 드려요.")
            )
        else:
            # 진행이 아니면 고치는 말로 본다. 요구사항 수정이면 반영하고 견적을 다시 보여준다.
            fixed = _apply_correction(session, user_text, by, is_owner) if session.get("prd") else None
            if fixed:
                session["state"] = "GATHERING"
                reply = f"고쳤어요: {fixed}\n무엇을 더 고칠까요? 다 됐으면 '시안 먼저'라고 보내 주세요."
            else:
                reply = "이대로 시안을 만들까요? '진행'이라고 보내 주시거나, 고칠 내용을 말씀해 주세요. (처음부터 다시 하려면 '취소'라고 보내 주세요)"

    else:  # DONE
        if any(w in user_text for w in NEW_PROJECT_WORDS) or not session.get("prd"):
            reply = "새 프로젝트를 시작할게요. 어떤 사이트를 만들까요?"
            session["state"] = "GATHERING"
            session["prd"] = None
        else:
            # 완료 뒤 아무 말에나 카드를 지우던 문제: 이제는 고칠 내용으로 받는다. 새로 시작은 말로 분명히 할 때만.
            reply = _edit_after_design(session, user_text, by, is_owner) or (
                "무엇을 바꿀까요? 예: '전화번호는 010-1234-5678이에요'. 새로 만들려면 '새 프로젝트'라고 보내 주세요.")

    _record_transition(session_id, state, session["state"])
    # 대화 턴 기록 (AI 성능 평가용, 90일). 폴링처럼 사람이 말하지 않은 턴은 남기지 않는다.
    if user_text:
        store.record_turn(session_id, room["room_id"] if room else None, by, user_text, reply,
                          state, session["state"], engine_trace)

    if room is not None:
        if session["state"] == "DONE":
            room["ai_status"] = "DONE"
        elif state == "GENERATING" and session["state"] != "GENERATING":
            room["ai_status"] = "IDLE"  # 코드생성 실패로 QUOTED에 복귀

    return reply
