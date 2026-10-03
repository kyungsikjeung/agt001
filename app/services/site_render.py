"""시안 렌더러 (작업 R1, C7 핵심).

입력: templates/samples 형식의 디자인 명세 dict
  {version, tokens:{palette,font_pair,density,radius,image_style},
   sections:[{id,type,variant,content}], locked}
출력: 완전한 HTML 문서 한 장 (스크립트 없음, CSP sandbox 전제).

계약 근거:
- templates/README.md (§2 토큰→CSS 변수, §3 부품별 변수, §4 파생값, §5 문의 폼)
- docs/product/SECTION_LIBRARY_SPEC.md (§1 토큰 파생값, §1.5 image_style, §2 부품)
"""
import hashlib
import html
import json
import re
from pathlib import Path
from urllib.parse import quote

import chevron

from app.config import settings
from app.services import components as COMP
from app.services.video_links import parse_video_url


class SiteSpecError(ValueError):
    """명세 검증 실패 (없는 type--variant 조합, 없는 토큰 ID 등)."""


# 허용 URL 앞부분 (href/src로 가는 값 전용, README §4·작업 지시).
# "/uploads/"는 우리 사진 주소 전용 (contracts/ROOM_FEATURES_API.md §4).
# "/art/"는 기본 제공 그림 주소 전용 (templates/art/, 외부 주소 아님).
# 그 외 상대경로는 계속 막는다.
_URL_OK_PREFIXES = ("https://", "tel:", "sms:", "mailto:", "#", "/uploads/", "/art/", "/art-lib/")  # /art-lib/: 태그 사진 창고(ART_LIB)

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
    motion_path = tokens / "motion.json"
    motion = json.loads(motion_path.read_text(encoding="utf-8")) if motion_path.is_file() else {}
    site_css = (base / "site.css").read_text(encoding="utf-8")
    # 2주차 부품 CSS: site.css 뒤에 templates/css/*.css를 이름순으로 이어 붙인다 (C1).
    # 폴더가 없어도 동작한다 (glob 빈 목록 → site.css만).
    css_dir = base / "css"
    if css_dir.is_dir():
        extra = [path.read_text(encoding="utf-8") for path in sorted(css_dir.glob("*.css"))]
        if extra:
            site_css = "\n".join([site_css, *extra])
    built = {
        "templates": templates,
        # 공용 조각 (templates/partials, COMPONENT_ENGINE_PLAN §2). 줄 안에 끼워 쓰므로 끝 줄바꿈 없음.
        "partials": COMP.partials(),
        "partials_path": str(base / "partials"),
        "palettes": palettes,
        "font_pairs": font_pairs,
        "density": density,
        "radius": radius,
        "motion": motion,
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


# 시안에서는 사진마다 붙던 "예시 이미지" 배지를 숨기고 위에 한 줄로 모은다 (디자인 품질 2번:
# 배지가 여기저기 붙어 견본처럼 보였다). 공개본은 D51대로 사진마다 표시를 남긴다.
_DRAFT_NOTE = ('<p class="s-draft-note">사진·지도는 예시예요. 내 가게 사진으로 바꿀 수 있어요.</p>'
               '<style>body:not(.is-public) .s-illu-badge,body:not(.is-public) .s-example--keep{display:none}</style>')

# 보며 고치기 미리보기 (EDIT_WAVE2_CONTRACT §3.3). 구역 뿌리의 data-section-id로만 구역을 알아낸다.
# agt-patch·agt-theme(COMPONENT_ENGINE_PLAN §5): 빌더가 다시 그린 구역 조각만 바꿔 끼우고, 토큰 CSS·스타일 축을
# 갈아 끼운다(새로 불러오지 않아 스크롤이 그대로). 부모 창이 보낸 것만 받는다.
# agt-flash는 빌더가 칩으로 켠 구역으로 눈을 이끄는 1초 반짝임 (BUILDER_CONTRACT §3-4).
_EDIT_STYLE = ('<style>[data-section-id]{cursor:pointer}'
               '[data-section-id]:hover{outline:2px dashed var(--c-primary);outline-offset:-2px}'
               '.agt-flash{outline:2px solid var(--c-primary);outline-offset:-2px;'
               'animation:agt-flash 1s ease}'
               '@keyframes agt-flash{0%{background:color-mix(in srgb,var(--c-primary) 25%,transparent)}'
               '100%{background:transparent}}'
               '@media (prefers-reduced-motion: reduce){.agt-flash{animation:none}}</style>')
_EDIT_SCRIPT = """<script>(function(){try{
document.addEventListener('click',function(e){var t=e.target&&e.target.closest?e.target.closest('[data-section-id]'):null;if(!t){e.preventDefault();return;}var el=e.target;var txt='';try{txt=((el.innerText||el.alt)||'').trim().slice(0,80)}catch(_){}var src='';var idx=-1;try{if(el.tagName==='IMG'){src=el.getAttribute('src')||'';var imgs=t.querySelectorAll('img');for(var i=0;i<imgs.length;i++){if(imgs[i]===el){idx=i;break}}}}catch(_){}var photo=null;try{if(el.tagName!=='IMG'){var f=t.querySelector('img');if(f){photo={src:f.getAttribute('src')||'',index:0}}}}catch(_){}try{parent.postMessage({type:'agt-edit',section:t.getAttribute('data-section-id'),text:txt,img:el.tagName==='IMG',src:src,index:idx,photo:photo},'*')}catch(_){}e.preventDefault();},true);
document.addEventListener('submit',function(e){e.preventDefault();},true);
function sec(id){var all=document.querySelectorAll('[data-section-id]');for(var i=0;i<all.length;i++){if(all[i].getAttribute('data-section-id')===id)return all[i]}return null}
function patch(d){var fresh={};var ps=d.parts||[];for(var i=0;i<ps.length;i++){var p=ps[i];if(!p||typeof p.id!=='string'||typeof p.html!=='string')continue;var t=document.createElement('template');t.innerHTML=p.html;var el=t.content.firstElementChild;if(!el)continue;var old=sec(p.id);if(old){old.replaceWith(el)}fresh[p.id]=el}
if(Array.isArray(d.order)){var cur=[].slice.call(document.querySelectorAll('body > [data-section-id]'));var first=cur[0];if(first){var mark=document.createComment('agt');first.parentNode.insertBefore(mark,first);var by={};for(var j=0;j<cur.length;j++){by[cur[j].getAttribute('data-section-id')]=cur[j];cur[j].remove()}for(var k=0;k<d.order.length;k++){var n=fresh[d.order[k]]||by[d.order[k]];if(n)mark.parentNode.insertBefore(n,mark)}mark.remove()}}
if(d.focus){var f=sec(d.focus);if(f){f.classList.add('agt-flash');setTimeout(function(){f.classList.remove('agt-flash')},1000)}}}
function theme(d){var a=document.getElementById('agt-theme');if(a&&typeof d.css==='string')a.textContent=d.css;var m=document.getElementById('agt-motion');if(m&&typeof d.motion==='string')m.textContent=d.motion;var at=d.attrs||{};var ax=d.axes||[];for(var i=0;i<ax.length;i++){if(typeof at[ax[i]]==='string')document.body.setAttribute(ax[i],at[ax[i]]);else document.body.removeAttribute(ax[i])}}
window.addEventListener('message',function(e){try{if(e.source!==parent)return;var d=e.data;if(!d||typeof d!=='object')return;if(d.type==='agt-patch'){patch(d);return}if(d.type==='agt-theme'){theme(d);return}if(!d.section)return;var q=sec(d.section);if(!q)return;if(d.type==='agt-scroll'){if(q.scrollIntoView)q.scrollIntoView()}else if(d.type==='agt-flash'){q.classList.add('agt-flash');setTimeout(function(){q.classList.remove('agt-flash')},1000)}}catch(_){}});
}catch(e){}})();</script>"""


def _og_tags(sections: list, site_key: str, page_title: str) -> list:
    """카톡·문자에 주소를 붙이면 뜨는 미리보기 (디자인 품질 7번, EDIT_PUBLISH_PLAN §5-1).
    첫 화면 제목·한 줄 소개·사진을 쓴다. 사진 주소는 공개 사이트와 같은 호스트의 절대 주소여야 한다."""
    hero = next((s.get("content") or {} for s in sections
                 if isinstance(s, dict) and s.get("type") == "hero" and isinstance(s.get("content"), dict)), {})
    ctx = _hero_context(hero)
    title = ctx["title"] or page_title
    desc = ctx["subtitle"] or page_title
    tags = [f'<meta property="og:type" content="website">',
            f'<meta property="og:title" content="{html.escape(title, quote=True)}">',
            f'<meta property="og:description" content="{html.escape(desc, quote=True)}">',
            f'<meta name="description" content="{html.escape(desc, quote=True)}">']
    base = f"https://{settings.preview_host}" if settings.preview_host else (settings.public_base_url or "").rstrip("/")
    img = ctx["image_src"]
    if img.startswith("/") and base.startswith("https://"):
        img = base + img
    if img.startswith("https://"):
        tags.append(f'<meta property="og:image" content="{html.escape(img, quote=True)}">')
    if base.startswith("https://") and site_key:
        tags.append(f'<meta property="og:url" content="{html.escape(f"{base}/site/{site_key}/", quote=True)}">')
    return tags


# 하단 탭 아이콘 (선 그림, 24칸). 탭 이름의 낱말로 고른다.
def _is_my_link(href: str) -> bool:
    """내 스탬프 화면 링크 (/api/orders/<키>/my). 구역이 아니라도 내비·탭에 둔다."""
    return isinstance(href, str) and href.startswith("/api/orders/") and href.endswith("/my")


_TAB_ICONS = (
    (("홈",), "M3 11l9-8 9 8M5 10v10h14V10"),
    (("메뉴", "시술", "가격", "요금"), "M4 6h16M4 12h16M4 18h16"),
    (("예약", "신청", "날짜", "상담"), "M4 6h16v14H4zM4 10h16M8 3v4M16 3v4"),
    (("오시는", "길", "위치", "지도"), "M12 21s-7-6.5-7-12a7 7 0 0 1 14 0c0 5.5-7 12-7 12zM12 11a2 2 0 1 0 0-4 2 2 0 0 0 0 4z"),
    (("전화",), "M5 4h4l2 5-3 2a11 11 0 0 0 5 5l2-3 5 2v4a2 2 0 0 1-2 2A17 17 0 0 1 3 6a2 2 0 0 1 2-2z"),
    (("공간", "사진", "스타일", "작품", "객실"), "M4 5h16v14H4zM4 16l5-5 4 4 3-3 4 4"),
    (("수업", "반", "클래스", "시간표"), "M4 5h7v15H4zM13 5h7v15h-7z"),
    (("스탬프", "쿠폰"), "M4 7h16v10H4zM14 7v10"),
)
_TAB_DEFAULT_ICON = "M4 5h16v11H9l-5 4z"  # 말풍선 (문의 등)


def _tab_icon(label: str) -> str:
    for words, path in _TAB_ICONS:
        if any(w in label for w in words):
            return path
    return _TAB_DEFAULT_ICON


def _app_tabs(nav: dict, bar: dict, body_ids: set) -> list:
    """하단 탭: 홈 + 구역 링크 + 주·보조 행동. 최대 5개, 행동이 먼저 자리를 잡고 링크가 남는 칸을 채운다.
    보조(전화 등)도 넣는다: 카페·식당은 주 행동이 길찾기라 빼면 전화 버튼이 사라진다."""
    top = nav.get("top") if isinstance(nav.get("top"), str) and nav.get("top").startswith("#") else "#"
    links = []
    for link in nav.get("links") or []:
        label, href = (link.get("label"), link.get("href")) if isinstance(link, dict) else (None, None)
        if isinstance(label, str) and isinstance(href, str) and (href[1:] in body_ids or _is_my_link(href)):
            links.append((label, href))
    actions = []
    for key in ("primary", "secondary"):
        label, href = _cta_pair(bar.get(key))
        if label and href and href != top and (not href.startswith("#") or href[1:] in body_ids):
            actions.append((label, href))
    act_hrefs = {h for _, h in actions}
    links = [(l, h) for l, h in links if h not in act_hrefs][:4 - len(actions)]
    tabs = [("홈", top), *links, *actions]
    return [{"label": l, "href": h, "icon": _tab_icon(l)} for l, h in tabs] if len(tabs) >= 2 else []


_BELL = ('<svg class="s-notice__bell" viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" focusable="false" '
         'fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
         '<path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/><path d="M10.3 21a1.94 1.94 0 0 0 3.4 0"/></svg>')


def _notice_photos(notice: dict) -> list:
    """공지 사진 주소 (NOTICE_PHOTO_CONTRACT §2): 이 사이트 올린 사진(/uploads/)만, 5장까지."""
    raw = notice.get("photos") if isinstance(notice.get("photos"), list) else []
    return [p for p in raw if isinstance(p, str) and p.startswith("/uploads/")][:5]


def _notice_band(text: str, photos: list, can_open: bool) -> str:
    """공지 띠: 종 아이콘 + (사진이면 첫 장 작은 그림) + 글. 팝업이 있으면 띠 전체가 여는 단추."""
    thumb = (f'<img class="s-notice__thumb" src="{html.escape(photos[0], quote=True)}" alt="" '
             'width="32" height="32" loading="lazy">' if photos else "")
    label = html.escape(text) if text else f"사진 공지 {len(photos)}장"
    inner = f'{_BELL}<span class="s-notice__label">공지</span>{thumb}<span class="s-notice__text">{label}</span>'
    if can_open:
        inner = f'<button type="button" class="s-notice__open" data-popup="open" aria-haspopup="dialog">{inner}</button>'
    return f'<div class="s-notice" role="note">{inner}</div>'


def _notice_popup(text: str, photos: list | None = None, auto_open: bool = True) -> str:
    """공지 팝업 (D56 + 사진 넘기기). 닫기만: 공개 사이트는 CSP sandbox(출처 없음)라 기기 저장소를 못 써
    '오늘 하루 보지 않기'가 저장되지 않는다. 스크립트가 없으면 hidden 그대로라 띠만 보인다."""
    photos = photos or []
    body = f'<p class="s-popup__text">{html.escape(text)}</p>' if text else ""
    if photos:
        items = "".join(f'<li><img src="{html.escape(u, quote=True)}" alt="공지 사진 {i}" loading="lazy"></li>'
                        for i, u in enumerate(photos, start=1))
        body += f'<ul class="s-notice__photos">{items}</ul>'
        if len(photos) > 1:
            body += ('<ol class="s-notice__dots" aria-hidden="true">'
                     + "".join('<li class="on"></li>' if i == 0 else "<li></li>" for i in range(len(photos))) + "</ol>")
    auto = "1" if auto_open else "0"
    return (
        f'<div class="s-popup" id="s-popup" role="dialog" aria-modal="true" aria-labelledby="s-popup-title" '
        f'data-auto="{auto}" hidden>'
        f'<div class="s-popup__panel"><p class="s-popup__kicker" id="s-popup-title">공지</p>{body}'
        '<div class="s-popup__row"><button type="button" data-popup="close">닫기</button></div></div></div>'
        "<script>(function(){var p=document.getElementById('s-popup');if(!p)return;"
        "if(p.getAttribute('data-auto')==='1')p.hidden=false;"
        "document.addEventListener('click',function(e){var t=e.target;"
        "if(t&&t.closest&&t.closest('[data-popup=\"open\"]')){p.hidden=false;return;}"
        "if(t===p||(t&&t.getAttribute&&t.getAttribute('data-popup')==='close'))p.hidden=true;});"
        "var ul=p.querySelector('.s-notice__photos'),d=p.querySelectorAll('.s-notice__dots li');"
        "if(ul&&d.length){ul.addEventListener('scroll',function(){var i=Math.round(ul.scrollLeft/Math.max(1,ul.clientWidth));"
        "for(var k=0;k<d.length;k++)d[k].className=(k===i?'on':'');},{passive:true});}})();</script>"
    )


def _favicon(page_title: str, palette: dict) -> str:
    """탭 아이콘: 가게 이름 첫 글자 (상단 로고와 같은 모양, 디자인 품질 7번)."""
    from urllib.parse import quote
    letter = html.escape((page_title or "·").strip()[:1] or "·")
    color = palette.get("primary") if isinstance(palette.get("primary"), str) else "#222"
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" rx="14" '
           f'fill="{html.escape(color, quote=True)}"/><text x="32" y="44" font-size="36" text-anchor="middle" '
           f'fill="#fff" font-family="sans-serif" font-weight="700">{letter}</text></svg>')
    return f'<link rel="icon" href="data:image/svg+xml,{quote(svg)}">'


def _has_example_art(parts: list) -> bool:
    return any("s-illu-badge" in p or "s-example--keep" in p for p in parts if isinstance(p, str))


def list_variants() -> list:
    """사용 가능한 type--variant 목록 (예: 'hero--photo-overlay')."""
    return sorted(_bundle()["templates"].keys())


def app_link(path: str) -> str:
    """공개 사이트에서 앱 페이지(채팅 등)로 가는 링크.

    공개 사이트는 미리보기 주소에서 열리고, 미리보기 주소는 앱 경로를 열지 않는다(main._split_hosts → 404).
    그래서 앱 주소(PUBLIC_BASE_URL, https)로 절대 주소를 만든다. 주소를 나눴는데 앱 주소를 모르면 빈 글
    (링크를 빼서 404를 막는다). 주소를 나누지 않는 개발 환경은 상대 주소.
    """
    base = (settings.public_base_url or "").strip().rstrip("/")
    if base.startswith("https://"):
        return f"{base}{path}"
    if settings.preview_host:
        return ""
    return path


def _chat_url(content: dict, site_key: str) -> str:
    """예약 채팅 링크 (BOOKING_BOT_IMPL_PLAN CH-1). https 주소이거나 이 가게의 /chat/<key>만 받는다."""
    raw = content.get("chat_url") if isinstance(content, dict) else None
    if not isinstance(raw, str) or not site_key:
        return ""
    raw = raw.strip()
    if raw == f"/chat/{site_key}" or (raw.startswith("https://") and raw.endswith(f"/chat/{site_key}")):
        return raw
    return ""


def _guest_chat_url(site_key: str) -> str:
    """손님 채팅 링크 (GUEST_CHAT_CONTRACT §2의 8). 공개된 가게+켜짐일 때만. 실패해도 렌더는 계속."""
    if not site_key:
        return ""
    try:
        from app.services import guest_chat
        if guest_chat.enabled(site_key):
            return app_link(f"/chat/{site_key}")
    except Exception:
        pass
    return ""


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


def _motion_css(motion) -> str:
    """움직임 토큰 → 등장 애니메이션 시간·곡선 덮어쓰기. 움직임 줄이기 설정이면 끈다."""
    if not isinstance(motion, dict):
        return ""
    try:
        dur, rise, stagger = int(motion["dur"]), int(motion["rise"]), int(motion["stagger"])
    except (KeyError, TypeError, ValueError):
        return ""
    ease = str(motion.get("ease") or "ease-out")
    if not re.fullmatch(r"[a-z\-]+|cubic-bezier\([\d.,\s-]+\)", ease):
        ease = "ease-out"
    return (f":root{{--m-dur:{dur}ms;--m-ease:{ease};--m-rise:{rise}px;--m-stagger:{stagger}ms}}"
            "@keyframes s-rise{from{opacity:0;transform:translateY(var(--m-rise))}to{opacity:1;transform:none}}"
            ".s-hero,section[class^=\"s-\"]{animation-duration:var(--m-dur)!important;"
            "animation-timing-function:var(--m-ease)!important}"
            ".s-btn{transition:transform var(--m-dur) var(--m-ease),box-shadow var(--m-dur) var(--m-ease)}"
            ".s-btn:hover{transform:translateY(-2px)}"
            "@media (prefers-reduced-motion:reduce){.s-hero,section[class^=\"s-\"]{animation:none!important}"
            ".s-btn{transition:none}}")


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


def _cta_fallback(bar, body_ids: set) -> tuple:
    """빠진 구역으로 가는 주 버튼의 차선책 (QA-1: min 쪽 길찾기처럼).

    전화(tel:)가 있으면 전화로, 없으면 문의 양식으로. 둘 다 없으면 ("", "").
    호출자는 빈 값이면 버튼을 그리지 않는다."""
    label2, href2 = _cta_pair((bar or {}).get("secondary") if isinstance(bar, dict) else None)
    if href2.lower().startswith("tel:") and _digits(href2[4:]):
        return (label2 or "전화", href2)
    for cand in sorted(body_ids):
        if cand.startswith("contact-title-"):
            return ("문의하기", f"#{cand}")
    return ("", "")


def _fix_hero_cta(part: str, body_ids: set, fallback: tuple) -> str:
    """첫 화면 버튼 묶음에서 빠진 구역으로 가는 링크를 고친다.

    첫 버튼(주 행동)은 차선책(전화·문의)으로 바꾸고, 둘째부터는 지운다.
    차선책도 없으면 버튼을 빼고, 묶음에 링크가 하나도 없으면 묶음째로 뺀다."""
    def fix_p(m):
        block = m.group(0)
        first = True

        def fix_a(a):
            nonlocal first
            head, target = a.group(1), a.group(2)
            mine = first
            first = False
            if target in body_ids:
                return a.group(0)
            if mine and fallback[1]:
                return (f'<a class="{head}" href="{html.escape(fallback[1], quote=True)}">'
                        f'{html.escape(fallback[0])}</a>')
            return ""

        block = re.sub(r'<a class="([^"]*)" href="#([^"]+)">.*?</a>', fix_a, block, flags=re.S)
        return "" if "<a " not in block else block

    return re.sub(r'<p class="(?:s-hero__cta|s-app-card__cta|ed-cine__cta)[^"]*">.*?</p>',
                  fix_p, part, flags=re.S)


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


def _geo_pair(geo) -> tuple | None:
    """공개 지도 좌표 (MAP_CONTRACT §4). 숫자로 안 읽히면 없음."""
    if not isinstance(geo, dict):
        return None
    try:
        return (float(geo.get("x")), float(geo.get("y")))
    except (TypeError, ValueError):
        return None


def _map_links(address: str, geo: tuple | None = None) -> list:
    """지도 앱 검색 링크 (키 필요 없음, D53②: 지도 그림은 아직 예시).

    좌표가 있으면 카카오맵 크게 보기 깊은 링크 한 개 (MAP_CONTRACT §4).
    """
    if geo is not None:
        x, y = geo
        # 이름에 쉼표가 있으면 링크 형식(이름,위도,경도)이 깨지므로 통째로 인코딩한다
        name = quote(address.strip() or "가게", safe="")
        return [{"label": "카카오맵에서 크게 보기",
                 "href": f"https://map.kakao.com/link/map/{name},{y},{x}"}]
    if not address.strip():
        return []
    q = quote(address.strip())
    return [{"label": "카카오맵", "href": f"https://map.kakao.com/?q={q}"},
            {"label": "네이버 지도", "href": f"https://map.naver.com/p/search/{q}"}]


def _menu_categories(content: dict) -> list:
    """분류 메뉴판: [{name, index, image_*, items:[{name, desc, price, price_example, badge, order_index, orderable}], count}]."""
    raw = content.get("categories")
    cats = []
    n = 0  # 주문 폼 칸 번호 (구역 안에서 0부터 차례로, site_data와 같은 규칙)
    for pos, entry in enumerate(raw if isinstance(raw, list) else [], start=1):
        if not isinstance(entry, dict):
            continue
        items = []
        for it in entry.get("items") if isinstance(entry.get("items"), list) else []:
            if not isinstance(it, dict) or not _text(it, "name").strip():
                continue
            stamped = it.get("order_index")
            if not isinstance(stamped, int) or isinstance(stamped, bool):
                stamped = n
            items.append({"name": _text(it, "name"), "desc": _text(it, "desc"), "price": _text(it, "price"),
                          "price_example": it.get("price_example") is True, "badge": _text(it, "badge")[:8],
                          "example": it.get("example") is True, "order_index": stamped,
                          "orderable": it.get("orderable") is True})
            n += 1
        if not items:
            continue
        name = _text(entry, "name")
        image = _clean_url(_text(entry, "image"))
        cats.append({"name": name, "index": pos, "count": len(items), "items": items,
                     "image_src": image, "image_alt": _text(entry, "image_alt") or f"{name} 사진",
                     "image_example": bool(image and entry.get("image_example"))})
    return cats


_STAFF_MAX = 12  # site_data._STAFF_MAX와 같다


def _staff_members(content: dict, section_id: str = "") -> list:
    """담당자 카드: [{name, role, subject, tagline, bio, initial, specialties, image_*, pos, popover_id, example}] 최대 12명.

    빌더 선생님 고치기 칸(site_data.clean_staff)이 12명까지 저장하므로 같은 상한으로 그린다."""
    raw = content.get("members")
    members = []
    pos = 0
    for entry in (raw if isinstance(raw, list) else [])[:_STAFF_MAX]:
        if not isinstance(entry, dict) or not _text(entry, "name").strip():
            continue
        pos += 1
        name, role = _text(entry, "name").strip(), _text(entry, "role")
        tags = entry.get("specialties")
        tags = [{"text": s} for s in (tags if isinstance(tags, list) else []) if isinstance(s, str) and s.strip()][:4]
        image = _clean_url(_text(entry, "image"))
        members.append({"name": name, "role": role, "subject": _text(entry, "subject"),
                        "tagline": _text(entry, "tagline"), "bio": _text(entry, "bio"), "initial": name[:1],
                        "specialties": tags, "has_specialties": bool(tags),
                        "image_src": image, "image_alt": f"{name} {role} 사진".strip(),
                        "image_example": bool(image and entry.get("image_example")),
                        "pos": pos, "popover_id": f"staff-{section_id}-{pos}",
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


def _class_items(content: dict) -> list:
    """반 카드: [{name, target, level, desc, when, capacity, fee, fee_example, example}] 최대 12개."""
    raw = content.get("classes")
    items = []
    for entry in (raw if isinstance(raw, list) else [])[:12]:
        if not isinstance(entry, dict) or not _text(entry, "name").strip():
            continue
        when = f"{_text(entry, 'days')} {_text(entry, 'time')}".strip()
        items.append({"name": _text(entry, "name"), "target": _text(entry, "target"),
                      "level": _text(entry, "level"), "desc": _text(entry, "desc"),
                      "when": when, "capacity": _text(entry, "capacity"),
                      "fee": _text(entry, "fee"),
                      "fee_example": entry.get("fee_example") is True,
                      "example": entry.get("example") is True})
    return items


def _booking_dates(content: dict) -> list:
    """입실일 현황: [{label, dow, value, key, state, state_label, is_full}] 최대 21일."""
    raw = content.get("days")
    days = []
    for entry in (raw if isinstance(raw, list) else [])[:21]:
        if not isinstance(entry, dict) or not _SLOT_VALUE.match(_text(entry, "date")):
            continue
        date = _text(entry, "date")
        state = entry.get("state") if entry.get("state") in _SLOT_STATES else "open"
        days.append({"label": _text(entry, "label") or date[5:].replace("-", "/"),
                     "dow": _text(entry, "dow"), "value": date,
                     "key": date.replace("-", ""), "state": state,
                     "state_label": _SLOT_STATES[state], "is_full": state == "full"})
    return days


def _nights_max(content: dict) -> int:
    """박 수 상한: 1~14 정수만, 아니면 기본 3."""
    raw = content.get("nights_max", 3)
    if isinstance(raw, bool):
        return 3
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return 3
    return value if 1 <= value <= 14 else 3


def _room_items(content: dict) -> list:
    """객실 카드: [{name, image_*, capacity, size, price, price_example, features,
    prices([{label, period, price, from, to, dow, is_current}]), has_prices, example}] 최대 8개."""
    raw = content.get("rooms")
    rooms = []
    for entry in (raw if isinstance(raw, list) else [])[:8]:
        if not isinstance(entry, dict) or not _text(entry, "name").strip():
            continue
        name = _text(entry, "name").strip()
        image = _clean_url(_text(entry, "image"))
        tags = entry.get("features")
        tags = [{"text": s} for s in (tags if isinstance(tags, list) else []) if isinstance(s, str) and s.strip()][:6]
        prices = []
        for found in (entry.get("prices") if isinstance(entry.get("prices"), list) else [])[:8]:
            if not isinstance(found, dict):
                continue
            prices.append({"label": _text(found, "label"), "period": _text(found, "period"),
                           "price": _text(found, "price"), "from": _text(found, "from"),
                           "to": _text(found, "to"), "dow": _text(found, "dow"),
                           "is_current": found.get("is_current") is True})
        rooms.append({"name": name, "capacity": _text(entry, "capacity"), "size": _text(entry, "size"),
                      "price": _text(entry, "price"), "price_example": entry.get("price_example") is True,
                      "image_src": image, "image_alt": _text(entry, "image_alt") or f"{name} 사진",
                      "image_example": bool(image and entry.get("image_example")),
                      "image_ai": bool(image and entry.get("image_ai")),
                      "prices": prices, "has_prices": bool(prices),
                      "features": tags, "has_features": bool(tags),
                      "example": entry.get("example") is True})
    return rooms


# 공개본 객실 요금표 다시 계산 (BETA_FLOW §2.5: 방문자 Asia/Seoul 날짜 기준, 20줄 안).
_SEASON_SCRIPT = """<script>
(()=>{try{
const n=new Date(new Date().toLocaleString("en-US",{timeZone:"Asia/Seoul"}));
const md=(n.getMonth()+1)*100+n.getDate(),dw=String(n.getDay());
const P={"극성수기":0,"성수기":1,"준성수기":2,"비수기":3,"주중":4,"주말":5,"":6};
const N=s=>{const m=/(\\d+)-(\\d+)/.exec(s||"");return m?+m[1]*100+ +m[2]:0};
const IN=(f,t)=>!!f&&!!t&&(f<=t?md>=f&&md<=t:md>=f||md<=t);
document.querySelectorAll("table.s-room__prices").forEach(t=>{
const rs=Array.from(t.querySelectorAll("tbody tr"));
const hit=rs.filter(r=>IN(N(r.dataset.from),N(r.dataset.to))).sort((a,b)=>(P[a.dataset.label]??9)-(P[b.dataset.label]??9))[0]||rs.find(r=>r.dataset.label==="비수기")||rs.find(r=>(r.dataset.dow||"").split(",").includes(dw));
rs.forEach(r=>{const on=r===hit;r.classList.toggle("is-current",on);let b=r.querySelector(".s-price-now");if(on&&!b)r.cells[2].insertAdjacentHTML("beforeend",' <span class="s-price-now">지금 적용</span>');if(!on&&b)b.remove()})});
}catch(e){}})();
</script>"""


# 초대·기념 부품 (청첩장 등): 남은 날(D-day)은 방문자 한국 날짜로, 계좌 복사는 클립보드가 될 때만 단추를 보인다.
_EVENT_SCRIPT = """<script>
(()=>{try{
const n=new Date(new Date().toLocaleString("en-US",{timeZone:"Asia/Seoul"}));n.setHours(0,0,0,0);
document.querySelectorAll("[data-dday]").forEach(p=>{const m=/^(\\d{4})-(\\d{2})-(\\d{2})$/.exec(p.dataset.dday||"");if(!m)return;
const d=Math.round((new Date(+m[1],m[2]-1,+m[3])-n)/864e5);if(d<0)return;p.textContent=d===0?"바로 오늘이에요":"D-"+d+" · "+d+"일 남았어요";p.hidden=false});
if(navigator.clipboard)document.querySelectorAll("[data-copy]").forEach(b=>{b.hidden=false;b.addEventListener("click",()=>{
navigator.clipboard.writeText(b.dataset.copy).then(()=>{b.textContent="복사됨";setTimeout(()=>{b.textContent="복사"},1500)},()=>{})})});
}catch(e){}})();
</script>"""

_WEEKDAYS = ("월", "화", "수", "목", "금", "토", "일")


def _event_date_context(content: dict) -> dict:
    """예식 날짜 (event--date): YYYY-MM-DD를 읽어 날짜 글·그달 달력(일요일 시작)·D-day 표지를 만든다. 틀린 날짜는 빈칸."""
    import calendar
    import datetime
    raw = _text(content, "date").strip()
    try:
        day = datetime.date.fromisoformat(raw)
    except ValueError:
        return {"has_date": False}
    weeks = []
    for week in calendar.Calendar(firstweekday=6).monthdayscalendar(day.year, day.month):
        weeks.append({"days": [{"n": n or "", "on": n == day.day,
                                "cls": "s-sun" if i == 0 else ("s-sat" if i == 6 else "")} for i, n in enumerate(week)]})
    return {
        "has_date": True, "iso": day.isoformat(),
        "date_text": f"{day.year}년 {day.month}월 {day.day}일 {_WEEKDAYS[day.weekday()]}요일",
        "time": _text(content, "time").strip(), "venue": _text(content, "venue").strip(),
        "month_label": f"{day.year}년 {day.month}월",
        "weekdays": [{"label": w, "cls": "s-sun" if w == "일" else ("s-sat" if w == "토" else "")}
                     for w in ("일", "월", "화", "수", "목", "금", "토")],
        "weeks": weeks,
    }


def _event_sides(content: dict, key: str, build) -> list:
    """양가 묶음 [{side, <key>: [...]}]: 최대 2묶음 × 4명. 이름 빈 사람·빈 묶음은 뺀다."""
    out = []
    for entry in (content.get("sides") if isinstance(content.get("sides"), list) else [])[:2]:
        if not isinstance(entry, dict) or not _text(entry, "side").strip():
            continue
        raw = entry.get(key) if isinstance(entry.get(key), list) else []
        items = [item for item in (build(e) for e in raw[:4] if isinstance(e, dict)) if item]
        if items:
            out.append({"side": _text(entry, "side").strip(), key: items})
    return out


def _family_person(entry: dict) -> dict | None:
    """연락처 한 사람: 맞는 전화번호일 때만 전화·문자 단추(digits)."""
    from app.services.validate import check_phone
    name = _text(entry, "name").strip()
    if not name:
        return None
    phone = _text(entry, "phone")
    return {"role": _text(entry, "role").strip(), "name": name,
            "digits": _digits(phone) if phone.strip() and check_phone(phone) is None else ""}


def _gift_account(entry: dict) -> dict | None:
    """계좌 한 줄: 번호는 숫자·하이픈만, 숫자 6~20자리. 주민등록번호 모양은 받지 않는다."""
    from app.services import validate as V
    holder, bank = _text(entry, "holder").strip(), _text(entry, "bank").strip()
    number = re.sub(r"[^0-9-]", "", _text(entry, "number")).strip("-")
    digits = re.sub(r"\D", "", number)
    if not holder or not bank or not 6 <= len(digits) <= 20:
        return None
    if V._RRN_HYPHEN_RE.search(number) or V._RRN_PLAIN_RE.search(digits):
        return None
    return {"role": _text(entry, "role").strip(), "holder": holder, "bank": bank, "number": number}


def _timetable_rows(content: dict, days: list) -> list:
    """시간표 행: [{time, cells:[{text}]}] 최대 12행. cells는 days 순서에 맞춘다."""
    raw = content.get("rows")
    rows = []
    for entry in (raw if isinstance(raw, list) else [])[:12]:
        if not isinstance(entry, dict) or not _text(entry, "time").strip():
            continue
        by_day = {}
        cells = entry.get("cells")
        if isinstance(cells, list):
            for cell in cells:
                if not isinstance(cell, dict):
                    continue
                day, text = _text(cell, "day"), _text(cell, "text")
                if day and isinstance(text, str) and day not in by_day:
                    by_day[day] = text
        rows.append({"time": _text(entry, "time"),
                     "cells": [{"text": by_day.get(day, "")} for day in days]})
    return rows


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
            one["image_ai"] = entry.get("image_ai") is True
            one["image_example"] = bool(one["image_src"]) and entry.get("image_example") is True  # D51 ③
            one["image_off"] = not one["image_src"] and entry.get("image_off") is True  # 사진 없음: 빈 칸도 안 그린다
        if with_index:
            one["index"] = pos
        # 확장 칸 (COMPOSE_INTERVIEW_CONTRACT §10): 항목 고유 이름·가격 숫자·행동 단추. 나중에 주문·결제·후기를 이 항목에 붙인다.
        item_id = entry.get("item_id", "")
        one["item_id"] = item_id if isinstance(item_id, str) and re.fullmatch(r"i-[0-9a-f]{6,16}", item_id) else ""
        won = entry.get("price_won")
        one["price_won"] = won if isinstance(won, int) and not isinstance(won, bool) and 0 < won < 100_000_000 else ""
        act = entry.get("action")
        if (isinstance(act, dict) and act.get("kind") in ("order", "book", "inquire")
                and isinstance(act.get("label"), str) and act["label"].strip()):
            href = _clean_url(act.get("href", ""))
            one["action"] = {"kind": act["kind"], "label": act["label"][:12], "href": href} if href else None
        else:
            one["action"] = None
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
    if section_type == "contact":
        # 손님 채팅 링크 (GUEST_CHAT_CONTRACT §2의 8): 모든 연락 부품에 단추 하나.
        url = _guest_chat_url(site_key)
        if url:
            ctx["guest_chat_url"] = url
    if section_type == "hero":
        ctx.update(_hero_context(content))
    elif section_type == "intro" and variant in ("short", "quote"):  # quote: 같은 글을 큰 인용문으로
        ctx["body"] = _text(content, "body")
        ctx["label"] = _text(content, "label")  # 비면 "소개" (청첩장은 "인사말")
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
    elif section_type == "offerings" and variant in ("list-price", "compact"):  # compact: 같은 목록을 메뉴판으로
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
            geo = _geo_pair(content.get("geo"))  # site_data가 location_geo에서 채운 좌표
            if geo is not None:
                ctx["has_geo"] = True
                ctx["geo_x"], ctx["geo_y"] = (str(geo[0]), str(geo[1]))
                ctx["map_key"] = settings.kakao_js_key
                ctx["links"] = _map_links(ctx["address"], geo)
            else:
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
        ctx["chat_url"] = _chat_url(content, site_key)
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
        ctx["scroll"] = len(items) >= 2
        ctx["count"] = len(items)
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
        # 포장 주문 폼 (PAY_WAVE3 §3.4): content의 order_form(action)만 그대로 넘긴다.
        form = content.get("order_form")
        if isinstance(form, dict) and isinstance(form.get("action"), str) and form["action"].startswith("/api/orders/"):
            ctx["order_form"] = {"action": form["action"]}
    elif section_type == "staff" and variant in ("team", "solo", "cards"):
        members = _staff_members(content, str(section_id))
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
        ctx["chat_url"] = _chat_url(content, site_key)
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
    elif section_type == "event" and variant == "date":
        # 초대·기념: 예식 날짜·시간·장소 + 그달 달력 + D-day (청첩장)
        ctx["label"] = _text(content, "label")
        ctx.update(_event_date_context(content))
        ctx["example"] = content.get("example") is True
    elif section_type == "family" and variant == "contacts":
        # 초대·기념: 신랑측·신부측 연락처, 사람마다 전화·문자
        ctx["label"] = _text(content, "label")
        ctx["sides"] = _event_sides(content, "people", _family_person)
        ctx["has_sides"] = bool(ctx["sides"])
        ctx["example"] = content.get("example") is True
    elif section_type == "guestbook" and variant == "list":
        # 초대·기념: 방명록. 공개본은 자리 표시(MARK)만 두고, 보낼 때 최신 글을 끼운다(guestbook.inject)
        ctx["site_key"] = site_key
        ctx["label"] = _text(content, "label")
    elif section_type == "rsvp" and variant == "form":
        # 초대·기념: 참석 여부 받기(문의 저장소로, /api/rsvp/). 측은 신랑측·신부측만
        ctx["site_key"] = site_key
        ctx["retention_days"] = int(retention_days)
        ctx["label"] = _text(content, "label")
        sides = [s for s in (content.get("sides") or []) if s in ("신랑측", "신부측")][:2]
        ctx["sides"], ctx["has_sides"] = [{"side": s} for s in sides], bool(sides)
    elif section_type == "gift" and variant == "accounts":
        # 초대·기념: 마음 전하실 곳(양가 계좌, 측마다 접기·복사)
        ctx["label"] = _text(content, "label")
        ctx["note"] = _text(content, "note").strip()
        ctx["sides"] = _event_sides(content, "accounts", _gift_account)
        ctx["has_sides"] = bool(ctx["sides"])
        ctx["example"] = content.get("example") is True
    elif section_type == "classes" and variant == "cards":
        # 학원 반 카드 (C1): 상담 신청 주소는 #만.
        ctx["label"] = _text(content, "label")
        href = _clean_url(_text(content, "cta_href"))
        ctx["cta_href"] = href if href.startswith("#") else ""
        ctx["classes"] = _class_items(content)
        ctx["has_classes"] = bool(ctx["classes"])
    elif section_type == "timetable" and variant == "week":
        # 학원 시간표 (C1): <table> + <caption> 필수.
        ctx["label"] = _text(content, "label")
        days = [d for d in (content.get("days") or []) if isinstance(d, str) and d.strip()][:7]
        ctx["days"] = [{"label": day} for day in days]
        ctx["rows"] = _timetable_rows(content, days)
        ctx["has_rows"] = bool(ctx["rows"])
        ctx["example"] = content.get("example") is True
    elif section_type == "rooms" and variant == "cards":
        # 펜션 객실 카드 (C1): 예약 주소는 #만.
        ctx["label"] = _text(content, "label")
        href = _clean_url(_text(content, "booking_href"))
        ctx["booking_href"] = href if href.startswith("#") else ""
        rooms = _room_items(content)
        ctx["rooms"] = rooms
        ctx["has_rooms"] = bool(rooms)
        ctx["scroll"] = len(rooms) >= 2
        ctx["count"] = len(rooms)
        ctx["has_prices"] = any(r.get("has_prices") for r in rooms)
    elif section_type == "booking" and variant == "dates":
        ctx["chat_url"] = _chat_url(content, site_key)
        # 펜션 입실일 + 객실 + 박 수 (C1): 입실일은 date로, 객실은 service로, 박 수는 nights로 보낸다.
        ctx["site_key"] = site_key
        ctx["retention_days"] = int(retention_days)
        ctx["label"] = _text(content, "label")
        ctx["note"] = _text(content, "note")
        rooms = [{"name": s} for s in (content.get("rooms") or []) if isinstance(s, str) and s.strip()]
        ctx["rooms"], ctx["has_rooms"] = rooms, bool(rooms)
        ctx["nights_max"] = _nights_max(content)
        ctx["days"] = _booking_dates(content)
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
    elif section_type == "hero" and variant == "video":
        # 영상 표지형: 영상 주소(지원 주소만)와 썸네일. 썸네일이 없으면 첫 화면 사진을 그대로 쓴다.
        info = parse_video_url(content.get("video_url", "")) if isinstance(content.get("video_url"), str) else None
        ctx["video_href"] = info["url"] if info else ""
        # 유튜브면 소리 없는 반복 배경 영상 틀 (YOUTUBE_EMBED_POLICY). 썸네일은 그 아래 깔려 막히면 그대로 보인다.
        from app.services import youtube_embed
        ctx["yt_id"] = youtube_embed.video_id(info)
        if info and info.get("thumb"):
            ctx["image_src"] = info["thumb"]
            ctx["image_alt"] = "영상 썸네일"
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
    if section_type == "classes":
        return not ctx.get("has_classes")
    if section_type == "timetable":
        # 예시 시간표는 값이 전부 예시이므로 공개본에서 뺀다.
        return not ctx.get("has_rows") or bool(ctx.get("example"))
    if section_type == "rooms":
        return not ctx.get("has_rooms")
    if section_type == "event":
        # 예시 날짜는 지어낸 값이라 공개본에서 뺀다(D26).
        return not ctx.get("has_date") or bool(ctx.get("example"))
    if section_type in ("family", "gift"):
        return not ctx.get("has_sides") or bool(ctx.get("example"))
    return False


def _apply_tone(part: str, section: dict) -> str:
    """tone이 inverse면 섹션 뿌리 요소의 첫 여는 태그에 data-tone을 붙인다 (C1)."""
    if not isinstance(section, dict) or section.get("tone") != "inverse":
        return part
    start = part.find("<")
    if start < 0:
        return part
    end = part.find(">", start)
    if end < 0 or "data-tone" in part[start:end]:
        return part
    return part[:end] + ' data-tone="inverse"' + part[end:]


def render_site(spec: dict, *, site_key: str = "", retention_days: int = 30,
                title: str = "", kind: str = "other", public: bool = False,
                edit: bool = False) -> str:
    """명세를 완전한 HTML 문서 한 장으로 렌더한다 (render_page의 html).

    kind는 업종 키 10종 중 하나 (모르면 other). 사진이 비었을 때
    대표(hero) 사진 칸과 사진 0장인 사진첩에 업종별 예시 그림을
    인라인 SVG로 넣는다. 사진이 있으면 그림을 쓰지 않는다.

    public=True(공개 사이트): 방문자에게 [… 입력] 빈칸을 보이지 않는다. 빈 부품은 빼고,
    빈 줄은 CSS로 숨기며, 빈 가격은 "가격 문의"로 보인다. 시안(public=False)에서는 사장님이 채울 곳이 보인다.
    공개본에만 객실 요금표 다시 계산용 인라인 스크립트 하나를 넣는다 (BETA_FLOW §2.5).
    edit=True(보며 고치기 미리보기): 구역 누름 알림 스크립트와 data-edit-mode를 넣는다. public과 함께 못 쓴다.
    """
    return render_page(spec, site_key=site_key, retention_days=retention_days, title=title,
                       kind=kind, public=public, edit=edit)["html"]


def _part_hash(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]


def render_page(spec: dict, *, site_key: str = "", retention_days: int = 30,
                title: str = "", kind: str = "other", public: bool = False,
                edit: bool = False) -> dict:
    """render_site와 같은 문서 + 실시간 미리보기용 조각 (COMPONENT_ENGINE_PLAN §4).

    돌려주는 것:
      html   완전한 문서 (render_site가 돌려주는 것과 같다)
      parts  [{key, html, hash, section}] 문서 몸통 조각을 그린 순서대로. 구역은 key = 구역 id(section=True),
             나머지는 "@nav"·"@notice"·"@actionbar"처럼 @로 시작한다
      order  그린 구역 id 순서
      theme  {css, motion, attrs}: 편집 미리보기가 다시 그리지 않고 바꿔 끼울 토큰 CSS·<body> 스타일 축 속성
      shell  구역·토큰을 뺀 나머지(머리·내비·행동 바·스크립트)의 해시. 같으면 구역만 바꿔 끼워도 된다
    """
    if edit and public:
        raise ValueError("edit와 public은 함께 쓸 수 없음")
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
    # 움직임 토큰(선택, COMPOSE_INTERVIEW_CONTRACT §6): 분위기마다 등장 속도·곡선·높이를 맞춘다. 없으면 기존 그대로.
    motion = (bundle.get("motion") or {}).get(tokens.get("motion")) if tokens.get("motion") else None
    partials = bundle["partials"]

    def _render(template: str, ctx: dict) -> str:
        return chevron.render(template, _safe(ctx), partials_dict=partials, partials_path=bundle["partials_path"])

    sections = spec.get("sections", [])
    if not isinstance(sections, list):
        raise SiteSpecError("sections가 목록 형태가 아님")
    kind = _normalize_kind(kind)
    # (key, html) 조각. 구역은 key = 구역 id, 그 밖은 "@…"
    parts: list = []
    need_season_script = False
    need_event_script = False
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
        if public and section_type == "rooms" and variant == "cards" and ctx.get("has_prices"):
            need_season_script = True
        if public and _empty_for_public(section_type, variant, ctx):
            continue
        if section_type == "event" and ctx.get("has_date") or section_type == "gift" and ctx.get("has_sides"):
            need_event_script = True
        if ctx.pop("is_example", False):
            parts.append((str(section_id), _apply_tone(
                _gallery_example_html(str(section_id), variant, kind, ctx.get("label", "")), section)))
            continue
        if section_type == "guestbook":
            ctx["public"] = public
        # 공용 제목 조각 {{> label}}의 기본 제목은 등록표에서 (components.json)
        ctx.setdefault("label_default", COMP.label_default(key))
        part = _render(template, ctx)
        if not public and "data-yt-bg" in part:
            # 유튜브 배경 틀은 공개 사이트에서만 (YOUTUBE_EMBED_POLICY). 시안·미리보기는 격리돼 재생이 안 되니 썸네일만 둔다.
            from app.services import youtube_embed
            part = youtube_embed.strip_allowed(part)
        if (section_type == "hero" and variant in _HERO_PHOTO_VARIANTS
                and not ctx.get("image_src")):
            # 사진 없음: 빈 자리 표시를 업종별 예시 그림으로 갈아끼운다.
            # 사진 있음: 그림을 쓰지 않는다.
            part = part.replace(_HERO_EMPTY_MARK, _illustration_block(kind, "hero"), 1)
        parts.append((str(section_id), _apply_tone(part, section)))
    section_keys = [k for k, _ in parts]

    def _body() -> str:
        return "".join(h for _, h in parts)

    # 첫 화면 버튼·내비 CTA도 빠진 섹션(공개본에서 빠진 빈 구역)을 가리키면
    # 차선책(전화·문의)으로 바꾸고, 없으면 그리지 않는다 (QA-1: min 쪽 길찾기).
    bar = spec.get("actionbar")
    ids = set(re.findall(r'id="([^"]+)"', _body()))
    fallback = _cta_fallback(bar if isinstance(bar, dict) else {}, ids)
    parts = [(k, _fix_hero_cta(h, ids, fallback)) for k, h in parts]
    parts = [(k, re.sub(r'<a class="s-hero__link" href="#([^"]+)">.*?</a>',
                        lambda m: m.group(0) if m.group(1) in ids else "", h)) for k, h in parts]

    if isinstance(nav, dict):
        # 내비는 섹션 다음에 그린다: 빠진 부품(공개본 빈칸·v3 사진첩)으로 가는 링크를 빼기 위해.
        body_ids = set(re.findall(r'id="([^"]+)"', _body()))
        links = [l for l in (nav.get("links") or []) if isinstance(l, dict)
                 and ((l.get("href") or "")[1:] in body_ids or _is_my_link(l.get("href") or ""))]
        nav_fixed = {**nav, "links": links}
        cta = nav_fixed.get("cta") if isinstance(nav_fixed.get("cta"), dict) else {}
        href = cta.get("href") if isinstance(cta.get("href"), str) else ""
        if href.startswith("#") and href[1:] not in body_ids:
            if fallback[1]:
                nav_fixed["cta"] = {"label": fallback[0], "href": fallback[1]}
            else:
                nav_fixed.pop("cta", None)
        nctx = _navbar_context(nav_fixed)
        if nctx is not None:
            ntemplate = bundle["templates"].get("navbar--main")
            if ntemplate is None:
                raise SiteSpecError("없는 type--variant 조합: navbar--main")
            parts.insert(0, ("@nav", _render(ntemplate, nctx)))

    notice = spec.get("notice") if isinstance(spec.get("notice"), dict) else {}
    notice_text = (notice.get("text") if isinstance(notice.get("text"), str) else "").strip()
    notice_photos = _notice_photos(notice)
    if notice_text or notice_photos:
        # 공지 띠는 맨 위(내비 다음). 팝업은 사진이 있거나 켰을 때만(편집 미리보기는 없음),
        # 켰으면 들어올 때 한 번 열고, 사진만 있으면 띠를 누를 때 연다. 스크립트가 없으면 띠만 보인다.
        with_popup = (notice.get("popup") is True or bool(notice_photos)) and not edit
        at = 1 if parts and parts[0][1].lstrip().startswith('<nav class="s-navbar"') else 0
        parts.insert(at, ("@notice", _notice_band(notice_text, notice_photos, with_popup)))
        if with_popup:
            parts.append(("@notice-popup", _notice_popup(notice_text, notice_photos,
                                                          auto_open=notice.get("popup") is True)))
    app_layout = spec.get("layout") == "app"
    bar = spec.get("actionbar")
    if app_layout:
        # 앱형 (D56 ①): 아래 행동 바 대신 하단 탭. 탭 = 홈 + 내비 링크(최대 3) + 주 행동.
        body_ids = set(re.findall(r'id="([^"]+)"', _body()))
        tabs = _app_tabs(nav if isinstance(nav, dict) else {}, bar if isinstance(bar, dict) else {}, body_ids)
        if tabs:
            parts.append(("@tabbar", _render(bundle["templates"]["tabbar--app"], {"tabs": tabs})))
    elif isinstance(bar, dict):
        # 하단 고정 행동 바 (휴대폰). 내비와 같이 섹션이 아니고, 빠진 섹션으로 가는 버튼은 그리지 않는다.
        body_ids = set(re.findall(r'id="([^"]+)"', _body()))
        label, href = _cta_pair(bar.get("primary"))
        label2, href2 = _cta_pair(bar.get("secondary"))
        ok = (lambda h: bool(h) and (not h.startswith("#") or h[1:] in body_ids))
        if not (label and ok(href)):
            # 주 버튼 구역이 빠졌으면(주소 없는 가게·빌더에서 숨긴 '오시는 길') 전화→문의로 올린다.
            # 전엔 행동 바가 통째로 빠져 공개 사이트에 전화 링크가 하나도 없을 수 있었다.
            label, href = _cta_fallback(bar, body_ids)
            if href == href2:
                label2, href2 = "", ""
        if label and ok(href):
            parts.append(("@actionbar", _render(bundle["templates"]["actionbar--sticky"], {
                "primary_label": label, "primary_href": href,
                "secondary_label": label2 if ok(href2) else "", "secondary_href": href2 if ok(href2) else ""})))

    page_title = title.strip() if isinstance(title, str) and title.strip() else "가게 홈페이지"
    css2_url = font_pair.get("css2_url") if isinstance(font_pair, dict) else None
    # 본문 글꼴 프리텐다드는 어느 글꼴 짝에서나 쓰므로 항상 불러온다(예전엔 안 불러와 휴대폰 기본 글꼴로 나왔다).
    font_link = f'<link rel="stylesheet" href="{PRETENDARD_CSS}">'
    if isinstance(css2_url, str) and css2_url.startswith("https://"):
        font_link += f'\n<link rel="stylesheet" href="{html.escape(css2_url, quote=True)}">'
    if public and need_season_script:
        parts.append(("@season", _SEASON_SCRIPT))
    if need_event_script and not edit:
        # 편집 미리보기는 누름을 고치기로 받으므로 복사·D-day 스크립트를 넣지 않는다.
        parts.append(("@event", _EVENT_SCRIPT))
    if edit:
        # 공지 팝업은 편집을 가리므로 빼고(띠는 둔다), relay는 </body> 바로 앞.
        parts.append(("@edit-style", _EDIT_STYLE))
        parts.append(("@edit-script", _EDIT_SCRIPT))
    # 스타일 축(surface·heading): 기본값이면 속성을 달지 않는다 → 지금 출력과 같다.
    attrs = COMP.body_attrs(tokens)
    attr_text = "".join(f' {name}="{html.escape(value, quote=True)}"' for name, value in attrs.items())
    # 공개 사이트에서는 시안용 "예시" 표시도 숨긴다. edit는 테스트용 표지로 data-edit-mode를 단다.
    if edit:
        body_open = (f"<body{attr_text} data-edit-mode>" if not app_layout
                     else f'<body{attr_text} data-edit-mode class="is-app">')
    elif public:
        body_open = ('<body{} class="is-public{}"><style>.is-public .s-kicker{{display:none}}</style>').format(
            attr_text, " is-app" if app_layout else "")
    else:
        body_open = f"<body{attr_text}>" if not app_layout else f'<body{attr_text} class="is-app">'
    root_css = _root_css(palette, font_pair, density, radius)
    motion_css = _motion_css(motion)
    if edit:
        # 편집 미리보기는 토큰 CSS를 따로 두어 빌더가 다시 그리지 않고 바꿔 끼운다(agt-theme). 순서·내용은 같다.
        style_block = [f'<style id="agt-theme">{root_css}</style>', "<style>", bundle["site_css"], "</style>",
                       f'<style id="agt-motion">{motion_css}</style>']
    else:
        style_block = ["<style>", root_css, bundle["site_css"], motion_css, "</style>"]
    meta_theme = f'<meta name="theme-color" content="{html.escape(palette["ground"], quote=True)}">'
    favicon = _favicon(page_title, palette)
    head = [
        "<!doctype html>",
        '<html lang="ko">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">',
        meta_theme,
        f"<title>{html.escape(page_title)}</title>",
        *(_og_tags(sections, site_key, page_title) if public else []),
        favicon,
        font_link,
    ]
    draft_note = [_DRAFT_NOTE] if not public and _has_example_art([h for _, h in parts]) else []
    doc = "\n".join([
        *head,
        *style_block,
        "</head>",
        body_open,
        *draft_note,
        *[h for _, h in parts],
        "</body>",
        "</html>",
        "",
    ])
    in_body = set(section_keys)
    # 구역·토큰을 뺀 뼈대: 같으면 미리보기는 구역 조각만 바꿔 끼우면 된다.
    # theme-color·파비콘은 색 토큰을 따르므로 뼈대에서 뺀다(미리보기에서는 보이지 않는다).
    shell_src = "\n".join([*[x for x in head if x not in (meta_theme, favicon)], bundle["site_css"],
                           body_open.replace(attr_text, "") if attr_text else body_open,
                           *draft_note, *[("<!--part-->" if k in in_body else h) for k, h in parts]])
    return {
        "html": doc,
        "parts": [{"key": k, "html": h, "hash": _part_hash(h), "section": k in in_body} for k, h in parts],
        "order": [k for k, _ in parts if k in in_body],
        "theme": {"css": root_css, "motion": motion_css, "attrs": attrs,
                  "axes": [f"data-{axis}" for axis in COMP.style_axes()]},
        "shell": _part_hash(shell_src),
    }
