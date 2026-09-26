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
    assert "사진을 시안에 넣었어요" in msgs[-1]["text"]


def test_kakao_channel_link_is_captured(client):
    rid = _room(client)
    client.post(f"/room/{rid}/chat", json={"member_id": "owner", "nickname": "사장님",
                                           "message": "채널은 https://pf.kakao.com/_abcDEF/chat 이에요"})
    card = store.read_session(store.read_room(rid)["session_id"])["prd"]
    assert card["kakao_channel_url"] == "https://pf.kakao.com/_abcDEF"
    spec = DV.base_spec(card)
    kakao = next(s for s in spec["sections"] if s["variant"] == "kakao-channel")
    assert kakao["content"]["kakao_channel_url"] == "https://pf.kakao.com/_abcDEF"
