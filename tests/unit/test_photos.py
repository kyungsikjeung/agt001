"""채팅방 사진 (계약 §4): 위치 정보 제거·축소·JPEG, 카드와 시안에 반영, 형식·크기·권한 검사."""
import io

from PIL import Image

from app import store
from app.services import design, design_variants as DV


def _room(client):
    rid = client.post("/room").json()["room_id"]
    client.post(f"/room/{rid}/chat", json={"member_id": "owner", "nickname": "사장님", "message": "카페 모퉁이 해요"})
    return rid


def _jpeg_with_gps(size=(3000, 2000)):
    img = Image.new("RGB", size, (120, 80, 40))
    exif = Image.Exif()
    exif[0x010F] = "PhoneMaker"
    gps = exif.get_ifd(0x8825)  # 위치 정보(GPS)
    gps[1], gps[2], gps[3], gps[4] = "N", (37.0, 33.0, 0.0), "E", (126.0, 58.0, 0.0)
    buf = io.BytesIO()
    img.save(buf, "JPEG", exif=exif)
    return buf.getvalue()


def test_upload_strips_exif_and_resizes(client):
    rid = _room(client)
    r = client.post(f"/room/{rid}/photos", files={"file": ("a.jpg", _jpeg_with_gps(), "image/jpeg")},
                    data={"caption": "매장 전경"}, headers={"X-Member-Id": "owner"})
    assert r.status_code == 201
    url = r.json()["url"]
    got = client.get(url)
    assert got.status_code == 200 and got.headers["content-type"] == "image/jpeg"
    img = Image.open(io.BytesIO(got.content))
    assert max(img.size) == 1600
    assert not img.getexif()  # 위치·기기 정보 없음
    msgs = client.get(f"/room/{rid}/messages", headers={"X-Member-Id": "owner"}).json()["messages"]
    assert msgs[-1]["kind"] == "photo" and msgs[-1]["photo"]["url"] == url
    card = store.read_session(store.read_room(rid)["session_id"])["prd"]
    assert card["photos"][0]["url"] == url and card["photos"][0]["caption"] == "매장 전경"


def test_photo_goes_into_design(client):
    rid = _room(client)
    client.post(f"/room/{rid}/photos", files={"file": ("a.jpg", _jpeg_with_gps((800, 600)), "image/jpeg")},
                headers={"X-Member-Id": "owner"})
    card = store.read_session(store.read_room(rid)["session_id"])["prd"]
    spec = DV.base_spec(card)
    hero = next(s for s in spec["sections"] if s["type"] == "hero")
    assert hero["content"]["image"].startswith("/uploads/")


def test_rejects_non_image_big_and_strangers(client):
    rid = _room(client)
    bad = client.post(f"/room/{rid}/photos", files={"file": ("a.txt", b"hello", "text/plain")}, headers={"X-Member-Id": "owner"})
    assert bad.status_code == 400
    big = client.post(f"/room/{rid}/photos", files={"file": ("a.jpg", b"\xff" * (10 * 1024 * 1024 + 10), "image/jpeg")},
                      headers={"X-Member-Id": "owner"})
    assert big.status_code == 400
    other = client.post(f"/room/{rid}/photos", files={"file": ("a.jpg", _jpeg_with_gps((100, 100)), "image/jpeg")},
                        headers={"X-Member-Id": "stranger"})
    assert other.status_code == 404


def test_delete_by_uploader_or_owner(client):
    rid = _room(client)
    client.post(f"/room/{rid}/chat", json={"member_id": "guest", "nickname": "손님", "message": ""})
    pid = client.post(f"/room/{rid}/photos", files={"file": ("a.jpg", _jpeg_with_gps((100, 100)), "image/jpeg")},
                      headers={"X-Member-Id": "owner"}).json()["id"]
    assert client.delete(f"/room/{rid}/photos/{pid}", headers={"X-Member-Id": "guest"}).status_code == 403
    assert client.delete(f"/room/{rid}/photos/{pid}", headers={"X-Member-Id": "owner"}).status_code == 204
    assert store.read_session(store.read_room(rid)["session_id"])["prd"]["photos"] == []


def test_upload_path_is_not_traversable(client):
    assert client.get("/uploads/abc/..%2F..%2Fetc.jpg").status_code == 404
    assert client.get("/uploads/abc/x.png").status_code == 404


def test_photo_after_design_refreshes_designs_and_site(client):
    """시안·공개 뒤에 올린 사진이 시안 3안과 공개본에 들어가고 방에 알린다(워크플로 검토 9/26)."""
    from app.services import photos
    rid = _room(client)
    session = store.read_session(store.read_room(rid)["session_id"])
    card = session["prd"]
    design.render_design(session["requirement_id"], "web", [], 0, "", card=card)
    design.publish_choice(session["requirement_id"], card, "v1")
    client.post(f"/room/{rid}/photos", files={"file": ("a.jpg", _jpeg_with_gps((800, 600)), "image/jpeg")},
                headers={"X-Member-Id": "owner"})
    with store.session_tx(store.read_room(rid)["session_id"]) as s2:
        s2["design_url"] = f"/design/{s2['requirement_id']}"
        s2["prd"]["published"] = "v1"
    photos.refresh_designs(rid, session["requirement_id"])
    site = client.get(f"/site/{session['requirement_id']}/").text
    assert "/uploads/" in site
    msgs = client.get(f"/room/{rid}/messages", headers={"X-Member-Id": "owner"}).json()["messages"]
    assert "시안에 넣었어요" in msgs[-1]["text"]


def test_kakao_channel_link_is_captured(client):
    rid = _room(client)
    client.post(f"/room/{rid}/chat", json={"member_id": "owner", "nickname": "사장님",
                                           "message": "채널은 https://pf.kakao.com/_abcDEF/chat 이에요"})
    card = store.read_session(store.read_room(rid)["session_id"])["prd"]
    assert card["kakao_channel_url"] == "https://pf.kakao.com/_abcDEF"
    spec = DV.base_spec(card)
    kakao = next(s for s in spec["sections"] if s["variant"] == "kakao-channel")
    assert kakao["content"]["kakao_channel_url"] == "https://pf.kakao.com/_abcDEF"


def test_video_link_goes_into_design(client):
    rid = _room(client)
    client.post(f"/room/{rid}/chat", json={"member_id": "owner", "nickname": "사장님",
                                           "message": "가게 영상이에요 https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=10"})
    card = store.read_session(store.read_room(rid)["session_id"])["prd"]
    assert card["videos"] == ["https://www.youtube.com/watch?v=dQw4w9WgXcQ"] or card["videos"][0].endswith("dQw4w9WgXcQ")
    types = [(s["type"], s["variant"]) for s in DV.base_spec(card)["sections"]]
    assert ("video", "card") in types
    from app.services.site_render import render_site
    html = render_site(DV.base_spec(card), kind="cafe", public=True)
    assert "i.ytimg.com/vi/dQw4w9WgXcQ" in html and "<iframe" not in html


def test_early_photo_ask_once_for_photo_first_industries():
    """D36: 식당·카페·펜션은 가게 이름이 정해진 직후 사진을 한 번 먼저 부탁한다(방이 있을 때만)."""
    from app.services import chat_flow, prd_engine as E, prd_schema as S
    card = E.new_card()
    card["industry"] = "restaurant"
    assert chat_flow._early_photo_ask(card, room={}) == ""  # 가게 이름 전에는 묻지 않는다
    E._put(card, "shop_name", "황남밥상", S.FILLED, 1)
    first = chat_flow._early_photo_ask(card, room={})
    assert "1) 지금 올릴게요" in first and "대표 메뉴" in first and "아래 '사진' 버튼" in first
    assert chat_flow._early_photo_ask(card, room={}) == ""  # 한 번만
    other = E.new_card()
    other["industry"] = "academy"
    E._put(other, "shop_name", "바른수학", S.FILLED, 1)
    assert chat_flow._early_photo_ask(other, room={}) == ""  # 사진이 덜 중요한 업종은 요약 때만
    with_photo = E.new_card()
    with_photo["industry"] = "cafe"
    E._put(with_photo, "shop_name", "모퉁이커피", S.FILLED, 1)
    with_photo["photos"] = [{"url": "/uploads/x/a.jpg"}]
    assert chat_flow._early_photo_ask(with_photo, room={}) == ""  # 이미 올렸으면 묻지 않는다


def test_deleted_photo_leaves_published_site(client, monkeypatch):
    """지운 사진은 공개 사이트에서도 빠져야 한다. 전에는 지워도 공개본을 다시 만들지 않아 깨진 이미지가 남았다."""
    from app.services import photos
    monkeypatch.setattr(photos, "_refresh_designs_async", photos.refresh_designs)  # 테스트는 뒤 작업 대신 바로
    rid = _room(client)
    session = store.read_session(store.read_room(rid)["session_id"])
    design.render_design(session["requirement_id"], "web", [], 0, "", card=session["prd"])
    with store.session_tx(session["id"] if "id" in session else store.read_room(rid)["session_id"]) as s2:
        s2["design_url"] = f"/design/{s2['requirement_id']}"
        s2["prd"]["published"] = "v1"
    design.publish_choice(session["requirement_id"], store.read_session(store.read_room(rid)["session_id"])["prd"], "v1")
    pid = client.post(f"/room/{rid}/photos", files={"file": ("a.jpg", _jpeg_with_gps((800, 600)), "image/jpeg")},
                      headers={"X-Member-Id": "owner"}).json()["id"]
    assert pid in client.get(f"/site/{session['requirement_id']}/").text
    assert client.delete(f"/room/{rid}/photos/{pid}", headers={"X-Member-Id": "owner"}).status_code == 204
    assert pid not in client.get(f"/site/{session['requirement_id']}/").text


def test_photo_choice_answer_parsing():
    """D48: 사진 말이 분명할 때만 가로챈다. 번호만('2')은 엔진 선택지와 겹치므로 받지 않는다."""
    from app.services import chat_flow
    assert chat_flow.photo_answer("지금 올릴게요") == "now"
    assert chat_flow.photo_answer("바로 올릴게요") == "now"
    assert chat_flow.photo_answer("나중에 올릴게요") == "later"
    assert chat_flow.photo_answer("사진이 없어요") == "none"
    assert chat_flow.photo_answer("예시 그림으로") == "none"
    assert chat_flow.photo_answer("2") is None
    assert chat_flow.photo_answer("전화는 010-1234-5678이에요") is None
    assert chat_flow.photo_answer("x" * 21) is None


def test_photo_choice_budget_untouched_and_once():
    """D48: 사진 질문은 질문 예산을 쓰지 않고 한 번만. '없어요'면 다시 묻지 않는다."""
    from app.services import chat_flow, prd_engine as E, prd_schema as S
    card = E.new_card()
    card["industry"] = "cafe"
    E._put(card, "shop_name", "모퉁이커피", S.FILLED, 1)
    asked_before = card["asked"]
    assert "1) 지금 올릴게요" in chat_flow._early_photo_ask(card, room={})
    assert card["asked"] == asked_before  # 예산 미소모
    card["photo_choice"] = "none"
    assert chat_flow._early_photo_ask(card, room={}) == ""
    assert chat_flow._photo_later_reminder(card) == ""  # '없어요'는 조용히


def test_photo_later_reminded_once():
    """D48: '나중에'는 시안 때 한 번만 다시 알린다."""
    from app.services import chat_flow
    card = {"photos": [], "photo_choice": "later"}
    first = chat_flow._photo_later_reminder(card)
    assert "나중에 올릴게요" in first
    assert chat_flow._photo_later_reminder(card) == ""
    card2 = {"photos": [{"url": "/uploads/x/a.jpg"}], "photo_choice": "later"}
    assert chat_flow._photo_later_reminder(card2) == ""  # 올렸으면 조용히
