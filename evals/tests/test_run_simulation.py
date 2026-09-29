"""T3 실행기·가상 사장님 시험 (소유: evals/tests/test_run_simulation.py).

실행: python3.11 -m evals.tests.test_run_simulation  (저장소 루트에서)
표준 라이브러리만 쓴다. 실제 NIM 호출 없음 — 결정적 가짜 LLM/가짜 엔진을 주입한다.
"""
import json
import re
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from evals import run_simulation as rs
from evals import sim_owner

SCEN_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scenarios")

FILLED, ASSUMED, PLACEHOLDER = "filled", "assumed", "placeholder"
SATISFIED = (FILLED, ASSUMED, PLACEHOLDER, "rejected")
FACT_SLOTS = ("phone", "hours", "location", "price")
LET_AI = "알아서 해주세요"
NOT_SURE = sim_owner.NOT_SURE

OPTIONS = {
    "business_type": ["펜션·숙박", "카페·식당", "미용실·공방·학원"],
    "shop_name": [],
    "goal": ["예약 문의 늘리기", "가게 알리기", "메뉴·가격 안내"],
    "offerings": [],
    "contact_method": ["전화", "카카오톡 채널", "예약 사이트 링크"],
    "hours": ["매일 같은 시간", "요일마다 달라요", "나중에 넣을게요"],
    "phone": ["나중에 넣을게요"],
    "location": ["나중에 넣을게요"],
    "target": ["초등학생", "중·고등학생", "성인"],
}


def load_scenario(sid):
    with open(os.path.join(SCEN_DIR, sid + ".json"), encoding="utf-8") as f:
        return json.load(f)


class FakeOwnerLLM:
    """사실표를 그대로 돌려주는 결정적 가짜. prompt의 표식([사실표]·[선택지]·[질문 칸] 등)을 읽는다."""

    def __init__(self):
        self.calls = 0

    def __call__(self, prompt: str) -> str:
        self.calls += 1
        facts, unknown, options, opinion, slot, qtext = {}, [], [], "", "", ""
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
            if line.startswith("[질문 칸]"):
                section = "slot"
                continue
            if line.startswith("[이번 질문]"):
                section = "qtext"
                continue
            if line.startswith("["):
                section = None
                continue
            if section == "facts" and line.strip().startswith("{"):
                try:
                    facts = json.loads(line.strip())
                except ValueError:
                    pass
            elif section == "unknown":
                unknown = [w.strip() for w in line.split(",") if w.strip() not in ("", "없음")]
            elif section == "options":
                options = [w.strip() for w in line.split("|")]
            elif section == "opinion":
                opinion += line
            elif section == "slot":
                slot = line.strip()
            elif section == "qtext":
                qtext += line
        values = []
        for v in facts.values():
            values += v if isinstance(v, list) else [v]
        values = [str(v) for v in values if v]
        # 방장 확인 질문: 인용된 값이 사실과 다르면 아니요.
        if "맞나요" in qtext and set(options) == {"네", "아니요"}:
            import re as _re
            m = _re.search(r"'([^']+)'", qtext)
            quoted = m.group(1) if m else ""
            want = facts.get(slot, "")
            return "네" if quoted and quoted == str(want) else "아니요"
        if opinion:
            for o in options:
                if o and o in opinion:
                    return o
        for o in options:  # 선택지가 맞으면 글자 그대로
            if o and any(o == v or v in o or o in v for v in values):
                return o
        if slot in unknown:
            return NOT_SURE
        if slot and slot in facts:
            v = facts[slot]
            return ", ".join(v) if isinstance(v, list) else str(v)
        if LET_AI in options:
            return LET_AI
        return NOT_SURE


def _tokens(s):
    import re as _re
    return [t for t in _re.split(r"[\s,·/()]+", s or "") if len(t) >= 2]


class FakeEngine:
    """최소 규칙 엔진. required 순서대로 묻고, 대답에서 사실을 뽑아 카드에 채운다."""

    def __init__(self, hidden_labels):
        self.labels = dict(hidden_labels or [])
        self.seen_is_owner = []

    def new_card(self, scenario):
        return {"slots": {}, "hidden": {"asked": False, "selected": []},
                "asked": 0, "pending": None, "done": False,
                "_facts": dict(scenario.get("facts") or {}),
                "_required": list((scenario.get("expect") or {}).get("required") or []),
                "_unknown": set(scenario.get("unknown") or [])}

    def _satisfied(self, card, k):
        return card["slots"].get(k, {}).get("status") in SATISFIED

    def _fill_from_text(self, card, text):
        for k, fv in card["_facts"].items():
            fvs = fv if isinstance(fv, list) else [fv]
            for v in fvs:
                v = str(v)
                compact_v, compact_t = v.replace(" ", ""), text.replace(" ", "")
                toks = _tokens(v)
                hit = (v and (v in text or compact_v in compact_t))
                hit = hit or (len(toks) >= 2 and sum(1 for t in toks if t in text) >= 2)
                hit = hit or (len(toks) == 1 and toks[0] in text)
                if hit:
                    card["slots"][k] = {"value": fv, "status": FILLED,
                                        "evidence": [], "by": None}
                    break

    def turn(self, card, text, by=None, is_owner=True):
        self.seen_is_owner.append(is_owner)
        t = (text or "").strip()
        p = card.get("pending")
        if not p and t:
            self._fill_from_text(card, t)  # 실제 엔진처럼 매 턴 추출한다
        if p and t:
            if p["kind"] == "multi":
                if t == "없음":
                    card["hidden"] = {"asked": True, "selected": []}
                else:
                    sel = [k for k, lb in self.labels.items() if lb in t]
                    card["hidden"] = {"asked": True, "selected": sel}
                card["pending"] = None
            elif p["kind"] == "owner_confirm":
                if t == "아니요":
                    card["slots"].pop(p["slot"], None)
                    fk = card["_facts"].get(p["slot"])
                    if fk:
                        card["slots"][p["slot"]] = {"value": fk, "status": FILLED,
                                                    "evidence": [], "by": "owner"}
                elif t == "네":
                    card["slots"][p["slot"]]["status"] = FILLED
                card["pending"] = None
            elif t == LET_AI:
                k = p["slot"]
                if k in FACT_SLOTS or k == "shop_name" or k in card["_unknown"]:
                    card["slots"][k] = {"value": None, "status": PLACEHOLDER,
                                        "evidence": [], "by": None}
                else:
                    card["slots"][k] = {"value": "AI가 정함", "status": ASSUMED,
                                        "evidence": [], "by": None}
                card["pending"] = None
            elif t in p.get("options", []):
                k = p["slot"]
                if k in FACT_SLOTS and not is_owner:
                    card["slots"][k] = {"value": t, "status": "pending_owner",
                                        "evidence": [], "by": by}
                else:
                    card["slots"][k] = {"value": t, "status": FILLED,
                                        "evidence": [], "by": None}
                card["pending"] = None
            elif t in (NOT_SURE, "나중에 넣을게요"):
                k = p["slot"]
                card["slots"][k] = {"value": None, "status": PLACEHOLDER,
                                    "evidence": [], "by": None}
                card["pending"] = None
            else:
                before = dict(card["slots"])
                self._fill_from_text(card, t)
                if card["slots"] == before:
                    pass  # 못 알아들음: pending 유지
                else:
                    card["pending"] = None
        # 방장 확인 대기
        for k, s in card["slots"].items():
            if s.get("status") == "pending_owner":
                card["asked"] += 1
                q = {"slot": k, "kind": "owner_confirm", "options": ["네", "아니요"],
                     "text": f"'{s['value']}'(으)로 받았어요. 방장님, 맞나요?"}
                card["pending"] = q
                return {"done": False, "question": q, "applied": [k]}
        missing = [k for k in card["_required"] if not self._satisfied(card, k)]
        if (not card["hidden"]["asked"] and self.labels
                and (len(card["_required"]) - len(missing) >= 3 or not missing)):
            card["asked"] += 1
            q = {"slot": None, "kind": "multi",
                 "options": list(self.labels.values()) + ["없음"],
                 "text": "해당되는 것을 모두 골라 주세요."}
            card["pending"] = q
            return {"done": False, "question": q, "applied": []}
        if missing and card["asked"] < 8:
            k = missing[0]
            card["asked"] += 1
            # 실제 엔진(next_question)은 단일 질문에 항상 "알아서 해주세요"를 붙인다.
            q = {"slot": k, "kind": "single",
                 "options": list(OPTIONS.get(k, [])) + [LET_AI],
                 "text": f"{k}을(를) 알려 주세요."}
            card["pending"] = q
            return {"done": False, "question": q, "applied": []}
        for k in card["_required"]:
            if not self._satisfied(card, k):
                if k in FACT_SLOTS or k in card["_unknown"]:
                    card["slots"][k] = {"value": None, "status": PLACEHOLDER,
                                        "evidence": [], "by": None}
                else:
                    card["slots"][k] = {"value": "기본값", "status": ASSUMED,
                                        "evidence": [], "by": None}
        card["hidden"]["asked"] = True
        card["pending"] = None
        card["done"] = True
        return {"done": True, "question": None, "applied": []}


def run_case(sid):
    sc = load_scenario(sid)
    eng = FakeEngine(rs.hidden_labels_for(sc))
    res = rs.run_dialogue(sc, eng, FakeOwnerLLM())
    return sc, eng, res, rs.score_dialogue(sc, res)


class TestRunSimulation(unittest.TestCase):
    def test_two_scenarios_end_to_end(self):
        """2개 시나리오를 끝까지 돌린다: 턴 상한·질문 상한을 지킨다."""
        for sid in ("pension-terse", "pension-talkative"):
            sc, eng, res, score = run_case(sid)
            self.assertLessEqual(res["turns"], 12, sid)
            self.assertLessEqual(score["questions"], score["max_questions"], sid)

    def test_perfect_run_scores(self):
        """짧게 답하는 시나리오: 채움률·정확도 1.0, 지어냄 0, 통과."""
        sc, eng, res, score = run_case("pension-terse")
        self.assertEqual(score["fill_rate"], 1.0)
        self.assertEqual(score["accuracy"], 1.0)
        self.assertEqual(score["invented"], [])
        self.assertEqual(score["duplicates"], 0)
        self.assertEqual(score["violations"], [])
        self.assertGreater(score["tkqr"], 0)
        self.assertTrue(score["passed"])

    def test_group_passes_on_agree_rate_not_question_count(self):
        """D52: 공유방은 질문 수가 상한을 넘어도 전원 동의(동의율 100%)면 그 항목은 통과로 본다."""
        sc, eng, res, score = run_case("pension-terse")
        self.assertIsNone(score["agree_rate"])  # 1:1은 기존대로 질문 수
        group = dict(sc, group={"members": [{"name": "사장님", "role": "owner"}, {"name": "딸"}]})
        many = dict(res, questions=list(res["questions"]) * 5, agree_rate=1.0)
        self.assertGreater(rs.score_dialogue(group, many)["questions"], score["max_questions"])
        self.assertTrue(rs.score_dialogue(group, many)["passed"])
        self.assertFalse(rs.score_dialogue(group, dict(many, agree_rate=0.0))["passed"])

    def test_invented_phone_is_critical_fail(self):
        """근거 없는 전화번호가 filled면 지어낸 값 + 불합격."""
        sc, eng, res, _ = run_case("pension-terse")
        card = res["final_card"]
        card["slots"]["phone"] = {"value": "010-1234-5678", "status": FILLED,
                                  "evidence": [], "by": None}
        score = rs.score_dialogue(sc, res)
        self.assertTrue(any(i["slot"] == "phone" for i in score["invented"]))
        self.assertIn("phone", score["critical_invented"])
        self.assertFalse(score["passed"])

    def test_hidden_rule_answer_without_llm(self):
        """숨은 항목 질문은 LLM 없이 규칙으로 답한다."""
        def boom(prompt):
            raise AssertionError("LLM을 부르면 안 된다")
        sc = load_scenario("pension-terse")  # parking/long_stay 참, bbq 거짓
        labels = rs.hidden_labels_for(sc)
        got = sim_owner.answer(
            scenario=sc, question={"text": "고르세요", "options": [], "slot": None,
                                   "kind": "multi"},
            history=[], llm_fn=boom, hidden_labels=labels)
        self.assertIn("주차", got)
        self.assertNotIn("바비큐", got)
        sc2 = dict(load_scenario("pension-talkative"))
        sc2["hidden_facts"] = {"bbq": False, "parking": False, "pet": False}
        got2 = sim_owner.answer(
            scenario=sc2, question={"text": "고르세요", "options": [], "slot": None,
                                    "kind": "multi"},
            history=[], llm_fn=boom, hidden_labels=rs.hidden_labels_for(sc2))
        self.assertEqual(got2, "없음")

    def test_tkqr_early_beats_late(self):
        """핵심 질문이 이를수록 TKQR이 높다. 정의: 평균(1/첫 질문 순번)."""
        sc = load_scenario("pension-terse")
        req = sc["expect"]["required"]
        self.assertEqual(rs.score_dialogue(
            sc, {"final_card": {"slots": {}, "hidden": {}}, "transcript": [],
                 "questions": [{"turn": 1, "slot": req[0], "kind": "single",
                                "text": "?", "options": ["a"]},
                               {"turn": 2, "slot": req[1], "kind": "single",
                                "text": "?", "options": ["a"]}],
                 "current_facts": {}, "confirmed": False, "turns": 2})["tkqr"],
            round((1.0 + 0.5) / len(req), 3))
        early = rs.score_dialogue(
            sc, {"final_card": {"slots": {}, "hidden": {}}, "transcript": [],
                 "questions": [{"turn": 1, "slot": k, "kind": "single",
                                "text": "?", "options": ["a"]} for k in req],
                 "current_facts": {}, "confirmed": False, "turns": 1})["tkqr"]
        late = rs.score_dialogue(
            sc, {"final_card": {"slots": {}, "hidden": {}}, "transcript": [],
                 "questions": [{"turn": 5, "slot": k, "kind": "single",
                                "text": "?", "options": ["a"]} for k in req],
                 "current_facts": {}, "confirmed": False, "turns": 5})["tkqr"]
        self.assertGreater(early, late)

    def test_duplicates_and_style_violation(self):
        """같은 칸을 또 물으면 중복, 모양 질문은 규칙 위반."""
        sc = load_scenario("pension-terse")
        qs = [{"turn": 1, "slot": "shop_name", "kind": "single",
               "text": "이름?", "options": ["a"]},
              {"turn": 2, "slot": "shop_name", "kind": "single",
               "text": "이름?", "options": ["a"]},
              {"turn": 3, "slot": "goal", "kind": "single",
               "text": "어떤 색 분위기가 좋으세요?", "options": ["빨강"]}]
        tr = [{"role": "사장님", "name": "사장님", "text": "처음 말"},
              {"role": "엔진", "name": "엔진", "text": "이름?"},
              {"role": "사장님", "name": "사장님", "text": "바다소리 펜션"},
              {"role": "엔진", "name": "엔진", "text": "이름?"},
              {"role": "사장님", "name": "사장님", "text": "바다소리 펜션"},
              {"role": "엔진", "name": "엔진", "text": "어떤 색 분위기가 좋으세요?"}]
        score = rs.score_dialogue(
            sc, {"final_card": {"slots": {}, "hidden": {}}, "transcript": tr,
                 "questions": qs, "current_facts": {}, "confirmed": False, "turns": 3})
        self.assertEqual(score["duplicates"], 1)
        self.assertTrue(any(v["kind"] == "style_question" for v in score["violations"]))
        self.assertFalse(score["passed"])

    def test_changes_patch_and_group_alternation(self):
        """도중에 바꾸면 사실표가 갱신되고, 공유방은 두 사람이 번갈아 말한다."""
        sc, _, res, score = run_case("cafe-changes_mind")
        self.assertIn("단체석 안내는 빼주세요", rs._transcript_text(res["transcript"]))
        self.assertEqual(res["current_facts"].get("price"), "라떼 5천5백원")
        sc2, eng2, res2, score2 = run_case("pension-group")
        names = {m.get("name") for m in res2["transcript"] if m.get("role") == "사장님"}
        self.assertGreaterEqual(len(names), 2)
        self.assertIn(True, eng2.seen_is_owner)
        self.assertIn(False, eng2.seen_is_owner)
        got = (res2["final_card"]["slots"].get("contact_method") or {}).get("value")
        self.assertEqual(got, "전화")  # 방장 결정이 이긴다


    def test_profile_gold_matches_owner_words(self):
        """프로필 정답의 가격·시간이 가상 사장님이 보는 말(say)과 맞는다 (D55 §3.3)."""
        from app.services import card_data
        from app.services import prd_engine as E
        scs = [s for s in rs.load_scenarios() if s.get("profile")]
        self.assertGreaterEqual(len(scs), 30)
        for sc in scs:
            say = sc["profile"].get("say", "")
            for patch in (c.get("patch") or {} for c in sc.get("changes") or []):
                if patch.get("price"):
                    say += ", " + patch["price"]  # 도중에 바뀐 가격이 정답 (아래에서 뒤 토막이 이긴다)
            segs = [x.strip() for x in re.split(r"(?<!\d),|,(?!\d)", say) if x.strip()]
            for item in sc["profile"]["items"]:
                seg = next((x for x in reversed(segs) if x.startswith(item["name"][:2])), "")
                if item["price_won"] is None:
                    self.assertFalse(seg, sc["id"])
                    self.assertIn("price", sc["unknown"], sc["id"])
                    continue
                self.assertEqual(card_data.price_won(seg), item["price_won"], (sc["id"], seg))
                if item.get("duration_min") is not None:
                    got = __import__("app.services.botmaker", fromlist=["x"]).parse_minutes(
                        E._PRICE_RE.sub(" ", seg).replace(item["name"], ""))
                    self.assertEqual(got, item["duration_min"], (sc["id"], seg))

    def test_score_profile(self):
        from app.services import prd_engine as E
        from app.services import prd_schema as S
        sc = {"profile": {"items": [{"name": "컷트", "price_won": 20000, "duration_min": 30},
                                    {"name": "펌", "price_won": 80000},
                                    {"name": "염색", "price_won": None}]}}
        card = E.new_card("salon")
        E._put(card, "offerings", ["컷", "펌", "염색"], S.FILLED, 1)
        card["price_pairs"] = {"컷": "2만원", "펌": "7만원", "염색": "5만원"}
        card["duration_pairs"] = {"컷": 30}
        p = rs.score_profile(sc, card)
        self.assertEqual((p["name_hit"], p["price_hit"], p["priced"], p["time_hit"]), (3, 1, 2, 1))
        self.assertEqual(p["invented_price"], [{"name": "염색", "got": [50000]}])
        self.assertIn("가격 짝", "\n".join(rs.profile_section([{"scenario_id": "x", "profile": p}])))


if __name__ == "__main__":
    unittest.main(verbosity=2)
