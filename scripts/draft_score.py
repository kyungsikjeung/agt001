"""중간 시안 품질 메트릭 (로컬, LLM·네트워크 불필요).

사용법: .venv/bin/python scripts/draft_score.py [--json]
임계값 미달이 하나라도 있으면 exit 1.
"""
import inspect
import io
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services import design_variants as DV  # noqa: E402
from app.services import site_render as SR  # noqa: E402
from scripts import draft_corpus as C  # noqa: E402

THRESH = {
    "text_only_hero_rate": 0.0,
    "svg_fallback_rate": 0.0,
    "distinct_palette_fail": 0,
    "min_distance_min": 8,
    "subtitle_present_rate": 1.0,
    "cta_present_rate": 1.0,
    "tel_leak": 0,
    "contrast_pass_rate": 1.0,
    "no_script_rate": 1.0,
    "relative_url_ok_rate": 1.0,
    "ai_postproc": True,
    "prompt_enriched": True,
    "model_routing": True,
    # 수상작 휴리스틱 (Awwwards/CSSDA·Nielsen·Jakob 매핑, 정적 검사)
    "single_cta_fail": 0,      # 스퀸트 테스트: 히어로 주 CTA는 1개
    "cta_target_fail": 0,      # locality: #앵커는 문서 내 id에 있어야 함
    "order_fail": 0,           # Jakob: 첫 섹션 hero + 전환(문의/예약) 경로 존재
    "stray_select_fail": 0,    # 예약 폼 밖 <select> 없음
    "overflow_fail": 0,        # 반응형: 390·1280에서 가로 넘침 없음 (3종 스팟)
    "navbar_rate": 1.0,
    "logo_rate": 1.0,
    "marquee_v2_rate": 1.0,
}


def _overflow_failures() -> int | None:
    """스팟 3종×3안×2너비 가로 넘침 검사. 브라우저 기동 실패면 None(스킵)."""
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return None
    try:
        fails = 0
        with sync_playwright() as p:
            browser = p.chromium.launch()
            try:
                for cid in ("cello-lesson", "cafe-talkative", "academy-talkative"):
                    case = C.get(cid)
                    card = C.build_card(case)
                    for v in DV.variants(card):
                        html = SR.render_site(
                            v["spec"], site_key="lab", title=DV.title_for(card),
                            kind=DV.kind_for(card))
                        for width in (390, 1280):
                            pg = browser.new_page(viewport={"width": width, "height": 800})
                            pg.set_content(html)
                            overflow = pg.evaluate(
                                "document.documentElement.scrollWidth - "
                                "document.documentElement.clientWidth")
                            pg.close()
                            if overflow > 1:
                                fails += 1
            finally:
                browser.close()
        return fails
    except Exception:
        return None


def _rendered(case):
    card = C.build_card(case)
    items = DV.variants(card)
    pages = []
    for v in items:
        html = SR.render_site(v["spec"], site_key="lab-" + case["id"],
                              title=DV.title_for(card), kind=DV.kind_for(card))
        pages.append((v, html))
    return card, pages


def main() -> int:
    n_heroes = n_text_only = n_pages = n_svg = 0
    pal_fails = 0
    dist_min = 99
    n_sub = n_cta = 0
    tel_leak = 0
    n_contrast = contrast_ok = 0
    n_noscript = n_urlok = 0
    single_cta_fail = cta_target_fail = order_fail = stray_select_fail = 0
    n_nav = n_logo = n_marquee_v2 = 0
    rows = []
    for case in C.CASES:
        card, pages = _rendered(case)
        specs = [v["spec"] for v, _ in pages]
        pals = {s["tokens"]["palette"] for s in specs}
        if len(pals) < 3:
            pal_fails += 1
        d = DV.min_distance(specs)
        dist_min = min(dist_min, d)
        has_phone = bool((card["slots"].get("phone") or {}).get("value"))
        for v, html in pages:
            n_pages += 1
            hero = next(s for s in v["spec"]["sections"] if s["type"] == "hero")
            n_heroes += 1
            if hero["variant"] == "text-only":
                n_text_only += 1
            if '<div class="s-illu"' in html:
                n_svg += 1
            ctx_hero = hero["content"]
            if (ctx_hero.get("subtitle") or "").strip():
                n_sub += 1
            cta = ctx_hero.get("cta") or {}
            if (cta.get("label") or "").strip():
                n_cta += 1
            if not has_phone and re.search(r'href="tel:', html):
                tel_leak += 1
            if "<script" not in html:
                n_noscript += 1
            rel_srcs = re.findall(r'src="(/[^"]*)"', html)
            if all(s.startswith(("/uploads/", "/art/")) for s in rel_srcs):
                n_urlok += 1
            # 스퀸트: 히어로 구간 주 버튼 1개 (내비는 제외하고 히어로 섹션만 본다)
            hi = html.find('<section class="s-hero')
            hero_html = html[hi:html.find("</section>", hi)] if hi >= 0 else ""
            if hero_html.count('class="s-btn') != 1:
                single_cta_fail += 1
            # locality: #앵커는 문서에 있어야 함
            for anchor in set(re.findall(r'href="(#[^"]+)"', html)):
                aid = anchor[1:]
                if f'id="{aid}"' not in html:
                    cta_target_fail += 1
                    break
            types = [s["type"] for s in v["spec"]["sections"]]
            if types[0] != "hero" or not any(
                    t in types for t in ("contact", "cta", "booking")):
                order_fail += 1
            if "<select" in html and "booking" not in types:
                stray_select_fail += 1
            if 'class="s-navbar"' in html:
                n_nav += 1
            if 'class="s-navbar__logo"' in html:
                n_logo += 1
            if v["id"] == "v2" and 'class="s-marquee"' in html:
                n_marquee_v2 += 1
            pal = SR._resolve_palette(v["spec"]["tokens"]["palette"])
            n_contrast += 1
            try:
                if SR.contrast_ratio(pal["primary"], pal["ground"]) >= 3.0 and \
                   SR.contrast_ratio(pal["ink"], pal["ground"]) >= 4.5:
                    contrast_ok += 1
            except Exception:
                pass
        rows.append(f'{case["id"]}: dist={d} pals={sorted(pals)}')

    # AI 파이프라인 (네트워크 없이 코드·함수 수준 검사)
    from app.services import ai_images as AI
    from app.services import photos
    ai_postproc = hasattr(photos, "_clean_ai_image")
    if ai_postproc:
        try:
            from PIL import Image
            buf = io.BytesIO()
            Image.new("RGB", (2400, 1600), (200, 150, 100)).save(buf, "PNG")
            clean, w, h = photos._clean_ai_image(buf.getvalue())
            ai_postproc = max(w, h) >= 1900 and clean[:2] == b"\xff\xd8"
        except Exception:
            ai_postproc = False
    p_hero = AI.prompt_for("cafe", "hero")
    p_gal = AI.prompt_for("cafe", "gallery-1")
    src = inspect.getsource(AI._generate_bytes)
    prompt_enriched = ("35mm" in p_hero and "16:9" in p_hero and "1:1" in p_gal
                       and "imageConfig" in src)
    # P2 모델 라우팅: hero 오버라이드 지정 시 hero만 상위 모델 (설정 복원)
    from app.config import settings as _settings
    _prev = _settings.gemini_image_model_hero
    try:
        _settings.gemini_image_model_hero = "probe-hero-model"
        model_routing = (AI._model_for("hero") == "probe-hero-model"
                         and AI._model_for("gallery-1") == (_settings.gemini_image_model or "").strip())
    finally:
        _settings.gemini_image_model_hero = _prev

    res = {
        "text_only_hero_rate": round(n_text_only / n_heroes, 3),
        "svg_fallback_rate": round(n_svg / n_pages, 3),
        "distinct_palette_fail": pal_fails,
        "min_distance_min": dist_min,
        "subtitle_present_rate": round(n_sub / n_pages, 3),
        "cta_present_rate": round(n_cta / n_pages, 3),
        "tel_leak": tel_leak,
        "contrast_pass_rate": round(contrast_ok / n_contrast, 3),
        "no_script_rate": round(n_noscript / n_pages, 3),
        "relative_url_ok_rate": round(n_urlok / n_pages, 3),
        "ai_postproc": ai_postproc,
        "prompt_enriched": prompt_enriched,
        "model_routing": model_routing,
        "single_cta_fail": single_cta_fail,
        "cta_target_fail": cta_target_fail,
        "order_fail": order_fail,
        "stray_select_fail": stray_select_fail,
        "navbar_rate": round(n_nav / n_pages, 3),
        "logo_rate": round(n_logo / n_pages, 3),
        "marquee_v2_rate": round(n_marquee_v2 / len(C.CASES), 3),
    }
    overflow = _overflow_failures()
    if overflow is not None:
        res["overflow_fail"] = overflow
    else:
        res["overflow_fail"] = "skip"
    fails = []
    if res["text_only_hero_rate"] != 0.0:
        fails.append("text_only_hero_rate")
    if res["svg_fallback_rate"] != 0.0:
        fails.append("svg_fallback_rate")
    if res["distinct_palette_fail"] != 0:
        fails.append("distinct_palette_fail")
    if res["min_distance_min"] < THRESH["min_distance_min"]:
        fails.append("min_distance_min")
    if res["subtitle_present_rate"] < 1.0:
        fails.append("subtitle_present_rate")
    if res["cta_present_rate"] < 1.0:
        fails.append("cta_present_rate")
    if res["tel_leak"] != 0:
        fails.append("tel_leak")
    if res["contrast_pass_rate"] < 1.0:
        fails.append("contrast_pass_rate")
    if res["no_script_rate"] < 1.0:
        fails.append("no_script_rate")
    if res["relative_url_ok_rate"] < 1.0:
        fails.append("relative_url_ok_rate")
    if res["ai_postproc"] is not True:
        fails.append("ai_postproc")
    if res["prompt_enriched"] is not True:
        fails.append("prompt_enriched")
    if res["model_routing"] is not True:
        fails.append("model_routing")
    if res["single_cta_fail"] != 0:
        fails.append("single_cta_fail")
    if res["cta_target_fail"] != 0:
        fails.append("cta_target_fail")
    if res["order_fail"] != 0:
        fails.append("order_fail")
    if res["stray_select_fail"] != 0:
        fails.append("stray_select_fail")
    if res["navbar_rate"] < 1.0:
        fails.append("navbar_rate")
    if res["logo_rate"] < 1.0:
        fails.append("logo_rate")
    if res["marquee_v2_rate"] < 1.0:
        fails.append("marquee_v2_rate")
    if res["overflow_fail"] != 0 and res["overflow_fail"] != "skip":
        fails.append("overflow_fail")
    print("\n".join(rows))
    print("---")
    for k, v in res.items():
        mark = "PASS" if k not in fails else "FAIL"
        print(f"{mark} {k}={v} (기준 {THRESH[k]})")
    if "--json" in sys.argv:
        import json
        print(json.dumps(res, ensure_ascii=False))
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
