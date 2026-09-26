"""UI 시안: 요구사항 카드 → 시안 3안(섹션 부품 + 토큰) + 헤드리스 브라우저 스크린샷(카카오 미리보기용).

카드가 없으면(예전 1:1 흐름) 예전 한 장짜리 템플릿으로 만든다.
"""
import html
import logging
from typing import Optional

from app.config import settings

log = logging.getLogger(__name__)


def screenshot_html(html_content: str, out_path, width: int = 800, height: int = 600) -> None:
    screenshot_many([(html_content, out_path)], width, height)


def screenshot_many(pages: list, width: int = 800, height: int = 600) -> None:
    """[(html, 저장 경로)]를 브라우저 한 번 띄워 차례로 찍는다(3안이면 기동 비용을 한 번만 낸다)."""
    # playwright는 무거워서 실제로 찍을 때만 import한다.
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            # 첫 화면 나타내기 애니메이션 도중에 찍으면 흐리게 나온다(9/26 품질 점검 Q-1). 끝난 모습으로 찍는다.
            page = browser.new_page(viewport={"width": width, "height": height}, reduced_motion="reduce")
            for html_content, out_path in pages:
                page.set_content(html_content, timeout=settings.design_screenshot_timeout_ms)
                page.screenshot(path=str(out_path))
        finally:
            browser.close()


_SECTION_NAMES = {"hero": "첫 화면", "intro": "소개", "gallery": "사진첩", "features": "이용 안내", "around": "오시는 길",
                  "cta": "예약·문의 버튼", "reviews": "후기", "video": "영상", "stats": "숫자로 보기"}
_CONTACT_NAMES = {"form": "문의하기 양식", "kakao-channel": "카카오톡 채널"}


def _section_name(sec: dict, offerings_label: str) -> str:
    if sec["type"] == "offerings":
        return offerings_label
    if sec["type"] == "contact":
        return _CONTACT_NAMES.get(sec["variant"], "영업시간·연락")
    return _SECTION_NAMES.get(sec["type"], sec["type"])


def _concept_board(requirement_id: str, title: str, items: list[dict], notes: list[str], placeholders: int,
                   concept: dict, offerings_label: str) -> str:
    """디자인 컨셉 보드 (Stitch식 과정 보여 주기): 컨셉 → 색 → 글꼴 → 구성 → 시안 3안.

    스크립트·폼 없는 보기 전용(시안 주소 CSP sandbox). 단계는 CSS로 차례로 나타난다. 고르기·고치기는 채팅방에서 한다."""
    from app.services import design_concept as DC
    from app.services import site_render

    e = html.escape
    rid = e(requirement_id)
    pal = site_render._resolve_palette(concept["palette"])
    fonts = site_render._bundle()["font_pairs"]
    font = fonts.get(concept["font_pair"], {})
    display = font.get("display", "Pretendard")
    links = f'<link rel="stylesheet" href="{site_render.PRETENDARD_CSS}">'
    if isinstance(font.get("css2_url"), str) and font["css2_url"].startswith("https://"):
        links += f'<link rel="stylesheet" href="{e(font["css2_url"])}">'
    on_primary = site_render.on_primary_for(pal["primary"])
    swatches = "".join(
        f'<li><span class="sw" style="background:{pal[k]}"></span><b>{name}</b><code>{pal[k]}</code></li>'
        for k, name in (("primary", "대표색"), ("accent", "강조색"), ("ground", "바탕"), ("ink", "글자")))
    wire = "".join(
        f'<li class="{"hero" if s["type"] == "hero" else ""}">{e(_section_name(s, offerings_label))}</li>'
        for s in items[0]["spec"]["sections"])
    phones = "\n".join(
        f"""<figure class="phone" style="--i:{i}"><div class="frame"><iframe src="/design/{rid}/{e(v['id'])}/" title="{e(v['name'])} 미리보기" loading="lazy"></iframe></div>
<figcaption><b>{i + 1}안 · {e(v['name'])}</b><span>{e(v['summary'])}</span><a href="/design/{rid}/{e(v['id'])}/" target="_blank" rel="noopener">크게 보기</a></figcaption></figure>"""
        for i, v in enumerate(items))
    note_html = "".join(f"<li>{e(n)}</li>" for n in notes)
    ph = f'<p class="ph">빈 자리 {placeholders}곳은 공개 전에 채우면 좋아요.</p>' if placeholders else ""
    by = "AI(NVIDIA NIM)가 정한 컨셉" if concept.get("source") == "ai" else "업종에 맞춘 기본 컨셉"
    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{e(title)} 디자인 컨셉</title>{links}
<style>
:root{{--p:{pal['primary']};--a:{pal['accent']};--g:{pal['ground']};--k:{pal['ink']};--on:{on_primary};
--disp:"{e(display)}","Pretendard",sans-serif;--body:"Pretendard","Noto Sans KR",sans-serif}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--g);color:var(--k);font:16px/1.6 var(--body);word-break:keep-all}}
::selection{{background:color-mix(in srgb,var(--p) 24%,transparent)}}
.hero{{background:var(--p);color:var(--on);padding:56px 20px 40px}}
.hero .in,.step .in{{max-width:1120px;margin:0 auto}}
.by{{margin:0 0 14px;font-size:14px;font-weight:700;opacity:.85}}
h1{{font:800 clamp(38px,9vw,76px)/1.05 var(--disp);letter-spacing:-.035em;margin:0 0 16px;text-wrap:balance}}
.mood{{display:flex;flex-wrap:wrap;gap:8px;list-style:none;margin:0 0 18px;padding:0}}
.mood li{{padding:6px 14px;border-radius:999px;border:1px solid color-mix(in srgb,var(--on) 40%,transparent);font-weight:700}}
.why{{max-width:40em;margin:0;font-size:18px}}
.step{{padding:40px 20px;border-top:1px solid color-mix(in srgb,var(--k) 12%,transparent);animation:up .8s cubic-bezier(.16,1,.3,1) both;animation-delay:calc(var(--n)*.35s)}}
.step h2{{font:800 22px/1.3 var(--body);letter-spacing:-.02em;margin:0 0 18px}} .step h2 small{{color:var(--p);margin-right:8px}}
.sws{{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:12px;list-style:none;margin:0;padding:0}}
.sws li{{display:grid;gap:2px}} .sw{{display:block;height:88px;border-radius:14px;border:1px solid color-mix(in srgb,var(--k) 14%,transparent)}}
.sws code{{font-size:14px;opacity:.75}}
.type{{display:grid;gap:8px}} .type .big{{font:800 clamp(34px,8vw,56px)/1.1 var(--disp);letter-spacing:-.03em}}
.type .small{{max-width:36em}}
.wire{{list-style:none;margin:0;padding:12px;display:grid;gap:8px;max-width:260px;border:2px solid color-mix(in srgb,var(--k) 20%,transparent);border-radius:28px;background:#fff}}
.wire li{{padding:10px 12px;border-radius:10px;background:color-mix(in srgb,var(--k) 7%,transparent);font-size:14px;font-weight:700}}
.wire li.hero{{padding:34px 12px;background:var(--p);color:var(--on)}}
.phones{{display:grid;gap:28px;grid-template-columns:repeat(auto-fit,minmax(280px,1fr))}}
.phone{{margin:0;animation:up .9s cubic-bezier(.16,1,.3,1) both;animation-delay:calc(1.6s + var(--i)*.45s)}}
.frame{{border:10px solid #16181c;border-radius:40px;overflow:hidden;background:#fff;box-shadow:0 30px 60px -30px rgba(0,0,0,.45)}}
.frame iframe{{display:block;width:100%;height:600px;border:0}}
figcaption{{display:grid;gap:2px;margin-top:12px}} figcaption b{{font-size:18px}} figcaption span{{opacity:.8}}
figcaption a{{color:var(--p);font-weight:700;min-height:44px;display:inline-flex;align-items:center}}
.how{{background:#fff;border-radius:18px;padding:20px;border:1px solid color-mix(in srgb,var(--k) 12%,transparent)}}
.how p{{margin:0 0 6px}} .how q{{font-weight:700;color:var(--p)}} .ph{{color:#8a5a00;font-weight:700}}
.notes{{margin:14px 0 0;padding-left:20px;opacity:.85}}
.sws{{grid-template-columns:repeat(2,1fr)}}
@media (min-width:960px){{.trio{{display:grid;grid-template-columns:1.2fr 1fr .8fr;max-width:1160px;margin:0 auto}}
.trio .step{{border-top:0;padding-top:48px}} .trio .step+.step{{border-left:1px solid color-mix(in srgb,var(--k) 12%,transparent)}}}}
@keyframes up{{from{{opacity:0;transform:translateY(16px)}}to{{opacity:1;transform:none}}}}
@media (prefers-reduced-motion:reduce){{.step,.phone{{animation:none}}}}
</style></head><body>
<header class="hero"><div class="in"><p class="by">{e(title)} · {by}</p><h1>{e(concept['name'])}</h1>
<ul class="mood">{"".join(f"<li>{e(m)}</li>" for m in concept['mood'])}</ul><p class="why">{e(concept['reason'])}</p></div></header>
<div class="trio"><section class="step" style="--n:1"><div class="in"><h2><small>1</small>색</h2><ul class="sws">{swatches}</ul>
<p>{e(DC.PALETTES[concept['palette']])}</p></div></section>
<section class="step" style="--n:2"><div class="in"><h2><small>2</small>글꼴</h2><div class="type"><div class="big">{e(title)}</div>
<p class="small">{e(DC.FONT_PAIRS[concept['font_pair']])}. 본문은 읽기 쉬운 프리텐다드로 맞췄어요.</p></div></div></section>
<section class="step" style="--n:3"><div class="in"><h2><small>3</small>구성</h2><ul class="wire">{wire}</ul>
<p>{e(DC.LEADS[concept['lead']])} · 여백 {e(DC.DENSITIES[concept['density']])} · 모서리 {e(DC.RADII[concept['radius']])}</p></div></section></div>
<section class="step" style="--n:4"><div class="in"><h2><small>4</small>시안 3안</h2>{ph}<div class="phones">{phones}</div>
<div class="how" style="margin-top:28px"><p>마음에 드는 번호를 채팅방에 보내 주세요. 예: <q>2안으로 할게요</q></p>
<p>말로 고칠 수도 있어요. 예: <q>더 고급스럽게</q> <q>더 따뜻한 색으로</q> <q>사진 먼저 보여 줘</q></p></div>
<ul class="notes">{note_html}</ul></div></section>
</body></html>"""


def render_variants(requirement_id: str, card: dict) -> dict:
    """카드 → generated/<id>/design/{v1,v2,v3}/index.html + 고르기 페이지 + 미리보기 그림."""
    from app.services import design_variants as DV
    from app.services import site_render

    design_dir = settings.generated_dir / requirement_id / "design"
    design_dir.mkdir(parents=True, exist_ok=True)
    title = DV.title_for(card)
    items = DV.variants(card)
    shots = []
    for v in items:
        page = site_render.render_site(v["spec"], site_key=requirement_id, title=title, kind=DV.kind_for(card))
        (design_dir / v["id"]).mkdir(exist_ok=True)
        (design_dir / v["id"] / "index.html").write_text(page, encoding="utf-8")
        shots.append((page, design_dir / f"{v['id']}.png"))
    from app.services import design_concept as DC
    from app.services import prd_engine as E
    concept = card.get("concept") or DC.rule_concept(card)
    (design_dir / "index.html").write_text(
        _concept_board(requirement_id, title, items, DV.feature_notes(card), DV.placeholder_count(card), concept,
                       E.S.label_for(E.industry_of(card), "offerings")), encoding="utf-8")

    try:
        # 휴대폰 화면 크기로 찍는다(사장님 대부분이 휴대폰으로 본다). 1안 그림을 카카오 미리보기로 쓴다.
        screenshot_many(shots, width=390, height=780)
        (design_dir / "preview.png").write_bytes((design_dir / "v1.png").read_bytes())
        previews = {v["id"]: f"/design/{requirement_id}/{v['id']}.png" for v in items}
    except Exception:
        log.exception("시안 스크린샷 실패, 플레이스홀더로 폴백")
        previews = {v["id"]: f"https://placehold.co/390x780?text={v['id']}" for v in items}

    return {
        "requirement_id": requirement_id,
        "design_variants": [{"id": v["id"], "name": v["name"], "summary": v["summary"], "preview_url": previews[v["id"]],
                             "url": f"/design/{requirement_id}/{v['id']}/"} for v in items],
        "design_url": f"/design/{requirement_id}",
        "preview_url": previews["v1"],
    }


def publish_choice(requirement_id: str, card: dict, variant_id: str) -> None:
    """고른 시안을 공개 사이트로 (generated/<id>/published/index.html → /site/<id>/).

    D31: AI가 서버 코드를 쓰지 않고, 정해진 부품으로 만든 화면 그대로 공개한다. 문의 폼은 공용 API로 동작한다."""
    from app.services import design_variants as DV
    from app.services import site_render

    v = DV.pick(card, variant_id)
    if v is None:
        raise ValueError(f"unknown variant {variant_id}")
    # 가게 이름을 아직 안 정했으면 공개본 첫 화면 제목은 업종으로(빈 제목 방지, 9/26 점검)
    import copy as _copy
    v = _copy.deepcopy(v)
    kind_name = ", ".join(DV._values(card, "business_type"))
    for sec in v["spec"]["sections"]:
        if sec["type"] == "hero" and not sec["content"].get("title") and kind_name:
            sec["content"]["title"] = kind_name
    out = settings.generated_dir / requirement_id / "published"
    out.mkdir(parents=True, exist_ok=True)
    (out / "index.html").write_text(
        site_render.render_site(v["spec"], site_key=requirement_id, title=DV.title_for(card), kind=DV.kind_for(card),
                                public=True),
        encoding="utf-8")


def render_design(requirement_id: str, platform: str, features: list[str], quote_amount: int, quote_basis: str,
                  card: Optional[dict] = None) -> dict:
    """generated/<id>/design/index.html을 만들고 contracts/design_to_link.schema.json 형식을 반환한다."""
    if card and card.get("slots"):
        return render_variants(requirement_id, card)
    template = (settings.templates_dir / "variant-1.html").read_text(encoding="utf-8")
    features_html = "\n".join(f"      <li>{html.escape(f)}</li>" for f in features) or "      <li>(기능 미지정)</li>"
    rendered = (
        template
        .replace("{{TITLE}}", html.escape(f"{platform} 프로젝트 시안"))
        .replace("{{PLATFORM}}", html.escape(platform))
        .replace("{{FEATURES_HTML}}", features_html)
        .replace("{{QUOTE_AMOUNT}}", html.escape(f"{quote_amount:,}원"))
        .replace("{{QUOTE_BASIS}}", html.escape(quote_basis))
        .replace("{{REQUIREMENT_ID}}", html.escape(requirement_id))
    )

    design_dir = settings.generated_dir / requirement_id / "design"
    design_dir.mkdir(parents=True, exist_ok=True)
    (design_dir / "index.html").write_text(rendered, encoding="utf-8")

    # 스크린샷이 실패해도 시안 페이지 자체는 살아 있어야 하므로 플레이스홀더로 폴백한다.
    try:
        screenshot_html(rendered, design_dir / "preview.png")
        preview_url = f"/design/{requirement_id}/preview.png"
    except Exception:
        log.exception("시안 스크린샷 실패, 플레이스홀더로 폴백")
        preview_url = f"https://placehold.co/600x400?text={platform}+UI+시안"

    return {
        "requirement_id": requirement_id,
        "design_variants": [{"id": "v1", "preview_url": preview_url}],
        "design_url": f"/design/{requirement_id}",
        "preview_url": preview_url,
    }
