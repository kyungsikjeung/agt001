"""사장님 알림 (D32 ①). 지금은 카카오톡 "나에게 보내기"만. 실패해도 채팅방 알림은 이미 남아 있다.

방문자 요청(문의 전송)을 카카오 호출로 늦추지 않도록 뒤에서 보낸다.
"""
import logging
import threading

log = logging.getLogger(__name__)
SYNC = False  # 테스트에서 바로 확인하려면 True


def _send(room_id: str, text: str) -> bool:
    try:
        from app.services import kakao_talk
        return kakao_talk.send_to_room_owner(room_id, text)
    except Exception:
        log.exception("방장 카톡 알림 실패 room=%s", room_id)
        return False


def owner_kakao(room_id: str, text: str) -> None:
    if SYNC:
        _send(room_id, text)
        return
    threading.Thread(target=_send, args=(room_id, text), daemon=True).start()
