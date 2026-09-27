"""요구사항 엔진 대화 시뮬레이션 실행기 (WP P-1e, 소유: evals/run_simulation.py).

TKQR 정의: 핵심 질문(= 시나리오 expect.required의 각 칸에 대한 첫 질문)을 얼마나 이른
턴에 했는지 재는 지표다. R을 필수 칸 집합, t_r을 칸 r을 처음 물은 엔진 질문 순번(1부터,
끝까지 묻지 않았으면 기여 0)이라 할 때 TKQR = (1/|R|) * Σ_{r∈R} (1/t_r).
1번째 질문에서 물으면 1.0, 늦을수록 감점된다. 범위는 [0, 1], 높을수록 좋다.
출처: RESEARCH.md §3 (ReqElicitGym), PLAN §7 성적표에 IRE·TKQR 추가.

IRE 정의: 사실표 hidden_facts에서 true인 항목 중 대화로 끌어낸(카드 hidden.selected에
들었거나 사장님 발화에서 표시 이름이 나온) 비율. 범위는 [0, 1].

사용법:
  python -m evals.run_simulation [--only pension-terse] [--out docs/product/evals/simulation-<날짜>.md]
  python -m evals.run_simulation --smoke            # 오프라인 자가 점검(규칙 기반 가짜 사장님, 비공식)
  python -m evals.run_simulation --live             # 실제 NIM 호출(Claude가 실행, .env는 읽지 않음)

원칙:
- 표준 라이브러리 + app.services.prd_schema만 최상위에서 import한다.
- app.llm / app.services.prd_engine은 최상위에서 import하지 않는다(openai 의존 때문).
  엔진·추출 LLM·사장님 LLM·채점은 모두 인자로 주입받는다. 기본 엔진 어댑터는 호출될 때
  비로소 prd_engine을 늦게 import한다. 실제 NIM 호출은 --live 때만 일어난다.
- .env를 읽지 않는다. git/SSH/OCI/docker/배포 스크립트에 손대지 않는다.

대화 한계: 시나리오당 최대 MAX_TURNS=12턴(PLAN §4.1: 약 12번 호출 가정).
합격선: PLAN §4.1 — 필수 칸 채움률 95%↑, 정확도 95%↑, 지어낸 값 0개(전화·주소·가격
1건이면 불합격), 질문 수 평균 3회 이하(§7 v2 상한 8회로 함께 표기), 중복 질문 0회,
규칙 위반 0회.
"""

import argparse
import datetime
import glob
import json
import logging
import os
import re
import sys

try:
    from evals import sim_owner
except ImportError:  # 저장소 루트가 path에 없을 때 직접 실행 대비
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from evals import sim_owner

try:
    from app.services import prd_schema as S
except ImportError:  # app 없이 규칙 상수만으로 돌 때의 최소 대체값
    class _S:  # noqa
        FILLED = "filled"
        ASSUMED = "assumed"
        PLACEHOLDER = "placeholder"
        PENDING_OWNER = "pending_owner"
        EMPTY = "empty"
        REJECTED = "rejected"
        LET_AI = "알아서 해주세요"
        MAX_QUESTIONS = 8
    S = _S()

MAX_TURNS = 12
SATISFIED = (S.FILLED, S.ASSUMED, S.PLACEHOLDER, S.REJECTED)
STYLE_WORDS = ("색상", " 색", "분위기", "배치", "폰트", "서체", "디자인 취향", "톤앤매너")
CRITICAL_SLOTS = ("phone", "location", "price")
CONFIRM_WORD = "확정합니다"


# ── 시나리오 ──────────────────────────────────────────────────────────

def scenario_dir() -> str:
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "scenarios")


def load_scenarios(only: str = "") -> list:
    paths = sorted(glob.glob(os.path.join(scenario_dir(), "*.json")))
    out = []
    for p in paths:
        with open(p, encoding="utf-8") as f:
            sc = json.load(f)
        if only and only not in sc.get("id", ""):
            continue
        out.append(sc)
    return out


def hidden_labels_for(scenario) -> list:
    """업종 hidden [(키, 표시 이름)]. prd_schema를 모르면 빈 목록."""
    try:
        ind = S.INDUSTRIES[(scenario.get("industry") or "other")]
        return list(ind.hidden)
    except Exception:
        return []


# ── 엔진 어댑터 (주입 지점) ───────────────────────────────────────────

class PrdEngineAdapter:
    """실제 prd_engine을 늦게 import해서 쓰는 기본 어댑터(--live 전용)."""

    def __init__(self):
        self._eng = None

    def _load(self):
        if self._eng is None:
            from app.services import prd_engine
            self._eng = prd_engine
        return self._eng

    def new_card(self, scenario) -> dict:
        return self._load().new_card()

    def turn(self, card, text, by=None, is_owner=True) -> dict:
        return self._load().turn(card, text, by=by, is_owner=is_owner)


def format_question_local(card, q) -> str:
    """엔진 질문을 대화 기록용 한 줄로. prd_engine.format_question과 같은 모양."""
    if not q:
        return ""
    if q.get("kind") == "multi":
        body = f"{q.get('text', '')} [" + " · ".join(q.get("options") or []) + "]"
    else:
        opts = "  ".join(f"{i + 1}) {o}" for i, o in enumerate(q.get("options") or []))
        body = f"{q.get('text', '')} {opts}".strip()
    asked = (card or {}).get("asked", "?")
    return f"{body} (질문 {asked})"


# ── 대화 ──────────────────────────────────────────────────────────────

def _owner_name(scenario, member_idx: int) -> tuple:
    """(화자 이름, is_owner). 공유방이면 멤버를 번갈아 내보낸다."""
    group = scenario.get("group")
    if not group:
        return "사장님", True
    members = group.get("members") or [{"name": "사장님", "role": "owner"}]
    m = members[member_idx % len(members)]
    return m.get("name", "참여자"), m.get("role", "member") == "owner"


def _opinion_text(scenario, member_idx: int, slot) -> str:
    group = scenario.get("group")
    if not group or not slot:
        return ""
    members = group.get("members") or []
    m = members[member_idx % len(members)] if members else {}
    opinions = m.get("opinions") or {}
    if slot in opinions:
        return f"이 사람은 '{slot}'에 대해 이렇게 생각한다: {opinions[slot]}"
    return ""


def run_dialogue(scenario, engine, owner_llm_fn, *, max_turns: int = MAX_TURNS) -> dict:
    """시나리오 하나를 끝까지 돌린다. transcript·final_card·questions를 돌려준다."""
    card = engine.new_card(scenario)
    transcript = []   # {"role", "name", "text"}
    questions = []    # {"turn", "slot", "kind", "text", "options"}
    current_facts = dict(scenario.get("facts") or {})
    changes = sorted(scenario.get("changes") or [], key=lambda c: c.get("after_question", 0))
    labels = hidden_labels_for(scenario)

    def say_owner(text, name, member_idx, change=False):
        entry = {"role": "사장님", "name": name, "text": text}
        if change:
            entry["change"] = True  # changes say: 질문 답이 아니라 도중 변경 발화
        transcript.append(entry)

    text = scenario.get("first_message", "")
    member_idx = 0
    name, is_owner = _owner_name(scenario, member_idx)
    say_owner(text, name, member_idx)
    member_idx += 1

    turn_no = 0
    while turn_no < max_turns:
        turn_no += 1
        out = engine.turn(card, text, by=name, is_owner=is_owner)
        q = out.get("question")
        if q:
            questions.append({"turn": turn_no, "slot": q.get("slot"),
                              "kind": q.get("kind"), "text": q.get("text", ""),
                              "options": list(q.get("options") or [])})
            transcript.append({"role": "엔진", "name": "엔진",
                               "text": format_question_local(card, q)})
        if out.get("done"):
            break
        if not q:  # 질문도 없고 done도 아니면 중단(엔진 이상)
            break
        # changes: after_question 시점에 say를 보낸다.
        asked = (card or {}).get("asked", len(questions))
        due = [c for c in changes if c.get("after_question", 0) == asked]
        if due:
            c = due[0]
            changes.remove(c)
            if isinstance(c.get("patch"), dict):
                current_facts.update(c["patch"])
            name, is_owner = _owner_name(scenario, member_idx)
            text = c.get("say", "")
            say_owner(text, name, member_idx, change=True)
            member_idx += 1
            continue
        name, is_owner = _owner_name(scenario, member_idx)
        opinion = _opinion_text(scenario, member_idx, (q or {}).get("slot"))
        text = sim_owner.answer(
            scenario=scenario, question=q, history=transcript,
            llm_fn=owner_llm_fn, is_owner=is_owner,
            current_facts=current_facts, opinion_text=opinion,
            hidden_labels=labels)
        say_owner(text, name, member_idx)
        member_idx += 1

    # 확정 단계: 최종 카드를 사실표와 비교해 틀린 곳은 고쳐 달라고 하고, 맞으면 확정.
    corrections = _find_corrections(scenario, current_facts, card)
    confirmed = not corrections
    extra_turns = 0
    while corrections and turn_no + extra_turns < max_turns and extra_turns < 2:
        c = corrections.pop(0)
        name, is_owner = "사장님", True  # 고치기는 방장이 한다
        text = f"{c['label']}는 {c['want']}예요. 고쳐 주세요."
        transcript.append({"role": "사장님", "name": name, "text": text})
        engine.turn(card, text, by=name, is_owner=True)
        extra_turns += 1
        corrections = _find_corrections(scenario, current_facts, card)
    if not corrections:
        confirmed = True
        transcript.append({"role": "사장님", "name": "사장님", "text": CONFIRM_WORD})

    return {"scenario_id": scenario.get("id"), "transcript": transcript,
            "final_card": card, "questions": questions,
            "current_facts": current_facts, "confirmed": confirmed,
            "turns": turn_no + extra_turns}


def _find_corrections(scenario, facts, card) -> list:
    """필수 칸 중 카드 값과 사실표가 다른 곳."""
    slots = (card or {}).get("slots", {})
    out = []
    for key in (scenario.get("expect") or {}).get("required", []):
        if key not in facts:
            continue
        want = facts[key]
        got = (slots.get(key) or {}).get("value")
        if not _value_matches(want, got):
            label = key
            try:
                ind = S.INDUSTRIES.get(scenario.get("industry") or "other")
                if ind is not None:
                    label = S.label_for(ind, key)
            except Exception:
                pass
            out.append({"slot": key, "label": label, "want": want, "got": got})
    return out


# ── 채점 ──────────────────────────────────────────────────────────────

def _norm(v) -> str:
    if isinstance(v, list):
        return " ".join(str(x) for x in v)
    return "" if v is None else str(v)


def _value_matches(fact, got) -> bool:
    """사실값과 카드값이 같은지. 여러 값 칸은 겹치는 항목이 하나라도 있으면 일치."""
    if got is None or got == "" or got == []:
        return False
    if isinstance(fact, list) or isinstance(got, list):
        # 사실표는 "아메리카노, 라떼"처럼 쉼표로 적힌 문자열인 경우가 많다
        f = fact if isinstance(fact, list) else re.split(r"\s*[,、]\s*", str(fact))
        g = got if isinstance(got, list) else [got]
        fs = {_nm(x) for x in f if _nm(x)}
        gs = {_nm(x) for x in g if _nm(x)}
        return bool(fs & gs)
    a, b = _nm(fact), _nm(got)
    if bool(a) and (a == b or a in b or b in a):
        return True
    # 시간·가격: 숫자 값이 같으면 일치("매일 10~21시" = "10시부터 밤 9시까지", 오후는 +12)
    try:
        from app.services.numbers import numbers_in, value_numbers
    except ImportError:
        return False
    fa = value_numbers(str(fact)) | numbers_in(str(fact))
    gb = value_numbers(str(got)) | numbers_in(str(got))
    gb |= {n + 12 for n in gb if isinstance(n, int) and 1 <= n <= 11}
    return bool(fa) and fa <= gb


def _nm(x) -> str:
    """채점 비교용: 띄어쓰기·문장부호를 빼고 비교한다("예약·문의 늘리기" = "예약 문의 늘리기")."""
    return re.sub(r"[^가-힣a-zA-Z0-9]", "", str(x)).lower()


def _transcript_text(transcript) -> str:
    return "\n".join(m.get("text", "") for m in transcript)


def _owner_text(transcript) -> str:
    return "\n".join(m.get("text", "") for m in transcript if m.get("role") == "사장님")


def score_dialogue(scenario, result) -> dict:
    """최종 카드 + 대화 기록을 사실표와 비교해 지표를 낸다(규칙 채점, LLM 불필요)."""
    from app.services.prd_engine import grounded_phrase  # 엔진과 같은 근거 기준 (늦은 import: 모듈 머리 주석 참고)
    card = result.get("final_card") or {}
    slots = card.get("slots", {})
    transcript = result.get("transcript") or []
    questions = result.get("questions") or []
    facts = result.get("current_facts") or dict(scenario.get("facts") or {})
    expect = scenario.get("expect") or {}
    required = expect.get("required") or []
    unknown = set(scenario.get("unknown") or [])
    all_text = _transcript_text(transcript)
    owner_text = _owner_text(transcript)
    digits_all = re.sub(r"\D", "", all_text)

    def status(k):
        return (slots.get(k) or {}).get("status", S.EMPTY)

    def value(k):
        return (slots.get(k) or {}).get("value")

    # 필수 칸 채움률: 사실이 있으면 값이 맞아야 하고, unknown이면 자리 표시여야 한다.
    filled_n = 0
    for k in required:
        if k in unknown or k not in facts:
            if status(k) in (S.PLACEHOLDER, S.FILLED, S.ASSUMED):
                filled_n += 1
        elif status(k) in (S.FILLED, S.ASSUMED) and value(k):
            filled_n += 1
    fill_rate = filled_n / len(required) if required else 1.0

    # 정확도: 채운 필수 칸 중 사실표와 일치하는 비율.
    match_n, denom = 0, 0
    mismatches = []  # 분석용: 어느 칸이 무엇으로 틀렸는지
    for k in required:
        if k in facts and status(k) in (S.FILLED, S.ASSUMED) and value(k):
            denom += 1
            if _value_matches(facts[k], value(k)):
                match_n += 1
            else:
                mismatches.append({"slot": k, "expected": facts[k], "got": value(k), "status": status(k)})
    accuracy = match_n / denom if denom else 1.0

    # 지어낸 값: filled인데 사실표에도 대화 어디에도 근거가 없는 값.
    invented = []
    for k, slot in slots.items():
        if slot.get("status") != S.FILLED or not slot.get("value"):
            continue
        vals = slot["value"] if isinstance(slot["value"], list) else [slot["value"]]
        fact_vals = facts.get(k)
        fvs = fact_vals if isinstance(fact_vals, list) else [fact_vals]
        bad_items = []
        for v in vals:
            s = str(v)
            if any(f is not None and _value_matches(f, v) for f in fvs):
                continue
            if s and s in all_text:
                continue
            digits = re.sub(r"\D", "", s)
            if digits and digits in digits_all:
                continue
            if k in CRITICAL_SLOTS or digits:
                # 전화·주소·가격과 숫자 있는 값은 기존 판정 그대로 둔다
                bad_items.append(v)
                continue
            # 숫자 없는 값은 엔진과 같은 공용 기준으로 본다. 근거는 사장님 말만 (엔진 선택지 글자는 근거가 아니다)
            if grounded_phrase(s, owner_text):
                continue
            bad_items.append(v)
        if bad_items:
            invented.append({"slot": k, "values": bad_items})
    critical = sorted({i["slot"] for i in invented if i["slot"] in CRITICAL_SLOTS})

    # 질문 수·최대 상한·TKQR용 첫 질문 턴.
    n_q = len(questions)
    first_turn = {}
    for q in questions:
        if q.get("slot") and q["slot"] not in first_turn:
            first_turn[q["slot"]] = q["turn"]
    tkqr_vals = [(1.0 / first_turn[k]) if k in first_turn else 0.0 for k in required]
    tkqr = sum(tkqr_vals) / len(tkqr_vals) if tkqr_vals else 1.0

    # 중복 질문: 이미 답한 칸을 또 묻기. 변경 발화(change)는 답이 아니므로 제외한다.
    asked, answered, dups, qi, last = set(), set(), 0, 0, None
    for m in transcript:
        if m.get("role") == "엔진":
            q_now = questions[qi] if qi < len(questions) else {}
            s = q_now.get("slot")
            qi += 1
            # 이어 묻기(followup)·방장 확인(owner_confirm)은 같은 칸을 다시 묻는 게 아니다
            if s and q_now.get("kind") in ("followup", "owner_confirm"):
                last = s
                continue
            if s:
                if s in asked and s in answered:
                    dups += 1
                asked.add(s)
                last = s
        elif m.get("role") == "사장님" and not m.get("change") and last:
            answered.add(last)

    # IRE: hidden_facts true 항목 중 끌어낸 비율.
    hidden_facts = scenario.get("hidden_facts") or {}
    labels = {k: lb for k, lb in hidden_labels_for(scenario)}
    true_keys = [k for k, v in hidden_facts.items()
                 if v is True or (isinstance(v, str) and v.strip())]
    selected = ((card.get("hidden") or {}).get("selected") or [])
    found = [k for k in true_keys
             if k in selected or (labels.get(k) and labels[k] in owner_text)]
    ire = len(found) / len(true_keys) if true_keys else 1.0

    # 규칙 위반: 선택지 없음·선택지 초과·한 턴 여러 질문·모양 질문.
    violations = []
    for q in questions:
        opts = q.get("options") or []
        if q.get("kind") != "multi" and not opts:
            violations.append({"turn": q["turn"], "kind": "no_options"})
        if len(opts) > 4 and q.get("kind") != "multi":
            # 여러 개 고르기(숨은 항목)는 항목이 5개 안팎이라 합계 4개 제한에서 뺀다.
            violations.append({"turn": q["turn"], "kind": "too_many_options"})
        if q.get("text", "").count("?") >= 2:
            violations.append({"turn": q["turn"], "kind": "multi_ask"})
        if any(w in q.get("text", "") for w in STYLE_WORDS):
            violations.append({"turn": q["turn"], "kind": "style_question"})
    max_q = (expect.get("max_questions") or S.MAX_QUESTIONS)

    passed = (fill_rate >= 0.95 and accuracy >= 0.95 and not invented
              and n_q <= max_q and dups == 0 and not violations)
    return {"scenario_id": scenario.get("id"), "fill_rate": round(fill_rate, 3),
            "accuracy": round(accuracy, 3), "mismatches": mismatches,
            "invented": invented, "critical_invented": critical,
            "questions": n_q, "max_questions": max_q, "duplicates": dups,
            "ire": round(ire, 3), "tkqr": round(tkqr, 3),
            "violations": violations, "confirmed": result.get("confirmed", False),
            "turns": result.get("turns", 0), "passed": passed}


# ── 보고서 ────────────────────────────────────────────────────────────

def _avg(rows, key) -> float:
    return round(sum(r[key] for r in rows) / len(rows), 3) if rows else 0.0


def write_markdown(results: list, path: str) -> str:
    """시나리오별 표 + 유형별·업종별 평균 + 합격선 대비 + 실패 대화 3개 전문."""
    skipped = [r["scenario"].get("id") for r in results if r.get("score") is None]
    results = [r for r in results if r.get("score") is not None]
    scores = [r["score"] for r in results]
    today = datetime.date.today().isoformat()
    n = len(scores)
    n_pass = sum(1 for s in scores if s["passed"])
    avg_q = _avg(scores, "questions")
    all_invented = sum(len(s["invented"]) for s in scores)
    critical_all = sorted({c for s in scores for c in s["critical_invented"]})

    L = [f"# 요구사항 엔진 대화 시뮬레이션 성적표 ({today})", "",
         f"대상 {n}개 시나리오 · 통과 {n_pass}/{n} · 평균 질문 {avg_q}회 · "
         f"지어낸 값 {all_invented}건(전화·주소·가격 {len(critical_all)}건) · "
         f"평균 IRE {_avg(scores, 'ire')} · 평균 TKQR {_avg(scores, 'tkqr')}", "",
         "## 시나리오별", "",
         "| 시나리오 | 채움률 | 정확도 | 지어냄 | 질문 | 중복 | IRE | TKQR | 위반 | 통과 |",
         "|---|---|---|---|---|---|---|---|---|---|"]
    for s in scores:
        inv = "-" if not s["invented"] else ",".join(i["slot"] for i in s["invented"])
        L.append(f"| {s['scenario_id']} | {s['fill_rate']} | {s['accuracy']} | {inv} | "
                 f"{s['questions']} | {s['duplicates']} | {s['ire']} | {s['tkqr']} | "
                 f"{len(s['violations'])} | {'O' if s['passed'] else 'X'} |")

    def group_of(key):
        groups = {}
        for s, r in zip(scores, results):
            g = r["scenario"].get(key, "?")
            groups.setdefault(g, []).append(s)
        return groups

    L += ["", "## 유형별 평균", "",
          "| 유형 | 채움률 | 정확도 | 평균 질문 | IRE | TKQR | 통과율 |",
          "|---|---|---|---|---|---|---|"]
    for g, rows in sorted(group_of("persona").items()):
        L.append(f"| {g} | {_avg(rows, 'fill_rate')} | {_avg(rows, 'accuracy')} | "
                 f"{_avg(rows, 'questions')} | {_avg(rows, 'ire')} | {_avg(rows, 'tkqr')} | "
                 f"{sum(r['passed'] for r in rows)}/{len(rows)} |")
    L += ["", "## 업종별 평균", "",
          "| 업종 | 채움률 | 정확도 | 평균 질문 | IRE | TKQR | 통과율 |",
          "|---|---|---|---|---|---|---|"]
    for g, rows in sorted(group_of("industry").items()):
        L.append(f"| {g} | {_avg(rows, 'fill_rate')} | {_avg(rows, 'accuracy')} | "
                 f"{_avg(rows, 'questions')} | {_avg(rows, 'ire')} | {_avg(rows, 'tkqr')} | "
                 f"{sum(r['passed'] for r in rows)}/{len(rows)} |")

    L += ["", "## 합격선 대비 (PLAN §4.1, 질문 상한은 §7 v2=8회 병기)", "",
          "| 지표 | 합격선 | 이번 결과 | 판정 |",
          "|---|---|---|---|"]
    checks = [
        ("필수 칸 채움률", "95% 이상", f"{_avg(scores, 'fill_rate') * 100:.1f}%",
         _avg(scores, "fill_rate") >= 0.95),
        ("정확도", "95% 이상", f"{_avg(scores, 'accuracy') * 100:.1f}%",
         _avg(scores, "accuracy") >= 0.95),
        ("지어낸 값", "0개 (전화·주소·가격 1건이면 불합격)", f"{all_invented}건",
         all_invented == 0),
        ("질문 수", "평균 3회 이하, 최대 5회 (§7 v2: 최대 8회)",
         f"평균 {avg_q}회, 최대 {max(s['questions'] for s in scores) if scores else 0}회",
         avg_q <= 3 and all(s["questions"] <= 8 for s in scores)),
        ("중복 질문", "0회", f"{sum(s['duplicates'] for s in scores)}회",
         all(s["duplicates"] == 0 for s in scores)),
        ("규칙 위반", "0회", f"{sum(len(s['violations']) for s in scores)}회",
         all(not s["violations"] for s in scores)),
    ]
    for name, line, got, ok in checks:
        L.append(f"| {name} | {line} | {got} | {'O' if ok else 'X'} |")

    failed = [r for r in results if not r["score"]["passed"]][:3]
    L += ["", "## 틀린 칸 (정확도 미달·지어냄)", "", "| 시나리오 | 칸 | 기대 | 실제 | 상태 |", "|---|---|---|---|---|"]
    for r in results:
        sc = r["score"]
        for m in sc.get("mismatches") or []:
            L.append(f"| {sc['scenario_id']} | {m['slot']} | {m['expected']} | {m['got']} | {m['status']} |")
        for inv in sc.get("invented") or []:
            L.append(f"| {sc['scenario_id']} | {inv['slot']} | (근거 없음) | {inv['values']} | filled |")
    L += ["", "## 실패 대화 전문 (최대 3개)", ""]
    if not failed:
        L.append("실패 없음.")
    for r in failed:
        L += [f"### {r['scenario'].get('id')}", ""]
        for m in r["result"]["transcript"]:
            L.append(f"- **{m.get('name', m.get('role'))}**: {m.get('text', '')}")
        L += ["", f"채점: {json.dumps(r['score'], ensure_ascii=False)}", ""]

    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")
    return path


# ── 실행 ──────────────────────────────────────────────────────────────

def rule_fallback_owner_llm(prompt: str) -> str:
    """오프라인 자가 점검용 결정적 대답(--smoke). 공식 성적에 쓰지 않는다."""
    import json as _j
    facts, unknown, options, opinion = {}, [], [], ""
    section = None
    for line in prompt.splitlines():
        if line.startswith("사장님 대답"):
            break
        if not line.strip():
            continue
        if line.startswith("[사실표]"):
            section = "facts"
            continue
        if line.startswith("[모르는 칸]"):
            section = "unknown"
            continue
        if line.startswith("[선택지]"):
            section = "options"
            continue
        if line.startswith("[이 사람의 의견]"):
            section = "opinion"
            continue
        if line.startswith("["):
            section = None
            continue
        if section == "facts" and line.strip().startswith("{"):
            try:
                facts = _j.loads(line.strip())
            except ValueError:
                pass
        elif section == "unknown":
            unknown = [w.strip() for w in line.split(",")]
        elif section == "options":
            options = [w.strip() for w in line.split("|")]
        elif section == "opinion":
            opinion += line
    values = []
    for v in facts.values():
        values += v if isinstance(v, list) else [v]
    for o in options:
        if o and any(o == str(v) or str(v) in o or o in str(v) for v in values if v):
            return o
    if opinion:
        for o in options:
            if o and o in opinion:
                return o
    for u in unknown:
        if u and u in prompt.split("[이번 질문]")[-1]:
            return sim_owner.NOT_SURE
    if S.LET_AI in options:
        return S.LET_AI
    for v in values:
        if v:
            return str(v) if not isinstance(v, list) else ", ".join(v)
    return sim_owner.NOT_SURE


def live_owner_llm(prompt: str) -> str:
    """실제 NIM 호출. --live 때만 쓴다. 여기서 import하므로 평소에는 openai가 필요 없다.
    무료 NIM은 몰아서 부르면 모든 모델이 503을 낼 때가 있어, 쉬었다가 몇 번 더 부른다."""
    import time
    from app import llm
    for attempt in range(4):
        try:
            return llm.chat([{"role": "user", "content": prompt}]) or sim_owner.NOT_SURE
        except Exception:
            if attempt == 3:
                raise
            time.sleep(5 * (attempt + 1))


# ── NIM 한도 감시 (r6: 한도에 걸린 채 돌면 작은 대비 모델이 답해 점수가 오염된다) ──

# 이만큼 대비 모델로 넘어가면 측정을 멈춘다. 정상 r4는 36개 전체에서 57번이었다.
MAX_FALLBACKS = 40
# 외부 장애(연결 끊김 등)로 이만큼 연달아 건너뛰면 멈춘다
MAX_SKIPS_IN_ROW = 3


class LimitWatch(logging.Handler):
    """app.llm이 남기는 "NIM 모델 … 실패 → 다음 모델" 경고를 센다. 앱 코드는 건드리지 않는다."""

    def __init__(self):
        super().__init__(logging.WARNING)
        self.fallbacks = 0
        self.rate_limits = 0

    def emit(self, record):
        msg = record.getMessage()
        if "다음 모델" in msg:
            self.fallbacks += 1
            self.rate_limits += "RateLimit" in msg


def quota_ok(watch: "LimitWatch", calls: int = 3) -> bool:
    """짧은 호출 몇 번에 주 모델이 한 번도 안 넘어가야 한도가 회복된 것으로 본다."""
    from app import llm
    before = watch.fallbacks
    for _ in range(calls):
        try:
            llm.chat_json("숫자 하나만 JSON으로 답하라.", '{"n": 1}을 그대로 돌려줘', timeout_sec=15.0, max_tokens=20)
        except Exception:
            return False
    return watch.fallbacks == before


def run_all(scenarios, engine, owner_llm_fn, watch: "LimitWatch | None" = None) -> list:
    import time
    results = []
    skipped_in_row = 0
    for i, sc in enumerate(scenarios, 1):
        # 진행 표시: 몇 번째·걸린 시간·통과 여부 (r6: 한도에 걸려 44분 동안 어디서 막혔는지 알 수 없었다)
        t0 = time.monotonic()
        try:
            res = run_dialogue(sc, engine, owner_llm_fn)
        except Exception as e:  # 한 시나리오의 외부 장애가 전체 실행을 멈추지 않게 하고, 결과에 남긴다
            print(f"[{i}/{len(scenarios)}] {sc.get('id')} 건너뜀 {type(e).__name__} {time.monotonic() - t0:.0f}초",
                  file=sys.stderr, flush=True)
            results.append({"scenario": sc, "result": None, "score": None, "error": type(e).__name__})
            skipped_in_row += 1
            if skipped_in_row >= MAX_SKIPS_IN_ROW:
                # 9/27 Zen 기준 측정: 인터넷이 끊겨 28개가 연달아 건너뛰어졌는데 "8개 중 8개 통과"로 끝났다.
                print(f"연결 중단: {skipped_in_row}개 연속 건너뜀 — {i}/{len(scenarios)}개에서 멈춤.", file=sys.stderr, flush=True)
                raise LimitStop(results)
            continue
        skipped_in_row = 0
        score = score_dialogue(sc, res)
        fb = f" 대비모델 누적 {watch.fallbacks}회" if watch else ""
        print(f"[{i}/{len(scenarios)}] {sc.get('id')} {'통과' if score['passed'] else '실패'} "
              f"{time.monotonic() - t0:.0f}초{fb}", file=sys.stderr, flush=True)
        results.append({"scenario": sc, "result": res, "score": score})
        if watch and watch.fallbacks >= MAX_FALLBACKS:
            print(f"한도 중단: 대비 모델 전환 {watch.fallbacks}회(한도 초과 {watch.rate_limits}회) — "
                  f"{i}/{len(scenarios)}개에서 멈춤. 점수가 오염되므로 공식 성적으로 쓰지 않는다.", file=sys.stderr, flush=True)
            raise LimitStop(results)
    return results


class LimitStop(Exception):
    def __init__(self, results):
        super().__init__("NIM 한도")
        self.results = results


def default_out_path() -> str:
    today = datetime.date.today().isoformat()
    return os.path.join("docs", "product", "evals", f"simulation-{today}.md")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="요구사항 엔진 대화 시뮬레이션 (T3)")
    ap.add_argument("--only", default="", help="시나리오 id 부분 일치 필터")
    ap.add_argument("--out", default="", help="결과 md 경로")
    ap.add_argument("--smoke", action="store_true", help="오프라인 자가 점검(비공식)")
    ap.add_argument("--live", action="store_true", help="실제 NIM 호출(Claude 실행용)")
    ap.add_argument("--no-precheck", action="store_true", help="--live 전 한도 점검 생략")
    args = ap.parse_args(argv)

    scenarios = load_scenarios(args.only)
    if not scenarios:
        print("시나리오가 없다.", file=sys.stderr)
        return 1
    watch = None
    if args.live:
        watch = LimitWatch()
        logging.getLogger("app.llm").addHandler(watch)
        if not args.no_precheck and not quota_ok(watch):
            print("한도 미회복: 짧은 호출에서 주 모델이 대비 모델로 넘어갔다. 측정하지 않는다.", file=sys.stderr)
            return 4
        engine, owner = PrdEngineAdapter(), live_owner_llm
    elif args.smoke:
        engine, owner = PrdEngineAdapter(), rule_fallback_owner_llm
        print("주의: --smoke는 규칙 기반 가짜 사장님이다. 공식 성적에 쓰지 말 것.")
    else:
        print("주입된 LLM이 없다. --smoke(자가 점검) 또는 --live(실제 호출)를 붙이라.",
              file=sys.stderr)
        return 2
    stopped = False
    try:
        results = run_all(scenarios, engine, owner, watch)
    except LimitStop as e:
        results, stopped = e.results, True
    except ModuleNotFoundError as e:
        print(f"필요한 패키지가 없다({e}). 실제 엔진 실행은 openai가 있는 환경에서 하라.",
              file=sys.stderr)
        return 3
    path = write_markdown(results, args.out or default_out_path())
    if stopped:
        with open(path, encoding="utf-8") as f:
            body = f.read()
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"> **중단(비공식)**: 한도·연결 문제로 멈춤(대비 모델 전환 {watch.fallbacks if watch else 0}회). "
                    f"{len(results)}/{len(scenarios)}개만 실행, 점수는 참고용.\n\n" + body)
        print(f"한도 중단 → {path}")
        return 4
    done = [r for r in results if r.get("score") is not None]
    n_pass = sum(1 for r in done if r["score"]["passed"])
    print(f"{len(done)}개 중 {n_pass}개 통과 (외부 장애로 건너뜀 {len(results) - len(done)}개) → {path}")
    return 0 if done and n_pass == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
