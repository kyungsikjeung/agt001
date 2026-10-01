"""공개 가게 한꺼번에 다시 공개 (scripts/republish_all.py). 카카오는 가짜로만 부른다."""
import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import delete

from app import store
from app.config import settings
from app.db.models import ShopRow
from app.db.session import get_sessionmaker
from app.services import geo

_SPEC = importlib.util.spec_from_file_location(
    "republish_all", Path(__file__).resolve().parents[2] / "scripts" / "republish_all.py")
republish_all = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(republish_all)


class _Resp:
    def __init__(self, docs):
        self.status_code = 200
        self._docs = docs

    def json(self):
        return {"documents": self._docs}


def _published_site(client, monkeypatch, location="연남로 12"):
    """키 없이(주소 확인 없이) 공개한 예전 가게: 주소는 있고 좌표는 없다."""
    from app.api import inquiries as inquiries_api
    monkeypatch.setattr(settings, "publish_login_required", False)
    monkeypatch.setattr(geo.keystore, "get", lambda name: None)
    with inquiries_api._lock:
        inquiries_api._hits.clear()
    body = client.post("/api/start", json={"template": "cafe"}).json()
    rid, h = body["room_id"], {"X-Member-Id": body["member_id"]}
    client.put(f"/api/rooms/{rid}/card", headers=h,
               json={"fields": {"shop_name": "모퉁이 커피", "phone": "010-1234-5678", "location": location}})
    assert client.post(f"/api/rooms/{rid}/publish", json={"force": True}, headers=h).json().get("ok")
    key = store.read_session(store.read_room(rid)["session_id"])["requirement_id"]
    with get_sessionmaker()() as db, db.begin():  # 10/1 버그: 공개 때 가게 행이 안 생겼다
        db.execute(delete(ShopRow).where(ShopRow.site_key == key))
    return rid, key


def _kakao(monkeypatch, docs):
    monkeypatch.setattr(geo.keystore, "get", lambda name: "k" if name == "kakao_rest_api_key" else None)
    monkeypatch.setattr(geo.httpx, "get", lambda url, **kw: _Resp(docs if "address" in url else []))


def _card(rid):
    return store.read_session(store.read_room(rid)["session_id"])["prd"]


def test_dry_run_changes_nothing(client, monkeypatch, capsys):
    rid, key = _published_site(client, monkeypatch)
    assert republish_all.main([]) == 0
    out = capsys.readouterr().out
    assert key in out and "가게 행 없음" in out and "좌표 없음" in out and "모퉁이" not in out
    with get_sessionmaker()() as db:
        assert db.get(ShopRow, key) is None
    assert "location_geo" not in _card(rid)


def test_apply_geo_restores_shop_and_map(client, monkeypatch, capsys):
    rid, key = _published_site(client, monkeypatch)
    _kakao(monkeypatch, [{"road_address": {"address_name": "서울 마포구 연남로 12"},
                          "address": {"address_name": "연남동 1"}, "x": "126.92", "y": "37.56"}])
    assert republish_all.main(["--apply", "--geo"]) == 0
    out = capsys.readouterr().out
    assert "가게 행 채움 1곳" in out and "좌표 채움 1곳" in out
    with get_sessionmaker()() as db:
        assert db.get(ShopRow, key) is not None
    assert _card(rid)["location_geo"]["x"] == 126.92
    page = (settings.generated_dir / key / "published" / "index.html").read_text(encoding="utf-8")
    assert f'href="/chat/{key}"' in page


def test_geo_never_blanks_address_when_not_found(client, monkeypatch):
    rid, key = _published_site(client, monkeypatch, location="마포구 어딘가 골목")
    _kakao(monkeypatch, [])
    assert republish_all.main(["--apply", "--geo"]) == 0
    card = _card(rid)
    assert "location_geo" not in card
    assert card["slots"]["location"]["status"] == "filled"  # 공개 주소를 빈칸·임시로 바꾸지 않는다


def test_only_one_site(client, monkeypatch, capsys):
    _, key1 = _published_site(client, monkeypatch)
    _, key2 = _published_site(client, monkeypatch)
    assert republish_all.main(["--apply", "--only", key2]) == 0
    with get_sessionmaker()() as db:
        assert db.get(ShopRow, key1) is None and db.get(ShopRow, key2) is not None
