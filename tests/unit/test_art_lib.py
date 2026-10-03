"""태그 사진 창고 (ART_LIB_CONTRACT §5의 1·2·4·5). Gemini·LLM은 가짜로만 부른다."""
import io
import json
import threading
import time

import pytest
from PIL import Image

from app.config import settings
from app.services import art_lib


def _png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (640, 480), (180, 140, 90)).save(buf, "PNG")
    return buf.getvalue()


@pytest.fixture
def lib(tmp_path, monkeypatch):
    """창고 폴더를 테스트용으로 두고, 생성기·LLM을 가짜로 바꾼다."""
    monkeypatch.setattr(settings, "generated_dir", tmp_path)
    monkeypatch.setattr(settings, "art_lib_daily_cap", 0)
    seen = {"gen": [], "llm": []}

    def fake_gen(prompt, timeout_sec=120.0, slot="hero"):
        seen["gen"].append({"prompt": prompt, "slot": slot})
        time.sleep(0.05)
        return _png()

    def fake_llm(system, user, timeout_sec=20.0, max_tokens=700):
        seen["llm"].append(json.loads(user))
        return json.dumps(seen.get("answer", {"tag": "pasta-oil", "prompt": "a plate of aglio e olio pasta"}))

    from app import llm
    from app.services import ai_images
    monkeypatch.setattr(ai_images, "_generate_bytes", fake_gen)
    monkeypatch.setattr(llm, "chat_json", fake_llm)
    return seen


def test_1_word_table_hit_without_llm(lib):
    assert art_lib.tag_for("아이스 아메리카노 (L)", "cafe") == "coffee-americano"
    assert art_lib.tag_for("라떼", "cafe") == "coffee-latte"
    assert lib["llm"] == []


def test_1_unknown_name_uses_llm_once_then_alias(lib):
    lib["answer"] = {"tag": "pasta-ragu", "prompt": "a plate of ragu pappardelle"}
    assert art_lib.tag_for("라구파파르델레", "restaurant") == "pasta-ragu"
    assert art_lib.tag_for("라구 파파르델레", "restaurant") == "pasta-ragu"  # 같은 이름(정규화)은 다시 묻지 않는다
    assert len(lib["llm"]) == 1
    sent = lib["llm"][0]
    assert sent["item"] == "라구파파르델레" and sent["industry"] == "restaurant"
    assert set(sent) == {"item", "industry", "existing_tags"}  # 가게 이름·전화 같은 칸이 없다


def test_1_bad_llm_tag_is_none_and_not_cached(lib):
    lib["answer"] = {"tag": "Pasta Oil!", "prompt": "x"}
    assert art_lib.tag_for("뇨끼", "restaurant") is None
    lib["answer"] = {"tag": "gnocchi", "prompt": "a plate of potato gnocchi"}
    assert art_lib.tag_for("뇨끼", "restaurant") == "gnocchi"  # 실패는 기록하지 않아 다음에 다시 정한다
    assert len(lib["llm"]) == 2


def test_1_short_names_do_not_match_everything(lib):
    assert art_lib.tag_for("라", "cafe", use_llm=False) is None
    assert art_lib.normalize("와인 1잔") == "와인"
    assert art_lib.normalize("무지개떡") == "무지개떡"


def test_2_ensure_saves_webp_and_index(lib):
    assert art_lib.ensure("coffee-americano", "cafe") is True
    path = settings.generated_dir / "art-lib" / "coffee-americano.webp"
    assert Image.open(path).format == "WEBP"
    index = json.loads((settings.generated_dir / "art-lib" / "index.json").read_text(encoding="utf-8"))
    assert index["tags"]["coffee-americano"]["src"] == "gemini" and index["tags"]["coffee-americano"]["made"]
    assert lib["gen"][0]["slot"] == "gallery-1" and "no text" in lib["gen"][0]["prompt"]
    assert art_lib.url("coffee-americano") == "/art-lib/coffee-americano.webp"
    assert art_lib.ensure("coffee-americano", "cafe") is True and len(lib["gen"]) == 1  # 있으면 다시 안 만든다


def test_2_same_tag_concurrently_made_once(lib):
    out = []
    threads = [threading.Thread(target=lambda: out.append(art_lib.ensure("coffee-latte", "cafe"))) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(lib["gen"]) == 1 and True in out


def test_2_daily_cap(lib, monkeypatch):
    monkeypatch.setattr(settings, "art_lib_daily_cap", 1)
    assert art_lib.ensure("coffee-americano", "cafe") is True
    assert art_lib.ensure("coffee-latte", "cafe") is False
    assert len(lib["gen"]) == 1


def test_2_generator_failure_is_false(lib, monkeypatch):
    from app.services import ai_images

    def boom(*a, **k):
        raise ai_images.ImageError("실패")
    monkeypatch.setattr(ai_images, "_generate_bytes", boom)
    assert art_lib.ensure("coffee-americano", "cafe") is False
    assert art_lib.url("coffee-americano") is None


def test_4_route(client, lib):
    art_lib.ensure("coffee-americano", "cafe")
    r = client.get("/art-lib/coffee-americano.webp")
    assert r.status_code == 200 and r.headers["content-type"] == "image/webp"
    assert client.get("/art-lib/no-such.webp").status_code == 404
    assert client.get("/art-lib/..%2Fx.webp").status_code == 404
    assert client.get("/art-lib/Bad_Tag.webp").status_code == 404


def test_5_pick_never_calls_llm_or_generator(lib):
    assert art_lib.pick({}, "아메리카노") == {}  # 창고에 없으면 빈 값(만들지 않는다)
    art_lib.ensure("coffee-americano", "cafe")
    n_gen = len(lib["gen"])
    got = art_lib.pick({}, "아이스 아메리카노")
    assert got == {"image": "/art-lib/coffee-americano.webp", "image_alt": "아이스 아메리카노 사진 (예시)",
                   "image_example": True}
    assert art_lib.pick({}, "처음 보는 메뉴") == {}
    assert lib["llm"] == [] and len(lib["gen"]) == n_gen


def test_5_prefetch_runs_in_background(lib, monkeypatch):
    from app.services import photo_needs, photos
    monkeypatch.setattr(photo_needs, "items", lambda card: [{"name": "아메리카노", "kind": "menu"},
                                                            {"name": "라떼", "kind": "menu"}])
    refreshed = []
    monkeypatch.setattr(photos, "_refresh_designs_async", lambda *a, **k: refreshed.append(a[:2]))
    from app.services import keystore
    monkeypatch.setattr(keystore, "get", lambda name: "k" if name == "gemini_api_key" else None)
    card = {"industry": "cafe", "slots": {}}
    t0 = time.monotonic()
    art_lib.prefetch(card, "room1", "req1")
    assert time.monotonic() - t0 < 0.05  # 부른 쪽은 기다리지 않는다
    for _ in range(100):
        if refreshed:
            break
        time.sleep(0.02)
    assert art_lib.url("coffee-americano") and art_lib.url("coffee-latte")
    assert refreshed == [("room1", "req1")]


def test_5_prefetch_skips_without_image_key(lib, monkeypatch):
    """이미지 키가 없으면 사진을 못 만드니 태그 정하기(LLM)도 하지 않는다."""
    from app.services import keystore, photo_needs
    monkeypatch.setattr(keystore, "get", lambda name: None)
    monkeypatch.setattr(photo_needs, "items", lambda card: [{"name": "처음 보는 메뉴", "kind": "menu"}])
    art_lib.prefetch({"industry": "cafe", "slots": {}}, "room1", "req1")
    time.sleep(0.1)
    assert lib["llm"] == [] and lib["gen"] == []


def test_3_item_image_order_uses_library_before_pack(lib):
    """사장님 사진 > AI > 창고 > 팩: 창고에 있으면 예시 팩 대신 창고 사진(예시 표시)."""
    from app.services import site_data
    art_lib.ensure("coffee-americano", "cafe")
    card = {"slots": {}, "photos": [], "ai_images": {}}
    got = site_data._item_image(card, "아메리카노", {}, {"image": "/art/ex/cafe-coffee.webp"})
    assert got["image"] == "/art-lib/coffee-americano.webp" and got["image_example"] is True
    assert site_data._item_image(card, "처음 보는 메뉴", {}, {"image": "/art/ex/x.webp"}) == {"image": "/art/ex/x.webp"}


# ---- 장면 사진 (첫 화면·사진첩): 처음 보는 종류(청첩장)도 그 종류 사진을 만들어 보인다 (10/2) ----
WEDDING = {"scenes": [
    {"tag": "wedding-rings", "prompt": "two gold wedding rings on white silk"},
    {"tag": "wedding-bouquet", "prompt": "a white rose bouquet on a chair"},
    {"tag": "wedding-aisle", "prompt": "a chapel aisle with candles"},
    {"tag": "Bad Tag!", "prompt": "x"},
    {"tag": "wedding-table", "prompt": "a wedding reception table setting"},
]}


def _wedding_card():
    return {"industry": "other", "slots": {"business_type": {"value": "결혼 청첩장", "status": "filled"}}, "photos": []}


def test_scenes_llm_once_per_kind_then_reused(lib):
    lib["answer"] = WEDDING
    assert art_lib.scene_tags(_wedding_card()) == ["wedding-rings", "wedding-bouquet", "wedding-aisle", "wedding-table"]
    assert lib["llm"][0] == {"site_kind": "청첩장", "existing_tags": lib["llm"][0]["existing_tags"]}
    assert art_lib.scene_tags(_wedding_card()) == ["wedding-rings", "wedding-bouquet", "wedding-aisle", "wedding-table"]
    assert len(lib["llm"]) == 1  # 같은 종류는 다시 묻지 않는다
    assert art_lib.pick_scenes(_wedding_card()) == []  # 아직 안 만들었으면 그리기에 안 쓴다


def test_scenes_prefetch_makes_photos_and_refreshes(lib, monkeypatch):
    lib["answer"] = WEDDING
    from app.services import keystore, photo_needs, photos
    monkeypatch.setattr(keystore, "get", lambda name: "k" if name == "gemini_api_key" else None)
    monkeypatch.setattr(photo_needs, "items", lambda card: [])
    refreshed = []
    monkeypatch.setattr(photos, "_refresh_designs_async", lambda *a, **k: refreshed.append(a[:2]))
    art_lib.prefetch(_wedding_card(), "room1", "req1")
    for _ in range(150):
        if refreshed:
            break
        time.sleep(0.02)
    assert refreshed == [("room1", "req1")]
    assert art_lib.pick_scenes(_wedding_card())[0] == "/art-lib/wedding-rings.webp"
    assert len(lib["gen"]) == 4 and all("no people" in g["prompt"] for g in lib["gen"])


def test_scenes_not_for_six_shop_kinds_or_when_owner_has_photos(lib, monkeypatch):
    from app.services import keystore, photo_needs
    monkeypatch.setattr(keystore, "get", lambda name: "k" if name == "gemini_api_key" else None)
    monkeypatch.setattr(photo_needs, "items", lambda card: [])
    cafe = {"industry": "cafe", "slots": {"business_type": {"value": "카페", "status": "filled"}}}
    art_lib.prefetch(cafe, "r", "q")
    own = {**_wedding_card(), "photos": [{"url": "/uploads/a.webp", "use": "site"}]}
    monkeypatch.setattr("app.services.photos.site_photos", lambda card: card.get("photos") or [])
    art_lib.prefetch(own, "r", "q")
    time.sleep(0.15)
    assert lib["llm"] == [] and lib["gen"] == []


def test_draft_uses_scene_photos_before_cafe_default_art(lib):
    lib["answer"] = WEDDING
    for tag in art_lib.scene_tags(_wedding_card()):
        art_lib.ensure(tag, "scene")
    from app.services import design_variants as DV
    spec = DV.base_spec(_wedding_card())
    hero = next(s for s in spec["sections"] if s["type"] == "hero")["content"]
    assert hero["image"] == "/art-lib/wedding-rings.webp" and "cafe" not in hero["image"]
    gallery = next((s for s in spec["sections"] if s["type"] == "gallery"), None)
    if gallery:
        assert all(i["src"].startswith("/art-lib/wedding-") for i in gallery["content"]["items"])


def test_scenes_shared_across_phrasings_of_the_same_kind(lib):
    """'결혼 청첩장'·'모바일 청첩장'은 같은 장면 묶음(청첩장) → LLM은 한 번만."""
    lib["answer"] = WEDDING
    other = {**_wedding_card(), "slots": {"business_type": {"value": "모바일 청첩장", "status": "filled"}}}
    assert art_lib.scene_tags(_wedding_card()) == art_lib.scene_tags(other)
    assert len(lib["llm"]) == 1


def test_scene_prompt_forbids_memorial_and_letters(lib):
    """10/2 운영: 칠순에 제사상, 돌잔치 현수막에 글자가 나왔다 → 장면 지시에 금지를 둔다."""
    seen = {}
    from app import llm

    def spy(system, user, timeout_sec=20.0, max_tokens=700):
        seen["system"] = system
        return json.dumps({"scenes": [{"tag": "chilseon-table", "prompt": "a festive table"}]})

    import pytest as _pytest
    mp = _pytest.MonkeyPatch()
    mp.setattr(llm, "chat_json", spy)
    try:
        art_lib._ask_scenes("칠순", [])
    finally:
        mp.undo()
    assert "never memorial" in seen["system"] and "no letters or characters on banners" in seen["system"]
