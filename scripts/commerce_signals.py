"""온라인 결제 운영 신호 보기 (WAVE5_CONTRACT §3.1).

최근 24시간의 payment_mismatch·webhook_bad_signature 사건 수와
사유별 수(funnel_events 표, props->>'reason')를 보여준다.
시간은 한국 시간으로 보여준다. 사건이 하나라도 있으면 종료 코드 1.

사용법: .venv/bin/python scripts/commerce_signals.py
"""
import datetime
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text  # noqa: E402

from app.db.session import get_sessionmaker  # noqa: E402

EVENTS = ("payment_mismatch", "webhook_bad_signature")
KST = datetime.timezone(datetime.timedelta(hours=9))


def _fmt(dt: datetime.datetime) -> str:
    return dt.astimezone(KST).strftime("%m월 %d일 %H:%M")


def main(argv) -> int:
    now = datetime.datetime.now(datetime.timezone.utc)
    cutoff = now - datetime.timedelta(hours=24)
    with get_sessionmaker()() as db:
        rows = db.execute(
            text("SELECT event, props ->> 'reason' AS reason, count(*) AS n"
                 " FROM funnel_events"
                 " WHERE ts >= :cutoff AND event IN ('payment_mismatch', 'webhook_bad_signature')"
                 " GROUP BY event, props ->> 'reason'"),
            {"cutoff": cutoff},
        ).all()
    by_event: dict = {e: {} for e in EVENTS}
    for event, reason, n in rows:
        by_event.setdefault(event, {})[reason or "없음"] = int(n)
    print(f"기간: {_fmt(cutoff)} ~ {_fmt(now)} (한국 시간, 최근 24시간)")
    total = 0
    for event in EVENTS:
        reasons = by_event.get(event) or {}
        sub = sum(reasons.values())
        total += sub
        if reasons:
            detail = ", ".join(f"{r} {c}건" for r, c in sorted(reasons.items()))
            print(f"{event}: {sub}건 ({detail})")
        else:
            print(f"{event}: 0건")
    if total:
        print("결제 신호가 있어요. 포트원 콘솔과 대조해 주세요.")
        return 1
    print("이상 없음.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
