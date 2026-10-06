"""사용 한도 장부 (USAGE_QUOTA_CONTRACT, D40 + 요금제 D61).

가게(사이트 키)마다 KST 한 달 포함량을 **요금제에서 읽는다**(plans.py 한 곳). 넘어도 막지 않는다:
답에 안내를 붙이고 운영자에게 알린다(지불 의사 신호). 장부는 지급·사용·충전을 한 표에 적는다.
포함량이 None인 것(유료의 디자인 고치기 등)은 무제한이라 세기만 하고 안내를 붙이지 않는다.
"""
import datetime
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.db.models import UsageLedgerRow
from app.db.session import get_sessionmaker

from app.services.plans import LABEL  # 이름도 요금제 쪽 한 곳에서

ACTIONS = ("design", "restyle", "chat_ai")  # 장부로 세는 것 (알림톡은 선불 충전 쪽, F4)
UNLIMITED = 10 ** 9  # 무제한을 장부에 적을 때 쓰는 큰 수(지급 줄이 모양을 지켜야 한다)
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


def _grant(site: str, action: str) -> int:
    """이 가게 요금제의 이번 달 지급량. 무제한은 큰 수로 적는다."""
    from app.services import plans
    want = plans.quota_for_site(site, action)
    return UNLIMITED if want is None else int(want)


def _balance(db, site: str, month: str, action: str, grant: Optional[int] = None) -> tuple:
    """(남은 수, 이번 달 총량). 지급 줄이 아직 없으면 요금제 지급량으로 친다(읽기만 할 때)."""
    rows = db.execute(select(UsageLedgerRow.kind, func.sum(UsageLedgerRow.amount))
                      .where(UsageLedgerRow.site_key == site, UsageLedgerRow.month == month,
                             UsageLedgerRow.action == action)
                      .group_by(UsageLedgerRow.kind)).all()
    by = {kind: int(total or 0) for kind, total in rows}
    total = by.get("grant", grant if grant is not None else _grant(site, action)) + by.get("topup", 0)
    return total + by.get("use", 0), total


def left(site: str, now: Optional[datetime.datetime] = None) -> dict:
    month = month_of(now)
    out = {"resets": resets_label(now)}
    with get_sessionmaker()() as db:
        for action in ACTIONS:
            bal, total = _balance(db, site, month, action)
            out[action] = {"left": max(0, bal), "total": total,
                           "unlimited": total >= UNLIMITED}
    return out


def use(site: str, action: str, now: Optional[datetime.datetime] = None) -> dict:
    """한 번 썼다고 적는다(막지 않음). → {left, total, over}. 넘으면 운영자에게 알린다."""
    month = month_of(now)
    with get_sessionmaker()() as db, db.begin():
        grant = _grant(site, action)
        db.execute(pg_insert(UsageLedgerRow).values(site_key=site, month=month, action=action, kind="grant",
                                                    amount=grant)
                   .on_conflict_do_nothing(index_elements=["site_key", "month", "action"],
                                           index_where=UsageLedgerRow.kind == "grant"))
        db.add(UsageLedgerRow(site_key=site, month=month, action=action, kind="use", amount=-1))
        db.flush()
        bal, total = _balance(db, site, month, action, grant)
    info = {"left": max(0, bal), "total": total, "over": bal < 0,
            "unlimited": total >= UNLIMITED}
    if info["over"]:
        from app.services import funnel  # 지불 의사 신호 (D40) → 운영자 텔레그램(ops_alert)
        funnel.record("quota_exceeded", props={"site": site, "kind": action, "over": -bal})
    return info


def note(info: Optional[dict], action: str) -> str:
    """답 끝에 붙일 한 줄. 넉넉하면 빈 글."""
    if not info:
        return ""
    if info.get("unlimited"):
        return ""  # 무제한 요금제에는 남은 횟수를 말하지 않는다
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
