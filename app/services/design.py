"""UI 시안: 정적 HTML 템플릿 렌더링 + 헤드리스 브라우저 스크린샷(카카오 미리보기용)."""
import html
import logging

from app.config import settings

log = logging.getLogger(__name__)


def screenshot_html(html_content: str, out_path, width: int = 800, height: int = 600) -> None:
    # playwright는 무거워서 실제로 찍을 때만 import한다.
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": width, "height": height})
            page.set_content(html_content, timeout=settings.design_screenshot_timeout_ms)
            page.screenshot(path=str(out_path))
        finally:
            browser.close()


def render_design(requirement_id: str, platform: str, features: list[str], quote_amount: int, quote_basis: str) -> dict:
    """generated/<id>/design/index.html을 만들고 contracts/design_to_link.schema.json 형식을 반환한다."""
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
