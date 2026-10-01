"""태그 사진 창고 미리 채우기 스크립트 (scripts/prefill_art_lib.py). Gemini는 가짜로만 부른다."""
import importlib.util
import io
from pathlib import Path

import pytest
from PIL import Image

from app.config import settings
from app.services import art_lib

_SPEC = importlib.util.spec_from_file_location(
    "prefill_art_lib", Path(__file__).resolve().parents[2] / "scripts" / "prefill_art_lib.py")
prefill = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(prefill)


@pytest.fixture
def gen(monkeypatch):
    """가짜 Gemini: 부른 횟수를 센다. ok=False면 실패."""
    from app.services import ai_images
    seen = {"n": 0, "ok": True}

    def fake(prompt, timeout_sec=120.0, slot="hero"):
        seen["n"] += 1
        if not seen["ok"]:
            raise ai_images.ImageError("실패")
        buf = io.BytesIO()
        Image.new("RGB", (64, 64), (120, 90, 60)).save(buf, "PNG")
        return buf.getvalue()

    monkeypatch.setattr(ai_images, "_generate_bytes", fake)
    monkeypatch.setattr(settings, "art_lib_daily_cap", 0)
    return seen


def test_dry_run_lists_missing_and_makes_nothing(gen, capsys):
    assert prefill.main(["--industry", "pension", "--limit", "3"]) == 0
    out = capsys.readouterr().out
    assert "없음 3개" in out and "$0.12" in out and gen["n"] == 0


def test_apply_makes_only_missing(gen, capsys):
    first = next(t for t, row in art_lib._table().items() if "academy" in (row.get("industry") or []))
    art_lib.ensure(first, "academy")
    gen["n"] = 0
    assert prefill.main(["--apply", "--industry", "academy", "--limit", "2"]) == 0
    out = capsys.readouterr().out
    assert gen["n"] == 1 and "만듦 1, 실패 0" in out and f"만듦 {first}" not in out


def test_industry_filter_and_limit(gen, capsys):
    prefill.main(["--industry", "salon"])
    lines = [ln for ln in capsys.readouterr().out.splitlines() if ln and not ln.startswith("미리 보기")]
    salon = [t for t, row in art_lib._table().items() if "salon" in (row.get("industry") or [])]
    assert lines == salon


def test_failure_exit_code(gen, capsys):
    gen["ok"] = False
    assert prefill.main(["--apply", "--limit", "1"]) == 1
    assert "실패" in capsys.readouterr().out
