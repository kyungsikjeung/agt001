"""시안 렌더러 (작업 R1, C7 핵심).

입력: templates/samples 형식의 디자인 명세 dict
  {version, tokens:{palette,font_pair,density,radius,image_style},
   sections:[{id,type,variant,content}], locked}
출력: 완전한 HTML 문서 한 장 (스크립트 없음, CSP sandbox 전제).

계약 근거:
- templates/README.md (§2 토큰→CSS 변수, §3 부품별 변수, §4 파생값, §5 문의 폼)
- docs/product/SECTION_LIBRARY_SPEC.md (§1 토큰 파생값, §1.5 image_style, §2 부품)
"""
import html
import json
import re
from pathlib import Path

import chevron

from app.config import settings


class SiteSpecError(ValueError):
    """명세 검증 실패 (없는 type--variant 조합, 없는 토큰 ID 등)."""


# 허용 URL 앞부분 (href/src로 가는 값 전용, README §4·작업 지시).
_URL_OK_PREFIXES = ("https://", "tel:", "sms:", "mailto:", "#")

# image_style 선택지 (SPEC §1.5, 수치 파일 없음).
_IMAGE_STYLES = ("full-bleed", "card", "circle-mini")

# 파일 캐시 (settings.templates_dir 기준, 한 번만 읽는다).
_CACHE: dict = {}


def _templates_dir() -> Path:
    return Path(settings.templates_dir)


def _bundle() -> dict:
    """템플릿·토큰·CSS 묶음을 읽어 캐시한다."""
    key = str(_templates_dir())
    hit = _CACHE.get(key)
    if hit is not None:
        return hit
    base = _templates_dir()
    templates = {}
    for path in sorted((base / "sections").glob("*.mustache")):
        templates[path.stem] = path.read_text(encoding="utf-8")
    tokens = base / "tokens"
    palettes = json.loads((tokens / "palettes.json").read_text(encoding="utf-8"))
    font_pairs = json.loads((tokens / "font_pairs.json").read_text(encoding="utf-8"))
    density = json.loads((tokens / "density.json").read_text(encoding="utf-8"))
    radius = json.loads((tokens / "radius.json").read_text(encoding="utf-8"))
    site_css = (base / "site.css").read_text(encoding="utf-8")
    built = {
        "templates": templates,
        "palettes": palettes,
        "font_pairs": font_pairs,
        "density": density,
        "radius": radius,
        "site_css": site_css,
    }
    _CACHE[key] = built
    return built


# chevron은 {{#이름}}...{{이름}}...{{/이름}}처럼 같은 이름이 겹치면
# 안쪽 {{이름}}을 문자열 스코프의 같은 이름 메서드(str.title 등)에서 먼저 찾아
# "<built-in method ...>"를 렌더하는 문제가 있다.
# Mustache 명세상 문자열 스코프에 이름 붙은 자식은 없으므로,
# 문자열을 일반 객체로 감싸 조회가 부모 스코프로 떨어지게 한다.
# 렌더 시점에는 str()로 풀어 평범한 문자열처럼 이스케이프된다.
# 밑줄 이름은 chevron 내부 동작과 겹칠 수 있어 별도로 막지 않고,
# __getattr__에서 전부 AttributeError로 떨어뜨린다.
class _SafeText:
    """chevron 스코프 그림자 방지용 문자열 상자."""

    __slots__ = ("_text",)

    def __init__(self, text):
        self._text = text if isinstance(text, str) else str(text)

    def __str__(self):
        return self._text

    def __repr__(self):
        return f"_SafeText({self._text!r})"

    def __bool__(self):
        return bool(self._text)

    def __eq__(self, other):
        if isinstance(other, _SafeText):
            return self._text == other._text
        if isinstance(other, str):
            return self._text == other
        return NotImplemented

    def __hash__(self):
        return hash(self._text)

    def __getattr__(self, name: str):
        raise AttributeError(name)


def _safe(value):
    """템플릿에 넘기기 전 모든 문자열을 _SafeText로 감싼다."""
    if isinstance(value, _SafeText):
        return value
    if isinstance(value, str):
        return _SafeText(value)
    if isinstance(value, list):
        return [_safe(item) for item in value]
    if isinstance(value, dict):
        return {key: _safe(item) for key, item in value.items()}
    return value


def list_variants() -> list:
    """사용 가능한 type--variant 목록 (예: 'hero--photo-overlay')."""
    return sorted(_bundle()["templates"].keys())


def _clean_url(value) -> str:
    """허용 앞부분이 아니면 빈 값으로 돌린다 (자리 표시 분기용)."""
    if not isinstance(value, str):
        return ""
    text = value.strip()
    lowered = text.lower()
    for prefix in _URL_OK_PREFIXES:
        if lowered.startswith(prefix):
            return text
    return ""


def _digits(value) -> str:
    """전화번호에서 숫자만 남긴다 (tel:/sms: href 전용)."""
    if not isinstance(value, str):
        return ""
    return re.sub(r"\D", "", value)


def _hex_to_rgb(color: str) -> tuple:
    """16진 6자리 소문자 색을 (r, g, b) 정수로 바꾼다."""
    code = color.strip().lstrip("#")
    if len(code) != 6 or not re.fullmatch(r"[0-9a-f]{6}", code.lower()):
        raise SiteSpecError(f"색 형식이 16진 6자리가 아님: {color!r}")
    code = code.lower()
    return (int(code[0:2], 16), int(code[2:4], 16), int(code[4:6], 16))


def _rel_luminance(rgb: tuple) -> float:
    """WCAG 상대 휘도."""

    def channel(value: int) -> float:
        part = value / 255.0
        if part <= 0.03928:
            return part / 12.92
        return ((part + 0.055) / 1.055) ** 2.4

    red, green, blue = rgb
    return 0.2126 * channel(red) + 0.7152 * channel(green) + 0.0722 * channel(blue)


def contrast_ratio(first: str, second: str) -> float:
    """두 16진 색의 WCAG 대비율."""
    light = _rel_luminance(_hex_to_rgb(first))
    dark = _rel_luminance(_hex_to_rgb(second))
    if light < dark:
        light, dark = dark, light
    return (light + 0.05) / (dark + 0.05)


def on_primary_for(primary: str) -> str:
    """SPEC §1.1: primary와 흰색 대비가 4.5:1 이상이면 흰색, 아니면 검정에 가까운 색."""
    if contrast_ratio(primary, "#ffffff") >= 4.5:
        return "#FFFFFF"
    return "#1A1A1A"


def _mix_with_white(color: str) -> str:
    """바탕색과 흰색 1:1 혼합 대체값 (구형 브라우저용)."""
    red, green, blue = _hex_to_rgb(color)
    mixed = tuple(round((part + 255) / 2) for part in (red, green, blue))
    return "#{:02x}{:02x}{:02x}".format(*mixed)


def _ink_to_rgba(color: str, alpha: float) -> str:
    """글자색에 투명도를 얹은 rgba() 대체값 (구형 브라우저용)."""
    red, green, blue = _hex_to_rgb(color)
    return f"rgba({red},{green},{blue},{alpha:g})"


def _mix_ink_ground(ink: str, ground: str, ink_ratio: float = 0.6) -> str:
    """--muted 대체값: 글자색 ink_ratio + 바탕색 혼합."""
    ink_rgb = _hex_to_rgb(ink)
    ground_rgb = _hex_to_rgb(ground)
    mixed = tuple(
        round(first * ink_ratio + second * (1 - ink_ratio))
        for first, second in zip(ink_rgb, ground_rgb)
    )
    return "#{:02x}{:02x}{:02x}".format(*mixed)


def _lookup_token(table: dict, token_id, kind: str):
    """토큰 ID를 표에서 찾는다. 없으면 SiteSpecError."""
    if not isinstance(token_id, str) or token_id not in table:
        raise SiteSpecError(f"없는 {kind} 토큰 ID: {token_id!r}")
    return table[token_id]


def _resolve_palette(palette_ref) -> dict:
    """팔레트 ID 문자열 또는 {primary,accent,ground,ink} dict를 색 dict로 바꾼다."""
    if isinstance(palette_ref, dict):
        for need in ("primary", "accent", "ground", "ink"):
            if need not in palette_ref:
                raise SiteSpecError(f"팔레트에 {need} 키가 없음")
            _hex_to_rgb(str(palette_ref[need]))
        return {key: str(palette_ref[key]).lower() for key in ("primary", "accent", "ground", "ink")}
    table = _bundle()["palettes"]
    found = _lookup_token(table, palette_ref, "palette")
    return {key: str(found[key]).lower() for key in ("primary", "accent", "ground", "ink")}


def _root_css(palette: dict, font_pair: dict, density: dict, radius: dict) -> str:
    """토큰 → :root CSS 변수 블록 (README §2 + SPEC §1.1 파생값)."""
    primary = palette["primary"]
    accent = palette["accent"]
    ground = palette["ground"]
    ink = palette["ink"]
    on_primary = on_primary_for(primary)
    ground_soft = _mix_with_white(ground)
    line = _ink_to_rgba(ink, 0.14)
    muted = _mix_ink_ground(ink, ground)
    display = str(font_pair.get("display", "Pretendard"))
    body = str(font_pair.get("body", "Pretendard"))
    if display == body:
        display_stack = f'"{display}", "Noto Sans KR", sans-serif'
    else:
        display_stack = f'"{display}", "{body}", sans-serif'
    body_stack = f'"{body}", "Noto Sans KR", sans-serif'
    pad = int(density["pad_y"])
    pad_mobile = int(density["pad_y_mobile"])
    gap = int(density["gap"])
    card_pad = int(density["card_pad"])
    card = int(radius["card"])
    btn = int(radius["btn"])
    lines = [
        ":root{",
        f"--c-primary:{primary};--c-accent:{accent};--c-ground:{ground};--c-ink:{ink};",
        f"--font-display:{display_stack};--font-body:{body_stack};",
        f"--space-section:{pad}px;--space-gap:{gap}px;--space-card:{card_pad}px;",
        f"--content-max:{int(density['content_max'])}px;",
        f"--radius-card:{card}px;--radius-btn:{btn}px;",
        f"--card:#FFFFFF;--on-primary:{on_primary};",
        # 구형 브라우저 대체값을 먼저 두고 color-mix를 덮어쓴다.
        f"--ground-soft:{ground_soft};",
        "--ground-soft:color-mix(in srgb, var(--c-ground) 50%, #FFFFFF);",
        f"--line:{line};",
        "--line:color-mix(in srgb, var(--c-ink) 14%, transparent);",
        f"--focus:{accent};",
        f"--muted:{muted};",
        "--muted:color-mix(in srgb, var(--c-ink) 60%, var(--c-ground));",
        "}",
        "@media (max-width:767px){:root{",
        f"--space-section:{pad_mobile}px;",
        "}}",
    ]
    return "".join(lines)


def _hero_context(content: dict) -> dict:
    cta = content.get("cta") or {}
    if not isinstance(cta, dict):
        cta = {}
    label = cta.get("label", "") if isinstance(cta.get("label", ""), str) else ""
    raw_href = cta.get("href", "") if isinstance(cta.get("href", ""), str) else ""
    href = _clean_url(raw_href)
    if href.lower().startswith("tel:"):
        digits = _digits(href[4:])
        href = f"tel:{digits}" if digits else ""
    if not label:
        label = ""
        href = ""
    image_raw = content.get("image", "")
    image_src = _clean_url(image_raw) if isinstance(image_raw, str) else ""
    alt_raw = content.get("image_alt", "")
    image_alt = alt_raw if isinstance(alt_raw, str) and alt_raw else "가게 전경 사진"
    return {
        "title": content.get("title", "") if isinstance(content.get("title", ""), str) else "",
        "subtitle": content.get("subtitle", "") if isinstance(content.get("subtitle", ""), str) else "",
        "image_src": image_src,
        "image_alt": image_alt,
        "cta_label": label,
        "cta_href": href,
    }


def _offering_items(content: dict, with_image: bool, with_index: bool) -> tuple:
    raw = content.get("items", [])
    if not isinstance(raw, list):
        raw = []
    items = []
    for pos, entry in enumerate(raw, start=1):
        if not isinstance(entry, dict):
            continue
        name = entry.get("name", "")
        desc = entry.get("desc", "")
        price = entry.get("price", "")
        one = {
            "name": name if isinstance(name, str) else "",
            "desc": desc if isinstance(desc, str) else "",
            "price": price if isinstance(price, str) else "",
        }
        if with_image:
            image_raw = entry.get("image", "")
            one["image_src"] = _clean_url(image_raw) if isinstance(image_raw, str) else ""
            alt_raw = entry.get("image_alt", "")
            one["image_alt"] = alt_raw if isinstance(alt_raw, str) and alt_raw else "상품 사진"
        if with_index:
            one["index"] = pos
        items.append(one)
    return items, bool(items)


def _gallery_items(content: dict) -> list:
    raw = content.get("items", [])
    if not isinstance(raw, list):
        return []
    items = []
    for pos, entry in enumerate(raw, start=1):
        if not isinstance(entry, dict):
            continue
        src_raw = entry.get("src", "") or entry.get("image", "")
        src = _clean_url(src_raw) if isinstance(src_raw, str) else ""
        alt_raw = entry.get("alt", "") or entry.get("image_alt", "")
        alt = alt_raw if isinstance(alt_raw, str) and alt_raw else f"가게 사진 {pos}"
        caption = entry.get("caption", "")
        items.append({
            "src": src,
            "alt": alt,
            "caption": caption if isinstance(caption, str) else "",
        })
    return [one for one in items if one["src"] or one["caption"] or one["alt"].strip()]


def _around_items(content: dict) -> tuple:
    raw = content.get("items", [])
    if not isinstance(raw, list):
        raw = []
    items = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name", "")
        note = entry.get("note", "")
        items.append({
            "name": name if isinstance(name, str) else "",
            "note": note if isinstance(note, str) else "",
        })
    return items, bool(items)


def _phone_pair(content: dict) -> tuple:
    phone = content.get("phone", "")
    if not isinstance(phone, str):
        phone = ""
    return phone, _digits(phone)


def _text(content: dict, key: str) -> str:
    value = content.get(key, "")
    return value if isinstance(value, str) else ""


def _section_context(
    section_type: str, variant: str, section_id: str, content: dict,
    *, site_key: str, retention_days: int,
) -> dict | None:
    """부품별 content → 템플릿 변수 매핑 (README §3·§4 그대로).

    갤러리는 사진 0장이면 None을 돌려 섹션을 숨긴다 (SPEC §2.4).
    """
    key = f"{section_type}--{variant}"
    ctx: dict = {"id": section_id}
    if section_type == "hero":
        ctx.update(_hero_context(content))
    elif section_type == "intro" and variant == "short":
        ctx["body"] = _text(content, "body")
    elif section_type == "intro" and variant == "owner":
        ctx["body"] = _text(content, "body")
        ctx["owner_name"] = _text(content, "owner_name")
    elif section_type == "intro" and variant == "stats":
        ctx["body"] = _text(content, "body")
        raw_stats = content.get("stats", [])
        stats = []
        if isinstance(raw_stats, list):
            for entry in raw_stats:
                if not isinstance(entry, dict):
                    continue
                label = entry.get("label", "")
                value = entry.get("value", "")
                stats.append({
                    "label": label if isinstance(label, str) else "",
                    "value": value if isinstance(value, str) else "",
                })
        ctx["stats"] = stats
        ctx["has_stats"] = bool(stats)
    elif section_type == "offerings" and variant == "list-price":
        ctx["label"] = _text(content, "label")
        items, has_items = _offering_items(content, with_image=False, with_index=False)
        ctx["items"] = items
        ctx["has_items"] = has_items
    elif section_type == "offerings" and variant == "photo-grid":
        ctx["label"] = _text(content, "label")
        items, has_items = _offering_items(content, with_image=True, with_index=False)
        ctx["items"] = items
        ctx["has_items"] = has_items
    elif section_type == "offerings" and variant == "tabs":
        ctx["label"] = _text(content, "label")
        items, has_items = _offering_items(content, with_image=False, with_index=True)
        ctx["items"] = items
        ctx["has_items"] = has_items
    elif section_type == "gallery":
        items = _gallery_items(content)
        if not items:
            return None
        ctx["items"] = items
    elif section_type == "around":
        ctx["address"] = _text(content, "address")
        map_raw = _text(content, "map_url")
        ctx["map_url"] = _clean_url(map_raw)
        items, has_items = _around_items(content)
        ctx["items"] = items
        ctx["has_items"] = has_items
    elif section_type == "contact" and variant == "call-first":
        phone, digits = _phone_pair(content)
        ctx["phone"] = phone
        ctx["phone_digits"] = digits
        ctx["hours"] = _text(content, "hours")
        ctx["address"] = _text(content, "address")
    elif section_type == "contact" and variant == "booking-first":
        phone, digits = _phone_pair(content)
        ctx["phone"] = phone
        ctx["phone_digits"] = digits
        ctx["hours"] = _text(content, "hours")
        ctx["address"] = _text(content, "address")
        ctx["booking_url"] = _clean_url(_text(content, "booking_url"))
    elif section_type == "contact" and variant == "chat-first":
        phone, digits = _phone_pair(content)
        ctx["phone"] = phone
        ctx["phone_digits"] = digits
        ctx["hours"] = _text(content, "hours")
        ctx["address"] = _text(content, "address")
        ctx["channel_url"] = _clean_url(_text(content, "channel_url"))
    elif section_type == "contact" and variant == "form":
        ctx["site_key"] = site_key
        ctx["retention_days"] = int(retention_days)
    elif section_type == "contact" and variant == "kakao-channel":
        kakao = _text(content, "kakao_channel_url") or _text(content, "channel_url")
        ctx["kakao_channel_url"] = _clean_url(kakao)
    elif section_type == "cta" and variant == "call-sms":
        phone, digits = _phone_pair(content)
        ctx["phone"] = phone
        ctx["phone_digits"] = digits
    elif section_type == "cta" and variant == "external":
        phone, digits = _phone_pair(content)
        ctx["phone"] = phone
        ctx["phone_digits"] = digits
        ctx["booking_url"] = _clean_url(_text(content, "booking_url"))
    elif section_type == "reviews" and variant == "list":
        raw = content.get("items", [])
        items = []
        if isinstance(raw, list):
            for entry in raw:
                if not isinstance(entry, dict):
                    continue
                quote = entry.get("quote", "")
                author = entry.get("author", "")
                source = entry.get("source", "")
                items.append({
                    "quote": quote if isinstance(quote, str) else "",
                    "author": author if isinstance(author, str) else "",
                    "source": source if isinstance(source, str) else "",
                })
        ctx["items"] = items
        ctx["has_items"] = bool(items)
    elif section_type == "reviews" and variant == "slot-only":
        pass
    else:  # pragma: no cover - 파일 존재 검사가 먼저 걸러내므로 여기 오지 않음
        raise SiteSpecError(f"매핑할 수 없는 조합: {key}")
    return ctx


def render_site(spec: dict, *, site_key: str = "", retention_days: int = 30, title: str = "") -> str:
    """명세를 완전한 HTML 문서 한 장으로 렌더한다 (스크립트 없음)."""
    if not isinstance(spec, dict):
        raise SiteSpecError("명세는 dict 형태여야 함")
    bundle = _bundle()
    tokens = spec.get("tokens", {})
    if not isinstance(tokens, dict):
        raise SiteSpecError("tokens가 없음")
    palette = _resolve_palette(tokens.get("palette"))
    font_pair = _lookup_token(bundle["font_pairs"], tokens.get("font_pair"), "font_pair")
    density = _lookup_token(bundle["density"], tokens.get("density"), "density")
    radius = _lookup_token(bundle["radius"], tokens.get("radius"), "radius")
    image_style = tokens.get("image_style", "")
    if image_style not in _IMAGE_STYLES:
        raise SiteSpecError(f"없는 image_style 토큰 ID: {image_style!r}")

    sections = spec.get("sections", [])
    if not isinstance(sections, list):
        raise SiteSpecError("sections가 목록 형태가 아님")
    rendered_parts = []
    for pos, section in enumerate(sections):
        if not isinstance(section, dict):
            raise SiteSpecError(f"{pos}번째 섹션이 dict 형태가 아님")
        section_type = section.get("type", "")
        variant = section.get("variant", "")
        section_id = section.get("id", "") or f"sec-{pos + 1}"
        key = f"{section_type}--{variant}"
        template = bundle["templates"].get(key)
        if template is None:
            raise SiteSpecError(f"없는 type--variant 조합: {key}")
        content = section.get("content", {})
        if content is None:
            content = {}
        if not isinstance(content, dict):
            raise SiteSpecError(f"섹션 {section_id!r}의 content가 dict 형태가 아님")
        ctx = _section_context(
            section_type, variant, str(section_id), content,
            site_key=site_key, retention_days=retention_days,
        )
        if ctx is None:
            continue
        rendered_parts.append(chevron.render(template, _safe(ctx)))

    page_title = title.strip() if isinstance(title, str) and title.strip() else "가게 홈페이지"
    css2_url = font_pair.get("css2_url") if isinstance(font_pair, dict) else None
    font_link = ""
    if isinstance(css2_url, str) and css2_url.startswith("https://"):
        font_link = f'<link rel="stylesheet" href="{html.escape(css2_url, quote=True)}">'
    doc = "\n".join([
        "<!doctype html>",
        '<html lang="ko">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>{html.escape(page_title)}</title>",
        font_link,
        "<style>",
        _root_css(palette, font_pair, density, radius),
        bundle["site_css"],
        "</style>",
        "</head>",
        "<body>",
        *rendered_parts,
        "</body>",
        "</html>",
        "",
    ])
    return doc
