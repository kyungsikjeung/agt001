"""주변 안내 (10/4 대표 요청): 대제목(장소) + 소제목(도보 n분·차로 n분·거리·직접 글) + 보이는 모양 3가지.

펜션 2안 '주변' 구역(bind nearby)에 그려지고, 줄이 없으면 예전처럼 공간 사진첩이다.
"""
import re

import pytest

from app.services import nearby, photos

ORIGIN = {"Origin": "http://testserver"}


@pytest.mark.parametrize("item,want", [
    ({"unit": "walk", "value": 3}, "도보 3분"),
    ({"unit": "car", "value": 10}, "차로 10분"),
    ({"unit": "km", "value": 1.2}, "1.2km"),
    ({"unit": "km", "value": 12}, "12km"),
    ({"unit": "km", "value": 0.5}, "500m"),
    ({"unit": "text", "text": "바로 앞"}, "바로 앞"),
    ({"unit": "walk", "value": None}, ""),
])
def test_sub_text(item, want):
    assert nearby.sub_text(item) == want


def test_clean_checks_and_keeps_numbers():
    data, errors = nearby.clean([
        {"name": " 해수욕장 ", "unit": "walk", "value": "3"},
        {"name": "편의점", "unit": "km", "value": "0.3"},
        {"name": "", "unit": "walk", "value": ""},  # 빈 줄은 버림
        {"name": "시장", "unit": "text", "text": "  주말에만  "},
    ], "badge")
    assert errors == []
    assert data == {"style": "badge", "items": [
        {"name": "해수욕장", "unit": "walk", "value": 3},
        {"name": "편의점", "unit": "km", "value": 0.3},
        {"name": "시장", "unit": "text", "text": "주말에만"},
    ]}
    _, errors = nearby.clean([{"name": "a", "unit": "walk", "value": "3.5"}, {"name": "a", "unit": "car", "value": 5},
                              {"name": "", "unit": "km", "value": "2"}, {"name": "b", "unit": "km", "value": "999"}], None)
    assert errors == ["a: 1~600분 사이 숫자로 적어 주세요", "a: 같은 이름이 두 번 있어요",
                      "3번째 줄: 장소 이름을 적어 주세요", "b: 0.05~500km 사이 숫자로 적어 주세요"]


def _pension(client):
    from app.api import inquiries as inquiries_api
    with inquiries_api._lock:
        inquiries_api._hits.clear()
    body = client.post("/api/start", json={"template": "pension"}).json()
    rid, h = body["room_id"], {"X-Member-Id": body["member_id"]}
    assert client.put(f"/api/rooms/{rid}/card", json={"choice": "v2"}, headers=h).status_code == 200
    return rid, h


def _view_section(html_text: str) -> str:
    m = re.search(r'<section class="s-gallery[^"]*" data-section-id="view".*?</section>', html_text, re.S)
    assert m, "주변 구역이 없어요"
    return m.group(0)


def test_pension_nearby_saves_renders_and_falls_back(client):
    rid, h = _pension(client)
    before = _view_section(client.get(f"/api/rooms/{rid}/card/preview", headers=h).json()["html"])
    assert "s-cap" not in before  # 줄이 없으면 예전 사진첩 그대로
    r = client.put(f"/api/rooms/{rid}/card", headers=h, json={"nearby": {"style": "badge", "items": [
        {"name": "해수욕장", "unit": "walk", "value": 3}, {"name": "편의점", "unit": "km", "value": "0.3"}]}})
    assert r.status_code == 200
    assert [(i["name"], i["sub"]) for i in r.json()["nearby"]["items"]] == [("해수욕장", "도보 3분"), ("편의점", "300m")]
    sec = _view_section(client.get(f"/api/rooms/{rid}/card/preview", headers=h).json()["html"])
    assert '<figcaption class="s-cap s-cap--badge"><strong class="s-cap__title">해수욕장</strong><span class="s-cap__sub">도보 3분</span>' in sec
    assert 's-cap-tile' in sec  # 사진 없는 줄은 글 칸
    # 틀린 값은 400, 지우면 다시 사진첩
    r = client.put(f"/api/rooms/{rid}/card", headers=h, json={"nearby": {"items": [{"name": "x", "unit": "car", "value": "abc"}]}})
    assert r.status_code == 400 and "1~600분" in r.json()["detail"]
    assert client.put(f"/api/rooms/{rid}/card", headers=h, json={"nearby": {"items": []}}).status_code == 200
    assert "s-cap" not in _view_section(client.get(f"/api/rooms/{rid}/card/preview", headers=h).json()["html"])


def test_row_photo_tag_only_in_its_row_and_follows_rename():
    card = {"photos": [{"url": "/uploads/a.jpg", "tag": "nearby:해수욕장"}, {"url": "/uploads/b.jpg", "tag": "space"}],
            "nearby": {"items": [{"name": "해수욕장", "unit": "walk", "value": 3}], "style": "stack"}}
    assert [p["url"] for p in photos.site_photos(card)] == ["/uploads/b.jpg"]  # 첫 화면·사진첩에 안 섞임
    assert nearby.view(card)["items"][0]["photo"] == "/uploads/a.jpg"
    photos.rename_row_tag(card, nearby.TAG_PREFIX, "해수욕장", "○○해변")
    assert card["photos"][0]["tag"] == "nearby:○○해변"
    from app.services import photo_needs
    assert photo_needs.valid_tag(card, "nearby:해수욕장") is True
    assert photo_needs.valid_tag(card, "nearby:없는곳") is False
