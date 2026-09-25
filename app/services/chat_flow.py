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

APPROVE_WORDS = ("승인", "네", "yes", "approve", "예")
REJECT_WORDS = ("거절", "아니오", "no", "reject")
log = logging.getLogger(__name__)

PROCEED_WORDS = ("진행", "네", "yes", "proceed", "예")


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
    elif state == "GENERATING":
        cg = session.get("codegen")
        if cg is None:
            reply = "코드 생성 중입니다... 잠시만 기다려주세요."
        elif cg["status"] == "done":
            deploy_url = deploy.site_url(session["requirement_id"], base_url)
            session["state"] = "DONE"
            session["deploy_url"] = deploy_url
            files_list = ", ".join(cg["files"][:5])
            reply = (
                "코드 생성이 완료됐습니다!\n\n"
                f"- 생성된 파일: {files_list}\n"
                f"- 배포 링크: {deploy_url}\n\n"
                "파이프라인 뼈대 관통 완료 (팀C 실구현)."
            )
        elif cg["status"] == "unavailable":
            # docker/키가 없어 생성을 못 돌린 경우 — 배포할 산출물도 없다.
            session["state"] = "DONE"
            reply = (
                f"{cg['note']}\n\n"
                f"- UI 시안: {session.get('design_url', '(없음)')}\n"
                "- 배포 링크: (코드생성을 건너뛰어 배포할 산출물이 없습니다)\n\n"
                "파이프라인 뼈대 관통 완료 (팀C 스텁 폴백)."
            )
        else:  # timeout / error / no_files_created
            session["state"] = "QUOTED"
            reply = f"코드 생성에 실패했습니다 ({cg['status']}). 다시 '진행'을 보내 재시도할 수 있습니다."

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
                + f"{_rag_note(spec)}\n\n이 내용으로 참고 견적을 만들어 볼까요? (승인/거절로 답해주세요)"
            )
            session["state"] = "AWAIT_APPROVAL"
        else:
            reply = prd_engine.ack_text(card, result["applied"]) + prd_engine.format_question(card, result["question"])
            session["state"] = "GATHERING"
        _set_room_status(room, "IDLE")

    elif state == "AWAIT_APPROVAL":
        if user_text in APPROVE_WORDS:
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
        elif user_text in REJECT_WORDS:
            session["state"] = "GATHERING"
            reply = "알겠습니다. 무엇을 고칠까요? 바꿀 내용을 말씀해 주세요."
        else:
            reply = "승인 또는 거절로 답해주세요."

    elif state == "QUOTED":
        if user_text in PROCEED_WORDS:
            # 시안을 코드생성보다 먼저 만들어 고객이 먼저 확인하게 한다 (시안 → 최종 순서 보장).
            amount, basis = quote.recommended_option(session.get("quote") or {"ok": False, "raw": ""})
            d = design.render_design(session["requirement_id"], "web", [session.get("last_request", "")], amount, basis,
                                     card=session.get("prd"))
            session["design_url"] = d["design_url"]
            session["design_preview_url"] = d["preview_url"]
            session["design_url_unsent"] = True

            session["codegen"] = None
            session["state"] = "GENERATING"
            _set_room_status(room, "GENERATING")
            codegen.start(session_id, session["requirement_id"], session.get("last_request", ""))
            reply = (
                f"진행합니다! UI 시안이 준비됐어요: {d['design_url']}\n"
                + ("1안 기본형 · 2안 사진 강조형 · 3안 간결형 중 마음에 드는 번호를 보내 주세요. 예: '2안으로 할게요'\n\n"
                   if len(d.get("design_variants", [])) >= 3 else "\n") +
                "팀C 코드생성 에이전트(Hermes)를 백그라운드로 시작했습니다. "
                "완료까지 최대 90초 정도 걸릴 수 있어요 — 잠시 후 아무 메시지나 보내시면 진행상황을 알려드립니다."
            )
        else:
            session["state"] = "GATHERING"
            reply = "알겠습니다. 처음부터 다시 요청해 주세요."

    else:  # DONE
        reply = "이미 완료된 요청입니다. 새 프로젝트를 원하시면 다시 말씀해 주세요."
        session["state"] = "GATHERING"
        session["prd"] = None

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
