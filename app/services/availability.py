"""예약 현황 실계산 (J7, D53④·D54 U5).

시안은 예시 현황(days_example)으로 보여 주고, 공개본은 확정 예약으로 계산한다.
계산은 이 파일 한 곳에 둔다 (card_data·site_data·design_variants는 고치지 않는다).

모든 날짜·시각은 KST다.
"""
import copy
import datetime
import json
import logging
import re

from sqlalchemy import select

from app.config import settings
from app.db.models import BookingRow, SessionRow
from app.db.session import get_sessionmaker
from app.security import sanitize_token

log = logging.getLogger(__name__)

# 한국 날짜 기준
KST = datetime.timezone(datetime.timedelta(hours=9))

# 요일 키(월요일=0) · 글자
_KEYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
_DOW = ("월", "화", "수", "목", "금", "토", "일")

# 영업시간을 못 읽었을 때 가정값 (D54 U5)
_ASSUMED_OPEN, _ASSUMED_CLOSE = 10 * 60, 18 * 60

# 시간 칸 길이(분) · 거절은 현황에 반영하지 않는다
SLOT_MIN = 60

# service 문자열에서 박 수를 읽는다 (API가 " · N박"을 붙인다)
_NIGHTS = re.compile(r"(\d+)\s*박")


def _today() -> datetime.date:
    return datetime.datetime.now(KST).date()


def _hours_text(card: dict) -> str:
    """hours 칸 글 (FILLED·ASSUMED만)."""
    slot = (card.get("slots") or {}).get("hours") or {}
    if slot.get("status") not in ("filled", "assumed"):
        return ""
    value = slot.get("value")
    items = value if isinstance(value, list) else [value]
    return ", ".join(str(v) for v in items if v)


def _structured(card: dict) -> dict:
    """카드 구조 데이터 (없으면 build로 계산)."""
    data = card.get("data")
    if isinstance(data, dict):
        return data
    try:
        from app.services import card_data as card_data_module
        return card_data_module.build(card)
    except Exception:
        return {}


def _to_min(prefix: str, hour: str, minute: str) -> int:
    h = int(hour)
    if prefix in ("오후", "저녁", "밤") and h < 12:
        h += 12
    if prefix == "오전" and h == 12:
        h = 0
    return h * 60 + int(minute or 0)


def _parse_hours(text: str):
    """영업시간 글 → (여는 분, 닫는 분, 휴무 키 집합). 못 읽으면 None."""
    t = re.sub(r"\s+", "", str(text or ""))
    if not t or "24시간" in t:
        return None
    closed = {_KEYS["월화수목금토일".index(m.group(1))]
              for m in re.finditer(r"([월화수목금토일])(?:요일)?휴무", t)}
    scope = None
    m = re.search(r"([월화수목금토일])~([월화수목금토일])", t)
    if m:
        a, b = "월화수목금토일".index(m.group(1)), "월화수목금토일".index(m.group(2))
        scope = {_KEYS[i] for i in range(a, b + 1)} if b >= a else set()
    elif "매일" in t or "연중무휴" in t:
        scope = set(_KEYS)
    elif "평일" in t:
        scope = set(_KEYS[:5])
        closed |= set(_KEYS[5:])
    elif "주말" in t:
        scope = set(_KEYS[5:])
    found = re.findall(r"(오전|오후|아침|저녁|밤)?(\d{1,2})(?::(\d{2}))?시?", t)
    if len(found) < 2:
        return None
    (p1, h1, m1), (p2, h2, m2) = found[0], found[1]
    opened, closed_at = _to_min(p1, h1, m1), _to_min(p2, h2, m2)
    if not p2 and closed_at <= opened and p1 in ("오후", "저녁", "밤"):
        closed_at += 12 * 60  # "오후 2시~8시" → 14~20시
    if not 0 <= opened < closed_at <= 24 * 60:
        return None
    if m1 and int(m1) > 59 or m2 and int(m2) > 59:
        return None
    open_days = (scope if scope is not None else set(_KEYS)) - closed
    if not open_days:
        return None
    return opened, closed_at, set(_KEYS) - open_days


def _hhmm(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def schedule(card: dict) -> dict:
    """영업 일정 구조화. 못 읽으면 10~18시·휴무 없음·assumed."""
    data = _structured(card)
    rooms = [r for r in (data.get("rooms") or [])
             if isinstance(r, dict) and str(r.get("name") or "").strip()]
    staff = [s for s in (data.get("staff") or [])
             if isinstance(s, dict) and str(s.get("name") or "").strip()]
    if rooms:
        capacity = len(rooms)  # 펜션(booking--dates)은 객실 수
    else:
        capacity = len(staff) if len(staff) >= 2 else 1
    parsed = _parse_hours(_hours_text(card))
    if parsed is None:
        weekly = {k: [["10:00", "18:00"]] for k in _KEYS}
        return {"weekly": weekly, "closed": [], "slot_min": SLOT_MIN,
                "capacity": capacity, "source": "assumed"}
    opened, closed_at, closed = parsed
    span = [_hhmm(opened), _hhmm(closed_at)]
    weekly = {k: [span] for k in _KEYS if k not in closed}
    return {"weekly": weekly, "closed": sorted(closed, key=_KEYS.index),
            "slot_min": SLOT_MIN, "capacity": capacity, "source": "owner"}


def _load(site_key: str, start: datetime.date, end: datetime.date) -> list:
    """기간 안의 예약 (날짜·시간·상태·service만). declined는 버린다."""
    with get_sessionmaker()() as db:
        rows = db.execute(
            select(BookingRow.visit_date, BookingRow.visit_time,
                   BookingRow.status, BookingRow.service)
            .where(BookingRow.site_key == site_key,
                   BookingRow.visit_date >= start, BookingRow.visit_date <= end)).all()
    return [r for r in rows if r.status in ("confirmed", "requested")]


def _slot_state(confirmed: int, requested: int, capacity: int) -> str:
    if confirmed >= capacity:
        return "full"
    if (confirmed > 0 and capacity - confirmed == 1) or requested > 0:
        return "few"
    return "open"


def days(card: dict, site_key: str, *, today=None, count: int = 5) -> list:
    """booking--slots의 days. 내일부터 휴무 뺀 count일, 확정 뺀 현황."""
    if today is None:
        today = _today()
    sched = schedule(card)
    capacity = sched["capacity"]
    closed = set(sched["closed"])
    dates = []
    day = today + datetime.timedelta(days=1)
    while len(dates) < count:
        if _KEYS[day.weekday()] not in closed:
            dates.append(day)
        day += datetime.timedelta(days=1)
    rows = _load(site_key, dates[0], dates[-1] + datetime.timedelta(days=1))
    now = datetime.datetime.now(KST)
    out = []
    for day in dates:
        opened, closed_at = sched["weekly"][_KEYS[day.weekday()]][0]
        o = int(opened[:2]) * 60 + int(opened[3:])
        c = int(closed_at[:2]) * 60 + int(closed_at[3:])
        slots = []
        t = o
        while t < c:
            time = _hhmm(t)
            if day > today or (day == today and
                               datetime.datetime.combine(day, datetime.time(t // 60, t % 60),
                                                         tzinfo=KST) > now):
                conf = sum(1 for r in rows if r.visit_date == day and r.status == "confirmed"
                           and (r.visit_time or "") == time)
                req = sum(1 for r in rows if r.visit_date == day and r.status == "requested"
                          and (r.visit_time or "") == time)
                slots.append({"time": time,
                              "state": _slot_state(conf, req, capacity)})
            t += sched["slot_min"]
        out.append({"date": day.isoformat(), "label": f"{day.month}/{day.day}",
                    "dow": _DOW[day.weekday()], "slots": slots})
    return out


def _nights_of(service: str) -> int:
    m = _NIGHTS.search(str(service or ""))
    if not m:
        return 1
    try:
        return min(14, max(1, int(m.group(1))))
    except ValueError:
        return 1


def nights(card: dict, site_key: str, *, today=None, count: int = 14) -> list:
    """booking--dates의 days. 확정 예약이 덮는 날짜를 막는다."""
    if today is None:
        today = _today()
    capacity = schedule(card)["capacity"]
    start = today + datetime.timedelta(days=1)
    last = start + datetime.timedelta(days=count - 1)
    rows = _load(site_key, start - datetime.timedelta(days=14), last)
    cover: dict = {}
    for r in rows:
        if r.status != "confirmed":
            continue
        for i in range(_nights_of(r.service)):
            day = r.visit_date + datetime.timedelta(days=i)
            if start <= day <= last:
                cover[day] = cover.get(day, 0) + 1
    out = []
    for i in range(count):
        day = start + datetime.timedelta(days=i)
        cov = cover.get(day, 0)
        req = sum(1 for r in rows if r.visit_date == day and r.status == "requested")
        out.append({"date": day.isoformat(), "label": f"{day.month}/{day.day}",
                    "dow": _DOW[day.weekday()],
                    "state": _slot_state(cov, req, capacity)})
    return out


def apply(spec: dict, card: dict, site_key: str, *, today=None) -> dict:
    """명세 사본의 예약 부품 days를 실계산으로 바꾼다 (days_example 끔)."""
    out = copy.deepcopy(spec)
    chat_url = _chat_url(site_key)
    for sec in out.get("sections") or []:
        if not isinstance(sec, dict) or sec.get("type") != "booking":
            continue
        content = sec.get("content")
        if not isinstance(content, dict):
            continue
        if chat_url:
            content["chat_url"] = chat_url
        if sec.get("variant") == "slots":
            content["days"] = days(card, site_key, today=today)
            content["days_example"] = False
        elif sec.get("variant") == "dates":
            content["days"] = nights(card, site_key, today=today)
            content["days_example"] = False
    return out


def _chat_url(site_key: str) -> str:
    """예약 봇을 켠 가게면 채팅 예약 주소(앱 주소). 생성 사이트는 미리보기 주소에서 열리므로 절대 주소로."""
    try:
        from app.services import booking_engine
        if booking_engine.active_spec(site_key) is None:
            return ""
    except Exception:
        return ""
    from app.services.site_render import app_link  # 손님 채팅 링크와 같은 규칙
    url = app_link(f"/chat/{site_key}")
    if not url:
        log.warning("PUBLIC_BASE_URL이 없어 채팅 예약 링크를 넣지 않아요 site=%s", site_key)
    return url


def _card_for_site(site_key: str):
    """requirement_id → 세션의 prd 카드 (없으면 None)."""
    key = sanitize_token(site_key or "")
    if not key:
        return None
    with get_sessionmaker()() as db:
        row = db.scalar(select(SessionRow).where(SessionRow.requirement_id == key))
        if row is None:
            return None
        prd = row.prd
    return prd if isinstance(prd, dict) else None


def _kst_today_str(today=None) -> str:
    return (today or _today()).isoformat()


def refresh_if_stale(site_key: str, *, today=None) -> bool:
    """공개본 날짜가 오늘(KST)이 아니고 예약 부품이 있으면 다시 그린다.

    날짜가 같으면 파일만 읽고 끝낸다. 실패하면 False (기존 파일을 그대로 보낸다).
    """
    try:
        key = sanitize_token(site_key or "")
        if not key:
            return False
        pub = settings.generated_dir / key / "published"
        index = pub / "index.html"
        if not index.is_file():
            return False
        today_s = _kst_today_str(today)
        meta_path = pub / "meta.json"
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            meta = {}
        if isinstance(meta, dict) and meta.get("kst_date") == today_s:
            return False
        try:
            html = index.read_text(encoding="utf-8")
        except Exception:
            return False
        if "/api/bookings/" not in html:
            # 예약 부품이 없으면 날짜만 갱신하고 끝낸다 (다음 요청은 파일만 읽는다)
            try:
                meta_path.write_text(json.dumps({"kst_date": today_s,
                                                 "variant": (meta or {}).get("variant")},
                                                ensure_ascii=False), encoding="utf-8")
            except Exception:
                pass
            return False
        card = _card_for_site(key)
        if card is None:
            return False
        variant = card.get("published") or (meta or {}).get("variant")
        if not variant:
            return False
        from app.services import design as design_module
        design_module.publish_choice(key, card, variant)
        return True
    except Exception:
        log.exception("공개본 날짜 넘어감 다시 그리기 실패 site=%s", site_key)
        return False


def slot_taken(db, site_key, visit_date, visit_time, service) -> bool:
    """마감 검사 (CUSTOMER_PLAN §1.3). 확정(confirmed) 예약만 센다.

    넘겨받은 db 세션으로 읽는다 (확정 때 잠금 안에서 부르기 위해).
    """
    card = _card_for_site(site_key)
    if card is None:
        capacity = 1
        has_rooms = False
    else:
        capacity = schedule(card)["capacity"]
        data = _structured(card)
        has_rooms = any(isinstance(r, dict) and str(r.get("name") or "").strip()
                        for r in (data.get("rooms") or []))
    day = visit_date
    if isinstance(day, str):
        day = datetime.date.fromisoformat(day.strip())
    elif isinstance(day, datetime.datetime):
        day = day.date()
    if has_rooms:
        nights = _nights_of(service)
        last = day + datetime.timedelta(days=nights - 1)
        rows = db.execute(
            select(BookingRow.visit_date, BookingRow.service)
            .where(BookingRow.site_key == site_key,
                   BookingRow.status == "confirmed",
                   BookingRow.visit_date >= day - datetime.timedelta(days=13),
                   BookingRow.visit_date <= last)).all()
        for i in range(nights):
            target = day + datetime.timedelta(days=i)
            cover = 0
            for r in rows:
                span = _nights_of(r.service)
                if r.visit_date <= target < r.visit_date + datetime.timedelta(days=span):
                    cover += 1
                    if cover >= capacity:
                        return True
        return False
    time_c = visit_time.strip() if isinstance(visit_time, str) else (visit_time or "")
    if not time_c:
        return False  # 날짜만 받는 예약은 시간 칸이 없어 막지 않는다
    rows = db.execute(
        select(BookingRow.id)
        .where(BookingRow.site_key == site_key,
               BookingRow.visit_date == day,
               BookingRow.visit_time == time_c,
               BookingRow.status == "confirmed")).all()
    return len(rows) >= capacity
