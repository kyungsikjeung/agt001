"""tests/unit 전용 픽스처.

저장소는 실제 PostgreSQL을 쓴다 (JSONB·잠금 동작은 SQLite로 검증할 수 없음, STAGE0_DESIGN.md §6.1).
로컬: docker run -d --name agt001-pg-test -e POSTGRES_USER=agt001 -e POSTGRES_PASSWORD=agt001 \
  -e POSTGRES_DB=agt001_test -p 127.0.0.1:55432:5432 postgres:16-alpine
"""
import os

# 앱 import 전에 테스트용 환경변수를 고정한다 (.env를 읽지 않고 동작해야 함).
os.environ["NIM_API_KEY"] = "test"
os.environ["PRECOMPUTE_EMBEDDINGS"] = "false"
os.environ["RUN_MIGRATIONS_ON_STARTUP"] = "false"
# 초대 링크 기능 전의 테스트는 여러 명이 방 주소로 들어온다. 초대 테스트는 켜서 따로 본다.
os.environ["ROOM_INVITE_REQUIRED"] = "false"
os.environ["PUBLISH_LOGIN_REQUIRED"] = "false"
os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://agt001:agt001@localhost:55432/agt001_test"
)

import pytest
from fakes import VALID_QUOTE_JSON
from fastapi.testclient import TestClient

from app import llm, store
from app.config import settings
from app.db import migrate as db_migrate
from app.main import create_app
from app.services import codegen as codegen_svc
from app.services import design as design_svc
from app.services import rag

_DOC_TEXTS = {d["text"] for d in rag.DOCS}


def default_embed(text):
    """문서 임베딩과 쿼리가 직교하도록 만들어 기본적으로 '신규 프로젝트'가 나온다."""
    if text in _DOC_TEXTS:
        return [1.0, 0.0]
    return [0.0, 1.0]


def default_chat(messages):
    return VALID_QUOTE_JSON


def default_chat_json(system, user, **kwargs):
    """요구사항 추출의 기본 가짜: 아무 칸도 뽑지 않는다(규칙만으로 흐름이 진행된다)."""
    return '{"updates": []}'


def raise_screenshot(*args, **kwargs):
    raise RuntimeError("fake screenshot disabled")


def fake_png_screenshot(html_content, out_path, width=800, height=600):
    from pathlib import Path

    Path(out_path).write_bytes(b"\x89PNG\r\n\x1a\nfakepng")


def _finish_codegen(session_id, result):
    # 실제 start()처럼 요청 트랜잭션 커밋 뒤에 결과를 기록한다.
    store.after_commit(lambda: store.set_codegen(session_id, result))


def fake_codegen_done(session_id, requirement_id, spec_text):
    web_dir = settings.generated_dir / requirement_id / "web"
    web_dir.mkdir(parents=True, exist_ok=True)
    (web_dir / "index.html").write_text("<html>fake done</html>", encoding="utf-8")
    _finish_codegen(session_id, {"status": "done", "dir": str(web_dir), "files": ["index.html"]})


def fake_codegen_timeout(session_id, requirement_id, spec_text):
    workdir = settings.generated_dir / requirement_id / "web"
    workdir.mkdir(parents=True, exist_ok=True)
    _finish_codegen(session_id, {"status": "timeout", "dir": str(workdir)})


def fake_codegen_unavailable(session_id, requirement_id, spec_text):
    _finish_codegen(session_id, {"status": "unavailable", "note": "fake unavailable"})


@pytest.fixture(scope="session", autouse=True)
def _db_schema():
    db_migrate.upgrade_head()


@pytest.fixture(autouse=True)
def _quote_enabled_by_default(monkeypatch):
    # 기존 흐름 테스트는 견적 단계를 거친다. 베타(견적 없음)는 test_beta_flow.py가 본다.
    monkeypatch.setattr(settings, "quote_enabled", True)


@pytest.fixture
def client(tmp_path, monkeypatch):
    """테스트마다 격리된 generated_dir + 비어 있는 저장소 + 가짜 외부 의존."""
    monkeypatch.setattr(settings, "generated_dir", tmp_path)
    store.reset_all()
    rag.reset_cache()
    monkeypatch.setattr(llm, "chat", default_chat)
    monkeypatch.setattr(llm, "chat_json", default_chat_json)
    monkeypatch.setattr(llm, "embed", default_embed)
    monkeypatch.setattr(llm, "embed_many", lambda texts: [default_embed(t) for t in texts])
    monkeypatch.setattr(design_svc, "screenshot_html", raise_screenshot)
    # 3안 스크린샷도 실제 브라우저를 띄우지 않는다(자리 그림 주소로 폴백). 켜 두면 테스트가 수십 초 느려진다.
    monkeypatch.setattr(design_svc, "screenshot_many", raise_screenshot)
    # UI 에이전트의 뒤쪽 다듬기 스레드도 끈다(무작위로 끼어들지 않게). 에이전트 흐름 테스트만 켠다.
    monkeypatch.setattr(settings, "ui_agent_enabled", False)
    # 사진을 올리면 뒤에서 시안을 다시 만드는데, 테스트 사이 DB 정리와 겹치지 않게 끈다(직접 부르는 테스트는 따로).
    from app.services import photos as photos_svc
    monkeypatch.setattr(photos_svc, "_refresh_designs_async", lambda *a, **k: None)
    monkeypatch.setattr(codegen_svc, "start", fake_codegen_done)
    with TestClient(create_app()) as c:
        yield c
    rag.reset_cache()
