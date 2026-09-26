"""휴대폰 크기 흐름 점검 (playwright sync API, 단독 스크립트).

실행 (실제 서버에 대고 Claude가 직접 돌린다):
  .venv/bin/python tests/e2e/mobile_flow.py https://예시서버 --out /tmp/mobile-out

흐름: 랜딩 열기 -> 입력 -> 채팅방 -> "시안 먼저" -> "승인" -> "진행"
  -> 시안 카드 3장 -> "이걸로 할게요"(2안) -> "공개" 또는 "그대로 공개"
  -> 공개 사이트 열림 -> 문의 폼 제출 -> 채팅방에 문의 알림.

단계마다 --out 폴더에 스크린샷을 남기고 걸린 시간·성공 여부를 표로 출력한다.
BASE_URL은 반드시 인자로 지정해야 한다 (기본값 없음, 실수 방지).
"""
import argparse
import re
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

# 휴대폰 크기 (대표 기종 너비) + 모바일 판정용 UA
VIEWPORT = {"width": 390, "height": 844}
MOBILE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 "
    "Mobile/15E148 Safari/604.1"
)

# 채팅방 첫 입력 (랜딩 입력창·채팅방 첫 메시지로 함께 쓰인다)
FIRST_MESSAGE = "우리 동네 분식집 소개 사이트를 만들고 싶어요. 메뉴는 떡볶이·순대·튀김이에요."

# 공개 사이트 주소 찾기 (채팅 답장 "사이트를 열었어요: .../site/<id>/")
SITE_RE = re.compile(r"/site/([A-Za-z0-9-]+)/?")


def _shot(page, out: Path, name: str) -> None:
    """지금 화면을 --out 폴더에 저장한다 (실패해도 흐름은 계속 간다)."""
    try:
        page.screenshot(path=str(out / name))
    except Exception:
        pass


def _send(page, text: str) -> None:
    """채팅방 입력창에 적고 보내기를 누른다."""
    page.locator("#input").fill(text)
    page.locator("#sendBtn").click()


def _wait_log_has(page, piece: str, timeout_ms: int) -> None:
    """채팅 기록(#log)에 piece 글자가 나타날 때까지 기다린다."""
    page.wait_for_function(
        "(t) => (document.querySelector('#log') || {}).innerText?.includes(t)",
        arg=piece,
        timeout=timeout_ms,
    )


def _wait_cards(page, count: int, timeout_ms: int) -> None:
    """시안 카드(.design-card)가 count개 보일 때까지 기다린다."""
    page.wait_for_function(
        "(n) => document.querySelectorAll('.design-card').length >= n",
        arg=count,
        timeout=timeout_ms,
    )


def _find_site_url(page) -> str | None:
    """채팅 기록에서 공개 사이트 주소를 찾는다 (없으면 None)."""
    text = page.evaluate("() => document.querySelector('#log')?.innerText || ''")
    m = SITE_RE.search(text)
    if not m:
        return None
    return m.group(0)


def run(base_url: str, out: Path, step_timeout_ms: int) -> int:
    out.mkdir(parents=True, exist_ok=True)
    base_url = base_url.rstrip("/")
    rows: list[tuple[str, bool, float, str]] = []
    room_url = ""
    site_url = ""

    def step(name: str, shot_name: str, fn) -> bool:
        """한 단계를 실행하고 시간·성공 여부를 기록한다. 실패하면 False."""
        nonlocal room_url, site_url
        start = time.monotonic()
        ok = True
        note = ""
        try:
            ret = fn()
            if isinstance(ret, str) and ret:
                note = ret
        except Exception as e:
            ok = False
            note = f"{type(e).__name__}: {e}"[:160]
        secs = time.monotonic() - start
        try:
            page.screenshot(path=str(out / shot_name))
        except Exception:
            pass
        rows.append((name, ok, secs, note))
        return ok

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            ctx = browser.new_context(
                viewport=VIEWPORT,
                is_mobile=True,
                has_touch=True,
                user_agent=MOBILE_UA,
            )
            page = ctx.new_page()

            # 1. 랜딩 열기
            def s1():
                page.goto(f"{base_url}/", wait_until="networkidle")
                page.locator("#prompt-input").wait_for(timeout=step_timeout_ms)
                return "랜딩 입력창 확인"

            if not step("랜딩 열기", "01-랜딩.png", s1):
                return _report(rows)

            # 2. 입력 후 채팅방으로 이동
            def s2():
                nonlocal room_url
                page.locator("#prompt-input").fill(FIRST_MESSAGE)
                page.locator("button.send").click()
                page.wait_for_url("**/room.html?room=*", timeout=step_timeout_ms)
                room_url = page.url
                return room_url

            if not step("입력 -> 채팅방 이동", "02-채팅방.png", s2):
                return _report(rows)

            # 3. "시안 먼저" (남은 질문 건너뛰고 요약으로)
            def s3():
                _send(page, "시안 먼저")
                _wait_log_has(page, "승인", step_timeout_ms)
                return "요약 + 승인 요청 확인"

            if not step('"시안 먼저"', "03-시안먼저.png", s3):
                return _report(rows)

            # 4. "승인" (견적 단계로)
            def s4():
                _send(page, "승인")
                _wait_log_has(page, "진행", step_timeout_ms)
                return "견적 + 진행 요청 확인"

            if not step('"승인"', "04-승인.png", s4):
                return _report(rows)

            # 5. "진행" (시안 3안 안내가 올 때까지)
            def s5():
                _send(page, "진행")
                _wait_log_has(page, "2안", step_timeout_ms * 2)
                return "시안 안내 확인"

            if not step('"진행"', "05-진행.png", s5):
                return _report(rows)

            # 6. 시안 카드 3장 보임
            def s6():
                _wait_cards(page, 3, step_timeout_ms)
                n = page.locator(".design-card").count()
                if n < 3:
                    raise AssertionError(f"시안 카드 {n}장 (3장 필요)")
                return f"카드 {n}장"

            if not step("시안 카드 3장", "06-시안카드.png", s6):
                return _report(rows)

            # 7. 2안 카드의 "이걸로 할게요" 누르기
            def s7():
                page.locator(".design-card").nth(1).locator(".design-pick-btn").click()
                _wait_log_has(page, "2안", step_timeout_ms)
                return "2안 선택 확인"

            if not step('"이걸로 할게요"(2안)', "07-2안선택.png", s7):
                return _report(rows)

            # 8. "공개" (빈 자리가 남았으면 "그대로 공개"로 한 번 더)
            def s8():
                nonlocal site_url
                _send(page, "공개")
                # 빈 자리 확인 질문("그대로 공개")이 오면 바로 답하고, 아니면 공개 주소를 기다린다
                page.wait_for_function(
                    "() => { const t = (document.querySelector('#log') || {}).innerText || '';"
                    " return t.includes('사이트를 열었어요') || t.includes(\"'그대로 공개'\"); }",
                    timeout=step_timeout_ms * 2,
                )
                if "사이트를 열었어요" not in page.evaluate("() => document.querySelector('#log').innerText"):
                    _send(page, "그대로 공개")
                _wait_log_has(page, "사이트를 열었어요", step_timeout_ms * 2)
                found = _find_site_url(page)
                if not found:
                    raise AssertionError("채팅 기록에 /site/ 주소 없음")
                if found.startswith("/"):
                    found = base_url + found
                site_url = found
                return site_url

            if not step('"공개"', "08-공개.png", s8):
                return _report(rows)

            # 9. 공개 사이트 열림
            site_page = ctx.new_page()

            def s9():
                site_page.goto(site_url, wait_until="networkidle")
                # 빈 자리 표시가 있어도 페이지는 열려야 한다
                body = site_page.locator("body")
                body.wait_for(timeout=step_timeout_ms)
                return site_url

            ok9 = step("공개 사이트 열림", "09-공개사이트.png", s9)
            # 스크린샷은 site_page에서 다시 찍는다 (step은 page 기준이므로)
            _shot(site_page, out, "09-공개사이트.png")
            if not ok9:
                return _report(rows)

            # 10. 문의 폼 제출
            def s10():
                site_page.locator('input[name="contact"]').fill("010-1234-5678")
                msg = site_page.locator('textarea[name="message"]')
                msg.fill("휴대폰 흐름 점검 문의입니다.")
                name_box = site_page.locator('input[name="name"]')
                if name_box.count():
                    name_box.fill("점검 손님")
                agree = site_page.locator('input[name="agree"]')
                if agree.count() and not agree.is_checked():
                    agree.check()
                site_page.locator('form button[type="submit"], form input[type="submit"]').first.click()
                site_page.wait_for_function(
                    "() => document.body.innerText.includes('문의가 전달됐어요')",
                    timeout=step_timeout_ms,
                )
                return "문의 접수 화면 확인"

            ok10 = step("문의 폼 제출", "10-문의제출.png", s10)
            _shot(site_page, out, "10-문의제출.png")
            site_page.close()
            if not ok10:
                return _report(rows)

            # 11. 채팅방에 문의 알림
            def s11():
                page.bring_to_front()
                # 폴링(4초)이 한 번 돌 시간을 주고, 없으면 직접 새로고침한다
                try:
                    _wait_log_has(page, "문의", step_timeout_ms * 2)
                except Exception:
                    page.reload(wait_until="networkidle")
                    _wait_log_has(page, "문의", step_timeout_ms)
                return "문의 알림 확인"

            step("채팅방 문의 알림", "11-문의알림.png", s11)
            return _report(rows)
        finally:
            browser.close()
    return 1


def _report(rows: list[tuple[str, bool, float, str]]) -> int:
    """단계 표를 출력하고 전체 성공이면 0, 아니면 1을 돌려준다."""
    print(f"{'단계':<22}{'결과':<8}{'시간(초)':<10}비고")
    print("-" * 70)
    all_ok = True
    for name, ok, secs, note in rows:
        mark = "성공" if ok else "실패"
        if not ok:
            all_ok = False
        print(f"{name:<22}{mark:<8}{secs:<10.1f}{note}")
    print("-" * 70)
    print(f"합계: {len(rows)}단계, 성공 {sum(1 for r in rows if r[1])}단계")
    return 0 if all_ok else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="휴대폰 크기(390x844) 흐름 점검")
    parser.add_argument("base_url", help="점검 대상 주소 (예: https://예시서버)")
    parser.add_argument("--out", default="mobile_flow_out", help="스크린샷 폴더 (기본: mobile_flow_out)")
    parser.add_argument(
        "--step-timeout",
        type=int,
        default=60,
        help="단계당 대기 초 (기본: 60, 진행·공개는 2배)",
    )
    args = parser.parse_args(argv)
    if not args.base_url:
        parser.error("BASE_URL을 반드시 지정해야 한다")
    return run(args.base_url, Path(args.out), args.step_timeout * 1000)


if __name__ == "__main__":
    sys.exit(main())
