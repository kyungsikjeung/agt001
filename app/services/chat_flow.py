"""대화 상태머신. 1:1 `/chat`과 공유방 `/room/{id}/chat`이 같은 본체를 공유한다.

상태: GREETING → GATHERING → AWAIT_APPROVAL → QUOTED → GENERATING → DONE
room을 넘기면 주요 전이마다 room["ai_status"]를 갱신해 다른 참여자가 AI 진행 상황을 보게 한다.
"""
import uuid
from typing import Optional

from app import store
from app.services import codegen, deploy, design, quote, rag

APPROVE_WORDS = ("승인", "네", "yes", "approve", "예")
REJECT_WORDS = ("거절", "아니오", "no", "reject")
PROCEED_WORDS = ("진행", "네", "yes", "proceed", "예")


def new_session() -> dict:
    return {"state": "GREETING", "requirement_id": str(uuid.uuid4())[:8]}


def _set_room_status(room: Optional[dict], status: str, persist: bool = False) -> None:
    if room is None:
        return
    room["ai_status"] = status
    if persist:
        # 긴 NIM 호출 전에 바로 커밋해 두어야 폴링하는 다른 참여자가 진행 상태를 볼 수 있다.
        store.set_room_ai_status(room["room_id"], status)


def process_turn(session_id: str, session: dict, user_text: str, base_url: str, room: Optional[dict] = None) -> str:
    state = session["state"]

    if state == "GENERATING":
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
        reply = "안녕하세요! 어떤 프로젝트를 원하시나요? (예: 예산, 원하는 기능을 알려주세요)"
        session["state"] = "GATHERING"

    elif state in ("GREETING", "GATHERING"):
        _set_room_status(room, "RAG_SEARCHING", persist=True)
        rag_result = rag.precheck(user_text)
        session["last_request"] = user_text
        reply = (
            f"{rag_result}\n\n"
            "요청하신 내용을 검토했습니다. 이 요구사항으로 견적을 진행할까요? (승인/거절로 답해주세요)"
        )
        session["state"] = "AWAIT_APPROVAL"
        _set_room_status(room, "IDLE")

    elif state == "AWAIT_APPROVAL":
        if user_text in APPROVE_WORDS:
            _set_room_status(room, "QUOTING", persist=True)
            q = quote.build_quote(session.get("last_request", ""))
            session["quote"] = q
            session["state"] = "QUOTED"
            reply = f"승인 감사합니다. 견적안입니다:\n\n{quote.format_quote_text(q)}\n\n이 견적으로 진행할까요? (진행/취소)"
            _set_room_status(room, "IDLE")
        elif user_text in REJECT_WORDS:
            session["state"] = "GATHERING"
            reply = "알겠습니다. 요구사항을 다시 말씀해 주세요."
        else:
            reply = "승인 또는 거절로 답해주세요."

    elif state == "QUOTED":
        if user_text in PROCEED_WORDS:
            # 시안을 코드생성보다 먼저 만들어 고객이 먼저 확인하게 한다 (시안 → 최종 순서 보장).
            amount, basis = quote.recommended_option(session.get("quote") or {"ok": False, "raw": ""})
            d = design.render_design(session["requirement_id"], "web", [session.get("last_request", "")], amount, basis)
            session["design_url"] = d["design_url"]
            session["design_preview_url"] = d["preview_url"]
            session["design_url_unsent"] = True

            session["codegen"] = None
            session["state"] = "GENERATING"
            _set_room_status(room, "GENERATING")
            codegen.start(session_id, session["requirement_id"], session.get("last_request", ""))
            reply = (
                f"진행합니다! UI 시안이 준비됐어요: {d['design_url']}\n\n"
                "팀C 코드생성 에이전트(Hermes)를 백그라운드로 시작했습니다. "
                "완료까지 최대 90초 정도 걸릴 수 있어요 — 잠시 후 아무 메시지나 보내시면 진행상황을 알려드립니다."
            )
        else:
            session["state"] = "GATHERING"
            reply = "알겠습니다. 처음부터 다시 요청해 주세요."

    else:  # DONE
        reply = "이미 완료된 요청입니다. 새 프로젝트를 원하시면 다시 말씀해 주세요."
        session["state"] = "GATHERING"

    if room is not None:
        if session["state"] == "DONE":
            room["ai_status"] = "DONE"
        elif state == "GENERATING" and session["state"] != "GENERATING":
            room["ai_status"] = "IDLE"  # 코드생성 실패로 QUOTED에 복귀

    return reply
