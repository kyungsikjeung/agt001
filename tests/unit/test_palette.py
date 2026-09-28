"""팔레트 규칙·고르기·사진 색 테스트 (DB 불필요)."""
from PIL import Image

from app.config import settings
from app.services import design_concept as DC
from app.services import design_variants as DV
from app.services import palette as P
from app.services import prd_engine as E
from app.services import prd_schema as S


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


def _solid(path, rgb, size=(100, 80)):
    Image.new("RGB", size, rgb).save(path)
    return path


def test_photo_color_solid_hues(tmp_path):
    """J2b: 단색 그림의 주요 색 색상각 (따뜻한 갈색·초록·파랑)."""
    brown = P.photo_color(_solid(tmp_path / "brown.png", (138, 90, 43)))
    assert set(brown) == {"L", "C", "H"} and 50 < brown["H"] < 80
    green = P.photo_color(_solid(tmp_path / "green.png", (47, 125, 58)))
    assert 130 < green["H"] < 160
    blue = P.photo_color(_solid(tmp_path / "blue.png", (43, 95, 191)))
    assert 250 < blue["H"] < 275
    again = P.photo_color(tmp_path / "brown.png")
    assert again == brown  # 경로+수정 시각 캐시


def test_photo_color_ignores_flat_colors(tmp_path):
    """J2b: 무채색만이면 None. 없는 파일·못 읽는 파일도 None."""
    assert P.photo_color(_solid(tmp_path / "gray.png", (128, 128, 128))) is None
    assert P.photo_color(_solid(tmp_path / "white.png", (255, 255, 255))) is None
    assert P.photo_color(_solid(tmp_path / "black.png", (0, 0, 0))) is None
    assert P.photo_color(tmp_path / "없음.jpg") is None
    broken = tmp_path / "broken.jpg"
    broken.write_bytes(b"not an image")
    assert P.photo_color(broken) is None


def test_pick_role2_photo(tmp_path):
    """J2b: ②는 사진 색상각과 가장 가까운 후보. 파랑 후보가 없으면 가장 가까운 것."""
    brown = P.photo_color(_solid(tmp_path / "brown.png", (138, 90, 43)))
    assert P.pick("A", 2, photo=brown) == "brick"  # 갈색 사진 → coffee·brick 쪽
    green = P.photo_color(_solid(tmp_path / "green.png", (47, 125, 58)))
    assert P.pick("A", 2, photo=green) == "evergreen"  # 초록 사진 → evergreen
    blue = P.photo_color(_solid(tmp_path / "blue.png", (43, 95, 191)))
    assert P.pick("A", 2, photo=blue) == "coffee"  # 후보에 파랑이 없어 가장 가까운 것
    assert P.pick("A", 2, photo=None) == "coffee"  # 사진 없음 → 첫 후보
    assert P.pick("A", 2, photo=green, used=("evergreen",)) == "coffee"  # 쓴 값 피함


def test_pick_mood_beats_photo_and_roles_unchanged(tmp_path):
    """J2b: 사장님 말한 색이 사진보다 먼저. ①③은 사진과 무관."""
    green = P.photo_color(_solid(tmp_path / "green.png", (47, 125, 58)))
    assert P.pick("A", 2, mood="brick", photo=green) == "brick"
    assert P.pick("A", 2, mood="brick", used=("brick",), photo=green) == "coffee"
    assert P.pick("A", 1, photo=green) == "espresso"
    assert P.pick("A", 3, photo=green) == "cobalt"


def test_pension_view_stays_green():
    """J2b: 실제 예시 사진으로 C 원형 ②를 고르면 초록 계열."""
    path = settings.templates_dir / "art" / "ex" / "pension-view.webp"
    assert P.pick("C", 2, photo=P.photo_color(path)) in {"evergreen", "moss", "sage"}


def _cafe_card():
    card = E.new_card("cafe")
    E._put(card, "business_type", "카페", S.FILLED, 1)
    E._put(card, "shop_name", "연남 느린오후", S.FILLED, 1)
    E._put(card, "offerings", ["아메리카노", "카페라떼"], S.FILLED, 1)
    E._put(card, "phone", "02-123-4567", S.FILLED, 1)
    E._put(card, "hours", "매일 10~21시", S.FILLED, 1)
    E._put(card, "location", "서울 마포구 연남로 12", S.FILLED, 1)
    card["turn"] = 1
    return card


def _photo_file(root, url, rgb):
    """업로드 주소에 해당하는 생성물 파일을 초록 단색으로 만든다."""
    rel = url[len("/uploads/"):]
    path = root / "uploads" / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (200, 150), rgb).save(path, quality=95)
    return path


def test_blueprint_v2_uses_owner_photo(tmp_path, monkeypatch):
    """J2b 새 경로: 사장님 사진(초록)이 있으면 ②가 사진에 가까운 evergreen."""
    monkeypatch.setattr(settings, "generated_dir", tmp_path)
    card = _cafe_card()
    _photo_file(tmp_path, "/uploads/room1/p1.jpg", (47, 125, 58))
    card["photos"] = [{"url": "/uploads/room1/p1.jpg", "caption": "매장 사진"}]
    got = [v["spec"]["tokens"]["palette"] for v in DV.variants(card)]
    assert got[0] == "espresso" and got[1] == "evergreen" and got[2] == "cobalt"


def test_blueprint_v2_spoken_color_beats_photo(tmp_path, monkeypatch):
    """J2b 새 경로: 사장님이 말한 색(brick)은 사진(초록)보다 먼저."""
    monkeypatch.setattr(settings, "generated_dir", tmp_path)
    card = _cafe_card()
    _photo_file(tmp_path, "/uploads/room1/p1.jpg", (47, 125, 58))
    card["photos"] = [{"url": "/uploads/room1/p1.jpg"}]
    card["concept"] = {**DC.rule_concept(card), "palette": "brick"}
    got = [v["spec"]["tokens"]["palette"] for v in DV.variants(card)]
    assert got[1] == "brick"


def test_blueprint_v2_rule_concept_is_not_spoken(tmp_path, monkeypatch):
    """J2b 새 경로: 규칙값과 같은 concept(coffee)는 말한 색이 아니라 사진이 이긴다."""
    monkeypatch.setattr(settings, "generated_dir", tmp_path)
    card = _cafe_card()
    _photo_file(tmp_path, "/uploads/room1/p1.jpg", (47, 125, 58))
    card["photos"] = [{"url": "/uploads/room1/p1.jpg"}]
    card["concept"] = DC.rule_concept(card)  # 카페 규칙 = coffee
    got = [v["spec"]["tokens"]["palette"] for v in DV.variants(card)]
    assert got[1] == "evergreen"


def test_blueprint_v2_uses_ai_hero_without_owner_photo(tmp_path, monkeypatch):
    """J2b 새 경로: 사장님 사진이 없으면 AI 예시 hero 색으로 ②를 고른다."""
    monkeypatch.setattr(settings, "generated_dir", tmp_path)
    card = _cafe_card()
    _photo_file(tmp_path, "/uploads/room1/ai-hero.jpg", (47, 125, 58))
    card["ai_images"] = {"hero": {"url": "/uploads/room1/ai-hero.jpg"}}
    got = [v["spec"]["tokens"]["palette"] for v in DV.variants(card)]
    assert got[1] == "evergreen"
