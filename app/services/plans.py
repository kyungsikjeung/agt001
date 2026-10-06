"""요금제 한 곳 (D61, PRICING_AND_CHAT_1006 §5.2).

가격·포함량·기능을 **여기 한 곳**에만 적는다. 사용 장부(usage.py)·사장님 화면·나중의 요금
결제(F4)가 모두 이 표를 읽는다. 결제는 아직 켜지 않는다 — 지금은 모든 가게가 `free`다.

D61 원칙: **원가 0인 기능은 기본에, 건당 원가가 드는 것만 실비 사용량.**
그래서 스탬프·쿠폰·회원·예약은 무료에도 켜져 있고(우리 DB 쓰기뿐이라 원가 ≈ 0),
알림톡·문자처럼 건당 돈이 나가는 것만 포함량을 두고 넘으면 선불 충전에서 깎는다.
"""
from typing import Optional

# 포함량: 숫자는 KST 한 달 기준, None은 "무제한(적정 사용)"
# restyle(디자인 고치기)은 D40(USAGE_QUOTA_CONTRACT)이 20, D61 가격표가 5다. 더 느슨한 20을 쓴다
# — 이미 쓰는 사장님의 한도를 결정 없이 조이지 않는다. 어느 쪽으로 갈지는 확인 필요.
PLANS: dict = {
    "free": {
        "name": "무료",
        "won": 0,
        "quota": {"design": 3, "restyle": 20, "chat_ai": 300, "alimtalk": 0},
        "features": ("site", "inquiry", "chat", "push", "stamp", "member", "booking"),
        "staff": 1,
        "overage_won": {"alimtalk": 15, "sms": 15},
    },
    "shop": {
        "name": "가게",
        "won": 9900,
        "quota": {"design": 3, "restyle": None, "chat_ai": 1000, "alimtalk": 100},
        "features": ("site", "inquiry", "chat", "push", "stamp", "member", "booking",
                     "order", "domain", "no_badge"),
        "staff": 3,
        "overage_won": {"alimtalk": 15, "sms": 15},
    },
    "pro": {
        "name": "프로",
        "won": 24900,
        "quota": {"design": 3, "restyle": None, "chat_ai": 3000, "alimtalk": 500},
        "features": ("site", "inquiry", "chat", "push", "stamp", "member", "booking",
                     "order", "domain", "no_badge"),
        "staff": 10,
        "overage_won": {"alimtalk": 12, "sms": 12},
    },
}
DEFAULT = "free"
SETUP_WON = 99000  # 제작비(한 번). 구독을 낮춘 만큼 첫 달에 회수한다 (D61 ⑤)
# 손님 결제 중개수수료는 0원이다(법 확인 전, PAYMENT_PLAN §2.3). 요금제와 무관하게 0.
GUEST_PAY_FEE_RATE = 0.0

LABEL = {"design": "시안 만들기", "restyle": "디자인 고치기",
         "chat_ai": "손님 채팅 AI 답", "alimtalk": "알림톡"}


def get(plan: Optional[str]) -> dict:
    """요금제 하나. 모르는 이름이면 무료로 본다(요금을 더 받는 쪽으로 틀리지 않게)."""
    return PLANS.get((plan or "").strip() or DEFAULT, PLANS[DEFAULT])


def of(site_key: Optional[str]) -> str:
    """이 가게가 지금 쓰는 요금제 이름. 구독 줄이 없거나 해지됐으면 무료.

    결제를 켜기 전까지는 사실상 모두 `free`다(구독을 만드는 코드가 아직 없다).
    """
    key = (site_key or "").strip()
    if not key:
        return DEFAULT
    try:
        from app.db.models import SubscriptionRow
        from app.db.session import get_sessionmaker
        with get_sessionmaker()() as db:
            row = db.get(SubscriptionRow, key)
    except Exception:
        import logging
        logging.getLogger(__name__).exception("요금제를 읽지 못함 — 무료로 봅니다 site=%s", key)
        return DEFAULT
    if row is None or row.status != "active" or row.plan not in PLANS:
        return DEFAULT
    return row.plan


def quota(action: str, plan: Optional[str] = None) -> Optional[int]:
    """이 요금제의 한 달 포함량. None은 무제한."""
    return get(plan)["quota"].get(action)


def quota_for_site(site_key: Optional[str], action: str) -> Optional[int]:
    return quota(action, of(site_key))


def has(feature: str, plan: Optional[str] = None) -> bool:
    """이 요금제에 그 기능이 켜져 있나 (site·inquiry·chat·push·stamp·member·booking·order·domain·no_badge)."""
    return feature in get(plan)["features"]


def overage_won(kind: str, plan: Optional[str] = None) -> int:
    """포함량을 넘었을 때 건당 깎는 금액(원)."""
    return int(get(plan)["overage_won"].get(kind, 0))
