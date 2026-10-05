"""운영 스모크 점검 스크립트 (scripts/smoke_prod.py). 바깥 호출 없이 가짜 서버로."""
import importlib.util
from pathlib import Path

import httpx

_SPEC = importlib.util.spec_from_file_location("smoke_prod", Path(__file__).resolve().parents[2] / "scripts" / "smoke_prod.py")
smoke = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(smoke)

APP, PV, KEY = "https://app.test", "https://pv.test", "k1"


def _server(chat_href: str, map_html: str = '<div class="s-map__live"></div><script src="https://dapi.kakao.com/v2/maps/sdk.js?appkey=x"></script>'):
    """10/1 운영과 같은 주소 분리: 미리보기 주소는 사이트·사진만, 앱 주소는 앱 페이지만."""
    page = (f'<section class="s-hero"></section><a href="{chat_href}">채팅하기</a>'
            f'{map_html}<img src="/art-lib/coffee-americano.webp">')

    def handler(req: httpx.Request) -> httpx.Response:
        host, path = req.url.host, req.url.path
        if host == "pv.test":
            if path == f"/site/{KEY}/":
                return httpx.Response(200, text=page, headers={"content-security-policy": "sandbox allow-scripts"})
            if path.startswith("/art-lib/"):
                return httpx.Response(200, content=b"webp")
            return httpx.Response(404, text="not found")
        if path == "/api/me":
            return httpx.Response(401)
        if path == "/room.html":
            return httpx.Response(200, text="사장님 화면 (예약·주문·채팅·스탬프)")
        if path == "/privacy.html":
            return httpx.Response(200, text="최종 개정: 2026년 10월 1일")
        return httpx.Response(200, text="ok")
    return httpx.MockTransport(handler)


def _marks(rows):
    return {name: mark for name, mark, _ in rows}


def test_relative_chat_link_on_split_hosts_fails():
    rows = smoke.run(APP, PV, KEY, transport=_server(f"/chat/{KEY}"))  # 10/1 버그: 미리보기 주소로 가서 404
    assert _marks(rows)["채팅하기 링크 따라가기"] == smoke.BAD


def test_app_host_chat_link_passes_everything():
    rows = smoke.run(APP, PV, KEY, transport=_server(f"{APP}/chat/{KEY}"))
    assert [r for r in rows if r[1] == smoke.BAD] == []
    marks = _marks(rows)
    assert marks["채팅하기 링크 따라가기"] == smoke.OK and marks["지도(카카오)"] == smoke.OK
    assert marks["메뉴 태그 사진"] == smoke.OK and marks["주소 분리(미리보기에서 앱 페이지 막힘)"] == smoke.OK


def test_map_css_without_map_section_is_not_a_failure():
    """10/5 운영: 지도 구역이 없는 가게도 공개본 CSS에 .s-map__live가 있어 '지도 실패'로 잘못 나왔다."""
    rows = smoke.run(APP, PV, KEY, transport=_server(f"{APP}/chat/{KEY}", map_html="<style>.s-map__live{width:100%}</style>"))
    assert _marks(rows)["지도(카카오)"] == smoke.INFO
