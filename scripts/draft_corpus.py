"""중간 시안 품질 루프용 입력 코퍼스 12건 (로컬 고정, LLM·DB 불필요).

각 케이스는 new_card()+_put() 규칙 조립만으로 카드를 만든다.
NIM·채팅·사진 파일을 쓰지 않는다. 사진 있는 케이스는 URL 문자열만 넣는다.
사용법: .venv/bin/python scripts/draft_lab.py --list
"""
from app.services import prd_engine as E
from app.services import prd_schema as S

CASES = [
    {"id": "cafe-talkative", "industry": "cafe", "photo": False,
     "slots": {"business_type": "카페", "shop_name": "마포 느린오후",
               "offerings": ["아메리카노", "카페라떼", "바스크치즈케이크"],
               "phone": "02-123-4567", "hours": "매일 10~21시",
               "location": "서울 마포구 연남로 12", "detail": "창가 자리가 넓은 조용한 카페예요."}},
    {"id": "cafe-owner-photo", "industry": "cafe", "photo": True,
     "slots": {"business_type": "카페", "shop_name": "마포 느린오후",
               "offerings": ["아메리카노", "카페라떼"],
               "phone": "02-123-4567", "hours": "매일 10~21시",
               "detail": "창가 자리가 넓은 조용한 카페예요."}},
    {"id": "restaurant-terse", "industry": "restaurant", "photo": False,
     "slots": {"business_type": "식당", "shop_name": "황남밥상",
               "offerings": ["김치찌개", "된장찌개"]}},
    {"id": "restaurant-changes", "industry": "restaurant", "photo": False,
     "slots": {"business_type": "식당", "shop_name": "황남밥상",
               "offerings": ["김치찌개", "제육볶음", "계란말이"],
               "hours": "평일 11~20시", "detail": "반찬을 직접 담그는 집밥 식당이에요."}},
    {"id": "salon-no-photo", "industry": "salon", "photo": False,
     "slots": {"business_type": "미용실", "shop_name": "단정손끝",
               "offerings": ["컷", "염색", "펌"], "hours": "10~19시, 월요일 휴무"}},
    {"id": "salon-photo", "industry": "salon", "photo": True,
     "slots": {"business_type": "미용실", "shop_name": "단정손끝",
               "offerings": ["컷", "염색"], "phone": "010-1111-2222"}},
    {"id": "academy-talkative", "industry": "academy", "photo": False,
     "slots": {"business_type": "영어 학원", "shop_name": "믿음영어",
               "offerings": ["초등 파닉스반", "중등 내신반", "고등 수능반"],
               "hours": "평일 14~22시", "location": "서울 노원구 상계로 77",
               "contact_method": "사이트에서 상담 신청",
               "detail": "반 정원이 8명인 동네 영어 학원이에요."}},
    {"id": "pension-family", "industry": "pension", "photo": False,
     "slots": {"business_type": "펜션", "shop_name": "숲속의 쉼",
               "offerings": ["101호(복층)", "102호(온돌)", "바베큐장"],
               "hours": "입실 15시·퇴실 11시", "location": "강원 평창군 봉평면",
               "detail": "아이와 함께 오기 좋은 조용한 펜션이에요."}},
    {"id": "cello-lesson", "industry": "individual", "photo": False,
     "slots": {"business_type": "첼로 레슨", "shop_name": "하늘첼로",
               "offerings": ["성인 취미반", "입시반"],
               "hours": "화·목 18~21시", "detail": "처음 만나는 첼로가 평생의 취미가 되도록 가르쳐요."}},
    {"id": "group-workshop", "industry": "group", "photo": True,
     "slots": {"business_type": "도예 모임", "shop_name": "흙손모임",
               "offerings": ["주말 원데이클래스", "4주 정규반"],
               "detail": "손으로 만드는 시간을 함께하는 모임이에요."}},
    {"id": "webservice-tool", "industry": "webservice", "photo": False,
     "slots": {"business_type": "예약 관리 웹서비스", "shop_name": "예약잇기",
               "offerings": ["문자 알림", "노쇼 관리"],
               "detail": "작은 가게의 예약을 대신 받아주는 서비스예요."}},
    {"id": "other-minimal", "industry": "other", "photo": False,
     "slots": {"business_type": "동네 가게"}},
]


def build_card(case: dict) -> dict:
    """케이스 → 카드. 사실 슬롯은 FILLED, 사진은 URL 문자열만."""
    card = E.new_card(case["industry"])
    for key, value in case["slots"].items():
        E._put(card, key, value, S.FILLED, 1)
    # 가격 짝 (실제 대화 경로와 같게: price 칸 값을 넣은 뒤 짝을 기록한다).
    price = case["slots"].get("price")
    if price:
        E._record_price_pairs(card, [{"slot": "price", "value": price}], price)
    card["turn"] = 1
    if case.get("photo"):
        rid = "lab-" + case["id"]
        card["photos"] = [
            {"id": "p1", "url": f"/uploads/{rid}/p1.jpg", "caption": "대표 사진"},
            {"id": "p2", "url": f"/uploads/{rid}/p2.jpg", "caption": "내부 사진"},
        ]
    return card



def get(case_id: str) -> dict:
    for c in CASES:
        if c["id"] == case_id:
            return c
    raise KeyError(case_id)


# 적합성 채점(scripts/draft_fit.py)용 케이스 (DESIGN_FIT_PLAN §5).
# 가격·디자이너·분류·주소가 들어 있고, expect에 시안에 반드시 보여야 할 것을 적는다.
# mode·categories는 1단계(상황 탐색)가 카드에 넣을 값이다. 그 전에는 채점기만 읽는다.
FIT_CASES = [
    {"id": "fit-cafe-dinein", "industry": "cafe", "photo": False, "mode": "dinein",
     "slots": {"business_type": "카페", "shop_name": "연남 느린오후",
               "offerings": ["아메리카노", "카페라떼", "딸기라떼", "유자에이드", "바스크치즈케이크", "휘낭시에"],
               "price": "아메리카노 4,500원, 카페라떼 5,000원, 바스크치즈케이크 6,500원",
               "phone": "02-123-4567", "hours": "매일 10~21시", "location": "서울 마포구 연남로 12",
               "detail": "창가 자리가 넓은 조용한 카페예요."},
     "expect": {"action": ("길찾기", "오시는 길"), "action_sections": ("around",),
                "categories": ("커피", "음료", "디저트"),
                "pairs": (("아메리카노", "4,500원"), ("카페라떼", "5,000원"), ("바스크치즈케이크", "6,500원")),
                "staff": (), "staff_mode": ""}},
    {"id": "fit-cafe-pickup", "industry": "cafe", "photo": False, "mode": "pickup",
     "slots": {"business_type": "카페", "shop_name": "연남 느린오후",
               "offerings": ["아메리카노", "카페라떼", "바스크치즈케이크"],
               "price": "아메리카노 4,500원, 카페라떼 5,000원, 바스크치즈케이크 6,500원",
               "phone": "02-123-4567", "hours": "매일 10~21시", "location": "서울 마포구 연남로 12",
               "contact_method": "픽업 주문"},
     "expect": {"action": ("주문",), "action_sections": ("offerings",),
                "categories": ("커피", "디저트"),
                "pairs": (("아메리카노", "4,500원"), ("바스크치즈케이크", "6,500원")),
                "staff": (), "staff_mode": ""}},
    {"id": "fit-salon-solo", "industry": "salon", "photo": False, "mode": "solo",
     "slots": {"business_type": "미용실", "shop_name": "단정손끝",
               "offerings": ["컷", "펌", "클리닉"], "price": "컷 2만원, 펌 8만원",
               "staff": ["원장 김단정(컷·펌)"], "hours": "10~19시, 월요일 휴무",
               "location": "서울 마포구 성미산로 21"},
     "expect": {"action": ("예약",), "action_sections": ("booking",), "categories": (),
                "pairs": (("컷", "2만원"), ("펌", "8만원")),
                "staff": ("김단정",), "staff_mode": "solo"}},
    {"id": "fit-salon-team", "industry": "salon", "photo": False, "mode": "team",
     "slots": {"business_type": "미용실", "shop_name": "살롱 드 연남",
               "offerings": ["컷", "염색", "펌"], "price": "컷 2만5천원, 염색 9만원, 펌 12만원",
               "staff": ["원장 김미용(컷)", "실장 박하나(염색)", "디자이너 이서준(펌)"],
               "phone": "02-333-4444", "hours": "10~20시", "location": "서울 마포구 동교로 30"},
     "expect": {"action": ("예약",), "action_sections": ("booking", "staff"), "categories": (),
                "pairs": (("컷", "2만5천원"), ("염색", "9만원"), ("펌", "12만원")),
                "staff": ("김미용", "박하나", "이서준"), "staff_mode": "team"}},
    {"id": "fit-pension", "industry": "pension", "photo": False, "mode": "",
     "slots": {"business_type": "펜션", "shop_name": "숲속의 쉼",
               "offerings": ["101호 복층", "102호 온돌"], "price": "101호 복층 18만원, 102호 온돌 12만원",
               "hours": "입실 15시·퇴실 11시", "location": "강원 평창군 봉평면 무이로 45",
               "phone": "033-000-1111"},
     "expect": {"action": ("예약",), "action_sections": ("booking", "offerings"), "categories": (),
                "pairs": (("101호 복층", "18만원"), ("102호 온돌", "12만원")),
                "staff": (), "staff_mode": ""}},
    {"id": "fit-academy", "industry": "academy", "photo": False, "mode": "",
     "slots": {"business_type": "영어 학원", "shop_name": "믿음영어",
               "offerings": ["초등 파닉스반", "중등 내신반"],
               "price": "초등 파닉스반 월 18만원, 중등 내신반 월 24만원",
               "staff": ["김믿음 원장(초등)"], "target": "초등·중학생",
               "location": "서울 노원구 상계로 77", "phone": "02-777-8888"},
     "expect": {"action": ("상담",), "action_sections": ("booking", "contact"), "categories": (),
                "pairs": (("초등 파닉스반", "월 18만원"), ("중등 내신반", "월 24만원")),
                "staff": ("김믿음",), "staff_mode": "solo"}},
]
