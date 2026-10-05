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
J3 채팅 → 주소 검색 단추 → 고른 주소가 좌표까지 카드에 들어간다
J4 공개 사이트 → '채팅하기' → 사장님께 물어보기 → 사장님 목록에 보이고 알림 1번
J5 사장님 화면 → '이 휴대폰으로 알림 받기' → 구독 1개 + 시험 알림 1건

바깥 것은 가짜로 둔다(네트워크·과금·외부 장애에 기대지 않는다): 다음 우편번호 창, 카카오 주소 검색,
브라우저 푸시 서비스, 푸시 전송. 가짜 자리는 테스트마다 주석으로 적었다.
"""
import json
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


def _publish_from_template(context, page) -> str:
    """템플릿 → 빌더 → (로그인) → 공개하기. 공개된 가게 키를 돌려준다. J1이 이 길을 따로 검증한다."""
    page.goto("/")
    page.get_by_role("list", name="업종 예시로 채우기").get_by_text("카페", exact=True).click()
    page.wait_for_url(re.compile(r"/start\?room="))
    builder_url = page.url
    _login(context)
    page.goto(builder_url)
    page.get_by_role("button", name="공개하기").click()
    confirm = page.get_by_role("button", name="그대로 공개")
    site = page.get_by_role("link", name="공개 사이트 보기")
    expect(confirm.or_(site)).to_be_visible(timeout=POLL_TIMEOUT)
    if confirm.is_visible():
        confirm.click()
    expect(site).to_be_visible(timeout=POLL_TIMEOUT)
    href = site.get_attribute("href") or ""
    m = re.search(r"/site/([^/?#]+)", href)
    assert m, f"공개 사이트 주소에서 가게 키를 못 찾았어요: {href}"
    return m.group(1)


def test_j3_address_search_saves_map_point(journey_context, monkeypatch):
    """J3 주소 검색 단추 → 고른 주소가 지도 좌표까지 카드에 들어간다.

    가짜 둘: ① 다음 우편번호 창(t1.daumcdn.net 바깥 스크립트) ② 카카오 주소 검색(geo.search).
    우리 몫만 본다 — 단추가 서버가 정한 대로(글자 짐작이 아니라 actions) 뜨는지, 저장이 좌표까지 넣는지.
    """
    from app import llm
    from app.services import geo
    from tests.unit import conftest as unit

    ROAD = "경기도 수원시 팔달구 정조로 790"
    X, Y = 127.0194, 37.2812

    def fill_location(system, user, **kwargs):
        """첫 말에서 주소 한 칸만 뽑는 추출기 (주소 칸이 채워져야 단추 조건이 선다)."""
        if "정조로" in user or "행궁동" in user:
            return '{"updates": [{"slot": "location", "value": "수원 행궁동"}]}'
        return unit.default_chat_json(system, user, **kwargs)

    monkeypatch.setattr(llm, "chat_json", fill_location)
    monkeypatch.setattr(geo, "search", lambda q: [{"road": ROAD, "jibun": "", "x": X, "y": Y}])

    page = journey_context.new_page()
    # 우편번호 창 가짜: embed하면 바로 사장님이 주소를 고른 것처럼 oncomplete를 부른다.
    # 바깥 스크립트는 아예 막아서, 가짜가 안 먹으면 조용히 진짜를 쓰는 일이 없게 한다.
    page.route("**/postcode.v2.js", lambda route: route.abort())
    page.add_init_script("""
      window.daum = {
        Postcode: function (opts) {
          this.embed = function () { opts.oncomplete({ roadAddress: %s, jibunAddress: '' }); };
        },
      };
    """ % json.dumps(ROAD, ensure_ascii=False))
    page.goto("/")
    page.get_by_label("만들고 싶은 사이트 설명").fill("행궁동 작은 카페예요. 오시는 길을 보여 주고 싶어요.")
    page.get_by_role("button", name="시작하기", exact=True).click()
    page.wait_for_url(re.compile(r"/room\.html\?room="))
    room_id = re.search(r"room=([^&]+)", page.url).group(1)

    # 서버가 보낸 actions대로 주소 단추가 뜬다(안내 글도 함께)
    addr_btn = page.get_by_role("button", name=re.compile("정확한 주소 검색"))
    expect(addr_btn).to_be_visible(timeout=POLL_TIMEOUT)
    addr_btn.click()

    # 시트가 열리고 가짜 우편번호 창이 주소를 골라 준다 → 저장
    expect(page.get_by_text("고른 주소: " + ROAD)).to_be_visible()
    page.get_by_label("상세 주소(층·호)").fill("2층")
    page.get_by_role("button", name="저장", exact=True).click()
    expect(page.locator("#addrSheetWrap")).to_be_hidden(timeout=POLL_TIMEOUT)

    # 카드에 좌표가 들어갔다 (지도·오시는 길이 이것으로 그려진다)
    from app import store

    card = store.read_session(store.read_room(room_id)["session_id"])["prd"]
    saved = card.get("location_geo")
    assert saved, "주소를 저장했는데 지도 좌표가 카드에 없어요"
    assert (saved["x"], saved["y"]) == (X, Y), saved
    assert saved["road"] == ROAD and saved["detail"] == "2층", saved
    assert card["slots"]["location"]["value"] == f"{ROAD} 2층", card["slots"]["location"]


def test_j4_published_site_guest_chat_to_owner(journey_context, monkeypatch):
    """J4 공개 사이트 '채팅하기' → 손님이 사장님께 물어보기 → 사장님 목록에 보이고 알림 1번.

    가짜 하나: 사장님 카톡 알림(notify.owner_kakao) — 바깥 카카오 API 대신 호출만 센다.
    """
    from app.services import notify

    calls = []
    monkeypatch.setattr(notify, "owner_kakao", lambda room_id, text: calls.append(text))

    page = journey_context.new_page()
    site_key = _publish_from_template(journey_context, page)

    # 공개 사이트에 '채팅하기' 링크가 있다 (링크가 빠지면 손님이 채팅에 들어올 길이 없다)
    page.goto(f"/site/{site_key}/")
    chat_link = page.get_by_role("link", name="채팅하기").first
    expect(chat_link).to_have_attribute("href", re.compile(rf"/chat/{re.escape(site_key)}$"))

    # 손님 채팅: 인사 + 단추. '사장님께 직접 물어보기' → 적은 글이 사장님에게 간다
    page.goto(f"/chat/{site_key}")
    ask_owner = page.get_by_role("button", name="사장님께 직접 물어보기")
    expect(ask_owner).to_be_visible(timeout=POLL_TIMEOUT)
    ask_owner.click()
    expect(page.get_by_text(re.compile("무엇이든 적어 주세요"))).to_be_visible(timeout=POLL_TIMEOUT)
    page.get_by_label("메시지").fill("주말에 단체 10명 가도 돼요?")
    page.get_by_role("button", name="보내기").click()
    expect(page.get_by_text(re.compile("사장님께 전했어요"))).to_be_visible(timeout=POLL_TIMEOUT)

    # 사장님 쪽: 채팅 목록에 보인다 (사장님 화면 '채팅' 탭이 읽는 그 API)
    res = page.request.get(f"/api/owner/shops/{site_key}/chats")
    assert res.ok, f"{res.status} {res.text()}"
    threads = res.json().get("threads") or res.json().get("chats") or []
    assert len(threads) == 1, res.json()
    assert "단체 10명" in json.dumps(threads, ensure_ascii=False), threads

    # 알림은 한 번만 (손님이 글을 보낼 때마다 사장님 휴대폰이 울리면 안 된다)
    assert len(calls) == 1, calls
    page.get_by_label("메시지").fill("아, 그리고 주차도 되나요?")
    page.get_by_role("button", name="보내기").click()
    page.wait_for_timeout(500)
    assert len(calls) == 1, f"연달아 보낸 글에도 알림이 또 갔어요: {calls}"


def test_j5_owner_turns_on_phone_push(journey_context, monkeypatch):
    """J5 사장님 화면 → '이 휴대폰으로 알림 받기' → 구독 1개 + 시험 알림 1건.

    가짜 둘: ① 브라우저 푸시 서비스(서비스워커·PushManager — 헤드리스에는 진짜가 없다)
    ② 푸시 전송(push._post) — 구글 FCM에 실제로 보내지 않고 호출만 센다.
    """
    from app.config import settings
    from app.db.models import PushSubscriptionRow
    from app.db.session import get_sessionmaker
    from app.services import push
    from sqlalchemy import select

    monkeypatch.setattr(settings, "vapid_private_key", push.generate_private_key())
    push.invalidate() if hasattr(push, "invalidate") else None
    sent = []
    monkeypatch.setattr(push, "_post", lambda endpoint, body, key, urgency="high": sent.append(endpoint) or 201)

    page = journey_context.new_page()
    # 사장님 화면의 알림 카드는 가게가 하나라도 있을 때 뜬다 → 먼저 사이트를 공개한다(로그인 포함).
    _publish_from_template(journey_context, page)
    # 브라우저 푸시 가짜: 권한 허용 + 구독 하나를 돌려준다(주소는 허용된 FCM 주소여야 한다).
    page.add_init_script("""
      const ENDPOINT = 'https://fcm.googleapis.com/fcm/send/journey-j5';
      const b64 = (n) => btoa(String.fromCharCode(...new Uint8Array(n))).replace(/\+/g, '-')
        .replace(/\//g, '_').replace(/=+$/, '');
      let made = null;
      async function makeSub() {
        // p256dh는 진짜 P-256 공개점이어야 서버 검사(check_keys)를 통과한다.
        const kp = await crypto.subtle.generateKey({ name: 'ECDH', namedCurve: 'P-256' }, true, ['deriveBits']);
        const pub = new Uint8Array(await crypto.subtle.exportKey('raw', kp.publicKey));
        const auth = new Uint8Array(16); crypto.getRandomValues(auth);
        return {
          endpoint: ENDPOINT,
          getKey: (n) => (n === 'p256dh' ? pub.buffer : auth.buffer),
          toJSON: () => ({ endpoint: ENDPOINT, keys: { p256dh: b64(pub), auth: b64(auth) } }),
          unsubscribe: async () => true,
        };
      }
      const reg = {
        pushManager: {
          getSubscription: async () => null,
          subscribe: async () => (made = made || await makeSub()),
        },
        showNotification: async () => {},
      };
      Object.defineProperty(navigator, 'serviceWorker', {
        value: { register: async () => reg, ready: Promise.resolve(reg), getRegistration: async () => reg },
        configurable: true,
      });
      window.Notification = { permission: 'default', requestPermission: async () => 'granted' };
    """)
    page.goto("/owner?push=1")
    turn_on = page.get_by_role("button", name="이 휴대폰으로 알림 받기")
    expect(turn_on).to_be_visible(timeout=POLL_TIMEOUT)
    turn_on.click()
    expect(page.get_by_text(re.compile("켜졌어요"))).to_be_visible(timeout=POLL_TIMEOUT)

    # 구독 1개 + 시험 알림 1건
    with get_sessionmaker()() as db:
        rows = db.scalars(select(PushSubscriptionRow.endpoint)).all()
    assert list(rows) == ["https://fcm.googleapis.com/fcm/send/journey-j5"], rows
    assert sent == ["https://fcm.googleapis.com/fcm/send/journey-j5"], sent
