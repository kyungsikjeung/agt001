"""핵심 여정 자동 점검 (UX_GAP_PLAN Q2). 휴대폰 크기(390x844) 실제 브라우저로 사장님 길을 따라간다.

앱은 이 프로세스 안에서 뜬다(tests/e2e/conftest.py journey_server): 실제 라우트·DB(TEST_DATABASE_URL),
LLM·스크린샷·코드 생성만 tests/unit 가짜. 로그인은 카카오 대신 세션 행을 만들고 쿠키를 넣는다.

로컬 실행 (Docker agt001-pg-test :55432, 프론트 빌드 필요 - 없으면 skip):
  (cd frontend && npm ci && npm run build)
  NIM_API_KEY=ci-dummy PRECOMPUTE_EMBEDDINGS=false \\
  TEST_DATABASE_URL=postgresql+psycopg://agt001:agt001@localhost:55432/agt001_test \\
  .venv/bin/python -m pytest tests/e2e/test_journeys.py -q
  (기본 `pytest`에는 안 들어간다 - pyproject testpaths가 tests/unit·tests/engine)

J1 템플릿 → 빌더 → 공개하기 → 로그인 → 다시 공개하기 (#41 회귀: 로그인해도 계속 '로그인해 주세요')
J2 랜딩 → 채팅방 첫 말 → 질문 단추 '직접 입력'·'알아서 해주세요' (#42)
"""
import re
import uuid

import pytest
from playwright.sync_api import expect

pytestmark = pytest.mark.journey

# 채팅방 폴링(4초)을 한두 번 기다릴 수 있는 여유
POLL_TIMEOUT = 10000


def _login(context) -> None:
    """카카오 로그인 대신: 계정 + 세션을 만들고 세션 쿠키를 브라우저에 넣는다.

    __Host- 쿠키는 Secure여야 한다. Chromium은 http://localhost를 보안 출처로 봐서 받아 준다
    (url로 넣으면 Playwright가 http라 Secure를 빼서 거부된다)."""
    from app.db.models import UserRow
    from app.db.session import get_sessionmaker
    from app.services import auth

    user_id = str(uuid.uuid4())
    with get_sessionmaker()() as db, db.begin():
        db.add(UserRow(id=user_id, nickname="여정 사장님"))
    context.add_cookies([{"name": auth.SESSION_COOKIE, "value": auth.create_session(user_id), "domain": "localhost",
                          "path": "/", "secure": True, "httpOnly": True, "sameSite": "Lax"}])


def test_j1_template_builder_publish_after_login(journey_context):
    page = journey_context.new_page()
    page.goto("/")
    page.get_by_role("list", name="업종 예시로 채우기").get_by_text("카페", exact=True).click()
    page.wait_for_url(re.compile(r"/start\?room="))
    builder_url = page.url
    publish = page.get_by_role("button", name="공개하기")
    kakao = page.get_by_role("link", name="카카오로 계속하기")

    # 로그인 전: 공개하기 → 로그인 단계
    publish.click()
    expect(kakao).to_be_visible()

    # 카카오에서 돌아온 것처럼: 쿠키를 넣고 빌더를 다시 연다
    _login(journey_context)
    page.goto(builder_url)
    publish.click()
    confirm = page.get_by_role("button", name="그대로 공개")
    site = page.get_by_role("link", name="공개 사이트 보기")
    # 공개는 사이트를 그리고 스크린샷을 재시도하는 왕복이라 expect 기본 5초보다 넉넉히
    expect(confirm.or_(site).or_(kakao)).to_be_visible(timeout=POLL_TIMEOUT)
    expect(kakao).to_have_count(0)  # 로그인 단계가 다시 나오면 #41 재발
    if confirm.is_visible():
        confirm.click()
    expect(site).to_be_visible(timeout=POLL_TIMEOUT)
    expect(site).to_have_attribute("href", re.compile(r"/site/"))


def test_j2_chat_question_buttons(journey_context):
    page = journey_context.new_page()
    page.goto("/")
    page.get_by_label("만들고 싶은 사이트 설명").fill("동네 작은 카페예요. 대표 메뉴와 영업시간을 보여 주고 싶어요.")
    page.get_by_role("button", name="시작하기", exact=True).click()
    page.wait_for_url(re.compile(r"/room\.html\?room="))
    room_url = page.url

    # 첫 말이 가고 질문 단추가 뜬다: 1) 직접 입력 2) 알아서 해주세요
    choices = page.locator("#choices")
    type_it = choices.get_by_role("button", name="직접 입력", exact=True)
    let_ai = choices.get_by_role("button", name="알아서 해주세요", exact=True)
    expect(type_it).to_be_visible(timeout=POLL_TIMEOUT)
    expect(let_ai).to_be_visible()
    log_items = page.locator("#log > *")
    before = log_items.count()

    # '직접 입력': 보내지 않고 입력칸으로. fetch는 onclick 안에서 바로 나가므로 요청 기록으로 본다
    posts = []
    page.on("request", lambda r: posts.append(r.url) if r.method == "POST" and r.url.endswith("/chat") else None)
    type_it.click()
    expect(page.locator("#input")).to_be_focused()
    expect(page.locator("#input")).to_have_attribute("placeholder", "여기에 적어 주세요")
    assert posts == [], f"'직접 입력'이 말을 보냈어요: {posts}"
    page.evaluate("pollMessages()")  # 서버 기록을 한 번 더 받아도 새 말이 없어야 한다
    expect(log_items).to_have_count(before)

    # 단추 막대는 같은 질문이면 다시 안 그린다 → 방을 다시 열어 단추를 되살린다(방장 그대로).
    # 제품 빈틈(따로 고칠 것): '직접 입력' 뒤엔 다시 열기 전까지 '알아서 해주세요'로 못 돌아가고,
    # 랜딩에서 온 '사장님' 닉네임이 저장되지 않아 다시 열면 닉네임을 또 묻는다.
    page.goto(room_url)
    page.get_by_placeholder("닉네임").fill("사장님")
    page.get_by_role("button", name="입장하기").click()
    expect(let_ai).to_be_visible(timeout=POLL_TIMEOUT)

    # '알아서 해주세요': 남은 질문 없이 요약 + 시안 동의 단계
    let_ai.click()
    vote_bar = page.locator("#voteBar")
    expect(vote_bar).to_be_visible(timeout=POLL_TIMEOUT)
    expect(vote_bar).to_contain_text("이 내용으로 시안을 만들까요?")
    expect(vote_bar.get_by_role("button", name="👍 동의")).to_be_visible()
    expect(page.locator("#choiceBar")).to_be_hidden()
    # 화면은 같은 질문을 다시 안 그리므로(choiceKey) 서버 응답을 직접 본다: 남은 질문 없이 시안 동의 단계
    room_id = re.search(r"room=([^&]+)", room_url).group(1)
    res = page.request.get(f"/room/{room_id}/messages?since=0", headers={"X-Member-Id": page.evaluate("memberId")})
    assert res.ok, res.status
    data = res.json()
    assert data["question"] is None, f"'알아서 해주세요' 뒤에도 질문이 남았어요: {data['question']}"
    assert data["state"] == "AWAIT_APPROVAL", data["state"]
