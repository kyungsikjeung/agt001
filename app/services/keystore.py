"""API 키 저장소 (DECISIONS.md D50).

관리자 화면에서 키를 바꿀 수 있다. 값은 DB에 암호화해 두고(서버 .env의 TOKEN_ENC_KEY로), 화면에는 뒤 4자리만 보인다.
저장된 값은 다시 꺼내 보여 주지 않는다. 바꿀 때는 새 키로 연결 테스트를 먼저 통과해야 하고, 이전 키는 7일간
되돌리기용으로 남긴다. 누가·언제·어떤 키를 바꿨는지 기록한다(값은 기록하지 않음). 재시작 없이 바로 쓰인다.

DB에 값이 없으면 서버 .env 값을 쓴다. 암호화 열쇠·DB 주소·관리자 명단은 여기서 다루지 않는다(화면에서 못 바꿈).
"""
import base64
import datetime
import hashlib
import logging
import threading
import time
from typing import Optional

import httpx
from sqlalchemy import delete, select

from app.config import settings
from app.db.models import AdminAuditRow, SecretRow, SecretVersionRow
from app.db.session import get_sessionmaker

log = logging.getLogger(__name__)

# 화면에서 바꿀 수 있는 키: 이름 → (보일 이름, 어디에 쓰는지)
EDITABLE = {
    "nim_api_key": ("NVIDIA NIM API 키", "대화·요구사항 검토·음성 인식·음성 합성"),
    "zen_api_key": ("OpenCode Zen API 키", "디자인 단계 유료 모델 비교(D39)"),
    "gemini_api_key": ("Gemini API 키", "포토리얼 예시 이미지 생성"),
    "kakao_rest_api_key": ("카카오 REST API 키", "카카오 로그인·카카오톡 알림"),
    "kakao_client_secret": ("카카오 Client Secret", "카카오 로그인·카카오톡 알림"),
    "google_client_secret": ("구글 로그인 Client Secret", "구글 로그인"),
    "telegram_bot_token": ("텔레그램 봇 토큰", "운영자 알림"),
}
KEEP_DAYS = 7
CACHE_SEC = 30.0  # 여러 서버 프로세스가 있어도 이 시간 안에 새 키를 읽는다

_cache: dict = {"at": 0.0, "values": {}}
_lock = threading.Lock()


class KeyError_(Exception):
    """사용자에게 보여 줄 한 줄."""


def ready() -> bool:
    """키 교체를 열 수 있는가: 암호화 열쇠가 .env에 따로 있어야 한다(카카오 비밀값에서 파생되면 안 됨)."""
    return bool((settings.token_enc_key or "").strip())


def _fernet():
    from cryptography.fernet import Fernet
    if not ready():
        raise KeyError_("서버 .env에 TOKEN_ENC_KEY를 먼저 넣어 주세요.")
    raw = "agt001-keystore:" + settings.token_enc_key.strip()
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(raw.encode()).digest()))


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _last4(value: str) -> str:
    return value[-4:] if len(value) >= 8 else "****"


def invalidate() -> None:
    with _lock:
        _cache["at"] = 0.0


def _db_values() -> dict:
    with _lock:
        if time.monotonic() - _cache["at"] < CACHE_SEC:
            return _cache["values"]
    values = {}
    if ready():
        f = _fernet()
        with get_sessionmaker()() as db:
            for row in db.scalars(select(SecretRow)).all():
                try:
                    values[row.name] = f.decrypt(row.value_enc.encode()).decode()
                except Exception:
                    log.error("키 %s를 풀 수 없어요(암호화 열쇠가 바뀌었나요?) — .env 값을 씁니다", row.name)
    with _lock:
        _cache.update(at=time.monotonic(), values=values)
    return values


def get(name: str) -> Optional[str]:
    """지금 쓸 키: 관리자 화면에서 바꾼 값이 있으면 그것, 없으면 .env 값."""
    if name in EDITABLE:
        try:
            value = _db_values().get(name)
        except Exception:
            log.exception("키 저장소를 읽지 못함 — .env 값을 씁니다")
            value = None
        if value:
            return value
    return getattr(settings, name, None)


def status() -> list[dict]:
    """화면에 보일 상태. 값은 뒤 4자리만."""
    rows, versions = {}, {}
    since = _now() - datetime.timedelta(days=KEEP_DAYS)
    with get_sessionmaker()() as db:
        for r in db.scalars(select(SecretRow)).all():
            rows[r.name] = r
        for v in db.scalars(select(SecretVersionRow).where(SecretVersionRow.replaced_at >= since)).all():
            versions.setdefault(v.name, 0)
            versions[v.name] += 1
    out = []
    for name, (label, use) in EDITABLE.items():
        env = getattr(settings, name, None)
        row = rows.get(name)
        source = "db" if row else ("env" if env else "none")
        out.append({"name": name, "label": label, "use": use, "source": source,
                    "last4": row.last4 if row else (_last4(env) if env else ""),
                    "updated_at": row.updated_at if row else None, "updated_by": row.updated_by if row else None,
                    "can_rollback": versions.get(name, 0) > 0})
    return out


def check_format(name: str, value: str) -> str:
    v = (value or "").strip()
    if name not in EDITABLE:
        raise KeyError_("바꿀 수 없는 키예요.")
    if not (8 <= len(v) <= 512) or any(c.isspace() for c in v) or not v.isascii() or not v.isprintable():
        raise KeyError_("키 형식이 맞지 않아요(8~512자, 공백 없이).")
    return v


def test(name: str, value: str) -> tuple[bool, str]:
    """새 키로 실제 연결을 해 본다. 확인 방법이 없는 키는 형식만 본다(그렇다고 알린다)."""
    try:
        if name == "nim_api_key":
            r = httpx.post(f"{settings.nim_base_url.rstrip('/')}/embeddings", timeout=15,
                           headers={"Authorization": f"Bearer {value}"},
                           json={"model": settings.nim_embed_model, "input": ["ok"], "input_type": "query"})
            return r.status_code == 200, f"NVIDIA 응답 {r.status_code}"
        if name == "zen_api_key":
            r = httpx.post("https://opencode.ai/zen/v1/chat/completions", timeout=20,
                           headers={"Authorization": f"Bearer {value}"},
                           json={"model": "deepseek-v4.1-flash", "max_tokens": 1,
                                 "messages": [{"role": "user", "content": "ok"}]})
            return r.status_code == 200, f"Zen 응답 {r.status_code}"
        if name == "telegram_bot_token":
            r = httpx.get(f"https://api.telegram.org/bot{value}/getMe", timeout=10)
            return r.status_code == 200 and bool(r.json().get("ok")), f"텔레그램 응답 {r.status_code}"
        if name == "gemini_api_key":
            base = (settings.gemini_api_base or "https://generativelanguage.googleapis.com").rstrip("/")
            r = httpx.get(f"{base}/v1beta/models", timeout=15, headers={"x-goog-api-key": value})  # 주소에 키 금지(로그)
            return r.status_code == 200, f"Gemini 응답 {r.status_code}"
    except httpx.HTTPError as e:
        return False, f"연결 실패({type(e).__name__})"
    return True, "형식만 확인했어요(이 키는 로그인을 한 번 해 봐야 확인돼요)."


def audit(user_id: str, action: str, target: Optional[str] = None, detail: Optional[dict] = None) -> None:
    with get_sessionmaker()() as db, db.begin():
        db.add(AdminAuditRow(user_id=user_id, action=action, target=target, detail=detail))


def replace(name: str, value: str, user_id: str, tested: bool) -> None:
    """새 키 저장. tested는 호출하는 쪽이 연결 테스트를 통과시켰다는 표시(통과 못 하면 저장하지 않는다)."""
    value = check_format(name, value)
    if not tested:
        raise KeyError_("연결 테스트를 통과해야 저장할 수 있어요.")
    f = _fernet()
    now = _now()
    with get_sessionmaker()() as db, db.begin():
        old = db.get(SecretRow, name)
        if old is not None:
            db.add(SecretVersionRow(name=name, value_enc=old.value_enc, last4=old.last4, replaced_by=user_id))
            old.value_enc, old.last4, old.updated_at, old.updated_by = f.encrypt(value.encode()).decode(), _last4(value), now, user_id
        else:
            db.add(SecretRow(name=name, value_enc=f.encrypt(value.encode()).decode(), last4=_last4(value), updated_by=user_id))
        db.execute(delete(SecretVersionRow).where(SecretVersionRow.replaced_at < now - datetime.timedelta(days=KEEP_DAYS)))
        db.add(AdminAuditRow(user_id=user_id, action="key_replace", target=name, detail={"last4": _last4(value)}))
    invalidate()
    _after_llm_key_change(name)


def rollback(name: str, user_id: str) -> None:
    """가장 최근 이전 키(7일 안)로 되돌린다. 지금 키는 이전 키 목록으로 옮겨 다시 되돌릴 수 있다."""
    if name not in EDITABLE:
        raise KeyError_("바꿀 수 없는 키예요.")
    since = _now() - datetime.timedelta(days=KEEP_DAYS)
    with get_sessionmaker()() as db, db.begin():
        prev = db.scalars(select(SecretVersionRow).where(SecretVersionRow.name == name, SecretVersionRow.replaced_at >= since)
                          .order_by(SecretVersionRow.replaced_at.desc(), SecretVersionRow.id.desc()).limit(1)).first()
        cur = db.get(SecretRow, name)
        if prev is None or cur is None:
            raise KeyError_("7일 안에 되돌릴 이전 키가 없어요.")
        db.add(SecretVersionRow(name=name, value_enc=cur.value_enc, last4=cur.last4, replaced_by=user_id))
        cur.value_enc, cur.last4, cur.updated_at, cur.updated_by = prev.value_enc, prev.last4, _now(), user_id
        db.delete(prev)
        db.add(AdminAuditRow(user_id=user_id, action="key_rollback", target=name, detail={"last4": prev.last4}))
    invalidate()
    _after_llm_key_change(name)


def clear(name: str, user_id: str) -> None:
    """화면에서 넣은 키를 지우고 .env 값으로 돌아간다(지운 키는 이전 키 목록에 7일 남는다)."""
    if name not in EDITABLE:
        raise KeyError_("바꿀 수 없는 키예요.")
    with get_sessionmaker()() as db, db.begin():
        cur = db.get(SecretRow, name)
        if cur is None:
            return
        db.add(SecretVersionRow(name=name, value_enc=cur.value_enc, last4=cur.last4, replaced_by=user_id))
        db.delete(cur)
        db.add(AdminAuditRow(user_id=user_id, action="key_clear", target=name, detail={"last4": cur.last4}))
    invalidate()
    _after_llm_key_change(name)


def _after_llm_key_change(name: str) -> None:
    if name == "nim_api_key":
        from app import llm
        llm.reset_client()
