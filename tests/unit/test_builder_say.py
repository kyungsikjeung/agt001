"""말로 고치기 서비스 수준 테스트 (SAY_CONTRACT §10 항목 1~6, 8, 9, 10).

LLM은 가짜로 둔다 (app.llm.chat_json을 끼워넣는다). 방·카드는 POST /api/start로
만들고 store.read_room / store.read_session으로 읽는다. 항목 7의 403·출처는
다음 물결의 경로 테스트에서 본다 (여기서는 되묻기·300자만 본다).
"""
import copy
import json

import pytest

from app import llm, store
from app.services import builder_agent as B
from app.services import prd_engine as E
from app.services import prd_schema as S


@pytest.fixture(autouse=True)
def _clear_rate_limit():
    # IP 제한(IP당 10분 5번)을 테스트마다 따로 센다.
    from app.api import inquiries as inquiries_api
    with inquiries_api._lock:
        inquiries_api._hits.clear()


def _boom(*args, **kwargs):
    raise AssertionError("규칙 경로에서 LLM을 부르면 안 됨")


def _no_llm(monkeypatch):
    monkeypatch.setattr(llm, "chat_json", _boom)


def _llm_json(monkeypatch, payload):
    def fake(system, user, **kwargs):
        return json.dumps(payload, ensure_ascii=False)
    monkeypatch.setattr(llm, "chat_json", fake)


def _start(client, template="cafe"):
    from app.api import inquiries as inquiries_api
    with inquiries_api._lock:
        inquiries_api._hits.clear()
    r = client.post("/api/start", json={"template": template})
    assert r.status_code == 200, r.text
    return r.json()


def _room_session(room_id):
    room = store.read_room(room_id)
    session = store.read_session(room["session_id"])
    return room, session


def _say(room_id, text):
    with store.room_tx(room_id) as (room, session):
        return B.say(room, session, room_id, text)


def _small_card():
    """평가 케이스 모양의 작은 카드 (DB 없음)."""
    return {"shop_name": "햇살카페",
            "offerings": ["아메리카노", "카페라떼", "바닐라라떼"],
            "price_pairs": {"아메리카노": "4,000원", "카페라떼": "4,500원",
                            "바닐라라떼": "5,000원"},
            "sections": [{"id": "menu", "label": "메뉴", "on": True},
                         {"id": "space", "label": "공간", "on": True},
                         {"id": "around", "label": "오시는 길", "on": True},
                         {"id": "inquiry", "label": "문의", "on": True}],
            "addable": [{"id": "sign", "label": "시그니처"},
                        {"id": "reviews", "label": "후기"}]}


def test_1_rule_guards_no_llm(monkeypatch):
    """항목 1: 칩 규칙·공개·안 바꾸기 가드. 규칙이면 LLM 0번."""
    _no_llm(monkeypatch)
    card = _small_card()
    got = B.plan(card, "후기 넣어 줘")
    assert got["source"] == "rule"
    assert got["ops"] == [{"op": "section", "id": "reviews", "action": "add"}]
    # 칩 이름+내용물이 남으면 규칙이 아니다 → LLM으로 (가짜가 터지면 실패)
    assert B.rules(card, "메뉴에 빙수 6천원 추가") is None
    # '공개 전에…'는 공개 안내가 아니다
    assert B.rules(card, "공개 전에 메뉴 바꿔") is None
    # '사진 크게…'는 안 바꾸기가 아니다
    assert B.rules(card, "사진 크게 보이는 걸로") is None


def test_2_rule_paths_no_llm(client, monkeypatch):
    """항목 2: 번호 고치기·앱형·느낌·전화번호. 원본 카드 그대로, LLM 0번."""
    _no_llm(monkeypatch)
    body = _start(client)
    with store.room_tx(body["room_id"]) as (room, session):
        card = session["prd"]
        E._put(card, "offerings", ["아메리카노", "카페라떼", "바닐라라떼"],
               S.FILLED, 1)
        card["price_pairs"] = {"아메리카노": "4,000원", "카페라떼": "4,500원",
                               "바닐라라떼": "5,000원"}
    _, session = _room_session(body["room_id"])
    before = copy.deepcopy(session["prd"])
    got = B.plan(session["prd"], "2번 가격 1만원")
    assert got["source"] == "rule"
    assert got["ops"] == [{"op": "item", "name": "카페라떼", "price": "1만원"}]
    assert session["prd"] == before  # plan은 복사본만 본다
    got = B.plan(session["prd"], "앱처럼")
    assert got["ops"] == [{"op": "variant", "variant": "v3"}]
    got = B.plan(session["prd"], "더 밝게")
    assert got["source"] == "rule" and got["ops"][0]["op"] == "style"
    got = B.plan(session["prd"], "전화번호 010 1234 5678")
    assert got["ops"] == [{"op": "set_field", "key": "phone",
                           "value": "010-1234-5678"}]
    assert session["prd"] == before


def test_3_llm_item_grounded_vs_dropped(client, monkeypatch):
    """항목 3: 말에 있는 값이면 적용, 없으면 버리고 rejected."""
    _llm_json(monkeypatch, {"ops": [{"op": "item", "name": "빙수",
                                     "price": "6000원", "add": True}],
                            "reply": "빙수를 넣었어요."})
    body = _start(client)
    out = _say(body["room_id"], "메뉴에 빙수 6천원 추가")
    assert out["source"] == "llm" and out["rejected"] == []
    _, session = _room_session(body["room_id"])
    assert session["prd"]["price_pairs"].get("빙수") == "6000원"
    assert set(out) == {"reply", "focus", "features", "undo", "rejected", "source"}

    out = _say(body["room_id"], "메뉴에 빙수 추가해줘")
    assert out["rejected"] != []  # 말에 가격이 없어서 버림
    _, session = _room_session(body["room_id"])
    assert session["prd"]["price_pairs"].get("빙수") == "6000원"  # 그대로


def test_4_fabricated_phone_dropped(client, monkeypatch):
    """항목 4: 말에 없는 전화번호는 버리고 카드 그대로."""
    _llm_json(monkeypatch, {"ops": [{"op": "set_field", "key": "phone",
                                     "value": "02-999-9999"}],
                            "reply": "전화를 바꿨어요."})
    body = _start(client)
    _, session = _room_session(body["room_id"])
    before = str(((session["prd"].get("slots") or {}).get("phone") or {}).get("value"))
    out = _say(body["room_id"], "전화번호 바꿔줘")
    assert out["rejected"] != [] and any("전화번호" in r for r in out["rejected"])
    _, session = _room_session(body["room_id"])
    after = str(((session["prd"].get("slots") or {}).get("phone") or {}).get("value"))
    assert after == before and "02-999-9999" not in after


def test_5_locked_section_dropped(client, monkeypatch):
    """항목 5: 잠긴 구역(inquiry) 숨기기는 버림."""
    _llm_json(monkeypatch, {"ops": [{"op": "section", "id": "inquiry",
                                     "action": "hide"}],
                            "reply": "문의를 숨겼어요."})
    body = _start(client)
    _, session = _room_session(body["room_id"])
    before = copy.deepcopy(session["prd"])
    out = _say(body["room_id"], "문의 숨겨줘")
    assert out["rejected"] != [] and any("잠긴" in r for r in out["rejected"])
    _, session = _room_session(body["room_id"])
    assert session["prd"] == before


def test_6_apply_then_undo(client, monkeypatch):
    """항목 6: 적용 → 되돌리기면 적용 전과 같음, 두 번째는 안내만."""
    _no_llm(monkeypatch)
    body = _start(client)
    _, session = _room_session(body["room_id"])
    before = copy.deepcopy(session["prd"])
    out = _say(body["room_id"], "시그니처 넣어줘")
    assert out["undo"] is True and out["focus"] == "sign"
    _, session = _room_session(body["room_id"])
    assert session["prd"] != before
    with store.room_tx(body["room_id"]) as (room, session):
        done = B.undo(room, session, body["room_id"])
    assert done["reply"] == "되돌렸어요." and done["undo"] is False
    _, session = _room_session(body["room_id"])
    assert session["prd"] == before
    with store.room_tx(body["room_id"]) as (room, session):
        done = B.undo(room, session, body["room_id"])
    assert done["reply"] == "되돌릴 게 없어요."


def test_7_llm_failure_asks_again_and_long_text_rejected(client, monkeypatch):
    """항목 7 중 서비스 몫: LLM 실패·시간 초과는 되묻기, 300자 초과는 ValueError."""
    def _fail(system, user, **kwargs):
        raise TimeoutError("시간 초과")
    monkeypatch.setattr(llm, "chat_json", _fail)
    body = _start(client)
    out = _say(body["room_id"], "영업시간 오전 11시부터 밤 9시까지야")
    assert set(out) == {"reply", "focus", "features", "undo", "rejected", "source"}
    assert out["source"] == "none" and "다시" in out["reply"]
    with store.room_tx(body["room_id"]) as (room, session):
        with pytest.raises(ValueError):
            B.say(room, session, body["room_id"], "가" * 301)
        with pytest.raises(ValueError):
            B.plan(session["prd"], "가" * 301)


def test_8_publish_and_feature_guide(client, monkeypatch):
    """항목 8: 공개 말은 적용 없이 안내, 스탬프는 안내만."""
    _no_llm(monkeypatch)
    body = _start(client)
    _, session = _room_session(body["room_id"])
    before = copy.deepcopy(session["prd"])
    out = _say(body["room_id"], "공개해 줘")
    assert "공개하기" in out["reply"]
    _, session = _room_session(body["room_id"])
    assert session["prd"] == before
    assert out["undo"] is False

    _llm_json(monkeypatch, {"ops": [{"op": "feature", "key": "stamps"}],
                            "reply": "스탬프를 켰어요."})
    out = _say(body["room_id"], "스탬프 넣어줘")
    assert "공개한 뒤 사장님 화면에서 켤 수 있어요" in out["reply"]
    _, session = _room_session(body["room_id"])
    assert session["prd"] == before


def test_9_published_republish_no_edit_markers(client, monkeypatch):
    """항목 9: 공개본이 있으면 적용 뒤 공개본에도 반영, 편집 표시 없음."""
    from app.api import card as card_api
    from app.config import settings
    from app.services import design as design_svc
    _no_llm(monkeypatch)
    seen = {}
    body = _start(client)
    with store.room_tx(body["room_id"]) as (room, session):
        session["prd"]["published"] = "v1"
        req = session["requirement_id"]

    def fake_publish(requirement_id, card, choice):
        seen["args"] = (requirement_id, choice)
        folder = settings.generated_dir / requirement_id / "published"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "index.html").write_text("<html><body>공개본</body></html>",
                                           encoding="utf-8")
    monkeypatch.setattr(design_svc, "publish_choice", fake_publish)
    out = _say(body["room_id"], "시그니처 넣어줘")
    assert seen.get("args") == (req, "v1")
    published = (settings.generated_dir / req / "published" / "index.html").read_text(
        encoding="utf-8")
    assert "data-edit-mode" not in published and "agt-edit" not in published
    assert card_api is not None and out["undo"] is True


def test_10_plan_writes_nothing(client, monkeypatch):
    """항목 10: plan()은 원본 카드·세션·DB 행 수를 바꾸지 않는다."""
    from app.db.session import get_sessionmaker
    from app.db.models import RoomRow, SessionRow
    _no_llm(monkeypatch)
    body = _start(client)
    room, session = _room_session(body["room_id"])
    room_before, session_before = copy.deepcopy(room), copy.deepcopy(session)

    def _counts():
        with get_sessionmaker()() as db:
            return (db.query(RoomRow).count(), db.query(SessionRow).count())
    rows_before = _counts()

    got = B.plan(session["prd"], "시그니처 넣어줘")
    assert got["source"] == "rule" and got["ops"]
    got = B.plan(session["prd"], "2번 가격 1만원")
    assert got["source"] in ("rule", "llm", "none")

    room, session = _room_session(body["room_id"])
    assert room == room_before and session == session_before
    assert _counts() == rows_before


def _owner_headers(body):
    return {"X-Member-Id": body["member_id"]}


def test_11_route_say_undo_owner(client, monkeypatch):
    """항목 7 중 경로 몫: 방장은 /say·/undo를 쓰고 답은 no-store다."""
    _no_llm(monkeypatch)
    body = _start(client)
    rid, headers = body["room_id"], _owner_headers(body)
    _, session = _room_session(rid)
    before = copy.deepcopy(session["prd"])
    r = client.post(f"/api/rooms/{rid}/say", json={"text": "시그니처 넣어줘"},
                    headers=headers)
    assert r.status_code == 200, r.text
    data = r.json()
    assert set(data) == {"reply", "focus", "features", "undo", "rejected", "source"}
    assert data["undo"] is True and data["focus"] == "sign"
    assert r.headers["cache-control"] == "no-store"
    _, session = _room_session(rid)
    assert session["prd"] != before
    r = client.post(f"/api/rooms/{rid}/undo", headers=headers)
    assert r.status_code == 200, r.text
    assert r.headers["cache-control"] == "no-store"
    assert r.json()["reply"] == "되돌렸어요."
    assert r.json()["undo"] is False
    _, session = _room_session(rid)
    assert session["prd"] == before


def test_12_route_guards_403_400_ask_again(client, monkeypatch):
    """항목 7 중 경로 몫: 방장 아님 403·다른 출처 403·301자 400·LLM 실패는 되묻기 200."""
    import uuid
    from app.config import settings
    from app.db.models import UserRoomRow, UserRow
    from app.db.session import get_sessionmaker
    from app.services import auth
    _no_llm(monkeypatch)
    body = _start(client)
    rid, headers = body["room_id"], _owner_headers(body)
    client.post(f"/room/{rid}/chat",
                json={"member_id": "guest", "nickname": "손님", "message": ""})
    guest = {"X-Member-Id": "guest"}
    r = client.post(f"/api/rooms/{rid}/say", json={"text": "시그니처 넣어줘"},
                    headers=guest)
    assert r.status_code == 403 and r.json()["detail"] == "owner only"
    r = client.post(f"/api/rooms/{rid}/undo", headers=guest)
    assert r.status_code == 403 and r.json()["detail"] == "owner only"
    # 쿠키로 붙은 쓰기는 우리 출처에서만 받는다.
    user_id = f"u-{uuid.uuid4().hex[:8]}"
    with get_sessionmaker()() as db, db.begin():
        db.add(UserRow(id=user_id, nickname="사장님"))
        db.flush()
        db.add(UserRoomRow(user_id=user_id, room_id=rid, member_id=body["member_id"]))
    client.cookies.set(auth.SESSION_COOKIE, auth.create_session(user_id))
    try:
        ours = (settings.public_base_url or "http://testserver").rstrip("/")
        payload = {"text": "시그니처 넣어줘"}
        assert client.post(f"/api/rooms/{rid}/say", json=payload).status_code == 403
        r = client.post(f"/api/rooms/{rid}/say", json=payload,
                        headers={"Origin": "https://evil.example"})
        assert r.status_code == 403, r.text
        r = client.post(f"/api/rooms/{rid}/say", json=payload,
                        headers={"Origin": ours})
        assert r.status_code == 200, r.text
    finally:
        client.cookies.clear()
    r = client.post(f"/api/rooms/{rid}/say", json={"text": "가" * 301},
                    headers=headers)
    assert r.status_code == 400

    def _fail(system, user, **kwargs):
        raise TimeoutError("시간 초과")
    monkeypatch.setattr(llm, "chat_json", _fail)
    r = client.post(f"/api/rooms/{rid}/say",
                    json={"text": "영업시간 오전 11시부터 밤 9시까지야"},
                    headers=headers)
    assert r.status_code == 200, r.text
    assert "다시" in r.json()["reply"]


def test_13_other_change_invalidates_undo(client, monkeypatch):
    """되돌리기 안전: 말로 고친 뒤 칩을 바꾸면 되돌리기는 무효, 칩 변경은 남는다."""
    _no_llm(monkeypatch)
    body = _start(client)
    rid, headers = body["room_id"], _owner_headers(body)
    r = client.post(f"/api/rooms/{rid}/say", json={"text": "시그니처 넣어줘"},
                    headers=headers)
    assert r.status_code == 200 and r.json()["undo"] is True
    r = client.put(f"/api/rooms/{rid}/features",
                   json={"key": "section:space", "on": True}, headers=headers)
    assert r.status_code == 200, r.text
    assert {f["key"]: f for f in r.json()["features"]}["section:space"]["on"] is True
    r = client.post(f"/api/rooms/{rid}/undo", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["reply"] == "되돌릴 게 없어요."
    feats = client.get(f"/api/rooms/{rid}/features", headers=headers).json()["features"]
    assert {f["key"]: f for f in feats}["section:space"]["on"] is True


def test_14_undo_keeps_unrelated_later_change(client, monkeypatch):
    """되돌리기는 말로 고친 칸만 되돌린다: 그 뒤 다른 칸(공지)을 바꿨으면 공지는 남는다."""
    _no_llm(monkeypatch)
    body = _start(client)
    rid, headers = body["room_id"], _owner_headers(body)
    r = client.post(f"/api/rooms/{rid}/say", json={"text": "시그니처 넣어줘"}, headers=headers)
    assert r.status_code == 200 and r.json()["undo"] is True
    r = client.put(f"/api/rooms/{rid}/features",
                   json={"key": "notice", "on": True, "text": "10월 휴무 없음"}, headers=headers)
    assert r.status_code == 200, r.text
    r = client.post(f"/api/rooms/{rid}/undo", headers=headers)
    assert r.json()["reply"] == "되돌렸어요.", r.text
    feats = {f["key"]: f for f in r.json()["features"]}
    assert feats["section:sign"]["on"] is False
    assert feats["notice"]["on"] is True
