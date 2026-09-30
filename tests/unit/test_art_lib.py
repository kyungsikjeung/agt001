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
    monkeypatch.setattr(photos, "_refresh_designs_async", lambda *a, **k: refreshed.append(a))
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
