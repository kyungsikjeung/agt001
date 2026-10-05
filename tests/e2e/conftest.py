"""E2E 공용 픽스처 (tests/e2e 전용).

- base_url·browser: 실제 서버(E2E_BASE_URL)에 대고 도는 test_room_e2e.py용. 없으면 skip.
- journey_*: 핵심 여정 점검(test_journeys.py)용. 앱을 이 프로세스 안에서 띄운다(가짜 LLM, TEST_DATABASE_URL).
"""
import os
import socket
import sys
import threading
import time
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

BASE_URL = os.environ.get("E2E_BASE_URL", "").rstrip("/")
ROOT = Path(__file__).resolve().parents[2]
DIST = ROOT / "frontend" / "dist"
# 휴대폰 크기 (mobile_flow.py와 같은 대표 기종 너비)
VIEWPORT = {"width": 390, "height": 844}


@pytest.fixture(scope="session")
def base_url():
    if not BASE_URL:
        pytest.skip("E2E_BASE_URL 미설정 - 실제 서버가 필요하므로 skip")
    return BASE_URL


@pytest.fixture(scope="session")
def browser():
    if not BASE_URL:
        pytest.skip("E2E_BASE_URL 미설정 - 실제 서버가 필요하므로 skip")
    with sync_playwright() as p:
        bw = p.chromium.launch()
        yield bw
        bw.close()


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def journey_server(tmp_path_factory):
    """앱을 이 프로세스 안 uvicorn 스레드로 띄우고 주소를 돌린다.

    가짜(LLM·스크린샷·코드 생성)는 tests/unit/conftest.py 것을 그대로 쓴다. 로그인 쿠키(__Host-, Secure)가
    붙도록 주소는 http://localhost (Chromium은 localhost를 보안 출처로 본다)."""
    if not (DIST / "index.html").is_file() or not (DIST / "builder.html").is_file():
        pytest.skip("frontend/dist 없음 - 먼저 `cd frontend && npm ci && npm run build`")
    # 단위 테스트 conftest가 앱 import 전에 테스트 환경변수를 고정한다(fakes도 그 폴더에 있다).
    sys.path.insert(0, str(ROOT / "tests" / "unit"))
    import uvicorn

    from tests.unit import conftest as unit
    from app import llm, store
    from app.config import settings
    from app.main import create_app
    from app.services import codegen as codegen_svc
    from app.services import design as design_svc
    from app.services import photos as photos_svc
    from app.services import rag

    mp = pytest.MonkeyPatch()
    # 단위 conftest가 끈 것 중 여정이 보는 것은 운영 기본값으로 되돌린다.
    mp.setattr(settings, "publish_login_required", True)
    mp.setattr(settings, "room_invite_required", True)
    mp.setattr(settings, "generated_dir", tmp_path_factory.mktemp("generated"))
    mp.setattr(settings, "ui_agent_enabled", False)
    mp.setattr(llm, "chat", unit.default_chat)
    mp.setattr(llm, "chat_json", unit.default_chat_json)
    mp.setattr(llm, "embed", unit.default_embed)
    mp.setattr(llm, "embed_many", lambda texts: [unit.default_embed(t) for t in texts])
    mp.setattr(design_svc, "screenshot_html", unit.raise_screenshot)
    mp.setattr(design_svc, "screenshot_many", unit.raise_screenshot)
    mp.setattr(photos_svc, "_refresh_designs_async", lambda *a, **k: None)
    mp.setattr(codegen_svc, "start", unit.fake_codegen_done)
    unit.db_migrate.upgrade_head()
    store.reset_all()
    rag.reset_cache()

    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(create_app(), host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 30
    while not server.started:
        if not thread.is_alive() or time.monotonic() > deadline:
            raise RuntimeError("여정 점검용 서버가 뜨지 않았어요")
        time.sleep(0.05)
    yield f"http://localhost:{port}"
    server.should_exit = True
    thread.join(timeout=10)
    rag.reset_cache()
    mp.undo()


@pytest.fixture(scope="session")
def journey_browser(journey_server):
    with sync_playwright() as p:
        bw = p.chromium.launch()
        yield bw
        bw.close()


@pytest.fixture
def journey_context(journey_browser, journey_server):
    """여정마다 새 브라우저 상태(저장소·쿠키 없음), 휴대폰 크기."""
    ctx = journey_browser.new_context(viewport=VIEWPORT, base_url=journey_server)
    ctx.set_default_timeout(15000)
    yield ctx
    ctx.close()
