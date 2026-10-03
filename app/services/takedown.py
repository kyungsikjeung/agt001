"""공개 사이트 내리기 (D47 "오픈 전 필수", D49 "사이트 내리기", 백로그 O-4).

관리자가 문제 있는 사이트(불법·사칭·신고)를 바로 내린다. 표시는 파일 하나:
generated/<site_key>/takedown.json. 공개본(published/)과 생성본(web/)은 지우지 않으므로
사장님이 다시 공개하거나 고쳐도 내림이 풀리지 않고, 관리자가 되돌리면 그대로 다시 열린다.
내린 사이트는 /site/가 410을 주고, 문의·예약·주문·손님 채팅도 받지 않는다.
"""
import datetime
import json
import logging
from typing import Optional

from app.config import settings
from app.security import sanitize_token

log = logging.getLogger(__name__)

MARKER = "takedown.json"
REASON_MAX = 200


def _marker(site_key: str):
    key = sanitize_token(site_key or "")
    return settings.generated_dir / key / MARKER if key else None


def info(site_key: str) -> Optional[dict]:
    """내렸으면 {reason, by, at}, 아니면 None."""
    path = _marker(site_key)
    if path is None or not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        log.exception("내림 표시 읽기 실패 %s", site_key)
        return {}  # 표시 파일이 있으면 깨졌어도 내린 것으로 본다(열어 두는 쪽이 더 위험)


def is_down(site_key: str) -> bool:
    return info(site_key) is not None


def take_down(site_key: str, user_id: str, reason: str) -> dict:
    from app.services import keystore, ops_alert
    path = _marker(site_key)
    if path is None:
        raise ValueError("사이트 키가 올바르지 않아요.")
    reason = " ".join((reason or "").split())[:REASON_MAX]
    if not reason:
        raise ValueError("내리는 이유를 적어 주세요.")
    data = {"reason": reason, "by": user_id,
            "at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    keystore.audit(user_id, "site_takedown", path.parent.name, {"reason": reason})
    try:
        ops_alert.send("site_takedown", f"[내림] 사이트 {path.parent.name} · {reason}")
    except Exception:
        pass
    return data


def restore(site_key: str, user_id: str) -> None:
    from app.services import keystore
    path = _marker(site_key)
    if path is None or not path.is_file():
        raise ValueError("내린 사이트가 아니에요.")
    path.unlink()
    keystore.audit(user_id, "site_restore", path.parent.name)
