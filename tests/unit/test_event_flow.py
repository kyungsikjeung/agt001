"""초대·기념 (청첩장) 2단계: 종류 판정 → 질문 흐름 → 원형 I 청사진 → 데이터 연결 → 공개본 (EVENT_INVITE_PLAN).

'결혼 청첩장'이라고 하면 4지선다(가게·개인·단체·웹서비스) 대신 두 분 성함·날짜·장소를 묻고,
시안 3안이 날짜와 장소·연락하기·마음 전하실 곳 부품으로 나온다.
"""
import datetime

from app.services import archetype as AT
from app.services import design_variants as DV
from app.services import prd_engine as E
from app.services import prd_schema as S
from app.services import site_data as SD
from app.services import site_render as SR


def _card(**facts):
    card = E.new_card()
    E._put(card, "business_type", facts.pop("kind", "결혼 청첩장"), S.FILLED)
    for key, value in facts.items():
        E._put(card, key, value, S.FILLED)
    return card


def test_invite_words_map_to_event_not_ambiguous():
    for words in ("결혼 청첩장", "모바일 청첩장", "아들 돌잔치", "아버지 칠순"):
        assert S.industry_for(words).key == "event"
    assert S.industry_for("웨딩 사진작가").key == "individual"  # 사진 일 하는 사람은 그대로
    assert S.industry_for("카페").key == "cafe"


def test_questions_ask_names_date_place_and_never_the_four_way_kind_question():
    card = _card()
    asked = []
    for _ in range(8):
        q = E.next_question(card)
        if not q:
            break
        assert q["kind"] != "site_kind"
        asked.append(q.get("slot"))
        if q.get("slot"):
            E._put(card, q["slot"], "x", S.FILLED)
        else:
            card["hidden"]["asked"] = True
    assert asked[0] == "shop_name" and "두 분 성함" in E.next_question(_card())["text"]
    assert {"shop_name", "hours", "location"} <= set(asked)


def test_event_date_reads_korean_dates_and_rolls_to_next_year():
    today = datetime.date(2026, 10, 2)
    assert SD.event_date("11월 14일 토요일 오후 1시 30분", today) == (datetime.date(2026, 11, 14), "오후 1시 30분")
    assert SD.event_date("9월 1일 오후 2시 반", today) == (datetime.date(2027, 9, 1), "오후 2시 반")
    assert SD.event_date("2027년 3월 6일 낮 12시", today) == (datetime.date(2027, 3, 6), "낮 12시")
    assert SD.event_date("1/10 11:30", today) == (datetime.date(2027, 1, 10), "11:30")
    assert SD.event_date("다음 달 중순", today) == (None, "")
    assert SD.event_date("2월 30일", today)[0] is None


WEDDING = dict(shop_name="김민준 · 이서연", hours="11월 14일 토요일 오후 1시 30분",
               location="더채플앳청담 3층, 서울 강남구 선릉로 757")


def test_three_drafts_use_invite_parts_and_owner_words():
    card = _card(**WEDDING)
    assert AT.of(card)[0] == "I"
    items = DV.variants(card)
    assert len(items) == 3 and items[2]["name"] == "날짜 먼저"  # 청첩장은 앱형으로 바꾸지 않는다
    for item in items:
        kinds = {s["type"] for s in item["spec"]["sections"]}
        assert {"hero", "event", "family", "gift", "gallery", "around"} <= kinds
    secs = {s["type"]: s["content"] for s in items[0]["spec"]["sections"]}
    when = datetime.date.fromisoformat(secs["event"]["date"])
    assert (when.month, when.day) == (11, 14) and secs["event"]["time"] == "오후 1시 30분"
    assert "더채플앳청담" in secs["event"]["venue"] and not secs["event"].get("example")
    assert [p["name"] for side in secs["family"]["sides"] for p in side["people"]] == ["김민준", "이서연"]
    assert [side["side"] for side in secs["family"]["sides"]] == ["신랑측", "신부측"]
    assert secs["gift"]["example"] is True  # 계좌는 사장님이 넣기 전까지 예시
    facts = {f["label"] for f in secs["hero"].get("facts") or []}
    assert "영업" not in facts
    assert secs["intro"]["label"] == "인사말"
    assert '<h2 id="intro-title-greeting">인사말</h2>' in SR.render_site(items[0]["spec"], site_key="k")


def test_public_page_keeps_date_and_drops_example_accounts_and_phoneless_contacts():
    card = _card(**WEDDING)
    spec = DV.variants(card)[0]["spec"]
    draft = SR.render_site(spec, site_key="k")
    public = SR.render_site(spec, site_key="k", public=True)
    assert "예시은행" in draft and "예시은행" not in public
    assert 'data-section-id="when"' in public and "11월 14일" in public
    assert 'data-section-id="family"' not in public  # 번호가 없으면 단추 없는 명단이라 뺀다
    with_phone = DV.variants(_card(phone="010-1234-5678", **WEDDING))[0]["spec"]
    assert 'href="tel:01012345678"' in SR.render_site(with_phone, site_key="k", public=True)


def test_unreadable_date_shows_example_date_in_draft_only():
    card = _card(shop_name="박지호", hours="다음 달 중순", kind="아들 돌잔치")
    secs = {s["type"]: s["content"] for s in DV.variants(card)[0]["spec"]["sections"]}
    assert secs["event"]["example"] is True
    assert [side["side"] for side in secs["family"]["sides"]] == ["연락처"]  # 결혼이 아니면 신랑측·신부측이 아니다
