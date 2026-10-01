"""공개 사이트·미리보기 지도 (MAP_CONTRACT §4·§6-5).

좌표 있으면 실제 지도 칸 + SDK 한 줄, 없거나 placeholder면 예전 그대로.
"""
from app.config import settings
from app.services import design as design_svc
from app.services import design_variants as DV
from app.services import prd_engine as E
from app.services import prd_schema as S
from app.services import site_data, site_render
from app.services.publish_check import check_html

GEO = {"road": "서울 마포구 연남로 12", "jibun": "서울 마포구 연남동 227-1",
       "detail": "2층", "x": 126.925, "y": 37.566, "src": "search"}
SDK_URL = f"https://dapi.kakao.com/v2/maps/sdk.js?appkey={settings.kakao_js_key}&autoload=false"

TOKENS = {"palette": "coffee", "font_pair": "serif-warm", "density": "comfortable",
          "radius": "soft", "image_style": "card"}


def _card(geo=None):
    """지도 테스트용 카페 카드."""
    card = E.new_card()
    E._put(card, "business_type", "카페", S.FILLED, 1)
    card["industry"] = "cafe"
    E._put(card, "shop_name", "작은숲", S.FILLED, 1)
    E._put(card, "offerings", ["아메리카노", "라떼"], S.FILLED, 1)
    E._put(card, "contact_method", "전화", S.FILLED, 1)
    E._put(card, "phone", "010-0000-1234", S.FILLED, 1)
    E._put(card, "location", "서울 마포구 연남로 12", S.FILLED, 1)
    card["turn"] = 1
    if geo is not None:
        card["location_geo"] = dict(geo)
    return card


def _around_spec(geo=None):
    """오시는 길 구역 하나짜리 명세."""
    content = {"address": "서울 마포구 연남로 12"}
    if geo is not None:
        content["geo"] = dict(geo)
    return {"version": 3, "tokens": dict(TOKENS),
            "sections": [{"id": "around", "type": "around", "variant": "map",
                          "content": content}]}


def _location_section(card):
    """site_data.resolve가 채운 location 구역."""
    spec = {"version": 3, "tokens": {},
            "sections": [{"id": "around", "type": "around", "variant": "map",
                          "bind": "location", "content": {}}]}
    out = site_data.resolve(spec, card, archetype="A")
    return next(s for s in out["sections"] if s.get("bind") == "location")


# ── site_data: geo는 search·postcode일 때만 ──

def test_geo_in_content_when_search():
    sec = _location_section(_card(GEO))
    assert sec["content"]["geo"] == {"x": 126.925, "y": 37.566}


def test_no_geo_when_placeholder_or_missing():
    sec = _location_section(_card({**GEO, "src": "placeholder"}))
    assert "geo" not in sec["content"]
    sec = _location_section(_card())
    assert "geo" not in sec["content"]


# ── 렌더: 좌표 있으면 공개본·미리보기 모두 실제 지도 ──

def test_live_map_in_public_and_preview():
    spec = _around_spec({"x": 126.925, "y": 37.566})
    for public in (True, False):
        page = site_render.render_site(spec, site_key="t", title="t", kind="cafe",
                                       public=public)
        assert "s-map__live" in page
        assert SDK_URL in page
        assert 'data-x="126.925"' in page and 'data-y="37.566"' in page
        assert "draggable:false" in page and "level:3" in page
        assert "s-map__art" in page  # 되돌림용 예시 지도는 hidden으로 남김
        assert "map.kakao.com/link/map/" in page
    assert check_html(site_render.render_site(spec, site_key="t", title="t",
                                              kind="cafe", public=True)) == []


def test_placeholder_renders_like_before():
    """placeholder는 site_data에서 geo가 빠져 예전 그대로 그려진다."""
    sec = _location_section(_card({**GEO, "src": "placeholder"}))
    spec = {"version": 3, "tokens": dict(TOKENS),
            "sections": [{"id": "around", "type": "around", "variant": "map",
                          "content": sec["content"]}]}
    page = site_render.render_site(spec, site_key="t", title="t", kind="cafe", public=True)
    assert 'class="s-map__art"' in page
    assert 'class="s-map__live"' not in page  # CSS 규칙 이름은 늘 있어 태그로 본다
    assert "dapi.kakao.com" not in page


def test_publish_choice_with_geo(client):
    """공개본(publish_choice)도 실제 지도 + 검사 통과."""
    card = _card(GEO)
    vid = next(v["id"] for v in DV.variants(card)
               if any(s.get("type") == "around" and s.get("variant") == "map"
                      for s in v["spec"].get("sections") or []))
    design_svc.publish_choice("req-map", card, vid)
    page = (settings.generated_dir / "req-map" / "published" / "index.html").read_text(
        encoding="utf-8")
    assert "s-map__live" in page and SDK_URL in page
    assert check_html(page) == []


# ── publish_check: SDK 한 주소만 예외 ──

def test_sdk_shape_only_exception():
    assert check_html(f'<script src="{SDK_URL}"></script>') == []
    assert check_html('<script src="https://evil.example/x.js"></script>')
    assert check_html('<script src="https://dapi.kakao.com/other.js?appkey=abc&autoload=false"></script>')
    assert check_html(f'<script src="https://dapi.kakao.com/v2/maps/sdk.js?appkey={settings.kakao_js_key}"></script>')
    assert check_html('<script src="https://dapi.kakao.com/v2/maps/sdk.js?appkey=ab-cd&autoload=false"></script>')


def test_kakao_link_encodes_address_with_comma():
    """이름에 쉼표가 있어도 크게 보기 링크 형식(이름,위도,경도)이 깨지지 않는다."""
    links = site_render._map_links("서울 마포구 연남로 12, 2층", (126.925, 37.566))
    assert links[0]["href"].endswith(",37.566,126.925")
    assert "%2C" in links[0]["href"] and " " not in links[0]["href"]
