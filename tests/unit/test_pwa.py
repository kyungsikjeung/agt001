"""PWA(안드로이드 홈 화면 설치, 주최 요구 5): 앱 정보·서비스 워커·아이콘·오프라인 안내가 루트에서 열린다."""
import json


def test_manifest_is_installable(client):
    r = client.get("/manifest.json")
    assert r.status_code == 200
    m = json.loads(r.text)
    assert m["display"] == "standalone" and m["start_url"].startswith("/")
    sizes = {i["sizes"] for i in m["icons"]}
    assert {"192x192", "512x512"} <= sizes
    for icon in m["icons"]:
        assert client.get(icon["src"]).headers["content-type"] == "image/png"


def test_service_worker_and_offline_page(client):
    sw = client.get("/sw.js")
    assert sw.status_code == 200 and "javascript" in sw.headers["content-type"]
    # 대화·로그인·API는 저장하지 않는다
    for path in ("/api/", "/auth/", "/room/", "/chat"):
        assert path in sw.text
    assert client.get("/offline.html").status_code == 200
    assert 'rel="manifest"' in client.get("/room.html").text
