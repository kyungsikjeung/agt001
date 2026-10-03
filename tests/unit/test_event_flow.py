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


# ---- 빌더에서 양가 연락처·계좌 넣기 (PUT /card event) ----
def _wedding_room(client):
    from app import store
    rid = client.post("/room").json()["room_id"]
    client.post(f"/room/{rid}/chat", json={"member_id": "owner", "nickname": "신랑", "message": "결혼 청첩장"})
    room = store.read_room(rid)
    with store.session_tx(room["session_id"]) as s:
        card = E.new_card()
        for key, value in dict(business_type="결혼 청첩장", **WEDDING).items():
            E._put(card, key, value, S.FILLED, 1)
        card["industry"], card["turn"] = "event", 1
        s["prd"] = card
    return rid


OWNER = {"X-Member-Id": "owner"}
FAMILY = [{"side": "신랑측", "people": [{"role": "신랑", "name": "김민준", "phone": "010-1234-5678"},
                                     {"role": "아버지", "name": "김철수", "phone": "010-2222-3333"}]},
          {"side": "신부측", "people": [{"role": "신부", "name": "이서연", "phone": ""}]}]
GIFT = [{"side": "신랑측", "accounts": [{"role": "신랑", "holder": "김민준", "bank": "국민은행", "number": "123456-01-234567"}]}]


def test_card_view_shows_editable_lists_with_defaults(client):
    rid = _wedding_room(client)
    view = client.get(f"/api/rooms/{rid}/card", headers=OWNER).json()
    assert [s["side"] for s in view["event"]["family"]] == ["신랑측", "신부측"]
    assert view["event"]["gift"][0]["accounts"][0]["bank"] == "예시은행"
    assert view["event"]["saved"] == {"family": False, "gift": False}


def test_saved_contacts_and_accounts_replace_examples_and_go_public(client):
    from app.services import design_variants as DV
    from app import store
    rid = _wedding_room(client)
    r = client.put(f"/api/rooms/{rid}/card", json={"event": {"family": FAMILY, "gift": GIFT}}, headers=OWNER)
    assert r.status_code == 200 and r.json()["event"]["saved"] == {"family": True, "gift": True}
    card = store.read_session(store.read_room(rid)["session_id"])["prd"]
    public = SR.render_site(DV.variants(card)[0]["spec"], site_key="k", public=True)
    assert 'href="tel:01022223333"' in public and "국민은행 123456-01-234567" in public and "예시은행" not in public
    # 빈 목록이면 예시로 되돌린다
    r = client.put(f"/api/rooms/{rid}/card", json={"event": {"gift": []}}, headers=OWNER)
    assert r.json()["event"]["saved"] == {"family": True, "gift": False}


def test_bad_phone_or_account_is_refused_with_who(client):
    rid = _wedding_room(client)
    bad_phone = [{"side": "신랑측", "people": [{"role": "신랑", "name": "김민준", "phone": "010-12"}]}]
    r = client.put(f"/api/rooms/{rid}/card", json={"event": {"family": bad_phone}}, headers=OWNER)
    assert r.status_code == 400 and "김민준" in r.json()["detail"]
    rrn = [{"side": "신랑측", "accounts": [{"holder": "김민준", "bank": "농협", "number": "900101-1234567"}]}]
    r = client.put(f"/api/rooms/{rid}/card", json={"event": {"gift": rrn}}, headers=OWNER)
    assert r.status_code == 400 and "주민등록번호" in r.json()["detail"]
    assert client.put(f"/api/rooms/{rid}/card", json={"event": {"gift": GIFT}},
                      headers={"X-Member-Id": "stranger"}).status_code in (403, 404)


# ---- 참석 여부 받기 (rsvp--form → /api/rsvp/, 문의 저장소) ----
import pytest

from app.api import inquiries as inquiries_api


@pytest.fixture(autouse=True)
def _reset_rate_limit():
    """문의·참석 여부는 IP당 10분 5건 제한을 같이 쓴다. 다른 테스트에 남기지 않게 앞뒤로 비운다."""
    inquiries_api._hits.clear()
    yield
    inquiries_api._hits.clear()


def _published_key(client):
    """공개된 청첩장 사이트 키(site_exists가 보는 requirement_id)."""
    from app import store
    rid = _wedding_room(client)
    room = store.read_room(rid)
    session = store.read_session(room["session_id"])
    return rid, session["requirement_id"]


def test_rsvp_form_in_drafts_with_wedding_sides():
    items = DV.variants(_card(**WEDDING))
    for item in items:
        kinds = [s["type"] for s in item["spec"]["sections"]]
        assert kinds.index("rsvp") < kinds.index("gift")
    bar = items[0]["spec"]["actionbar"]  # 주 버튼 오시는 길 + 참석 여부 (같은 버튼 두 개가 아니게)
    assert bar["primary"]["label"] == "오시는 길" and bar["secondary"]["label"] == "참석 여부"
    html = SR.render_site(items[0]["spec"], site_key="abc", public=True)
    assert 'action="/api/rsvp/abc"' in html and 'value="신랑측"' in html and 'name="attend"' in html


def test_rsvp_submit_goes_to_inquiries_and_owner_room(client):
    from app import store
    rid, key = _published_key(client)
    r = client.post(f"/api/rsvp/{key}", data={"name": "박하객", "side": "신부측", "attend": "yes", "count": "2",
                                             "meal": "yes", "message": "축하해요!", "agree": "yes"})
    assert r.status_code == 200 and "참석 여부를 전했어요" in r.text
    msgs = [m for m in store.read_messages(rid, 0) if m.get("kind") == "inquiry"]
    assert msgs and "[참석 여부] 신부측 · 참석 · 2명 · 식사함" in msgs[-1]["text"] and "박하객" in msgs[-1]["text"]


def test_rsvp_needs_name_attend_and_agree(client):
    _, key = _published_key(client)
    assert client.post(f"/api/rsvp/{key}", data={"attend": "yes", "agree": "yes"}).status_code == 400
    assert client.post(f"/api/rsvp/{key}", data={"name": "a", "agree": "yes"}).status_code == 400
    assert client.post(f"/api/rsvp/{key}", data={"name": "a", "attend": "no"}).status_code == 400
    assert client.post("/api/rsvp/nope", data={"name": "a", "attend": "no", "agree": "yes"}).status_code == 400


def test_rsvp_summary_counts_people_meals_sides_and_is_owner_only(client):
    rid, key = _published_key(client)
    for form in ({"name": "박하객", "side": "신부측", "attend": "yes", "count": "2", "meal": "yes"},
                 {"name": "김친구", "side": "신랑측", "attend": "yes", "count": "3", "meal": "no", "message": "늦을 수 있어요"},
                 {"name": "이선배", "side": "신랑측", "attend": "no"}):
        assert client.post(f"/api/rsvp/{key}", data={**form, "agree": "yes"}).status_code == 200
    client.post(f"/api/inquiries/{key}", data={"name": "문의", "contact": "010-1234-5678", "message": "주차 되나요?", "agree": "yes"})
    data = client.get(f"/api/rooms/{rid}/rsvp", headers=OWNER).json()
    assert data["total"] == {"replies": 3, "people": 5, "declined": 1, "meal": 2}
    assert data["sides"] == {"신부측": 2, "신랑측": 3}
    assert [e["name"] for e in data["entries"]] == ["이선배", "김친구", "박하객"]  # 최신순, 일반 문의는 빼고
    assert data["entries"][1]["note"] == "늦을 수 있어요"
    assert client.get(f"/api/rooms/{rid}/rsvp", headers={"X-Member-Id": "guest"}).status_code in (403, 404)
