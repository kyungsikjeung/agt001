"""쿠폰 바코드 Code128-C SVG (STAMP_WAVE4_CONTRACT §3.3).

외부 호출·라이브러리 없음. 흰 바탕·검정 막대.
"""
from __future__ import annotations

# 시작 C
START_C = 105
# 멈춤
STOP = 106
# 양옆 조용한 여백 (모듈 수)
QUIET = 10

# ISO/IEC 15417 표. 값 0..105는 막대/여백 6개, 합 11모듈. 멈춤은 7개, 합 13모듈.
PATTERNS = (
    "212222",  # 0
    "222122",  # 1
    "222221",  # 2
    "121223",  # 3
    "121322",  # 4
    "131222",  # 5
    "122213",  # 6
    "122312",  # 7
    "132212",  # 8
    "221213",  # 9
    "221312",  # 10
    "231212",  # 11
    "112232",  # 12
    "122132",  # 13
    "122231",  # 14
    "113222",  # 15
    "123122",  # 16
    "123221",  # 17
    "223211",  # 18
    "221132",  # 19
    "221231",  # 20
    "213212",  # 21
    "223112",  # 22
    "312131",  # 23
    "311222",  # 24
    "321122",  # 25
    "321221",  # 26
    "312212",  # 27
    "322112",  # 28
    "322211",  # 29
    "212123",  # 30
    "212321",  # 31
    "232121",  # 32
    "111323",  # 33
    "131123",  # 34
    "131321",  # 35
    "112313",  # 36
    "132113",  # 37
    "132311",  # 38
    "211313",  # 39
    "231113",  # 40
    "231311",  # 41
    "112133",  # 42
    "112331",  # 43
    "132131",  # 44
    "113123",  # 45
    "113321",  # 46
    "133121",  # 47
    "313121",  # 48
    "211331",  # 49
    "231131",  # 50
    "213113",  # 51
    "213311",  # 52
    "213131",  # 53
    "311123",  # 54
    "311321",  # 55
    "331121",  # 56
    "312113",  # 57
    "312311",  # 58
    "332111",  # 59
    "314111",  # 60
    "221411",  # 61
    "431111",  # 62
    "111224",  # 63
    "111422",  # 64
    "121124",  # 65
    "121421",  # 66
    "141122",  # 67
    "141221",  # 68
    "112214",  # 69
    "112412",  # 70
    "122114",  # 71
    "122411",  # 72
    "142112",  # 73
    "142211",  # 74
    "241211",  # 75
    "221114",  # 76
    "413111",  # 77
    "241112",  # 78
    "134111",  # 79
    "111242",  # 80
    "121142",  # 81
    "121241",  # 82
    "114212",  # 83
    "124112",  # 84
    "124211",  # 85
    "411212",  # 86
    "421112",  # 87
    "421211",  # 88
    "212141",  # 89
    "214121",  # 90
    "412121",  # 91
    "111143",  # 92
    "111341",  # 93
    "131141",  # 94
    "114113",  # 95
    "114311",  # 96
    "411113",  # 97
    "411311",  # 98
    "113141",  # 99
    "114131",  # 100
    "311141",  # 101
    "411131",  # 102
    "211412",  # 103 시작 A
    "211214",  # 104 시작 B
    "211232",  # 105 시작 C
    "2331112",  # 106 멈춤
)


def _check(digits: str) -> None:
    """입력 검사. 빈 값·홀수 자리·숫자 아님은 ValueError."""
    if not isinstance(digits, str) or not digits:
        raise ValueError("빈 쿠폰 번호예요")
    if any(c not in "0123456789" for c in digits):
        raise ValueError("숫자만 돼요")
    if len(digits) % 2 == 1:
        raise ValueError("짝수 자리만 돼요")


def _expand(widths: str) -> str:
    """너비 표기 → '1'(막대)/'0'(여백) 비트열."""
    out = []
    for i, ch in enumerate(widths):
        out.append(("1" if i % 2 == 0 else "0") * int(ch))
    return "".join(out)


def _values(digits: str) -> list[int]:
    """두 자리씩 끊은 기호값 목록."""
    return [int(digits[i : i + 2]) for i in range(0, len(digits), 2)]


def checksum(values: list[int]) -> int:
    """검사값. (105 + Σ값×위치) % 103. 위치는 1부터."""
    return (START_C + sum(v * (i + 1) for i, v in enumerate(values))) % 103


def modules(digits: str) -> str:
    """막대/여백 패턴 ('1'/'0'). 조용한 여백 포함."""
    _check(digits)
    vals = _values(digits)
    syms = [START_C] + vals + [checksum(vals), STOP]
    return "0" * QUIET + "".join(_expand(PATTERNS[s]) for s in syms) + "0" * QUIET


def code128c_svg(digits: str, *, height: int = 80, module: int = 2) -> str:
    """짝수 자리 숫자 → Code128 코드 C SVG 문자열. 시작 C + 두 자리씩 + 검사값 + 멈춤."""
    _check(digits)
    pattern = modules(digits)
    width = len(pattern) * module
    text = " ".join(digits[i : i + 4] for i in range(0, len(digits), 4))
    total = height + 28
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {total}"'
        f' width="{width}" height="{total}" role="img" aria-label="쿠폰 번호 {digits}">',
        f'<rect x="0" y="0" width="{width}" height="{total}" fill="white"/>',
    ]
    i = 0
    n = len(pattern)
    while i < n:
        if pattern[i] == "1":
            j = i
            while j < n and pattern[j] == "1":
                j += 1
            parts.append(
                f'<rect x="{i * module}" y="0" width="{(j - i) * module}"'
                f' height="{height}" fill="black"/>'
            )
            i = j
        else:
            i += 1
    parts.append(
        f'<text x="{width // 2}" y="{height + 20}" text-anchor="middle"'
        f' font-size="16" font-family="monospace" fill="black">{text}</text>'
    )
    parts.append("</svg>")
    return "".join(parts)
