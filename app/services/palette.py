"""팔레트 규칙 검사·고르기 (BUILD_W1_W2 §1.5).

OKLCH 변환·WCAG 대비를 직접 구현한다(새 의존성 없음).
"""
import json
import math
from functools import lru_cache
from pathlib import Path

from app.config import settings

# 원형별 팔레트. 첫 값 = ① 정석, 마지막 = ③ 대비, 중간 = ② 분위기 후보.
ARCHETYPE_PALETTES = {
    "A": ("espresso", "coffee", "evergreen", "brick", "tomato", "cobalt"),
    "B": ("charcoal-gold", "ink-rose", "sage", "espresso", "plum"),
    "C": ("forest", "evergreen", "moss", "sage", "navy"),
    "D": ("navy", "cobalt", "evergreen", "plum", "tomato"),
    "E": ("moss", "brick", "coffee", "sage", "plum"),
    "F": ("sage", "ink-rose", "charcoal-gold", "espresso", "cobalt"),
    "G": ("evergreen", "navy", "moss", "brick", "tomato"),
    "H": ("cobalt", "plum", "navy", "evergreen", "tomato"),
}


@lru_cache(maxsize=None)
def _table() -> dict:
    path = settings.templates_dir / "tokens" / "palettes.json"
    return json.loads(path.read_text(encoding="utf-8"))


def library() -> list[str]:
    """팔레트 이름 목록."""
    return list(_table())


def get(name: str) -> dict:
    """팔레트 색 dict. 없으면 KeyError."""
    found = _table()[name]
    return {key: str(found[key]).lower() for key in ("primary", "accent", "ground", "ink")}


def _hex_to_rgb(code: str) -> tuple:
    code = code.strip().lstrip("#").lower()
    return (int(code[0:2], 16), int(code[2:4], 16), int(code[4:6], 16))


def _rel_luminance(code: str) -> float:
    """WCAG 상대 휘도."""

    def channel(value: int) -> float:
        part = value / 255.0
        if part <= 0.03928:
            return part / 12.92
        return ((part + 0.055) / 1.055) ** 2.4

    red, green, blue = _hex_to_rgb(code)
    return 0.2126 * channel(red) + 0.7152 * channel(green) + 0.0722 * channel(blue)


def contrast_ratio(first: str, second: str) -> float:
    """두 16진 색의 WCAG 대비율."""
    light = _rel_luminance(first)
    dark = _rel_luminance(second)
    if light < dark:
        light, dark = dark, light
    return (light + 0.05) / (dark + 0.05)


def _to_linear(value: int) -> float:
    part = value / 255.0
    if part <= 0.04045:
        return part / 12.92
    return ((part + 0.055) / 1.055) ** 2.4


def _rgb_to_oklch(red: int, green: int, blue: int) -> tuple:
    """0~255 RGB → (밝기, 채도, 색상각)."""
    red, green, blue = (_to_linear(v) for v in (red, green, blue))
    lone = 0.4122214708 * red + 0.5363325363 * green + 0.0514459929 * blue
    emm = 0.2119034982 * red + 0.6806995451 * green + 0.1073969566 * blue
    ess = 0.0883024619 * red + 0.2817188376 * green + 0.6299787005 * blue
    lone, emm, ess = lone ** (1 / 3), emm ** (1 / 3), ess ** (1 / 3)
    light = 0.2104542553 * lone + 0.7936177850 * emm - 0.0040720468 * ess
    axis_a = 1.9779984951 * lone - 2.4285922050 * emm + 0.4505937099 * ess
    axis_b = 0.0259040371 * lone + 0.7827717662 * emm - 0.8086757660 * ess
    chroma = math.hypot(axis_a, axis_b)
    hue = math.degrees(math.atan2(axis_b, axis_a)) % 360
    return (light, chroma, hue)


def hex_to_oklch(code: str) -> tuple:
    """16진 색 → (밝기, 채도, 색상각)."""
    return _rgb_to_oklch(*_hex_to_rgb(code))


def oklch_to_hex(light: float, chroma: float, hue: float) -> str:
    """OKLCH → 16진 색(범위 밖은 자름)."""
    turn = math.radians(hue)
    axis_a = chroma * math.cos(turn)
    axis_b = chroma * math.sin(turn)
    lone = light + 0.3963377774 * axis_a + 0.2158037573 * axis_b
    emm = light - 0.1055613458 * axis_a - 0.0638541728 * axis_b
    ess = light - 0.0894841775 * axis_a - 1.2914855480 * axis_b
    lone, emm, ess = lone ** 3, emm ** 3, ess ** 3
    red = +4.0767416621 * lone - 3.3077115913 * emm + 0.2309699292 * ess
    green = -1.2684380046 * lone + 2.6097574011 * emm - 0.3413193965 * ess
    blue = -0.0041960863 * lone - 0.7034186147 * emm + 1.7076147010 * ess

    def encode(value: float) -> int:
        value = max(0.0, min(1.0, value))
        if value <= 0.0031308:
            out = value * 12.92
        else:
            out = 1.055 * (value ** (1 / 2.4)) - 0.055
        return round(max(0, min(255, out * 255)))

    return "#{:02x}{:02x}{:02x}".format(encode(red), encode(green), encode(blue))


def inverse_hex(primary: str) -> str:
    """--inverse 근사값: 주색을 밝기 0.25·채도 최대 0.08로 바꿔 sRGB로."""
    light, chroma, hue = hex_to_oklch(primary)
    return oklch_to_hex(0.25, min(chroma, 0.08), hue)


def _hue_gap(first: float, second: float) -> float:
    gap = abs(first - second) % 360
    return min(gap, 360 - gap)


def check(name: str) -> list[str]:
    """§1.5 팔레트 규칙 위반 목록. 비어 있으면 통과."""
    try:
        pal = get(name)
    except KeyError:
        return [f"없는 팔레트: {name}"]
    broken = []
    plight, pchroma, phue = hex_to_oklch(pal["primary"])
    _, achroma, ahue = hex_to_oklch(pal["accent"])
    _, gchroma, _ = hex_to_oklch(pal["ground"])
    dark_primary = pchroma < 0.10 and plight <= 0.30
    if not (pchroma >= 0.10 or plight <= 0.30):
        broken.append(f"주색이 탁함: 채도 {pchroma:.3f}·밝기 {plight:.3f}")
    # 짙은 무채색 주색은 색상각이 무의미해서 강조색 선명도로 대신 본다.
    # coffee처럼 색상각이 벌어진 경우는 그대로 통과한다.
    if _hue_gap(ahue, phue) < 90 and not (dark_primary and achroma >= 0.12):
        broken.append(f"강조색이 주색과 같은 계열: 색상각 차이 {_hue_gap(ahue, phue):.0f}도")
    if gchroma > 0.012:
        broken.append(f"바탕이 누런 크림: 채도 {gchroma:.4f}")
    pairs = (
        ("글자", pal["ink"], pal["ground"], 7.0),
        ("주색", pal["primary"], pal["ground"], 4.5),
        ("강조색", pal["accent"], pal["ground"], 4.5),
        ("흰색·강조색", "#ffffff", pal["accent"], 4.5),
    )
    for label, first, second, bar in pairs:
        ratio = contrast_ratio(first, second)
        if ratio < bar:
            broken.append(f"{label} 대비 {ratio:.2f} (기준 {bar})")
    return broken


def _photo_color_uncached(path_str: str) -> dict | None:
    """사진 주요 색. 64px로 줄여 6색 양자화 뒤 픽셀 수 × 채도가 가장 큰 색."""
    from PIL import Image

    try:
        method = Image.Quantize.MEDIANCUT
    except AttributeError:  # 낡은 Pillow 예비
        method = 0
    try:
        with Image.open(path_str) as img:
            img = img.convert("RGB")
            img.thumbnail((64, 64))
            small = img.quantize(colors=6, method=method, dither=Image.Dither.NONE)
            counts = small.getcolors(maxcolors=small.width * small.height)
            if not counts:
                return None
            table = small.getpalette() or []
            best = None
            for count, index in counts:
                part = table[index * 3:index * 3 + 3]
                if len(part) < 3:
                    continue
                light, chroma, hue = _rgb_to_oklch(*part)
                if chroma < 0.03 or light < 0.15 or light > 0.95:
                    continue  # 무채색·너무 어둡거나 밝은 색은 빼기
                score = count * chroma
                if best is None or score > best[0]:
                    best = (score, light, chroma, hue)
    except Exception:
        return None
    if best is None:
        return None
    return {"L": best[1], "C": best[2], "H": best[3]}


@lru_cache(maxsize=256)
def _photo_color_cached(path_str: str, mtime_ns: int) -> tuple | None:
    """경로+수정 시각 기준 캐시. 못 읽으면 None을 그대로 기억한다."""
    found = _photo_color_uncached(path_str)
    if found is None:
        return None
    return (found["L"], found["C"], found["H"])


def photo_color(path) -> dict | None:
    """사진 파일 주요 색 {"L", "C", "H"}. 없거나 못 읽으면 None."""
    try:
        real = Path(path)
        stamp = real.stat().st_mtime_ns
    except (OSError, TypeError, ValueError):
        return None
    hit = _photo_color_cached(str(real), stamp)
    if hit is None:
        return None
    return {"L": hit[0], "C": hit[1], "H": hit[2]}


def _photo_hue(photo) -> float | None:
    """photo_color 결과 → 색상각. 모양이 다르면 None."""
    try:
        if isinstance(photo, dict):
            return float(photo["H"]) % 360
        return float(photo) % 360
    except (KeyError, TypeError, ValueError):
        return None


def _representative_hue(name: str) -> float:
    """팔레트 대표 색 색상각. 주색이 짙으면(밝기 0.30 이하) 강조색으로."""
    pal = get(name)
    light, _, hue = hex_to_oklch(pal["primary"])
    if light <= 0.30:
        _, _, hue = hex_to_oklch(pal["accent"])
    return hue


def pick(archetype: str, role: int, mood: str | None = None, used: tuple = (),
         photo: dict | None = None) -> str:
    """원형·역할로 팔레트 고르기. 모르는 원형은 A 표를 쓴다."""
    row = ARCHETYPE_PALETTES.get(archetype, ARCHETYPE_PALETTES["A"])
    if role == 3:
        return row[-1]
    if role == 2:
        cands = row[1:-1]
        # D43 ② 사장님 분위기: 사장님 말에서 나온 색은 업종 후보 밖이라도 규칙을 통과하면 쓴다
        if mood and mood not in used and (mood in cands or (mood in library() and not check(mood))):
            return mood
        # J2b 사진에 맞춘 색: mood가 없을 때 사진 색상각과 가장 가까운 후보
        hue = None if mood else _photo_hue(photo)
        if hue is not None:
            pool = [c for c in cands if c not in used] or list(cands)
            return min(pool, key=lambda name: _hue_gap(_representative_hue(name), hue))
        for cand in cands:
            if cand not in used:
                return cand
        return cands[0]
    return row[0]
