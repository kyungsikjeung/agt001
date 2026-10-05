"""설정 점검 (UX_GAP_PLAN Q3): 빠진 설정을 조용히 넘기지 않고 알린다.

10/1~10/5 PUBLIC_BASE_URL이 없어 공개 사이트 채팅하기·주문 링크가 5일간 빠졌고, 10/3 주 모델이 서비스 종료됐는데
아무도 몰랐다. 서버가 뜰 때 한 번 알리고(announce), 관리자 화면에서 늘 보인다(problems).
설정·키 저장소만 읽는다. 바깥 호출 없음, 예외를 내지 않음. 글에 키 값은 넣지 않는다.
"""
import logging

from app.config import settings
from app.services import keystore

log = logging.getLogger(__name__)


def _key(name: str):
    try:
        return keystore.get(name)
    except Exception:
        return None


def _model_gone() -> bool:
    try:
        from app import llm
        return llm.gone(settings.nim_chat_model)
    except Exception:
        return False


def problems() -> list[dict]:
    """지금 설정에서 꺼져 있는 것. level: error(손님 기능이 깨짐)·warn(운영이 깜깜)·info(선택 기능 꺼짐)."""
    out = []

    def add(key, level, text, fix):
        out.append({"key": key, "level": level, "text": text, "fix": fix})

    if settings.preview_host and not (settings.public_base_url or "").strip().startswith("https://"):
        add("public_base_url", "error",
            "PUBLIC_BASE_URL이 없어 공개 사이트의 채팅하기·주문·전화 인증·알림 링크가 꺼져 있어요",
            "서버 .env에 PUBLIC_BASE_URL=https://앱 주소 를 넣고 다시 시작")
    if _model_gone():
        add("nim_chat_model", "error",
            f"주 AI 모델 {settings.nim_chat_model}이 응답하지 않아요(서비스 종료) · 대비 모델로 답하는 중",
            "서버 .env NIM_CHAT_MODEL을 지금 서비스 중인 모델로 바꾸고 다시 시작")
    if not _key("telegram_bot_token") or not (settings.telegram_chat_id or "").strip():
        add("telegram", "warn", "운영자 텔레그램 알림이 꺼져 있어 오류·설정 문제를 아무도 못 받아요",
            "관리자 화면 키 탭 '텔레그램 봇 토큰' + 서버 .env TELEGRAM_CHAT_ID")
    if not (settings.token_enc_key or "").strip():
        add("token_enc_key", "warn", "TOKEN_ENC_KEY가 없어 관리자 화면에서 키를 바꾸거나 넣을 수 없어요",
            "서버 .env에 TOKEN_ENC_KEY(긴 임의 문자열)를 넣고 다시 시작")
    if not _key("vapid_private_key"):
        add("vapid", "info", "휴대폰 알림(웹 푸시) 키가 없어 사장님 휴대폰 알림이 꺼져 있어요",
            "scripts/gen_vapid.py로 만든 값을 관리자 화면 키 탭 또는 서버 .env VAPID_PRIVATE_KEY에")
    if not (settings.kakao_js_key or "").strip():
        add("kakao_js_key", "info", "카카오 지도 JS 키가 없어 공개 사이트 지도가 예시 그림으로만 나와요",
            "서버 .env KAKAO_JS_KEY")
    return out


def announce() -> None:
    """서버가 뜰 때 한 번: error·warn을 로그로, 묶어서 운영 알림 한 건. 문제가 없으면 아무것도 안 보낸다."""
    try:
        loud = [p for p in problems() if p["level"] in ("error", "warn")]
        for p in loud:
            log.warning("설정 점검: %s → %s", p["text"], p["fix"])
        if loud:
            from app.services import ops_alert
            ops_alert.send("config", "[설정] " + "\n".join(f"· {p['text']} → {p['fix']}" for p in loud))
    except Exception:
        log.warning("설정 점검을 하지 못함", exc_info=True)
