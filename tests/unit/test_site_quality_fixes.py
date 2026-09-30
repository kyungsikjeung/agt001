"""QA-1 공개 사이트 품질 회귀 테스트 (EDIT_WAVE2 QA-1).

외부 호출·DB 없음. 카드→시안→공개본 렌더와 CSS 묶음·프로브 원문을 직접 본다.
"""
import re
import shutil
import subprocess
from pathlib import Path

from evals.run_site_quality import _PROBE, make_card
from evals.run_site_quality import collect_actions, check_actions, card_action_facts
from app.services import design_variants as DV
from app.services import site_render

ROOT = Path(__file__).resolve().parents[2]
INDUSTRIES = ("cafe", "restaurant", "pension", "salon", "academy", "workshop")


def _public_html(industry: str, level: str) -> list:
    """min/full 카드의 3안 공개본 HTML."""
    card, _ = make_card(industry, level)
    out = []
    for v in DV.variants(card):
        html = site_render.render_site(v["spec"], site_key="qa1test",
                                       title="테스트", kind="qa1test", public=True)
        out.append((v["id"], html))
    return out


def test_min쪽_빠진구역_링크없음():
    """min 쪽(주소 없음)에서 빠진 구역(#around 등)으로 가는 버튼이 하나도 없다."""
    for ind in INDUSTRIES:
        card, _ = make_card(ind, "min")
        facts = card_action_facts(card)
        for vid, html in _public_html(ind, "min"):
            got = collect_actions(html)
            problems = check_actions(got["links"], got["buttons"], got["forms"],
                                     got["ids"], facts)
            bad = [p for p in problems
                   if p.get("kind") in ("dead", "missing_anchor", "bad_form")]
            assert bad == [], f"{ind}-min-{vid}: {bad}"


def test_min쪽_주버튼_차선책():
    """길찾기가 빠지면 문의하기로 바뀐다 (버튼을 그냥 지우지 않는다)."""
    card, _ = make_card("cafe", "min")
    html = _public_html("cafe", "min")[0][1]
    assert 'href="#contact-title-inquiry"' in html
    assert "문의하기" in html
    assert "around-title-around" not in html


# ── CSS 묶음 (site.css + templates/css/*.css, 렌더 묶음과 같은 순서) ──

def _bundle_css() -> str:
    parts = [(ROOT / "templates" / "site.css").read_text(encoding="utf-8")]
    css_dir = ROOT / "templates" / "css"
    if css_dir.is_dir():
        for path in sorted(css_dir.glob("*.css")):
            parts.append(path.read_text(encoding="utf-8"))
    return "\n".join(parts)


def _rules(css_text: str) -> list:
    """단순 규칙 목록 [(선택자, {속성: 값})]. 미디어 안쪽 규칙도 순서대로 담는다."""
    css_text = re.sub(r"/\*.*?\*/", "", css_text, flags=re.S)
    out = []
    for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", css_text):
        sels = [s.strip() for s in m.group(1).split(",") if s.strip()]
        decls: dict = {}
        for d in m.group(2).split(";"):
            if ":" in d:
                k, v = d.split(":", 1)
                decls[k.strip()] = v.strip()
        out.append((sels, decls))
    return out


def _specificity(selector: str) -> tuple:
    ids = len(re.findall(r"#[A-Za-z0-9_-]+", selector))
    classes = len(re.findall(r"\.[A-Za-z0-9_-]+", selector))
    tags = len([t for t in re.split(r"[\s>+~.#:\[]+", selector) if t and t != "*"])
    return (ids, classes, tags)


def _matches(selector: str, tag: str, classes: set) -> bool:
    """단순 선택자 매칭 (가상 클래스·미디어 조건은 본다)."""
    if ":" in selector or "@media" in selector:
        return False
    parts = [p for p in re.split(r"[\s>+~]+", selector.strip()) if p]
    if not parts:
        return False
    for i, part in enumerate(parts):
        need_tag = re.split(r"[.#\[]", part)[0]
        need_classes = set(re.findall(r"\.([A-Za-z0-9_-]+)", part))
        if i == len(parts) - 1:
            if need_tag and need_tag != tag:
                return False
            if not need_classes <= classes:
                return False
        else:
            if not need_classes <= (classes | {"s-classes", "s-rooms", "s-menu", "section"}):
                if need_tag not in ("section", ""):
                    return False
    return True


def _effective(prop: str, tag: str, classes: set) -> str:
    """묶음에서 이 요소에 이기는 마지막 선언값."""
    best = (None, (-1, -1, -1), -1)
    for order, (sels, decls) in enumerate(_rules(_bundle_css())):
        if prop not in decls:
            continue
        for sel in sels:
            if _matches(sel, tag, classes):
                spec = _specificity(sel)
                if (spec, order) >= (best[1], best[2]):
                    best = (decls[prop], spec, order)
    assert best[0] is not None, f"{prop} 선언 없음"
    return best[0]


def _px(value: str) -> float:
    m = re.match(r"([0-9.]+)px$", value)
    assert m, f"px 값 아님: {value}"
    return float(m.group(1))


def test_누름칸_44px_선언():
    """내비 CTA 높이·분류 칩 가로세로 44px 이상 (실효값)."""
    assert _px(_effective("min-height", "a", {"s-btn", "s-navbar__cta"})) >= 44
    assert _px(_effective("min-height", "a", {"s-chip"})) >= 44
    assert _px(_effective("min-width", "a", {"s-chip"})) >= 44


def test_작은글자_14px_실효():
    """깃발 3종(옆으로 넘겨·개수 1·칩 중등)의 실효 글자 크기 14px 이상."""
    assert _px(_effective("font-size", "p", {"s-rooms__hint"})) >= 14
    assert _px(_effective("font-size", "p", {"s-cards__hint"})) >= 14
    assert _px(_effective("font-size", "span", {"s-menu__count"})) >= 14
    assert _px(_effective("font-size", "span", {"s-chip", "s-chip--sm"})) >= 14


# ── 프로브 (목표 4: oklch·사진 위 글자) ──

def _probe_helpers() -> str:
    """_PROBE의 순수 색 함수(rgb·oklchToRgb·lum·blend)만 뽑는다."""
    start = _PROBE.index("const rgb =")
    end = _PROBE.index("a: 1});") + len("a: 1});")
    return _PROBE[start:end]


def test_프로브_oklch_배경대비():
    """역위 띠 oklch 배경을 읽어 흰 글자 대비가 10 이상 나온다 (node로 실제 JS 실행)."""
    if shutil.which("node") is None:
        import pytest
        pytest.skip("node 없음")
    driver = _probe_helpers() + """
const dark = color('oklch(0.25 0.08 27.519)');
if (!dark) { console.log('PARSE_FAIL'); process.exit(0); }
const fg = color('rgb(255, 255, 255)');
const f = blend(fg, dark); const L1 = lum(f), L2 = lum(dark);
const ratio = (Math.max(L1, L2) + 0.05) / (Math.min(L1, L2) + 0.05);
console.log(JSON.stringify({dark, ratio}));
"""
    got = subprocess.run(["node", "-e", driver], capture_output=True, text=True, timeout=60)
    assert got.returncode == 0, got.stderr
    import json
    data = json.loads(got.stdout.strip())
    assert data != "PARSE_FAIL"
    # 실측 배경(#400d0a 부근)과 맞아야 한다
    assert abs(data["dark"]["r"] - 64) < 6
    assert abs(data["dark"]["g"] - 13) < 6
    assert abs(data["dark"]["b"] - 10) < 6
    assert data["ratio"] >= 10


def test_프로브_사진위글자_보류():
    """첫 화면 사진 위 글자는 대비 실패가 아니라 보류(photoBacked)로 센다."""
    assert "photoBacked" in _PROBE
    assert ".s-hero--photo-overlay .s-hero__body" in _PROBE


def test_actionbar_promotes_phone_when_primary_section_missing():
    """주 버튼('길찾기')의 구역이 빠져도 행동 바를 통째로 빼지 않고 전화를 주 버튼으로
    (주소 없는 가게·빌더에서 '오시는 길'을 숨긴 경우 — 전엔 공개 사이트에 전화 링크가 없었다)."""
    import re
    from app.services import design_variants as DV
    from app.services import prd_engine as E
    from app.services import prd_schema as S
    from app.services.site_render import render_site
    card = E.new_card("cafe")
    E._put(card, "shop_name", "모퉁이커피", S.FILLED, 1)
    E._put(card, "phone", "02-123-4567", S.FILLED, 1)
    card["turn"] = 1
    card["layout_edits"] = {"v1": {"hidden": ["around"]}}  # 빌더 처음 모양처럼 '오시는 길'을 숨김
    spec = DV.variants(card)[0]["spec"]
    doc = render_site(spec, site_key="x", title="모퉁이커피", kind="cafe", public=True)
    ids = set(re.findall(r'id="([^"]+)"', doc))
    assert "around-title-around" not in ids  # '오시는 길'이 빠진 공개본
    bar = re.search(r'<nav class="s-actionbar".*?</nav>', doc, re.S)
    assert bar and "tel:021234567" in bar.group(0) and "#around-title-around" not in bar.group(0)
