"""예약 신청 폼 부품 단위 테스트 (BOOKING_PLAN §2.3, 트랙 O1).

외부 호출 없음. 렌더 결과 문자열만 확인한다. DB를 쓰지 않는다.
"""
import copy
import json
import re

from pathlib import Path

from app.services.site_render import render_site

SAMPLES_DIR = Path(__file__).resolve().parents[2] / "templates" / "samples"


def _tokens():
    """카페 샘플의 토큰을 그대로 쓴다 (예약 폼은 토큰과 무관)."""
    sample = json.loads((SAMPLES_DIR / "cafe.json").read_text(encoding="utf-8"))
    return copy.deepcopy(sample["tokens"])


def _booking_spec(services=None, time_options=None, note="가게에서 확인 후 연락드려요"):
    """예약 폼 한 장짜리 명세를 만든다."""
    content = {}
    if services is not None:
        content["services"] = services
    if time_options is not None:
        content["time_options"] = time_options
    if note is not None:
        content["note"] = note
    return {
        "version": 3,
        "tokens": _tokens(),
        "locked": [],
        "sections": [
            {"id": "booking", "type": "booking", "variant": "form", "content": content},
        ],
    }


def test_액션과_제목과_버튼():
    out = render_site(_booking_spec(), site_key="가게키", retention_days=30)
    assert 'action="/api/bookings/가게키"' in out
    assert 'id="booking-title-booking"' in out
    assert "예약 신청" in out
    assert "예약 신청하기" in out


def test_필드이름_필수값():
    out = render_site(_booking_spec(), site_key="키1")
    for name in ("date", "time", "party", "name", "phone", "memo", "agree", "website"):
        assert f'name="{name}"' in out
    # 메모 칸은 300자 제한
    assert 'name="memo"' in out and 'maxlength="300"' in out
    # 인원은 1~20, 기본 1
    assert 'name="party"' in out and 'min="1"' in out and 'max="20"' in out
    assert 'value="1"' in out
    # 연락처는 전화 칸, 동의는 필수 체크
    assert 'name="phone"' in out and 'type="tel"' in out
    assert 'name="agree"' in out and 'value="yes"' in out
    # 필수 칸에는 required가 붙는다. 시간은 선택지가 없으면 선택 입력(펜션 등, BOOKING_PLAN §2.3 통합 변경)
    assert "required" not in re.search(r'<[^>]*name="time"[^>]*>', out).group(0)
    for name in ("date", "party", "phone", "agree"):
        tag = re.search(rf'<[^>]*name="{name}"[^>]*>', out).group(0)
        assert "required" in tag


def test_날짜범위는_HTML에_굳히지_않음_보관안내():
    # 스크립트 없는 공개본에 min/max를 넣으면 공개 날짜로 굳어 두 달 뒤엔 고를 날이 없다. 범위는 서버가 검사한다.
    out = render_site(_booking_spec(), site_key="키1", retention_days=30)
    date_tag = re.search(r'<[^>]*name="date"[^>]*>', out).group(0)
    assert "min=" not in date_tag and "max=" not in date_tag
    assert "60일 안에서" in out
    assert "30일 보관 후 삭제" in out


def test_시간선택있으면_select_없으면_time입력():
    out = render_site(
        _booking_spec(time_options=["10:00", "10:30"]), site_key="키1",
    )
    assert '<select id="booking-time-booking" name="time"' in out
    assert '<option value="10:00">10:00</option>' in out
    assert '<option value="10:30">10:30</option>' in out
    out2 = render_site(_booking_spec(time_options=[]), site_key="키1")
    assert '<select id="booking-time-booking"' not in out2
    assert '<input id="booking-time-booking" name="time" type="time"' in out2


def test_메뉴있으면_select_없으면_숨김():
    out = render_site(_booking_spec(services=["컷트", "염색"]), site_key="키1")
    assert '<select id="booking-service-booking" name="service"' in out
    assert '<option value="컷트">컷트</option>' in out
    out2 = render_site(_booking_spec(services=[]), site_key="키1")
    assert 'name="service"' not in out2


def test_스크립트없음_서비스이름_이스케이프():
    out = render_site(
        _booking_spec(services=["<script>alert(1)</script>"], time_options=["10:00"]),
        site_key="키1",
    )
    assert "<script" not in out
    assert "&lt;script&gt;" in out


def test_스팸칸과_동의필수():
    out = render_site(_booking_spec(), site_key="키1")
    assert 'name="website"' in out
    tag = re.search(r'<[^>]*name="agree"[^>]*>', out).group(0)
    assert "required" in tag
