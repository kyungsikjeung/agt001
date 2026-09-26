"""요구사항 카드 → 시안 3안 명세 (C7, 해커톤 요구 7, DESIGN_PIPELINE_PLAN.md).

AI가 화면을 새로 짜지 않는다: 업종 기본 조합(templates/samples)에서 출발해 부품 변형과 토큰만 바꾼 3안을 만든다.
가게 사실(이름·전화·주소·시간·가격)은 사장님이 직접 말한 값(FILLED)만 넣고, 나머지는 자리 표시로 둔다(D23·D26).
"""
import copy
import json
from functools import lru_cache
from typing import Optional

from app.config import settings
from app.services import intake
from app.services import prd_engine as E
from app.services import prd_schema as S

# 종류별 출발 샘플. 가게 6업종은 같은 이름의 샘플, 나머지는 구성이 가장 가까운 것.
_SAMPLE_FOR = {"individual": "workshop", "group": "academy", "webservice": "cafe", "other": "cafe"}

# 3안: (id, 이름, 한 줄 설명, 바꿀 것). v1은 업종 기본 그대로.
VARIANTS = (
    ("v1", "기본형", "업종에 맞춘 기본 구성", {}),
    ("v2", "사진 강조형", "큰 사진과 넉넉한 여백", {"hero": "photo", "gallery": "grid",
                                             "density": "roomy", "radius": "round", "font_pair": "serif-elegant"}),
    ("v3", "간결형", "글 중심, 빠르게 읽히는 구성", {"hero": "text-only", "density": "compact",
                                            "radius": "sharp", "font_pair": "gothic-strong"}),
)
# 안마다 색 계열이 겹치지 않게 고른다(같은 초록끼리면 3안이 비슷해 보인다).
_PALETTE_GROUPS = {"forest": "green", "moss": "green", "navy": "blue", "coffee": "warm", "brick": "warm",
                   "charcoal-gold": "dark"}
_PALETTE_ORDER = ("navy", "brick", "charcoal-gold", "forest", "coffee", "moss")

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


def base_spec(card: dict) -> dict:
    """카드 내용을 업종 기본 조합에 채운 명세 (v1)."""
    ind = E.industry_of(card)
    spec = copy.deepcopy(_sample(_SAMPLE_FOR.get(ind.key, ind.key)))
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
            for k, v in (("phone", phone), ("hours", hours), ("address", address)):
                if k in c:
                    c[k] = v
        sections.append(sec)

    extra = []
    if _wants_kakao_channel(card):
        extra.append({"id": "kakao", "type": "contact", "variant": "kakao-channel",
                      "content": {"kakao_channel_url": card.get("kakao_channel_url") or ""}})
    # 편의 안내(방안 6): 사장님이 고른 숨은 항목(주차·반려동물 동반 등)을 아이콘 칸으로. 덧붙인 말은 설명으로.
    chosen = [(k, label) for k, label in ind.hidden if k in (card.get("hidden") or {}).get("selected", [])]
    if chosen:
        note = (card.get("hidden") or {}).get("note") or ""
        feats = [{"title": label, "desc": note if i == 0 else "", "icon": _FEATURE_ICON.get(k, "star")}
                 for i, (k, label) in enumerate(chosen)]
        at = next((i + 1 for i, s in enumerate(sections) if s["type"] == "offerings"), len(sections))
        sections.insert(at, {"id": "features", "type": "features", "variant": "icons",
                             "content": {"label": "이용 안내", "items": feats}})
    # 영상 카드(방안 5): 소개 바로 뒤에
    if card.get("videos"):
        at_intro = next((i + 1 for i, s in enumerate(sections) if s["type"] == "intro"), 1)
        sections.insert(at_intro, {"id": "video", "type": "video", "variant": "card",
                                   "content": {"items": [{"url": u, "title": ""} for u in card["videos"]]}})
    # 문의 양식은 플랫폼 공용 기능(D31·D32)이라 기본으로 넣는다. "문의 폼은 빼주세요"처럼 말했을 때만 뺀다.
    if _wants_form(card) or not any(w in excluded for w in ("문의", "양식", "폼")):
        extra.append({"id": "inquiry", "type": "contact", "variant": "form", "content": {}})
    # 문의 부품은 후기 앞(보통 맨 끝 바로 앞)에 둔다.
    at = next((i for i, s in enumerate(sections) if s["type"] == "reviews"), len(sections))
    spec["sections"] = sections[:at] + extra + sections[at:]
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
                    # 기본안과 다른 사진 배치: 겹침형이면 옆 배치로, 아니면 겹침형으로
                    want = "photo-side" if sec["variant"] == "photo-overlay" else "photo-overlay"
                if want:
                    sec["variant"] = want
        out.append({"id": vid, "name": name, "summary": summary, "spec": spec})
    return out


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
