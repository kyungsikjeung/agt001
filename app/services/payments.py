"""포트원 테스트 결제 코어 (PAY_WAVE3_CONTRACT §3.2).

포트원 호출은 이 파일에만 둔다. 금액은 손님 말이 아니라 DB와 포트원 조회에서만 본다.
"""
import base64
import datetime
import hashlib
import hmac
import json
import logging
from typing import Optional

import httpx
from sqlalchemy import func, select

from app import store
from app.config import settings
from app.db.models import CouponRow, OrderItemRow, OrderRow, PaymentRow, RefundRow, RoomRow, SessionRow
from app.db.session import get_sessionmaker

log = logging.getLogger(__name__)

API = "https://api.portone.io"
TIMEOUT = 10.0

# 테스트에서 httpx.MockTransport를 넣어 가짜 응답을 쓴다.
_TRANSPORT: Optional[httpx.BaseTransport] = None


def _api_secret() -> str:
    from app.services import keystore
    return (keystore.get("portone_api_secret") or "").strip()


def _client() -> httpx.Client:
    return httpx.Client(base_url=API, headers={"Authorization": f"PortOne {_api_secret()}"},
                        timeout=TIMEOUT, transport=_TRANSPORT)


def ready() -> bool:
    """store_id·channel_key·api_secret이 다 있으면 True."""
    return bool((settings.portone_store_id or "").strip()) \
        and bool((settings.portone_channel_key or "").strip()) \
        and bool(_api_secret())


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _unwrap(data: dict) -> dict:
    # V2 조회 응답 모양이 {payment: {...}}로 올 수도 있어 한 겹만 벗긴다.
    if isinstance(data, dict) and isinstance(data.get("payment"), dict):
        return data["payment"]
    return data if isinstance(data, dict) else {}


def _parse_remote(data: dict) -> tuple:
    """(status, total, currency). 필드 이름은 developers.portone.io V2 기준 (DEVIATIONS 참고)."""
    d = _unwrap(data)
    status = str(d.get("status") or "").upper()
    amt = d.get("amount")
    total = amt.get("total") if isinstance(amt, dict) else (amt if isinstance(amt, int) else None)
    if isinstance(total, bool):
        total = None
    currency = str(d.get("currency") or "").upper()
    return status, total, currency


def _notify_paid(site_key: str, order_id: int, text: str) -> None:
    """커밋 뒤에 방 알림 + 사장님 카톡. 실패해도 결제는 그대로 둔다."""
    try:
        with get_sessionmaker()() as db:
            room_id = db.scalar(select(RoomRow.id)
                                .join(SessionRow, RoomRow.session_id == SessionRow.id)
                                .where(SessionRow.requirement_id == site_key))
        if room_id:
            try:
                with store.room_tx(room_id) as (room, _session):
                    if room is not None:
                        from app.services import rooms
                        rooms._append(room, "system", "주문 알림", text, kind="order",
                                      meta={"order_id": order_id})

            except Exception:
                log.exception("주문 알림 실패 room=%s", room_id)
        else:
            room_id = None
        if room_id:
            def _kakao(rid=room_id, msg=text):
                try:
                    from app.services import notify
                    notify.owner_kakao(rid, msg)
                except Exception:
                    log.exception("주문 카톡 알림 실패 room=%s", rid)
            store.after_commit(_kakao)
    except Exception:
        log.exception("주문 알림 준비 실패 site=%s", site_key)


def complete(pay_id: str) -> str:
    """§1 10~12. 'paid'·'already'·'failed'·'pending'·'unknown'."""
    pid = (pay_id or "").strip()
    if not pid:
        return "unknown"
    result = "pending"
    notify_args: Optional[tuple] = None
    with get_sessionmaker()() as db, db.begin():
        pay = db.scalar(select(PaymentRow).where(PaymentRow.provider_payment_id == pid).with_for_update())
        if pay is None:
            result = "unknown"
        elif pay.status == "paid":
            result = "already"
        elif pay.status == "canceled":
            result = "failed"
        else:
            want = pay.amount
            order_id = pay.order_id
            site_key = pay.site_key
            try:
                with _client() as client:
                    resp = client.get(f"/payments/{pid}")
            except httpx.HTTPError:
                result = "pending"
                resp = None
            if resp is not None:
                if resp.status_code == 404:
                    result = "unknown"
                elif not 200 <= resp.status_code < 300:
                    result = "pending"
                else:
                    try:
                        data = resp.json()
                    except ValueError:
                        data = None
                    if data is None:
                        result = "pending"
                    else:
                        status, total, currency = _parse_remote(data)
                        pay.raw = data if isinstance(data, dict) else {"raw": str(data)[:2000]}
                        if status == "PAID" and total == want and currency == "KRW":
                            pay.status = "paid"
                            pay.paid_at = _now()
                            order = db.scalar(select(OrderRow).where(OrderRow.id == order_id).with_for_update())
                            if order is not None:
                                order.status = "paid"
                            # 도장·쿠폰은 처음 paid가 되는 자리에서 (W4-C).
                            coupon_used = False
                            try:
                                from app.services import stamps
                                held = db.scalar(select(func.count()).select_from(CouponRow).where(
                                    CouponRow.held_order_id == order_id,
                                    CouponRow.status == "held")) or 0
                                # savepoint: 도장 쪽 DB 오류가 결제 확정까지 되돌리지 않게
                                with db.begin_nested():
                                    stamps.settle_held(db, order_id)
                                    stamps.earn(db, order_id)
                                coupon_used = held > 0
                            except Exception:
                                log.exception("스탬프 적립 실패 order=%s", order_id)
                            items = db.scalars(select(OrderItemRow).where(OrderItemRow.order_id == order_id)
                                               .order_by(OrderItemRow.id)).all()
                            desc = ", ".join(f"{r.name} {r.qty}" for r in items) or "주문"
                            text = f"새 주문: {desc} · {want:,}원 (테스트 결제)"
                            if coupon_used:
                                text += " · 쿠폰 사용"
                            notify_args = (site_key, order_id, text)
                            result = "paid"
                        elif status == "PAID":
                            # PAID인데 금액·통화가 다르면 실패로 둔다. 사장님께 알리지 않는다.
                            pay.status = "failed"
                            result = "failed"
                            # 금액 먼저 본다. 둘 다 다르면 amount로 남긴다.
                            reason = "amount" if total != want else ("currency" if currency != "KRW" else None)
                            if reason is not None:
                                try:
                                    from app.services import funnel
                                    funnel.record("payment_mismatch",
                                                  props={"site": site_key, "reason": reason})
                                except Exception:
                                    pass
                        elif status in ("FAILED", "CANCELED", "CANCELLED"):
                            pay.status = "failed"
                            result = "failed"
                        else:
                            result = "pending"
    # 커밋된 뒤에 알린다. 처음 paid가 될 때만.
    if notify_args is not None:
        _notify_paid(*notify_args)
    return result


def complete_free(pay_id: str) -> str:
    """합계 0원 주문을 포트원 없이 확정한다. 'paid'·'already'. 금액이 남으면 ValueError."""
    pid = (pay_id or "").strip()
    if not pid:
        raise ValueError("결제할 금액이 남아 있어요.")
    notify_args: Optional[tuple] = None
    with get_sessionmaker()() as db, db.begin():
        pay = db.scalar(select(PaymentRow).where(PaymentRow.provider_payment_id == pid).with_for_update())
        if pay is None:
            raise ValueError("결제할 금액이 남아 있어요.")
        if pay.status == "paid":
            return "already"
        if pay.status != "ready" or pay.amount != 0:
            raise ValueError("결제할 금액이 남아 있어요.")
        # 0원은 쿠폰 덕분이다. 그 쿠폰이 아직 이 주문에 묶여 있어야 한다: 잡은 시간(60분)이 지나 풀린 쿠폰을
        # 매장·다른 주문에서 쓴 뒤 이 주문을 0원으로 확정하면 한 쿠폰으로 두 번 받는다 (보안 점검 9/30).
        held = db.scalar(select(CouponRow).where(
            CouponRow.held_order_id == pay.order_id, CouponRow.status == "held").with_for_update())
        until = held.held_until if held is not None else None
        if until is not None and until.tzinfo is None:
            until = until.replace(tzinfo=datetime.timezone.utc)
        if until is None or until <= _now():
            raise ValueError("쿠폰을 잡아 둔 시간이 지났어요. 쿠폰을 다시 골라 주세요.")
        pay.provider = "manual"
        pay.method = "coupon"
        pay.status = "paid"
        pay.paid_at = _now()
        order = db.scalar(select(OrderRow).where(OrderRow.id == pay.order_id).with_for_update())
        if order is not None:
            order.status = "paid"
        try:
            from app.services import stamps
            with db.begin_nested():  # 도장 실패가 결제 확정을 되돌리지 않게
                stamps.settle_held(db, pay.order_id)
                stamps.earn(db, pay.order_id)
        except Exception:
            log.exception("스탬프 적립 실패 order=%s", pay.order_id)
        items = db.scalars(select(OrderItemRow).where(OrderItemRow.order_id == pay.order_id)
                           .order_by(OrderItemRow.id)).all()
        desc = ", ".join(f"{r.name} {r.qty}" for r in items) or "주문"
        notify_args = (pay.site_key, pay.order_id,
                       f"새 주문: {desc} · 0원 (테스트 결제) · 쿠폰 사용")
    if notify_args is not None:
        _notify_paid(*notify_args)
    return "paid"


def refund(site_key: str, order_id: int, amount: int | None, reason: str, by: str) -> dict:
    """남은 금액 안에서 취소. None이면 남은 전액. 다른 가게 주문이면 LookupError."""
    key = (site_key or "").strip()
    with get_sessionmaker()() as db, db.begin():
        order = db.scalar(select(OrderRow).where(OrderRow.id == order_id).with_for_update())
        if order is None or order.site_key != key:
            raise LookupError("주문을 찾을 수 없어요.")
        pay = db.scalar(select(PaymentRow).where(PaymentRow.order_id == order_id).with_for_update())
        if pay is None or pay.site_key != key:
            raise LookupError("주문을 찾을 수 없어요.")
        if pay.status != "paid":
            raise ValueError("결제된 주문만 환불할 수 있어요.")
        done = db.scalar(select(func.coalesce(func.sum(RefundRow.amount), 0))
                         .where(RefundRow.payment_id == pay.id)) or 0
        remaining = pay.amount - done
        want = remaining if amount is None else amount
        if isinstance(want, bool) or not isinstance(want, int) or want <= 0 or want > remaining:
            raise ValueError("환불 금액은 남은 금액보다 클 수 없어요.")
        why = (str(reason or "").strip() or "사장님 환불")[:200]
        try:
            with _client() as client:
                resp = client.post(f"/payments/{pay.provider_payment_id}/cancel",
                                   json={"amount": want, "reason": why})
        except httpx.HTTPError:
            raise ValueError("환불에 실패했어요. 잠시 뒤 다시 해 주세요.")
        if not 200 <= resp.status_code < 300:
            raise ValueError("환불에 실패했어요. 잠시 뒤 다시 해 주세요.")
        try:
            data = resp.json() if resp.content else {}
        except ValueError:
            data = {}
        d = _unwrap(data if isinstance(data, dict) else {})
        cancel_id = None
        if isinstance(d, dict):
            canc = d.get("cancellation")
            cancel_id = (canc.get("id") if isinstance(canc, dict) else None) \
                or d.get("cancel_id") or d.get("id")
        db.add(RefundRow(payment_id=pay.id, site_key=key, amount=want, reason=why,
                         by_user_id=(str(by or "")[:80] or None),
                         provider_cancel_id=str(cancel_id)[:120] if cancel_id else None))
        left = remaining - want
        if left == 0:
            pay.status = "canceled"
            order.status = "canceled"
            # 전액 환불이면 그 주문 도장을 회수한다 (W4-C).
            try:
                from app.services import stamps
                with db.begin_nested():  # 회수 실패가 환불 기록을 되돌리지 않게
                    stamps.revoke(db, order_id)
            except Exception:
                log.exception("스탬프 회수 실패 order=%s", order_id)
        return {"order_id": order_id, "payment_id": pay.id, "refunded": want,
                "remaining": left, "status": pay.status}


def verify_webhook(headers: dict, body: bytes) -> dict:
    """Standard Webhooks 서명 확인(HMAC-SHA256). 틀리면 ValueError. 맞으면 JSON."""
    from app.services import keystore

    def _note(reason: str) -> None:
        # 기록 실패가 검증 결과를 바꾸지 않게 삼킨다.
        try:
            from app.services import funnel
            funnel.record("webhook_bad_signature", props={"reason": reason})
        except Exception:
            pass

    low = {str(k).lower(): v for k, v in (headers or {}).items()}
    wid = str(low.get("webhook-id") or "").strip()
    ts = str(low.get("webhook-timestamp") or "").strip()
    sig = str(low.get("webhook-signature") or "").strip()
    if not (wid and ts and sig):
        _note("missing")
        raise ValueError("서명이 없어요.")
    try:
        ts_n = int(ts)
    except ValueError:
        _note("stale")
        raise ValueError("서명이 틀렸어요.")
    now_n = int(_now().timestamp())
    if abs(now_n - ts_n) > 300:
        _note("stale")
        raise ValueError("서명이 틀렸어요.")
    secret = (keystore.get("portone_webhook_secret") or "").strip()
    if secret.startswith("whsec_"):
        secret = secret[len("whsec_"):]
    try:
        raw_key = base64.b64decode(secret, validate=True)
    except Exception:
        _note("mismatch")
        raise ValueError("서명이 틀렸어요.")
    if not raw_key:
        # 비밀값이 없으면 빈 열쇠 서명을 누구나 만들 수 있다 → 받지 않는다
        _note("no_secret")
        raise ValueError("웹훅 비밀값이 없어요.")
    try:
        text = body.decode("utf-8")
    except Exception:
        _note("mismatch")
        raise ValueError("서명이 틀렸어요.")
    msg = f"{wid}.{ts}.{text}".encode("utf-8")
    digest = base64.b64encode(hmac.new(raw_key, msg, hashlib.sha256).digest()).decode()
    ok = False
    for part in sig.split():
        version, _, v = part.partition(",")
        if version != "v1":
            continue
        if hmac.compare_digest(v.strip(), digest):
            ok = True
            break
    if not ok:
        _note("mismatch")
        raise ValueError("서명이 틀렸어요.")
    try:
        return json.loads(text)
    except ValueError:
        _note("mismatch")
        raise ValueError("서명이 틀렸어요.")
