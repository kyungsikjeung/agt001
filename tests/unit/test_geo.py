"""주소 검색·임시 주소·저장 (MAP_CONTRACT §6의 1~3). 카카오는 가짜로만 부른다."""
import pytest

from app.services import geo


class _Resp:
    def __init__(self, status, body):
        self.status_code = status
        self._body = body

    def json(self):
        return self._body


def _addr_doc(road, jibun, x, y):
    return {"road_address": {"address_name": road} if road else None,
            "address": {"address_name": jibun}, "x": str(x), "y": str(y)}


@pytest.fixture
def fake_kakao(monkeypatch):
    """주소 검색 → 키워드 검색 순서로 부른 요청을 잡는다."""
    calls, answers = [], {}
    monkeypatch.setattr(geo.keystore, "get", lambda name: "rest-key" if name == "kakao_rest_api_key" else None)

    def fake_get(url, headers=None, params=None, timeout=None):
        calls.append({"url": url, "headers": headers, "params": params, "timeout": timeout})
        kind = "keyword" if "keyword" in url else "address"
        status, docs = answers.get(kind, (200, []))
        if isinstance(docs, Exception):
            raise docs
        return _Resp(status, {"documents": docs})

    monkeypatch.setattr(geo.httpx, "get", fake_get)
    return calls, answers


def test_1_address_results_capped_at_five(fake_kakao):
    calls, answers = fake_kakao
    answers["address"] = (200, [_addr_doc(f"서울 마포구 연남로 {i}", f"연남동 {i}", 126.9, 37.5) for i in range(8)])
    got = geo.search("연남로")
    assert len(got) == 5 and got[0] == {"road": "서울 마포구 연남로 0", "jibun": "연남동 0", "x": 126.9, "y": 37.5}
    assert len(calls) == 1 and calls[0]["timeout"] == 3.0
    assert calls[0]["headers"] == {"Authorization": "KakaoAK rest-key"}
    assert calls[0]["params"] == {"query": "연남로"}  # 주소 말만 보낸다


def test_1_keyword_when_no_address_and_jibun_only(fake_kakao):
    calls, answers = fake_kakao
    answers["address"] = (200, [])
    answers["keyword"] = (200, [{"road_address_name": "", "address_name": "강원 평창군 봉평면 1", "x": "128.3", "y": "37.6"}])
    got = geo.search("봉평 메밀밭 근처")
    assert [c["url"].endswith("keyword.json") for c in calls] == [False, True]
    assert got == [{"road": "강원 평창군 봉평면 1", "jibun": "강원 평창군 봉평면 1", "x": 128.3, "y": 37.6}]


def test_1_failures_are_empty(fake_kakao, monkeypatch):
    calls, answers = fake_kakao
    answers["address"] = (200, TimeoutError("느림"))
    assert geo.search("연남로") == []
    answers["address"] = (500, [])
    assert geo.search("연남로") == []
    assert geo.search("  ") == []
    monkeypatch.setattr(geo.keystore, "get", lambda name: None)
    n = len(calls)
    assert geo.search("연남로") == [] and len(calls) == n  # 키 없으면 부르지도 않는다


@pytest.mark.parametrize("words,road", [
    ("마포구 연남동 골목", "서울특별시 마포구 월드컵로 212"),
    ("부산 해운대 쪽", "부산광역시 연제구 중앙대로 1001"),
    ("부산 강서구", "부산광역시 연제구 중앙대로 1001"),   # 서울 강서구가 아니다
    ("경기 광주 퇴촌", "경기도 수원시 영통구 도청로 30"),   # 광주광역시가 아니다
    ("서울 중구 을지로", "서울특별시 중구 창경궁로 17"),
    ("동네 어딘가", "서울특별시 중구 세종대로 110"),
])
def test_2_placeholder(words, road):
    got = geo.placeholder(words)
    assert got["road"] == road and got["src"] == "placeholder"
    assert geo.X_MIN <= got["x"] <= geo.X_MAX and geo.Y_MIN <= got["y"] <= geo.Y_MAX


# ── 경로 (§6의 3) ──

def _start(client):
    from app.api import inquiries as inquiries_api
    with inquiries_api._lock:
        inquiries_api._hits.clear()
    body = client.post("/api/start", json={"template": "cafe"}).json()
    return body["room_id"], {"X-Member-Id": body["member_id"]}


def test_3_search_route_owner_only(client, fake_kakao):
    calls, answers = fake_kakao
    answers["address"] = (200, [_addr_doc("서울 마포구 연남로 12", "연남동 1", 126.92, 37.56)])
    rid, owner = _start(client)
    r = client.get(f"/api/rooms/{rid}/geo/search", params={"q": "연남로 12"}, headers=owner)
    assert r.status_code == 200 and r.json()["candidates"][0]["road"] == "서울 마포구 연남로 12"
    assert client.get(f"/api/rooms/{rid}/geo/search", params={"q": ""}, headers=owner).status_code == 400
    client.post(f"/room/{rid}/chat", json={"member_id": "guest", "nickname": "손님", "message": ""})
    assert client.get(f"/api/rooms/{rid}/geo/search", params={"q": "연남로"},
                      headers={"X-Member-Id": "guest"}).status_code == 403


def test_3_put_geo_saves_and_rerenders(client):
    rid, owner = _start(client)
    bad = {"road": "어딘가", "x": 10.0, "y": 10.0, "src": "search"}
    assert client.put(f"/api/rooms/{rid}/geo", json=bad, headers=owner).status_code == 400
    ok = {"road": "서울 마포구 연남로 12", "detail": "2층", "x": 126.92, "y": 37.56, "src": "postcode"}
    r = client.put(f"/api/rooms/{rid}/geo", json=ok, headers=owner)
    assert r.status_code == 200
    from app import store
    from app.security import sanitize_token
    card = store.read_session(store.read_room(sanitize_token(rid))["session_id"])["prd"]
    assert card["slots"]["location"]["value"] == "서울 마포구 연남로 12 2층"
    assert card["slots"]["location"]["status"] == "filled"
    assert card["location_geo"] == {"road": "서울 마포구 연남로 12", "jibun": "", "detail": "2층",
                                    "x": 126.92, "y": 37.56, "src": "postcode"}
    # 오시는 길 칩을 켜면 미리보기에 실제 지도 칸과 새 주소가 생긴다
    feats = client.get(f"/api/rooms/{rid}/features", headers=owner).json()["features"]
    key = next(f["key"] for f in feats if f["label"] == "오시는 길")
    assert client.put(f"/api/rooms/{rid}/features", json={"key": key, "on": True}, headers=owner).status_code == 200
    html = client.get(f"/api/rooms/{rid}/card/preview", headers=owner).json()["html"]
    assert 'class="s-map__live"' in html and "서울 마포구 연남로 12 2층" in html


def test_3_placeholder_needs_confirm_on_publish(client, monkeypatch):
    rid, owner = _start(client)
    ph = geo.placeholder("마포구")
    r = client.put(f"/api/rooms/{rid}/geo", json=ph, headers=owner)
    assert r.status_code == 200
    from app import store
    from app.security import sanitize_token
    session = store.read_session(store.read_room(sanitize_token(rid))["session_id"])
    assert session["prd"]["slots"]["location"]["status"] == "placeholder"
    assert session["prd"]["location_geo"]["src"] == "placeholder"
