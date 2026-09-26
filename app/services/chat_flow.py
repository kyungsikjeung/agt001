"""대화 상태머신. 1:1 `/chat`과 공유방 `/room/{id}/chat`이 같은 본체를 공유한다.

상태: GREETING → GATHERING → AWAIT_APPROVAL → QUOTED → GENERATING → DONE
room을 넘기면 주요 전이마다 room["ai_status"]를 갱신해 다른 참여자가 AI 진행 상황을 보게 한다.
"""
import logging
import re
import uuid
from typing import Optional

from app import store
from app.services import codegen, deploy, design, funnel, prd_engine, quote, rag

log = logging.getLogger(__name__)


# 짧은 대답의 뜻(B-6·BACKLOG S-1): "승인할게요", "진행해 주세요", "좋아요!"도 알아듣는다.
# 정확히 일치하는 말 + 앞머리가 같은 짧은 말(12자 이하). 거절·부정은 승인보다 먼저 본다.
_INTENT_EXACT = {
    "approve": ("승인", "네", "예", "yes", "approve", "좋아요", "좋습니다", "찬성", "ok", "오케이", "넵", "응"),
    "reject": ("거절", "아니오", "아니요", "no", "reject", "반대", "싫어요", "별로예요"),
    "proceed": ("진행", "네", "예", "yes", "proceed", "좋아요", "시작", "만들어주세요", "넵", "응"),
}
_INTENT_PREFIX = {"approve": ("승인", "찬성", "좋아"), "reject": ("거절", "반대"), "proceed": ("진행", "만들어", "시작해")}
_NEGATION = ("안할", "안해", "말고", "취소", "그만")


def intent(text: str, kind: str) -> bool:
    """kind('approve'·'reject'·'proceed') 뜻의 짧은 대답인지."""
    n = prd_engine._norm(text)
    if not n or len(n) > 12:
        return False
    if kind != "reject" and any(w in n for w in _NEGATION):
        return False
    return n in {prd_engine._norm(w) for w in _INTENT_EXACT[kind]} or n.startswith(_INTENT_PREFIX[kind])


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


def _rag_note(spec: str) -> str:
    """비슷한 사례(기능 사례집·업종 프로필)를 사람 말로. 없으면 없다고 말한다 (해커톤 요구 4)."""
    names = rag.similar(spec)
    log.info("비슷한 사례: %s", names)
    if names:
        return "비슷한 사례를 참고해 설계할게요: " + ", ".join(names)
    return "말씀하신 내용과 업종 기본 구성에 맞춰 설계할게요."


NEW_PROJECT_WORDS = ("새 프로젝트", "처음부터", "새로 만들", "다른 사이트")
# 시안 뒤 고치기는 사이트에 바로 보이는 칸만 받는다(구성·기능 변경은 새 시안이 필요해 채팅 흐름 밖).
_EDITABLE = ("shop_name", "phone", "hours", "location", "price", "offerings", "detail", "target", "contact_method")


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
        design.publish_choice(session["requirement_id"], card, card["published"])
        return f"반영했어요({labels}). 사이트에도 바로 바꿨어요: {session.get('deploy_url')}"
    return f"반영했어요({labels}). 공개할 때 이 내용으로 열게요."


_KAKAO_CHANNEL = re.compile(r"(?:https?://)?(pf\.kakao\.com/_[A-Za-z0-9]+)(?:/chat)?")
PHOTO_ASK = "가게 사진이 있으면 📷 버튼으로 올려 주세요. 없으면 업종에 맞는 예시 그림으로 만들고, 나중에 올리셔도 바로 바뀌어요.\n\n"


VARIANT_NAMES = {"v1": "기본형", "v2": "사진 강조형", "v3": "간결형"}
PUBLISH_WORDS = ("공개", "공개해줘", "공개해 주세요", "공개할게요", "그대로 공개")


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
                "사이트에는 [입력 필요]로 보여요. 그래도 먼저 열려면 '그대로 공개'라고 보내 주세요.")
    design.publish_choice(session["requirement_id"], card, choice)
    url = deploy.site_url(session["requirement_id"], base_url)
    session["deploy_url"] = url
    card["published"] = choice
    return (f"사이트를 열었어요: {url}\n"
            f"{choice[1]}안({VARIANT_NAMES[choice]}) 그대로예요. 문의 양식으로 온 글은 이 채팅방에 알려 드릴게요.")


_CHOICE = re.compile(r"(?<!\d)([1-3])\s*(?:안|번)")


def _design_choice(text: str) -> Optional[str]:
    """ "2안으로 할게요", "3번" → v2, v3. 짧은 메시지에서만 본다(긴 문장 속 숫자를 오인하지 않게)."""
    t = (text or "").strip()
    m = _CHOICE.search(t) if len(t) <= 20 else None
    return f"v{m.group(1)}" if m else None


def process_turn(session_id: str, session: dict, user_text: str, base_url: str, room: Optional[dict] = None,
                 by: Optional[str] = None, is_owner: bool = True) -> str:
    state = session["state"]
    engine_trace = None

    channel = _KAKAO_CHANNEL.search(user_text or "")
    if channel and session.get("prd") is not None:
        # "채널이 있나요?"에 주소까지 받는다(워크플로 검토 9/26). 시안·공개본의 채널 버튼에 들어간다.
        session["prd"]["kakao_channel_url"] = "https://" + channel.group(1)
    has_design = bool(session.get("design_url") and session.get("prd"))
    choice = _design_choice(user_text) if has_design else None
    publish_cmd = has_design and state in ("GENERATING", "DONE") and user_text.strip() in PUBLISH_WORDS
    if choice and state in ("GENERATING", "DONE"):
        # 시안 3안 고르기 (C7): 카드에 남긴다. 제작 상태는 그대로 둔다.
        session["prd"]["design_choice"] = choice
        name = VARIANT_NAMES[choice]
        reply = (f"{choice[1]}안({name})으로 정했어요. {session['design_url']}/{choice}/ 에서 크게 볼 수 있어요.\n"
                 "이대로 사이트를 열려면 '공개'라고 보내 주세요. 바꾸고 싶으면 다른 번호를 보내 주세요.")
    elif publish_cmd:
        reply = _publish(session, base_url, force=user_text.strip() == "그대로 공개")
    elif state == "GENERATING" and session.get("codegen") is None and user_text and session.get("prd"):
        # 제작 중에도 가게 정보를 고칠 수 있다(시안 공개 전후 모두).
        reply = _edit_after_design(session, user_text, by, is_owner) or "사이트 파일을 만들고 있어요. 잠시만 기다려 주세요."
    elif state == "GENERATING":
        cg = session.get("codegen")
        if cg is None:
            reply = "사이트 파일을 만들고 있어요. 잠시만 기다려 주세요."
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
            reply = "사이트 파일을 만들다가 실패했어요. 다시 '진행'이라고 보내 주세요."

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
                spec = prd_engine.spec_text(card)
                session["last_request"] = spec
                reply = (
                    f"정리했어요.\n{prd_engine.summary_text(card)}\n\n{_rag_note(spec)}\n\n"
                    "이 내용으로 참고 견적을 만들어 볼까요? (승인/거절로 답해주세요)"
                )
                session["state"] = "AWAIT_APPROVAL"
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
            # 리뷰어 에이전트: 요약 직전 한 번, 원문과 카드를 대조해 빠진 요구를 채운다.
            rv = prd_engine.review(card)
            if engine_trace is not None:
                engine_trace["review"] = {"ok": rv["ok"], "added": rv["added"], "conflicts": len(rv["conflicts"]), "ms": rv["ms"]}
            spec = prd_engine.spec_text(card)
            session["last_request"] = spec
            note = prd_engine.review_text(card)
            reply = (
                f"정리했어요.\n{prd_engine.summary_text(card)}\n\n" + (f"{note}\n\n" if note else "")
                + (PHOTO_ASK if room is not None and not card.get("photos") else "")
                + f"{_rag_note(spec)}\n\n이 내용으로 참고 견적을 만들어 볼까요? (승인/거절로 답해주세요)"
            )
            session["state"] = "AWAIT_APPROVAL"
        else:
            nudge = "사이트 이야기로 돌아가 볼까요?\n" if result.get("nudge") else ""
            reply = nudge + prd_engine.ack_text(card, result["applied"]) + prd_engine.format_question(card, result["question"])
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
            reply = "승인 또는 거절로 답해주세요."

    elif state == "QUOTED":
        if intent(user_text, "proceed"):
            # 시안을 코드생성보다 먼저 만들어 고객이 먼저 확인하게 한다 (시안 → 최종 순서 보장).
            amount, basis = quote.recommended_option(session.get("quote") or {"ok": False, "raw": ""})
            card = session.get("prd")
            if card and card.get("slots") and not card.get("copy"):
                # 방안 3: 빈 소개·첫 화면 문구를 AI 초안으로(사실은 지어내지 않음). 실패하면 초안 없이 만든다.
                from app.services import copywriter
                card["copy"] = copywriter.generate(card)
            d = design.render_design(session["requirement_id"], "web", [session.get("last_request", "")], amount, basis,
                                     card=card)
            session["design_url"] = d["design_url"]
            session["design_preview_url"] = d["preview_url"]
            session["design_url_unsent"] = True

            session["codegen"] = None
            session["state"] = "GENERATING"
            _set_room_status(room, "GENERATING")
            codegen.start(session_id, session["requirement_id"], session.get("last_request", ""))
            reply = (
                f"시안 3안이 준비됐어요: {d['design_url']}\n"
                + ("1안 기본형 · 2안 사진 강조형 · 3안 간결형 중 마음에 드는 번호를 보내 주세요. 예: '2안으로 할게요'\n\n"
                   if len(d.get("design_variants", [])) >= 3 else "\n") +
                ("소개·첫 화면 문구는 AI 초안이에요. 방장은 '직접 고치기'에서 바꿀 수 있어요.\n"
                   if (card or {}).get("copy") else "") +
                ("지금은 사진 대신 예시 그림이 들어가 있어요. 📷 버튼으로 가게 사진을 올리면 시안에 바로 넣어 드려요.\n"
                   if room is not None and card and not card.get("photos") else "") +
                "뒤에서 사이트 파일도 함께 만들고 있어요(선택). "
                "다 되면 알려 드릴게요. 잠시 후 아무 말이나 보내 주시면 진행 상황을 알려 드려요."
            )
        else:
            session["state"] = "GATHERING"
            reply = "알겠습니다. 처음부터 다시 요청해 주세요."

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
