"""바코드 (STAMP_WAVE4_CONTRACT §5 테스트 7)."""
import pytest

from app.services import barcode as BC


def test_table_shape():
    """표 107개. 0..105는 6원소·합 11·서로 다름. 멈춤은 합 13."""
    assert len(BC.PATTERNS) == 107
    seen = set()
    for v in range(106):
        w = BC.PATTERNS[v]
        assert len(w) == 6
        assert sum(int(c) for c in w) == 11
        assert w not in seen
        seen.add(w)
    stop = BC.PATTERNS[106]
    assert stop == "2331112"
    assert len(stop) == 7
    assert sum(int(c) for c in stop) == 13


def test_checksum_known():
    """알려진 입력의 검사값."""
    assert BC.checksum([12, 34, 56, 78, 90, 12]) == 54
    assert BC.checksum([0, 0, 0, 0, 0, 0]) == 2


def test_modules_shape():
    """조용한 여백·길이·시작 패턴."""
    pat = BC.modules("123456789012")
    assert pat.startswith("0" * 10)
    assert pat.endswith("0" * 10)
    # 10 + 11*(시작 1 + 자료 6 + 검사 1) + 13(멈춤) + 10
    assert len(pat) == 10 + 11 * (1 + 6 + 1) + 13 + 10
    assert pat[10 : 10 + 11] == "11010011100"


def test_svg_basic():
    """SVG에 스크립트 없음, 라벨·숫자 있음."""
    svg = BC.code128c_svg("123456789012")
    assert "<script" not in svg
    assert 'aria-label="쿠폰 번호 123456789012"' in svg
    assert "1234 5678 9012" in svg
    assert 'role="img"' in svg
    assert "<rect" in svg
    assert "<text" in svg
    assert "class" not in svg


def test_value_errors():
    """빈 값·홀수 자리·숫자 아님은 ValueError."""
    for bad in ("", "123", "12345", "abcdefghijkl", "12345678901a", "12 34"):
        with pytest.raises(ValueError):
            BC.code128c_svg(bad)
        with pytest.raises(ValueError):
            BC.modules(bad)
