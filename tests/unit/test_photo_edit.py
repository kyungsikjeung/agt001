"""빌더에서 사진 고치기 (PHOTO_EDIT_CONTRACT §7 테스트 1-9, 서비스 수준).

Gemini는 가짜로 둔다 (ai_images의 httpx.post를 끼워넣고 보낸 JSON을 잡는다).
"""
import base64
import hashlib
import io
import time

import pytest
from PIL import Image, ImageStat

from app.config import settings
from app.services import ai_images as AI
from app.services import design_variants as DV
from app.services import photo_edit as PE
from app.services import photos
from app.services import prd_engine as E
from app.services import prd_schema as S


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


def _pension_card():
    card = E.new_card("pension")
    E._put(card, "business_type", "펜션", S.FILLED, 1)
    E._put(card, "shop_name", "숲속의쉼", S.FILLED, 1)
    E._put(card, "offerings", ["101호 복층", "102호 온돌"], S.FILLED, 1)
    E._put(card, "phone", "033-000-1111", S.FILLED, 1)
    E._put(card, "location", "강원 평창군 봉평면", S.FILLED, 1)
    card["turn"] = 1
    return card


def _jpeg_bytes(size=(800, 600), color=(120, 80, 40)):
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, "JPEG", quality=90)
    return buf.getvalue()


def _put_upload(room_id, fid, data):
    folder = photos._dir(room_id)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{fid}.jpg").write_bytes(data)
    return photos.url_for(room_id, fid)


@pytest.fixture
def room_iso(tmp_path, monkeypatch):
    """생성물 폴더를 테스트용으로 둔다."""
    monkeypatch.setattr(settings, "generated_dir", tmp_path)
    return "room1"


@pytest.fixture
def fake_gemini(monkeypatch):
    """가짜 Gemini: 보낸 JSON을 잡고 PNG를 돌려준다."""
    monkeypatch.setattr("app.services.keystore.get", lambda name: "k")
    seen = {}

    class _Resp:
        status_code = 200
        text = "ok"

        def json(self):
            return {"candidates": [{"content": {"parts": [
                {"inlineData": {"mimeType": "image/png",
                                "data": base64.b64encode(_jpeg_bytes((400, 300))).decode()}}]}}]}

    def fake_post(url, **kwargs):
        seen["url"] = url
        seen["json"] = kwargs.get("json")
        seen["headers"] = kwargs.get("headers")
        return _Resp()

    monkeypatch.setattr(AI.httpx, "post", fake_post)
    return seen


def _session(card):
    return {"id": "sess1", "prd": card, "photo_candidates": {}}


def test_1_resolve_target(room_iso):
    """첫 화면 예시→hero·example, 사장님 사진→owner, 사진첩 두 번째→gallery-2,
    메뉴 항목→item:<이름>, 모르는 src는 ValueError."""
    card = _cafe_card()
    spec = DV.variants(card)[0]["spec"]
    hero_url = next(s for s in spec["sections"] if s["id"] == "hero")["content"]["image"]
    assert hero_url.startswith("/art/ex/")
    got = PE.resolve_target(card, spec, "hero", hero_url, 0)
    assert got["target"] == "hero" and got["kind"] == "example"
    assert got["current_url"] == hero_url

    url = _put_upload(room_iso, "p1", _jpeg_bytes())
    card["photos"] = [{"id": "p1", "url": url}]
    spec2 = DV.variants(card)[0]["spec"]
    hero_url2 = next(s for s in spec2["sections"] if s["id"] == "hero")["content"]["image"]
    assert hero_url2 == url
    got = PE.resolve_target(card, spec2, "hero", url, 0)
    assert got["target"] == "hero" and got["kind"] == "owner"

    url2 = _put_upload(room_iso, "p2", _jpeg_bytes())
    url3 = _put_upload(room_iso, "p3", _jpeg_bytes())
    card["photos"].append({"id": "p2", "url": url2})
    card["photos"].append({"id": "p3", "url": url3})
    spec3 = DV.variants(card)[0]["spec"]
    space = next(s for s in spec3["sections"] if s["id"] == "space")
    got = PE.resolve_target(card, spec3, "space", space["content"]["items"][1]["src"], 1)
    assert got["target"] == "gallery-2"

    pension = _pension_card()
    pspec = DV.variants(pension)[0]["spec"]
    rooms = next(s for s in pspec["sections"] if s["id"] == "rooms")
    first = rooms["content"]["rooms"][0]
    got = PE.resolve_target(pension, pspec, "rooms", first["image"], 0)
    assert got["target"] == "item:" + first["name"] and got["kind"] == "example"

    with pytest.raises(ValueError, match="이 사진은 여기서 고칠 수 없어요"):
        PE.resolve_target(card, spec3, "space", "/uploads/room1/none.jpg", 9)
    with pytest.raises(ValueError, match="이 사진은 여기서 고칠 수 없어요"):
        PE.resolve_target(card, spec3, "nosuch", url, 0)


def test_2_adjust_all_actions(room_iso):
    """보정 5종: 크기·비율, 밝게는 평균 밝기 증가, EXIF 없음, 원본 그대로."""
    raw = _jpeg_bytes((800, 600))
    before = _put_upload(room_iso, "orig", raw)
    before_bytes = (photos._dir(room_iso) / "orig.jpg").read_bytes()
    dark = ImageStat.Stat(Image.open(io.BytesIO(raw)).convert("L")).mean[0]

    brighter = PE.adjust(raw, "brighter")
    assert ImageStat.Stat(Image.open(io.BytesIO(brighter)).convert("L")).mean[0] > dark
    assert PE.adjust(raw, "warmer")[:2] == b"\xff\xd8"
    assert PE.adjust(raw, "sharper")[:2] == b"\xff\xd8"

    square = Image.open(io.BytesIO(PE.adjust(raw, "square")))
    assert square.size[0] == square.size[1]
    wide = Image.open(io.BytesIO(PE.adjust(raw, "wide")))
    assert abs(wide.size[0] / wide.size[1] - 4 / 3) < 0.02

    for action in PE.actions_for("owner"):
        out = Image.open(io.BytesIO(PE.adjust(raw, action)))
        assert max(out.size) <= 1600 and not out.getexif()
    assert (photos._dir(room_iso) / "orig.jpg").read_bytes() == before_bytes
    assert before.endswith("orig.jpg")
    with pytest.raises(ValueError):
        PE.adjust(raw, "bogus")


def test_3_owner_words_rule(room_iso):
    """사장님 사진 + 내용 바꾸는 말→400 안내, 밝게→brighter 보정."""
    card = _cafe_card()
    url = _put_upload(room_iso, "p1", _jpeg_bytes())
    card["photos"] = [{"id": "p1", "url": url, "tag": "hero"}]
    spec = DV.variants(card)[0]["spec"]
    target = PE.resolve_target(card, spec, "hero", url, 0)
    assert target["kind"] == "owner"
    session = _session(card)

    with pytest.raises(ValueError, match="실제 사진은"):
        PE.make_candidate(room_iso, session, target, instruction="배경 바꿔 줘")
    assert PE.action_from_words("좀 밝게 해줘") == "brighter"
    assert PE.action_from_words("배경 바꿔 줘") is None
    got = PE.make_candidate(room_iso, session, target, instruction="좀 밝게 해줘")
    assert got["before_url"] == url and got["after_url"].endswith(".jpg")
    assert "ai_images" not in card  # 후보일 뿐 카드는 그대로


def test_4_ai_edit_sends_only_image_and_words(room_iso, fake_gemini):
    """AI 고치기: 본문에 inlineData + 프롬프트, 가게 이름·전화·주소 없음,
    결과는 후보로만 저장되고 카드는 그대로."""
    card = _cafe_card()
    spec = DV.variants(card)[0]["spec"]
    hero_url = next(s for s in spec["sections"] if s["id"] == "hero")["content"]["image"]
    target = PE.resolve_target(card, spec, "hero", hero_url, 0)
    assert target["kind"] == "example"
    session = _session(card)
    got = PE.make_candidate(room_iso, session, target, instruction="여름 느낌으로")
    assert got["before_url"] == hero_url

    body = fake_gemini["json"]
    parts = body["contents"][0]["parts"]
    assert parts[0]["inlineData"]["mimeType"] == "image/jpeg"
    assert parts[0]["inlineData"]["data"]
    prompt = parts[1]["text"]
    assert "여름 느낌으로" in prompt and "photorealistic" in prompt
    dumped = str(body)
    for secret in ("모퉁이커피", "02-123-4567", "연남로", "마포구", "10~21시"):
        assert secret not in dumped
    assert "hero" not in card.get("ai_images", {})
    assert (photos._dir(room_iso) / (got["after_url"].rsplit("/", 1)[-1])).exists()


def test_5_forbidden_words_and_numbers_stripped(room_iso, fake_gemini):
    """금지 말은 400, 숫자·주소 모양은 프롬프트에서 빠진다."""
    card = _cafe_card()
    spec = DV.variants(card)[0]["spec"]
    hero_url = next(s for s in spec["sections"] if s["id"] == "hero")["content"]["image"]
    target = PE.resolve_target(card, spec, "hero", hero_url, 0)
    session = _session(card)

    for bad in ("사람 넣어 줘", "간판에 가게 이름 넣어줘", "로고 추가해 줘", "face 넣어줘"):
        with pytest.raises(ValueError, match="사람·글자·간판·로고는 넣을 수 없어요"):
            PE.make_candidate(room_iso, session, target, instruction=bad)

    PE.make_candidate(room_iso, session, target, instruction="연남로 12번지 느낌으로 010-1234-5678")
    prompt = fake_gemini["json"]["contents"][0]["parts"][1]["text"]
    assert "010" not in prompt and "1234" not in prompt and "연남로 12" not in prompt


def test_6_limits(room_iso, fake_gemini):
    """같은 칸 10분 안 두 번째는 400(남은 분), 하루 11번째는 400."""
    card = _cafe_card()
    spec = DV.variants(card)[0]["spec"]
    hero_url = next(s for s in spec["sections"] if s["id"] == "hero")["content"]["image"]
    target = PE.resolve_target(card, spec, "hero", hero_url, 0)
    session = _session(card)

    card["ai_images"] = {"hero": {"url": "/uploads/x/ai-hero.jpg", "at": time.time()}}
    with pytest.raises(ValueError, match="분 뒤에"):
        PE.make_candidate(room_iso, session, target, instruction="여름 느낌으로")

    card["ai_images"]["hero"]["at"] = time.time() - AI.COOLDOWN_SEC - 1
    card["ai_edit_day"] = {"date": PE._kst_today(), "n": 10}
    with pytest.raises(ValueError, match="하루 10번"):
        PE.make_candidate(room_iso, session, target, instruction="여름 느낌으로")

    card["ai_edit_day"] = {"date": PE._kst_today(), "n": 9}
    got = PE.make_candidate(room_iso, session, target, instruction="여름 느낌으로")
    assert got["after_url"]
    assert card["ai_edit_day"]["n"] == 10


def test_7_apply_writes_card_and_expires(room_iso, fake_gemini):
    """apply: 카드 칸이 후보 주소로·prev 보관·새 spec에 반영, 30분 지난 후보는 거절."""
    card = _cafe_card()
    spec = DV.variants(card)[0]["spec"]
    hero_url = next(s for s in spec["sections"] if s["id"] == "hero")["content"]["image"]
    target = PE.resolve_target(card, spec, "hero", hero_url, 0)
    session = _session(card)

    got = PE.make_candidate(room_iso, session, target, instruction="여름 느낌으로")
    out = PE.apply_candidate(session, got["candidate_id"])
    assert out["url"] == got["after_url"]
    entry = card["ai_images"]["hero"]
    assert entry["url"] == got["after_url"] and entry["prev_url"] == hero_url

    hero_now = next(s for s in DV.variants(card)[0]["spec"]["sections"]
                    if s["id"] == "hero")["content"]["image"]
    assert hero_now == got["after_url"]

    got2 = PE.make_candidate(room_iso, session, target, action="brighter")
    session["photo_candidates"][got2["candidate_id"]]["at"] = time.time() - 31 * 60
    with pytest.raises(ValueError, match="만료"):
        PE.apply_candidate(session, got2["candidate_id"])


def test_8_undo_once(room_iso, fake_gemini):
    """undo: prev로 되돌림, 두 번째 undo는 400."""
    card = _cafe_card()
    url = _put_upload(room_iso, "p1", _jpeg_bytes())
    card["photos"] = [{"id": "p1", "url": url, "tag": "hero"}]
    spec = DV.variants(card)[0]["spec"]
    target = PE.resolve_target(card, spec, "hero", url, 0)
    session = _session(card)

    got = PE.make_candidate(room_iso, session, target, action="brighter")
    PE.apply_candidate(session, got["candidate_id"])
    assert card["photos"][0]["url"] == got["after_url"]

    out = PE.undo(session, "hero")
    assert out["url"] == url and card["photos"][0]["url"] == url
    with pytest.raises(ValueError, match="되돌릴 게 없어요"):
        PE.undo(session, "hero")

    # AI 칸도 되돌리기 1단계
    card2 = _cafe_card()
    spec2 = DV.variants(card2)[0]["spec"]
    hero_url = next(s for s in spec2["sections"] if s["id"] == "hero")["content"]["image"]
    target2 = PE.resolve_target(card2, spec2, "hero", hero_url, 0)
    session2 = _session(card2)
    got2 = PE.make_candidate(room_iso, session2, target2, instruction="여름 느낌으로")
    PE.apply_candidate(session2, got2["candidate_id"])
    assert PE.undo(session2, "hero")["url"] == hero_url
    with pytest.raises(ValueError, match="되돌릴 게 없어요"):
        PE.undo(session2, "hero")


def test_9_example_files_untouched(room_iso, fake_gemini):
    """공용 예시를 고친 뒤에도 templates/art/ex 파일이 그대로다."""
    before = {}
    for path in (settings.templates_dir / "art" / "ex").glob("*"):
        before[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()

    card = _cafe_card()
    spec = DV.variants(card)[0]["spec"]
    space = next(s for s in spec["sections"] if s["id"] == "space")
    target = PE.resolve_target(card, spec, "space", space["content"]["items"][0]["src"], 0)
    assert target["kind"] == "example"
    session = _session(card)
    got = PE.make_candidate(room_iso, session, target, instruction="더 따뜻한 조명")
    PE.apply_candidate(session, got["candidate_id"])
    assert card["ai_images"][target["target"]]["url"] == got["after_url"]

    after = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
             for p in (settings.templates_dir / "art" / "ex").glob("*")}
    assert after == before


def test_10_forged_target_path_is_not_read(room_iso, fake_gemini, tmp_path):
    """검토 9/30: 넘겨받은 파일 경로·남의 방 주소를 믿지 않는다 (서버 파일을 읽어 AI로 보내는 틈)."""
    secret = tmp_path / "secret.txt"
    secret.write_text("비밀")
    card = _cafe_card()
    session = _session(card)
    for forged in ({"target": "hero", "kind": "example", "current_url": "/uploads/otherroom/p.jpg",
                    "current_path": str(secret)},
                   {"target": "hero", "kind": "ai", "current_url": "/etc/passwd", "current_path": "/etc/passwd"}):
        with pytest.raises(ValueError):
            PE.make_candidate(room_iso, session, forged, instruction="여름 느낌으로")
    assert "json" not in fake_gemini  # Gemini를 부르지 않았다


def test_11_cooldown_counts_unapplied_candidates(room_iso, fake_gemini):
    """적용하지 않고 후보만 거듭 만들어도 같은 칸 10분 제한."""
    card = _cafe_card()
    spec = DV.variants(card)[0]["spec"]
    hero_url = next(s for s in spec["sections"] if s["id"] == "hero")["content"]["image"]
    target = PE.resolve_target(card, spec, "hero", hero_url, 0)
    session = _session(card)
    PE.make_candidate(room_iso, session, target, instruction="여름 느낌으로")
    with pytest.raises(ValueError, match="분 뒤에"):
        PE.make_candidate(room_iso, session, target, instruction="겨울 느낌으로")


def test_12_webp_input_sent_as_real_jpeg(room_iso, fake_gemini):
    """공용 예시(webp)를 보낼 때도 image/jpeg라고 적은 대로 실제 JPEG 바이트를 보낸다."""
    card = _cafe_card()
    spec = DV.variants(card)[0]["spec"]
    hero_url = next(s for s in spec["sections"] if s["id"] == "hero")["content"]["image"]
    assert hero_url.endswith(".webp")
    target = PE.resolve_target(card, spec, "hero", hero_url, 0)
    PE.make_candidate(room_iso, _session(card), target, instruction="여름 느낌으로")
    part = fake_gemini["json"]["contents"][0]["parts"][0]["inlineData"]
    assert part["mimeType"] == "image/jpeg" and base64.b64decode(part["data"])[:3] == b"\xff\xd8\xff"


# --- 경로 테스트 (JOB A, 계약서 §4·§7 항목 7·8·10 + target/preview) ---


def _start_room(client):
    """빌더 방 만들기 (POST /api/start, IP 제한은 테스트마다 따로 센다)."""
    from app.api import inquiries as inquiries_api
    with inquiries_api._lock:
        inquiries_api._hits.clear()
    r = client.post("/api/start", json={"template": "cafe"})
    assert r.status_code == 200, r.text
    return r.json()


def _owner_headers(body):
    return {"X-Member-Id": body["member_id"]}


def _hero_url(body):
    """방 카드의 첫 화면 사진 주소 (미리보기가 그리는 명세와 같은 안 고르기)."""
    from app import store
    room = store.read_room(body["room_id"])
    card = store.read_session(room["session_id"])["prd"]
    vid = card.get("design_choice")
    vid = vid if vid in ("v1", "v2", "v3") else "v1"
    spec = DV.pick(card, vid)["spec"]
    return next(s for s in spec["sections"] if s["id"] == "hero")["content"]["image"]


def test_route_target_kind_actions(client):
    """target 경로: kind·actions·ai_allowed·남은 횟수, 모르는 사진은 400."""
    body = _start_room(client)
    rid, headers = body["room_id"], _owner_headers(body)
    url = _hero_url(body)
    r = client.get(f"/api/rooms/{rid}/photo-edit/target",
                   params={"section": "hero", "src": url, "index": 0}, headers=headers)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["target"] == "hero" and data["kind"] == "example"
    assert data["current_url"] == url
    assert data["actions"] == PE.actions_for("example") and len(data["actions"]) == 5
    assert data["ai_allowed"] is True
    assert data["left_today"] == PE.DAY_LIMIT and data["cooldown_sec"] == 0
    assert r.headers["cache-control"] == "no-store"
    assert "current_path" not in data

    r = client.get(f"/api/rooms/{rid}/photo-edit/target",
                   params={"section": "hero", "src": "/uploads/x/none.jpg", "index": 9},
                   headers=headers)
    assert r.status_code == 400
    assert r.json()["detail"] == PE.UNKNOWN


def test_route_preview_brighter_keeps_card(client):
    """preview 보정: 후보를 돌려주고 카드는 그대로 둔다."""
    body = _start_room(client)
    rid, headers = body["room_id"], _owner_headers(body)
    r = client.post(f"/api/rooms/{rid}/photo-edit/preview",
                    json={"target": "hero", "action": "brighter"}, headers=headers)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["before_url"] == _hero_url(body) and data["after_url"] != data["before_url"]
    assert data["candidate_id"]
    assert r.headers["cache-control"] == "no-store"

    from app import store
    card = store.read_session(store.read_room(rid)["session_id"])["prd"]
    assert not card.get("ai_images")

    r = client.post(f"/api/rooms/{rid}/photo-edit/preview",
                    json={"target": "없는칸", "action": "brighter"}, headers=headers)
    assert r.status_code == 400
    assert r.json()["detail"] == PE.UNKNOWN


def test_route_preview_ai_records_funnel(client, fake_gemini):
    """AI 고치기 경로: 후보만 만들고 카드는 그대로, ai_image_edited을 기록한다."""
    from sqlalchemy import select
    from app import store
    from app.db.models import FunnelEventRow
    from app.db.session import get_sessionmaker
    body = _start_room(client)
    rid, headers = body["room_id"], _owner_headers(body)
    before = _hero_url(body)
    r = client.post(f"/api/rooms/{rid}/photo-edit/preview",
                    json={"target": "hero", "instruction": "여름 느낌으로"}, headers=headers)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["before_url"] == before and data["after_url"] != before

    card = store.read_session(store.read_room(rid)["session_id"])["prd"]
    assert "hero" not in card.get("ai_images", {})
    assert card["ai_edit_day"]["n"] == 1
    with get_sessionmaker()() as db:
        rows = db.scalars(select(FunnelEventRow).where(
            FunnelEventRow.event == "ai_image_edited")).all()
    assert rows
    assert rows[-1].props == {"industry": "cafe", "kind": "hero", "source": "example"}


def test_route_apply_writes_card_and_expires(client):
    """§7-7: 카드 칸이 후보 주소로·prev 보관·미리보기 HTML에 반영, 30분 지난 후보는 거절."""
    from app import store
    body = _start_room(client)
    rid, headers = body["room_id"], _owner_headers(body)
    cand = client.post(f"/api/rooms/{rid}/photo-edit/preview",
                       json={"target": "hero", "action": "brighter"}, headers=headers).json()

    r = client.post(f"/api/rooms/{rid}/photo-edit/apply",
                    json={"candidate_id": cand["candidate_id"]}, headers=headers)
    assert r.status_code == 200, r.text
    assert r.headers["cache-control"] == "no-store"
    assert r.json() == {"ok": True, "url": cand["after_url"], "undo": True}

    card = store.read_session(store.read_room(rid)["session_id"])["prd"]
    assert card["ai_images"]["hero"]["url"] == cand["after_url"]
    assert card["ai_images"]["hero"]["prev_url"] == cand["before_url"]
    html = client.get(f"/api/rooms/{rid}/card/preview", headers=headers).json()["html"]
    assert cand["after_url"] in html

    cand2 = client.post(f"/api/rooms/{rid}/photo-edit/preview",
                        json={"target": "hero", "action": "brighter"}, headers=headers).json()
    with store.session_tx(store.read_room(rid)["session_id"]) as sess:
        sess["prd"]["photo_candidates"][cand2["candidate_id"]]["at"] = time.time() - 31 * 60
    r = client.post(f"/api/rooms/{rid}/photo-edit/apply",
                    json={"candidate_id": cand2["candidate_id"]}, headers=headers)
    assert r.status_code == 400
    assert "만료" in r.json()["detail"]


def test_route_undo_once_then_400(client):
    """§7-8: 되돌리면 prev로, 두 번째 되돌리기는 400."""
    from app import store
    body = _start_room(client)
    rid, headers = body["room_id"], _owner_headers(body)
    cand = client.post(f"/api/rooms/{rid}/photo-edit/preview",
                       json={"target": "hero", "action": "brighter"}, headers=headers).json()
    client.post(f"/api/rooms/{rid}/photo-edit/apply",
                json={"candidate_id": cand["candidate_id"]}, headers=headers)

    r = client.post(f"/api/rooms/{rid}/photo-edit/undo", json={"target": "hero"}, headers=headers)
    assert r.status_code == 200, r.text
    assert r.headers["cache-control"] == "no-store"
    assert r.json() == {"ok": True, "url": cand["before_url"]}
    card = store.read_session(store.read_room(rid)["session_id"])["prd"]
    assert card["ai_images"]["hero"]["url"] == cand["before_url"]
    html = client.get(f"/api/rooms/{rid}/card/preview", headers=headers).json()["html"]
    assert cand["before_url"] in html

    r = client.post(f"/api/rooms/{rid}/photo-edit/undo", json={"target": "hero"}, headers=headers)
    assert r.status_code == 400
    assert "되돌릴 게 없어요" in r.json()["detail"]


def test_route_owner_only_and_foreign_origin(client):
    """§7-10: 방장 아님 403, 쿠키 인증 + 다른 출처 쓰기 403."""
    import uuid
    from app import store
    from app.config import settings
    from app.db.models import UserRoomRow, UserRow
    from app.db.session import get_sessionmaker
    from app.services import auth
    body = _start_room(client)
    rid = body["room_id"]
    url = _hero_url(body)

    client.post(f"/room/{rid}/chat", json={"member_id": "guest", "nickname": "손님", "message": ""})
    guest = {"X-Member-Id": "guest"}
    r = client.get(f"/api/rooms/{rid}/photo-edit/target",
                   params={"section": "hero", "src": url, "index": 0}, headers=guest)
    assert r.status_code == 403 and r.json()["detail"] == "owner only"
    for path, payload in (("preview", {"target": "hero", "action": "brighter"}),
                          ("apply", {"candidate_id": "c0"}),
                          ("undo", {"target": "hero"})):
        r = client.post(f"/api/rooms/{rid}/photo-edit/{path}", json=payload, headers=guest)
        assert r.status_code == 403, (path, r.text)

    user_id = f"u-{uuid.uuid4().hex[:8]}"
    with get_sessionmaker()() as db, db.begin():
        db.add(UserRow(id=user_id, nickname="사장님"))
        db.flush()
        db.add(UserRoomRow(user_id=user_id, room_id=rid, member_id=body["member_id"]))
    client.cookies.set(auth.SESSION_COOKIE, auth.create_session(user_id))
    try:
        ours = (settings.public_base_url or "http://testserver").rstrip("/")
        payload = {"target": "hero", "action": "brighter"}
        assert client.post(f"/api/rooms/{rid}/photo-edit/preview", json=payload).status_code == 403
        r = client.post(f"/api/rooms/{rid}/photo-edit/preview", json=payload,
                        headers={"Origin": "https://evil.example"})
        assert r.status_code == 403, r.text
        r = client.post(f"/api/rooms/{rid}/photo-edit/preview", json=payload,
                        headers={"Origin": ours})
        assert r.status_code == 200, r.text
    finally:
        client.cookies.clear()


def test_edit_script_sends_src_and_index():
    """편집 스크립트가 사진 src·순서를 함께 보낸다 (계약서 §4)."""
    from app.services import site_render as SR
    assert "getAttribute('src')" in SR._EDIT_SCRIPT
    assert "index" in SR._EDIT_SCRIPT


def test_13_forged_kind_cannot_ai_edit_owner_photo(room_iso, fake_gemini):
    """검토 9/30: kind를 example로 속여도 사장님 사진이면 보정만 (D57)."""
    card = _cafe_card()
    url = _put_upload(room_iso, "p1", _jpeg_bytes())
    card["photos"] = [{"id": "p1", "url": url, "tag": "hero"}]
    forged = {"target": "hero", "kind": "example", "current_url": url}
    with pytest.raises(ValueError, match="실제 사진은"):
        PE.make_candidate(room_iso, _session(card), forged, instruction="배경 바꿔 줘")
    assert "json" not in fake_gemini


def test_14_owner_undo_finds_the_edited_photo(room_iso):
    """검토 9/30: 되돌리기가 칸 위치를 추측하지 않고 고친 그 사진을 되돌린다."""
    card = _cafe_card()
    u1 = _put_upload(room_iso, "p1", _jpeg_bytes())
    u2 = _put_upload(room_iso, "p2", _jpeg_bytes(color=(10, 90, 200)))
    card["photos"] = [{"id": "p1", "url": u1, "tag": "space"}, {"id": "p2", "url": u2, "tag": "hero"}]
    session = _session(card)
    got = PE.make_candidate(room_iso, session, {"target": "hero", "current_url": u2}, action="brighter")
    PE.apply_candidate(session, got["candidate_id"])
    assert PE.undo(session, "hero")["url"] == u2
    assert card["photos"][0]["url"] == u1 and card["photos"][1]["url"] == u2
