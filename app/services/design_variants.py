"""요구사항 카드 → 시안 3안 명세 (C7, 해커톤 요구 7, DESIGN_PIPELINE_PLAN.md).

AI가 화면을 새로 짜지 않는다: 업종 기본 조합(templates/samples)에서 출발해 부품 변형과 토큰만 바꾼 3안을 만든다.
가게 사실(이름·전화·주소·시간·가격)은 사장님이 직접 말한 값(FILLED)만 넣고, 나머지는 자리 표시로 둔다(D23·D26).
"""
import copy
import json
from functools import lru_cache
from typing import Optional

from app.config import settings
from app.services import design_concept as DC
from app.services import intake
from app.services import prd_engine as E
from app.services import prd_schema as S

# 종류별 출발 샘플. 가게 6업종은 같은 이름의 샘플, 나머지는 구성이 가장 가까운 것.
_SAMPLE_FOR = {"individual": "workshop", "group": "academy", "webservice": "cafe", "other": "cafe"}

# 3안: (id, 이름, 한 줄 설명, 바꿀 것). v1은 업종 기본 그대로.
# H0-1: 색·여백뿐 아니라 첫 화면·상품형까지 다르게 (3안 차이 8 미만 4곳 해소용).
#   v1 기본형: 업종 샘플 그대로 (photo-overlay 또는 text-only + list-price)
#   v2 사진 강조형: 옆 배치 + 사진첩 그리드 + 상품 사진그리드
#   v3 간결형: 글 중심 + 상품 탭 + 사진첩은 실사진 있을 때만 (_reorder에서 제거)
VARIANTS = (
    ("v1", "기본형", "업종에 맞춘 기본 구성", {}),
    ("v2", "사진 강조형", "큰 사진과 넉넉한 여백", {"hero": "photo", "gallery": "grid", "offerings": "photo-grid",
                                             "density": "roomy", "radius": "round", "font_pair": "serif-elegant"}),
    ("v3", "간결형", "글 중심, 빠르게 읽히는 구성", {"hero": "text-only", "gallery": "swipe", "offerings": "tabs",
                                            "density": "compact", "radius": "sharp", "font_pair": "gothic-strong"}),
)
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
    """카드 내용을 업종 기본 조합에 채운 명세 (v1)."""
    ind = E.industry_of(card)
    spec = copy.deepcopy(_sample(_SAMPLE_FOR.get(ind.key, ind.key)))
    # 디자인 컨셉(design_concept): 1안은 컨셉의 색·글꼴·여백·모서리를 그대로 쓴다. 없으면 업종 규칙 컨셉.
    concept = card.get("concept") or DC.rule_concept(card)
    spec["tokens"].update({k: concept[k] for k in ("palette", "font_pair", "density", "radius")})
    shop = _fact(card, "shop_name")
    phone, hours, address = _fact(card, "phone"), _fact(card, "hours"), _fact(card, "location")
    offerings = _values(card, "offerings")
    detail = _fact(card, "detail")
    draft = card.get("copy") or {}  # AI 문구 초안(app/services/copywriter.py). 사장님이 말한 소개가 우선
    excluded = " ".join(_values(card, "exclude"))
    photos = [p for p in card.get("photos") or [] if str(p.get("url", "")).startswith("/uploads/")]
    drop = {t for word, t in _EXCLUDE_TYPES.items() if word in excluded}

    sections = []
    for sec in spec["sections"]:
        if sec["type"] in drop:
            continue
        c = sec["content"]
        if sec["type"] == "hero":
            # 사진이 있으면 사진을 크게 깐 첫 화면, 없으면 컨셉 색을 넓게 깐 글자 중심 첫 화면(예시 그림을 겹치지 않음, Q-7)
            sec["variant"] = "photo-overlay" if photos else "text-only"
            c["facts"] = [{"label": lab, "value": val} for lab, val in (("영업", hours), ("위치", address)) if val]
            if photos:
                c["image"] = photos[0]["url"]
                c["image_alt"] = photos[0].get("caption") or f"{shop or '가게'} 대표 사진"
            c["title"] = shop
            c["subtitle"] = detail or draft.get("tagline") or ", ".join(_values(card, "business_type"))
            # 전화가 없으면 문의 양식으로(양식은 기본 포함, 제목 id = contact-title-inquiry)
            c["cta"] = {"label": "전화 문의", "href": f"tel:{phone}"} if phone else {"label": "문의하기", "href": "#contact-title-inquiry"}
        elif sec["type"] == "intro":
            c["body"] = detail or draft.get("intro") or ""
        elif sec["type"] == "gallery" and photos:
            # 대표로 쓴 첫 장 말고 나머지(한 장뿐이면 그 한 장)를 사진첩에
            c["items"] = [{"src": p["url"], "alt": p.get("caption") or f"사진 {i + 1}", "caption": p.get("caption") or ""}
                          for i, p in enumerate(photos[1:] or photos)]
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
    return spec


def variants(card: dict) -> list[dict]:
    """[{id, name, summary, spec}] 3개."""
    base = base_spec(card)
    used = [base["tokens"]["palette"]]
    out = []
    for vid, name, summary, change in VARIANTS:
        spec = copy.deepcopy(base)
        if change:
            groups = {_PALETTE_GROUPS.get(p) for p in used}
            palette = next((p for p in _PALETTE_ORDER if _PALETTE_GROUPS[p] not in groups),
                           next(p for p in _PALETTE_ORDER if p not in used))
            used.append(palette)
            spec["tokens"].update({"palette": palette, **{k: change[k] for k in ("density", "radius", "font_pair")}})
            for sec in spec["sections"]:
                want = change.get(sec["type"])
                if sec["type"] == "hero" and want == "photo":
                    # 사진 강조형은 옆 배치: 1안(사진 있으면 겹침형, 없으면 글자형)과 늘 다르고,
                    # 사진이 없을 때 예시 그림 위에 글자를 겹치지 않는다(Q-7)
                    want = "photo-side"
                if want:
                    sec["variant"] = want
            spec["sections"] = _reorder(spec["sections"], vid)
        out.append({"id": vid, "name": name, "summary": summary, "spec": spec})
    return out


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
