"""공개 서빙: health·design·site·정적 파일."""
from pathlib import Path

from app.config import settings
from app.services import design as design_svc


def _render_design_entry(requirement_id="demo1"):
    # conftest가 screenshot_html을 예외로 막아 두었으므로 플레이스홀더 폴백 경로를 탄다.
    return design_svc.render_design(requirement_id, "web", ["예약 기능"], 1000000, "기본안")


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_design_page_200_and_404(client):
    d = _render_design_entry("demo1")
    r = client.get("/design/demo1")
    assert r.status_code == 200
    assert "시안" in r.text
    assert client.get("/design/nonexistentzzz").status_code == 404


def test_design_preview_png(client, monkeypatch):
    from fakes import fake_png_screenshot

    monkeypatch.setattr(design_svc, "screenshot_html", fake_png_screenshot)
    design_svc.render_design("withimg", "web", ["f"], 100, "basis")
    r = client.get("/design/withimg/preview.png")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    assert client.get("/design/nonexistentzzz/preview.png").status_code == 404


def test_design_preview_missing_when_placeholder(client):
    _render_design_entry("noimg")
    # 스크린샷이 실패해 플레이스홀더 URL이면 로컬 PNG 파일이 없으므로 404
    assert client.get("/design/noimg/preview.png").status_code == 404


def test_site_redirect_and_files(client):
    web = settings.generated_dir / "site1" / "web"
    web.mkdir(parents=True, exist_ok=True)
    (web / "index.html").write_text("<h1>hello site</h1>", encoding="utf-8")
    (web / "app.js").write_text("console.log(1)", encoding="utf-8")

    r = client.get("/site/site1", follow_redirects=False)
    assert r.status_code == 308
    assert r.headers["location"].endswith("/site/site1/")

    r = client.get("/site/site1/")
    assert r.status_code == 200
    assert "hello site" in r.text

    r = client.get("/site/site1/app.js")
    assert r.status_code == 200

    assert client.get("/site/nonexistentzzz/").status_code == 404
    assert client.get("/site/site1/missing.js").status_code == 404


def test_site_traversal_blocked(client):
    web = settings.generated_dir / "trav" / "web"
    web.mkdir(parents=True, exist_ok=True)
    (web / "index.html").write_text("hi", encoding="utf-8")
    (settings.generated_dir / "secret.txt").write_text("SECRET", encoding="utf-8")

    assert client.get("/site/trav/../secret.txt").status_code == 404
    assert client.get("/site/trav/%2e%2e/secret.txt").status_code == 404
    assert client.get("/site/trav/%2E%2E/secret.txt").status_code == 404
    assert client.get("/site/trav/..%2fsecret.txt").status_code == 404


def test_static_root_and_room(client):
    assert client.get("/").status_code == 200
    r = client.get("/room.html")
    assert r.status_code == 200


def test_generated_pages_are_sandboxed(client):
    """AI가 만든 페이지는 앱 출처로 취급되면 안 된다 (채팅방 본인 확인 값 탈취 방지)."""
    web = settings.generated_dir / "sbx" / "web"
    web.mkdir(parents=True)
    (web / "index.html").write_text("<script>localStorage.getItem('agt001_member_id')</script>", encoding="utf-8")
    r = client.get("/site/sbx/")
    csp = r.headers["content-security-policy"]
    assert csp.startswith("sandbox") and "allow-same-origin" not in csp
    assert r.headers["x-content-type-options"] == "nosniff"

    design = settings.generated_dir / "sbx" / "design"
    design.mkdir(parents=True)
    (design / "index.html").write_text("<h1>시안</h1>", encoding="utf-8")
    d = client.get("/design/sbx")
    assert d.headers["content-security-policy"].startswith("sandbox")
    assert "allow-scripts" not in d.headers["content-security-policy"]
    assert d.headers["x-robots-tag"] == "noindex"
