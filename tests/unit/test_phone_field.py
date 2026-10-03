"""전화번호 칸: 한 가지 모양으로 저장, 틀린 번호는 저장 거부 (10/4 대표 요청).

화면 칸(frontend/src/editor/fields/phone.ts)은 쓰는 동안 같은 규칙으로 하이픈을 넣어 보인다.
"""
import pytest

from app import store
from app.services import prd_engine as E
from app.services import prd_schema as S
from app.services import validate as V


@pytest.mark.parametrize("raw,want", [
    ("01033332222", "010-3333-2222"),
    ("010 3333 2222", "010-3333-2222"),
    ("010.333.3222", "010-333-3222"),
    ("0212345678", "02-1234-5678"),
    ("02-123-4567", "02-123-4567"),
    ("0311234567", "031-123-4567"),
    ("031-1234-5678", "031-1234-5678"),
    ("15881234", "1588-1234"),
    ("07012345678", "070-1234-5678"),
    ("050712345678", "0507-1234-5678"),
    ("05051234567", "0505-123-4567"),
])
def test_format_phone(raw, want):
    assert V.check_phone(raw) is None
    assert V.format_phone(raw) == want


def test_0507_smartcall_is_valid_now():
    """네이버 스마트콜 0507-xxxx-xxxx(12자리)는 가게 번호로 흔하다. 예전엔 자리수 오류로 막았다."""
    assert V.check_phone("0507-1234-5678") is None
    assert V.check_phone("0507-123-456") == "전화번호 자리수가 맞지 않아요"


def _room(client):
    rid = client.post("/room").json()["room_id"]
    client.post(f"/room/{rid}/chat", json={"member_id": "owner", "nickname": "사장님", "message": ""})
    with store.room_tx(rid) as (_room, session):
        card = E.new_card()
        E._put(card, "business_type", "카페", S.FILLED, 1)
        E._put(card, "shop_name", "모퉁이", S.FILLED, 1)
        session["prd"] = card
    return rid


def _phone(client, rid):
    card = client.get(f"/api/rooms/{rid}/card", headers={"X-Member-Id": "owner"}).json()
    return next(f for f in card["fields"] if f["key"] == "phone")["value"]


def test_save_normalizes_and_rejects(client):
    rid = _room(client)
    h = {"X-Member-Id": "owner"}
    r = client.put(f"/api/rooms/{rid}/card", json={"fields": {"phone": "01033332222"}}, headers=h)
    assert r.status_code == 200 and _phone(client, rid) == "010-3333-2222"
    r = client.put(f"/api/rooms/{rid}/card", json={"fields": {"phone": "010-333"}}, headers=h)
    assert r.status_code == 400 and r.json()["detail"] == "전화번호: 전화번호 자리수가 맞지 않아요"
    assert _phone(client, rid) == "010-3333-2222"  # 틀린 값은 저장하지 않는다
    r = client.put(f"/api/rooms/{rid}/card", json={"fields": {"phone": "공일공 1234 5678"}}, headers=h)
    assert r.status_code == 200 and _phone(client, rid) == "010-1234-5678"  # 말로 읽은 번호도 같은 모양
