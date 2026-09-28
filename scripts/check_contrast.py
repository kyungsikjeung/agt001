"""짙은 띠 포함 시안의 글자·배경 대비를 잰다 (F1 작업, F2에서 범위 확대).

사용법:
  .venv/bin/python scripts/check_contrast.py            # 정답 시안 + FIT_CASES 3안×시안/공개본
  .venv/bin/python scripts/check_contrast.py --palettes # 위 + 13팔레트 대표 페이지 검사

static/compare/fit/*.html(색 비교용 color-*·엔진 진단 engine-*·index 제외)을
390·1280 너비에서 열어 글자가 있는 보이는 요소마다 WCAG 대비를 잰다.
여기에 scripts/draft_corpus.FIT_CASES 전부를 design_variants.variants로 3안씩,
시안(public=False)·공개본(public=True) 둘 다 렌더해
임시 폴더(static/compare/fit/_check/, 끝나면 지운다)에서 같은 기준으로 검사한다.
이미지 주소는 render_fit_gold처럼 상대 경로로 바꾼다.
--palettes면 13개 팔레트를 대표 한 페이지(FIT 카페 v1 명세의 palette만 바꿔)에 입혀 검사한다.
실패가 있으면 exit 1.
"""
import copy
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIT = ROOT / "static" / "compare" / "fit"
CHECK = FIT / "_check"
PORT = 8767

# 애니메이션을 끄는 스타일 (측정 전에 넣는다)
KILL_ANIM = "*{animation:none!important;transition:none!important}"

# 글자 크기 기준 (큰 글자 판정)
LARGE_PX = 24.0
BOLD_LARGE_PX = 18.66

PROBE_JS = """() => {
  function oklchToRgb(L, C, Hdeg) {
    // oklch를 sRGB(0~255)로 바꾼다 (계산 결과는 빛 값이라 감마를 입힌다)
    const H = (Hdeg || 0) * Math.PI / 180;
    const a = C * Math.cos(H), b = C * Math.sin(H);
    let l = L + 0.3963377774 * a + 0.2158037573 * b;
    let m = L - 0.1055613458 * a - 0.0638541728 * b;
    let s = L - 0.0894841775 * a - 1.2914855480 * b;
    l = l * l * l; m = m * m * m; s = s * s * s;
    const r = 4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s;
    const g = -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s;
    const bl = -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s;
    const f = (x) => {
      x = Math.min(Math.max(x, 0), 1);
      return (x <= 0.0031308 ? 12.92 * x : 1.055 * Math.pow(x, 1 / 2.4) - 0.055) * 255;
    };
    return [f(r), f(g), f(bl)];
  }
  function num(t) {
    // 수 뒤에 %가 있으면 0~1로 (밝기·채도용)
    t = t.trim();
    if (t.endsWith("%")) return parseFloat(t) / 100;
    return parseFloat(t);
  }
  function parse(c) {
    let m = c.match(/rgba?\\(\\s*([\\d.]+)[,\\s]+([\\d.]+)[,\\s]+([\\d.]+)(?:[,\\/\\s]+([\\d.]+))?\\)/);
    if (m) return [parseFloat(m[1]), parseFloat(m[2]), parseFloat(m[3]),
            m[4] === undefined ? 1 : parseFloat(m[4])];
    // color-mix·상대색을 쓴 규칙은 계산된 값이 oklch·srgb로 나오므로 둘 다 받는다
    m = c.match(/oklch\\(\\s*([\\d.]+%?)\\s+([\\d.]+%?)\\s+([\\d.]+|none)(?:\\s*\\/\\s*([\\d.]+%?))?\\s*\\)/);
    if (m) {
      const rgb = oklchToRgb(num(m[1]), num(m[2]), m[3] === "none" ? 0 : parseFloat(m[3]));
      let a = 1;
      if (m[4] !== undefined) a = m[4].trim().endsWith("%") ? parseFloat(m[4]) / 100 : parseFloat(m[4]);
      return [rgb[0], rgb[1], rgb[2], a];
    }
    m = c.match(/color\\(srgb\\s+([\\d.]+)\\s+([\\d.]+)\\s+([\\d.]+)(?:\\s*\\/\\s*([\\d.]+%?))?\\s*\\)/);
    if (m) {
      let a = 1;
      if (m[4] !== undefined) a = m[4].trim().endsWith("%") ? parseFloat(m[4]) / 100 : parseFloat(m[4]);
      return [parseFloat(m[1]) * 255, parseFloat(m[2]) * 255, parseFloat(m[3]) * 255, a];
    }
    return null;
  }
  function visible(el) {
    let e = el;
    while (e && e.nodeType === 1) {
      const c = getComputedStyle(e);
      if (c.display === "none" || c.visibility === "hidden" || parseFloat(c.opacity) === 0) return false;
      e = e.parentElement;
    }
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  }
  function effBg(el) {
    // 자기부터 조상으로 올라가며 배경색을 흰색 위에 섞는다
    const chain = [];
    let e = el;
    while (e && e.nodeType === 1) { chain.unshift(e); e = e.parentElement; }
    let r = 255, g = 255, b = 255;
    for (const n of chain) {
      const c = parse(getComputedStyle(n).backgroundColor);
      if (c && c[3] > 0) {
        const a = c[3];
        r = c[0] * a + r * (1 - a);
        g = c[1] * a + g * (1 - a);
        b = c[2] * a + b * (1 - a);
      }
    }
    return [r, g, b];
  }
  function sel(el, pseudo) {
    const parts = [];
    let e = el;
    for (let i = 0; i < 3 && e && e.tagName; i++) {
      let s = e.tagName.toLowerCase();
      if (e.id) s += "#" + e.id;
      else if (e.className && typeof e.className === "string") {
        const cls = e.className.trim().split(/\\s+/).slice(0, 2).join(".");
        if (cls) s += "." + cls;
      }
      parts.unshift(s);
      e = e.parentElement;
    }
    return parts.join(" ") + (pseudo || "");
  }
  function weightNum(w) {
    if (w === "bold") return 700;
    if (w === "normal") return 400;
    const n = parseInt(w, 10);
    return isNaN(n) ? 400 : n;
  }
  const out = [];
  const skipTag = /^(SCRIPT|STYLE|NOSCRIPT|TEMPLATE|OPTION|TITLE|SVG|PATH)$/;
  const all = document.querySelectorAll("body *");
  for (const el of all) {
    if (skipTag.test(el.tagName)) continue;
    if (el.closest("svg")) continue;
    // 배경 그림 위 글자·자리 표시·숨김은 제외
    if (el.closest(".s-hero--photo-overlay, .s-hero--cinematic")) continue;
    if (el.closest(".is-placeholder, [aria-hidden='true']")) continue;
    if (!visible(el)) continue;
    const cs = getComputedStyle(el);
    // 직접 가진 글자만 잰다 (부모·자식 중복 방지)
    let text = "";
    for (const n of el.childNodes) {
      if (n.nodeType === 3 && n.textContent.trim()) { text += n.textContent.trim() + " "; }
    }
    text = text.trim();
    if (text) {
      const fg = parse(cs.color);
      out.push({sel: sel(el, ""), text: text.slice(0, 24),
                fg: fg ? fg.slice(0, 3) : [0, 0, 0], bg: effBg(el),
                size: parseFloat(cs.fontSize) || 16, weight: weightNum(cs.fontWeight)});
    }
    // 인용부호 같은 가상 요소 글자도 잰다
    for (const p of ["::before", "::after"]) {
      const pc = getComputedStyle(el, p);
      let content = pc.content || "none";
      if (content === "none" || content === "normal") continue;
      content = content.replace(/^["']|["']$/g, "").trim();
      if (!content || content === "none") continue;
      const fg = parse(pc.color);
      out.push({sel: sel(el, p), text: content.slice(0, 24),
                fg: fg ? fg.slice(0, 3) : [0, 0, 0], bg: effBg(el),
                size: parseFloat(pc.fontSize) || parseFloat(cs.fontSize) || 16,
                weight: weightNum(pc.fontWeight)});
    }
  }
  return out;
}"""


def _chan(v: float) -> float:
    v /= 255.0
    return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4


def contrast(fg, bg) -> float:
    """WCAG 대비 (두 색의 상대 밝기로 계산)."""
    lum = lambda c: 0.2126 * _chan(c[0]) + 0.7152 * _chan(c[1]) + 0.0722 * _chan(c[2])
    hi, lo = max(lum(fg), lum(bg)), min(lum(fg), lum(bg))
    return (hi + 0.05) / (lo + 0.05)


def needed(item) -> float:
    """기준: 큰 글자(24px 이상, 18.66px 이상 굵게) 3.0, 본문 4.5."""
    if item["size"] >= LARGE_PX:
        return 3.0
    if item["size"] >= BOLD_LARGE_PX and item["weight"] >= 700:
        return 3.0
    return 4.5


def _render_fresh() -> list[str]:
    """FIT_CASES 전부를 3안×시안/공개본으로 _check/에 렌더한다. 파일 이름 목록을 돌려준다."""
    sys.path.insert(0, str(ROOT))
    from scripts import draft_corpus as C  # noqa: E402
    from app.services import design_variants as DV  # noqa: E402
    from app.services import site_render as SR  # noqa: E402

    names = []
    for case in C.FIT_CASES:
        card = C.build_card(case)
        for v in DV.variants(card):
            for public in (False, True):
                doc = SR.render_site(
                    v["spec"], site_key=f"check-{case['id']}-{v['id']}",
                    title=DV.title_for(card), kind=DV.kind_for(card), public=public)
                # _check/는 fit/보다 한 단계 깊으니 ../을 하나 더 붙인다
                doc = doc.replace('"/art/', '"../../../../templates/art/')
                name = f"{case['id']}-{v['id']}{'-public' if public else ''}.html"
                (CHECK / name).write_text(doc, encoding="utf-8")
                names.append(name)
    return names


def _render_palettes() -> list[str]:
    """13개 팔레트를 대표 한 페이지(FIT 카페 v1 명세)에 입혀 _check/에 렌더한다."""
    sys.path.insert(0, str(ROOT))
    from scripts import draft_corpus as C  # noqa: E402
    from app.services import design_variants as DV  # noqa: E402
    from app.services import palette as PAL  # noqa: E402
    from app.services import site_render as SR  # noqa: E402

    case = next(c for c in C.FIT_CASES if c["id"] == "fit-cafe-dinein")
    card = C.build_card(case)
    base = DV.variants(card)[0]["spec"]  # v1 명세
    names = []
    for pal in PAL.library():
        spec = copy.deepcopy(base)
        spec["tokens"]["palette"] = pal
        for public in (False, True):
            doc = SR.render_site(
                spec, site_key=f"check-pal-{pal}",
                title=DV.title_for(card), kind=DV.kind_for(card), public=public)
            doc = doc.replace('"/art/', '"../../../../templates/art/')
            name = f"pal-{pal}{'-public' if public else ''}.html"
            (CHECK / name).write_text(doc, encoding="utf-8")
            names.append(name)
    return names


def main() -> int:
    from playwright.sync_api import sync_playwright

    with_palettes = "--palettes" in sys.argv[1:]
    # 정답 시안만 잰다. engine-*은 F2 진단용 스냅샷(구 CSS 내장)이라
    # FIT_CASES fresh 렌더(_check/)로 같은 내용을 새로 재서 대신한다.
    files = [(p.name, f"static/compare/fit/{p.name}") for p in sorted(FIT.glob("*.html"))
             if not p.name.startswith("color-") and not p.name.startswith("engine-")
             and p.name != "index.html"]
    shutil.rmtree(CHECK, ignore_errors=True)
    CHECK.mkdir(parents=True, exist_ok=True)
    try:
        fresh = _render_fresh()
        files += [(n, f"static/compare/fit/_check/{n}") for n in fresh]
        if with_palettes:
            files += [(n, f"static/compare/fit/_check/{n}") for n in _render_palettes()]
    except Exception as exc:
        print(f"렌더 실패: {exc}")
        shutil.rmtree(CHECK, ignore_errors=True)
        return 1
    # 측정용 서버를 켜고 끝나면 끈다 (8766은 쓰지 않는다)
    srv = subprocess.Popen([sys.executable, "-m", "http.server", str(PORT),
                            "--bind", "127.0.0.1"],
                           cwd=str(ROOT),
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(100):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{PORT}/", timeout=1).read(1)
                break
            except Exception:
                time.sleep(0.1)
        fails = []
        with sync_playwright() as p:
            browser = p.chromium.launch()
            for name, url in files:
                for width in (390, 1280):
                    page = browser.new_page(viewport={"width": width, "height": 900})
                    page.goto(f"http://127.0.0.1:{PORT}/{url}")
                    page.add_style_tag(content=KILL_ANIM)
                    for item in page.evaluate(PROBE_JS):
                        ratio = contrast(item["fg"], item["bg"])
                        if ratio < needed(item):
                            text = re.sub(r"\s+", " ", item["text"])
                            fails.append(f"{name}:{width}:{item['sel']}:{text}:{ratio:.2f}")
                    page.close()
            browser.close()
        for line in fails:
            print(line)
        print(f"실패: {len(fails)}건")
        return 1 if fails else 0
    finally:
        srv.terminate()
        srv.wait()
        shutil.rmtree(CHECK, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
