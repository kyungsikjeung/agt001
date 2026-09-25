"""가상 사장님 (WP P-1e, 소유: evals/sim_owner.py).

REQUIREMENTS_ENGINE_PLAN.md §4.1(T3)과 RESEARCH.md §2(가상 사장님 세 원칙)의 구현이다.
표준 라이브러리만 쓴다. LLM 함수는 바깥에서 주입받는다(실제 NIM 호출 금지 — 시험은 가짜로).

세 원칙:
- 근거 한정: 사실표에 있는 것만 말한다. 밖이면 "잘 모르겠어요".
- 수동 응답: 묻지 않은 것은 먼저 말하지 않는다 (talkative도 첫 메시지 이후에는 같다).
- 맥락 유지: 전체 대화를 매번 프롬프트에 넘긴다.
"""

NOT_SURE = "잘 모르겠어요"
NONE_WORD = "없음"


def is_hidden_question(question) -> bool:
    """숨은 항목 여러 개 고르기 질문인지. 엔진은 kind='multi', slot=None으로 낸다."""
    if not isinstance(question, dict):
        return False
    return question.get("kind") == "multi" or question.get("slot") is None


def _is_true(value) -> bool:
    if value is True:
        return True
    if isinstance(value, str) and value.strip():
        return True
    return False


def rule_hidden_answer(hidden_facts, hidden_labels) -> str:
    """숨은 항목 여러 개 고르기는 LLM 없이 규칙으로 답한다.

    hidden_facts에서 true인 것의 표시 이름을 쉼표로 잇고, 없으면 "없음".
    hidden_labels: [(키, 표시 이름), ...] (업종 Industry.hidden).
    """
    hidden_facts = hidden_facts or {}
    labels = {k: label for k, label in (hidden_labels or [])}
    picked = [labels[k] for k in hidden_facts if _is_true(hidden_facts[k]) and k in labels]
    # 표시 이름을 모르는 키가 true여도(라벨표에 없음) 키 그대로는 말하지 않는다.
    if not picked:
        return NONE_WORD
    return ", ".join(picked)


def facts_for_viewer(scenario, is_owner: bool = True) -> dict:
    """이 화자가 볼 수 있는 사실만 돌려준다.

    공유방에서 방장이 아닌 사람은 방장만 아는 사실(owner_decides 값)을 모른다(D24).
    """
    facts = dict(scenario.get("facts") or {})
    if is_owner:
        return facts
    group = scenario.get("group") or {}
    decides = (group.get("owner_decides") or {})
    if isinstance(decides, dict):
        for v in decides.values():
            for k, fv in list(facts.items()):
                if fv == v:
                    facts.pop(k, None)
    return facts


def build_prompt(*, facts, persona_note="", unknown=(), question_text="",
                 options=(), history=(), opinion_text="", hidden_labels=None,
                 persona="", slot="") -> str:
    """가상 사장님 프롬프트. 선택지가 사실과 맞으면 글자 그대로 답하도록 지시한다."""
    import json
    lines = [
        "너는 소상공인 가게 사장님을 연기한다. 아래 사실표에 있는 것만 말한다.",
        "규칙:",
        "1. 사실표에 없는 것을 묻거든 \"" + NOT_SURE + "\"라고만 답한다. 지어내지 않는다.",
        "2. 묻지 않은 것은 먼저 말하지 않는다. 한 번에 한 가지만 짧게 답한다.",
        "3. 앞에서 한 말과 어긋나게 말하지 않는다.",
        "4. 선택지가 주어졌고 사실과 맞는 선택지가 있으면, 그 선택지의 글자를 그대로 답한다(바꾸지 않는다).",
        "5. '알아서 해주세요'가 선택지에 있고 정말 모르는 것이면 그대로 답한다.",
    ]
    if persona == "talkative":
        lines.append("6. 넌 말 많은 사장님이지만 첫 메시지에서 이미 많이 말했으니, 이제는 묻는 것에만 짧게 답한다.")
    parts = [
        "\n".join(lines),
        "[사실표]\n" + json.dumps(facts, ensure_ascii=False),
        "[모르는 칸]\n" + ", ".join(unknown) if unknown else "[모르는 칸]\n없음",
        "[말투]\n" + (persona_note or "짧게 답함"),
    ]
    if opinion_text:
        parts.append("[이 사람의 의견]\n" + opinion_text)
    if history:
        dlg = "\n".join(f"{m.get('role', '')}: {m.get('text', '')}" for m in history[-20:])
        parts.append("[지금까지 대화]\n" + dlg)
    parts.append("[이번 질문]\n" + (question_text or ""))
    if slot:
        parts.append("[질문 칸]\n" + slot)
    if options:
        parts.append("[선택지]\n" + " | ".join(options))
    parts.append("사장님 대답 한 줄:")
    return "\n\n".join(parts)


def answer(*, scenario, question, history=(), llm_fn,
           is_owner: bool = True, current_facts=None, opinion_text="",
           hidden_labels=None) -> str:
    """엔진 질문에 대한 가상 사장님 대답 한 줄.

    scenario: 시나리오 dict(facts·hidden_facts·unknown·persona_note·persona).
    question: {"text", "options", "slot", "kind"}.
    history: [{"role", "text"}] (role은 '사장님'/'엔진' 등).
    llm_fn: prompt(str) -> str. 주입 필수(숨은 항목 규칙 답변 제외).
    current_facts: changes 패치가 반영된 사실표(없으면 scenario facts).
    opinion_text: 공유방 멤버의 의견 충돌문(예: "연락 방법: 카카오톡 채널").
    hidden_labels: [(키, 표시 이름)] — 숨은 항목 규칙 답변용.
    """
    q = question or {}
    if is_hidden_question(q):
        return rule_hidden_answer(scenario.get("hidden_facts"), hidden_labels)
    facts = dict(current_facts) if current_facts is not None else facts_for_viewer(scenario, is_owner)
    # 방장이 아닌데 방장만 아는 사실을 직접 묻는 경우: 사실표에 없으므로 LLM이 "잘 모르겠어요" 한다.
    if not is_owner:
        facts = {k: v for k, v in facts.items()
                 if k in facts_for_viewer(scenario, is_owner=False)}
    prompt = build_prompt(
        facts=facts,
        persona_note=scenario.get("persona_note", ""),
        unknown=scenario.get("unknown") or [],
        question_text=q.get("text", ""),
        options=q.get("options") or [],
        history=history,
        opinion_text=opinion_text,
        hidden_labels=hidden_labels,
        persona=scenario.get("persona", ""),
        slot=q.get("slot") or "",
    )
    if llm_fn is None:
        raise RuntimeError("가상 사장님 LLM 함수가 없다. 가짜/실제 함수를 주입하라.")
    resp = llm_fn(prompt)
    return (resp or "").strip().splitlines()[0].strip() if (resp or "").strip() else NOT_SURE
