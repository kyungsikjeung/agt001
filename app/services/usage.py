"""무료 사용 한도 장부 (USAGE_QUOTA_CONTRACT, D40).

가게(사이트 키)마다 KST 한 달에 시안 만들기 3회 + 디자인 고치기 20회. 넘어도 막지 않는다:
답에 안내를 붙이고 운영자에게 알린다(지불 의사 신호). 장부는 지급·사용·충전을 한 표에 적는다.
"""
import datetime
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.db.models import UsageLedgerRow
from app.db.session import get_sessionmaker

FREE = {"design": 3, "restyle": 20}
LABEL = {"design": "시안 만들기", "restyle": "디자인 고치기"}
LOW = 2  # 이만큼 남으면 미리 알린다
KST = datetime.timezone(datetime.timedelta(hours=9))


def _kst_now(now: Optional[datetime.datetime] = None) -> datetime.datetime:
    return (now or datetime.datetime.now(datetime.timezone.utc)).astimezone(KST)


def month_of(now: Optional[datetime.datetime] = None) -> str:
    return _kst_now(now).strftime("%Y-%m")


def resets_label(now: Optional[datetime.datetime] = None) -> str:
    """다음에 다시 채워지는 날 ("11월 1일")."""
    d = _kst_now(now)
    return f"{1 if d.month == 12 else d.month + 1}월 1일"


def _balance(db, site: str, month: str, action: str) -> tuple:
    """(남은 수, 이번 달 총량). 지급 줄이 아직 없으면 기본 지급으로 친다(읽기만 할 때)."""
    rows = db.execute(select(UsageLedgerRow.kind, func.sum(UsageLedgerRow.amount))
                      .where(UsageLedgerRow.site_key == site, UsageLedgerRow.month == month,
                             UsageLedgerRow.action == action)
                      .group_by(UsageLedgerRow.kind)).all()
    by = {kind: int(total or 0) for kind, total in rows}
    total = by.get("grant", FREE[action]) + by.get("topup", 0)
    return total + by.get("use", 0), total


def left(site: str, now: Optional[datetime.datetime] = None) -> dict:
    month = month_of(now)
    out = {"resets": resets_label(now)}
    with get_sessionmaker()() as db:
        for action in FREE:
            bal, total = _balance(db, site, month, action)
            out[action] = {"left": max(0, bal), "total": total}
    return out


def use(site: str, action: str, now: Optional[datetime.datetime] = None) -> dict:
    """한 번 썼다고 적는다(막지 않음). → {left, total, over}. 넘으면 운영자에게 알린다."""
    month = month_of(now)
    with get_sessionmaker()() as db, db.begin():
        db.execute(pg_insert(UsageLedgerRow).values(site_key=site, month=month, action=action, kind="grant",
                                                    amount=FREE[action])
                   .on_conflict_do_nothing(index_elements=["site_key", "month", "action"],
                                           index_where=UsageLedgerRow.kind == "grant"))
        db.add(UsageLedgerRow(site_key=site, month=month, action=action, kind="use", amount=-1))
        db.flush()
        bal, total = _balance(db, site, month, action)
    info = {"left": max(0, bal), "total": total, "over": bal < 0}
    if info["over"]:
        from app.services import funnel  # 지불 의사 신호 (D40) → 운영자 텔레그램(ops_alert)
        funnel.record("quota_exceeded", props={"site": site, "kind": action, "over": -bal})
    return info


def note(info: Optional[dict], action: str) -> str:
    """답 끝에 붙일 한 줄. 넉넉하면 빈 글."""
    if not info:
        return ""
    label = LABEL[action]
    if info.get("over"):
        return (f"이번 달 무료 {label}를 다 썼어요. 그래도 해 드렸어요 — 다음 달 1일에 다시 채워져요. "
                "더 필요하면 말씀해 주세요.")
    if info.get("left", 99) <= LOW:
        return f"이번 달 무료 {label} {info['left']}번 남았어요."
    return ""


def safe_use(site: Optional[str], action: str) -> Optional[dict]:
    """세다가 실패해도 디자인 일은 그대로 간다(장부는 보조)."""
    if not site:
        return None
    try:
        return use(site, action)
    except Exception:
        import logging
        logging.getLogger(__name__).exception("사용 장부 기록 실패 site=%s action=%s", site, action)
        return None
