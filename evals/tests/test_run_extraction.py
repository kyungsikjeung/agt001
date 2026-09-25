"""WP P-1d: 추출 평가 실행기 채점 로직 시험 (가짜 추출기만 사용).

실행:
    python3.11 -m pytest evals/tests/test_run_extraction.py -v
    # pytest 가 없으면:
    python3.11 -m unittest evals.tests.test_run_extraction -v

실제 AI 호출 없음. openai 패키지 불필요 (runner 는 prd_engine 을 lazy import).
"""

import unittest

from evals.run_extraction import (
    actual_from_updates,
    local_grounded,
    run_all,
    run_one_case,
    score_case,
)


def fake_extract(updates):
    """고정 추출 목록을 돌려주는 가짜 추출기."""
    return lambda text, last_q: [dict(u) for u in updates]


class TestScoreCase(unittest.TestCase):
    def test_exact_match_passes(self):
        case = {"expect": {"shop_name": "바다정원"}, "must_not": ["phone", "location"]}
        actual = {"shop_name": ["바다정원"]}
        r = score_case(case, actual)
        self.assertTrue(r["passed"])
        self.assertEqual(r["matched"], 1)
        self.assertEqual(r["must_not_violations"], [])

    def test_substring_match_passes(self):
        # 기대 값이 추출 값에 포함되면 일치 (부분 문자열 포함)
        case = {"expect": {"hours": ["세 시"]}, "must_not": []}
        actual = {"hours": ["오후 세 시"]}
        r = score_case(case, actual)
        self.assertTrue(r["passed"])
        self.assertEqual(r["matched"], 1)

    def test_mismatch_fails(self):
        case = {"expect": {"shop_name": "바다정원"}, "must_not": []}
        actual = {"shop_name": ["파도소리"]}
        r = score_case(case, actual)
        self.assertFalse(r["passed"])
        self.assertEqual(r["reason"], "slot-mismatch")
        self.assertEqual(r["matched"], 0)

    def test_list_expect_scored_per_item(self):
        # 기대 리스트는 항목마다 각각 판정
        case = {"expect": {"offerings": ["아메리카노", "라떼"]}, "must_not": []}
        actual = {"offerings": ["아메리카노"]}
        r = score_case(case, actual)
        self.assertFalse(r["passed"])
        self.assertEqual(r["expected_total"], 2)
        self.assertEqual(r["matched"], 1)

    def test_must_not_violation_fails(self):
        # 칸이 일치해도 must_not 칸이 하나라도 있으면 실패
        case = {
            "expect": {"contact_method": "전화"},
            "must_not": ["phone"],
        }
        actual = {"contact_method": ["전화"], "phone": ["010-0000-1234"]}
        r = score_case(case, actual)
        self.assertFalse(r["passed"])
        self.assertEqual(r["must_not_violations"], ["phone"])
        self.assertEqual(r["reason"], "must-not-violated")

    def test_empty_expect_empty_actual_passes(self):
        # "알아서 해주세요"형: 빈 기대 + 빈 추출 → 통과
        case = {"expect": {}, "must_not": ["goal"]}
        r = score_case(case, {})
        self.assertTrue(r["passed"])
        self.assertTrue(r["empty_expect"])

    def test_empty_expect_with_extraction_fails(self):
        case = {"expect": {}, "must_not": ["goal"]}
        r = score_case(case, {"goal": ["예약 문의"]})
        self.assertFalse(r["passed"])
        self.assertEqual(r["reason"], "empty-expect-violated")

    def test_ungrounded_fact_is_discarded(self):
        # 사실 칸 근거 없는 값은 버려진 것으로 친다
        text = "전화로 예약 받아요"  # 번호 없음
        self.assertFalse(local_grounded("phone", "010-0000-1234", text))
        actual = actual_from_updates([{"slot": "phone", "value": "010-0000-1234"}], text)
        self.assertEqual(actual, {})
        case = {"expect": {}, "must_not": ["phone"]}
        r = score_case(case, actual)
        self.assertTrue(r["passed"])


class TestRunAll(unittest.TestCase):
    def test_run_all_with_fake_extractor(self):
        cases = [
            {
                "id": "t1",
                "industry": "cafe",
                "text": "아메리카노랑 소금빵이요",
                "last_question": "대표 메뉴는 무엇인가요?",
                "expect": {"offerings": ["아메리카노", "소금빵"]},
                "must_not": ["phone"],
                "note": "일치",
            },
            {
                "id": "t2",
                "industry": "cafe",
                "text": "전화요",
                "last_question": "손님 연락은 어떻게 받으실까요?",
                "expect": {"contact_method": "전화"},
                "must_not": ["phone"],
                "note": "must_not 위반 유도",
            },
        ]

        def router(text, last_q):
            if "소금빵" in text:
                return [
                    {"slot": "offerings", "value": "아메리카노"},
                    {"slot": "offerings", "value": "소금빵"},
                ]
            return [
                {"slot": "contact_method", "value": "전화"},
                {"slot": "phone", "value": "전화"},  # 비사실? phone 팩트+숫자 없음 → 버려짐
            ]

        summary = run_all(cases, router, use_engine_apply=False)
        self.assertEqual(summary["total_cases"], 2)
        # t2 의 phone="전화" 는 숫자 없는 사실 → '전화' 두 글자가 본문에 있어
        # grounded 통과이므로 must_not 위반 1건으로 집계된다.
        self.assertEqual(summary["must_not_slots"], 1)
        self.assertFalse(summary["verdict"])
        self.assertGreaterEqual(summary["avg_sec"], 0.0)
        self.assertGreaterEqual(summary["max_sec"], summary["avg_sec"])
        by_id = {r["id"]: r for r in summary["case_results"]}
        self.assertTrue(by_id["t1"]["passed"])
        self.assertFalse(by_id["t2"]["passed"])
        self.assertIn("elapsed_sec", by_id["t1"])

    def test_run_one_case_records_timing(self):
        case = {
            "id": "t3",
            "industry": "pension",
            "text": "알아서 해주세요",
            "last_question": "사이트로 가장 이루고 싶은 것은 무엇인가요?",
            "expect": {},
            "must_not": ["goal"],
            "note": "",
        }
        r = run_one_case(case, fake_extract([]), use_engine_apply=False)
        self.assertTrue(r["passed"])
        self.assertGreaterEqual(r["elapsed_sec"], 0.0)


if __name__ == "__main__":
    unittest.main()
