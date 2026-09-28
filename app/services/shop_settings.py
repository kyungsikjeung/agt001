"""가게별 설정 저장 (OWNER_SETTINGS_PLAN §1.2·§1.3).

솔라피 키·시크릿은 keystore._fernet()으로 암호화해 둔다. 비밀값은 절대 돌려주거나 로그에 남기지 않는다.
"""
import datetime
import logging
from typing import Optional

from sqlalchemy import select

from app import store
from app.config import settings
from app.db.models import ShopSettingsRow, UserRoomRow
from app.db.session import get_sessionmaker
from app.services import rooms as rooms_svc

log = logging.getLogger(__name__)

_NO_KEY_MSG = "서버 설정 때문에 지금은 자기 키를 넣을 수 없어요."


class SettingsError(Exception):
    """사장님에게 보여 줄 한 줄 사유."""


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _shop_name_of(session: Optional[dict]) -> str:
    card = (session or {}).get("prd") or {}
    slot = (card.get("slots") or {}).get("shop_name") or {}
    raw = slot.get("value") or ""
    return raw.strip() if isinstance(raw, str) else ""


def owned_sites(user_id: str) -> list[dict]:
    """계정에 붙은 방 중 방장인 방의 {site_key, room_id, shop_name, published}."""
    if not user_id:
        return []
    with get_sessionmaker()() as db:
        claims = db.execute(
            select(UserRoomRow.room_id, UserRoomRow.member_id).where(UserRoomRow.user_id == user_id)
        ).all()
    out = []
    for room_id, member_id in claims:
        room = store.read_room(room_id)
        if room is None:
            continue
        try:
            if rooms_svc.owner_id(room) != member_id:
                continue
        except Exception:
            continue
        session = store.read_session(room["session_id"])
        if session is None or not session.get("requirement_id"):
            continue
        card = session.get("prd") or {}
        out.append({"site_key": session["requirement_id"], "room_id": room_id,
                    "shop_name": _shop_name_of(session), "published": bool(card.get("published"))})
    return out


def can_edit(user_id: str, site_key: str) -> bool:
    """위 목록에 있으면 True."""
    return any(s["site_key"] == site_key for s in owned_sites(user_id))


def get(site_key: str) -> dict:
    """{phone_verify, own_key, key_last4, sms_sender} — 비밀값은 절대 돌려주지 않음."""
    with get_sessionmaker()() as db:
        row = db.get(ShopSettingsRow, site_key)
        if row is None:
            return {"phone_verify": False, "own_key": False, "key_last4": "", "sms_sender": ""}
        return {"phone_verify": bool(row.phone_verify),
                "own_key": bool(row.solapi_key_enc and row.solapi_secret_enc),
                "key_last4": row.key_last4 or "",
                "sms_sender": row.sms_sender or ""}


def update(user_id: str, site_key: str, phone_verify: Optional[bool] = None,
           solapi_key: Optional[str] = None, solapi_secret: Optional[str] = None,
           sms_sender: Optional[str] = None, clear_key: bool = False) -> dict:
    """가게 설정을 바꾼다. 권한 없으면 PermissionError, 입력이 틀리면 SettingsError."""
    if not can_edit(user_id, site_key):
        raise PermissionError("이 가게 설정을 바꿀 수 없어요.")
    with get_sessionmaker()() as db, db.begin():
        row = db.get(ShopSettingsRow, site_key)
        if row is None:
            row = ShopSettingsRow(site_key=site_key, phone_verify=False)
            db.add(row)
        if clear_key:
            row.solapi_key_enc = None
            row.solapi_secret_enc = None
            row.key_last4 = None
            row.sms_sender = None
        elif solapi_key is not None or solapi_secret is not None or sms_sender is not None:
            key = (solapi_key or "").strip()
            secret = (solapi_secret or "").strip()
            sender = "".join(ch for ch in (sms_sender or "") if ch.isdigit())
            if not (key and secret and sender):
                raise SettingsError("솔라피 키·시크릿·발신번호를 함께 넣어 주세요.")
            try:
                from app.services import keystore
                f = keystore._fernet()
            except Exception:
                raise SettingsError(_NO_KEY_MSG)
            row.solapi_key_enc = f.encrypt(key.encode()).decode()
            row.solapi_secret_enc = f.encrypt(secret.encode()).decode()
            row.sms_sender = sender
            row.key_last4 = key[-4:]
        if phone_verify is not None:
            row.phone_verify = bool(phone_verify)
        row.updated_by = user_id
        row.updated_at = _now()
    return get(site_key)


def sms_credentials(site_key: Optional[str]) -> Optional[tuple]:
    """복호화한 (key, secret, sender) — 서버 안에서만 쓴다. 없거나 풀 수 없으면 None."""
    if not site_key:
        return None
    with get_sessionmaker()() as db:
        row = db.get(ShopSettingsRow, site_key)
        if row is None or not row.solapi_key_enc or not row.solapi_secret_enc or not row.sms_sender:
            return None
        key_enc, secret_enc, sender = row.solapi_key_enc, row.solapi_secret_enc, row.sms_sender
    try:
        from app.services import keystore
        f = keystore._fernet()
        return (f.decrypt(key_enc.encode()).decode(), f.decrypt(secret_enc.encode()).decode(), sender)
    except Exception:
        log.warning("가게 문자 키를 풀 수 없어요")
        return None


def phone_verify_on(site_key: str) -> bool:
    """phone_verify 켜짐 그리고 sms.available(site_key)."""
    with get_sessionmaker()() as db:
        row = db.get(ShopSettingsRow, site_key)
        if row is None or not row.phone_verify:
            return False
    from app.services import sms as sms_svc
    return sms_svc.available(site_key)
