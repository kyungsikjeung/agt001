"""화면 글 → 읽을 글 (VOICE_QA_REQUIREMENTS FR-1)."""
from app.services import prd_engine as E
from app.services.voice_turn import speech_text


def test_question_drops_hint_and_reads_options_as_numbers():
    text = "사이트로 가장 이루고 싶은 것은 무엇인가요?\n1) 예약·문의 늘리기  2) 가게 알리기  3) 알아서 해주세요\n\n(질문 3/8 · '시안 먼저'라고 하시면 나머지는 알아서 채울게요)"
    s = speech_text(text)
    assert "질문 3/8" not in s and "시안 먼저" not in s and ")" not in s
    assert "1번, 예약, 문의 늘리기. 2번, 가게 알리기. 3번, 알아서 해주세요." in s


def test_multi_select_and_bullets():
    s = speech_text("해당되는 것을 모두 골라 주세요.\n주차 · 반려동물 동반 · 없음\n• 가게 이름: 달빛카페")
    assert s == "해당되는 것을 모두 골라 주세요. 주차, 반려동물 동반, 없음. 가게 이름: 달빛카페."


def test_hours_phone_url_and_emoji():
    s = speech_text("영업은 10~21시예요 ☕ 전화 010-0000-1234\n링크: https://example.com/a?b=1")
    assert "10~21시" in s and "https" not in s and "☕" not in s
    assert "전화 공일공, 공공공공, 일이삼사" in s  # 전화번호는 한 자리씩


def test_phone_read_digit_by_digit():
    """10/1 사장님: 01096567830을 '일억…'으로 읽었다 → 한 자리씩."""
    assert speech_text("번호는 01096567830이에요") == "번호는 공일공, 구육오육, 칠팔삼공이에요."
    assert "공이, 일이삼, 사오육칠" in speech_text("02-123-4567")
    assert "3000원" in speech_text("아메리카노 3000원")  # 가격은 그대로


def test_real_engine_question_has_no_symbols():
    card = E.new_card("cafe")
    q = {"slot": "goal", "kind": "single", "options": ["예약·문의 늘리기", "가게 알리기"], "text": "목적은?"}
    card["asked"] = 2
    s = speech_text(E.format_question(card, q))
    assert "(" not in s and "/" not in s and "1번," in s


def test_empty_stays_empty():
    assert speech_text("(질문 1/8)") == ""
