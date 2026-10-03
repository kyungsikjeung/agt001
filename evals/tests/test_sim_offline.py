"""--offline 부품 시험: 사실표에 없는 값은 만들지 않고, 시간 질문은 z3 기록처럼 답한다."""
import json
import unittest

from evals import sim_offline as O


class TestExtractFromFacts(unittest.TestCase):
    def test_only_values_said_in_text(self):
        facts = {"shop_name": "숯불향 고깃집", "offerings": "삼겹살, 목살", "phone": "010-0000-3305"}
        ups = O.extract_from_facts("삼겹살이 주력이에요", facts)
        self.assertEqual(ups, [{"slot": "offerings", "value": "삼겹살"}])

    def test_phone_and_hours(self):
        facts = {"phone": "010-0000-1101", "hours": "매일 11~21시"}
        ups = O.extract_from_facts("매일 11~21시, 번호는 010-0000-1101", facts)
        self.assertIn({"slot": "phone", "value": "010-0000-1101"}, ups)
        self.assertEqual([u["slot"] for u in ups].count("hours"), 1)

    def test_exclude_needs_remove_word(self):
        facts = {"exclude#0": ["포장·배달"]}
        self.assertEqual(O.extract_from_facts("포장도 해요", facts), [])
        self.assertEqual(O.extract_from_facts("포장·배달 안내는 빼주세요", facts),
                         [{"slot": "exclude", "value": "포장·배달"}])

    def test_fake_chat_json_routes_extract_and_review(self):
        ref = {"facts": {"shop_name": "작은숲"}}
        fn = O.fake_chat_json(ref)
        out = json.loads(fn("sys", "[사장님 메시지] 작은숲이에요"))
        self.assertEqual(out["updates"], [{"slot": "shop_name", "value": "작은숲"}])
        self.assertEqual(json.loads(fn("sys", "검토해 주세요")), {"missing": [], "conflicts": []})


class TestOfflineOwner(unittest.TestCase):
    def _prompt(self, question, facts):
        return f"[사실표]\n{json.dumps(facts, ensure_ascii=False)}\n[이번 질문]\n{question}\n사장님 대답 한 줄:"

    def test_picks_same_time_option_like_z3(self):
        owner = O.offline_owner_llm(lambda p: "규칙")
        q = "영업시간은 어떻게 되나요? 1) 매일 같은 시간 2) 요일마다 달라요"
        self.assertEqual(owner(self._prompt(q, {"hours": "매일 10~19시"})), "매일 같은 시간")

    def test_says_hours_when_asked_directly(self):
        owner = O.offline_owner_llm(lambda p: "규칙")
        q = "몇 시부터 몇 시까지 여나요?"
        self.assertEqual(owner(self._prompt(q, {"hours": "매일 10~19시"})), "매일 10~19시")

    def test_other_questions_go_to_fallback(self):
        owner = O.offline_owner_llm(lambda p: "규칙")
        self.assertEqual(owner(self._prompt("가게 이름이 무엇인가요?", {"hours": "매일 10~19시"})), "규칙")


if __name__ == "__main__":
    unittest.main()
