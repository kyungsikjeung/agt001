"""AI 예시 이미지 (Gemini 생성, 버튼식)."""
import base64
import io

import pytest
from PIL import Image

from app import store
from app.services import ai_images as AI
from app.services import design_variants as DV
from app.services import site_render as SR


def _png_bytes(size=(64, 64)):
    buf = io.BytesIO()
    Image.new("RGB", size, (200, 150, 100)).save(buf, "PNG")
    return buf.getvalue()


class _Resp:
    def __init__(self, status=200, payload=None):
        self.status_code = status
        self._payload = payload or {}
        self.text = "err"

    def json(self):
        return self._payload


def _ok_resp(raw: bytes):
    return _Resp(200, {"candidates": [{"content": {"parts": [
        {"inlineData": {"mimeType": "image/png", "data": base64.b64encode(raw).decode()}}]}}]})


def test_prompt_has_no_personal_data():
    for kind in ("pension", "cafe", "restaurant", "salon", "workshop",
                 "academy", "individual", "group", "webservice", "other", "bogus"):
        for slot in AI.SLOTS:
            p = AI.prompt_for(kind, slot)
            assert "010" not in p and "전화" not in p
            for banned in ("no people", "no text", "no logos"):
                assert banned in p
    with pytest.raises(AI.ImageError):
        AI.prompt_for("cafe", "bogus-slot")


def test_generate_bytes_success_and_failures(monkeypatch):
    monkeypatch.setattr(AI.httpx, "post", lambda *a, **k: _ok_resp(_png_bytes()))
    out = AI._generate_bytes("a cafe", timeout_sec=5)
    assert out[:8] == _png_bytes()[:8]

    monkeypatch.setattr(AI.httpx, "post", lambda *a, **k: _Resp(429))
    with pytest.raises(AI.ImageError):
        AI._generate_bytes("a cafe", timeout_sec=5)

    monkeypatch.setattr(AI.httpx, "post", lambda *a, **k: _Resp(200, {"candidates": []}))
    with pytest.raises(AI.ImageError):
        AI._generate_bytes("a cafe", timeout_sec=5)


def test_model_routing_hero_override(monkeypatch):
    """P2: hero는 상위 모델 지정 시 그걸, 갤러리는 기본 모델. 미지정이면 전부 기본."""
    from app.config import settings
    monkeypatch.setattr("app.services.keystore.get", lambda name: "k")
    seen = {}

    def fake_post(url, **kwargs):
        seen[kwargs.get("slot", "") or url] = url
        return _ok_resp(_png_bytes())

    monkeypatch.setattr(AI.httpx, "post", fake_post)
    assert AI._model_for("hero") == (settings.gemini_image_model or "").strip()
    assert AI._model_for("gallery-1") == (settings.gemini_image_model or "").strip()
    monkeypatch.setattr(settings, "gemini_image_model_hero", "probe-hero-model")
    assert AI._model_for("hero") == "probe-hero-model"
    assert AI._model_for("gallery-1") == (settings.gemini_image_model or "").strip()
    AI._generate_bytes("a cafe", timeout_sec=5, slot="hero")
    AI._generate_bytes("a cafe", timeout_sec=5, slot="gallery-1")
    urls = list(seen.values())
    assert any("probe-hero-model" in u for u in urls)
    assert any("probe-hero-model" not in u for u in urls)


def test_generate_needs_key(monkeypatch):
    monkeypatch.setattr("app.services.keystore.get", lambda name: "")
    with pytest.raises(AI.ImageError):
        AI._generate_bytes("a cafe", timeout_sec=5)


def _room(client):
    rid = client.post("/room").json()["room_id"]
    client.post(f"/room/{rid}/chat", json={"member_id": "owner", "nickname": "사장님",
                                           "message": "식당 사이트 해요"})
    return rid


def test_ensure_records_card_and_skips_with_owner_photos(client, monkeypatch):
    monkeypatch.setattr(AI, "_generate_bytes", lambda prompt, **k: _png_bytes())
    rid = _room(client)
    # 사장님 사진이 있으면 만들지 않는다.
    with store.room_tx(rid) as (_, session):
        session["prd"].setdefault("photos", []).append({"id": "p1", "url": "/uploads/x/p1.jpg"})
    out = AI.ensure(rid, "hero")
    assert out["made"] == [] and out["skipped"]

    with store.room_tx(rid) as (_, session):
        session["prd"]["photos"] = []
    out = AI.ensure(rid, "hero")
    assert out["made"] == ["hero"]
    card = store.read_session(store.read_room(rid)["session_id"])["prd"]
    assert card["ai_images"]["hero"]["url"].endswith("ai-hero.jpg")
    # 두 번째는 쿨다운으로 막힌다.
    out2 = AI.ensure(rid, "hero")
    assert out2["made"] == [] and "hero" in out2["skipped"]


def test_ensure_rejects_bad_slot_and_stranger(client):
    rid = _room(client)
    with pytest.raises(AI.ImageError):
        AI.ensure(rid, "bogus")
    client.post(f"/room/{rid}/chat", json={"member_id": "guest", "nickname": "손님", "message": ""})
    from app.services import rooms
    with pytest.raises(rooms.NotOwner):
        AI.ensure(rid, "hero", by_owner=False)


def test_base_spec_prefers_owner_photos_over_ai():
    from app.services import prd_engine as E
    card = E.new_card("restaurant")
    card["ai_images"] = {"hero": {"url": "/uploads/r/ai-hero.jpg"},
                         "gallery-1": {"url": "/uploads/r/ai-gallery-1.jpg"},
                         "gallery-2": {"url": "/uploads/r/ai-gallery-2.jpg"}}
    spec = DV.base_spec(card)
    hero = next(s for s in spec["sections"] if s["type"] == "hero")
    assert hero["content"]["image"] == "/uploads/r/ai-hero.jpg"
    assert hero["content"]["ai_example"] is True
    gallery = next(s for s in spec["sections"] if s["type"] == "gallery")
    assert all(i.get("ai") for i in gallery["content"]["items"])

    card["photos"] = [{"id": "p1", "url": "/uploads/r/p1.jpg"}]
    spec2 = DV.base_spec(card)
    hero2 = next(s for s in spec2["sections"] if s["type"] == "hero")
    assert hero2["content"]["image"] == "/uploads/r/p1.jpg"
    assert "ai_example" not in hero2["content"]


def test_render_badges_for_ai():
    hero_ctx = SR._hero_context({"image": "/uploads/r/ai-hero.jpg", "image_alt": "x",
                                 "title": "t", "ai_example": True})
    assert hero_ctx["image_ai_badge"] is True
    hero_ctx2 = SR._hero_context({"image": "/uploads/r/p1.jpg", "title": "t"})
    assert hero_ctx2["image_ai_badge"] is False
    items = SR._gallery_items({"items": [{"src": "/uploads/r/ai-gallery-1.jpg", "ai": True}]})
    assert items[0]["ai_badge"] is True
    items2 = SR._gallery_items({"items": [{"src": "/uploads/r/p1.jpg"}]})
    assert items2[0]["ai_badge"] is False
