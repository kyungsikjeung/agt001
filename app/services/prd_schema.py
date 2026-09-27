"""요구사항 카드의 칸 정의와 업종별 표 (REQUIREMENTS_ENGINE_PLAN.md §2, §7).

AI는 이 칸들을 채우기만 하고, 무엇을 물을지는 prd_engine의 규칙이 이 표를 보고 정한다.
칸을 늘릴 때는 시나리오(evals/scenarios)와 추출 테스트도 같이 늘린다.
"""
from dataclasses import dataclass, field

# 칸 상태
EMPTY = "empty"
FILLED = "filled"            # 사장님(참여자)이 말함
ASSUMED = "assumed"          # 기본값으로 채움("가정")
PLACEHOLDER = "placeholder"  # 사실 칸인데 모름 → 시안·사이트에 자리 표시, 공개 전 필수(D23)
PENDING_OWNER = "pending_owner"  # 공유방에서 방장 아닌 사람이 말한 사실 → 방장 확인 대기(D24)
REJECTED = "rejected"        # "필요 없어요" → 다시 묻지 않음

MAX_QUESTIONS = 8  # D20
MAX_OPTIONS = 3    # 선택지 3개 + "알아서 해주세요" = 4개 이하 (조사 #9)
LET_AI = "알아서 해주세요"


@dataclass(frozen=True)
class Slot:
    key: str
    label: str
    describe: str          # 추출 프롬프트에 들어가는 한 줄 정의(예·반례 포함)
    fact: bool = False     # 전화·주소·가격·영업시간처럼 지어내면 안 되는 사실
    multi: bool = False    # 값이 여러 개인 칸


SLOTS: dict[str, Slot] = {s.key: s for s in [
    Slot("business_type", "업종", "하는 일·업종·다루는 분야. 가게가 아니어도 된다. 예: 펜션, 카페, 한식당, 미용실, 도자기 공방, 영어 학원, 첼로 레슨, 악기 수리, 개인 연주자, 사진 스튜디오. 'OO사이트를 만들고 싶어요'의 OO도 업종이다. '염색 및 클리닉'처럼 품목 나열은 업종이 아니라 offerings다"),
    Slot("shop_name", "가게 이름", "간판에 쓰는 가게 이름. 업종이나 품목(예: '도자기', '영어')은 가게 이름이 아니다. 품목만 말한 것(예: '네일', '커피')도 가게 이름이 아니다"),
    Slot("goal", "사이트 목적", "사이트로 이루고 싶은 것. 예: 예약·문의 늘리기, 가게 알리기, 메뉴·가격 안내, 수강 신청 받기. 대상 손님이나 품목은 목적이 아니다. 반례: '초등 영어'(대상+품목), '아이들이 많이 와요'(대상 손님 얘기)는 목적이 아니다"),
    Slot("target", "대상 손님", "주로 오는 손님·수강생. 예: 가족 여행객, 초등학생, 직장인. 자랑·품목이 섞여 있으면('파마 잘해요, 중년 아주머니가 많이 와요') 손님 부분만 target에 넣는다"),
    Slot("offerings", "상품·객실·메뉴·수업", "파는 것의 구성. 예: 객실 3개, 대표 메뉴 아메리카노·라떼, 원데이 클래스, 초등 영어 반. 가격까지 붙어 있으면('아메리카노 5천원') 메뉴는 offerings에, 가격은 price에 나눠서 넣는다. 주력 품목('염색 및 클리닉')은 업종이 아니라 offerings다", multi=True),
    Slot("sections", "담을 내용", "사이트에 넣고 싶은 부분. 예: 객실 소개, 바비큐장, 주변 맛집, 오시는 길, 가격표", multi=True),
    Slot("features", "필요한 기능", "사이트에서 동작해야 하는 기능·연동(섹션 이름이 아님). 예: 카카오톡으로 문의 받기, 온라인 예약, 수강 신청, 지도, 가격표, 공지사항", multi=True),
    Slot("exclude", "뺄 것", "넣지 말라고 한 것. 예: '바비큐는 빼주세요' → 바비큐", multi=True),
    Slot("contact_method", "연락 방법", "손님이 연락·예약하는 방법. 예: 전화, 카카오톡 채널, 네이버 예약, 문자"),
    Slot("phone", "전화번호", "사장님이 직접 말한 전화번호만. 말하지 않았으면 넣지 않는다", fact=True),
    Slot("hours", "영업시간", "사장님이 직접 말한 영업시간·체크인 시간·수업 시간만", fact=True),
    Slot("location", "위치", "사장님이 직접 말한 지역·주소만. 예: 강릉 경포, 부산 해운대구 우동 123", fact=True),
    Slot("price", "가격", "사장님이 직접 말한 가격만. 예: 원데이 클래스 3만5천원. 메뉴 이름이 붙어 있으면('젤네일 5만원', '컷트 2만원') 메뉴는 offerings로 나누고 가격만 price에 넣는다", fact=True),
    Slot("detail", "특징", "가게만의 특징이나 자랑. 예: 바다가 보이는 객실, 직접 로스팅. 대상이 섞여 있으면('중년 아주머니가 많이 와요') 그 부분은 target으로 나눈다"),
    Slot("booking_url", "예약 주소", "손님이 예약하는 페이지 주소. 사장님이 직접 붙여넣은 URL만. '네이버 예약으로 받아요' 같은 말은 contact_method이지 주소가 아니다. 주소가 없으면 넣지 않는다"),
    Slot("staff", "담당자", "담당 디자이너·선생님·의료진. 예: 원장 김미용(컷트), 영어 김선생님. 메뉴·시술 이름은 담당자가 아니다", multi=True),
    # 상황 탐색 칸 (BUILD_W1_W2 §1.6, D53 ③): 사실 칸이 아니고 질문 한도 밖이다.
    # 어느 업종의 required에도 넣지 않는다.
    Slot("team_mode", "운영 인원", "가게를 혼자 운영하는지 담당자가 여럿인지. 값: 혼자, 2~3명, 4명 이상"),
    Slot("order_mode", "주문 방식", "손님 주문 방식. 값: 매장 방문, 주문 앱 링크, 픽업 주문"),
    Slot("menu_categories", "메뉴 분류", "메뉴를 나누는 분류 이름. 예: 커피, 음료, 디저트", multi=True),
]}

FACT_SLOTS = frozenset(k for k, s in SLOTS.items() if s.fact)


@dataclass(frozen=True)
class Question:
    slot: str
    ask: str                      # 구체화형 질문
    confirm: str = ""             # 확인형 질문 ({value} 자리). 가정값이 있을 때 쓴다
    options: tuple[str, ...] = ()  # 최대 MAX_OPTIONS개, 첫 번째가 추천


@dataclass(frozen=True)
class Industry:
    key: str
    name: str
    aliases: tuple[str, ...]
    required: tuple[str, ...]      # 필수 칸(공통 + 업종별), 질문 우선순위 순서
    labels: dict = field(default_factory=dict)          # 업종에 맞춘 칸 이름 (예: offerings → 객실 구성)
    default_sections: tuple[str, ...] = ()
    hidden: tuple[tuple[str, str], ...] = ()            # (키, 표시 이름) 숨은 항목 후보 (D21)
    questions: dict = field(default_factory=dict)       # 칸별 질문 덮어쓰기


COMMON_QUESTIONS: dict[str, Question] = {
    # 업종은 끝이 없으므로 고정 선택지를 두지 않는다(첼로 레슨에게 '펜션·카페'를 보여주지 않게).
    "business_type": Question("business_type", "어떤 일을 하시나요? 예: 첼로 레슨, 카페, 펜션처럼 적어 주세요."),
    "shop_name": Question("shop_name", "가게 이름이 무엇인가요?"),
    "goal": Question("goal", "사이트로 가장 이루고 싶은 것은 무엇인가요?",
                     confirm="사이트 목적을 '{value}'로 할까요?",
                     options=("예약·문의 늘리기", "가게 알리기", "메뉴·가격 안내")),
    "offerings": Question("offerings", "어떤 것을 소개하고 싶으세요?"),
    "contact_method": Question("contact_method", "손님 연락은 어떻게 받으실까요?",
                               options=("전화", "카카오톡 채널", "예약 사이트 링크")),
    "hours": Question("hours", "영업시간은 어떻게 되나요?", options=("매일 같은 시간", "요일마다 달라요", "나중에 넣을게요")),
    "phone": Question("phone", "연락받을 전화번호를 알려 주세요.", options=("나중에 넣을게요",)),
    "location": Question("location", "가게는 어디에 있나요? 지역만 알려 주셔도 돼요.", options=("나중에 넣을게요",)),
}

INDUSTRIES: dict[str, Industry] = {i.key: i for i in [
    Industry(
        "pension", "펜션·숙박", ("펜션", "숙박", "민박", "게스트하우스", "풀빌라", "캠핑", "글램핑", "호텔", "모텔"),
        required=("business_type", "shop_name", "offerings", "contact_method", "goal", "hours"),
        labels={"offerings": "객실 구성", "hours": "체크인·아웃 시간"},
        default_sections=("객실 소개", "편의시설", "주변 안내", "오시는 길", "예약 문의"),
        hidden=(("parking", "주차"), ("pet", "반려동물 동반"), ("bbq", "바비큐·취사"), ("pickup", "픽업"), ("long_stay", "장기 숙박 할인")),
        questions={
            "offerings": Question("offerings", "객실은 몇 개이고 어떻게 구성돼 있나요?"),
            "hours": Question("hours", "체크인·체크아웃 시간은 언제인가요?", options=("15시 / 11시", "나중에 넣을게요")),
            "goal": Question("goal", "사이트로 가장 이루고 싶은 것은 무엇인가요?", options=("예약 문의 늘리기", "펜션 알리기", "객실·요금 안내")),
        },
    ),
    Industry(
        "cafe", "카페", ("카페", "커피", "베이커리", "디저트", "빵집"),
        required=("business_type", "shop_name", "offerings", "hours", "contact_method", "goal"),
        labels={"offerings": "대표 메뉴"},
        default_sections=("대표 메뉴", "매장 소개", "영업시간", "오시는 길"),
        hidden=(("parking", "주차"), ("pet", "반려동물 동반"), ("wifi", "콘센트·와이파이"), ("group", "단체석"), ("reserve", "예약")),
        questions={"offerings": Question("offerings", "대표 메뉴는 무엇인가요?")},
    ),
    Industry(
        "restaurant", "식당", ("식당", "한식", "중식", "일식", "양식", "고깃집", "밥집", "분식", "주점", "치킨", "피자"),
        required=("business_type", "shop_name", "offerings", "hours", "contact_method", "goal"),
        labels={"offerings": "메뉴"},
        default_sections=("대표 메뉴", "가게 소개", "영업시간", "오시는 길"),
        hidden=(("parking", "주차"), ("group", "단체 예약"), ("takeout", "포장·배달"), ("kids", "아이 의자"), ("wheelchair", "휠체어 이용")),
        questions={"offerings": Question("offerings", "대표 메뉴와 가격을 알려 주세요. 메뉴만 말씀하셔도 돼요.")},
    ),
    Industry(
        "salon", "미용실", ("미용실", "헤어", "네일", "피부", "왁싱", "속눈썹", "바버"),
        required=("business_type", "shop_name", "offerings", "contact_method", "hours", "goal"),
        labels={"offerings": "시술 메뉴", "contact_method": "예약 방법", "staff": "디자이너"},
        default_sections=("시술 메뉴", "디자이너 소개", "예약 안내", "오시는 길"),
        hidden=(("designer", "디자이너 지정"), ("parking", "주차"), ("same_day", "당일 예약"), ("men", "남성 전용 메뉴")),
        questions={"contact_method": Question("contact_method", "예약은 어떻게 받으시나요?", options=("네이버 예약", "전화", "카카오톡 채널"))},
    ),
    Industry(
        "workshop", "공방", ("공방", "도자기", "가죽", "목공", "플라워", "꽃", "캔들", "향수", "클래스"),
        required=("business_type", "shop_name", "offerings", "contact_method", "hours", "goal"),
        labels={"offerings": "수업 종류", "contact_method": "신청 방법", "hours": "수업 시간"},
        default_sections=("수업 안내", "작품 사진", "신청 방법", "오시는 길"),
        hidden=(("supplies", "준비물 안내"), ("parking", "주차"), ("group", "단체·기업 수업"), ("delivery", "완성품 배송")),
        questions={
            "offerings": Question("offerings", "어떤 수업을 하시나요?", options=("원데이 클래스", "정규반", "둘 다")),
            "goal": Question("goal", "사이트로 가장 이루고 싶은 것은 무엇인가요?", options=("수업 신청 받기", "작품 알리기", "수업·가격 안내")),
        },
    ),
    Industry(
        "academy", "학원", ("학원", "교습소", "과외", "영어", "수학", "피아노", "태권도", "미술"),
        required=("business_type", "shop_name", "target", "offerings", "contact_method", "goal"),
        labels={"offerings": "반 구성", "contact_method": "상담 방법", "target": "대상", "staff": "선생님"},
        default_sections=("반 구성", "수업 시간표", "선생님 소개", "상담 신청"),
        hidden=(("shuttle", "차량 운행"), ("trial", "체험 수업"), ("makeup", "보강"), ("sibling", "형제 할인")),
        questions={
            "target": Question("target", "주로 어떤 학생을 가르치시나요?", options=("초등학생", "중·고등학생", "성인")),
            "contact_method": Question("contact_method", "상담 신청은 어떻게 받으시나요?", options=("전화", "카카오톡 채널", "방문 상담")),
            "goal": Question("goal", "사이트로 가장 이루고 싶은 것은 무엇인가요?", options=("상담 신청 늘리기", "학원 알리기", "시간표·수업 안내")),
        },
    ),
    Industry(
        "other", "기타", (),
        required=("business_type", "shop_name", "offerings", "contact_method", "goal"),
        default_sections=("가게 소개", "상품·서비스", "오시는 길", "문의"),
        hidden=(("parking", "주차"), ("reserve", "예약"), ("delivery", "배송·출장")),
    ),
]}


def industry_for(business_type: str | None) -> Industry:
    """업종 표현을 업종 키로 바꾼다. 모르면 '기타'."""
    text = (business_type or "").replace(" ", "")
    for ind in INDUSTRIES.values():
        if any(a in text for a in ind.aliases):
            return ind
    return INDUSTRIES["other"]


def question_for(ind: Industry, slot: str) -> Question:
    return ind.questions.get(slot) or COMMON_QUESTIONS.get(slot) or Question(slot, f"{ind.labels.get(slot, SLOTS[slot].label)}을(를) 알려 주세요.")


def label_for(ind: Industry, slot: str) -> str:
    return ind.labels.get(slot, SLOTS[slot].label)


# ── 문의 종류별 프로필 (INTAKE_GATE_DESIGN.md §3, D29) ──────────────────
# 가게·매장은 위 6업종 표가 맡고, 개인·단체·웹서비스는 app/data/intake_profiles.json에서 읽는다.

def _load_profiles() -> dict:
    import json
    from pathlib import Path
    return json.loads((Path(__file__).resolve().parents[1] / "data" / "intake_profiles.json").read_text(encoding="utf-8"))


PROFILES = _load_profiles()

for _key in ("individual", "group", "webservice"):
    _p = PROFILES[_key]
    _qs = {}
    for _slot, _q in (_p.get("questions") or {}).items():
        if isinstance(_q, dict) and _slot in SLOTS:
            _qs[_slot] = Question(_slot, _q["ask"], options=tuple(_q.get("options") or ())[:MAX_OPTIONS])
    INDUSTRIES[_key] = Industry(
        _key, _p["label"], tuple(_p.get("aliases") or ()),
        required=tuple(k for k in _p["required"] if k in SLOTS),
        labels=dict(_p.get("labels") or {}),
        default_sections=tuple(_p.get("default_sections") or ()),
        hidden=tuple((h[0], h[1]) for h in _p.get("hidden") or ()),
        questions=_qs,
    )

# 질문 예산(§6): 가게 8(D20), 개인 7, 단체 8, 웹서비스 12. 확인이 필요한 기능마다 +1, 최대 +4.
BUDGETS = {k: PROFILES[k].get("budget", MAX_QUESTIONS) for k in ("individual", "group", "webservice")}
FEATURE_BONUS_MAX = 4
KIND_QUESTION = PROFILES["ambiguous"]["ask"]
KIND_OPTIONS = tuple(PROFILES["ambiguous"]["options"])
KIND_KEYS = tuple(PROFILES["ambiguous"]["keys"])


def budget_for(industry_key: str | None) -> int:
    return BUDGETS.get(industry_key or "", MAX_QUESTIONS)
