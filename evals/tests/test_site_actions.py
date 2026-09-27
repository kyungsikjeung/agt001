"""누를 것 점검 순수 함수 시험 (BOOKING_PLAN.md 트랙 O3 소유).

check_actions(링크 목록·버튼·폼·쪽 id·카드 사실 → 문제 목록)를 브라우저 없이 표 형태로 시험한다.
실행: .venv/bin/python -m pytest evals/tests/test_site_actions.py -q
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from evals.run_site_quality import (  # noqa: E402
    check_actions,
    collect_actions,
    summarize_action_problems,
)

FACTS = {"phone": "010-1234-5678", "booking_url": "https://booking.naver.com/abc",
         "channel_url": "https://pf.kakao.com/abc",
         "video_urls": ["https://www.youtube.com/watch?v=dQw4w9WgXcQ"]}

INQUIRY_FORM = {"action": "/api/inquiries/키",
                "fields": [{"name": "contact", "required": True},
                           {"name": "message", "required": True},
                           {"name": "agree", "required": True}]}

# (이름, links, buttons, forms, ids, 바라는 문제 종류 목록)
CASES = [
    ("맞는 전화", [{"href": "tel:01012345678"}], [], [], [], []),
    ("맞는 문자", [{"href": "sms:010-1234-5678"}], [], [], [], []),
    ("틀린 번호", [{"href": "tel:010-9999-8888"}], [], [], [], ["wrong_phone"]),
    ("카드 번호 없음", [{"href": "tel:010-1234-5678"}], [], [], [],
     ["wrong_phone"]),  # facts를 빈 번호로 바꿔서 시험 (아래에서 덮어씀)
    ("예약 주소", [{"href": "https://booking.naver.com/abc"}], [], [], [], []),
    ("채널 주소", [{"href": "https://pf.kakao.com/abc"}], [], [], [], []),
    ("영상 주소", [{"href": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"}], [], [], [], []),
    ("모르는 링크", [{"href": "https://example.com/모름"}], [], [], [], ["unknown_link"]),
    ("있는 내부 주소", [{"href": "#contact-title-inquiry"}], [], [],
     ["contact-title-inquiry"], []),
    ("빠진 내부 주소", [{"href": "#없는-칸"}], [], [], [], ["missing_anchor"]),
    ("죽은 #", [{"href": "#"}], [], [], [], ["dead"]),
    ("빈 href", [{"href": ""}], [], [], [], ["dead"]),
    ("자바스크립트", [{"href": "javascript:void(0)"}], [], [], [], ["dead"]),
    ("좋은 문의 폼", [], [], [INQUIRY_FORM], [], []),
    ("좋은 예약 폼", [],
     [], [{"action": "/api/bookings/키",
           "fields": [{"name": "phone", "required": True}, {"name": "agree", "required": True}]}],
     [], []),
    ("잘못된 폼 주소", [], [], [{"action": "/문의", "fields": INQUIRY_FORM["fields"]}], [], ["bad_form"]),
    ("required 없음", [], [], [{"action": "/api/inquiries/키", "fields": [{"name": "contact", "required": False}]}],
     [], ["bad_form"]),
    ("폼 안 전송 버튼은 통과", [],
     [{"type": "submit", "form_action": "/api/inquiries/키", "text": "문의 보내기"}],
     [INQUIRY_FORM], [], []),
    ("홀로 있는 버튼은 죽음", [{"href": "#contact-title-inquiry"}],
     [{"type": "button", "form_action": None, "text": "눌러보세요"}], [], ["contact-title-inquiry"], ["dead"]),
]

# 위 표에서 facts를 바꿔서 시험할 경우만 (이름 → facts)
FACTS_SWAP = {"카드 번호 없음": {"phone": "", "booking_url": "", "channel_url": "", "video_urls": []}}


class TestCheckActions(unittest.TestCase):
    def test_표(self) -> None:
        """경우마다 바라는 문제 종류와 꼭 같아야 한다."""
        for name, links, buttons, forms, ids, want in CASES:
            with self.subTest(name=name):
                facts = FACTS_SWAP.get(name, FACTS)
                got = [p["kind"] for p in check_actions(links, buttons, forms, ids, facts)]
                self.assertEqual(got, want, name)

    def test_개수_합치기(self) -> None:
        """빠진 # id·잘못된 폼은 죽은 버튼에 합치고, 죽음·틀림이 있으면 X."""
        problems = [{"kind": "missing_anchor", "detail": "x"}, {"kind": "bad_form", "detail": "y"},
                    {"kind": "wrong_phone", "detail": "z"}, {"kind": "unknown_link", "detail": "w"}]
        counts = summarize_action_problems(problems)
        self.assertEqual(counts, {"dead": 2, "wrong": 1, "unknown": 1})
        self.assertFalse(counts["dead"] == 0 and counts["wrong"] == 0)

    def test_모으기(self) -> None:
        """실제 공개본 조각에서 링크·폼·id를 뽑는다."""
        html = ('<section><h2 id="contact-title-inquiry">문의</h2>'
                '<a href="tel:01012345678">전화</a><a href="#">죽음</a>'
                '<form method="post" action="/api/inquiries/키">'
                '<input name="contact" required><button type="submit">보내기</button></form></section>')
        got = collect_actions(html)
        self.assertEqual([a["href"] for a in got["links"]], ["tel:01012345678", "#"])
        self.assertIn("contact-title-inquiry", got["ids"])
        self.assertEqual(got["forms"][0]["action"], "/api/inquiries/키")
        self.assertTrue(got["forms"][0]["fields"][0]["required"])
        self.assertEqual(got["buttons"][0]["form_action"], "/api/inquiries/키")
        problems = check_actions(got["links"], got["buttons"], got["forms"], got["ids"], FACTS)
        self.assertEqual([p["kind"] for p in problems], ["dead"])


if __name__ == "__main__":
    unittest.main()
