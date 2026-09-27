"""잘못된 입력 시나리오 시험 (소유: evals/tests/test_wrong_scenarios.py).

실행: .venv/bin/python -m pytest evals/tests -q  (저장소 루트에서)
표준 라이브러리만 쓴다. 실제 NIM 호출 없음 — 가짜 카드로 판정 함수만 본다.
모든 날짜·시간 판단은 한국 시간 기준이며, 여기서는 날짜를 직접 다루지 않는다.
"""
import glob
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from evals import run_simulation as rs

try:
    from app.services import prd_schema as S
except ImportError:  # app 없이 돌 때의 최소 대체값
    class _S:  # noqa
        FILLED = "filled"
        SLOTS = {k: None for k in (
            "business_type", "shop_name", "goal", "target", "offerings",
            "sections", "features", "exclude", "contact_method", "phone",
            "hours", "location", "price", "detail", "booking_url", "staff")}
        INDUSTRIES = {}
    S = _S()

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
SCEN_DIR = os.path.join(TESTS_DIR, "..", "scenarios")
WRONG_DIR = os.path.join(TESTS_DIR, "..", "scenarios_wrong")

WRONG_IDS = ("cafe-wrong_input", "restaurant-wrong_input", "salon-wrong_input",
             "pension-wrong_input", "workshop-wrong_input", "academy-wrong_input")


def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _hidden_keys(industry):
    try:
        return {k for k, _lb in S.INDUSTRIES[industry].hidden}
    except Exception:
        return set()


def _base_scenario():
    # 판정 시험용 최소 시나리오 (가게 이름 하나만 필수)
    return {"id": "t-wrong", "industry": "cafe", "persona": "wrong_input",
            "facts": {"shop_name": "언덕위 카페"},
            "unknown": [],
            "expect": {"required": ["shop_name"], "placeholder": [],
                       "must_not_invent": [], "max_questions": 8,
                       "must_not_store": ["010-123-45"]}}


def _result(card_slots):
    return {"final_card": {"slots": card_slots, "hidden": {}},
            "transcript": [{"role": "사장님", "name": "사장님", "text": "언덕위 카페"}],
            "questions": [], "current_facts": {"shop_name": "언덕위 카페"},
            "confirmed": False, "turns": 1}


class TestWrongScenarioFormat(unittest.TestCase):
    def test_여섯개_파일이_있다(self):
        paths = sorted(glob.glob(os.path.join(WRONG_DIR, "*.json")))
        self.assertEqual(len(paths), 6)
        self.assertEqual(sorted(os.path.basename(p) for p in paths),
                         sorted(s + ".json" for s in WRONG_IDS))

    def test_형식_키를_지킨다(self):
        for sid in WRONG_IDS:
            sc = _load(os.path.join(WRONG_DIR, sid + ".json"))
            self.assertEqual(sc["persona"], "wrong_input", sid)
            for key in ("id", "industry", "persona", "persona_note", "first_message",
                        "facts", "unknown", "hidden_facts", "changes", "group", "expect"):
                self.assertIn(key, sc, sid)
            expect = sc["expect"]
            for key in ("required", "placeholder", "must_not_invent",
                        "max_questions", "must_not_store"):
                self.assertIn(key, expect, sid)
            self.assertEqual(expect["max_questions"], 8, sid)
            bad = expect["must_not_store"]
            self.assertIsInstance(bad, list, sid)
            self.assertTrue(bad and all(isinstance(b, str) and b for b in bad), sid)
            # 틀린 값은 사실표나 첫 메시지에 그대로 있어야 한다
            blob = " ".join(str(v) for v in sc["facts"].values())
            blob += " " + sc["first_message"]
            self.assertTrue(any(b in blob for b in bad), sid)
            # 사실 키는 칸 표에 있는 키만 쓴다
            for k in sc["facts"]:
                self.assertIn(k, S.SLOTS, sid)
            # 숨은 항목은 업종 표 키만, 2개 이상, 참·거짓 섞음
            hidden = sc["hidden_facts"] or {}
            self.assertGreaterEqual(len(hidden), 2, sid)
            self.assertTrue(set(hidden) <= _hidden_keys(sc["industry"]), sid)
            vals = list(hidden.values())
            self.assertTrue(any(v is True or (isinstance(v, str) and v.strip()) for v in vals), sid)
            self.assertTrue(any(v is False for v in vals), sid)

    def test_기존_36개는_손대지_않는다(self):
        old = sorted(glob.glob(os.path.join(SCEN_DIR, "*.json")))
        self.assertEqual(len(old), 36)
        for p in old:
            sc = _load(p)
            self.assertNotIn("must_not_store", sc.get("expect") or {}, p)


class TestMustNotStore(unittest.TestCase):
    def test_그대로_저장하면_걸린다(self):
        card = {"slots": {"phone": {"value": "010-123-45", "status": S.FILLED}}}
        hits = rs.find_stored_bad_values(card, ["010-123-45"])
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["slot"], "phone")

    def test_숫자만_같아도_걸린다(self):
        card = {"slots": {"phone": {"value": "01012345", "status": S.FILLED}}}
        hits = rs.find_stored_bad_values(card, ["010-123-45"])
        self.assertEqual(len(hits), 1)

    def test_주민번호_하이픈_없어도_걸린다(self):
        card = {"slots": {"phone": {"value": "9001011234567", "status": S.FILLED}}}
        hits = rs.find_stored_bad_values(card, ["900101-1234567"])
        self.assertEqual(len(hits), 1)

    def test_자리표시나_가정은_저장으로_세지_않는다(self):
        for status in ("placeholder", "assumed", "empty"):
            card = {"slots": {"phone": {"value": "010-123-45", "status": status}}}
            self.assertEqual(rs.find_stored_bad_values(card, ["010-123-45"]), [], status)

    def test_깨끗한_카드는_통과한다(self):
        card = {"slots": {"shop_name": {"value": "언덕위 카페", "status": S.FILLED}}}
        self.assertEqual(rs.find_stored_bad_values(card, ["010-123-45"]), [])

    def test_점수에_위반으로_잡힌다(self):
        sc = _base_scenario()
        bad_card = {"shop_name": {"value": "언덕위 카페", "status": S.FILLED},
                    "phone": {"value": "010-123-45", "status": S.FILLED}}
        score = rs.score_dialogue(sc, _result(bad_card))
        self.assertTrue(any(v["kind"] == "stored_bad_value" for v in score["violations"]))
        self.assertFalse(score["passed"])

    def test_다시_물어_비우면_위반이_없다(self):
        sc = _base_scenario()
        clean_card = {"shop_name": {"value": "언덕위 카페", "status": S.FILLED},
                      "phone": {"value": None, "status": "placeholder"}}
        score = rs.score_dialogue(sc, _result(clean_card))
        self.assertFalse(any(v["kind"] == "stored_bad_value" for v in score["violations"]))
        self.assertTrue(score["passed"])

    def test_기존_시나리오는_동작이_같다(self):
        sc = _base_scenario()
        del sc["expect"]["must_not_store"]
        bad_card = {"shop_name": {"value": "언덕위 카페", "status": S.FILLED},
                    "phone": {"value": "010-123-45", "status": S.FILLED}}
        score = rs.score_dialogue(sc, _result(bad_card))
        self.assertFalse(any(v["kind"] == "stored_bad_value" for v in score["violations"]))


class TestScenarioDir(unittest.TestCase):
    def test_기본은_기존_36개다(self):
        self.assertEqual(len(rs.load_scenarios()), 36)

    def test_폴더를_바꾸면_6개다(self):
        got = rs.load_scenarios("", WRONG_DIR)
        self.assertEqual(len(got), 6)
        self.assertEqual(sorted(s["id"] for s in got), sorted(WRONG_IDS))

    def test_바꾼_폴더에서도_이름_걸러진다(self):
        got = rs.load_scenarios("cafe", WRONG_DIR)
        self.assertEqual([s["id"] for s in got], ["cafe-wrong_input"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
