"""처음 보는 종류 추론 (KIND_INFER_CONTRACT).

업종이 6업종·프로필 어디에도 안 맞으면(`industry_of` = `other`) 사장님 말에서 종류를 먼저 추론한다.
무엇을 고를지는 LLM이 정하고 엔진이 검증한다(situation.py와 같은 모양).
실패하면 None을 돌려주고, 부른 쪽은 4지선다(`site_kind`) 질문으로 되돌아간다.
"""
import json
import logging
import re

from app import llm
from app.services import prd_schema as S

log = logging.getLogger(__name__)

# 추론할 수 있는 종류
ALLOWED = ("shop", "individual", "group", "webservice", "event")


def _system_prompt() -> str:
    descs = {
        "shop": "가게·매장: 물건·음식·서비스를 파는 곳",
        "individual": S.PROFILES["individual"]["description"],
        "group": S.PROFILES["group"]["description"],
        "webservice": S.PROFILES["webservice"]["description"],
        "event": S.PROFILES["event"]["description"],
    }
    lines = "\n".join(f"- {k}: {descs[k]}" for k in ALLOWED)
    return (
        "너는 소상공인 웹사이트의 종류를 고르는 도우미다. 아래 만들 사이트 설명을 보고, "
        "가장 맞는 종류 하나와 방문자가 사이트에서 봐야 할 내용 이름(needs)을 고른다. JSON만 출력한다.\n"
        f"종류:\n{lines}\n"
        '출력 형식: {"kind": "event", "needs": ["날짜와 장소", "오시는 길"]}'
    )


def _clean_needs(raw) -> list[str]:
    """방문자가 봐야 할 내용 이름: 문자열만, 앞뒤 공백 제거, 1~12자, 중복 제거, 최대 6개.

    한국어가 아닌 말이 든 것은 버린다. 목록이 아니면 빈 목록(kind만으로도 성공이다).
    """
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for need in raw:
        if not isinstance(need, str):
            continue
        name = need.strip()
        if not 1 <= len(name) <= 12 or name in out:
            continue
        if llm.foreign_words(name):
            continue
        out.append(name)
        if len(out) >= 6:
            break
    return out


def infer(business_type: str) -> dict | None:
    """사장님 말(업종 칸 값)에서 종류를 추론한다. 검증 실패·예외는 None."""
    try:
        raw = llm.chat_json(_system_prompt(), f"만들 사이트: {business_type}",
                            timeout_sec=12, max_tokens=300)
    except Exception:
        log.exception("종류 추론 호출 실패(4지선다로)")
        return None
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        m = re.search(r"\{.*\}", raw or "", re.S)
        try:
            data = json.loads(m.group(0)) if m else {}
        except ValueError:
            return None
    kind = data.get("kind") if isinstance(data, dict) else None
    if kind not in ALLOWED:
        return None
    industry = "other" if kind == "shop" else kind
    return {"kind": kind, "industry": industry, "needs": _clean_needs(data.get("needs"))}
