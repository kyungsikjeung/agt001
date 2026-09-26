"""공개 사이트 품질 평가: 6업종 × 정보 2단계(다 줌·거의 안 줌) × 3안 = 36쪽.

AI를 부르지 않는다. 평가 시나리오(evals/scenarios/*-terse.json)의 가게 사실로 카드를 직접 만들고,
운영과 같은 코드(design.publish_choice)로 공개본을 만든 뒤 휴대폰 크기(390×844) 브라우저에서 잰다.
사진·AI 문구 초안은 넣지 않는다(사진 칸은 업종 예시 그림으로 나온다).

사용법: .venv/bin/python -m evals.run_site_quality [--out DIR] [--report PATH]
"""
import argparse
import copy
import datetime
import json
import tempfile
from pathlib import Path

from app.config import settings
from app.services import design
from app.services import design_variants as DV
from app.services import prd_engine as E
from app.services import prd_schema as S

ROOT = Path(__file__).resolve().parent
INDUSTRIES = ("cafe", "restaurant", "pension", "salon", "academy", "workshop")
VIEW_W, VIEW_H = 390, 844

# 쪽마다 브라우저 안에서 잰다. 결과는 JSON 한 덩어리.
_PROBE = r"""
(facts) => {
  const vis = (el) => { const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none' && +s.opacity !== 0; };
  const rgb = (c) => { const m = c.match(/rgba?\(([^)]+)\)/); if (!m) return null;
    const p = m[1].split(/[ ,\/]+/).filter(Boolean).map(Number); return {r:p[0], g:p[1], b:p[2], a: p.length > 3 ? p[3] : 1}; };
  const lum = (c) => { const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
    return 0.2126 * f(c.r) + 0.7152 * f(c.g) + 0.0722 * f(c.b); };
  const blend = (fg, bg) => ({r: fg.r * fg.a + bg.r * (1 - fg.a), g: fg.g * fg.a + bg.g * (1 - fg.a), b: fg.b * fg.a + bg.b * (1 - fg.a), a: 1});
  // 글자 뒤 배경: 불투명한 배경색이 나올 때까지 위로. 배경 그림·그라데이션을 만나면 판정 보류.
  const bgOf = (el) => { let layers = [];
    for (let e = el; e; e = e.parentElement) { const s = getComputedStyle(e);
      if (s.backgroundImage && s.backgroundImage !== 'none') return null;
      const c = rgb(s.backgroundColor); if (c && c.a > 0) { layers.push(c); if (c.a >= 1) break; } }
    let base = {r:255, g:255, b:255, a:1}; for (const c of layers.reverse()) base = blend(c, base); return base; };
  const out = {overflow: document.documentElement.scrollWidth > window.innerWidth + 1,
    scrollWidth: document.documentElement.scrollWidth, height: document.documentElement.scrollHeight,
    smallText: [], lowContrast: [], contrastUnknown: 0, textChecked: 0, smallTargets: [], brokenImages: 0,
    missingAlt: 0, h1: document.querySelectorAll('h1').length, sections: document.querySelectorAll('section').length};
  const seen = new Set();
  for (const el of document.body.querySelectorAll('*')) {
    const own = [...el.childNodes].filter(n => n.nodeType === 3).map(n => n.textContent.trim()).join(' ').trim();
    if (!own || !vis(el) || el.closest('svg')) continue;
    const s = getComputedStyle(el); const size = parseFloat(s.fontSize); out.textChecked++;
    if (size < 14 && !seen.has('s' + own)) { seen.add('s' + own); out.smallText.push(`${size}px "${own.slice(0, 30)}"`); }
    const fg = rgb(s.color); const bg = bgOf(el);
    if (!fg || !bg) { out.contrastUnknown++; continue; }
    const f = blend(fg, bg); const L1 = lum(f), L2 = lum(bg);
    const ratio = (Math.max(L1, L2) + 0.05) / (Math.min(L1, L2) + 0.05);
    const large = size >= 24 || (size >= 18.66 && +s.fontWeight >= 700);
    if (ratio < (large ? 3 : 4.5) && !seen.has('c' + own)) { seen.add('c' + own);
      out.lowContrast.push(`${ratio.toFixed(2)} "${own.slice(0, 30)}"`); }
  }
  for (const el of document.querySelectorAll('a[href], button, input:not([type=hidden]), textarea, select')) {
    if (!vis(el)) continue; const r = el.getBoundingClientRect();
    if (r.right <= 0 || r.bottom <= 0 || r.left >= document.documentElement.scrollWidth) continue;  // 화면 밖(스팸 숨김 칸)
    // 문장 안 링크는 제외(WCAG 2.5.8 예외). 한 줄짜리 독립 링크·버튼·입력칸만 본다.
    const inline = el.tagName === 'A' && getComputedStyle(el).display === 'inline' && el.parentElement &&
      el.parentElement.textContent.trim().length > el.textContent.trim().length + 5;
    if (!inline && (r.height < 44 || r.width < 44))
      out.smallTargets.push(`${Math.round(r.width)}×${Math.round(r.height)} ${el.tagName.toLowerCase()} "${(el.textContent || el.getAttribute('aria-label') || el.name || '').trim().slice(0, 20)}"`);
  }
  for (const img of document.images) { if (img.complete && img.naturalWidth === 0) out.brokenImages++; if (!img.hasAttribute('alt')) out.missingAlt++; }
  const text = document.body.innerText;
  // 눈에 보이는 글자만(글자 크기 0으로 감춘 빈칸은 제외): 화면에 실제로 보이는 빈칸·'예시' 표시
  const shown = []; const walk = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  for (let n; (n = walk.nextNode());) { const e = n.parentElement;
    if (e && vis(e) && parseFloat(getComputedStyle(e).fontSize) > 0) shown.push(n.textContent); }
  const shownText = shown.join(' ');
  out.placeholders = [...new Set(shownText.match(/\[[^\]\n]{0,20}입력\]/g) || [])];
  // D36: "예시 이미지" 배지는 방문자에게 보이는 게 맞다. 사장님용 안내 문구만 문제로 센다.
  out.exampleLabel = /사진으로 바뀌어요/.test(shownText);
  const firstScreen = [...document.querySelectorAll('h1, h2, a, button, p')].filter(e => vis(e) && e.getBoundingClientRect().top < window.innerHeight);
  const firstText = firstScreen.map(e => e.innerText).join(' ');
  out.nameAboveFold = !!facts.name && firstText.includes(facts.name);
  out.ctaAboveFold = firstScreen.some(e => (e.tagName === 'A' || e.tagName === 'BUTTON') && /문의|전화|예약|신청/.test(e.innerText));
  out.facts = {};
  for (const [k, v] of Object.entries(facts)) {
    if (!v) continue;
    out.facts[k] = k === 'phone' ? !!document.querySelector(`a[href="tel:${v}"]`) || text.includes(v)
      : Array.isArray(v) ? v.every(x => text.includes(x)) : text.includes(v);
  }
  return out;
}
"""


def _scenario(ind: str) -> dict:
    return json.loads((ROOT / "scenarios" / f"{ind}-terse.json").read_text(encoding="utf-8"))


def make_card(ind: str, level: str) -> tuple[dict, dict]:
    """(카드, 화면에 있어야 할 사실). level: full(다 줌) | min(업종·가게 이름만)."""
    sc = _scenario(ind)
    f = sc["facts"]
    card = E.new_card()
    card["industry"] = ind
    E._put(card, "business_type", f["business_type"], S.FILLED, 1)
    E._put(card, "shop_name", f["shop_name"], S.FILLED, 1)
    expect = {"name": f["shop_name"]}
    if level == "full":
        phone = f.get("phone") or "010-0000-" + str(1000 + INDUSTRIES.index(ind))
        offerings = [o.strip() for o in f["offerings"].split(",")]
        E._put(card, "phone", phone, S.FILLED, 1)
        E._put(card, "hours", f["hours"], S.FILLED, 1)
        E._put(card, "location", f["location"], S.FILLED, 1)
        E._put(card, "offerings", offerings, S.FILLED, 1)
        if f.get("detail"):
            E._put(card, "detail", f["detail"], S.FILLED, 1)
        hidden_keys = [k for k, _ in S.INDUSTRIES[ind].hidden]
        card["hidden"] = {"asked": True, "selected": [k for k, v in sc["hidden_facts"].items() if v and k in hidden_keys]}
        expect.update(phone=phone, hours=f["hours"], location=f["location"], offerings=offerings)
    return card, expect


def build_pages(out_dir: Path) -> list[dict]:
    """공개본 HTML 36쪽을 운영 코드로 만든다."""
    pages = []
    gen = Path(tempfile.mkdtemp(prefix="siteq-"))
    old = settings.generated_dir
    settings.generated_dir = gen
    try:
        for ind in INDUSTRIES:
            for level in ("full", "min"):
                card, expect = make_card(ind, level)
                for v in DV.variants(card):
                    rid = f"{ind}-{level}"
                    design.publish_choice(rid, copy.deepcopy(card), v["id"])
                    html = (gen / rid / "published" / "index.html").read_text(encoding="utf-8")
                    path = out_dir / f"{rid}-{v['id']}.html"
                    path.write_text(html, encoding="utf-8")
                    pages.append({"industry": ind, "level": level, "variant": v["id"], "name": v["name"],
                                  "html": path, "expect": expect})
    finally:
        settings.generated_dir = old
    return pages


def measure(pages: list[dict], out_dir: Path) -> None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            # 나타내기 애니메이션이 끝난 모습으로 찍는다(전체 캡처는 스크롤하지 않아 아래 부품이 투명하게 찍힌다)
            page = browser.new_page(viewport={"width": VIEW_W, "height": VIEW_H}, device_scale_factor=1,
                                    reduced_motion="reduce")
            for pg in pages:
                page.goto(pg["html"].as_uri())
                page.wait_for_load_state("load")
                pg["m"] = page.evaluate(_PROBE, pg["expect"])
                shot = out_dir / (pg["html"].stem + ".png")
                page.screenshot(path=str(shot), full_page=True)
                page.screenshot(path=str(out_dir / (pg["html"].stem + "-fold.png")))
                pg["shot"] = shot
        finally:
            browser.close()


def distinctness(pages: list[dict], out_dir: Path) -> dict:
    """같은 조건의 3안 첫 화면이 얼마나 다른지 (0 = 똑같음, 100 = 완전히 다름). 픽셀 평균 차이."""
    from PIL import Image, ImageChops, ImageStat

    res = {}
    for ind in INDUSTRIES:
        for level in ("full", "min"):
            ims = [Image.open(out_dir / f"{ind}-{level}-{v}-fold.png").convert("L").resize((130, 281))
                   for v in ("v1", "v2", "v3")]
            diffs = [ImageStat.Stat(ImageChops.difference(ims[a], ims[b])).mean[0] / 2.55
                     for a, b in ((0, 1), (0, 2), (1, 2))]
            res[f"{ind}-{level}"] = round(min(diffs), 1)
    return res


def contact_sheets(pages: list[dict], out_dir: Path) -> None:
    """업종·조건마다 3안 전체 화면을 나란히 붙인 그림 (사람 눈 검토용)."""
    from PIL import Image

    for ind in INDUSTRIES:
        for level in ("full", "min"):
            ims = [Image.open(out_dir / f"{ind}-{level}-{v}.png") for v in ("v1", "v2", "v3")]
            h = max(i.height for i in ims)
            sheet = Image.new("RGB", (VIEW_W * 3 + 40, h), "white")
            for n, im in enumerate(ims):
                sheet.paste(im, (n * (VIEW_W + 20), 0))
            scale = min(1.0, 2400 / h)
            sheet = sheet.resize((int(sheet.width * scale), int(h * scale)))
            sheet.save(out_dir / f"sheet-{ind}-{level}.png")


def report(pages: list[dict], dist: dict) -> str:
    rows, issues = [], {"overflow": 0, "small": 0, "contrast": 0, "targets": 0, "broken": 0, "ph": 0, "facts": 0,
                        "fold_name": 0, "fold_cta": 0, "h1": 0}
    for pg in pages:
        m = pg["m"]
        missing = [k for k, ok in m["facts"].items() if not ok]
        flags = {"overflow": m["overflow"], "small": bool(m["smallText"]), "contrast": bool(m["lowContrast"]),
                 "targets": bool(m["smallTargets"]), "broken": m["brokenImages"] > 0,
                 "ph": bool(m["placeholders"]) or m["exampleLabel"], "facts": bool(missing),
                 "fold_name": not m["nameAboveFold"], "fold_cta": not m["ctaAboveFold"], "h1": m["h1"] != 1}
        for k, v in flags.items():
            issues[k] += bool(v)
        rows.append(f"| {pg['industry']}-{pg['level']}-{pg['variant']} | {'X' if m['overflow'] else '-'} | "
                    f"{len(m['smallText'])} | {len(m['lowContrast'])} | {len(m['smallTargets'])} | {m['brokenImages']} | "
                    f"{', '.join(m['placeholders']) or ('예시' if m['exampleLabel'] else '-')} | {', '.join(missing) or '-'} | "
                    f"{'O' if m['nameAboveFold'] else 'X'} | {'O' if m['ctaAboveFold'] else 'X'} | {m['h1']} | {m['height']} |")
    n = len(pages)
    detail = []
    for pg in pages:
        m = pg["m"]
        items = [("작은 글자", m["smallText"]), ("대비 부족", m["lowContrast"]), ("작은 누름 칸", m["smallTargets"])]
        lines = [f"  - {k}: " + "; ".join(v[:6]) + (" …" if len(v) > 6 else "") for k, v in items if v]
        if lines:
            detail.append(f"- **{pg['industry']}-{pg['level']}-{pg['variant']}**\n" + "\n".join(lines))
    today = datetime.date.today().isoformat()
    head = (f"# 공개 사이트 품질 자동 점검 ({today})\n\n"
            f"대상 {n}쪽(6업종 × 정보 다 줌/거의 안 줌 × 3안), 휴대폰 {VIEW_W}×{VIEW_H}, 공개본(`publish_choice`). "
            "사진·AI 문구 초안 없음. 실행: `.venv/bin/python -m evals.run_site_quality`\n\n"
            "## 문제가 있는 쪽 수\n\n| 항목 | 기준 | 쪽 수 |\n|---|---|---|\n"
            f"| 가로 넘침 | 화면보다 넓으면 X | {issues['overflow']}/{n} |\n"
            f"| 작은 글자 | 14px 미만 글자가 있음 | {issues['small']}/{n} |\n"
            f"| 글자 대비 | WCAG AA(4.5:1, 큰 글자 3:1) 미달 | {issues['contrast']}/{n} |\n"
            f"| 누름 칸 크기 | 44×44px 미만 버튼·링크·입력칸 | {issues['targets']}/{n} |\n"
            f"| 깨진 그림 | 불러오지 못한 이미지 | {issues['broken']}/{n} |\n"
            f"| 빈칸 노출 | 공개본에 `[… 입력]`·'예시' | {issues['ph']}/{n} |\n"
            f"| 사실 누락 | 카드의 이름·전화·시간·주소·상품이 화면에 없음 | {issues['facts']}/{n} |\n"
            f"| 첫 화면 이름 | 첫 화면에 가게 이름 없음 | {issues['fold_name']}/{n} |\n"
            f"| 첫 화면 행동 | 첫 화면에 문의·전화·예약 버튼 없음 | {issues['fold_cta']}/{n} |\n"
            f"| 제목 구조 | h1이 정확히 1개가 아님 | {issues['h1']}/{n} |\n\n"
            "## 3안 첫 화면 차이 (가장 비슷한 두 안의 픽셀 차이, 0=같음)\n\n| 업종-조건 | 최소 차이 |\n|---|---|\n"
            + "\n".join(f"| {k} | {v} |" for k, v in dist.items()) +
            "\n\n## 쪽별\n\n| 쪽 | 넘침 | 작은 글자 | 대비 | 작은 칸 | 깨진 그림 | 빈칸 | 없는 사실 | 첫화면 이름 | 첫화면 버튼 | h1 | 높이 |\n"
            "|---|---|---|---|---|---|---|---|---|---|---|---|\n")
    return head + "\n".join(rows) + "\n\n## 세부\n\n" + "\n".join(detail) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None, help="HTML·스크린샷 저장 폴더 (기본: 임시 폴더)")
    ap.add_argument("--report", default=None, help="성적표 저장 경로 (기본: 화면에만)")
    a = ap.parse_args()
    out_dir = Path(a.out or tempfile.mkdtemp(prefix="siteq-out-"))
    out_dir.mkdir(parents=True, exist_ok=True)
    pages = build_pages(out_dir)
    measure(pages, out_dir)
    dist = distinctness(pages, out_dir)
    contact_sheets(pages, out_dir)
    text = report(pages, dist)
    (out_dir / "measure.json").write_text(json.dumps([{**{k: v for k, v in p.items() if k not in ('html', 'shot')}}
                                                       for p in pages], ensure_ascii=False, indent=1), encoding="utf-8")
    if a.report:
        Path(a.report).write_text(text, encoding="utf-8")
    print(text)
    print(f"그림·HTML: {out_dir}")


if __name__ == "__main__":
    main()
