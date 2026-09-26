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


def _picker_page(requirement_id: str, title: str, items: list[dict], notes: list[str], placeholders: int) -> str:
    """3안을 나란히 보는 페이지. 고르기는 채팅방에서 한다(이 페이지는 스크립트·폼 없는 보기 전용)."""
    rid = html.escape(requirement_id)
    cards = "\n".join(
        f"""<article class="card"><iframe src="/design/{rid}/{html.escape(v['id'])}/" title="{html.escape(v['name'])} 미리보기" loading="lazy"></iframe>
<h2>{i + 1}안 · {html.escape(v['name'])}</h2><p>{html.escape(v['summary'])}</p>
<a href="/design/{rid}/{html.escape(v['id'])}/" target="_blank" rel="noopener">크게 보기</a></article>"""
        for i, v in enumerate(items))
    note_html = "".join(f"<li>{html.escape(n)}</li>" for n in notes)
    ph = f"<p class=\"ph\">[입력 필요] 자리 {placeholders}곳은 공개 전에 채워야 해요.</p>" if placeholders else ""
    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)} 시안 3안</title>
<style>
body{{margin:0;font-family:system-ui,-apple-system,"Noto Sans KR",sans-serif;background:#f6f7f9;color:#1f2328}}
header{{padding:20px 16px 4px;max-width:1200px;margin:0 auto}} h1{{font-size:1.25rem;margin:0 0 4px}}
header p{{margin:0;color:#57606a}} .ph{{color:#9a6700}}
.grid{{display:grid;gap:16px;padding:16px;max-width:1200px;margin:0 auto;grid-template-columns:repeat(auto-fit,minmax(300px,1fr))}}
.card{{background:#fff;border:1px solid #d0d7de;border-radius:12px;overflow:hidden;padding-bottom:12px}}
.card iframe{{width:100%;height:520px;border:0;border-bottom:1px solid #d0d7de;background:#fff}}
.card h2{{font-size:1rem;margin:12px 12px 2px}} .card p{{margin:0 12px 8px;color:#57606a}} .card a{{margin:0 12px;color:#0b5fff}}
ul{{max-width:1200px;margin:0 auto;padding:0 32px 24px;color:#57606a}}
</style></head><body><header><h1>{html.escape(title)} · 시안 3안</h1>
<p>마음에 드는 안의 번호를 채팅방에 보내 주세요. 예: "2안으로 할게요"</p>{ph}</header>
<main class="grid">{cards}</main><ul>{note_html}</ul></body></html>"""


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
    (design_dir / "index.html").write_text(
        _picker_page(requirement_id, title, items, DV.feature_notes(card), DV.placeholder_count(card)), encoding="utf-8")

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
