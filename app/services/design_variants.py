"""요구사항 카드 → 시안 3안 명세 (C7, 해커톤 요구 7, DESIGN_PIPELINE_PLAN.md).

AI가 화면을 새로 짜지 않는다: 업종 기본 조합(templates/samples)에서 출발해 부품 변형과 토큰만 바꾼 3안을 만든다.
가게 사실(이름·전화·주소·시간·가격)은 사장님이 직접 말한 값(FILLED)만 넣고, 나머지는 자리 표시로 둔다(D23·D26).
"""
import copy
import json
from functools import lru_cache
from pathlib import Path
from typing import Optional

from app.config import settings
from app.services import design_concept as DC
from app.services import intake
from app.services import layout_edits as LE
from app.services import prd_engine as E
from app.services import prd_schema as S

# 종류별 출발 샘플. 가게 6업종은 같은 이름의 샘플, 나머지는 구성이 가장 가까운 것.
_SAMPLE_FOR = {"individual": "workshop", "group": "academy", "webservice": "cafe", "other": "cafe"}

# photo-first: 사장님 사진·AI 예시가 없을 때 시안 첫 화면·사진첩에 넣을 기본 그림.
# /art/는 기본 제공 그림 전용 주소(site_render._URL_OK_PREFIXES 허용, 외부 호출 없음).
# 파일 3종을 업종 분위기에 맞게 매핑한다. SVG 예시 그림보다 항상 먼저 쓴다.
_ART_FILES = ("cafe-engraving", "academy-glass", "pension-example")
_DEFAULT_ART = {
    "cafe": "cafe-engraving", "restaurant": "cafe-engraving",
    "webservice": "cafe-engraving", "other": "cafe-engraving",
    "academy": "academy-glass", "salon": "academy-glass",
    "individual": "academy-glass", "group": "academy-glass",
    "pension": "pension-example", "workshop": "pension-example",
}
_EXEMPLAR_ALT = "예시 이미지: 사장님 사진으로 바뀌어요"


def _default_art(kind: str) -> str:
    """업종 기본 그림 주소 (/art/<파일>.webp). 모르면 pension-example."""
    base = _DEFAULT_ART.get(kind if isinstance(kind, str) else "", "pension-example")
    if base not in _ART_FILES:
        base = "pension-example"
    return f"/art/{base}.webp"


def _default_gallery(kind: str) -> list[str]:
    """사진첩용 기본 그림 2장 (대표와 다른 파일 우선)."""
    hero = _default_art(kind)
    rest = [f"/art/{f}.webp" for f in _ART_FILES if f"/art/{f}.webp" != hero]
    return (rest + [hero])[:2]


def _mock_path(kind: str, slot: str) -> str:
    """목업 팩 파일이 있으면 그 주소, 없으면 빈 문자열.
    (scripts/make_mockup_pack.py가 templates/art/mock-<업종>-<슬롯>.webp로 만든다.)"""
    name = f"mock-{kind}-{slot}.webp"
    if (settings.templates_dir / "art" / name).is_file():
        return f"/art/{name}"
    return ""

# 3안 역할 고정 (P3-8, D43). id·이름은 그대로 둔다
# (채팅 안내·"기본형으로" 같은 고르기 말 인식·채팅방 미리보기 카드가 이름에 묶여 있음).
# 역할은 토큰·lead·구성으로 배정한다.
#   v1 기본형 = ① 업종 정석: 업종 _RULE 컨셉 그대로 (토큰·lead 모두 규칙값, 카드 AI 컨셉 무시)
#   v2 사진 강조형 = ② 사장님 분위기: 카드 컨셉(mood·brand_story 반영 AI 컨셉, 없으면 규칙)의
#     토큰·lead에 사진 강조 구조를 얹는다. 사장님이 표현하지 않은 칸(규칙과 같은 값)은
#     기존 사진 강조형 차별화값(옆 배치·사진첩 그리드·상품 사진그리드·넉넉한 여백)으로 메운다.
#   v3 간결형 = ③ 과감한 대비: v1과 색·글꼴·lead가 최대 차이 + 아치형 첫 화면.
#     사진이 없어도 기본 그림(/art/)으로 채워 빈 첫 화면(text-only)을 두지 않는다(photo-first).
# 최소차이 8 (D42-4·P3-11): 3쌍 중 최소 _spec_distance가 8 미만이면
#   v3를 palette → font_pair → lead 순으로 강제 분기한다 (_ensure_contrast).
# 첫 화면 구도는 Q-6 규칙이 따로 맡는다: 견본 첫 화면이 글자형인 업종(미용실)은
# 사진이 없을 때 v3를 겹침형으로 (1안·3안 첫 화면이 똑같아 최소 차이 2.0이던 문제).
VARIANTS = (
    ("v1", "기본형", "업종 정석 — 업종에 맞춘 기본 구성", {}),
    ("v2", "사진 강조형", "사장님 분위기 — 말씀에서 뽑은 느낌에 큰 사진",
     {"hero": "photo", "gallery": "marquee", "offerings": "photo-grid"}),
    ("v3", "간결형", "과감한 대비 — 색·글꼴·구성이 가장 다른 구성",
     {"hero": "arch", "gallery": "swipe", "offerings": "tabs"}),
)
# v2 토큰 폴백(사장님이 표현하지 않은 칸): 사진 강조형 차별화값 (a1b8a61 유지)
_V2_TOKEN_FALLBACK = {"density": "roomy", "radius": "round"}
# v3 토큰 고정: 촘촘·각짐 (a1b8a61 유지). palette·font_pair는 대비 선택.
_V3_TOKENS = {"density": "compact", "radius": "sharp"}
# 글꼴 대비 순서: 앞에서부터 v1·v2와 다른 첫 값을 쓴다
_FONT_CONTRAST_ORDER = ("serif-elegant", "gothic-strong", "serif-warm", "sans-clean", "round-soft", "pop-point")
# v3 lead 후보: v1 lead와 다른 첫 값을 쓴다 (v2 바로 다음 부품과도 다르면 더 좋음)
_LEAD_CANDIDATES = ("intro", "offerings", "gallery")
# 3안 최소차이 기준 (D42-4)
MIN_DISTANCE = 8
# 안마다 색 계열이 겹치지 않게 고른다(같은 초록끼리면 3안이 비슷해 보인다).
_PALETTE_GROUPS = {"forest": "green", "moss": "green", "sage": "green", "navy": "blue", "coffee": "warm", "brick": "warm",
                   "tomato": "warm", "charcoal-gold": "dark"}
_PALETTE_ORDER = ("navy", "brick", "charcoal-gold", "forest", "coffee", "moss", "tomato", "sage")

# 숨은 항목 → 아이콘(templates/sections/features--icons.mustache 6종)
_FEATURE_ICON = {"parking": "pin", "pickup": "pin", "shuttle": "pin", "pet": "heart", "kids": "heart",
                 "family": "heart", "wheelchair": "heart", "reserve": "clock", "same_day": "clock",
                 "regular": "clock", "trial": "star", "online": "phone", "wifi": "phone", "bbq": "leaf",
                 "takeout": "leaf", "delivery": "leaf", "supplies": "leaf"}
# "뺄 것"에 이런 말이 있으면 해당 부품을 뺀다.
_EXCLUDE_TYPES = {"후기": "reviews", "리뷰": "reviews", "사진": "gallery", "갤러리": "gallery",
                  "지도": "around", "주변": "around", "오시는": "around", "소개": "intro"}


@lru_cache(maxsize=None)
def _sample(key: str) -> dict:
    return json.loads((settings.templates_dir / "samples" / f"{key}.json").read_text(encoding="utf-8"))


def _fact(card: dict, key: str) -> str:
    slot = card["slots"].get(key) or {}
    if slot.get("status") != S.FILLED:
        return ""
    value = slot.get("value")
    return ", ".join(value) if isinstance(value, list) else str(value or "")


def _values(card: dict, key: str) -> list[str]:
    slot = card["slots"].get(key) or {}
    if slot.get("status") not in (S.FILLED, S.ASSUMED):
        return []
    value = slot.get("value")
    return [v for v in (value if isinstance(value, list) else [value]) if v]


def _wants_form(card: dict) -> bool:
    # "문의는 사이트 문의 양식으로" 같은 말은 AI가 기능이 아니라 연락 방법 칸에 넣기도 한다.
    contact = " ".join(_values(card, "contact_method"))
    if any(w in contact for w in ("문의 양식", "문의양식", "문의 폼", "양식")):
        return True
    for v in card.get("features_judged") or []:
        if v.get("id") == "inquiry_form":
            return True
        answer = (card.get("feature_answers") or {}).get(v.get("id")) or ""
        if v.get("id") == "kakao_form_bridge" and ("양식" in answer or "채팅방 알림" in answer):
            return True
    return False


def _wants_kakao_channel(card: dict) -> bool:
    contact = " ".join(_values(card, "contact_method"))
    answers = " ".join((card.get("feature_answers") or {}).values())
    return (bool(card.get("kakao_channel_url")) or "카카오톡 채널" in contact or "카톡 채널" in contact or "채널 버튼" in answers
            or any(v.get("id") == "kakao_channel_chat" for v in card.get("features_judged") or []))


# 예약 신청 받기(플랫폼 공용 ②, BOOKING_PLAN §2.5): 외부 예약 주소가 없는 예약형 업종에 기본으로 넣는다.
_BOOKING_INDUSTRIES = ("salon", "pension", "restaurant", "workshop", "academy")


def _booking_section(card: dict, ind, offerings: list[str], hours: str, excluded: str) -> Optional[dict]:
    if _fact(card, "booking_url") or "예약" in excluded:
        return None  # 네이버 예약 등 외부 주소가 있으면 지금처럼 링크, "예약은 빼주세요"면 없음
    contact = " ".join(_values(card, "contact_method"))
    asked = any(w in contact for w in ("여기서", "사이트에서", "예약 신청", "사이트 예약"))
    if not asked and ind.key not in _BOOKING_INDUSTRIES:
        return None
    return {"id": "booking", "type": "booking", "variant": "form",
            "content": {"services": offerings[:8], "service_label": S.label_for(ind, "offerings"), "time_options": [] if ind.key == "pension" else _time_options(hours),
                        "note": "상담 예약 신청이에요. 가게에서 확인 후 연락드려요." if ind.key == "academy"
                        else "가게에서 확인 후 연락드려요. 신청만으로 예약이 확정되지는 않아요."}}


def _time_options(hours: str) -> list[str]:
    """영업시간에서 30분 간격 선택지. 여는·닫는 시각이 딱 두 개로 읽힐 때만(애매하면 빈 목록 → 시간 직접 입력)."""
    from app.services.numbers import numbers_in
    if any(w in (hours or "") for w in ("오전", "오후", "저녁", "밤", "새벽")):
        return []  # "오후 2시~8시"의 8은 20시인데 숫자만으로는 모른다
    hs = sorted(n for n in numbers_in(hours or "") if isinstance(n, int) and 6 <= n <= 24)
    if len(hs) != 2 or hs[1] - hs[0] < 2:
        return []
    return [f"{h:02d}:{m:02d}" for h in range(hs[0], hs[1] - 1) for m in (0, 30)] + [f"{hs[1] - 1:02d}:00"]


def base_spec(card: dict) -> dict:
    """카드 내용을 업종 기본 조합에 채운 명세. 카드 컨셉(없으면 업종 규칙)을 쓴다."""
    return _build_spec(card, card.get("concept") or DC.rule_concept(card))


def _build_spec(card: dict, concept: dict) -> dict:
    """카드 + 지정 컨셉 → 명세. v1은 규칙 컨셉, v2는 사장님 분위기 컨셉으로 부른다."""
    ind = E.industry_of(card)
    spec = copy.deepcopy(_sample(_SAMPLE_FOR.get(ind.key, ind.key)))
    # 지정 컨셉의 색·글꼴·여백·모서리를 그대로 쓴다.
    spec["tokens"].update({k: concept[k] for k in ("palette", "font_pair", "density", "radius")})
    shop = _fact(card, "shop_name")
    phone, hours, address = _fact(card, "phone"), _fact(card, "hours"), _fact(card, "location")
    offerings = _values(card, "offerings")
    detail = _fact(card, "detail")
    draft = card.get("copy") or {}  # AI 문구 초안(app/services/copywriter.py). 사장님이 말한 소개가 우선
    excluded = " ".join(_values(card, "exclude"))
    photos = [p for p in card.get("photos") or [] if str(p.get("url", "")).startswith("/uploads/")]
    # 사장님 사진이 없으면 AI 예시 이미지를 쓴다(버튼으로 만든 것만, SVG 예시 그림보다 먼저).
    ai = card.get("ai_images") or {}
    ai_hero = str((ai.get("hero") or {}).get("url") or "")
    ai_gallery = [str((ai.get(s) or {}).get("url") or "") for s in ("gallery-1", "gallery-2")]
    ai_gallery = [u for u in ai_gallery if u.startswith("/uploads/")]
    if not ai_hero.startswith("/uploads/"):
        ai_hero = ""
    drop = {t for word, t in _EXCLUDE_TYPES.items() if word in excluded}

    sections = []
    for sec in spec["sections"]:
        if sec["type"] in drop:
            continue
        c = sec["content"]
        if sec["type"] == "hero":
            # photo-first: 사장님 사진 → AI 예시 → 업종 기본 그림(/art/) 순.
            # 사진이 없어도 글자 중심 첫 화면(text-only)을 두지 않는다(Q-7).
            sec["variant"] = "photo-overlay"
            # 펜션은 체크인·체크아웃 시간이라 '영업' 대신 '입실·퇴실'로 말한다
            hours_label = "입실·퇴실" if ind.key == "pension" else "영업"
            c["facts"] = [{"label": lab, "value": val} for lab, val in ((hours_label, hours), ("위치", address)) if val]
            if photos:
                c["image"] = photos[0]["url"]
                c["image_alt"] = photos[0].get("caption") or f"{shop or '가게'} 대표 사진"
            elif ai_hero:
                c["image"] = ai_hero
                c["image_alt"] = "AI 예시 이미지: 사장님 사진으로 바뀌어요"
                c["ai_example"] = True
            else:
                c["image"] = _mock_path(ind.key, "hero") or _default_art(ind.key)
                c["image_alt"] = _EXEMPLAR_ALT
                c.pop("ai_example", None)
            c["title"] = shop
            c["subtitle"] = detail or draft.get("tagline") or ", ".join(_values(card, "business_type"))
            # 전화가 없으면 문의 양식으로(양식은 기본 포함, 제목 id = contact-title-inquiry)
            c["cta"] = {"label": "전화 문의", "href": f"tel:{phone}"} if phone else {"label": "문의하기", "href": "#contact-title-inquiry"}
        elif sec["type"] == "intro":
            c["body"] = detail or draft.get("intro") or ""
        elif sec["type"] == "gallery":
            # 대표로 쓴 첫 장 말고 나머지(한 장뿐이면 그 한 장)를 사진첩에.
            # 사진이 없어도 기본 그림 2장으로 채워 빈 사진첩(SVG 폴백)을 두지 않는다.
            if photos:
                c["items"] = [{"src": p["url"], "alt": p.get("caption") or f"사진 {i + 1}", "caption": p.get("caption") or ""}
                              for i, p in enumerate(photos[1:] or photos)]
            elif ai_gallery:
                c["items"] = [{"src": u, "alt": "AI 예시 이미지: 사장님 사진으로 바뀌어요", "caption": "", "ai": True}
                              for u in ai_gallery]
            else:
                mock = [_mock_path(ind.key, s) for s in ("gallery-1", "gallery-2")]
                if all(mock):
                    c["items"] = [{"src": u, "alt": _EXEMPLAR_ALT, "caption": ""}
                                  for u in mock]
                else:
                    c["items"] = [{"src": u, "alt": _EXEMPLAR_ALT, "caption": ""}
                                  for u in _default_gallery(ind.key)]
        elif sec["type"] == "offerings":
            c["label"] = S.label_for(ind, "offerings")
            # 이름만 넣는다. 가격은 사장님이 말한 가격표가 생기면 채운다(지어내지 않음).
            descs = draft.get("items") or {}
            c["items"] = [{"name": o, "desc": descs.get(o, ""), "price": ""} for o in offerings] or c.get("items", [])
        elif sec["type"] in ("contact", "cta", "around"):
            for k, v in (("phone", phone), ("hours", hours), ("address", address),
                         ("booking_url", _fact(card, "booking_url"))):
                if k in c:
                    c[k] = v
        sections.append(sec)

    extra = []
    if _wants_kakao_channel(card):
        extra.append({"id": "kakao", "type": "contact", "variant": "kakao-channel",
                      "content": {"kakao_channel_url": card.get("kakao_channel_url") or ""}})
    # 편의 안내(방안 6): 사장님이 고른 숨은 항목(주차·반려동물 동반 등)을 아이콘 칸으로.
    # 목록 밖에서 더한 항목(extra)도 별 모양 아이콘 칸으로 뒤에 잇는다. 덧붙인 말(note)은
    # 첫 항목 설명에 붙이지 않고 내용(note 키)으로 따로 둔다(보기는 site_render이 한 줄로 그린다).
    chosen = [(k, label) for k, label in ind.hidden if k in (card.get("hidden") or {}).get("selected", [])]
    hidden = card.get("hidden") or {}
    raw_extra = hidden.get("extra") or []
    extra_names = [n.strip() for n in raw_extra if isinstance(n, str) and n.strip()]
    if chosen or extra_names:
        note = hidden.get("note") or ""
        feats = [{"title": label, "desc": "", "icon": _FEATURE_ICON.get(k, "star")}
                 for k, label in chosen]
        feats += [{"title": name, "desc": "", "icon": "star"} for name in extra_names]
        content = {"label": "이용 안내", "items": feats}
        if note:
            content["note"] = note
        at = next((i + 1 for i, s in enumerate(sections) if s["type"] == "offerings"), len(sections))
        sections.insert(at, {"id": "features", "type": "features", "variant": "icons",
                             "content": content})
    # 영상 카드(방안 5): 소개 바로 뒤에
    if card.get("videos"):
        at_intro = next((i + 1 for i, s in enumerate(sections) if s["type"] == "intro"), 1)
        sections.insert(at_intro, {"id": "video", "type": "video", "variant": "card",
                                   "content": {"items": [{"url": u, "title": ""} for u in card["videos"]]}})
    booking = _booking_section(card, ind, offerings, hours, excluded)
    if booking:
        extra.insert(0, booking)
        # 첫 화면 버튼은 예약 신청으로(예약형 업종은 전화보다 신청이 먼저)
        hero = next((s for s in sections if s["type"] == "hero"), None)
        if hero is not None:
            hero["content"]["cta"] = {"label": "상담 신청" if ind.key == "academy" else "예약 신청",
                                      "href": "#booking-title-booking"}
    # 문의 양식은 플랫폼 공용 기능(D31·D32)이라 기본으로 넣는다. "문의 폼은 빼주세요"처럼 말했을 때만 뺀다.
    if _wants_form(card) or not any(w in excluded for w in ("문의", "양식", "폼")):
        extra.append({"id": "inquiry", "type": "contact", "variant": "form", "content": {}})
    # 문의 부품은 후기 앞(보통 맨 끝 바로 앞)에 둔다.
    at = next((i for i, s in enumerate(sections) if s["type"] == "reviews"), len(sections))
    sections = sections[:at] + extra + sections[at:]
    # H0-5: 전화 중복 제거 — 연락처에 전화가 있으면 하단 띠(cta call-sms)는 뺀다.
    # 첫 화면 CTA(hero) + 연락처(contact)를 남기고 세 번째 전화 버튼을 없앤다 (Q-10).
    if phone:
        has_contact_phone = any(s["type"] == "contact" and s.get("variant") in
                                ("call-first", "booking-first", "chat-first") for s in sections)
        if has_contact_phone:
            sections = [s for s in sections
                        if not (s["type"] == "cta" and s.get("variant") == "call-sms")]
    # 컨셉의 "먼저 보여 줄 것"을 첫 화면 바로 뒤로
    lead = next((s for s in sections if s["type"] == concept.get("lead")), None)
    if lead is not None and sections and sections[0]["type"] == "hero":
        sections = [sections[0], lead] + [s for s in sections[1:] if s is not lead]
    spec["sections"] = sections
    spec["navbar"] = _build_navbar(card, sections)
    return spec


def _build_navbar(card: dict, sections: list) -> dict:
    """전역 내비 (할리스 GNB 1단 + 로고). 링크는 실제 제목 id(#<종류>-title-<id>)만,
    CTA는 히어로와 동일. 섹션이 아니라 순서·거리 계산에 들어가지 않는다."""
    by_type: dict = {}
    for s in sections:
        by_type.setdefault(s.get("type"), s)

    def _link(key: str, label: str) -> dict | None:
        sec = by_type.get(key)
        if sec is None:
            return None
        return {"label": label, "href": f"#{key}-title-{sec.get('id')}"}

    hero = by_type.get("hero", {})
    hero_content = hero.get("content") or {}
    links = [l for l in (
        _link("intro", "소개"),
        _link("offerings", (by_type.get("offerings", {}).get("content") or {}).get("label") or "메뉴"),
        _link("gallery", "사진"),
        _link("contact", "연락·예약") or _link("booking", "연락·예약") or _link("cta", "연락·예약"),
    ) if l is not None]
    return {"title": hero_content.get("title") or "", "links": links,
            "cta": hero_content.get("cta") or {},
            "top": f"#hero-title-{hero.get('id')}" if hero.get("id") else "#"}


def _pick_font(exclude) -> str:
    """글꼴 대비 순서에서 제외 집합에 없는 첫 값."""
    ex = set(exclude or ())
    for f in _FONT_CONTRAST_ORDER:
        if f not in ex:
            return f
    return "sans-clean"


@lru_cache(maxsize=None)
def _palette_hexes() -> dict:
    return json.loads((settings.templates_dir / "tokens" / "palettes.json").read_text(encoding="utf-8"))


def _luminance(hexcode: str) -> float:
    """16진 색의 WCAG 상대 휘도 (대비 선택용)."""
    h = hexcode.strip().lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))

    def chan(v: float) -> float:
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

    return 0.2126 * chan(r) + 0.7152 * chan(g) + 0.0722 * chan(b)


def _contrast_palette(v1pal: str, v2pal: str, skip: frozenset = frozenset()) -> str:
    """v3 색: v1과 다른 계열 중에서 v1 대표색과 휘도 차이가 가장 큰 것.
    v2 계열·값과도 다르면 더 좋고, 이미 쓴 값(skip)은 피한다."""
    hexes = _palette_hexes()
    v1g = _PALETTE_GROUPS.get(v1pal)
    v2g = _PALETTE_GROUPS.get(v2pal)
    base = _luminance(hexes[v1pal]["primary"])
    cands = [p for p in _PALETTE_ORDER
             if p != v1pal and p not in skip and _PALETTE_GROUPS.get(p) != v1g]
    if not cands:
        cands = [p for p in _PALETTE_ORDER if p != v1pal and p not in skip] or list(_PALETTE_ORDER)
    pool = [p for p in cands if p != v2pal and _PALETTE_GROUPS.get(p) != v2g] or cands
    return max(pool, key=lambda p: abs(_luminance(hexes[p]["primary"]) - base))


def _sample_hero(card: dict) -> str:
    """업종 견본의 첫 화면 변형 (Q-6: 견본이 글자형이면 v3 첫 화면을 바꾼다)."""
    ind = E.industry_of(card)
    sample = _sample(_SAMPLE_FOR.get(ind.key, ind.key))
    hero = next((s for s in sample.get("sections", []) if s.get("type") == "hero"), {})
    return hero.get("variant", "")


def _hero_of(spec: dict) -> str:
    hero = next((s for s in spec.get("sections", []) if s.get("type") == "hero"), {})
    return hero.get("variant", "")


def _offerings_variant(spec: dict) -> str:
    sec = next((s for s in spec.get("sections", []) if s.get("type") == "offerings"), {})
    return sec.get("variant", "")


def _gallery_variant(spec: dict) -> str:
    secs = [s for s in spec.get("sections", []) if s.get("type") == "gallery"]
    return secs[0].get("variant", "") if secs else ""


def _second_type(spec: dict) -> str:
    secs = spec.get("sections", [])
    return secs[1].get("type", "") if len(secs) > 1 else ""


def _spec_distance(a: dict, b: dict) -> int:
    """두 명세가 눈에 얼마나 다른지 0~17 가점 (D42-4 최소차이 8의 판정 기준).
    픽셀 평가와 같은 단위가 아니라 명세 차이의 근사치다:
    색 계열 4·글꼴 2·첫 화면 3·상품형 2·바로 다음 부품 2·사진첩 1·여백 1·모서리 1·사진처리 1."""
    score = 0
    ta, tb = a.get("tokens", {}), b.get("tokens", {})
    pa, pb = ta.get("palette"), tb.get("palette")
    if pa != pb:
        score += 2 if _PALETTE_GROUPS.get(pa) == _PALETTE_GROUPS.get(pb) else 4
    if ta.get("font_pair") != tb.get("font_pair"):
        score += 2
    if _hero_of(a) != _hero_of(b):
        score += 3
    if _offerings_variant(a) != _offerings_variant(b):
        score += 2
    ga = [s for s in a.get("sections", []) if s.get("type") == "gallery"]
    gb = [s for s in b.get("sections", []) if s.get("type") == "gallery"]
    va = ga[0].get("variant", "") if ga else ""
    vb = gb[0].get("variant", "") if gb else ""
    if (bool(ga) != bool(gb)) or (ga and gb and va != vb):
        score += 1
    if _second_type(a) != _second_type(b):
        score += 2
    if ta.get("density") != tb.get("density"):
        score += 1
    if ta.get("radius") != tb.get("radius"):
        score += 1
    if ta.get("image_style") != tb.get("image_style"):
        score += 1
    return score


def min_distance(specs: list[dict]) -> int:
    """3안 중 가장 비슷한 두 안의 차이."""
    ds = [_spec_distance(specs[i], specs[j]) for i in range(3) for j in range(i + 1, 3)]
    return min(ds) if ds else 0


def _move_lead(sections: list, lead: str) -> list:
    """lead 부품을 첫 화면 바로 뒤로 (없으면 그대로)."""
    if not sections or sections[0].get("type") != "hero":
        return sections
    for i, s in enumerate(sections):
        if s.get("type") == lead:
            return [sections[0], s] + [x for j, x in enumerate(sections) if j not in (0, i)]
    return sections


def _ensure_contrast(s1: dict, s2: dict, s3: dict) -> dict:
    """3안 최소차이 8 미만이면 v3를 palette → font_pair → lead 순으로 강제 분기한다."""
    s3 = copy.deepcopy(s3)
    if min_distance([s1, s2, s3]) >= MIN_DISTANCE:
        return s3
    # 1) 색: v1·v2와 다른 계열·값으로 (지금 값은 건너뛰고 다음으로 큰 휘도 차이를 고른다)
    s3["tokens"]["palette"] = _contrast_palette(
        s1["tokens"]["palette"], s2["tokens"]["palette"], frozenset({s3["tokens"]["palette"]}))
    if min_distance([s1, s2, s3]) >= MIN_DISTANCE:
        return s3
    # 2) 글꼴: v1·v2·지금 값과 다른 값으로
    s3["tokens"]["font_pair"] = _pick_font({s1["tokens"]["font_pair"], s2["tokens"]["font_pair"],
                                           s3["tokens"]["font_pair"]})
    if min_distance([s1, s2, s3]) >= MIN_DISTANCE:
        return s3
    # 3) lead: v1 바로 다음과 다른 부품을 첫 화면 뒤로 (v3에 있는 것만, v2 다음과도 다르면 더 좋음)
    first, second2 = _second_type(s1), _second_type(s2)
    present = [s["type"] for s in s3["sections"]]
    cands = [t for t in _LEAD_CANDIDATES if t != first and t in present]
    pool = [t for t in cands if t != second2] or cands
    if pool:
        s3["sections"] = _move_lead(s3["sections"], pool[0])
    return s3


def _apply_structure(spec: dict, change: dict) -> None:
    """부품 변형만 바꾼다 (토큰·순서는 역할 로직이 따로 정한다)."""
    for sec in spec["sections"]:
        want = change.get(sec["type"])
        if sec["type"] == "hero" and want == "photo":
            # 사진 강조형은 옆 배치: 1안(사진 있으면 겹침형, 없으면 글자형)과 늘 다르고,
            # 사진이 없을 때 예시 그림 위에 글자를 겹치지 않는다(Q-7)
            want = "photo-side"
        if want:
            sec["variant"] = want


def _spoken_palette(card: dict) -> str | None:
    """사장님이 실제로 말한 색. 카드 컨셉 팔레트가 규칙 컨셉과 다를 때만 그 값."""
    concept = card.get("concept")
    if not isinstance(concept, dict):
        return None
    said = concept.get("palette")
    if not isinstance(said, str) or not said:
        return None
    try:
        rule = DC.rule_concept(card).get("palette")
    except Exception:
        return None
    return said if said != rule else None


def _photo_path_for_url(url: str) -> Path | None:
    """업로드 주소(/uploads/로 시작) → 생성물 파일 경로. 밖이면 None."""
    if not isinstance(url, str) or not url.startswith("/uploads/"):
        return None
    rest = [p for p in url[len("/uploads/"):].split("/") if p not in ("", ".", "..")]
    if not rest:
        return None
    return settings.generated_dir / "uploads" / Path(*rest)


def _representative_photo_path(card: dict) -> Path | None:
    """대표 사진 파일 경로: 사장님 사진 첫 장 → AI 예시 hero → 없음.

    예시 팩(/art/ex/)은 사장님 가게 사진이 아니라서 쓰지 않는다.
    """
    for photo in card.get("photos") or []:
        if isinstance(photo, dict):
            found = _photo_path_for_url(photo.get("url"))
            if found is not None:
                return found
    ai = card.get("ai_images") or {}
    hero = ai.get("hero") if isinstance(ai, dict) else None
    if isinstance(hero, dict):
        return _photo_path_for_url(hero.get("url"))
    return None


def _blueprint_variants(card: dict, blueprint: dict, archetype: str) -> list[dict]:
    """청사진 새 경로 (BUILD_W1_W2 J5): skeleton → tokens → resolve로 3안.

    카드 사본에 card_data.build 결과를 넣어 구조 데이터를 고정하고,
    전략마다 청사진 토큰 + palette.pick(①②③) 색을 입힌다.
    결과 형식 [{id, name, summary, spec}]은 기존 경로와 같다.
    """
    from app.services import card_data as CD
    from app.services import palette as PAL
    from app.services import site_data as SD
    data = CD.build(card)
    work = copy.deepcopy(card)
    work["data"] = data
    # ② 분위기 색 우선순위: (1) 사장님이 말한 색 → (2) 대표 사진 색 → (3) 원형 후보 첫 값.
    # 예전에는 concept이 항상 채워져 있어 (2)가 쓰일 기회가 없었다.
    mood = _spoken_palette(work)
    photo = None
    if mood is None:
        at = _representative_photo_path(work)
        if at is not None:
            try:
                photo = PAL.photo_color(at)
            except Exception:
                photo = None
    base_tokens = blueprint.get("tokens") or {}
    out = []
    used: list = []
    for pos, strategy in enumerate(blueprint.get("strategies") or []):
        spec = SD.skeleton(blueprint, pos)
        spec = LE.apply(spec, blueprint, pos, (card.get("layout_edits") or {}).get(strategy.get("id") or f"v{pos + 1}"))
        pal = PAL.pick(archetype, pos + 1, mood=mood, used=tuple(used), photo=photo)
        used.append(pal)
        tokens = dict(base_tokens)
        tokens["palette"] = pal
        spec["tokens"] = tokens
        resolved = SD.resolve(spec, work, archetype=archetype)
        out.append({"id": strategy.get("id") or f"v{pos + 1}",
                    "name": strategy.get("name") or f"{pos + 1}안",
                    "summary": strategy.get("journey") or "",
                    "spec": resolved})
    if len(out) == 3 and min_distance([v["spec"] for v in out]) < MIN_DISTANCE:
        out[2]["spec"] = _recolor_v3(out, archetype)
    return out


def _recolor_v3(items: list[dict], archetype: str) -> dict:
    """3안 최소 차이 미달이면 v3 팔레트를 다음 후보로 바꾼다 (D42-4)."""
    from app.services import palette as PAL
    specs = [v["spec"] for v in items]
    current = specs[2]["tokens"]["palette"]
    try:
        lib = PAL.library()
    except Exception:
        return specs[2]
    start = lib.index(current) + 1 if current in lib else 0
    tried = {specs[0]["tokens"]["palette"], specs[1]["tokens"]["palette"], current}
    for cand in lib[start:] + lib[:start]:
        if cand in tried:
            continue
        trial = copy.deepcopy(specs[2])
        trial["tokens"]["palette"] = cand
        if min_distance([specs[0], specs[1], trial]) >= MIN_DISTANCE:
            return trial
    return specs[2]


def _agent_apply(card: dict, items: list) -> list:
    """에이전트 수정 조각 (J11 ui_agent.apply가 있으면 쓴다, 없거나 실패하면 그대로)."""
    try:
        from app.services import ui_agent
        apply = getattr(ui_agent, "apply", None)
        if not callable(apply):
            return items
        result = apply(card, items)
        return result if isinstance(result, list) and result else items
    except Exception:
        return items


APP_NAME = "앱형"
APP_SUMMARY = "앱처럼 아래 탭으로 오가요"


def _to_app(item: dict) -> dict:
    """3안(대비형)을 앱형으로 (D56 ①): 인사 첫 화면 + 하단 탭 + 고딕·둥근 카드. 구역 구성은 그대로."""
    spec = copy.deepcopy(item["spec"])
    spec["layout"] = "app"
    tokens = dict(spec.get("tokens") or {})
    tokens.update({"font_pair": "sans-clean", "radius": "round", "density": "comfortable"})
    spec["tokens"] = tokens
    for sec in spec.get("sections") or []:
        if isinstance(sec, dict) and sec.get("type") == "hero":
            sec["variant"] = "app"
    journey = item.get("summary") or ""
    return {**item, "name": APP_NAME, "summary": f"{APP_SUMMARY} · {journey}" if journey else APP_SUMMARY, "spec": spec}


def variants(card: dict) -> list[dict]:
    """[{id, name, summary, spec}] 3개. 역할 고정 (P3-8, D43): ① 정석 ② 분위기 ③ 앱형(D56, 전엔 대비형)."""
    try:
        from app.services import archetype as AT
        blueprint = AT.blueprint(card)
        arch, _ = AT.of(card)
    except Exception:
        blueprint, arch = None, ""
    items = None
    if blueprint is not None:
        try:
            items = _blueprint_variants(card, blueprint, arch)
        except Exception:
            items = None
    if items is None:
        items = _legacy_variants(card)
    if len(items) >= 3:
        items = items[:2] + [_to_app(items[2])] + items[3:]
    return _agent_apply(card, items)


def _legacy_variants(card: dict) -> list[dict]:
    """[{id, name, summary, spec}] 3개. 역할 고정 (P3-8, D43): ① 정석 ② 분위기 ③ 대비."""
    rule = DC.rule_concept(card)
    mood = card.get("concept") or rule
    # ① 업종 정석: 규칙 컨셉 그대로
    s1 = _build_spec(card, rule)
    v1pal = s1["tokens"]["palette"]
    v1font = s1["tokens"]["font_pair"]

    # ② 사장님 분위기: 카드 컨셉의 토큰·lead + 사진 강조 구조.
    # v2 순서는 사진첩을 첫 화면 바로 뒤에 두는 고정 순서(방안 7)라 mood lead는 토큰에만 남는다.
    s2 = _build_spec(card, mood)
    if mood.get("palette") == rule.get("palette"):
        groups = {_PALETTE_GROUPS.get(v1pal)}
        s2["tokens"]["palette"] = next(
            (p for p in _PALETTE_ORDER if _PALETTE_GROUPS[p] not in groups),
            next(p for p in _PALETTE_ORDER if p != v1pal))
    if mood.get("font_pair") == rule.get("font_pair"):
        s2["tokens"]["font_pair"] = _pick_font({v1font})
    if mood.get("density") == rule.get("density"):
        s2["tokens"]["density"] = _V2_TOKEN_FALLBACK["density"]
    if mood.get("radius") == rule.get("radius"):
        s2["tokens"]["radius"] = _V2_TOKEN_FALLBACK["radius"]
    _apply_structure(s2, dict(VARIANTS[1][3]))
    s2["sections"] = _reorder(s2["sections"], "v2")
    # 안별 사진 처리(image_style): v1 카드형 / v2 와이드 / v3 미니.
    # 토큰 검증 목록 안의 값만 쓴다(렌더러가 모르는 값이면 SiteSpecError).
    s2["tokens"]["image_style"] = "full-bleed"

    # ③ 과감한 대비: v1과 색·글꼴이 최대 차이 + 간결 구조 (상품 탭·사진첩은 실사진 있을 때만)
    s3 = _build_spec(card, rule)
    s3["tokens"]["palette"] = _contrast_palette(v1pal, s2["tokens"]["palette"])
    s3["tokens"]["font_pair"] = _pick_font({v1font, s2["tokens"]["font_pair"]})
    s3["tokens"].update(_V3_TOKENS)
    s3["tokens"]["image_style"] = "circle-mini"
    _apply_structure(s3, dict(VARIANTS[2][3]))
    s3["sections"] = _reorder(s3["sections"], "v3")
    # Q-6 (photo-first 이후 예비): 견본 첫 화면이 글자형이어도 _build_spec이
    # 기본 그림으로 겹침형을 만들기 때문에 이 조건은 보통 성립하지 않는다.
    if _sample_hero(card) == "text-only" and _hero_of(s1) == "text-only":
        for sec in s3["sections"]:
            if sec["type"] == "hero":
                sec["variant"] = "photo-overlay"
    # v3 lead는 v1과 최대 차이: 첫 화면 구도까지 같고 바로 다음 부품도 같으면
    # 첫 화면 한 장(픽셀 차이)이 거의 똑같아진다. v2 바로 다음과도 다르면 더 좋다.
    # (개별 카드의 규칙 lead는 intro라 시험 카드에는 걸리지 않는다.)
    if _hero_of(s3) == _hero_of(s1) and _second_type(s3) == _second_type(s1):
        first, second2 = _second_type(s1), _second_type(s2)
        present = [s["type"] for s in s3["sections"]]
        cands = [t for t in _LEAD_CANDIDATES if t != first and t in present]
        pool = [t for t in cands if t != second2] or cands
        if pool:
            s3["sections"] = _move_lead(s3["sections"], pool[0])
    s3 = _ensure_contrast(s1, s2, s3)

    specs = {"v1": s1, "v2": s2, "v3": s3}
    return [{"id": vid, "name": name, "summary": summary, "spec": specs[vid]}
            for vid, name, summary, _ in VARIANTS]


# 방안 7: 3안이 색·배치뿐 아니라 구성 순서부터 다르게 보이도록.
#   v2 사진 강조형: 첫 화면 바로 뒤에 사진첩, 그다음 소개
#   v3 간결형: 상품·수업을 먼저, 사진첩은 사장님 사진이 있을 때만, 영상은 맨 아래
_ORDER = {
    "v2": ("hero", "gallery", "intro", "video", "offerings", "features", "stats", "around", "contact", "cta", "reviews"),
    "v3": ("hero", "offerings", "features", "intro", "contact", "cta", "around", "video", "gallery", "reviews"),
}


def _reorder(sections: list, vid: str) -> list:
    order = _ORDER.get(vid)
    if not order:
        return sections
    if vid == "v3":
        sections = [s for s in sections if s["type"] != "gallery"
                    or any(str(i.get("src", "")).startswith("/uploads/") for i in s["content"].get("items", []))]
    rank = {t: i for i, t in enumerate(order)}
    # 같은 종류끼리는 원래 순서를 지킨다(문의 양식·카카오 채널 등)
    return sorted(sections, key=lambda s: (rank.get(s["type"], len(order)), sections.index(s)))


def kind_for(card: dict) -> str:
    """예시 그림을 고를 업종 키(templates/illustrations/<키>-*.svg)."""
    return E.industry_of(card).key


def title_for(card: dict) -> str:
    return _fact(card, "shop_name") or f"{', '.join(_values(card, 'business_type')) or '우리 가게'} 사이트"


def feature_notes(card: dict) -> list[str]:
    """시안 선택 페이지 아래에 보일 기능 판정 요약."""
    return [intake.note_for(v) for v in card.get("features_judged") or []]


def placeholder_count(card: dict) -> int:
    return sum(1 for s in card["slots"].values() if s.get("status") == S.PLACEHOLDER)


def pick(card: dict, variant_id: Optional[str]) -> Optional[dict]:
    return next((v for v in variants(card) if v["id"] == variant_id), None)
