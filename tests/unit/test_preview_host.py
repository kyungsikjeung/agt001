"""미리보기 주소 분리 (S-1): 생성물은 미리보기 주소로, 앱 경로는 미리보기 주소에서 막힘."""
import pytest

from app.config import settings

PREVIEW = "144-24-91-250.sslip.io"


@pytest.fixture
def preview(monkeypatch):
    monkeypatch.setattr(settings, "preview_host", PREVIEW)


def test_app_host_redirects_generated_paths(client, preview):
    r = client.get("/design/abc/v1/?x=1", headers={"host": "144.24.91.250.sslip.io"}, follow_redirects=False)
    assert r.status_code == 308 and r.headers["location"] == f"https://{PREVIEW}/design/abc/v1/?x=1"
    r = client.get("/site/abc/", headers={"host": "144.24.91.250.sslip.io"}, follow_redirects=False)
    assert r.status_code == 308


def test_preview_host_blocks_app_paths(client, preview):
    for path in ("/", "/api/me", "/projects", "/room.html"):
        assert client.get(path, headers={"host": PREVIEW}).status_code == 404
    assert client.post("/chat", json={"message": ""}, headers={"host": PREVIEW}).status_code == 404


def test_preview_host_serves_generated_and_inquiries(client, preview):
    assert client.get("/health", headers={"host": PREVIEW}).status_code == 200
    # 없는 시안은 앱 라우터의 404(미들웨어가 막은 것이 아님)
    r = client.get("/design/nope", headers={"host": PREVIEW})
    assert r.status_code == 404 and r.text != "not found"
    r = client.post("/api/inquiries/nope", data={"contact": "010-1111-2222", "message": "hi", "agree": "yes"},
                    headers={"host": PREVIEW}, follow_redirects=False)
    assert r.status_code == 400  # 없는 사이트 → 앱의 문의 처리까지 도달


def test_off_by_default(client):
    # conftest가 개발자 .env 값에 끌려가지 않게 빈 값으로 고정한다(None과 빈 값 모두 "꺼짐").
    assert not settings.preview_host
    assert client.get("/design/nope").status_code == 404  # 리다이렉트 없음
