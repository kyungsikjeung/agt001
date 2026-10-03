"""사진 구역 설정 (10/4 대표 요청): 보일 장수·사진 비율·움직임(넘기기 자동 넘김·흐름 속도).

구역 편집(layout_edits)의 opts로 안마다 저장하고, 그릴 때 장수를 자르고 data-* 속성을 단다.
"""
import re

from app.services import layout_edits as LE
from app.services import site_render

TOKENS = {"palette": "forest", "font_pair": "serif-warm", "density": "comfortable", "radius": "soft", "image_style": "card"}
PHOTOS = [{"src": f"/uploads/p{i}.jpg", "alt": f"사진 {i}"} for i in range(6)]


def _page(variant, opts):
    spec = {"version": 3, "tokens": dict(TOKENS),
            "sections": [{"id": "view", "type": "gallery", "variant": variant, "opts": opts,
                          "content": {"label": "주변", "items": PHOTOS}}]}
    return site_render.render_site(spec, site_key="t", title="t", kind="pension", public=True)


def test_render_count_ratio_motion():
    page = _page("swipe", {"count": 3, "ratio": "square", "autoplay": 5})
    sec = re.search(r'<section class="s-gallery s-gallery--swipe".*?</section>', page, re.S).group(0)
    assert sec.count("<img ") == 3
    assert 'data-ratio="square"' in sec and 'data-autoplay="5"' in sec
    assert "data-autoplay" in page and "setInterval" in page  # 자동 넘김은 문서 스크립트가 맡는다
    page = _page("marquee", {"speed": "fast"})
    assert 'data-speed="fast"' in page
    plain = _page("swipe", None)
    assert "data-ratio" not in plain.split("<style")[0] and 'data-autoplay="' not in plain


def _pension(client):
    from app.api import inquiries as inquiries_api
    with inquiries_api._lock:
        inquiries_api._hits.clear()
    body = client.post("/api/start", json={"template": "pension"}).json()
    return body["room_id"], {"X-Member-Id": body["member_id"]}


def test_opts_saved_per_variant_and_cleaned(client):
    rid, h = _pension(client)
    # 2안: view=넘기기(swipe), tour=흐름(marquee). 펜션 둘러보기 숨김 해제
    pv = client.get(f"/api/rooms/{rid}/card/preview?variant=v2", headers=h).json()
    view = next(s for s in pv["sections"] if s["id"] == "view")
    assert view["type"] == "gallery" and view["opts"] == {}
    order = [s["id"] for s in pv["sections"]]
    layout = {"variant": "v2", "order": order, "hidden": [], "added": [], "opts": {
        "view": {"count": 4, "ratio": "tall", "autoplay": 3, "speed": "fast"},  # speed는 흐름 모양만 → 버림
        "tour": {"speed": "slow", "autoplay": 5, "ratio": "wide", "count": 5},  # autoplay 버림, wide 기본·5 모름 → 버림
        "booking": {"count": 2},  # 사진첩이 아니면 버림
    }}
    r = client.put(f"/api/rooms/{rid}/card", json={"layout": layout}, headers=h)
    assert r.status_code == 200
    pv = client.get(f"/api/rooms/{rid}/card/preview?variant=v2", headers=h).json()
    got = {s["id"]: s["opts"] for s in pv["sections"]}
    assert got["view"] == {"count": 4, "ratio": "tall", "autoplay": 3}
    assert got["tour"] == {"speed": "slow"}
    assert got["booking"] == {}
    assert 'data-autoplay="3"' in pv["html"] and 'data-speed="slow"' in pv["html"]
    # 순서만 바꿔 보낼 때(opts 없음)는 설정을 지우지 않는다
    client.put(f"/api/rooms/{rid}/card", json={"layout": {"variant": "v2", "order": order[::-1], "hidden": [], "added": []}}, headers=h)
    pv = client.get(f"/api/rooms/{rid}/card/preview?variant=v2", headers=h).json()
    assert {s["id"]: s["opts"] for s in pv["sections"]}["view"] == {"count": 4, "ratio": "tall", "autoplay": 3}


def test_clean_opts_unit():
    bp = {"strategies": [{"id": "v1", "sections": [{"id": "g", "type": "gallery", "variant": "grid", "bind": "space_photos"}]}]}
    assert LE._clean_opts({"g": {"autoplay": 3, "count": 2}}, bp, 0, {"g"}, {}) == {"g": {"count": 2}}  # 격자는 자동 넘김 없음
    assert LE._clean_opts({"g": {"autoplay": 3}}, bp, 0, {"g"}, {"g": "swipe"}) == {"g": {"autoplay": 3}}  # 모양을 넘기기로 바꾼 뒤
