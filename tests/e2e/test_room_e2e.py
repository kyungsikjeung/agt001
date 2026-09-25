"""room.html 다인원 공유방 브라우저 E2E 테스트 (playwright sync API + pytest).

실행: E2E_BASE_URL=http://127.0.0.1:8643 .venv/bin/python -m pytest tests/e2e -q
  (서버는 사용자가 따로 띄운다고 가정. 기본 `pytest` 실행에는 포함되지 않는다 -
  pyproject.toml testpaths가 tests/unit이라 의도적으로 제외됨.)

과거 회귀 커버리지:
  (1) 카카오 인앱브라우저/평문 HTTP에서 localStorage·crypto.randomUUID 예외로
      스크립트 전체 사망 -> safeGet/safeSet/makeMemberId 폴백 (test 4, 5)
  (2) 폴링 경쟁으로 자기 메시지 중복 렌더링 -> pollInFlight (test 2)
  (3) 새 방 첫 입장 시 온보딩 안내 1회 (test 1, 3)

NIM을 실제로 부르는 흐름(견적/코드생성)은 테스트하지 않는다. 메시지를 보내면
서버가 RAG NIM 임베딩을 호출할 수 있으나, 여기서는 AI 답변 내용이 아니라
입장·전송·표시 여부와 개수만 본다.
"""
import os
import uuid

import pytest
from playwright.sync_api import expect

BASE_URL = os.environ.get("E2E_BASE_URL", "").rstrip("/")

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(
        not os.environ.get("E2E_BASE_URL"),
        reason="E2E_BASE_URL 미설정 - 실제 서버가 필요하므로 skip",
    ),
]

# room.html ONBOARDING_TEXT 중 서버 폴백 답변과 겹치지 않는 고유 조각
# (서버 폴백: "안녕하세요! 어떤 프로젝트를 원하시나요? ...")
ONBOARDING_SNIPPET = "웹사이트 제작을 돕는 AI 어시스턴트"

JOIN_TIMEOUT = 15000
POLL_TIMEOUT = 15000
# room.html 폴링 간격 4초 -> 2회 이상 돌고도 안정적인지 본다
DUPLICATE_SETTLE_MS = 9000


def _uid() -> str:
    return uuid.uuid4().hex[:8]


def _join(page, nickname: str) -> None:
    """닉네임 입력 -> 입장하기. 오버레이 제거 + ?room= + 입장 system 메시지까지 대기."""
    page.locator("#nicknameInput").fill(nickname)
    page.locator("#nicknameJoinBtn").click()
    page.locator("#nicknameOverlay").wait_for(state="detached", timeout=JOIN_TIMEOUT)
    page.wait_for_function(
        "() => new URL(location.href).searchParams.has('room')",
        timeout=JOIN_TIMEOUT,
    )
    expect(
        page.locator("#log .kind-system .text", has_text=f"{nickname}님이 입장했습니다")
    ).to_be_visible(timeout=JOIN_TIMEOUT)


def _send(page, text: str) -> None:
    page.locator("#input").fill(text)
    page.locator("#sendBtn").click()


def _exact_chat_count(page, text: str) -> int:
    """같은 텍스트의 .kind-chat 버블 개수 (정확히 일치, 부분일치 아님)."""
    return page.evaluate(
        "(t) => [...document.querySelectorAll('#log .kind-chat .text')]"
        ".filter((el) => el.textContent === t).length",
        text,
    )


@pytest.mark.e2e
def test_new_room_join_shows_onboarding_once(base_url, browser):
    ctx = browser.new_context()
    try:
        page = ctx.new_page()
        page.goto(f"{base_url}/room.html")
        _join(page, f"e2e-새방-{_uid()}")

        assert "room=" in page.url
        onboarding = page.locator("#log .kind-ai_reply .text", has_text=ONBOARDING_SNIPPET)
        expect(onboarding).to_have_count(1, timeout=JOIN_TIMEOUT)
        # 폴링 1회 이상 지난 뒤에도 정확히 1개 유지
        page.wait_for_timeout(5000)
        expect(onboarding).to_have_count(1)
    finally:
        ctx.close()


@pytest.mark.e2e
def test_sent_message_renders_exactly_once(base_url, browser):
    """폴링 경쟁 중복 렌더링 회귀: 전송 후 폴링 2회 이상 지나도 같은 텍스트 버블 1개."""
    ctx = browser.new_context()
    try:
        page = ctx.new_page()
        page.goto(f"{base_url}/room.html")
        _join(page, f"e2e-중복-{_uid()}")

        text = f"중복체크-{_uid()}"
        _send(page, text)
        expect(
            page.locator("#log .kind-chat .text", has_text=text)
        ).to_be_visible(timeout=JOIN_TIMEOUT)

        page.wait_for_timeout(DUPLICATE_SETTLE_MS)
        assert _exact_chat_count(page, text) == 1
    finally:
        ctx.close()


@pytest.mark.e2e
def test_two_users_share_room(base_url, browser):
    ctx1 = browser.new_context()
    ctx2 = browser.new_context()
    try:
        p1 = ctx1.new_page()
        p1.goto(f"{base_url}/room.html")
        nick1 = f"e2e-일번-{_uid()}"
        _join(p1, nick1)
        room_url = p1.url
        assert "room=" in room_url

        p2 = ctx2.new_page()
        p2.goto(room_url)
        nick2 = f"e2e-이번-{_uid()}"
        _join(p2, nick2)

        # 두 번째 입장자에게 온보딩이 뜨면 안 됨 (입장 ping 이후 1폴링 이상 대기 후 확인)
        expect(
            p2.locator("#log .kind-system .text", has_text=nick2)
        ).to_be_visible(timeout=JOIN_TIMEOUT)
        p2.wait_for_timeout(5000)
        expect(
            p2.locator("#log .kind-ai_reply .text", has_text=ONBOARDING_SNIPPET)
        ).to_have_count(0)
        # 첫 입장자의 온보딩은 프론트 전용이라 두 번째 화면에 전파되지 않음
        expect(
            p1.locator("#log .kind-ai_reply .text", has_text=ONBOARDING_SNIPPET)
        ).to_have_count(1)

        # 서로의 메시지가 폴링으로 보임
        m1 = f"일번메시지-{_uid()}"
        _send(p1, m1)
        expect(
            p2.locator("#log .kind-chat .text", has_text=m1)
        ).to_be_visible(timeout=POLL_TIMEOUT)

        m2 = f"이번메시지-{_uid()}"
        _send(p2, m2)
        expect(
            p1.locator("#log .kind-chat .text", has_text=m2)
        ).to_be_visible(timeout=POLL_TIMEOUT)

        expect(p1.locator("#memberCount")).to_contain_text("2명 참여 중", timeout=POLL_TIMEOUT)
        expect(p2.locator("#memberCount")).to_contain_text("2명 참여 중", timeout=POLL_TIMEOUT)
    finally:
        ctx1.close()
        ctx2.close()


@pytest.mark.e2e
def test_join_and_send_with_blocked_local_storage(base_url, browser):
    """localStorage 접근이 SecurityError를 던져도 입장·전송이 된다 (스크립트 생존)."""
    ctx = browser.new_context()
    ctx.add_init_script(
        "Object.defineProperty(window, 'localStorage',"
        " { get() { throw new DOMException('blocked', 'SecurityError'); } });"
    )
    try:
        page = ctx.new_page()
        page.goto(f"{base_url}/room.html")
        _join(page, f"e2e-스토리지-{_uid()}")

        text = f"스토리지차단-{_uid()}"
        _send(page, text)
        expect(
            page.locator("#log .kind-chat .text", has_text=text)
        ).to_be_visible(timeout=JOIN_TIMEOUT)
    finally:
        ctx.close()


@pytest.mark.e2e
def test_join_without_crypto_random_uuid(base_url, browser):
    """crypto.randomUUID이 없어도(평문 HTTP) makeMemberId 폴백으로 입장된다."""
    ctx = browser.new_context()
    ctx.add_init_script(
        "(() => {"
        " try {"
        "   const c = window.crypto;"
        "   if (c) {"
        "     try { delete c.randomUUID; } catch (e) {}"
        "     try { c.randomUUID = undefined; } catch (e) {}"
        "   }"
        " } catch (e) {}"
        "})();"
    )
    try:
        page = ctx.new_page()
        page.goto(f"{base_url}/room.html")
        assert page.evaluate("() => typeof window.crypto?.randomUUID") != "function"
        _join(page, f"e2e-uuid-{_uid()}")
        assert "room=" in page.url
    finally:
        ctx.close()
