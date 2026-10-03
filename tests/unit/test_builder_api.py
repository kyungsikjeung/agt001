"""빌더 시작·기능·공개 API (BUILDER_CONTRACT §6 테스트 1~6).

외부 호출 없음 (LLM·스크린샷은 conftest 가짜, 시안 파일은 tmp generated_dir).
"""
import re

import pytest

from app import store
from app.config import settings

TEMPLATES = ["pension", "cafe", "restaurant", "salon", "workshop", "academy"]


@pytest.fixture(autouse=True)
def _clear_rate_limit():
    # IP 제한(IP당 10분 5번)을 테스트마다 따로 센다.
    from app.api import inquiries as inquiries_api
    with inquiries_api._lock:
        inquiries_api._hits.clear()


def _start(client, template="cafe"):
    from app.api import inquiries as inquiries_api
    with inquiries_api._lock:  # 한 테스트에서 여러 방을 만들 때 제한에 안 걸리게
        inquiries_api._hits.clear()
    r = client.post("/api/start", json={"template": template})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["builder_url"] == f"/start?room={body['room_id']}"
    assert r.headers["cache-control"] == "no-store"
    return body


def _owner(body):
    return {"X-Member-Id": body["member_id"]}


def _section_ids(html_text: str) -> list:
    return re.findall(r'data-section-id="([^"]+)"', html_text)


def test_start_templates_rate_limit_and_owner_preview(client):
    """테스트 1: 템플릿 6종 성공·모르는 id 400·IP 6번째 429·member_id로 미리보기 200."""
    for template in TEMPLATES:
        body = _start(client, template)
        room = store.read_room(body["room_id"])
        assert room["members"][0]["member_id"] == body["member_id"]  # 첫 입장자가 방장
        session = store.read_session(room["session_id"])
        assert session["state"] == "DONE"
        assert session["design_url"] == f"/design/{session['requirement_id']}"
        assert session["prd"]["builder"] is True
        assert session["prd"]["design_choice"] == "v1"
    assert client.post("/api/start", json={"template": "nope"}).status_code == 400
    assert client.post("/api/start", json={"template": "other"}).status_code == 400
    assert client.post("/api/start", json={}).status_code == 400
    # IP당 10분 5번. 따로 세서 5번은 되고 6번째는 429.
    from app.api import inquiries as inquiries_api
    with inquiries_api._lock:
        inquiries_api._hits.clear()
    for _ in range(5):
        assert client.post("/api/start", json={"template": "cafe"}).status_code == 200
    assert client.post("/api/start", json={"template": "cafe"}).status_code == 429
    # 응답의 member_id는 방장이라 미리보기가 열린다.
    body = _start(client)
    r = client.get(f"/api/rooms/{body['room_id']}/card/preview", headers=_owner(body))
    assert r.status_code == 200
    assert r.json()["variant"] == "v1"


def test_initial_layout_keeps_first_section_only(client):
    """테스트 2: 안마다 보이는 구역이 hero·첫 구역·inquiry뿐."""
    from app.services import archetype as AT
    from app.services import layout_edits as LE
    body = _start(client)
    room = store.read_room(body["room_id"])
    session = store.read_session(room["session_id"])
    card = session["prd"]
    blueprint = AT.blueprint(card)
    assert blueprint is not None
    for pos in range(3):
        vid = blueprint["strategies"][pos]["id"]
        secs = LE.sections(blueprint, pos, (card.get("layout_edits") or {}).get(vid))
        visible = [s["id"] for s in secs if not s["hidden"]]
        first = next(s["id"] for s in secs if s["id"] not in LE.LOCKED)
        assert visible == ["hero", first, "inquiry"], (vid, visible)


def test_features_sections_and_pickup_order(client):
    """테스트 3: hero·inquiry 없음, 숨긴 구역 on=false, dinein엔 order 없음·픽업엔 있음."""
    body = _start(client)
    feats = client.get(f"/api/rooms/{body['room_id']}/features", headers=_owner(body)).json()
    assert feats["variant"] == "v1"
    keys = [f["key"] for f in feats["features"]]
    assert not any(k in ("section:hero", "section:inquiry") for k in keys)
    by_key = {f["key"]: f for f in feats["features"]}
    assert by_key["section:space"]["on"] is False  # 처음엔 숨김
    assert by_key["section:menu"]["on"] is True  # 첫 구역은 보임
    assert by_key["notice"] == {"key": "notice", "label": "공지", "kind": "shop",
                                "on": False, "needs_text": True}
    assert by_key["stamps"]["after_publish"] is True
    assert "section:order" not in keys and not any(k == "order" for k in keys)  # dinein엔 없음
    # 픽업(연락 방법에 픽업)이면 order 칩이 생긴다.
    from app.services import prd_engine as E
    room = store.read_room(body["room_id"])
    with store.session_tx(room["session_id"]) as s:
        E._put(s["prd"], "contact_method", "픽업 주문", E.S.FILLED, 1)
    feats = client.get(f"/api/rooms/{body['room_id']}/features", headers=_owner(body)).json()
    assert feats["features"][-1]["key"] == "order"


def test_put_section_on_off_unknown_and_guest(client):
    """테스트 4: 켜기 → focus·미리보기에 있음 / 끄기 → 없음 / 모르는 id 400 / 다른 참여자 403."""
    body = _start(client)
    rid, headers = body["room_id"], _owner(body)
    r = client.put(f"/api/rooms/{rid}/features", json={"key": "section:space", "on": True}, headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["focus"] == "space"
    assert {f["key"]: f for f in r.json()["features"]}["section:space"]["on"] is True
    html = client.get(f"/api/rooms/{rid}/card/preview", headers=headers).json()["html"]
    assert "space" in _section_ids(html)
    r = client.put(f"/api/rooms/{rid}/features", json={"key": "section:space", "on": False}, headers=headers)
    assert r.status_code == 200 and r.json()["focus"] is None
    html = client.get(f"/api/rooms/{rid}/card/preview", headers=headers).json()["html"]
    assert "space" not in _section_ids(html)
    # 더할 수 있는 구역 켜기 (v1에 없는 sign) → 미리보기에 생긴다.
    r = client.put(f"/api/rooms/{rid}/features", json={"key": "section:sign", "on": True}, headers=headers)
    assert r.status_code == 200 and r.json()["focus"] == "sign"
    html = client.get(f"/api/rooms/{rid}/card/preview", headers=headers).json()["html"]
    assert "sign" in _section_ids(html)
    assert client.put(f"/api/rooms/{rid}/features",
                      json={"key": "section:nope", "on": True}, headers=headers).status_code == 400
    assert client.put(f"/api/rooms/{rid}/features",
                      json={"key": "section:hero", "on": False}, headers=headers).status_code == 400
    client.post(f"/room/{rid}/chat", json={"member_id": "guest", "nickname": "손님", "message": ""})
    guest = {"X-Member-Id": "guest"}
    assert client.get(f"/api/rooms/{rid}/features", headers=guest).status_code == 403
    assert client.put(f"/api/rooms/{rid}/features",
                      json={"key": "section:space", "on": True}, headers=guest).status_code == 403
    assert client.post(f"/api/rooms/{rid}/publish", json={}, headers=guest).status_code == 403


def test_put_notice_and_after_publish_chips(client):
    """테스트 5: 글 없이 켜기 400, 글과 켜기 → 미리보기에 공지 띠 / stamps·order 400 안내."""
    body = _start(client)
    rid, headers = body["room_id"], _owner(body)
    r = client.put(f"/api/rooms/{rid}/features", json={"key": "notice", "on": True}, headers=headers)
    assert r.status_code == 400
    assert r.json()["detail"] == "공지 글이나 사진을 넣어 주세요"
    r = client.put(f"/api/rooms/{rid}/features",
                   json={"key": "notice", "on": True, "text": "10월 3일은 쉬어요"}, headers=headers)
    assert r.status_code == 200
    assert {f["key"]: f for f in r.json()["features"]}["notice"]["on"] is True
    html = client.get(f"/api/rooms/{rid}/card/preview", headers=headers).json()["html"]
    assert "10월 3일은 쉬어요" in html
    r = client.put(f"/api/rooms/{rid}/features", json={"key": "notice", "on": False}, headers=headers)
    assert r.status_code == 200 and r.json()["focus"] is None
    assert {f["key"]: f for f in r.json()["features"]}["notice"]["on"] is False
    for key in ("stamps", "order", "nope"):
        r = client.put(f"/api/rooms/{rid}/features", json={"key": key, "on": True}, headers=headers)
        assert r.status_code == 400
        assert r.json()["detail"] in ("공개한 뒤 사장님 화면에서 켤 수 있어요", "없는 기능이에요")


def test_publish_login_confirm_force(client, monkeypatch):
    """테스트 6: 로그인 필요면 need=login, 빈칸이면 need=confirm, force로 공개 → site_url."""
    body = _start(client)
    rid, headers = body["room_id"], _owner(body)
    monkeypatch.setattr(settings, "publish_login_required", True)
    r = client.post(f"/api/rooms/{rid}/publish", json={}, headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["need"] == "login"
    assert r.json()["message"].split("\n")[0].startswith("공개하려면 먼저 로그인")
    assert len(r.json()["login_urls"]) == 2
    assert all(f"/auth/{p}/start?next=%2Fstart%3Froom%3D{rid}" in u
               for p, u in zip(("kakao", "google"), r.json()["login_urls"]))
    monkeypatch.setattr(settings, "publish_login_required", False)
    r = client.post(f"/api/rooms/{rid}/publish", json={}, headers=headers)
    assert r.status_code == 200
    assert r.json()["need"] == "confirm"
    assert r.json()["message"].startswith("공개 전에 확인해 주세요")
    r = client.post(f"/api/rooms/{rid}/publish", json={"force": True}, headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True and r.json()["site_url"]
    room = store.read_room(rid)
    req = store.read_session(room["session_id"])["requirement_id"]
    published = (settings.generated_dir / req / "published" / "index.html").read_text(encoding="utf-8")
    assert published.count("data-edit-mode") == 0 and published.count("agt-edit") == 0
    # 채팅방에도 같은 결과가 남는다.
    texts = [m["text"] for m in store.read_messages(rid, 0) if m["member_id"] == "system"]
    assert any("사이트를 열었어요" in t for t in texts)


def test_put_card_choice_sets_design_choice(client):
    """B1: PUT /card choice로 모양 바꾸기. 미리보기 기본 안도 따라간다."""
    body = _start(client)
    rid, headers = body["room_id"], _owner(body)
    r = client.put(f"/api/rooms/{rid}/card", json={"choice": "v2"}, headers=headers)
    assert r.status_code == 200
    assert r.json()["choice"] == "v2"
    assert client.get(f"/api/rooms/{rid}/card/preview", headers=headers).json()["variant"] == "v2"
    assert client.get(f"/api/rooms/{rid}/features", headers=headers).json()["variant"] == "v2"
    assert client.put(f"/api/rooms/{rid}/card", json={"choice": "v9"}, headers=headers).status_code == 422


def test_start_page_missing_build_is_404(client):
    """§2.6: 빌드 전(/start 서빙 파일 없음)에는 404."""
    page = settings.frontend_dist_dir / "builder.html"
    if page.is_file():
        assert client.get("/start").status_code == 200
    else:
        assert client.get("/start").status_code == 404


def test_builder_feature_records_chip_id(client, monkeypatch):
    """builder_feature 사건에 어떤 칩인지(ref) 남긴다 — 칩별 인기 보기 (B4)."""
    from app.api import start as start_api
    seen = []
    monkeypatch.setattr(start_api.funnel, "record",
                        lambda event, **kw: seen.append((event, kw.get("props"))) or True)
    body = _start(client)
    rid, headers = body["room_id"], _owner(body)
    client.put(f"/api/rooms/{rid}/features", json={"key": "section:space", "on": True}, headers=headers)
    client.put(f"/api/rooms/{rid}/features", json={"key": "notice", "on": True, "text": "쉬어요"}, headers=headers)
    feats = [p for e, p in seen if e == "builder_feature"]
    assert feats == [{"kind": "section", "ref": "space", "choice": "on"},
                     {"kind": "notice", "ref": "notice", "choice": "on"}]


def test_app_shell_pages_are_no_cache(client):
    """랜딩·빌더 화면 틀은 no-cache — 추측 캐시로 새 빌드 뒤에도 옛 화면이 보이던 것 (10/1)."""
    assert client.get("/").headers["cache-control"] == "no-cache"
    r = client.get("/start")
    if r.status_code == 200:
        assert r.headers["cache-control"] == "no-cache"


def test_builder_notice_edit_keeps_popup(client):
    """빌더 공지 고치기 창(칩 다시 누름)으로 글만 바꿔도 사장님이 켠 팝업은 그대로 (10/4)."""
    body = _start(client)
    rid, headers = body["room_id"], _owner(body)
    r = client.put(f"/api/rooms/{rid}/card", json={"notice": {"text": "추석 휴무", "popup": True}}, headers=headers)
    assert r.status_code == 200 and r.json()["notice"]["popup"] is True
    r = client.put(f"/api/rooms/{rid}/features",
                   json={"key": "notice", "on": True, "text": "추석 연휴 9/16~18 휴무"}, headers=headers)
    assert r.status_code == 200
    card = client.get(f"/api/rooms/{rid}/card", headers=headers).json()
    assert card["notice"] == {"text": "추석 연휴 9/16~18 휴무", "popup": True, "photos": []}
