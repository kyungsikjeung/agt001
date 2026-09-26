"""디자인 컨셉 잡기 (9/26 대표 요청: "Stitch처럼 디자인 컨셉을 잡는 과정을 보여 달라").

Stitch는 디자인 시스템(색·글꼴·여백)을 먼저 정하고, 그걸로 화면을 여러 안 그린 뒤, 말로 고치게 한다.
우리도 같은 순서를 따르되 AI가 HTML을 짜지 않는다(D31): NVIDIA NIM은 정해진 토큰 목록 안에서만 고르고,
화면은 검증된 부품으로 그린다. AI가 실패하면 업종별 규칙 컨셉으로 대신한다.

컨셉 = {name, mood[3], palette, font_pair, density, radius, lead, reason, source}
  lead: 첫 화면 바로 다음에 올 부품(offerings 상품·메뉴 / gallery 사진 / intro 소개)
"""
import json
import logging
import re
from typing import Optional

from app import llm
from app.services import prd_engine as E

log = logging.getLogger(__name__)

PALETTES = {
    "tomato": "토마토 빨강·겨자 — 식욕이 도는 따뜻한 색",
    "brick": "벽돌 빨강 — 오래된 노포 같은 묵직함",
    "coffee": "커피 갈색 — 볶은 원두의 포근함",
    "forest": "숲 초록 — 자연·휴식",
    "moss": "이끼 초록 — 손으로 만든 차분함",
    "sage": "세이지 녹회색 — 깨끗하고 부드러운 관리",
    "navy": "남색 — 신뢰·공부",
    "charcoal-gold": "먹색·금색 — 절제된 고급스러움",
}
FONT_PAIRS = {
    "sans-clean": "프리텐다드 — 깔끔하고 읽기 쉬움",
    "gothic-strong": "IBM Plex 고딕 — 단단하고 또렷함",
    "serif-warm": "노토 세리프 — 따뜻한 손글씨 느낌의 명조",
    "serif-elegant": "고운바탕 — 우아한 명조",
    "round-soft": "고운돋움 — 둥글고 친근함",
    "pop-point": "주아 — 귀엽고 발랄함",
}
DENSITIES = {"compact": "촘촘하게", "comfortable": "보통", "roomy": "넉넉하게"}
RADII = {"sharp": "각지게", "soft": "살짝 둥글게", "round": "둥글게"}
LEADS = {"offerings": "메뉴·상품 먼저", "gallery": "사진 먼저", "intro": "소개 먼저"}

# 업종별 규칙 컨셉 (AI가 실패해도 이 값으로 그린다)
_RULE = {
    "restaurant": ("정직한 동네 밥상", ["따뜻한", "푸짐한", "정겨운"], "tomato", "gothic-strong", "comfortable", "soft", "offerings",
                   "식당은 메뉴와 가격을 가장 먼저 찾아서, 식욕이 도는 따뜻한 색에 굵은 글씨로 메뉴를 앞에 뒀어요."),
    "cafe": ("천천히 머무는 카페", ["포근한", "여유로운", "향긋한"], "coffee", "serif-warm", "roomy", "round", "gallery",
             "카페는 분위기로 고르는 곳이라, 커피색 바탕에 여백을 넉넉히 두고 사진을 먼저 보여 줘요."),
    "pension": ("숲속의 쉼", ["조용한", "자연스러운", "편안한"], "forest", "serif-elegant", "roomy", "soft", "gallery",
                "숙소는 풍경과 객실을 보고 예약해서, 숲 초록에 명조 제목으로 쉬는 느낌을 살렸어요."),
    "salon": ("단정한 손끝", ["깔끔한", "세련된", "부드러운"], "sage", "sans-clean", "comfortable", "round", "offerings",
              "미용실은 시술과 가격을 먼저 확인해서, 차분한 세이지색에 깔끔한 고딕으로 정리했어요."),
    "academy": ("믿을 수 있는 배움", ["성실한", "명확한", "든든한"], "navy", "gothic-strong", "comfortable", "sharp", "offerings",
                "학원은 반 구성과 상담이 핵심이라, 신뢰감 있는 남색에 또렷한 글씨로 반 안내를 앞에 뒀어요."),
    "workshop": ("손으로 만드는 시간", ["따뜻한", "정성스러운", "소박한"], "moss", "serif-warm", "roomy", "soft", "offerings",
                 "공방은 만드는 과정이 매력이라, 이끼색에 손글씨 느낌 명조로 수업을 먼저 보여 줘요."),
}
_RULE_DEFAULT = ("우리 동네 가게", ["친근한", "깔끔한", "믿음직한"], "navy", "sans-clean", "comfortable", "soft", "intro",
                 "처음 보는 분도 무엇을 하는 곳인지 바로 알 수 있게 깔끔하게 정리했어요.")

_SYSTEM = (
    "너는 동네 가게 홈페이지의 디자인 디렉터다. 사장님 요구사항을 읽고 사이트 디자인 컨셉을 정한다.\n"
    "반드시 아래 목록의 키만 고른다. 목록 밖 값은 쓰지 않는다.\n"
    f"palette: {json.dumps(PALETTES, ensure_ascii=False)}\n"
    f"font_pair: {json.dumps(FONT_PAIRS, ensure_ascii=False)}\n"
    f"density: {json.dumps(DENSITIES, ensure_ascii=False)}\n"
    f"radius: {json.dumps(RADII, ensure_ascii=False)}\n"
    f"lead: {json.dumps(LEADS, ensure_ascii=False)}\n"
    "출력은 JSON 하나: {\"name\": \"컨셉 이름(12자 이내, 명사형, 가게 이름은 쓰지 말고 분위기를 이름으로)\", \"mood\": [\"분위기 형용사\", 3개], "
    "\"palette\": \"키\", \"font_pair\": \"키\", \"density\": \"키\", \"radius\": \"키\", \"lead\": \"키\", "
    "\"reason\": \"왜 이렇게 정했는지 사장님께 한 문장(60자 이내, ~했어요 말투)\"}.\n"
    "사장님이 말하지 않은 사실(가격, 수상, 경력)은 쓰지 않는다. 이모지 금지."
)

_ADJUST_SYSTEM = (
    "너는 디자인 디렉터다. 지금 컨셉과 사장님의 디자인 수정 요청을 받아, 바꿀 값만 고른다.\n"
    "반드시 아래 목록의 키만 쓴다.\n"
    f"palette: {json.dumps(PALETTES, ensure_ascii=False)}\n"
    f"font_pair: {json.dumps(FONT_PAIRS, ensure_ascii=False)}\n"
    f"density: {json.dumps(DENSITIES, ensure_ascii=False)}\n"
    f"radius: {json.dumps(RADII, ensure_ascii=False)}\n"
    f"lead: {json.dumps(LEADS, ensure_ascii=False)}\n"
    "출력은 JSON 하나: {\"changes\": {바꿀 키: 값}, \"mood\": [\"바뀐 분위기 형용사\", 3개], "
    "\"reply\": \"무엇을 바꿨는지 사장님이 알아듣는 쉬운 말로 한 문장(50자 이내, ~했어요 말투, 팔레트·폰트 같은 전문 용어 금지)\"}. "
    "요청과 관계없는 값은 바꾸지 않는다."
)

# 말로 디자인 고치기: 이런 말이 있으면 디자인 요청으로 본다(가게 정보 수정과 구분).
_STYLE_WORDS = ("따뜻", "고급", "세련", "밝게", "밝은", "어둡", "차분", "화사", "귀엽", "깔끔", "심플", "모던", "우아",
                "색", "컬러", "글씨체", "글꼴", "폰트", "여백", "넉넉", "촘촘", "둥글", "각지", "분위기", "느낌",
                "사진 먼저", "메뉴 먼저", "소개 먼저", "디자인")

# AI 없이도 되는 기본 대응(규칙). 앞에서부터 맞는 것을 모두 적용한다.
_KEYWORD_CHANGES = (
    (("따뜻", "포근"), {"palette": "coffee"}, "따뜻한"),
    (("고급", "우아", "품격"), {"palette": "charcoal-gold", "font_pair": "serif-elegant", "radius": "sharp"}, "고급스러운"),
    (("세련", "모던", "깔끔", "심플"), {"font_pair": "sans-clean", "radius": "sharp"}, "세련된"),
    (("귀엽", "발랄", "아기자기"), {"font_pair": "pop-point", "radius": "round"}, "귀여운"),
    (("차분", "조용"), {"palette": "sage", "density": "roomy"}, "차분한"),
    (("화사", "밝게", "밝은", "산뜻"), {"palette": "tomato"}, "화사한"),
    (("넉넉", "여유"), {"density": "roomy"}, "여유로운"),
    (("촘촘", "빽빽", "한눈에"), {"density": "compact"}, "한눈에 보이는"),
    (("둥글",), {"radius": "round"}, "부드러운"),
    (("각지", "반듯"), {"radius": "sharp"}, "반듯한"),
    (("사진 먼저", "사진을 먼저", "사진 크게"), {"lead": "gallery"}, "사진 중심의"),
    (("메뉴 먼저", "메뉴를 먼저", "가격 먼저"), {"lead": "offerings"}, "메뉴 중심의"),
    (("소개 먼저", "소개를 먼저"), {"lead": "intro"}, "이야기 중심의"),
)


def _from_rule(key: str) -> dict:
    name, mood, palette, font, density, radius, lead, reason = _RULE.get(key, _RULE_DEFAULT)
    return {"name": name, "mood": list(mood), "palette": palette, "font_pair": font, "density": density,
            "radius": radius, "lead": lead, "reason": reason, "source": "rule"}


def rule_concept(card: dict) -> dict:
    return _from_rule(E.industry_of(card).key)


def _composed_reason(c: dict) -> str:
    """AI 이유를 못 쓸 때: 실제로 고른 값으로 이유 문장을 만든다(고른 값과 설명이 어긋나지 않게)."""
    color = PALETTES[c["palette"]].split(" — ")[1]
    font = FONT_PAIRS[c["font_pair"]].split(" — ")[0]
    return f"{c['mood'][0]} 느낌을 살리려고 {color}에 {font} 글꼴을 쓰고, {LEADS[c['lead']]} 보이게 했어요."


def _valid(c: dict, base: dict, shop: str = "", allowed_digits: frozenset = frozenset()) -> dict:
    """AI 결과를 목록 안의 값으로만 받아들인다. 틀린 값은 base 값으로 둔다."""
    out = dict(base)
    for key, allowed in (("palette", PALETTES), ("font_pair", FONT_PAIRS), ("density", DENSITIES),
                         ("radius", RADII), ("lead", LEADS)):
        if c.get(key) in allowed:
            out[key] = c[key]
    name = str(c.get("name") or "").strip()
    if 2 <= len(name) <= 16 and not (shop and (shop in name or name in shop)):  # 가게 이름은 컨셉 이름이 아니다
        out["name"] = name
    mood = [str(m).strip() for m in (c.get("mood") or []) if str(m).strip()][:3]
    if len(mood) == 3 and all(len(m) <= 8 for m in mood):
        out["mood"] = mood
    reason = str(c.get("reason") or "").strip()
    # 사장님이 말하지 않은 숫자가 든 이유는 지어낸 사실일 수 있어 버린다
    if 8 <= len(reason) <= 90 and set(re.findall(r"\d+", reason)) <= allowed_digits:
        out["reason"] = reason
    elif any(out[k] != base[k] for k in ("palette", "font_pair", "lead")):
        out["reason"] = _composed_reason(out)
    return out


def _parse(raw: str) -> Optional[dict]:
    m = re.search(r"\{.*\}", raw or "", re.S)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def make(card: dict) -> dict:
    """카드 → 컨셉. NIM이 목록 안에서 고르고, 실패하면 업종 규칙 컨셉."""
    base = rule_concept(card)
    try:
        user = f"[업종] {E.industry_of(card).name}\n[요구사항]\n{E.summary_text(card)}\n[사진] {'있음' if card.get('photos') else '없음'}"
        data = _parse(llm.chat_json(_SYSTEM, user, timeout_sec=15.0, max_tokens=300))
        if data:
            shop = str((card["slots"].get("shop_name") or {}).get("value") or "")
            said = E.summary_text(card) + " " + " ".join(card.get("said") or [])
            out = _valid(data, base, shop, frozenset(re.findall(r"\d+", said)))
            out["source"] = "ai"
            return out
    except Exception:
        log.exception("디자인 컨셉 AI 실패, 규칙 컨셉으로")
    return base


def is_style_request(text: str) -> bool:
    t = (text or "").strip()
    return 2 <= len(t) <= 80 and any(w in t for w in _STYLE_WORDS)


def _keyword_adjust(concept: dict, text: str) -> tuple[dict, str]:
    out, moods = dict(concept), []
    for words, changes, mood in _KEYWORD_CHANGES:
        if any(w in text for w in words):
            out.update(changes)
            moods.append(mood)
    if not moods:
        return out, ""
    out["mood"] = (moods + [m for m in concept.get("mood", []) if m not in moods])[:3]
    return out, f"{', '.join(moods)} 느낌으로 바꿨어요."


def adjust(concept: dict, text: str) -> tuple[dict, str]:
    """말로 디자인 고치기. (새 컨셉, 한 줄 답) — 바꿀 게 없으면 답이 빈 문자열."""
    try:
        user = f"[지금 컨셉] {json.dumps({k: concept.get(k) for k in ('name', 'mood', 'palette', 'font_pair', 'density', 'radius', 'lead')}, ensure_ascii=False)}\n[요청] {text}"
        data = _parse(llm.chat_json(_ADJUST_SYSTEM, user, timeout_sec=12.0, max_tokens=250))
        changes = (data or {}).get("changes") or {}
        if isinstance(changes, dict) and changes:
            out = _valid({**{k: concept.get(k) for k in ("palette", "font_pair", "density", "radius", "lead")}, **changes,
                          "mood": (data or {}).get("mood")}, concept)
            if any(out.get(k) != concept.get(k) for k in ("palette", "font_pair", "density", "radius", "lead")):
                reply = str((data or {}).get("reply") or "").strip()
                if not (4 <= len(reply) <= 80) or re.search(r"\d", reply):
                    reply = "말씀하신 느낌으로 바꿨어요."
                return out, reply
    except Exception:
        log.exception("디자인 수정 AI 실패, 규칙으로")
    return _keyword_adjust(concept, text)


def summary_line(c: dict) -> str:
    """채팅에 보일 컨셉 한 줄."""
    return (f"디자인 컨셉: 「{c['name']}」 — {' · '.join(c['mood'])}\n"
            f"{PALETTES[c['palette']].split(' — ')[0]} · {FONT_PAIRS[c['font_pair']].split(' — ')[0]} · "
            f"{LEADS[c['lead']]}\n{c['reason']}")
