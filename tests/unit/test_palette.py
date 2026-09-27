"""팔레트 규칙·고르기 테스트 (DB 불필요)."""
from app.services import palette as P


def test_library_has_13():
    names = P.library()
    assert len(names) == 13
    assert set(names) == {
        "espresso", "cobalt", "evergreen", "ink-rose", "plum",
        "coffee", "forest", "moss", "sage", "brick", "tomato",
        "navy", "charcoal-gold",
    }
    for name in names:  # 16진은 소문자
        for key in ("primary", "accent", "ground", "ink"):
            assert P.get(name)[key] == P.get(name)[key].lower()


def test_all_palettes_pass_check():
    for name in P.library():
        assert P.check(name) == [], f"{name}: {P.check(name)}"


def test_check_unknown_palette():
    assert P.check("no-such-palette") != []


def test_pick_role1_is_first():
    assert P.pick("A", 1) == "espresso"
    assert P.pick("B", 1) == "charcoal-gold"
    assert P.pick("H", 1) == "cobalt"


def test_pick_role3_is_contrast():
    assert P.pick("A", 3) == "cobalt"
    assert P.pick("B", 3) == "plum"
    assert P.pick("C", 3) == "navy"


def test_pick_role2_mood_and_used():
    assert P.pick("A", 2, mood="brick") == "brick"  # 후보면 mood
    assert P.pick("A", 2, mood="plum") == "plum"  # D43: 규칙을 통과한 사장님 색은 업종 후보 밖이라도 쓴다
    assert P.pick("A", 2, mood="없는색") == "coffee"  # 모르는 색이면 첫 후보
    assert P.pick("A", 2, mood="plum", used=("plum",)) == "coffee"  # 이미 쓴 색이면 후보에서
    assert P.pick("A", 2) == "coffee"
    assert P.pick("A", 2, used=("coffee",)) == "evergreen"  # 쓴 값 피함
    assert P.pick("A", 2, used=("coffee", "evergreen", "brick", "tomato")) == "coffee"


def test_pick_unknown_archetype_uses_a():
    assert P.pick("Z", 1) == P.pick("A", 1) == "espresso"
    assert P.pick("Z", 3) == P.pick("A", 3) == "cobalt"


def test_inverse_contrast_with_white():
    for name in P.library():
        inv = P.inverse_hex(P.get(name)["primary"])
        assert P.contrast_ratio("#ffffff", inv) >= 7.0, f"{name}: {inv}"
