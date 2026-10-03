"""전화번호 저장 형식 (10/4): 숫자만 넣어도 하이픈 표준 표기로 저장한다. 프런트 phone.ts와 같은 규칙."""
import pytest

from app.services.phone_format import format_phone


@pytest.mark.parametrize("raw,want", [
    ("01096567830", "010-9656-7830"),
    ("010 9656 7830", "010-9656-7830"),
    ("010.9656.7830", "010-9656-7830"),
    ("+82 10-9656-7830", "010-9656-7830"),
    ("021234567", "02-123-4567"),
    ("0212345678", "02-1234-5678"),
    ("0311234567", "031-123-4567"),
    ("15881234", "1588-1234"),
    ("050712345678", "0507-1234-5678"),
])
def test_numbers_get_standard_hyphens(raw, want):
    assert format_phone(raw) == want


@pytest.mark.parametrize("raw", ["", "카톡으로 문의", "010-1234", "12345", "010-1234-5678 사장님"])
def test_not_a_full_number_is_left_alone(raw):
    assert format_phone(raw) is None


def test_card_put_saves_digits_as_hyphenated(client):
    from tests.unit.test_card_api import _room
    rid = _room(client)
    for raw, saved in (("01096567830", "010-9656-7830"), ("카톡으로 문의", "카톡으로 문의")):
        r = client.put(f"/api/rooms/{rid}/card", json={"fields": {"phone": raw}}, headers={"X-Member-Id": "owner"})
        assert r.status_code == 200
        assert {x["key"]: x for x in r.json()["fields"]}["phone"]["value"] == saved
