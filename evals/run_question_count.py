"""오프라인 질문 수 측정 (비공식, NIM 호출 없음).

추출은 시나리오 사실표를 아는 가짜 추출기, 사장님은 규칙 대답이다. 그래서 AI 품질이 아니라
엔진 흐름(무엇을 몇 번 묻나)만 본다. 공식 성적은 run_simulation --live로 잰다.

  python -m evals.run_question_count [시나리오 id 일부] [-v]
"""
import collections
import json
import os
import re
import sys

os.environ.setdefault("NIM_API_KEY", "offline")
from app import llm
from app.services import prd_engine as E, prd_schema as S
from evals import run_simulation as R, sim_owner

# 시안용 상황 질문 (D53 ③: 질문 한도 밖)
SITUATION_SLOTS = ("order_mode", "menu_categories", "team_mode")

CUR = {"facts": {}, "pending": None}


def _n(s):
    return re.sub(r"\s+", "", str(s))


def fake_chat_json(system, user, **kw):
    if "[사장님 메시지]" not in user:
        return "{}"
    text = user.split("[사장님 메시지] ", 1)[-1]
    nt = _n(text)
    ups = []
    for k, v in CUR["facts"].items():
        if k not in S.SLOTS:
            continue
        items = v if isinstance(v, list) else [x.strip() for x in re.split(r",", str(v))] if k in ("offerings",) else [v]
        for it in items:
            if it and _n(it) and _n(it) in nt:
                ups.append({"slot": k, "value": str(it)})
    p = CUR["pending"] or {}
    if p.get("slot") and p.get("kind") in ("single", "followup") and not any(u["slot"] == p["slot"] for u in ups):
        if text not in (sim_owner.NOT_SURE, S.LET_AI, E.LATER) and "모르" not in text and not re.search("바꿔|빼주|말고", text):
            ups.append({"slot": p["slot"], "value": text})
    return json.dumps({"updates": ups}, ensure_ascii=False)


def owner_answer(scenario=None, question=None, current_facts=None, hidden_labels=None, is_owner=True, **kw):
    q = question or {}
    facts = current_facts or {}
    unknown = set(scenario.get("unknown") or [])
    opts = q.get("options") or []
    if sim_owner.is_hidden_question(q):
        return sim_owner.rule_hidden_answer(scenario.get("hidden_facts"), hidden_labels)
    slot = q.get("slot")
    let_ai = scenario.get("persona") == "let_ai"
    if slot in facts and slot not in unknown:
        v = facts[slot]
        v = ", ".join(v) if isinstance(v, list) else str(v)
        for o in opts:
            if o and (o in v or v in o):
                return o
        if slot == "hours" and "매일 같은 시간" in opts and "매일" in v:
            return "매일 같은 시간"
        return v
    if let_ai and S.LET_AI in opts:
        return S.LET_AI
    if E.LATER in opts and slot in unknown:
        return E.LATER
    if S.LET_AI in opts:
        return S.LET_AI
    return sim_owner.NOT_SURE


class Adapter(R.PrdEngineAdapter):
    def new_card(self, sc):
        CUR["facts"] = sc.get("facts") or {}
        return super().new_card(sc)

    def turn(self, card, text, by=None, is_owner=True):
        CUR["pending"] = card.get("pending")
        return super().turn(card, text, by=by, is_owner=is_owner)


def main():
    # 가짜는 여기서만 끼운다 (import만으로 다른 코드가 바뀌지 않게)
    llm.chat_json = fake_chat_json
    sim_owner.answer = owner_answer
    args = [a for a in sys.argv[1:] if a != "-v"]
    verbose = "-v" in sys.argv
    scs = R.load_scenarios(args[0] if args else "", "")
    sit, solo, kinds, passed = [], [], collections.Counter(), 0
    for sc in scs:
        CUR["facts"] = dict(sc.get("facts") or {})
        if (sc.get("profile") or {}).get("say"):
            CUR["facts"]["price"] = sc["profile"]["say"]
        res = R.run_dialogue(sc, Adapter(), None)
        s = R.score_dialogue(sc, res)
        passed += s["passed"]
        for q in res["questions"]:
            kinds[(q["kind"], q["slot"])] += 1
        if not sc.get("group"):
            solo.append(s["questions"])
            sit.append(sum(1 for q in res["questions"] if q["slot"] in SITUATION_SLOTS))
        tag = "O" if s["passed"] else "X"
        print(f"{sc['id']:28s} q={s['questions']} {tag} acc={s['accuracy']} " + " ".join(
            f"{q['kind'][:4]}:{q['slot']}" for q in res["questions"]))
        if verbose:
            for m in res["transcript"]:
                print("   ", m["role"], m["text"])
        if not s["passed"]:
            print("    ", {k: s[k] for k in ("mismatches", "invented", "violations", "duplicates", "fill_rate")})
    print(f"\n통과 {passed}/{len(scs)} · 1:1 평균 질문 {sum(solo) / len(solo):.2f}회 (최대 {max(solo)}) · "
          f"상황 질문 빼면 {(sum(solo) - sum(sit)) / len(solo):.2f}회")
    for k, v in kinds.most_common():
        print(f"  {v:3d} {k}")


if __name__ == "__main__":
    main()
