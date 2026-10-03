"""주변 안내 직접 편집 (10/4): "OO역 · 도보 3분"처럼 장소 + 거리·시간 줄, 크게 보일 것 고르기."""
from app.services import site_data as SD


def test_around_note_units():
    assert SD.around_note("walk", "3") == "도보 3분"
    assert SD.around_note("car", "10") == "차로 10분"
    assert SD.around_note("distance", "1.2") == "1.2km"
    assert SD.around_note("distance", "800m") == "800m"
    assert SD.around_note("walk", "3~5분") == "도보 3~5분"
    assert SD.around_note("text", "버스 7번 종점") == "버스 7번 종점"
    assert SD.around_note("walk", "  ") == ""


def test_clean_around_trims_drops_and_limits():
    saved, errors = SD.clean_around({"title": "distance", "items": [
        {"name": "  강릉역 ", "how": "car", "value": " 15 "}, {"name": "", "how": "walk", "value": "3"},
        {"name": "해변", "how": "nope", "value": "바로 앞"}]})
    assert errors == []
    assert saved == {"title": "distance", "items": [
        {"name": "강릉역", "how": "car", "value": "15"}, {"name": "해변", "how": "text", "value": "바로 앞"}]}
    _, errors = SD.clean_around({"items": [{"name": "가" * 21, "value": "1"}] + [{"name": f"곳{i}"} for i in range(9)]})
    assert any("8줄" in e for e in errors) and any("20자" in e for e in errors)
    assert SD.clean_around([])[1]


def test_rows_place_first_or_distance_first():
    card = {"around_edit": {"title": "place", "items": [{"name": "강릉역", "how": "car", "value": "15"}]}}
    assert SD._around_rows(card) == [{"name": "강릉역", "note": "차로 15분"}]
    card["around_edit"]["title"] = "distance"
    assert SD._around_rows(card) == [{"name": "차로 15분", "note": "강릉역"}]
    assert SD._around_rows({}) == []


def test_api_saves_and_preview_shows_rows(client):
    from tests.unit.test_card_api import _cafe_room
    rid = _cafe_room(client)
    h = {"X-Member-Id": "owner"}
    r = client.put(f"/api/rooms/{rid}/card", headers=h, json={"around": {"title": "place", "items": [
        {"name": "홍대입구역", "how": "walk", "value": "7"}, {"name": "공영주차장", "how": "distance", "value": "300m"}]}})
    assert r.status_code == 200, r.text
    assert r.json()["around"]["items"][0] == {"name": "홍대입구역", "how": "walk", "value": "7"}
    doc = client.get(f"/api/rooms/{rid}/card/preview?variant=v1", headers=h).json()["html"]
    assert "홍대입구역" in doc and "도보 7분" in doc and "300m" in doc
    assert doc.index("홍대입구역") < doc.index("02-123-4567")   # 주변 안내가 전화보다 먼저
    # 400: 너무 긴 이름
    r = client.put(f"/api/rooms/{rid}/card", headers=h, json={"around": {"items": [{"name": "가" * 21}]}})
    assert r.status_code == 400
    # 빈 목록이면 지운다
    r = client.put(f"/api/rooms/{rid}/card", headers=h, json={"around": {"items": []}})
    assert r.json()["around"] == {"title": "place", "items": []}
    assert client.put(f"/api/rooms/{rid}/card", headers={"X-Member-Id": "guest"},
                      json={"around": {"items": []}}).status_code == 403
