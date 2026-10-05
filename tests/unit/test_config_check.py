"""설정 점검 (UX_GAP_PLAN Q3): 빠진 설정을 시끄럽게. 텔레그램은 부르지 않는다(보내기는 가짜)."""
import logging

import httpx
import openai
import pytest
from sqlalchemy import select

from app import llm
from app.config import settings
from app.db.models import AdminAuditRow, UserRow
from app.db.session import get_sessionmaker
from app.services import auth as auth_svc
from app.services import config_check, keystore, ops_alert, site_render

KEYS = {"telegram_bot_token": "123:token", "vapid_private_key": "vapid-secret"}


@pytest.fixture
def clean(monkeypatch):
    """문제 없는 설정. 테스트가 하나씩 끈다."""
    keys = dict(KEYS)
    monkeypatch.setattr(keystore, "get", lambda name: keys.get(name))
    for k, v in {"preview_host": "preview.example", "public_base_url": "https://app.example",
                 "telegram_chat_id": "42", "token_enc_key": "enc-key", "kakao_js_key": "js-key",
                 "nim_chat_model": "primary", "nim_chat_fallback_models": "second",
                 "nim_all_fail_backoff_sec": 0}.items():
        monkeypatch.setattr(settings, k, v)
    monkeypatch.setattr(llm, "_cooldown", {})
    monkeypatch.setattr(llm, "_gone", {})
    return keys


@pytest.fixture
def sent(monkeypatch):
    out = []
    monkeypatch.setattr(ops_alert, "send", lambda kind, text, wait=False: out.append((kind, text)) or True)
    return out


def _levels():
    return {p["key"]: p["level"] for p in config_check.problems()}


def test_clean_has_no_problems(clean):
    assert config_check.problems() == []


@pytest.mark.parametrize("off, key, level", [
    (lambda k: setattr(settings, "public_base_url", None), "public_base_url", "error"),
    (lambda k: setattr(settings, "public_base_url", "http://app.example"), "public_base_url", "error"),
    (lambda k: k.pop("telegram_bot_token"), "telegram", "warn"),
    (lambda k: setattr(settings, "telegram_chat_id", ""), "telegram", "warn"),
    (lambda k: setattr(settings, "token_enc_key", ""), "token_enc_key", "warn"),
    (lambda k: k.pop("vapid_private_key"), "vapid", "info"),
    (lambda k: setattr(settings, "kakao_js_key", ""), "kakao_js_key", "info"),
    (lambda k: llm._gone.update(primary=llm.time.monotonic() + 60), "nim_chat_model", "error"),
])
def test_each_check(clean, off, key, level):
    off(clean)
    assert _levels() == {key: level}
    p = config_check.problems()[0]
    assert p["text"] and p["fix"]


def test_no_preview_host_means_relative_links_are_fine(clean, monkeypatch):
    monkeypatch.setattr(settings, "preview_host", None)
    monkeypatch.setattr(settings, "public_base_url", None)
    assert "public_base_url" not in _levels()


def test_keystore_error_does_not_raise(clean, monkeypatch):
    def boom(name):
        raise RuntimeError("db down")
    monkeypatch.setattr(keystore, "get", boom)
    assert _levels() == {"telegram": "warn", "vapid": "info"}


def test_announce_one_alert_with_error_and_warn(clean, sent, caplog):
    settings.public_base_url = None
    settings.token_enc_key = ""
    clean.pop("vapid_private_key")
    with caplog.at_level(logging.WARNING, logger=config_check.__name__):
        config_check.announce()
    assert len(sent) == 1 and sent[0][0] == "config"
    text = sent[0][1]
    assert text.startswith("[설정]") and "PUBLIC_BASE_URL" in text and "TOKEN_ENC_KEY" in text
    assert "웹 푸시" not in text  # info는 알리지 않는다
    assert "enc-key" not in text and "123:token" not in text
    assert len([r for r in caplog.records if r.name == config_check.__name__]) == 2


def test_announce_silent_when_clean_or_info_only(clean, sent):
    config_check.announce()
    clean.pop("vapid_private_key")
    config_check.announce()
    assert sent == []


def test_announce_never_raises(monkeypatch, sent):
    monkeypatch.setattr(config_check, "problems", lambda: 1 / 0)
    config_check.announce()
    assert sent == []


def test_app_link_warns_once_and_returns_empty(clean, monkeypatch, caplog):
    monkeypatch.setattr(site_render, "_warned_no_base", False)
    monkeypatch.setattr(settings, "public_base_url", None)
    with caplog.at_level(logging.WARNING, logger=site_render.__name__):
        assert site_render.app_link("/chat/k1") == ""
        assert site_render.app_link("/order/k1") == ""
    warned = [r for r in caplog.records if r.name == site_render.__name__]
    assert len(warned) == 1 and "PUBLIC_BASE_URL" in warned[0].getMessage()
    monkeypatch.setattr(settings, "public_base_url", "https://app.example/")
    assert site_render.app_link("/chat/k1") == "https://app.example/chat/k1"
    monkeypatch.setattr(settings, "preview_host", None)
    monkeypatch.setattr(settings, "public_base_url", None)
    assert site_render.app_link("/chat/k1") == "/chat/k1"


def _err(status):
    req = httpx.Request("POST", "https://x/v1/chat/completions")
    return openai.APIStatusError("gone", response=httpx.Response(status, request=req), body=None)


def test_gone_model_alerts_and_still_falls_back(clean, sent):
    def call(model):
        if model == "primary":
            raise _err(404)
        return f"ok:{model}"

    assert llm._with_fallback(call) == "ok:second"
    assert sent == [("model_gone:primary", "[AI] 모델 primary 응답 없음(404) · 대비 모델로 넘겼어요 · 서버 .env NIM_CHAT_MODEL 확인")]
    assert llm.gone("primary") and not llm.gone("second")
    assert _levels() == {"nim_chat_model": "error"}


def test_gone_alert_names_the_right_key(clean, sent, monkeypatch):
    # 대비 모델이 없어졌으면 대비 모델 키를, 넘길 모델이 없으면 '넘겼어요'를 쓰지 않는다
    with pytest.raises(openai.APIStatusError):
        llm._with_fallback(lambda m: (_ for _ in ()).throw(_err(410)))
    assert list(dict.fromkeys(sent)) == [  # 두 바퀴 돌아 같은 알림이 두 번 (ops_alert가 종류별로 묶는다)
        ("model_gone:primary", "[AI] 모델 primary 응답 없음(410) · 대비 모델로 넘겼어요 · 서버 .env NIM_CHAT_MODEL 확인"),
        ("model_gone:second", "[AI] 모델 second 응답 없음(410) · 대비 모델로 넘겼어요 · 서버 .env NIM_CHAT_FALLBACK_MODELS 확인")]
    sent.clear()
    monkeypatch.setattr(settings, "nim_chat_fallback_models", "")
    with pytest.raises(openai.APIStatusError):
        llm._with_fallback(lambda m: (_ for _ in ()).throw(_err(404)))
    assert sent == [("model_gone:primary", "[AI] 모델 primary 응답 없음(404) · 서버 .env NIM_CHAT_MODEL 확인")]


def test_gone_clears_when_model_answers_again(clean, sent):
    llm._gone["primary"] = llm.time.monotonic() + 60
    assert llm._with_fallback(lambda m: "ok") == "ok"
    assert not llm.gone("primary") and _levels() == {}


def test_overload_is_not_gone(clean, sent):
    def call(model):
        if model == "primary":
            raise openai.InternalServerError("busy", response=httpx.Response(
                503, request=httpx.Request("POST", "https://x")), body=None)
        return "ok"

    assert llm._with_fallback(call) == "ok"
    assert sent == [] and not llm.gone("primary")


def test_alert_failure_does_not_break_fallback(clean, monkeypatch):
    monkeypatch.setattr(ops_alert, "send", lambda *a, **k: 1 / 0)
    assert llm._with_fallback(lambda m: (_ for _ in ()).throw(_err(410)) if m == "primary" else "ok") == "ok"


ADMIN, OWNER = "u_admin_cfg", "u_owner_cfg"


def test_admin_endpoint(client, monkeypatch):
    with get_sessionmaker()() as db, db.begin():
        db.add_all([UserRow(id=ADMIN, nickname="관리자"), UserRow(id=OWNER, nickname="사장님")])
    monkeypatch.setattr(settings, "admin_user_ids", ADMIN)
    monkeypatch.setattr(config_check, "problems", lambda: [{"key": "telegram", "level": "warn", "text": "t", "fix": "f"}])
    assert client.get("/api/admin/config-check").status_code == 401
    client.cookies.set(auth_svc.SESSION_COOKIE, auth_svc.create_session(OWNER))
    assert client.get("/api/admin/config-check").status_code == 404
    client.cookies.set(auth_svc.SESSION_COOKIE, auth_svc.create_session(ADMIN))
    r = client.get("/api/admin/config-check")
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    assert r.json() == {"problems": [{"key": "telegram", "level": "warn", "text": "t", "fix": "f"}]}
    with get_sessionmaker()() as db:
        rows = db.execute(select(AdminAuditRow.action).where(AdminAuditRow.user_id == ADMIN)).scalars().all()
    assert "view:config-check" in rows
