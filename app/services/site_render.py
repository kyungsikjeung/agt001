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
from urllib.parse import quote

import chevron

from app.config import settings
from app.services.video_links import parse_video_url


class SiteSpecError(ValueError):
    """명세 검증 실패 (없는 type--variant 조합, 없는 토큰 ID 등)."""


# 허용 URL 앞부분 (href/src로 가는 값 전용, README §4·작업 지시).
# "/uploads/"는 우리 사진 주소 전용 (contracts/ROOM_FEATURES_API.md §4).
# "/art/"는 기본 제공 그림 주소 전용 (templates/art/, 외부 주소 아님).
# 그 외 상대경로는 계속 막는다.
_URL_OK_PREFIXES = ("https://", "tel:", "sms:", "mailto:", "#", "/uploads/", "/art/")

# 업종별 예시 그림 키 (작업 A1, design_variants._SAMPLE_FOR 업종 키와 같음).
KIND_KEYS = ("pension", "cafe", "restaurant", "salon", "workshop",
             "academy", "individual", "group", "webservice", "other")

# 사진 칸 대체 그림 용도 (대표 1장 + 사진첩용 2장).
_ILLU_NAMES = ("hero", "gallery-1", "gallery-2")

# 사진 있는 hero 템플릿 (text-only는 사진 칸이 없어 대상 아님).
_HERO_PHOTO_VARIANTS = ("photo-overlay", "photo-side")

# hero·gallery 템플릿의 빈 사진 자리 표시 (인라인 그림으로 갈아끼운다).
_HERO_EMPTY_MARK = ('<div class="s-media__empty is-placeholder"'
                    ' aria-label="사진: 아직 입력되지 않음">[사진 입력]</div>')

# image_style 선택지 (SPEC §1.5, 수치 파일 없음).
_IMAGE_STYLES = ("full-bleed", "card", "circle-mini")
# 프리텐다드 가변 글꼴(한글 부분 집합, SIL OFL). jsdelivr는 버전 고정 주소만 쓴다.
PRETENDARD_CSS = ("https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/"
                  "pretendardvariable-dynamic-subset.min.css")

# 예시 그림 원문 캐시 (종류·용도별 SVG, 인라인으로만 쓴다).
_ILLUSTRATIONS: dict = {}


def _normalize_kind(kind) -> str:
    """업종 키를 10종 중 하나로 맞춘다. 모르면 other."""
    if isinstance(kind, str) and kind.strip().lower() in KIND_KEYS:
        return kind.strip().lower()
    return "other"


def _illustration_svg(kind: str, name: str) -> str:
    """업종·용도별 예시 SVG 원문을 돌린다 (자체 제작, 외부 파일 호출 없음)."""
    safe_kind = _normalize_kind(kind)
    if name not in _ILLU_NAMES:
        name = "hero"
    key = f"{safe_kind}/{name}"
    hit = _ILLUSTRATIONS.get(key)
    if hit is not None:
        return hit
    path = _templates_dir() / "illustrations" / f"{safe_kind}-{name}.svg"
    if not path.is_file():
        path = _templates_dir() / "illustrations" / f"other-{name}.svg"
    text = path.read_text(encoding="utf-8")
    if "<script" in text.lower():
        raise SiteSpecError(f"예시 그림에 스크립트가 있음: {key}")
    _ILLUSTRATIONS[key] = text
    return text


def _illustration_block(kind: str, name: str) -> str:
    """빈 사진 칸에 넣을 인라인 그림 + 예시 표시 한 묶음."""
    return ('<div class="s-illu" role="img" aria-label="예시 이미지: 사장님 사진으로 바뀌어요">'
            + _illustration_svg(kind, name)
            + '<span class="s-illu-badge">예시 이미지</span></div>')


def _gallery_example_html(section_id: str, variant: str, kind: str, label: str = "") -> str:
    """사진 0장인 사진첩의 예시 그림 2장 + 안내 문구 (템플릿 구조와 같은 등급)."""
    safe_id = html.escape(section_id, quote=True)
    if variant not in ("grid", "swipe"):
        variant = "grid"
    list_class = "s-gallery__swipe" if variant == "swipe" else "s-gallery__list"
    figures = "".join(
        "<li><figure>" + _illustration_block(kind, name) + "</figure></li>"
        for name in ("gallery-1", "gallery-2")
    )
    return (
        f'<section class="s-gallery s-gallery--{variant}"'
        f' data-section-id="{safe_id}" aria-labelledby="gallery-title-{safe_id}">'
        f'<h2 id="gallery-title-{safe_id}">{html.escape(label or "사진첩")}</h2>'
        f'<ul class="{list_class}">{figures}</ul>'
        '<p class="s-gallery__notice">사장님 사진으로 바뀌어요</p>'
        "</section>"
    )


def _templates_dir() -> Path:
    return Path(settings.templates_dir)


# 파일 캐시 (settings.templates_dir 기준, 한 번만 읽는다).
_CACHE: dict = {}


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
    """허용 앞부분이 아니면 빈 값으로 돌린다 (자리 표시·예시 그림 분기용).

    우리 사진 주소 "/uploads/"로 시작하는 값도 허용한다
    (contracts/ROOM_FEATURES_API.md §4). 다른 상대경로는 계속 막는다.
    """
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
    facts = [f for f in (content.get("facts") or []) if isinstance(f, dict)
             and isinstance(f.get("label"), str) and isinstance(f.get("value"), str) and f["value"].strip()][:3]
    label2, href2 = _cta_pair(content.get("cta2"))
    return {
        "cta2_label": label2 if label else "",
        "cta2_href": href2 if label else "",
        "facts": [{"label": f["label"], "value": f["value"]} for f in facts],
        "has_facts": bool(facts),
        "title": content.get("title", "") if isinstance(content.get("title", ""), str) else "",
        "subtitle": content.get("subtitle", "") if isinstance(content.get("subtitle", ""), str) else "",
        "image_src": image_src,
        "image_alt": image_alt,
        "image_ai_badge": bool(image_src and content.get("ai_example")),
        "cta_label": label,
        "cta_href": href,
    }


def _cta_pair(cta) -> tuple:
    """{label, href} → (라벨, 허용된 주소). 전화는 숫자만 남긴다. 하나라도 비면 ("", "")."""
    if not isinstance(cta, dict):
        return "", ""
    label = cta.get("label") if isinstance(cta.get("label"), str) else ""
    href = _clean_url(cta.get("href", ""))
    if href.lower().startswith("tel:"):
        digits = _digits(href[4:])
        href = f"tel:{digits}" if digits else ""
    return (label, href) if label.strip() and href else ("", "")


def _drop_examples(value):
    """공개본용 (D53①): example=True인 목록 항목은 빼고, <칸>_example=True인 칸 값은 비운다.
    image_example(예시 이미지 표시)은 D51대로 공개본에도 표시와 함께 남긴다."""
    if isinstance(value, list):
        return [_drop_examples(v) for v in value if not (isinstance(v, dict) and v.get("example") is True)]
    if isinstance(value, dict):
        out = {k: _drop_examples(v) for k, v in value.items()}
        for k, v in value.items():
            field = k[:-len("_example")]
            if k.endswith("_example") and v is True and field != "image" and field in out:
                out[field] = [] if isinstance(out[field], list) else ""
        return out
    return value


def _map_links(address: str) -> list:
    """지도 앱 검색 링크 (키 필요 없음, D53②: 지도 그림은 아직 예시)."""
    if not address.strip():
        return []
    q = quote(address.strip())
    return [{"label": "카카오맵", "href": f"https://map.kakao.com/?q={q}"},
            {"label": "네이버 지도", "href": f"https://map.naver.com/p/search/{q}"}]


def _menu_categories(content: dict) -> list:
    """분류 메뉴판: [{name, index, image_*, items:[{name, desc, price, price_example, badge}], count}]."""
    raw = content.get("categories")
    cats = []
    for pos, entry in enumerate(raw if isinstance(raw, list) else [], start=1):
        if not isinstance(entry, dict):
            continue
        items = []
        for it in entry.get("items") if isinstance(entry.get("items"), list) else []:
            if not isinstance(it, dict) or not _text(it, "name").strip():
                continue
            items.append({"name": _text(it, "name"), "desc": _text(it, "desc"), "price": _text(it, "price"),
                          "price_example": it.get("price_example") is True, "badge": _text(it, "badge")[:8],
                          "example": it.get("example") is True})
        if not items:
            continue
        name = _text(entry, "name")
        image = _clean_url(_text(entry, "image"))
        cats.append({"name": name, "index": pos, "count": len(items), "items": items,
                     "image_src": image, "image_alt": _text(entry, "image_alt") or f"{name} 사진",
                     "image_example": bool(image and entry.get("image_example"))})
    return cats


def _staff_members(content: dict) -> list:
    """담당자 카드: [{name, role, bio, initial, specialties, image_*, example}] 최대 8명."""
    raw = content.get("members")
    members = []
    for entry in (raw if isinstance(raw, list) else [])[:8]:
        if not isinstance(entry, dict) or not _text(entry, "name").strip():
            continue
        name, role = _text(entry, "name").strip(), _text(entry, "role")
        tags = entry.get("specialties")
        tags = [{"text": s} for s in (tags if isinstance(tags, list) else []) if isinstance(s, str) and s.strip()][:4]
        image = _clean_url(_text(entry, "image"))
        members.append({"name": name, "role": role, "bio": _text(entry, "bio"), "initial": name[:1],
                        "specialties": tags, "has_specialties": bool(tags),
                        "image_src": image, "image_alt": f"{name} {role} 사진".strip(),
                        "image_example": bool(image and entry.get("image_example")),
                        "example": entry.get("example") is True})
    return members


_SLOT_STATES = {"open": "여유", "few": "마감 임박", "full": "마감"}
_SLOT_VALUE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_SLOT_TIME = re.compile(r"^\d{2}:\d{2}$")


def _booking_days(content: dict) -> list:
    """예약 현황: [{label, dow, slots:[{time, value, key, state, state_label, is_full}]}] 최대 14일·하루 16칸."""
    raw = content.get("days")
    days = []
    for entry in (raw if isinstance(raw, list) else [])[:14]:
        if not isinstance(entry, dict) or not _SLOT_VALUE.match(_text(entry, "date")):
            continue
        date = _text(entry, "date")
        slots = []
        for s in (entry.get("slots") if isinstance(entry.get("slots"), list) else [])[:16]:
            if not isinstance(s, dict) or not _SLOT_TIME.match(_text(s, "time")):
                continue
            state = s.get("state") if s.get("state") in _SLOT_STATES else "open"
            slots.append({"time": s["time"], "value": f"{date} {s['time']}",
                          "key": f"{date}-{s['time']}".replace(":", ""), "state": state,
                          "state_label": _SLOT_STATES[state], "is_full": state == "full"})
        if slots:
            days.append({"label": _text(entry, "label") or date[5:].replace("-", "/"),
                         "dow": _text(entry, "dow"), "slots": slots})
    return days


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
            "ai_badge": bool(src and entry.get("ai")),
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


def _video_items(content: dict) -> list:
    """영상 카드용 items (최대 3개, https·지원 주소만, 썸네일 포함)."""
    raw = content.get("items", [])
    if not isinstance(raw, list):
        return []
    items = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        info = parse_video_url(entry.get("url", ""))
        if info is None:
            continue
        title = entry.get("title", "")
        if not isinstance(title, str):
            title = ""
        items.append({
            "url": info["url"],
            "title": title,
            "platform": info["platform"],
            "platform_label": info["platform_label"],
            "thumb": info["thumb"],
        })
        if len(items) >= 3:
            break
    return items


def _navbar_context(nav: dict) -> dict | None:
    """전역 내비게이션 (섹션 아님: 순서·거리·리드 계산에서 제외).
    로고=상호 첫 글자(SVG·AI 생성 없이 텍스트 모노그램), 링크=실제 섹션 id만."""
    if not isinstance(nav, dict):
        return None
    title = nav.get("title") if isinstance(nav.get("title"), str) else ""
    letter = (title.strip()[:1] or "우") if title else "우"
    links = [l for l in (nav.get("links") or []) if isinstance(l, dict)
             and isinstance(l.get("label"), str) and isinstance(l.get("href"), str)
             and l["label"].strip() and l["href"].strip()][:4]
    ctx: dict = {"logo_letter": letter, "title": title, "links": links,
               "top": nav.get("top") if isinstance(nav.get("top"), str) and nav.get("top").startswith("#") else "#"}
    cta = nav.get("cta") or {}
    label = cta.get("label", "") if isinstance(cta, dict) else ""
    href = cta.get("href", "") if isinstance(cta, dict) else ""
    href = _clean_url(href) if isinstance(href, str) else ""
    if isinstance(label, str) and label and href:
        if href.lower().startswith("tel:"):
            digits = _digits(href[4:])
            href = f"tel:{digits}" if digits else ""
        if href:
            ctx["cta_label"] = label
            ctx["cta_href"] = href
    return ctx


def _section_context(
    section_type: str, variant: str, section_id: str, content: dict,
    *, site_key: str, retention_days: int,
) -> dict | None:
    """부품별 content → 템플릿 변수 매핑 (README §3·§4 그대로).

    갤러리는 사진 0장이면 예시 그림 표시용 {"is_example": True}를 돌린다
    (작업 A1, SPEC §2.4 숨김 대신). render_site가 예시 HTML로 채운다.
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
        if not any(one.get("src") for one in items):
            return {"id": section_id, "is_example": True, "label": _text(content, "label")}
        ctx["label"] = _text(content, "label")
        ctx["items"] = items
        # marquee(자동 흐름)는 같은 목록을 두 번 이어 붙인다 (뒷복사는 장식으로만).
        if variant == "marquee":
            ctx["items_twice"] = items + [{**one, "repeat": True} for one in items]
    elif section_type == "around":
        ctx["address"] = _text(content, "address")
        map_raw = _text(content, "map_url")
        ctx["map_url"] = _clean_url(map_raw)
        items, has_items = _around_items(content)
        ctx["items"] = items
        ctx["has_items"] = has_items
        if variant == "map":
            ctx["label"] = _text(content, "label")
            ctx["links"] = _map_links(ctx["address"])
            ctx["has_links"] = bool(ctx["links"])
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
    elif section_type == "booking" and variant == "form":
        # 예약 신청 폼 (BOOKING_PLAN §2.3): 사장님 입력은 _text 경로로만 받는다.
        ctx["site_key"] = site_key
        ctx["retention_days"] = int(retention_days)
        # 방문일 범위(오늘~60일)는 HTML에 넣지 않는다: 공개 날짜로 굳어 두 달 뒤엔 고를 날이 없어진다.
        # 범위 검사는 서버(bookings.submit, 한국 날짜)가 한다.
        ctx["note"] = _text(content, "note")
        ctx["service_label"] = _text(content, "service_label") or "메뉴"
        raw_services = content.get("services", [])
        services = []
        if isinstance(raw_services, list):
            for entry in raw_services:
                if isinstance(entry, str) and entry.strip():
                    services.append({"name": entry})
        ctx["services"] = services
        ctx["has_services"] = bool(services)
        raw_times = content.get("time_options", [])
        times = []
        if isinstance(raw_times, list):
            for entry in raw_times:
                if isinstance(entry, str) and entry.strip():
                    times.append({"value": entry})
        ctx["time_options"] = times
        ctx["has_time_options"] = bool(times)
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
    elif section_type == "features" and variant == "icons":
        # P2 새 부품(templates/README.md §3): 아이콘 6종 중 하나만 참으로
        icons = ("star", "pin", "clock", "phone", "leaf", "heart")
        items = []
        for raw in content.get("items", [])[:6] if isinstance(content.get("items"), list) else []:
            if not isinstance(raw, dict) or not _text(raw, "title"):
                continue
            icon = raw.get("icon") if raw.get("icon") in icons else "star"
            items.append({"title": _text(raw, "title"), "desc": _text(raw, "desc"), "icon": icon,
                          **{f"icon_{i}": i == icon for i in icons}})
        if not items:
            return None
        ctx["label"] = _text(content, "label")
        ctx["items"] = items
        ctx["has_items"] = True
        # 편의 안내 덧붙인 말: 항목 아래 한 줄로 보인다(chevron {{note}} 경로로 빠져나감)
        ctx["note"] = _text(content, "note")
    elif section_type == "stats" and variant == "band":
        items = [{"value": _text(r, "value"), "label": _text(r, "label")}
                 for r in (content.get("items") or []) if isinstance(r, dict) and _text(r, "value")][:4]
        if not items:
            return None  # 사장님이 말한 숫자가 없으면 띠를 두지 않는다
        ctx["title"] = _text(content, "title")
        ctx["items"] = items
        ctx["has_items"] = True
    elif section_type == "video" and variant == "card":
        items = _video_items(content)
        if not items:
            return None
        ctx["items"] = items
    elif section_type == "offerings" and variant == "cards":
        # 편집형 A 메뉴 카드 격자 (이름·한 줄 특징·가격 + 사진).
        ctx["label"] = _text(content, "label")
        items, has_items = _offering_items(content, with_image=True, with_index=False)
        ctx["items"] = items
        ctx["has_items"] = has_items
    elif section_type == "concerns" and variant == "bubbles":
        # 편집형 B 고민 말풍선 (새 type).
        ctx["heading"] = _text(content, "heading")
        ctx["note"] = _text(content, "note")
        raw = content.get("items", [])
        items = []
        if isinstance(raw, list):
            for entry in raw:
                if not isinstance(entry, dict):
                    continue
                quote = entry.get("quote", "")
                who = entry.get("who", "")
                if not isinstance(quote, str) or not quote.strip():
                    continue
                items.append({
                    "quote": quote,
                    "who": who if isinstance(who, str) else "",
                })
                if len(items) >= 6:
                    break
        ctx["items"] = items
        ctx["has_items"] = bool(items)
    elif section_type == "offerings" and variant == "categories":
        # 분류 메뉴판 (DESIGN_FIT_PLAN §2). order=True면 담기·주문하기가 준비 중 안내창(#order-soon)으로 간다(D53⑤).
        ctx["label"] = _text(content, "label")
        ctx["order"] = content.get("order") is True
        ctx["categories"] = _menu_categories(content)
        ctx["has_categories"] = bool(ctx["categories"])
        ctx["has_chips"] = len(ctx["categories"]) > 1
    elif section_type == "staff" and variant in ("team", "solo"):
        members = _staff_members(content)
        if not members:
            return None
        ctx["label"] = _text(content, "label")
        href = _clean_url(_text(content, "booking_href"))
        ctx["booking_href"] = href if href.startswith("#") else ""
        ctx["members"] = members
        ctx["member"] = members[0]
        works = [{"src": _clean_url(_text(w, "src")), "alt": _text(w, "alt") or "작업 사진",
                  "example": w.get("image_example") is True}
                 for w in (content.get("works") or []) if isinstance(w, dict)] if variant == "solo" else []
        ctx["works"] = [w for w in works if w["src"]][:6]
        ctx["has_works"] = bool(ctx["works"])
    elif section_type == "booking" and variant == "slots":
        # 예약 현황 + 신청 (D53④): 시안은 예시 현황(days_example), 공개본은 확정 예약으로 계산한 days.
        ctx["site_key"] = site_key
        ctx["retention_days"] = int(retention_days)
        ctx["label"] = _text(content, "label")
        ctx["note"] = _text(content, "note")
        ctx["service_label"] = _text(content, "service_label") or "메뉴"
        services = [{"name": s} for s in (content.get("services") or []) if isinstance(s, str) and s.strip()]
        ctx["services"], ctx["has_services"] = services, bool(services)
        staff = [{"name": s, "index": i} for i, s in enumerate(content.get("staff") or [], start=1)
                 if isinstance(s, str) and s.strip()]
        ctx["staff"], ctx["has_staff"] = staff, len(staff) > 1
        ctx["days"] = _booking_days(content)
        ctx["has_days"] = bool(ctx["days"])
        ctx["days_example"] = content.get("days_example") is True and ctx["has_days"]
    elif section_type == "order" and variant == "soon":
        # 주문 준비 중 안내창 (D53⑤). 스크립트 없이 #order-soon(:target)으로 열린다.
        phone, digits = _phone_pair(content)
        ctx["phone"], ctx["phone_digits"] = (phone, digits) if digits else ("", "")
        ctx["title"] = _text(content, "title") or "온라인 주문은 준비 중이에요"
        ctx["body"] = _text(content, "body") or "지금은 매장에서 주문해 주세요. 곧 여기서 바로 주문할 수 있게 열어 드릴게요."
        back = _text(content, "return_href")
        ctx["return_href"] = back if back.startswith("#") and len(back) > 1 else "#"
    elif section_type == "quickbar" and variant == "float":
        # 편집형 D 고정 빠른 버튼 (새 type, 전화·카톡·예약).
        phone, digits = _phone_pair(content)
        ctx["phone"] = phone
        ctx["phone_digits"] = digits
        ctx["has_phone"] = bool(digits)
        channel = (_text(content, "channel_url") or _text(content, "kakao_channel_url")
                   or _text(content, "kakao"))
        ctx["channel_url"] = _clean_url(channel)
        ctx["has_channel"] = bool(ctx["channel_url"])
        ctx["booking_url"] = _clean_url(_text(content, "booking_url"))
        ctx["has_booking"] = bool(ctx["booking_url"])
        if not (ctx["has_phone"] or ctx["has_channel"] or ctx["has_booking"]):
            return None
    else:  # pragma: no cover - 파일 존재 검사가 먼저 걸러내므로 여기 오지 않음
        raise SiteSpecError(f"매핑할 수 없는 조합: {key}")
    # 편집형 hero 4종 보강: 위 `if section_type == "hero"` 분기가 기본값(_hero_context)을
    # 이미 채웠으므로(기존 분기 그대로 둠), 새 변형별 추가 키만 여기서 덧붙인다.
    if section_type == "hero" and variant == "illustrated":
        # A 빈티지 일러스트형: 짧은 선언문 3~4줄.
        raw_lines = content.get("lines", [])
        lines = []
        if isinstance(raw_lines, list):
            for entry in raw_lines:
                if isinstance(entry, str) and entry.strip():
                    lines.append({"text": entry})
                if len(lines) >= 4:
                    break
        ctx["lines"] = lines
        ctx["has_lines"] = bool(lines)
    elif section_type == "hero" and variant == "story":
        # B 산뜻한 스토리형: 제목 속 핵심어 mark 강조.
        title = _text(content, "title")
        mark = _text(content, "highlight")
        if mark and mark in title:
            head, _, tail = title.partition(mark)
            ctx["title_head"] = head
            ctx["title_mark"] = mark
            ctx["title_tail"] = tail
            ctx["has_mark"] = True
        else:
            ctx["title_head"] = ""
            ctx["title_mark"] = ""
            ctx["title_tail"] = ""
            ctx["has_mark"] = False
    elif section_type == "hero" and variant == "arch":
        # C 로맨틱 에디토리얼: 작은 윗줄 + 세로 영문 라벨.
        ctx["eyebrow"] = _text(content, "eyebrow")
        ctx["label_en"] = _text(content, "label_en")[:40]
    elif section_type == "hero" and variant == "cinematic":
        # D 다크 시네마틱: 윗줄 문구 + 두 번째 버튼.
        ctx["kicker"] = _text(content, "kicker")
        cta2 = content.get("cta2") or {}
        if not isinstance(cta2, dict):
            cta2 = {}
        label2 = cta2.get("label", "") if isinstance(cta2.get("label", ""), str) else ""
        href2 = _clean_url(cta2.get("href", "")) if isinstance(cta2.get("href", ""), str) else ""
        if href2.lower().startswith("tel:"):
            digits2 = _digits(href2[4:])
            href2 = f"tel:{digits2}" if digits2 else ""
        if not label2:
            href2 = ""
        ctx["cta2_label"] = label2
        ctx["cta2_href"] = href2
    return ctx


def _empty_for_public(section_type: str, variant: str, ctx: dict) -> bool:
    """공개 사이트에서 통째로 뺄 빈 부품(방문자에게 [… 입력]만 남는 경우)."""
    if section_type == "intro":
        return not ctx.get("body")
    if section_type == "reviews" and variant == "slot-only":
        return True
    if section_type == "cta":
        # external은 예약 주소가 있어야 버튼이 나온다(전화만 있으면 제목만 남음, 품질 점검 Q-4)
        if variant == "external":
            return not ctx.get("booking_url")
        return not (ctx.get("phone") or ctx.get("booking_url"))
    if section_type == "offerings":
        return not (ctx.get("has_items") or ctx.get("has_categories"))
    if section_type == "contact" and variant == "kakao-channel":
        return not ctx.get("kakao_channel_url")
    if section_type == "around":
        return not (ctx.get("address") or ctx.get("has_items"))
    if section_type == "contact" and variant in ("call-first", "booking-first", "chat-first"):
        # 연락 줄이 모두 빈칸이면 제목만 남으므로 뺀다(9/26 휴대폰 점검)
        return not any(ctx.get(k) for k in ("phone", "hours", "address", "booking_url", "channel_url"))
    return False


def render_site(spec: dict, *, site_key: str = "", retention_days: int = 30,
                title: str = "", kind: str = "other", public: bool = False) -> str:
    """명세를 완전한 HTML 문서 한 장으로 렌더한다 (스크립트 없음).

    kind는 업종 키 10종 중 하나 (모르면 other). 사진이 비었을 때
    대표(hero) 사진 칸과 사진 0장인 사진첩에 업종별 예시 그림을
    인라인 SVG로 넣는다. 사진이 있으면 그림을 쓰지 않는다.

    public=True(공개 사이트): 방문자에게 [… 입력] 빈칸을 보이지 않는다. 빈 부품은 빼고,
    빈 줄은 CSS로 숨기며, 빈 가격은 "가격 문의"로 보인다. 시안(public=False)에서는 사장님이 채울 곳이 보인다.
    """
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
    kind = _normalize_kind(kind)
    rendered_parts = []
    nav = spec.get("navbar")
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
        if public:
            content = _drop_examples(content)
        if public and section_type == "offerings" and isinstance(content.get("items"), list):
            # 이름 없는 항목은 공개본에서 뺀다("가격 문의"만 남은 빈 카드 방지, 품질 점검 Q-5)
            content = {**content, "items": [i for i in content["items"]
                                             if isinstance(i, dict) and str(i.get("name") or "").strip()]}
        ctx = _section_context(
            section_type, variant, str(section_id), content,
            site_key=site_key, retention_days=retention_days,
        )
        if ctx is None:
            continue
        if public and _empty_for_public(section_type, variant, ctx):
            continue
        if ctx.pop("is_example", False):
            rendered_parts.append(_gallery_example_html(str(section_id), variant, kind, ctx.get("label", "")))
            continue
        part = chevron.render(template, _safe(ctx))
        if (section_type == "hero" and variant in _HERO_PHOTO_VARIANTS
                and not ctx.get("image_src")):
            # 사진 없음: 빈 자리 표시를 업종별 예시 그림으로 갈아끼운다.
            # 사진 있음: 그림을 쓰지 않는다.
            part = part.replace(_HERO_EMPTY_MARK, _illustration_block(kind, "hero"), 1)
        rendered_parts.append(part)

    if isinstance(nav, dict):
        # 내비는 섹션 다음에 그린다: 빠진 부품(공개본 빈칸·v3 사진첩)으로 가는 링크를 빼기 위해.
        body_ids = set(re.findall(r'id="([^"]+)"', "".join(rendered_parts)))
        links = [l for l in (nav.get("links") or []) if isinstance(l, dict)
                 and (l.get("href") or "")[1:] in body_ids]
        nctx = _navbar_context({**nav, "links": links})
        if nctx is not None:
            ntemplate = bundle["templates"].get("navbar--main")
            if ntemplate is None:
                raise SiteSpecError("없는 type--variant 조합: navbar--main")
            rendered_parts.insert(0, chevron.render(ntemplate, _safe(nctx)))

    bar = spec.get("actionbar")
    if isinstance(bar, dict):
        # 하단 고정 행동 바 (휴대폰). 내비와 같이 섹션이 아니고, 빠진 섹션으로 가는 버튼은 그리지 않는다.
        body_ids = set(re.findall(r'id="([^"]+)"', "".join(rendered_parts)))
        label, href = _cta_pair(bar.get("primary"))
        label2, href2 = _cta_pair(bar.get("secondary"))
        ok = (lambda h: bool(h) and (not h.startswith("#") or h[1:] in body_ids))
        if label and ok(href):
            rendered_parts.append(chevron.render(bundle["templates"]["actionbar--sticky"], _safe({
                "primary_label": label, "primary_href": href,
                "secondary_label": label2 if ok(href2) else "", "secondary_href": href2 if ok(href2) else ""})))

    page_title = title.strip() if isinstance(title, str) and title.strip() else "가게 홈페이지"
    css2_url = font_pair.get("css2_url") if isinstance(font_pair, dict) else None
    # 본문 글꼴 프리텐다드는 어느 글꼴 짝에서나 쓰므로 항상 불러온다(예전엔 안 불러와 휴대폰 기본 글꼴로 나왔다).
    font_link = f'<link rel="stylesheet" href="{PRETENDARD_CSS}">'
    if isinstance(css2_url, str) and css2_url.startswith("https://"):
        font_link += f'\n<link rel="stylesheet" href="{html.escape(css2_url, quote=True)}">'
    doc = "\n".join([
        "<!doctype html>",
        '<html lang="ko">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">',
        f'<meta name="theme-color" content="{html.escape(palette["ground"], quote=True)}">',
        f"<title>{html.escape(page_title)}</title>",
        font_link,
        "<style>",
        _root_css(palette, font_pair, density, radius),
        bundle["site_css"],
        "</style>",
        "</head>",
        # 공개 사이트에서는 시안용 "예시" 표시도 숨긴다
        '<body class="is-public"><style>.is-public .s-kicker{display:none}</style>' if public else "<body>",
        *rendered_parts,
        "</body>",
        "</html>",
        "",
    ])
    return doc
