"""시안 3안 (C7): 카드 사실만 들어가고, 3안이 서로 다르며, 문의 부품이 요구대로 붙는다."""
from app.services import design, design_variants as DV
from app.services import prd_engine as E
from app.services import prd_schema as S


def _card():
    card = E.new_card()
    E._put(card, "business_type", "첼로 레슨", S.FILLED, 1)
    card["industry"] = "individual"
    E._put(card, "shop_name", "하늘첼로", S.FILLED, 1)
    E._put(card, "offerings", ["성인 취미반", "입시반"], S.FILLED, 1)
    E._put(card, "phone", None, S.PLACEHOLDER)
    E._put(card, "location", "서울 마포", S.ASSUMED)  # 가정값은 사실로 넣지 않는다
    E._put(card, "features", ["문의 내용이 카카오톡으로 전송"], S.FILLED, 1)
    card["turn"] = 1
    E._judge_features(card)
    card["feature_answers"] = {"kakao_form_bridge": "사이트 문의 양식 + 채팅방 알림"}
    return card


def test_three_distinct_variants():
    vs = DV.variants(_card())
    assert [v["id"] for v in vs] == ["v1", "v2", "v3"]
    palettes = {v["spec"]["tokens"]["palette"] for v in vs}
    assert len(palettes) == 3
    heroes = [next(s["variant"] for s in v["spec"]["sections"] if s["type"] == "hero") for v in vs]
    assert heroes == ["photo-overlay", "photo-side", "arch"]  # photo-first: 빈 첫 화면 없음
    groups = {DV._PALETTE_GROUPS[v["spec"]["tokens"]["palette"]] for v in vs}
    assert len(groups) == 3  # 색 계열도 서로 다르다


def test_only_owner_facts_and_inquiry_form():
    spec = DV.base_spec(_card())
    hero = next(s for s in spec["sections"] if s["type"] == "hero")
    assert hero["content"]["title"] == "하늘첼로"
    assert "서울 마포" not in str(spec)  # ASSUMED 위치는 넣지 않는다
    types = [(s["type"], s["variant"]) for s in spec["sections"]]
    assert ("contact", "form") in types
    offer = next(s for s in spec["sections"] if s["type"] == "offerings")
    assert [i["name"] for i in offer["content"]["items"]] == ["성인 취미반", "입시반"]


def test_render_variants_writes_pages(client, monkeypatch, tmp_path):
    monkeypatch.setattr(design, "screenshot_many", lambda pages, **kw: [p.write_bytes(b"png") for _, p in pages])
    d = design.render_design("req-c7", "web", [], 0, "", card=_card())
    assert len(d["design_variants"]) == 3 and d["preview_url"].endswith("/v1.png")
    r = client.get("/design/req-c7")
    assert r.status_code == 200 and "/design/req-c7/v2/" in r.text
    v2 = client.get("/design/req-c7/v2/")
    assert v2.status_code == 200 and "하늘첼로" in v2.text and "<script" not in v2.text
    assert "sandbox" in v2.headers["content-security-policy"]
    assert 'action="/api/inquiries/req-c7"' in v2.text
    assert client.get("/design/req-c7/preview.png").status_code == 200
    assert client.get("/design/req-c7/v9/").status_code == 404


def test_form_from_contact_method():
    card = E.new_card()
    E._put(card, "business_type", "첼로 레슨", S.FILLED, 1)
    E._put(card, "contact_method", "사이트 문의 양식", S.FILLED, 1)
    types = [(s["type"], s["variant"]) for s in DV.base_spec(card)["sections"]]
    assert ("contact", "form") in types


def test_hidden_items_become_icon_features():
    """방안 6: 고른 숨은 항목(주차·반려동물)과 덧붙인 말이 '이용 안내' 아이콘 칸으로 들어간다."""
    from app.services.site_render import render_site
    card = E.new_card("pension")
    card["hidden"] = {"asked": True, "selected": ["parking", "pet"], "note": "소형견만 가능해요"}
    spec = DV.base_spec(card)
    feat = next(s for s in spec["sections"] if s["type"] == "features")
    assert [i["title"] for i in feat["content"]["items"]] == ["주차", "반려동물 동반"]
    html = render_site(spec, kind="pension", public=True)
    assert "이용 안내" in html and "소형견만 가능해요" in html and "<svg" in html


def test_three_variants_differ_in_structure():
    """방안 7: 2안은 사진첩이 첫 화면 바로 뒤, 3안은 상품이 먼저이고 사진이 없으면 사진첩이 없다."""
    vs = DV.variants(_card())
    order = [[s["type"] for s in v["spec"]["sections"]] for v in vs]
    assert order[1][:2] == ["hero", "gallery"]
    assert order[2][1] == "offerings" and "gallery" not in order[2]
    assert len({tuple(o) for o in order}) == 3


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


def _salon_card(*staff):
    card = E.new_card("salon")
    E._put(card, "business_type", "미용실", S.FILLED, 1)
    E._put(card, "shop_name", "단정손끝", S.FILLED, 1)
    E._put(card, "offerings", ["컷", "펌"], S.FILLED, 1)
    if staff:
        E._put(card, "staff", list(staff), S.FILLED, 1)
    card["turn"] = 1
    return card


def test_blueprint_path_cafe_names_sections_palette():
    """J5 새 경로(A): 안 이름이 청사진 전략 이름, 두 번째 섹션이 서로 다름,
    ① 팔레트는 원형 기본(espresso), 예시 표시가 붙는다."""
    vs = DV.variants(_cafe_card())
    assert [v["id"] for v in vs] == ["v1", "v2", "v3"]
    assert [v["name"] for v in vs] == ["메뉴판형", "공간·방문형", "시그니처형"]
    assert [v["summary"] for v in vs] == ["메뉴 보고 → 길찾기", "공간 보고 → 길찾기", "대표 메뉴 보고 → 길찾기"]
    seconds = [v["spec"]["sections"][1]["type"] for v in vs]
    assert len(set(seconds)) == 3
    assert [v["spec"]["tokens"]["palette"] for v in vs][0] == "espresso"
    assert DV.min_distance([v["spec"] for v in vs]) >= DV.MIN_DISTANCE
    hero = vs[0]["spec"]["sections"][0]["content"]
    assert hero.get("ai_example") is True  # 사장님 사진 없음 → 예시 팩 + 표시
    menu = next(s for s in vs[0]["spec"]["sections"] if s.get("bind") == "catalog")
    guess = [i for c in menu["content"]["categories"] for i in c["items"]]
    assert guess and all(i.get("price_example") is True for i in guess)  # 가격 없음 → 예시 가격 + 표시
    around = next(s for s in vs[0]["spec"]["sections"] if s.get("bind") == "location")
    assert {"name": "전화", "note": "02-123-4567"} in around["content"]["items"]
    assert {"name": "영업시간", "note": "매일 10~21시"} in around["content"]["items"]


def test_blueprint_path_salon_solo_and_team():
    """J5 새 경로(B): 1인분은 solo, 2인분은 team 청사진을 쓴다."""
    solo = DV.variants(_salon_card("원장 김단정(컷·펌)"))
    assert [v["name"] for v in solo] == ["원장 브랜드형", "스타일 포트폴리오형", "시술·가격형"]
    assert solo[0]["spec"]["tokens"]["palette"] == "charcoal-gold"
    staff = next(s for s in solo[0]["spec"]["sections"] if s.get("bind") == "staff")
    assert staff["variant"] == "solo"
    assert [m["name"] for m in staff["content"]["members"]] == ["김단정"]
    team = DV.variants(_salon_card("원장 김미용(컷)", "실장 박하나(염색)"))
    assert [v["name"] for v in team] == ["디자이너 선택형", "스타일형", "시술·가격형"]
    staff = next(s for s in team[0]["spec"]["sections"] if s.get("bind") == "staff")
    assert staff["variant"] == "team"
    assert DV.min_distance([v["spec"] for v in team]) >= DV.MIN_DISTANCE


def test_blueprint_path_staff_example_when_empty():
    """J5: 담당자가 없으면 예시 파일 staff를 예시 표시로 채운다(빈 섹션 없음)."""
    vs = DV.variants(_salon_card())
    staff = next(s for s in vs[0]["spec"]["sections"] if s.get("bind") == "staff")
    assert staff["content"]["members"] and all(m.get("example") is True for m in staff["content"]["members"])
