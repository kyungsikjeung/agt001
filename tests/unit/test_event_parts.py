"""초대·기념 부품 (청첩장 1단계): 날짜와 장소·양가 연락처·마음 전하실 곳.

부품마다 채움 / 빈칸(시안 자리 표시) / 공개본(빈 부품·예시 제외) / 걸러내기를 본다.
DB가 필요 없다: `pytest --noconftest tests/unit/test_event_parts.py`로도 돈다.
"""
import re

from app.services import site_render as SR

TOKENS = {"palette": "coffee", "font_pair": "sans-clean", "density": "comfortable", "radius": "soft", "image_style": "card"}


def _page(sections, public=False, edit=False):
    return SR.render_site({"tokens": TOKENS, "sections": sections}, site_key="k", public=public, edit=edit)


def _date(**content):
    return {"id": "when", "type": "event", "variant": "date", "content": content}


def _family(sides, **extra):
    return {"id": "call", "type": "family", "variant": "contacts", "content": {"sides": sides, **extra}}


def _gift(sides, **extra):
    return {"id": "gift", "type": "gift", "variant": "accounts", "content": {"sides": sides, **extra}}


# ---- 날짜와 장소 ----
def test_event_date_shows_korean_date_calendar_and_dday_hook():
    doc = _page([_date(date="2026-11-14", time="오후 1시 30분", venue="더채플앳청담 3층 그랜드홀")])
    assert "2026년 11월 14일 토요일" in doc and "오후 1시 30분" in doc and "더채플앳청담" in doc
    assert '<time datetime="2026-11-14">' in doc and 'data-dday="2026-11-14"' in doc
    assert "<caption>2026년 11월</caption>" in doc
    # 그날만 동그라미, 2026-11-01은 일요일이라 달력 첫 칸부터 1일
    assert doc.count('class="s-event__day"') == 1 and 'aria-label="14일, 예식 날"' in doc
    first_row = re.search(r"<tbody>\s*<tr>(.*?)</tr>", doc, re.S).group(1)
    assert re.search(r'<td class="s-sun">1</td>', first_row)
    assert "_EVENT_SCRIPT" not in doc and "data-dday" in doc and "<script>" in doc


def test_event_date_bad_or_missing_date_is_placeholder_and_dropped_when_public():
    for content in ({}, {"date": "11월 14일"}, {"date": "2026-02-30"}):
        assert "[예식 날짜·시간·장소 입력]" in _page([_date(**content)])
        assert 'data-section-id="when"' not in _page([_date(**content)], public=True)


def test_event_example_date_is_marked_and_not_published():
    assert "예시 날짜" in _page([_date(date="2026-11-14", example=True)])
    assert 'data-section-id="when"' not in _page([_date(date="2026-11-14", example=True)], public=True)


# ---- 연락하기 ----
SIDES = [
    {"side": "신랑측", "people": [{"role": "신랑", "name": "김민준", "phone": "010-1234-5678"},
                                 {"role": "아버지", "name": "김철수", "phone": "02-123-45"},
                                 {"role": "어머니", "name": ""}]},
    {"side": "신부측", "people": [{"role": "신부", "name": "이서연", "phone": "010 9876 5432"}]},
    {"side": "세 번째", "people": [{"role": "x", "name": "넘침"}]},
]


def test_family_contacts_two_sides_with_call_and_sms_only_for_valid_phones():
    doc = _page([_family(SIDES)])
    assert "<h3>신랑측</h3>" in doc and "<h3>신부측</h3>" in doc and "세 번째" not in doc
    assert 'href="tel:01012345678"' in doc and 'href="sms:01012345678"' in doc
    assert 'href="tel:01098765432"' in doc
    # 자리수 틀린 번호는 이름만, 이름 없는 사람은 뺀다
    assert "김철수" in doc and "tel:0212345" not in doc
    assert doc.count('class="s-family__person"') == 3


def test_family_contacts_empty_is_placeholder_and_dropped_when_public():
    assert "[신랑측·신부측 연락처 입력]" in _page([_family([])])
    assert 'data-section-id="call"' not in _page([_family([{"side": "신랑측", "people": [{"name": ""}]}])], public=True)
    assert 'data-section-id="call"' in _page([_family(SIDES)], public=True)


# ---- 마음 전하실 곳 ----
ACCOUNTS = [
    {"side": "신랑측", "accounts": [{"role": "신랑", "holder": "김민준", "bank": "국민은행", "number": "123456-01-234567"},
                                   {"role": "아버지", "holder": "김철수", "bank": "신한", "number": "12"},
                                   {"holder": "주민번호", "bank": "농협", "number": "900101-1234567"}]},
    {"side": "신부측", "accounts": [{"role": "신부", "holder": "이서연", "bank": "카카오뱅크", "number": "3333 01 2345678"}]},
]


def test_gift_accounts_fold_per_side_with_copy_button_and_clean_numbers():
    doc = _page([_gift(ACCOUNTS, note="참석이 어려우신 분들을 위해 적었어요")])
    assert doc.count('<details class="s-gift__side">') == 2 and "신랑측 계좌번호" in doc
    assert "국민은행 123456-01-234567" in doc and 'data-copy="국민은행 123456-01-234567"' in doc
    # 공백은 지운다, 너무 짧은 번호·주민등록번호 모양은 받지 않는다
    assert "카카오뱅크 3333012345678" in doc
    assert "김철수" not in doc and "900101" not in doc and "주민번호" not in doc
    # 복사 단추는 스크립트가 클립보드를 확인한 뒤에만 보인다
    assert re.search(r'<button[^>]*s-gift__copy[^>]*hidden>', doc)
    assert "참석이 어려우신 분들" in doc


def test_gift_accounts_empty_is_placeholder_and_dropped_when_public():
    assert "[양가 계좌번호 입력]" in _page([_gift([])])
    assert 'data-section-id="gift"' not in _page([_gift([])], public=True)
    assert 'data-section-id="gift"' not in _page([_gift(ACCOUNTS, example=True)], public=True)


# ---- 공용 ----
def test_event_script_only_when_needed_and_never_in_edit_preview():
    assert "data-copy" not in _page([_family(SIDES)]) and "<script>" not in _page([_family(SIDES)])
    assert "navigator.clipboard" in _page([_gift(ACCOUNTS)])
    assert "navigator.clipboard" in _page([_date(date="2026-11-14")], public=True)
    assert "navigator.clipboard" not in _page([_gift(ACCOUNTS), _date(date="2026-11-14")], edit=True)


def test_event_parts_escape_owner_text():
    doc = _page([_family([{"side": "<b>신랑측</b>", "people": [{"name": "<script>x</script>"}]}]),
                 _gift([{"side": "s", "accounts": [{"holder": '"><img>', "bank": "b", "number": "1234567890"}]}])])
    assert "<b>신랑측</b>" not in doc and "<script>x" not in doc and '"><img>' not in doc
