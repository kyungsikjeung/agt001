"""tests/unit 전용 픽스처. app/, backend.py 등은 절대 수정하지 않는다."""
import json
import os

# 앱 import 전에 테스트용 환경변수를 고정한다 (.env를 읽지 않고 동작해야 함).
os.environ["NIM_API_KEY"] = "test"
os.environ["PRECOMPUTE_EMBEDDINGS"] = "false"

import pytest
from fastapi.testclient import TestClient

from app import llm, store
from app.config import settings
from app.main import create_app
from app.services import codegen as codegen_svc
from app.services import design as design_svc
from app.services import rag

VALID_QUOTE_JSON = json.dumps(
    {
        "options": [
            {"id": "A", "weeks": 2, "amount": 1500000, "desc": "기본안"},
            {"id": "B", "weeks": 1, "amount": 1000000, "desc": "최소안"},
            {"id": "C", "weeks": 3, "amount": 2500000, "desc": "고급안"},
        ],
        "recommended": "B",
    },
    ensure_ascii=False,
)

_DOC_TEXTS = {d["text"] for d in rag.FAKE_RAG_DOCS}


def default_embed(text):
    """문서 임베딩과 쿼리가 직교하도록 만들어 기본적으로 '신규 프로젝트'가 나온다."""
    if text in _DOC_TEXTS:
        return [1.0, 0.0]
    return [0.0, 1.0]


def default_chat(messages):
    return VALID_QUOTE_JSON


def raise_screenshot(*args, **kwargs):
    raise RuntimeError("fake screenshot disabled")


def fake_png_screenshot(html_content, out_path, width=800, height=600):
    from pathlib import Path

    Path(out_path).write_bytes(b"\x89PNG\r\n\x1a\nfakepng")


def fake_codegen_done(session_id, requirement_id, spec_text):
    web_dir = settings.generated_dir / requirement_id / "web"
    web_dir.mkdir(parents=True, exist_ok=True)
    (web_dir / "index.html").write_text("<html>fake done</html>", encoding="utf-8")
    sess = store.sessions.get(session_id)
    if sess is not None:
        sess["codegen"] = {"status": "done", "dir": str(web_dir), "files": ["index.html"]}


def fake_codegen_timeout(session_id, requirement_id, spec_text):
    workdir = settings.generated_dir / requirement_id / "web"
    workdir.mkdir(parents=True, exist_ok=True)
    sess = store.sessions.get(session_id)
    if sess is not None:
        sess["codegen"] = {"status": "timeout", "dir": str(workdir)}


def fake_codegen_unavailable(session_id, requirement_id, spec_text):
    sess = store.sessions.get(session_id)
    if sess is not None:
        sess["codegen"] = {"status": "unavailable", "note": "fake unavailable"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    """테스트마다 격리된 generated_dir + 비어 있는 저장소 + 가짜 외부 의존."""
    monkeypatch.setattr(settings, "generated_dir", tmp_path)
    store.sessions.clear()
    store.rooms.clear()
    rag.reset_cache()
    monkeypatch.setattr(llm, "chat", default_chat)
    monkeypatch.setattr(llm, "embed", default_embed)
    monkeypatch.setattr(design_svc, "screenshot_html", raise_screenshot)
    monkeypatch.setattr(codegen_svc, "start", fake_codegen_done)
    with TestClient(create_app()) as c:
        yield c
    store.sessions.clear()
    store.rooms.clear()
    rag.reset_cache()
