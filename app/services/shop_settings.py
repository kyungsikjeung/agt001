"""가게별 설정 저장 (OWNER_SETTINGS_PLAN §1.2·§1.3).

솔라피 키·시크릿은 keystore._fernet()으로 암호화해 둔다. 비밀값은 절대 돌려주거나 로그에 남기지 않는다.
"""
import datetime
import logging
from typing import Optional

from app.db.models import ShopSettingsRow
from app.db.session import get_sessionmaker

log = logging.getLogger(__name__)

_NO_KEY_MSG = "서버 설정 때문에 지금은 자기 키를 넣을 수 없어요."


class SettingsError(ValueError):
    """사장님에게 보여 줄 한 줄 사유."""


def _payments_ready() -> bool:
    """결제 준비됨 (규칙은 payments.ready() 한 곳)."""
    from app.services import payments
    return payments.ready()


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def owned_sites(user_id: str) -> list[dict]:
    """주인(owner)인 가게의 {site_key, room_id, shop_name, published}. 권한은 shops.member_sites가 정한다."""
    from app.services import shops
    return [{k: s[k] for k in ("site_key", "room_id", "shop_name", "published")}
            for s in shops.member_sites(user_id) if s["role"] == "owner"]


def can_edit(user_id: str, site_key: str) -> bool:
    """위 목록에 있으면 True."""
    return any(s["site_key"] == site_key for s in owned_sites(user_id))


def get(site_key: str) -> dict:
    """{phone_verify, own_key, key_last4, sms_sender, order_on, guest_chat_on} — 비밀값은 절대 돌려주지 않음."""
    with get_sessionmaker()() as db:
        row = db.get(ShopSettingsRow, site_key)
        if row is None:
            return {"phone_verify": False, "own_key": False, "key_last4": "", "sms_sender": "",
                    "order_on": False, "guest_chat_on": True}
        return {"phone_verify": bool(row.phone_verify),
                "own_key": bool(row.solapi_key_enc and row.solapi_secret_enc),
                "key_last4": row.key_last4 or "",
                "sms_sender": row.sms_sender or "",
                "order_on": bool(row.order_on),
                "guest_chat_on": bool(row.guest_chat_on)}


def update(user_id: str, site_key: str, phone_verify: Optional[bool] = None,
           solapi_key: Optional[str] = None, solapi_secret: Optional[str] = None,
           sms_sender: Optional[str] = None, clear_key: bool = False,
           order_on: Optional[bool] = None, guest_chat_on: Optional[bool] = None) -> dict:
    """가게 설정을 바꾼다. 권한 없으면 PermissionError, 입력이 틀리면 SettingsError."""
    if not can_edit(user_id, site_key):
        raise PermissionError("이 가게 설정을 바꿀 수 없어요.")
    with get_sessionmaker()() as db, db.begin():
        row = db.get(ShopSettingsRow, site_key)
        if row is None:
            row = ShopSettingsRow(site_key=site_key, phone_verify=False, order_on=False, guest_chat_on=True)
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
        if order_on is not None:
            if bool(order_on) and not _payments_ready():
                raise SettingsError("결제 준비 중이에요")
            row.order_on = bool(order_on)
        if guest_chat_on is not None:
            row.guest_chat_on = bool(guest_chat_on)
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
