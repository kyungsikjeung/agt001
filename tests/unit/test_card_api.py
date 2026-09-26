"""직접 편집 API (계약 §5): 참여자는 읽기, 방장만 고치기, 빈 값은 입력 필요, 공개본에 바로 반영."""
from app import store


def _room(client):
    rid = client.post("/room").json()["room_id"]
    client.post(f"/room/{rid}/chat", json={"member_id": "owner", "nickname": "사장님", "message": "카페예요"})
    client.post(f"/room/{rid}/chat", json={"member_id": "guest", "nickname": "손님", "message": ""})
    return rid


def test_read_and_owner_only_edit(client):
    rid = _room(client)
    v = client.get(f"/api/rooms/{rid}/card", headers={"X-Member-Id": "guest"}).json()
    assert v["can_edit"] is False and {f["key"] for f in v["fields"]} >= {"shop_name", "phone"}
    assert client.put(f"/api/rooms/{rid}/card", json={"fields": {"shop_name": "x"}}, headers={"X-Member-Id": "guest"}).status_code == 403
    r = client.put(f"/api/rooms/{rid}/card", json={"fields": {"shop_name": "모퉁이커피", "phone": "공일공 1234 5678", "offerings": "라떼, 모카"}},
                   headers={"X-Member-Id": "owner"})
    assert r.status_code == 200
    f = {x["key"]: x for x in r.json()["fields"]}
    assert f["shop_name"]["value"] == "모퉁이커피" and f["shop_name"]["status"] == "filled"
    assert f["phone"]["value"] == "010-1234-5678" and f["offerings"]["value"] == "라떼, 모카"
    r = client.put(f"/api/rooms/{rid}/card", json={"fields": {"shop_name": ""}}, headers={"X-Member-Id": "owner"})
    assert {x["key"]: x for x in r.json()["fields"]}["shop_name"]["status"] == "placeholder"
    assert client.get(f"/api/rooms/{rid}/card", headers={"X-Member-Id": "stranger"}).status_code == 404
