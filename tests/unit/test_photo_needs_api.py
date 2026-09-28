"""항목 사진 태그 (BETA_FLOW_PLAN §2.7): 올리기 태그 저장·걸러내기, 카드 photo_tags."""
import io

from PIL import Image

from app import store
from app.services import prd_engine as E
from app.services import prd_schema as S


def _room(client):
    rid = client.post("/room").json()["room_id"]
    client.post(f"/room/{rid}/chat", json={"member_id": "owner", "nickname": "사장님",
                                           "message": "미용실이에요"})
    with store.room_tx(rid) as (_, session):
        card = session["prd"]
        card["industry"] = "salon"
        E._put(card, "offerings", ["컷", "펌", "염색"], S.FILLED, 1)
    return rid


def _jpeg():
    img = Image.new("RGB", (100, 100), (120, 80, 40))
    buf = io.BytesIO()
    img.save(buf, "JPEG")
    return buf.getvalue()


def test_upload_with_item_tag_stores_tag(client):
    rid = _room(client)
    r = client.post(f"/room/{rid}/photos", files={"file": ("a.jpg", _jpeg(), "image/jpeg")},
                    data={"tag": "item:펌"}, headers={"X-Member-Id": "owner"})
    assert r.status_code == 201
    card = store.read_session(store.read_room(rid)["session_id"])["prd"]
    assert card["photos"][-1]["tag"] == "item:펌"


def test_upload_with_bad_tag_drops_tag(client):
    rid = _room(client)
    r = client.post(f"/room/{rid}/photos", files={"file": ("a.jpg", _jpeg(), "image/jpeg")},
                    data={"tag": "item:없는항목"}, headers={"X-Member-Id": "owner"})
    assert r.status_code == 201
    card = store.read_session(store.read_room(rid)["session_id"])["prd"]
    assert "tag" not in card["photos"][-1]


def test_card_has_photo_tags(client):
    rid = _room(client)
    v = client.get(f"/api/rooms/{rid}/card", headers={"X-Member-Id": "owner"}).json()
    tags = v["photo_tags"]
    assert {"tag": "item:펌", "label": "펌"} in tags
    assert tags[-1] == {"tag": "space", "label": "가게·공간"}
