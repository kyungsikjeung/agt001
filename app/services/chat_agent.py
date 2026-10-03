"""손님 예약 채팅 (BOOKING_BOT_IMPL_PLAN CH-1~CH-7, AI_BOOKING_AGENT_PLAN §2).

- 버튼(action)은 AI를 거치지 않는다. 자유 문장은 규칙으로 먼저 읽고, 못 읽으면 사장님께 넘긴다.
- 시각은 booking_engine.available이 돌려준 것만 버튼으로 보인다(CH-4). 답 글에 시각을 지어 넣지 않는다.
- 조회·변경·취소는 이 브라우저 토큰으로 만든 예약만(CH-5).
- 대화 초안은 agent_threads에 둔다. 30분 지나면 버린다(CH-6).
"""
import datetime
import hashlib
import logging
import re
from typing import Optional

from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.db.models import AgentThreadRow
from app.db.session import get_sessionmaker
from app.services import booking_engine as E
from app.services import booking_spec as S
from app.services import customers
from app.services.slots import KST

log = logging.getLogger(__name__)

IDLE = datetime.timedelta(minutes=30)
KEEP_DAYS = 7
_KO = "월화수목금토일"
MENU = [{"label": "예약하기", "action": "book"}, {"label": "내 예약 보기·바꾸기", "action": "mine"},
        {"label": "문의하기", "action": "ask"}]
_PHONE = re.compile(r"01[016789][-\s.]?\d{3,4}[-\s.]?\d{4}")


def token_hash(token: Optional[str]) -> Optional[str]:
    return hashlib.sha256(token.encode()).hexdigest() if token else None


def _now() -> datetime.datetime:
    return datetime.datetime.now(KST)


# ── 상태 ──

def _load(th: str, shop_id: str, now: datetime.datetime) -> dict:
    with get_sessionmaker()() as db:
        row = db.get(AgentThreadRow, th)
        if row is None or row.shop_id != shop_id or row.updated_at < now - IDLE:
            return {}
        return dict(row.draft or {})


def _save(th: str, shop_id: str, draft: dict, now: datetime.datetime) -> None:
    stmt = pg_insert(AgentThreadRow).values(token_hash=th, shop_id=shop_id, draft=draft, updated_at=now)
    with get_sessionmaker()() as db, db.begin():
        db.execute(stmt.on_conflict_do_update(index_elements=["token_hash"],
                                              set_={"shop_id": shop_id, "draft": draft, "updated_at": now}))


def purge(now: Optional[datetime.datetime] = None) -> int:
    from sqlalchemy import delete
    cutoff = (now or _now()) - datetime.timedelta(days=KEEP_DAYS)
    with get_sessionmaker()() as db, db.begin():
        return db.execute(delete(AgentThreadRow).where(AgentThreadRow.updated_at < cutoff)).rowcount


# ── 읽기 (규칙) ──

def parse_date(text: str, today: datetime.date) -> Optional[datetime.date]:
    t = re.sub(r"\s+", "", text or "")
    if "모레" in t:
        return today + datetime.timedelta(days=2)
    if "내일" in t:
        return today + datetime.timedelta(days=1)
    if "오늘" in t:
        return today
    m = re.search(r"(\d{1,2})[/월.](\d{1,2})일?", t)
    if m:
        try:
            d = datetime.date(today.year, int(m.group(1)), int(m.group(2)))
        except ValueError:
            return None
        return d if d >= today else d.replace(year=today.year + 1)
    m = re.search(r"(다음주|담주)?([월화수목금토일])요일", t)
    if m:
        ahead = (_KO.index(m.group(2)) - today.weekday()) % 7 or 7
        if m.group(1) and ahead < 7:
            ahead += 7 if today.weekday() <= _KO.index(m.group(2)) else 0
        return today + datetime.timedelta(days=ahead)
    return None


def parse_time(text: str) -> Optional[str]:
    t = re.sub(r"\s+", "", text or "")
    m = re.search(r"(\d{1,2}):(\d{2})", t)
    if m:
        return f"{int(m.group(1)):02d}:{m.group(2)}"
    m = re.search(r"(오전|오후|저녁|밤)?(\d{1,2})시(반|30분)?", t)
    if not m:
        return None
    h = int(m.group(2))
    if (m.group(1) in ("오후", "저녁", "밤") or (not m.group(1) and 1 <= h <= 8)) and h < 12:
        h += 12
    return f"{h:02d}:{'30' if m.group(3) else '00'}"


def parse_party(text: str) -> Optional[int]:
    t = re.sub(r"\s+", "", text or "")
    if "혼자" in t:
        return 1
    words = {"둘": 2, "두": 2, "셋": 3, "세": 3, "넷": 4, "네": 4, "다섯": 5, "여섯": 6}
    m = re.search(r"(\d{1,2})(?:명|인)", t)
    if m:
        return int(m.group(1))
    for w, n in words.items():
        if re.search(w + r"(?:명|이서|이요)", t):
            return n
    return None


def intent_of(text: str) -> str:
    t = re.sub(r"\s+", "", text or "")
    if "취소" in t:
        return "cancel"
    if re.search(r"변경|바꾸|바꿀|옮기", t):
        return "change"
    if re.search(r"내예약|예약확인|예약조회|확인해", t):
        return "mine"
    if re.search(r"주차|얼마|가격|어디|위치|주소|전화|번호|반려|강아지|아이|유아|와이파이", t):
        return "ask"  # "주차 돼요?"는 예약이 아니라 문의
    if re.search(r"예약|자리|되나요|돼요|가능|잡아", t):
        return "book"
    return "ask"


# ── 답 모양 ──

def _r(text: str, buttons=None, **extra) -> dict:
    return {"reply": text, "buttons": buttons or [], **extra}


def _label(d: datetime.date) -> str:
    return f"{d.month}/{d.day}({_KO[d.weekday()]})"


def _card(site_key: str) -> dict:
    from app.services import availability
    return availability._card_for_site(site_key) or {}


def _slot_value(card: dict, key: str) -> str:
    slot = (card.get("slots") or {}).get(key) or {}
    if slot.get("status") not in ("filled", "assumed"):
        return ""
    v = slot.get("value")
    return ", ".join(map(str, v)) if isinstance(v, list) else str(v or "")


def _shop_phone(card: dict) -> str:
    return _slot_value(card, "phone")


def _call_line(card: dict) -> str:
    phone = _shop_phone(card)
    return f"가게로 전화 주세요: {phone}" if phone else "가게로 직접 연락해 주세요."


# ── 흐름 ──

OWNER_BTN = {"label": "사장님께 직접 물어보기", "action": "owner"}


def respond(site_key: str, token: Optional[str], *, text: Optional[str] = None, action: Optional[str] = None,
            now: Optional[datetime.datetime] = None) -> dict:
    from app.services import guest_chat, takedown
    if takedown.is_down(site_key):  # 관리자가 내린 사이트는 예약 봇도 답하지 않는다 (P2-4)
        return _r("지금은 이용할 수 없는 가게예요.")
    now = now or _now()
    got = E.active_spec(site_key)
    card = _card(site_key)
    name = _slot_value(card, "shop_name") or "가게"
    th = token_hash(token)
    said = (text or "").strip()
    open_chat = guest_chat.enabled(site_key)  # 공개된 가게 + 손님 채팅 켜짐 (GUEST_CHAT_CONTRACT)
    if got is None and not open_chat:
        return _r(f"{name}은(는) 아직 채팅 예약을 받지 않아요. {_call_line(card)}")
    if open_chat and th:
        state = guest_chat.status(site_key, th)
        if state in guest_chat.CLOSED_STATES and (said or action == "owner"):
            return _r(f"지금은 이 대화에 글을 보낼 수 없어요. {_call_line(card)}")
        if action == "owner":
            guest_chat.to_owner(site_key, th)
            hours = _slot_value(card, "hours")
            return _r("무엇이든 적어 주세요. 사장님이 확인하면 여기로 답해요"
                      + (f" · 영업시간 {hours}" if hours else "") + ".", mode="owner")
        if state == guest_chat.TO_OWNER and said and not action:
            # 사장님 대기: AI를 거치지 않고 저장. 연달아 보내면 두 번째부터는 답하지 않는다.
            first = guest_chat.last_sender(site_key, th) != "guest"
            reply = "사장님께 전했어요. 답이 오면 여기에 보여요." if first else ""
            guest_chat.log_turn(site_key, th, said, "", to_owner=True)  # 접수 안내는 대화 기록에 넣지 않는다
            return _r(reply, mode="owner")
    if got is None:
        out = _no_bot_step(site_key, card, name, said, action)
    else:
        shop_id, spec = got
        draft = _load(th, shop_id, now) if th else {}
        try:
            out = _step(site_key, spec, card, name, draft, th, said, action, now)
        except E.EngineError as e:
            out = _r(str(e), [{"label": "처음으로", "action": "menu"}])
        if th:
            _save(th, shop_id, draft, now)
    to_owner = bool(out.pop("to_owner", False))
    if open_chat:
        if th and said:
            guest_chat.log_turn(site_key, th, said, out.get("reply") or "", to_owner=to_owner)
        if out.get("buttons") and OWNER_BTN not in out["buttons"] and any(
                b.get("action") == "ask" for b in out["buttons"]):
            out["buttons"] = [*out["buttons"], OWNER_BTN]
        if to_owner:
            out["mode"] = "owner"
    return out


def _no_bot_step(site_key: str, card: dict, shop_name: str, text: str, action: Optional[str]) -> dict:
    """예약 봇이 없는 공개 가게: 가게 정보로 답하고, 모르면 사장님께. 예약은 전화로 안내."""
    buttons = [{"label": "문의하기", "action": "ask"}, OWNER_BTN]
    if action == "ask":
        return _r("궁금한 것을 적어 주세요. 가게 정보로 바로 답하고, 모르면 사장님께 전해 드려요.")
    if not text or action in ("menu", "book", "mine") or action:
        return _r(f"안녕하세요, {shop_name}입니다. 무엇이 궁금하세요?", buttons)
    if intent_of(text) in ("book", "mine", "change", "cancel"):
        return _r(f"채팅 예약은 아직 받지 않아요. {_call_line(card)}", [OWNER_BTN])
    out = _answer(site_key, card, text)
    if out.get("buttons") == MENU:
        out["buttons"] = buttons  # 예약 봇이 없으니 예약 단추 대신 문의·사장님
    return out


def _step(site_key, spec, card, shop_name, draft, th, text, action, now) -> dict:
    today = now.date()
    if action in (None, "") and not text or action == "menu":
        draft.clear()
        return _r(f"안녕하세요, {shop_name}입니다. 무엇을 도와드릴까요?", MENU)
    if action == "book":
        draft.clear()
        draft["flow"] = "book"
    elif action == "mine":
        draft.clear()
        return _mine(site_key, card, th, now)
    elif action == "ask":
        draft.clear()
        draft["flow"] = "ask"
        return _r("궁금한 것을 적어 주세요. 사장님께 바로 전해 드릴게요.")
    elif action and action.startswith(("cancel:", "change:", "cancel_ok:")):
        return _manage(site_key, spec, card, draft, th, action, now)
    elif not action and text and not draft.get("flow"):
        intent = intent_of(text)
        if intent in ("mine", "change", "cancel"):
            return _mine(site_key, card, th, now)
        if intent == "ask":
            return _answer(site_key, card, text)
        draft["flow"] = "book"
    if draft.get("flow") == "ask" and text:
        draft.clear()
        return _answer(site_key, card, text, force_owner=True)
    if draft.get("flow") in ("book", "change"):
        return _book(site_key, spec, card, draft, th, text, action, now, today)
    return _r(f"안녕하세요, {shop_name}입니다. 무엇을 도와드릴까요?", MENU)


def _book(site_key, spec, card, draft, th, text, action, now, today) -> dict:
    mode = spec.get("mode")
    pol = S.policy(spec)
    # 버튼으로 온 값
    if action:
        kind, _, value = action.partition(":")
        if kind == "svc":
            draft["service"] = value
        elif kind == "staff":
            draft["staff"] = value or None
            draft["staff_asked"] = True
        elif kind == "party":
            draft["party"] = int(value)
        elif kind == "date":
            draft["date"] = value
            draft.pop("time", None)
        elif kind == "time":
            draft["time"] = value
        elif kind == "confirm":
            return _confirm(site_key, card, draft, th, now)
        elif kind == "restart":
            flow = draft.get("flow")
            draft.clear()
            draft["flow"] = flow or "book"
    # 글로 온 값 (한 문장에 여러 개가 있어도 읽는다)
    if text:
        for s in spec.get("services") or []:
            if s["name"] in text:
                draft["service"] = s["name"]
        for r in S.staff(spec):
            if r["name"] in text:
                draft["staff"], draft["staff_asked"] = r["name"], True
        d = parse_date(text, today)
        if d:
            draft["date"] = d.isoformat()
        p = parse_party(text)
        if p:
            draft["party"] = p
        tm = parse_time(text)
        if tm:
            draft["want_time"] = tm
        if draft.get("hold_id") and (_PHONE.search(text) or draft.get("need_contact")):
            return _contact(site_key, card, draft, th, text, now)
    # 빠진 것을 하나씩
    if draft["flow"] == "book" and mode == "slot" and not draft.get("service"):
        return _r("어떤 시술을 예약하실까요?",
                  [{"label": s["name"], "action": f"svc:{s['name']}"} for s in spec.get("services") or []])
    if draft["flow"] == "book" and mode == "slot" and not draft.get("staff_asked"):
        svc = S.service(spec, draft["service"])
        people = S.capable(spec, svc) if svc else []
        if len(people) >= 2:
            return _r("담당 선생님을 고르실래요?",
                      [{"label": r["name"], "action": f"staff:{r['name']}"} for r in people]
                      + [{"label": "상관없음", "action": "staff:"}])
        draft["staff_asked"] = True
    if draft["flow"] == "book" and mode == "table" and not draft.get("party"):
        return _r("몇 분이 오세요?", [{"label": f"{n}명", "action": f"party:{n}"} for n in range(1, 7)])
    if mode == "table" and int(draft.get("party") or 1) > int(pol["party_max"]):
        n = draft.pop("party")
        return _r(f"{n}명 단체는 채팅으로 받지 않아요. {_call_line(card)}", [{"label": "처음으로", "action": "menu"}])
    kw = {"service": draft.get("service"), "staff": draft.get("staff"), "party": int(draft.get("party") or 1)}
    if not draft.get("date"):
        days = E.next_days(site_key, today, count=5, now=now, **kw)
        if not days:
            return _r(f"가까운 날에는 예약 가능한 시간이 없어요. {_call_line(card)}")
        return _r("언제 오실까요?", [{"label": _label(d["date"]), "action": f"date:{d['date'].isoformat()}"}
                                     for d in days])
    day = datetime.date.fromisoformat(draft["date"])
    if not draft.get("time"):
        found = E.available(site_key, day, now=now, **kw)
        want = draft.pop("want_time", None)
        if want and any(f["time"] == want for f in found):
            draft["time"] = want
        elif not found:
            draft.pop("date", None)
            days = E.next_days(site_key, day + datetime.timedelta(days=1), count=3, now=now, **kw)
            return _r(f"{_label(day)}에는 가능한 시간이 없어요." + (" 이날은 어떠세요?" if days else f" {_call_line(card)}"),
                      [{"label": _label(d["date"]), "action": f"date:{d['date'].isoformat()}"} for d in days])
        else:
            head = f"{_label(day)} {want}은(는) 어려워요. " if want else ""
            return _r(head + f"{_label(day)}에 가능한 시간이에요.",
                      [{"label": f["time"], "action": f"time:{f['time']}"} for f in found[:24]]
                      + [{"label": "다른 날", "action": "date:"}])
    if draft["flow"] == "change":
        new = E.change(site_key, int(draft["booking_id"]), th, day, draft["time"], staff=draft.get("staff"), now=now)
        draft.clear()
        word = "바꿨어요" if new["status"] == "confirmed" else "바꿔서 다시 신청했어요. 사장님이 확인하면 알려 드릴게요"
        return _r(f"{_label(day)} {new['time']}(으)로 {word}.", MENU)
    if not draft.get("hold_id"):
        draft["hold_id"] = E.hold(site_key, day, draft["time"], token_hash=th, now=now, **kw)
    draft["need_contact"] = True
    return _r(f"{_label(day)} {draft['time']} 자리를 10분 동안 잡아 뒀어요. 이름과 연락받을 번호를 알려 주세요. "
              "예: 김민지 010-1234-5678")


def _contact(site_key, card, draft, th, text, now) -> dict:
    m = _PHONE.search(text)
    if not m or not customers.normalize_phone(m.group(0)):
        return _r("연락받을 휴대폰 번호를 적어 주세요. 예: 김민지 010-1234-5678")
    draft["phone"] = m.group(0)
    rest = (text[:m.start()] + text[m.end():]).strip(" ,/")
    draft["name"] = rest[:20] or None
    day = datetime.date.fromisoformat(draft["date"])
    what = " · ".join(v for v in (draft.get("service"), draft.get("staff")) if v)
    party = f" {draft['party']}명" if draft.get("party") else ""
    masked = draft["phone"][:3] + "-****-" + re.sub(r"\D", "", draft["phone"])[-4:]
    return _r(f"{_label(day)} {draft['time']} {what}{party} · {draft['name'] or '이름 없음'} · {masked}\n맞으면 눌러 주세요.",
              [{"label": "예약 신청", "action": "confirm:"}, {"label": "처음부터", "action": "restart:"}])


def _confirm(site_key, card, draft, th, now) -> dict:
    if not draft.get("hold_id") or not draft.get("phone"):
        return _r("먼저 시간과 연락처를 알려 주세요.", [{"label": "예약하기", "action": "book"}])
    out = E.confirm_hold(site_key, int(draft["hold_id"]), th, name=draft.get("name"), phone=draft["phone"],
                         memo=None, now=now)
    draft.clear()
    if out["status"] == "confirmed":
        return _r("예약이 확정됐어요. 바꾸거나 취소하려면 '내 예약 보기'를 눌러 주세요.", MENU, booking=out)
    return _r("예약을 신청했어요. 사장님이 확인하면 연락드려요. 이 창에서 '내 예약 보기'로 확인할 수 있어요.", MENU,
              booking=out)


def _mine(site_key, card, th, now) -> dict:
    mine = E.my_bookings(site_key, th, now=now)
    if not mine:
        return _r(f"이 기기로 한 예약이 없어요. 다른 기기나 전화로 예약하셨다면 {_call_line(card)}", MENU)
    lines, buttons = [], []
    for b in mine:
        d = datetime.date.fromisoformat(b["date"])
        state = "확정" if b["status"] == "confirmed" else "확인 중"
        lines.append(f"· {_label(d)} {b['time']} {b['service'] or ''} ({state})")
        buttons += [{"label": f"{_label(d)} {b['time']} 바꾸기", "action": f"change:{b['id']}"},
                    {"label": f"{_label(d)} {b['time']} 취소", "action": f"cancel:{b['id']}"}]
    return _r("예약 내역이에요.\n" + "\n".join(lines), buttons + [{"label": "처음으로", "action": "menu"}])


def _manage(site_key, spec, card, draft, th, action, now) -> dict:
    kind, _, raw = action.partition(":")
    bid = int(raw) if raw.isdigit() else 0
    mine = {b["id"]: b for b in E.my_bookings(site_key, th, now=now)}
    if bid not in mine:
        return _r("예약을 찾을 수 없어요.", MENU)
    b = mine[bid]
    when = f"{_label(datetime.date.fromisoformat(b['date']))} {b['time']}"
    if kind == "cancel":
        return _r(f"{when} 예약을 취소할까요?", [{"label": "취소하기", "action": f"cancel_ok:{bid}"},
                                             {"label": "아니요", "action": "menu"}])
    if kind == "cancel_ok":
        E.cancel(site_key, bid, token_hash=th, now=now)
        draft.clear()
        return _r(f"{when} 예약을 취소했어요. 다음에 또 찾아 주세요.", MENU)
    pol = S.policy(spec)
    start = datetime.datetime.fromisoformat(b["start_at"])
    if now > start - datetime.timedelta(hours=int(pol["change_deadline_hours"])):
        return _r(f"방문 {pol['change_deadline_hours']}시간 전부터는 채팅으로 바꿀 수 없어요. {_call_line(card)}", MENU)
    svc, _, staff = (b["service"] or "").partition(" · ")
    draft.clear()
    draft.update({"flow": "change", "booking_id": bid, "service": svc or None, "staff": staff or None,
                  "staff_asked": True, "party": b["party"]})
    return _book(site_key, spec, card, draft, th, "", None, now, now.date())


def _answer(site_key, card, text, force_owner=False) -> dict:
    """가게 정보로 답할 수 있으면 답하고, 아니면 사장님께 넘긴다(지어내지 않음)."""
    t = re.sub(r"\s+", "", text)
    if not force_owner:
        facts = [(r"얼마|가격|비용", "price"), (r"어디|위치|주소|오시는", "location"),
                 (r"몇시|영업|언제|문열|닫", "hours"), (r"전화|번호|연락처", "phone")]
        for pattern, key in facts:
            if re.search(pattern, t):
                if key == "price":
                    pairs = card.get("price_pairs") or {}
                    hit = [f"{k} {v}" for k, v in pairs.items() if k in text]
                    if hit:
                        return _r(" / ".join(hit), MENU)
                    continue
                value = _slot_value(card, key)
                if value:
                    return _r(value, MENU)
    from app.services import guest_chat
    if guest_chat.enabled(site_key):
        # 손님 채팅이 켜진 가게: 대화를 사장님 대기로(알림은 guest_chat이 한 번 보낸다), 답은 이 창으로
        return _r("그건 사장님께 여쭤볼게요. 사장님이 확인하면 여기로 답해요.", MENU, to_owner=True)
    _ask_owner(site_key, text)
    return _r("그건 사장님께 여쭤볼게요. 전해 드렸어요. 답을 받으려면 연락처도 함께 남겨 주세요.", MENU)


def _ask_owner(site_key: str, text: str) -> None:
    room_id = E._room_for(site_key)
    if not room_id:
        return
    from app import store
    from app.services import rooms
    try:
        with store.room_tx(room_id) as (room, _session):
            if room is not None:
                rooms._append(room, "system", "손님 문의(채팅)", text[:300], kind="inquiry")
    except Exception:
        log.exception("채팅 문의 알림 실패 room=%s", room_id)
