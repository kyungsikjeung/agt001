"""AI 없이 도는 대화 시뮬레이션 부품 (run_simulation --offline, 비공식).

키가 없는 환경에서 엔진 규칙 변경의 전후를 같은 조건으로 비교하려고 만든다.
- 추출: 시나리오 사실표에 있는 값 중 이번 발화에 글자 그대로 나온 것만 뽑는다.
- 사장님: 규칙 기반 대답(rule_fallback_owner_llm)에, 시간 질문에서는 z3 실제 기록처럼
  "매일 같은 시간"이 있으면 고르고 없으면 사실표 시간을 그대로 말한다.
AI의 표현 차이·실수는 재현하지 못하므로 공식 성적에 쓰지 않는다.
"""
import json
import re

_TOKEN_SPLIT = re.compile(r"[,·()/]|\s+그리고\s+")
_PHONE_RE = re.compile(r"01\d-?\d{3,4}-?\d{4}")
_HOURS_RE = re.compile(r"\d+\s*(시|:)|[~～]\s*\d")
_EXCLUDE_RE = re.compile(r"빼|제외")


def scenario_facts(scenario) -> dict:
    """사실표 + 도중 변경 값 + 품목별 가격 글. 키 뒤 '#n'은 같은 칸의 다른 값이다."""
    facts = dict(scenario.get("facts") or {})
    for i, ch in enumerate(scenario.get("changes") or []):
        for k, v in (ch.get("patch") or {}).items():
            facts[f"{k}#{i}"] = v
    say = (scenario.get("profile") or {}).get("say")
    if say:
        facts["price#profile"] = say
    return facts


def extract_from_facts(text: str, facts: dict) -> list:
    """사실표 값이 발화에 그대로 나오면 그 칸으로 뽑는다. 없는 값은 만들지 않는다."""
    updates = []
    for key, value in facts.items():
        slot = key.split("#")[0]
        if slot == "phone":
            m = _PHONE_RE.search(text)
            if m:
                updates.append({"slot": "phone", "value": m.group(0)})
            continue
        if slot == "hours":
            if _HOURS_RE.search(text):
                updates.append({"slot": "hours", "value": text.strip(" .")})
            continue
        items = value if isinstance(value, list) else [value]
        if slot == "exclude":
            if _EXCLUDE_RE.search(text):
                updates += [{"slot": "exclude", "value": i} for i in items if str(i).split("·")[0] in text]
            continue
        hits = []
        for item in items:
            item = str(item)
            if item in text:
                hits.append(item)
                continue
            hits += [t.strip() for t in _TOKEN_SPLIT.split(item)
                     if len(t.strip()) >= 2 and t.strip() in text and t.strip() not in hits]
        if hits:
            updates.append({"slot": slot, "value": ", ".join(hits)})
    return updates


def fake_chat_json(facts_ref: dict):
    """app.llm.chat_json 자리에 끼우는 함수. facts_ref['facts']를 지금 시나리오 사실표로 쓴다."""
    def chat_json(system, user, **kw):
        if "[사장님 메시지] " in user:
            text = user.split("[사장님 메시지] ", 1)[-1]
            return json.dumps({"updates": extract_from_facts(text, facts_ref.get("facts") or {})},
                              ensure_ascii=False)
        return json.dumps({"missing": [], "conflicts": []})  # 리뷰어: 지적 없음
    return chat_json


def _prompt_facts(prompt: str) -> dict:
    lines = prompt.splitlines()
    for i, line in enumerate(lines):
        if line.startswith("[사실표]"):
            for nxt in lines[i + 1:]:
                if nxt.strip().startswith("{"):
                    try:
                        return json.loads(nxt.strip())
                    except ValueError:
                        return {}
    return {}


def offline_owner_llm(fallback):
    """규칙 사장님 + 시간 질문 규칙. fallback은 rule_fallback_owner_llm."""
    def owner(prompt: str) -> str:
        question = prompt.split("[이번 질문]")[-1].split("사장님 대답")[0]
        hours = _prompt_facts(prompt).get("hours")
        if hours and ("영업시간" in question or "시부터" in question or "체크인" in question):
            if "매일 같은 시간" in question and str(hours).startswith("매일"):
                return "매일 같은 시간"
            return str(hours)
        return fallback(prompt)
    return owner
