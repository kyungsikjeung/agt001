"""빌더 미리보기 스크립트 (10/4): 지도가 빈 칸으로 남지 않기 · 바꿔 끼운 구역의 스크립트 다시 돌기 · 가로 띠 마우스로 끌기.

브라우저 검사는 Chromium을 띄울 수 있을 때만 돈다(CI에는 브라우저가 없어 건너뛴다). 문자열 검사는 늘 돈다.
"""
import html
import http.server
import os
import threading

import pytest

from app.services import site_render as SR

TOKENS = {"palette": "forest", "font_pair": "serif-warm", "density": "comfortable", "radius": "soft",
          "image_style": "card"}
GEO_SPEC = {"tokens": TOKENS, "sections": [
    {"id": "around", "type": "around", "variant": "map",
     "content": {"address": "경기 성남시 수정구 위례순환로 17", "geo": {"x": 127.14, "y": 37.47}}}]}
SWIPE_SPEC = {"tokens": TOKENS, "sections": [
    {"id": "view", "type": "gallery", "variant": "swipe", "label": "주변", "content": {"items": [
        {"src": "/art/ex/pension-space1.webp", "alt": "a"}, {"src": "/art/ex/pension-space2.webp", "alt": "b"},
        {"src": "/art/ex/pension-space3.webp", "alt": "c"}]}}]}


def test_map_script_falls_back_when_sdk_never_draws():
    doc = SR.render_site(GEO_SPEC, edit=True)
    assert "setTimeout(back,5000)" in doc            # SDK는 있는데 그리기가 안 끝나도 예시 지도로
    assert "done=true" in doc


def test_patch_reruns_scripts_of_swapped_sections():
    doc = SR.render_site(GEO_SPEC, edit=True)
    assert "function run(el)" in doc and "run(fresh[r])" in doc


def test_drag_script_only_in_edit_preview_with_strips():
    assert "@drag" not in str(SR.render_page(SWIPE_SPEC)["parts"])
    edit = SR.render_site(SWIPE_SPEC, edit=True)
    assert 'pointerType!=="mouse"' in edit and ".s-gallery__swipe" in edit
    assert "<script" not in SR.render_site(SWIPE_SPEC).lower()          # 시안은 스크립트 없이
    assert "<script" not in SR.render_site(SWIPE_SPEC, public=True).lower()
    assert 'pointerType!=="mouse"' not in SR.render_site(GEO_SPEC, edit=True)  # 띠가 없으면 안 넣는다


# ---- 실제 브라우저 ----

CHROME = os.environ.get("CHROMIUM_PATH") or "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"


@pytest.fixture(scope="module")
def page():
    if not os.path.exists(CHROME):
        pytest.skip("Chromium 없음")
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=CHROME)
        yield browser.new_page(viewport={"width": 420, "height": 860})
        browser.close()


def _host(doc: str) -> str:
    # 빌더와 같은 틀: srcdoc + sandbox allow-scripts(출처 없음)
    return ('<!doctype html><body style="margin:0"><iframe sandbox="allow-scripts" '
            'style="width:390px;height:800px;border:0" srcdoc="' + html.escape(doc, quote=True) + '"></iframe>'
            '<script>window.got=[];addEventListener("message",e=>got.push(e.data&&e.data.type))</script></body>')


@pytest.fixture(scope="module")
def fake_sdk():
    """카카오 SDK 대신: /hang는 load가 끝나지 않고, /ok는 바로 그린다."""
    bodies = {"/hang": "window.kakao={maps:{load:function(){}}};",
              "/ok": ("window.kakao={maps:{load:function(c){c()},LatLng:function(){},Marker:function(){},"
                      "Map:function(el){el.setAttribute('data-drawn','1')}}};")}

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "application/javascript")
            self.end_headers()
            self.wfile.write(bodies.get(self.path.split("?")[0], "").encode())

        def log_message(self, *a):
            pass

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def _map_state(frame):
    return frame.evaluate("(()=>{const l=document.querySelector('.s-map__live'),a=document.querySelector('.s-map__art');"
                          "return {live:!l.hidden,art:!a.hidden,drawn:l.getAttribute('data-drawn')==='1'}})()")


def _with_sdk(text: str, base: str, mode: str) -> str:
    return text.replace("https://dapi.kakao.com/v2/maps/sdk.js", f"{base}/{mode}")


def test_browser_map_never_stays_blank(page, fake_sdk, tmp_path):
    page_doc = SR.render_page(GEO_SPEC, edit=True)
    host = tmp_path / "hang.html"
    host.write_text(_host(_with_sdk(page_doc["html"], fake_sdk, "hang")), encoding="utf-8")
    page.goto(host.as_uri())
    frame = page.frames[-1]
    page.wait_for_timeout(6500)
    assert _map_state(frame) == {"live": False, "art": True, "drawn": False}   # 예전: 빈 칸 그대로


def test_browser_map_redrawn_after_patch(page, fake_sdk, tmp_path):
    page_doc = SR.render_page(GEO_SPEC, edit=True)
    part = next(p for p in page_doc["parts"] if p["key"] == "around")
    host = tmp_path / "ok.html"
    host.write_text(_host(_with_sdk(page_doc["html"], fake_sdk, "ok")), encoding="utf-8")
    page.goto(host.as_uri())
    frame = page.frames[-1]
    page.wait_for_timeout(800)
    assert _map_state(frame)["drawn"]
    page.evaluate("h=>document.querySelector('iframe').contentWindow.postMessage("
                  "{type:'agt-patch',parts:[{id:'around',html:h}]},'*')", _with_sdk(part["html"], fake_sdk, "ok"))
    page.wait_for_timeout(800)
    assert _map_state(frame) == {"live": True, "art": False, "drawn": True}    # 예전: 바꿔 끼운 뒤 빈 칸


def test_browser_drag_scrolls_strip_and_keeps_click(page, tmp_path):
    host = tmp_path / "swipe.html"
    host.write_text(_host(SR.render_site(SWIPE_SPEC, edit=True)), encoding="utf-8")
    page.goto(host.as_uri())
    frame = page.frames[-1]
    page.wait_for_timeout(400)
    strip = frame.locator(".s-gallery__swipe")
    box = strip.bounding_box()
    y = box["y"] + 50
    page.mouse.move(box["x"] + 260, y)
    page.mouse.down()
    page.mouse.move(box["x"] + 20, y, steps=8)
    page.mouse.up()
    page.wait_for_timeout(200)
    assert frame.evaluate("document.querySelector('.s-gallery__swipe').scrollLeft") > 100
    assert page.evaluate("window.got") == []           # 끈 것은 구역 열기로 치지 않는다
    page.mouse.click(box["x"] + 60, y)
    page.wait_for_timeout(200)
    assert page.evaluate("window.got") == ["agt-edit"]  # 그냥 누르면 그대로 열린다
