"""운영 스모크 점검 (REHEARSAL_1015 §3). 읽기만 한다(GET). 배포 뒤·리허설 때 한 번에 돌린다.

사용법:
  python scripts/smoke_prod.py https://144.24.91.250.sslip.io [--preview https://144-24-91-250.sslip.io] [--site <공개 가게 키>]

- 앱 페이지·로그인 경로·주소 분리(미리보기 주소는 앱 페이지를 열지 않음)를 본다.
- --site를 주면 공개 사이트를 열고, 그 안의 "채팅하기" 링크를 **실제로 따라가** 열리는지 본다(10/1 404 같은 것).
- 가게 이름·전화·주소는 출력하지 않는다. 실패가 하나라도 있으면 종료 코드 1.
"""
import argparse
import re
import sys
from urllib.parse import urljoin

import httpx

OK, BAD, INFO = "✅", "❌", "ℹ️"


def _get(client: httpx.Client, url: str, **kw):
    try:
        return client.get(url, **kw)
    except httpx.HTTPError as e:
        return e


def run(app: str, preview: str, site: str = "", transport=None) -> list:
    rows = []

    def check(name: str, ok, note: str = "") -> None:
        rows.append((name, OK if ok is True else (INFO if ok is None else BAD), note))

    def status(r) -> str:
        return str(r.status_code) if isinstance(r, httpx.Response) else type(r).__name__

    with httpx.Client(timeout=15, follow_redirects=False, transport=transport) as c:
        r = _get(c, f"{app}/health")
        check("헬스", isinstance(r, httpx.Response) and r.status_code == 200, status(r))
        for path, must in (("/", ""), ("/room.html", "사장님 화면 (예약·주문·채팅·스탬프)"), ("/owner", ""),
                           ("/settings", ""), ("/privacy.html", "최종 개정"), ("/terms.html", "")):
            r = _get(c, f"{app}{path}")
            good = isinstance(r, httpx.Response) and r.status_code == 200 and (not must or must in r.text)
            check(f"앱 페이지 {path}", good, status(r) + ("" if good or not must else " · 글자 없음"))
        r = _get(c, f"{app}/api/me")
        check("로그인 확인 경로", isinstance(r, httpx.Response) and r.status_code == 401, status(r))
        r = _get(c, f"{preview}/room.html")
        check("주소 분리(미리보기에서 앱 페이지 막힘)", isinstance(r, httpx.Response) and r.status_code == 404, status(r))
        if not site:
            check("공개 사이트", None, "--site 없음(건너뜀)")
            return rows
        url = f"{preview}/site/{site}/"
        r = _get(c, url)
        if not (isinstance(r, httpx.Response) and r.status_code == 200):
            check("공개 사이트", False, status(r))
            return rows
        page = r.text
        check("공개 사이트", True, "200")
        check("공개 사이트 격리(CSP sandbox)", "sandbox" in r.headers.get("content-security-policy", ""), "")
        m = re.search(r'href="([^"]*/chat/' + re.escape(site) + r')"', page)
        if m:
            target = urljoin(url, m.group(1))
            r2 = _get(c, target)
            check("채팅하기 링크 따라가기", isinstance(r2, httpx.Response) and r2.status_code == 200,
                  f"{status(r2)} · {'앱 주소' if target.startswith(app) else '다른 주소'}")
        else:
            check("채팅하기 링크", None, "없음(손님 채팅 꺼짐이거나 앱 주소 설정 없음)")
        r = _get(c, f"{app}/api/chat/{site}/messages", headers={"Cookie": f"agt_chat_{site[:40]}=smoke"})
        check("손님 채팅 새 글 확인 API", isinstance(r, httpx.Response) and r.status_code == 200, status(r))
        if "s-map__live" in page:
            check("지도(카카오)", "dapi.kakao.com/v2/maps/sdk.js?appkey=" in page, "좌표 있음")
        else:
            check("지도(카카오)", None, "좌표 없음 → 예시 지도(주소 검색 전)")
        tags = re.findall(r"/art-lib/[a-z0-9-]+\.webp", page)
        if tags:
            r = _get(c, urljoin(url, tags[0]))
            check("메뉴 태그 사진", isinstance(r, httpx.Response) and r.status_code == 200, f"{len(set(tags))}장 · 첫 장 {status(r)}")
        else:
            check("메뉴 태그 사진", None, "없음(창고 미리 채우기 전이거나 사장님 사진)")
        check("공지", None, "있음" if "s-notice" in page else "없음")
    return rows


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(description="운영 스모크 점검(읽기만)")
    ap.add_argument("app", help="앱 주소, 예: https://144.24.91.250.sslip.io")
    ap.add_argument("--preview", help="미리보기 주소(공개 사이트), 기본은 앱 주소의 점을 하이픈으로")
    ap.add_argument("--site", default="", help="공개 가게 키(사이트 키)")
    a = ap.parse_args(argv)
    app = a.app.rstrip("/")
    preview = (a.preview or re.sub(r"https://(\d+)\.(\d+)\.(\d+)\.(\d+)\.", r"https://\1-\2-\3-\4.", app)).rstrip("/")
    rows = run(app, preview, a.site.strip())
    width = max(len(n) for n, _, _ in rows) + 2
    for name, mark, note in rows:
        print(f"{mark} {name.ljust(width)} {note}")
    bad = sum(1 for _, mark, _ in rows if mark == BAD)
    print(f"합계 {len(rows)}개, 실패 {bad}개")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
