"""항목 판단 엔진 (COMPOSE_INTERVIEW_CONTRACT §10): 메뉴·시술·객실·수업 같은 "파는 것"을 어떻게 보여 줄지 먼저 판단한다.

"메뉴니까 메뉴판"으로 바로 그리지 않고, 카드 내용을 보고 아래를 이유와 함께 정한다.
  - kind: 항목 종류 (menu 메뉴 · service 시술·서비스 · room 객실 · class 수업 · program 활동 · plan 요금제)
  - fields: 카드에 보일 칸 (이름·가격·사진·설명·걸리는 시간·인원·시간표)
  - photo: 항목 사진이 필요한가 — each(항목마다) · signature(대표 몇 개만) · none(항목 사진 없음, 사진첩으로)
  - layout: 모양 — cards(옆으로 넘기는 사진 카드, 캐러셀) · categories(분류별 메뉴판) · list-price(이름·가격 목록)
            · rooms·classes(전용 카드 부품)
  - commerce: 손님 행동 — info(보기만) · inquire(문의) · book(예약·신청) · order(주문) · pay(주문+결제)
              ready: 지금 켤 수 있는지(가격이 다 있는지), missing: 무엇이 더 필요한지
  - reviews: 후기 자리를 둘지 (지금은 자리만, 주문·방문 뒤 쌓이면 보인다)
  - reasons: 사장님에게 보여 줄 판단 이유(한국어 한 줄씩)

순수 함수다(카드만 읽고 고치지 않는다). LLM을 쓰지 않는다 — 같은 카드면 늘 같은 판단.
"""
from typing import Optional

from app.services import card_data as CD
from app.services import prd_engine as E

KIND_BY_INDUSTRY = {"cafe": "menu", "restaurant": "menu", "salon": "service", "pension": "room",
                    "academy": "class", "workshop": "class", "individual": "service", "group": "program",
                    "webservice": "plan", "event": "program", "other": "menu"}
NOUN = {"menu": "메뉴", "service": "시술·서비스", "room": "객실", "class": "수업", "program": "활동",
        "plan": "요금제"}
FIELDS = {"menu": ("name", "price", "photo", "desc"),
          "service": ("name", "price", "duration", "desc"),
          "room": ("name", "photo", "capacity", "price"),
          "class": ("name", "schedule", "price", "desc"),
          "program": ("name", "schedule", "desc"),
          "plan": ("name", "price", "desc")}
COMMERCE_LEVELS = ("info", "inquire", "book", "order", "pay")
COMMERCE_LABEL = {"info": "보기만", "inquire": "문의", "book": "예약·신청", "order": "주문", "pay": "주문+결제"}
# 항목 카드 행동 단추 (나중에 주문·결제·후기를 붙이는 자리)
ACTION = {"order": ("order", "주문하기"), "pay": ("order", "주문하기"), "book": ("book", "예약하기"),
          "inquire": ("inquire", "문의하기")}

CAROUSEL_MAX = 8      # 이보다 많으면 넘기기 카드가 지루해진다 → 분류별 메뉴판
SIGNATURE_COUNT = 3   # 항목이 많을 때 사진은 대표 몇 개만
_ORDER_WORDS = ("주문", "포장", "픽업", "배달", "테이크아웃", "택배", "배송")
_PAY_WORDS = ("결제", "선결제", "카드 결제", "카드결제", "계좌", "입금")
_BOOK_WORDS = ("예약", "신청", "접수")


def _items(card: dict) -> list:
    vals = (E._slot(card, "offerings") or {}).get("value")
    if isinstance(vals, list):
        return [str(v) for v in vals if str(v).strip()]
    return [str(vals)] if isinstance(vals, str) and vals.strip() else []


def _said(card: dict) -> str:
    parts = [str(x) for x in card.get("said") or []]
    for key in ("features", "contact_method", "sections", "goal", "order_mode"):
        v = (E._slot(card, key) or {}).get("value")
        parts.append(", ".join(map(str, v)) if isinstance(v, list) else str(v or ""))
    hidden = (card.get("hidden") or {}).get("selected") or []
    if "takeout" in hidden:
        parts.append("포장")
    return " ".join(parts)


def kind_of(card: dict) -> str:
    return KIND_BY_INDUSTRY.get(E.industry_of(card).key, "menu")


def _owner_item_photos(card: dict, items: list) -> int:
    n = 0
    for name in items:
        try:
            if CD.item_photo(card, name):
                n += 1
        except Exception:
            pass
    return n


def decide(card: dict) -> dict:
    """카드 → 항목 판단. reasons는 사장님에게 그대로 보여 줄 문장."""
    kind = kind_of(card)
    noun = NOUN[kind]
    items = _items(card)
    count = len(items)
    pairs = card.get("price_pairs") or {}
    priced = [n for n in items if CD.price_won(pairs.get(n, "")) or CD.price_won(n)]
    missing_price = [n for n in items if n not in priced]
    groups = len(CD._catalog(card, E.industry_of(card).key)) if count else 0
    own_photos = _owner_item_photos(card, items)
    reasons: list = []

    # ── 사진: 정말 항목마다 사진이 필요한가 ──
    if own_photos:
        photo = "each"
        reasons.append(f"올려 주신 {noun} 사진이 있어 항목마다 사진을 보여 드려요.")
    elif kind == "menu":
        if count and count > CAROUSEL_MAX:
            photo = "signature"
            reasons.append(f"{noun}가 {count}개로 많아서, 사진은 대표 {SIGNATURE_COUNT}개만 크게 보이고 나머지는 이름·가격으로 정리해요.")
        else:
            photo = "each"
            reasons.append("음식·음료는 사진을 보고 고르는 경우가 많아 항목마다 사진을 둬요.")
    elif kind == "room":
        photo = "each"
        reasons.append("객실은 사진으로 비교해서 고르니 객실마다 사진이 꼭 필요해요.")
    elif kind == "class" and E.industry_of(card).key == "workshop":
        photo = "each"
        reasons.append("공방 수업은 완성 작품 사진이 신청을 부르니 수업마다 사진을 둬요.")
    else:
        photo = "none"
        if kind == "service":
            reasons.append("시술은 항목 사진보다 스타일 사진첩이 손님에게 더 도움이 돼서, 항목은 이름·가격·시간만 깔끔하게 보여요.")
        elif kind == "class":
            reasons.append("학원 수업은 사진보다 대상·시간·수강료가 중요해서 글로 정리해요.")
        else:
            reasons.append(f"{E._josa(noun, '은는')} 사진 없이 글로 정리하는 편이 읽기 쉬워요.")

    # ── 모양: 캐러셀 카드 / 메뉴판 / 목록 / 전용 카드 ──
    if kind == "room":
        layout = "rooms"
    elif kind == "class" and E.industry_of(card).key in ("academy", "workshop"):
        layout = "classes"
    elif photo == "each" and (not count or count <= CAROUSEL_MAX):
        layout = "cards"
        if count:
            reasons.append(f"{noun} {count}개를 사진 카드로 옆으로 넘겨 보게(캐러셀) 할게요.")
    elif photo == "signature" or groups >= 3:
        layout = "categories"
        if groups >= 2:
            reasons.append(f"종류가 {groups}가지라 분류별 메뉴판으로 나눠 보여요.")
        else:
            reasons.append(f"{noun}가 많아서 한 장짜리 메뉴판으로 정리해요.")
    else:
        layout = "list-price"
        if count:
            reasons.append(f"{noun} {count}개를 이름·가격 목록으로 한눈에 보여요.")

    # ── 손님 행동: 보기만 / 문의 / 예약 / 주문 / 결제 ──
    said = _said(card)
    explicit = card.get("commerce") if card.get("commerce") in COMMERCE_LEVELS else None
    inferred = None
    if any(w in said for w in _PAY_WORDS):
        inferred = "pay"
    elif any(w in said for w in _ORDER_WORDS) and kind in ("menu", "plan"):
        inferred = "order"
    elif kind in ("room", "service", "class") or any(w in said for w in _BOOK_WORDS):
        inferred = "book"
    level = explicit or inferred or ("info" if kind == "menu" else "inquire")
    ask_commerce = explicit is None and kind in ("menu", "plan") and inferred is None
    missing = []
    if level in ("order", "pay") and missing_price:
        missing.append("price")
    ready = not missing
    if level in ("order", "pay"):
        line = f"손님이 {noun}를 골라 바로 주문할 수 있게 카드마다 '주문하기' 단추를 둬요."
        if level == "pay":
            line += " 결제는 가게 설정에서 결제를 켜면 바로 이어져요."
        reasons.append(line)
        if missing_price:
            reasons.append(f"가격이 없는 {noun} {len(missing_price)}개는 가격을 넣으면 주문 단추가 켜져요.")
    elif level == "book":
        reasons.append(f"{noun}마다 '예약하기' 단추를 둬서 바로 예약·신청으로 이어지게 해요.")
    elif level == "inquire":
        reasons.append(f"{noun}마다 '문의하기' 단추를 둬요.")
    elif count:
        reasons.append(f"지금은 {noun}와 가격만 보여 드려요. 나중에 주문을 켜도 같은 카드에 단추만 붙어요.")

    # ── 후기 자리 ──
    reviews = kind in ("menu", "service", "room", "class")
    if reviews:
        reasons.append("후기 자리를 미리 만들어 두면 주문·방문 뒤 후기가 쌓일 때 바로 보여요.")

    return {
        "kind": kind, "noun": noun, "count": count, "groups": groups,
        "fields": list(FIELDS[kind]),
        "photo": photo, "layout": layout,
        "commerce": {"level": level, "label": COMMERCE_LABEL[level], "explicit": explicit is not None,
                     "ask": ask_commerce, "ready": ready, "missing": missing,
                     "missing_price": missing_price},
        "reviews": reviews,
        "reasons": reasons,
    }


def item_action(card: dict) -> Optional[dict]:
    """항목 카드 행동 단추. 사장님이 실시간 대화에서 손님 행동을 정했을 때만(기존 시안은 그대로)."""
    level = card.get("commerce")
    if level not in ACTION:
        return None
    kind, label = ACTION[level]
    return {"kind": kind, "label": label}


def commerce_options(card: dict) -> list:
    """손님 행동 질문의 선택지 (항목 종류에 맞게, 첫 번째가 추천)."""
    kind = kind_of(card)
    noun = NOUN[kind]
    if kind in ("menu", "plan"):
        return [("info", f"{noun}·가격만 보여 주기", ("보여", "안내", "가격만", "보기만", "그냥"),
                 "손님은 보고 가게로 와요. 나중에 주문을 켜도 같은 카드에 단추만 붙어요."),
                ("order", "주문 받기 (포장·픽업)", ("주문", "포장", "픽업", "테이크아웃"),
                 f"{noun} 카드마다 '주문하기' 단추. 주문이 오면 알려 드려요."),
                ("pay", "주문하고 바로 결제", ("결제", "카드", "선결제"),
                 "주문할 때 결제까지 받아요. 가게 설정에서 결제를 켜야 해요."),
                ("book", "예약 받기", ("예약", "자리"), "자리·시간 예약을 받아요.")]
    return [("book", "예약·신청 받기", ("예약", "신청", "접수"), f"{noun}마다 '예약하기' 단추를 둬요."),
            ("inquire", "문의만 받기", ("문의", "연락", "전화"), f"{noun}마다 '문의하기' 단추를 둬요."),
            ("info", "보기만", ("보기만", "안내만", "그냥"), "단추 없이 정보만 보여요.")]
