"""컴포넌트 갤러리 (COMPONENT_ENGINE_PLAN §8): 모양 묶음·스타일 축을 한 페이지에서 눈으로 비교한다.

    .venv/bin/python scripts/component_gallery.py [--out generated/component-gallery] [--shots]

- 모양 묶음(components.json groups)마다 같은 내용으로 모든 모양을 그린다 → 바꿔 끼워도 깨지지 않는지 본다.
- 스타일 축(surface·heading)은 같은 사이트를 값마다 그린다.
- index.html 하나에 휴대폰 폭(390px) 칸으로 모은다. 파일로 열 수 있게 /art/ 그림은 파일 주소로 바꾼다.
- --shots: 칸마다 휴대폰 폭 스크린숏(PNG)도 남긴다(Playwright, 설치된 Chromium).
DB·네트워크를 쓰지 않는다. 결과는 generated/ 아래(깃에 넣지 않음).
"""
import argparse
import copy
import html
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("NIM_API_KEY", "gallery")
os.environ.setdefault("PRECOMPUTE_EMBEDDINGS", "false")

from app.services import components as COMP  # noqa: E402
from app.services import site_render as SR  # noqa: E402

ART = ROOT / "templates" / "art"
EX = "/art/ex/"

SAMPLE = {
    "hero": {"title": "연남 느린오후", "subtitle": "천천히 내리는 동네 커피", "image": EX + "cafe-hero.webp",
             "cta": {"label": "전화하기", "href": "tel:021234567"}, "facts": [{"label": "영업", "value": "매일 10~21시"}],
             "eyebrow": "SINCE 2016", "label_en": "SLOW AFTERNOON", "kicker": "연남동 골목 카페"},
    "greeting": {"label": "", "body": "골목 끝 작은 가게에서 10년째 원두를 볶고 있어요. 천천히 머물다 가세요."},
    "catalog": {"label": "", "items": [
        {"name": "아메리카노", "desc": "산미 적은 다크 로스트", "price": "4,500원", "image": EX + "cafe-space1.webp"},
        {"name": "바닐라 라떼", "desc": "직접 만든 바닐라 시럽", "price": "5,500원", "image": EX + "cafe-dessert.webp"},
        {"name": "말차 라떼", "desc": "", "price": "6,000원"},
        {"name": "바스크 치즈케이크", "desc": "매일 아침 굽는", "price": "7,000원"}],
        "categories": [{"name": "커피", "items": [{"name": "아메리카노", "price": "4,500원", "desc": "다크 로스트"},
                                                {"name": "바닐라 라떼", "price": "5,500원"}]},
                       {"name": "디저트", "items": [{"name": "바스크 치즈케이크", "price": "7,000원"}]}]},
    "photos": {"label": "", "items": [{"src": EX + n, "alt": "가게 사진", "caption": c} for n, c in (
        ("cafe-space1.webp", "창가 자리"), ("cafe-hero.webp", ""), ("cafe-dessert.webp", "오늘의 디저트"),
        ("salon-space1.webp", ""), ("pension-space3.webp", "테라스"), ("workshop-space3.webp", ""))]},
    "location": {"label": "", "address": "서울 마포구 연남로 12", "items": [
        {"name": "지하철", "note": "홍대입구역 3번 출구 도보 7분"}, {"name": "주차", "note": "건물 뒤 2대"}]},
}

BASE_TOKENS = {"palette": "coffee", "font_pair": "sans-clean", "density": "comfortable", "radius": "soft",
               "image_style": "card"}


def _fix_art(doc: str) -> str:
    """파일로 열어도 그림이 보이게 /art/ 주소를 파일 주소로."""
    return doc.replace('"/art/', f'"{ART.as_uri()}/')


def _render(sections: list, tokens: dict | None = None) -> str:
    spec = {"tokens": {**BASE_TOKENS, **(tokens or {})}, "sections": copy.deepcopy(sections)}
    return _fix_art(SR.render_site(spec, title="갤러리", kind="cafe"))


def _site_sections() -> list:
    """스타일 축 비교용 한 장: 첫 화면 + 소개 + 메뉴 카드 + 사진첩 + 오시는 길."""
    return [
        {"id": "hero", "type": "hero", "variant": "text-only", "content": SAMPLE["hero"]},
        {"id": "greeting", "type": "intro", "variant": "short", "content": SAMPLE["greeting"]},
        {"id": "menu", "type": "offerings", "variant": "photo-grid", "content": SAMPLE["catalog"]},
        {"id": "reviews", "type": "reviews", "variant": "list", "content": {"items": [
            {"quote": "라떼가 정말 부드러워요", "author": "단골 손님", "source": "네이버"}]}},
        {"id": "space", "type": "gallery", "variant": "grid", "content": SAMPLE["photos"]},
        {"id": "where", "type": "around", "variant": "transit", "content": SAMPLE["location"]},
    ]


def build(out: Path) -> list[dict]:
    out.mkdir(parents=True, exist_ok=True)
    pages = []
    hero = {"id": "hero", "type": "hero", "variant": "text-only", "content": {"title": "연남 느린오후"}}
    for name, group in COMP.registry()["groups"].items():
        stype = group["type"]
        for variant in group["variants"]:
            sec = {"id": name, "type": stype, "variant": variant, "content": SAMPLE.get(name, {})}
            sections = [sec] if stype == "hero" else [hero, sec]
            key = f"{stype}--{variant}"
            doc = _render(sections)
            path = out / f"shape-{name}-{variant}.html"
            path.write_text(doc, encoding="utf-8")
            pages.append({"file": path.name, "group": name, "title": COMP.info(key).get("name") or variant,
                          "note": key + (" · 새" if COMP.info(key).get("new") else "")})
    for axis, spec in COMP.style_axes().items():
        for value, label in spec["values"].items():
            doc = _render(_site_sections(), {axis: value})
            path = out / f"style-{axis}-{value}.html"
            path.write_text(doc, encoding="utf-8")
            pages.append({"file": path.name, "group": f"style:{axis}", "title": label,
                          "note": f"{axis}={value}" + (" (기본)" if value == spec["default"] else "")})
    rows = []
    for group in dict.fromkeys(p["group"] for p in pages):
        cells = "".join(
            f'<figure><figcaption><b>{html.escape(p["title"])}</b> <small>{html.escape(p["note"])}</small></figcaption>'
            f'<iframe src="{html.escape(p["file"])}" loading="lazy" title="{html.escape(p["title"])}"></iframe></figure>'
            for p in pages if p["group"] == group)
        rows.append(f"<section><h2>{html.escape(group)}</h2><div class=row>{cells}</div></section>")
    problems = COMP.problems()
    index = (
        '<!doctype html><html lang="ko"><head><meta charset="utf-8"><title>컴포넌트 갤러리</title>'
        "<style>body{margin:0;padding:16px;font:14px/1.5 system-ui,sans-serif;background:#f4f4f5;color:#18181b}"
        ".row{display:flex;gap:16px;overflow-x:auto;padding-bottom:8px}figure{margin:0;flex:none}"
        "iframe{width:390px;height:760px;border:1px solid #d4d4d8;border-radius:12px;background:#fff}"
        "figcaption{margin-bottom:6px}small{color:#52525b}h2{margin:24px 0 8px}</style></head><body>"
        f"<h1>컴포넌트 갤러리</h1><p>등록표 점검: {'문제 없음' if not problems else html.escape('; '.join(problems))}</p>"
        + "".join(rows) + "</body></html>")
    (out / "index.html").write_text(index, encoding="utf-8")
    (out / "pages.json").write_text(json.dumps(pages, ensure_ascii=False, indent=1), encoding="utf-8")
    return pages


def shots(out: Path, pages: list[dict]) -> None:
    from playwright.sync_api import sync_playwright
    exe = os.environ.get("CHROMIUM_PATH") or "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=exe if Path(exe).exists() else None)
        page = browser.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=1)
        # 스크롤 나타내기(view 타임라인)는 통째 캡처에서 화면 밖 구역을 흐리게 찍는다 → 움직임 줄이기로 찍는다
        page.emulate_media(reduced_motion="reduce")
        for p in pages:
            page.goto((out / p["file"]).as_uri())
            page.wait_for_timeout(250)
            page.screenshot(path=str(out / (p["file"][:-5] + ".png")), full_page=True)
        browser.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "generated" / "component-gallery"))
    ap.add_argument("--shots", action="store_true")
    args = ap.parse_args()
    target = Path(args.out)
    built = build(target)
    print(f"{len(built)} pages → {target / 'index.html'}")
    if args.shots:
        shots(target, built)
        print("screenshots done")
