"""시안 실물 렌더 + 캡처 (로컬 확인용).

사용법:
  .venv/bin/python scripts/draft_academy_preview.py --case academy-talkative
  .venv/bin/python scripts/draft_academy_preview.py --all --dir /tmp/draft_lab
출력: <dir>/<case>/index.html (3안 갤러리) + v1/v2/v3.html + shots/*.png (390·1280)
  --all이면 12종 전체 + <dir>/index.html 목록 (캡처는 학원만, 나머지는 HTML).
"""
import argparse
import functools
import http.server
import shutil
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services import design_variants as DV  # noqa: E402
from app.services import site_render as SR  # noqa: E402
from scripts import draft_corpus as C  # noqa: E402


def _copy_art(out: Path) -> None:
    # /art/ 기본 그림이 미리보기에서도 풀리게 복사.
    # (운영에선 앱이 /art/를 서빙하므로 엔진 변경 없음.)
    from app.config import settings as _settings
    (out / "art").mkdir(parents=True, exist_ok=True)
    for f in (_settings.templates_dir / "art").glob("*.webp"):
        shutil.copy(f, out / "art" / f.name)


def render_case(out: Path, case: dict, shots: bool) -> None:
    (out / "shots").mkdir(parents=True, exist_ok=True)
    _copy_art(out)
    card = C.build_card(case)
    items = DV.variants(card)
    cards_html = []
    for v in items:
        html = SR.render_site(v["spec"], site_key="lab-" + case["id"],
                              title=DV.title_for(card), kind=DV.kind_for(card))
        (out / f'{v["id"]}.html').write_text(html, encoding="utf-8")
        toks = v["spec"]["tokens"]
        hero = next(s for s in v["spec"]["sections"] if s["type"] == "hero")
        order = [s["type"] for s in v["spec"]["sections"]][:4]
        shot_links = ""
        if shots:
            shot_links = (
                f' · <a href="shots/{v["id"]}-390.png">폰(390)</a> · '
                f'<a href="shots/{v["id"]}-1280.png">데스크탑(1280)</a> · '
                f'<img src="shots/{v["id"]}-390.png" width="195" alt="{v["id"]} 미리보기">')
        cards_html.append(
            f'<section><h2>{v["id"]} · {v["name"]}</h2>'
            f'<p>{v["summary"]}</p>'
            f'<p>색 {toks["palette"]} · 글꼴 {toks["font_pair"]} · '
            f'여백 {toks["density"]} · 모서리 {toks["radius"]} · 사진처리 {toks["image_style"]}</p>'
            f'<p>첫화면 {hero["variant"]} · 순서 {" → ".join(order)}</p>'
            f'<p>제목 {hero["content"].get("title")} · 부제 {hero["content"].get("subtitle")} · '
            f'버튼 {(hero["content"].get("cta") or {}).get("label")} · '
            f'사진 {hero["content"].get("image")}</p>'
            f'<p><a href="{v["id"]}.html">실물 열기</a>{shot_links}</p>'
            f"</section>")
    (out / "index.html").write_text(
        "<!doctype html><html lang=ko><head><meta charset=utf-8>"
        "<meta name=viewport content='width=device-width,initial-scale=1'>"
        f"<title>{case['id']} 시안 3안</title></head><body><h1>{case['id']} 시안 3안</h1>"
        + "".join(cards_html) + "</body></html>", encoding="utf-8")
    if shots:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(out))
            httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
            threading.Thread(target=httpd.serve_forever, daemon=True).start()
            base = f"http://127.0.0.1:{httpd.server_port}"
            browser = p.chromium.launch()
            try:
                for v in items:
                    for width in (390, 1280):
                        pg = browser.new_page(viewport={"width": width, "height": 900})
                        pg.goto(f"{base}/{v['id']}.html")
                        pg.screenshot(path=str(out / "shots" / f'{v["id"]}-{width}.png'))
                        pg.close()
            finally:
                browser.close()
                httpd.shutdown()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="/tmp/draft_lab")
    ap.add_argument("--case", default="academy-talkative")
    ap.add_argument("--all", action="store_true")
    args = ap.parse_args()
    root = Path(args.dir)
    if args.all:
        cases = C.CASES
    else:
        cases = [C.get(args.case)]
    links = []
    for case in cases:
        out = root / case["id"]
        render_case(out, case, shots=args.all)
        links.append(f'<li><a href="{case["id"]}/index.html">{case["id"]}</a></li>')
        print(str(out / "index.html"))
    if args.all:
        (root / "index.html").write_text(
            "<!doctype html><html lang=ko><head><meta charset=utf-8>"
            "<title>시안 12종</title></head><body><h1>시안 12종</h1><ul>"
            + "".join(links) + "</ul></body></html>", encoding="utf-8")
        print(str(root / "index.html"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
