"""선생님 직접 편집 (S1, BUILDER_FIX_1003_CONTRACT): DB 없이 --noconftest로 돈다.

clean_staff 검사(길이·중복·빈 이름·12명), staff_list·_fill_staff가 staff_edit를 쓰는지,
사장님 사진(staff:이름) 우선, teachers·teacher 구역의 cards 변형, staff 태그 허용.
"""
from app.services import photo_needs as PN
from app.services import prd_engine as E
from app.services import site_data as SD
from app.services import site_render as SR


def _person(name, **extra):
    base = {"name": name, "role": "선생님", "subject": "영어",
            "tagline": "쉽게 가르쳐요", "bio": "10년 차예요",
            "specialties": ["문법", "회화"]}
    base.update(extra)
    return base


def _card(**kw):
    card = E.new_card()
    for key, value in kw.items():
        card[key] = value
    return card


def test_clean_staff_keeps_all_fields_and_trims():
    people, errors = SD.clean_staff([_person("  김선생  ", role=" 원장 ")])
    assert errors == []
    assert people == [_person("김선생", role="원장")]


def test_clean_staff_drops_empty_names():
    people, errors = SD.clean_staff([_person(""), _person("   "), _person("김선생")])
    assert errors == []
    assert [p["name"] for p in people] == ["김선생"]


def test_clean_staff_reports_lengths():
    people, errors = SD.clean_staff([_person(
        "이름" * 11,  # 22자
        role="역할" * 7,  # 14자
        subject="과목" * 7,  # 14자
        tagline="한 줄 소개 " * 10,  # 70자
        bio="소개 " * 100,  # 300자
        specialties=["하나", "전문" * 7, "셋", "넷", "다섯"],  # 5개·14자 항목
    )])
    assert any("20자" in e for e in errors)
    assert any("역할" in e for e in errors)
    assert any("과목" in e for e in errors)
    assert any("한 줄 소개" in e for e in errors)
    assert any("소개" in e for e in errors)
    assert any("4개" in e for e in errors)
    assert any("12자" in e for e in errors)
    assert len(people) == 1 and len(people[0]["specialties"]) == 4


def test_clean_staff_reports_duplicate_names():
    _, errors = SD.clean_staff([_person("김선생"), _person("김선생")])
    assert errors == ["같은 이름이 두 번 있어요: 김선생"]


def test_clean_staff_reports_over_twelve():
    raw = [_person(f"선생{i}") for i in range(13)]
    people, errors = SD.clean_staff(raw)
    assert any("12명" in e for e in errors)
    assert len(people) == 12


def test_clean_staff_rejects_non_list():
    people, errors = SD.clean_staff("김선생")
    assert people == [] and errors


def test_staff_list_prefers_staff_edit():
    card = _card(data={"catalog": [], "staff": [{"name": "대화선생", "role": "강사"}]})
    card["staff_edit"] = [_person("직접선생")]
    got = SD.staff_list(card)
    assert [p["name"] for p in got] == ["직접선생"]
    assert got[0]["subject"] == "영어" and got[0]["bio"] == "10년 차예요"


def test_staff_list_falls_back_to_conversation_without_examples():
    card = _card(data={"catalog": [],
                       "staff": [{"name": "대화선생", "role": "강사",
                                  "specialties": ["문법"]}]})
    got = SD.staff_list(card)
    assert got == [{"name": "대화선생", "role": "강사", "subject": "",
                    "tagline": "", "bio": "", "specialties": ["문법"]}]


def _academy_blueprint(section_id):
    return {
        "archetype": "D", "mode": "team",
        "primary": {"label": "상담 신청", "target": "booking"},
        "tokens": {"palette": "charcoal-gold", "font_pair": "serif-elegant",
                   "density": "comfortable", "radius": "soft", "image_style": "card"},
        "strategies": [{
            "id": "v1", "name": "기본형", "journey": "", "tone": "calm",
            "hero": "photo-overlay",
            "sections": [
                {"id": section_id, "type": "staff", "variant": "solo",
                 "bind": "staff", "label": "선생님", "optional": True},
            ],
        }],
    }


def test_fill_staff_uses_staff_edit_and_cards_variant():
    card = _card(data={"catalog": [],
                       "staff": [{"name": "대화선생", "role": "강사"}]})
    card["staff_edit"] = [_person("김선생", subject="영어", tagline="쉽게",
                                  bio="10년 차")]
    spec = SD.resolve(SD.skeleton(_academy_blueprint("teachers"), 0),
                      card, archetype="D")
    sec = next(s for s in spec["sections"] if s.get("bind") == "staff")
    assert sec["variant"] == "cards"  # 1명도 격자 카드
    member = sec["content"]["members"][0]
    assert member["name"] == "김선생" and member["subject"] == "영어"
    assert member["tagline"] == "쉽게" and member["bio"] == "10년 차"


def test_fill_staff_teacher_id_is_cards_too():
    card = _card(data={"catalog": [], "staff": []})
    card["staff_edit"] = [_person("김선생"), _person("이선생")]
    spec = SD.resolve(SD.skeleton(_academy_blueprint("teacher"), 0),
                      card, archetype="E")
    sec = next(s for s in spec["sections"] if s.get("bind") == "staff")
    assert sec["variant"] == "cards"


def test_fill_staff_owner_photo_has_no_example_mark():
    card = _card(data={"catalog": [], "staff": []},
                 photos=[{"url": "/uploads/s1.jpg", "tag": "staff:김선생",
                          "caption": ""}])
    card["staff_edit"] = [_person("김선생"), _person("이선생")]
    sec = {"id": "teachers", "type": "staff", "variant": "solo",
           "bind": "staff", "label": "선생님"}
    SD._fill_staff(sec, {"staff": []}, {"photos": {"staff:1": "/art/a.png",
                                                  "staff:2": "/art/b.png"}},
                   "#booking-title-booking", card)
    members = sec["content"]["members"]
    assert members[0]["image"] == "/uploads/s1.jpg"
    assert "image_example" not in members[0]  # 사장님 사진은 예시 표시 없음
    # 선생님 카드는 사람 자리라 예시 팩 사물 사진을 쓰지 않고 이니셜 원 (D51)
    assert "image" not in members[1]


def test_fill_staff_solo_team_without_teacher_ids():
    card = _card(data={"catalog": [], "staff": []})
    card["staff_edit"] = [_person("김선생")]
    one = {"id": "staff", "type": "staff", "variant": "team", "bind": "staff"}
    SD._fill_staff(one, {"staff": []}, {"photos": {}}, "", card)
    assert one["variant"] == "solo"
    card["staff_edit"] = [_person("김선생"), _person("이선생")]
    two = {"id": "staff", "type": "staff", "variant": "solo", "bind": "staff"}
    SD._fill_staff(two, {"staff": []}, {"photos": {}}, "", card)
    assert two["variant"] == "team"


def test_optional_staff_section_removed_without_staff_edit():
    card = _card(data={"catalog": [], "staff": []})
    spec = SD.resolve(SD.skeleton(_academy_blueprint("teachers"), 0),
                      card, archetype="D")
    assert [s for s in spec["sections"] if s.get("bind") == "staff"] == []


def test_valid_tag_accepts_staff_edit_names():
    card = _card()
    card["staff_edit"] = [_person("김선생")]
    assert PN.valid_tag(card, "staff:김선생") is True
    assert PN.valid_tag(card, "staff:없는선생") is False
    assert PN.valid_tag(card, "staff:") is False
    assert PN.valid_tag(card, "hero") is True


def test_section_context_cards_has_pos_and_popover():
    content = {"label": "선생님", "booking_href": "#booking-title-booking",
               "members": [{"name": "김선생", "role": "원장", "subject": "영어",
                            "tagline": "쉽게", "bio": "10년 차",
                            "specialties": ["문법"]},
                           {"name": "이선생", "role": "강사"}]}
    ctx = SR._section_context("staff", "cards", "teachers", content,
                              site_key="", retention_days=30)
    assert ctx["label"] == "선생님" and ctx["booking_href"] == "#booking-title-booking"
    first, second = ctx["members"]
    assert (first["subject"], first["tagline"], first["bio"]) == ("영어", "쉽게", "10년 차")
    assert (first["pos"], first["popover_id"]) == (1, "staff-teachers-1")
    assert (second["pos"], second["popover_id"]) == (2, "staff-teachers-2")
