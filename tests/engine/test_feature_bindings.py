"""데이터 연결표 (BUILD_W1_W2 J9, UI_AGENT_PLAN §5.2·§5.3).

기능 42개마다 components·binding·resource가 있고, components는 실제 부품이며,
out_of_beta는 대안 부품(alternative_ui)이다.
"""
import pytest

from app.services import intake
from app.services import site_render


def items():
    return intake._catalog()


def by_id(fid):
    return next(it for it in items() if it["id"] == fid)


def test_42_items_have_three_fields():
    assert len(items()) == 42
    for it in items():
        assert isinstance(it.get("components"), list), it["id"]
        assert it.get("binding") in intake.BINDINGS, it["id"]
        assert it.get("resource") in intake.RESOURCES, it["id"]


def test_components_are_real_variants():
    known = set(site_render.list_variants())
    for it in items():
        for c in it["components"]:
            assert c in known, (it["id"], c)


def test_out_of_beta_has_alternative_ui():
    got = [it["id"] for it in items() if it["verdict"] == intake.OUT_OF_BETA]
    assert len(got) == 11
    for it in items():
        if it["verdict"] == intake.OUT_OF_BETA:
            assert it.get("alternative_ui") is True, it["id"]
        else:
            assert it.get("alternative_ui") is not True, it["id"]


def test_menu_and_price_use_offerings_categories():
    for fid in ("menu_board", "price_list"):
        it = by_id(fid)
        assert "offerings--categories" in it["components"]
        assert it["binding"] == "static"


def test_booking_calendar_custom_binding():
    it = by_id("booking_calendar_custom")
    assert "booking--slots" in it["components"]
    assert it["resource"] == "bookings"
    assert it["binding"] == "computed"


def test_inquiry_form_binding():
    it = by_id("inquiry_form")
    assert "contact--form" in it["components"]
    assert it["resource"] == "inquiries"


def test_ready_components_returns_only_ready():
    rc = intake.ready_components()
    ready_ids = {it["id"] for it in items() if it["verdict"] == intake.READY}
    assert set(rc) == ready_ids
    assert len(rc) == 19
    assert rc["menu_board"] == ["offerings--categories"]
    # 원형 인자는 지금은 거르지 않고 받아만 둔다
    assert intake.ready_components("A") == rc


def test_bad_catalog_raises_value_error():
    bad = [{"id": "x", "components": ["없는부품"], "binding": "static", "resource": ""}]
    with pytest.raises(ValueError):
        intake._check_bindings(bad)
    bad2 = [{"id": "x", "components": [], "binding": "마음대로", "resource": ""}]
    with pytest.raises(ValueError):
        intake._check_bindings(bad2)
