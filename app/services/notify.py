"""사장님 알림 허브 (D32 ①, OWNER_NOTIFY_PLAN N3). 실패해도 채팅방 알림은 이미 남아 있다.

채널마다 따로 보낸다(하나가 실패해도 다른 것은 간다):
- 휴대폰 알림(웹 푸시, push.py): 무료 기본 채널. 사장님이 기기에서 켰을 때만.
- 카카오톡 "나에게 보내기"(kakao_talk.py): 사장님이 동의했을 때만.

방문자 요청(문의 전송)을 바깥 호출로 늦추지 않도록 뒤에서 보낸다.
"""
import logging
import threading

log = logging.getLogger(__name__)
SYNC = False  # 테스트에서 바로 확인하려면 True


def _kakao(room_id: str, text: str) -> bool:
    try:
        from app.services import kakao_talk
        return kakao_talk.send_to_room_owner(room_id, text)
    except Exception:
        log.exception("방장 카톡 알림 실패 room=%s", room_id)
        return False


def _push(room_id: str, text: str) -> int:
    try:
        from app.services import push
        return push.send_to_room_owner(room_id, text)
    except Exception:
        log.exception("방장 휴대폰 알림 실패 room=%s", room_id)
        return 0


def _send(room_id: str, text: str) -> None:
    _push(room_id, text)
    _kakao(room_id, text)


def owner(room_id: str, text: str) -> None:
    """방장에게 모든 켜진 채널로 알린다. text 첫 줄은 잠금 화면에 보이니 ':' 앞에 손님 정보를 넣지 않는다."""
    if SYNC:
        _send(room_id, text)
        return
    threading.Thread(target=_send, args=(room_id, text), daemon=True).start()


# 예전 이름. 호출하는 곳(문의·예약·주문·채팅·방 경고)과 테스트가 이 이름을 쓴다.
def owner_kakao(room_id: str, text: str) -> None:
    owner(room_id, text)
