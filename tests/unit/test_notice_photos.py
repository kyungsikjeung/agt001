"""공지에 사진 (NOTICE_PHOTO_CONTRACT §5 테스트 1~3): 서버 쪽.

공지 사진은 이 방에 notice 태그로 올린 사진만 받고, 첫 화면·공간·메뉴 사진으로는 쓰지 않는다.
"""
from app import store
from app.api import card as card_api
from app.services import card_data
from app.services import design_variants as DV
from app.services import photo_needs
from app.services import photos
from app.services import prd_engine as E
from app.services import prd_schema as S
from app.services import site_data

NOTICE_TAG = "notice"


def _cafe_card():
    card = E.new_card("cafe")
    E._put(card, "business_type", "카페", S.FILLED, 1)
    E._put(card, "shop_name", "모퉁이커피", S.FILLED, 1)
    E._put(card, "offerings", ["아메리카노", "카페라떼"], S.FILLED, 1)
    E._put(card, "phone", "02-123-4567", S.FILLED, 1)
    E._put(card, "hours", "매일 10~21시", S.FILLED, 1)
    E._put(card, "location", "서울 마포구 연남로 12", S.FILLED, 1)
    card["turn"] = 1
    return card


def _photo(card, url, tag=None, caption=None):
    out = {"id": url.rsplit("/", 1)[-1].split(".")[0], "url": url, "caption": caption}
    if tag is not None:
        out["tag"] = tag
    card.setdefault("photos", []).append(out)
    return url


def _room(client):
    rid = client.post("/room").json()["room_id"]
    client.post(f"/room/{rid}/chat", json={"member_id": "owner", "nickname": "사장님", "message": "카페예요"})
    client.post(f"/room/{rid}/chat", json={"member_id": "guest", "nickname": "손님", "message": ""})
    return rid


def _sid(rid):
    return store.read_room(rid)["session_id"]


def _notice_photo_urls(rid, count):
    """이 방에 notice 태그로 올린 사진 주소."""
    with store.session_tx(_sid(rid)) as s:
        card = s["prd"] or _cafe_card()
        for i in range(count):
            card.setdefault("photos", []).append(
                {"id": f"n{i}", "url": f"/uploads/{rid}/n{i}.jpg", "caption": None, "tag": NOTICE_TAG})
        s["prd"] = card
    return photos.notice_urls(store.read_session(_sid(rid))["prd"])


def _hero_image(card):
    spec = DV.variants(card)[0]["spec"]
    return next(s for s in spec["sections"] if s["id"] == "hero")["content"].get("image")


# --- §5-1: 태그와 사진 후보 ---

def test_1_notice_tag_allowed():
    card = _cafe_card()
    assert photo_needs.valid_tag(card, NOTICE_TAG) is True
    assert photo_needs.valid_tag(card, "hero") is True
    assert photo_needs.valid_tag(card, "space") is True
    assert photo_needs.valid_tag(card, "item:없는이름") is False


def test_1_notice_photo_is_not_site_candidate():
    """공지 사진만 올린 카드는 첫 화면이 예시 사진 그대로, 사장님 사진을 넣으면 다시 쓰인다."""
    card = _cafe_card()
    notice_url = _photo(card, "/uploads/r1/n0.jpg", NOTICE_TAG, "3월 휴강")
    assert photos.site_photos(card) == []
    assert photos.notice_urls(card) == [notice_url]
    assert not str(_hero_image(card) or "").startswith("/uploads/")
    assert card_data.item_photo(card, "아메리카노") is None

    owner_url = _photo(card, "/uploads/r1/o0.jpg", "space", "가게 앞")
    assert photos.site_photos(card) == [
        {"id": "o0", "url": owner_url, "caption": "가게 앞", "tag": "space"}]
    assert _hero_image(card) == owner_url


def test_1_site_data_notice_photos_unchanged():
    """공지 사진 주소는 그대로 나간다. 예전 {text, popup}은 photos=[]로 읽는다 (§0)."""
    card = _cafe_card()
    mine = _photo(card, "/uploads/r1/n0.jpg", NOTICE_TAG)

    card_api.save_notice(card, "3월 3일은 쉬어요", photos=[mine])
    out = site_data.resolve(DV.variants(card)[0]["spec"], card, archetype="A")
    assert out["notice"] == {"text": "3월 3일은 쉬어요", "photos": [mine], "popup": False}

    old = _cafe_card()
    old["notice"] = {"text": "쉬어요", "popup": True}
    out = site_data.resolve(DV.variants(old)[0]["spec"], old, archetype="A")
    assert out["notice"] == {"text": "쉬어요", "photos": [], "popup": True}


# --- §5-2: save_notice ---

def test_2_save_notice_text_photo_both_and_empty():
    card = _cafe_card()
    n1 = _photo(card, "/uploads/r1/n0.jpg", NOTICE_TAG)
    n2 = _photo(card, "/uploads/r1/n1.jpg", NOTICE_TAG)
    _photo(card, "/uploads/r1/o0.jpg", "space")  # 공지 사진 아님

    # 글만
    assert card_api.save_notice(card, "  10월 3일은 쉬어요  ") is True
    assert card["notice"] == {"text": "10월 3일은 쉬어요", "photos": [], "popup": False}
    assert card_api.save_notice(card, "10월 3일은 쉬어요") is False  # 결과가 같으면 False

    # 사진만
    assert card_api.save_notice(card, "", photos=[n1]) is True
    assert card["notice"]["text"] == "" and card["notice"]["photos"] == [n1]

    # 둘 다
    assert card_api.save_notice(card, "쉬어요", True, [n1, n2]) is True
    assert card["notice"] == {"text": "쉬어요", "popup": True, "photos": [n1, n2]}

    # 둘 다 빔 → 끔
    assert card_api.save_notice(card, "", True, []) is True
    assert "notice" not in card


def test_2_save_notice_drops_foreign_and_caps_five():
    card = _cafe_card()
    mine = [_photo(card, f"/uploads/r1/n{i}.jpg", NOTICE_TAG) for i in range(6)]
    assert card_api.save_notice(
        card, "공지", False,
        ["/uploads/다른방/x.jpg", mine[0], "/uploads/r1/태그없음.jpg", mine[1]]) is True
    assert card["notice"]["photos"] == [mine[0], mine[1]]  # 남의 방·태그 없는 주소 버림
    card_api.save_notice(card, "공지", False, mine)  # 6장 → 5장, 순서 그대로
    assert card["notice"]["photos"] == mine[:5]


def test_api_card_notice_photos(client):
    """PUT /card: notice.photos를 넘기면 고쳐지고, 6장 넘으면 422로 막는다."""
    rid = _room(client)
    h = {"X-Member-Id": "owner"}
    urls = _notice_photo_urls(rid, 6)
    r = client.put(f"/api/rooms/{rid}/card",
                   json={"notice": {"text": "쉬어요", "photos": urls[:5]}}, headers=h)
    assert r.status_code == 200
    assert r.json()["notice"]["photos"] == urls[:5]
    assert client.put(f"/api/rooms/{rid}/card",
                      json={"notice": {"text": "쉬어요", "photos": urls[:6]}}, headers=h).status_code == 422
    r = client.put(f"/api/rooms/{rid}/card", json={"notice": {"text": "", "photos": []}}, headers=h)
    assert r.json()["notice"] == {"text": "", "popup": False}


def test_api_features_notice_needs_text_or_photo(client):
    """§5-3: 글·사진 없이 켜기 400, 사진만으로 켜기, 칩 on."""
    from app.api import inquiries as inquiries_api

    with inquiries_api._lock:
        inquiries_api._hits.clear()
    body = client.post("/api/start", json={"template": "cafe"}).json()
    rid, h = body["room_id"], {"X-Member-Id": body["member_id"]}
    url = _notice_photo_urls(rid, 1)[0]

    r = client.put(f"/api/rooms/{rid}/features", json={"key": "notice", "on": True}, headers=h)
    assert r.status_code == 400
    assert r.json()["detail"] == "공지 글이나 사진을 넣어 주세요"
    r = client.put(f"/api/rooms/{rid}/features",
                   json={"key": "notice", "on": True, "photos": [url]}, headers=h)
    assert r.status_code == 200, r.text
    assert {f["key"]: f for f in r.json()["features"]}["notice"]["on"] is True
    card = store.read_session(_sid(rid))["prd"]
    assert card["notice"]["text"] == "" and card["notice"]["photos"] == [url]
    r = client.put(f"/api/rooms/{rid}/features", json={"key": "notice", "on": False}, headers=h)
    assert r.status_code == 200
    assert {f["key"]: f for f in r.json()["features"]}["notice"]["on"] is False
    assert "notice" not in (store.read_session(_sid(rid))["prd"] or {})


def test_api_chip_on_and_fix_targets_current(client):
    """§1-5·§1-6: 글 없어도 사진 있으면 칩 on, fix-targets notice 칸은 글 또는 '사진 N장'."""
    rid = _room(client)
    h = {"X-Member-Id": "owner"}
    urls = _notice_photo_urls(rid, 2)
    assert client.put(f"/api/rooms/{rid}/features",
                      json={"key": "notice", "on": True, "photos": urls[:1]}, headers=h).status_code == 200
    feats = {f["key"]: f for f in client.get(f"/api/rooms/{rid}/features", headers=h).json()["features"]}
    assert feats["notice"]["on"] is True

    targets = client.get(f"/api/rooms/{rid}/fix-targets", headers=h).json()["targets"]
    assert next(t for t in targets if t["key"] == "notice")["current"] == "사진 1장"

    with store.session_tx(_sid(rid)) as s:
        card_api.save_notice(s["prd"], "10월 휴무", photos=urls)
    targets = client.get(f"/api/rooms/{rid}/fix-targets", headers=h).json()["targets"]
    assert next(t for t in targets if t["key"] == "notice")["current"] == "10월 휴무"

    with store.session_tx(_sid(rid)) as s:
        s["prd"].pop("notice", None)
    keys = [t["key"] for t in client.get(f"/api/rooms/{rid}/fix-targets", headers=h).json()["targets"]]
    assert "notice" not in keys
