"""입구 게이트: 금지 요청 거르기 + 기능 요구 판정 (INTAKE_GATE_DESIGN.md §2 ②④⑧~⑬, D29~D33).

문의 종류 분류는 prd_schema.industry_for(업종 표현 → 가게 6업종·개인·단체·웹서비스)와
prd_engine의 "종류 묻기" 질문이 맡는다. 여기서는 규칙으로 판단할 수 있는 두 가지만 한다.
"""
import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Optional

from app.services import prd_schema as S

_DATA = Path(__file__).resolve().parents[1] / "data"

READY, ALTERNATIVE, OWNER_SETUP, OUT_OF_BETA = "ready", "alternative", "owner_setup", "out_of_beta"
# 데이터 연결표 바인딩 값 (UI_AGENT_PLAN §5.2: 정적·자원·계산·외부·없음)
BINDINGS = ("static", "resource", "computed", "external", "none")
# 지금 있는 플랫폼 자원은 bookings·inquiries뿐 (UI_AGENT_PLAN §5.3)
RESOURCES = ("", "bookings", "inquiries")
# 확인 질문이 필요한 판정 (질문 예산 +1 대상, §6)
NEEDS_CONFIRM = (ALTERNATIVE, OWNER_SETUP)
MATCH_MIN = 0.5  # 사례집 별칭과 요구 문장의 글자 쌍 겹침 비율 하한


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", (s or "").lower())
    # 같은 뜻의 흔한 줄임말을 맞춘다
    s = s.replace("카카오톡", "카톡").replace("카카오", "카톡")
    return re.sub(r"[^가-힣a-z0-9]", "", s)


def _bigrams(s: str) -> set[str]:
    return {s[i:i + 2] for i in range(len(s) - 1)} if len(s) >= 2 else {s} if s else set()


@lru_cache(maxsize=1)
def _catalog() -> list[dict]:
    items = json.loads((_DATA / "feature_catalog.json").read_text(encoding="utf-8"))["items"]
    _check_bindings(items)
    for it in items:
        it["_keys"] = [_norm(a) for a in [it["name"], *it.get("aliases", [])] if _norm(a)]
    return items


def _check_bindings(items: list[dict]) -> None:
    """데이터 연결표 검증. 어기면 개발 중에 바로 알 수 있게 ValueError."""
    from app.services import site_render
    known = set(site_render.list_variants())
    for it in items:
        fid = it.get("id")
        comps = it.get("components")
        if not isinstance(comps, list) or any(c not in known for c in comps):
            raise ValueError(f"feature_catalog {fid}: components가 실제 부품이 아님: {comps!r}")
        if it.get("binding") not in BINDINGS:
            raise ValueError(f"feature_catalog {fid}: binding이 허용 값이 아님: {it.get('binding')!r}")
        if it.get("resource") not in RESOURCES:
            raise ValueError(f"feature_catalog {fid}: resource가 플랫폼 자원이 아님: {it.get('resource')!r}")


def ready_components(archetype: str | None = None) -> dict[str, list[str]]:
    """verdict가 ready인 기능 id → components. 원형 인자는 2주차 UI 에이전트가 쓴다(지금은 거르지 않음)."""
    return {it["id"]: list(it.get("components") or [])
            for it in _catalog() if it.get("verdict") == READY}


def blocked_reason(text: str) -> Optional[str]:
    """사칭·피싱·도박 등 금지 요청이면 거절 이유 한 줄, 아니면 None."""
    n = _norm(text)
    for rule in S.PROFILES.get("blocked", []):
        # 예외 표현("마약김밥", "오피스텔")은 빼고 본다. 흔한 가게 말이 금지 요청으로 막히던 문제(T3 restaurant-unordered)
        body = n
        for a in rule.get("allow", []):
            body = body.replace(_norm(a), " ")
        if any(_norm(k) and _norm(k) in body for k in rule["keywords"]):
            return rule["description"].split(".")[0]
    return None


def match_feature(text: str) -> Optional[dict]:
    """요구 한 줄 → 가장 가까운 사례집 항목 (없으면 None)."""
    n = _norm(text)
    if len(n) < 2:
        return None
    grams = _bigrams(n)
    best, best_score = None, 0.0
    for it in _catalog():
        for key in it["_keys"]:
            if key in n:
                score = 1.0 + len(key) / 100  # 요구 문장이 별칭을 품음: 긴 별칭일수록 구체적
            elif n in key:
                score = 0.9  # 짧은 요구("지도")가 별칭 안에 있음
            else:
                kg = _bigrams(key)
                score = len(kg & grams) / len(kg) if kg else 0.0
            if score > best_score:
                best, best_score = it, score
    return best if best_score >= MATCH_MIN else None


def judge(text: str) -> dict:
    """카드에 남길 판정 한 건. 사례집에 없으면 'unknown'(시안 단계에서 사람이 본다)."""
    it = match_feature(text)
    if it is None:
        return {"text": text, "id": None, "verdict": "unknown"}
    q = (it.get("questions") or [None])[0]
    return {
        "text": text, "id": it["id"], "name": it["name"], "verdict": it["verdict"], "how": it.get("how", ""),
        "owner_tasks": list(it.get("owner_tasks") or []),
        "alternatives": [a["name"] for a in it.get("alternatives") or []],
        "question": ({"ask": q["ask"], "options": list(q.get("options") or [])[:S.MAX_OPTIONS]}
                     if q and it["verdict"] in NEEDS_CONFIRM else None),
    }


def note_for(v: dict) -> str:
    """판정을 사장님께 알리는 한 줄."""
    name = v.get("name") or v["text"]
    if v["verdict"] == READY:
        return f"'{name}' 넣을게요."
    if v["verdict"] == OWNER_SETUP:
        tasks = ", ".join(v.get("owner_tasks") or [])
        return f"'{name}'은(는) 사장님 준비가 조금 필요해요({tasks}). 준비 전에는 다른 방법으로 만들어 둘게요."
    if v["verdict"] == ALTERNATIVE:
        alt = v["alternatives"][0] if v.get("alternatives") else "비슷한 방법"
        return f"'{v['text']}'은(는) 지금은 '{alt}'(으)로 만들 수 있어요."
    if v["verdict"] == OUT_OF_BETA:
        alt = f" 대신 '{v['alternatives'][0]}'(으)로 만들고," if v.get("alternatives") else ""
        return f"'{name}'은(는) 베타에서는 아직 못 해요.{alt} 나중 할 일에 적어 둘게요."
    return f"'{v['text']}'은(는) 시안을 만들 때 가능한지 확인해 볼게요."
