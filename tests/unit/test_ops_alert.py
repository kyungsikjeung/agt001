"""운영자 텔레그램 알림 (OPS_ALERT_CONTRACT). 텔레그램은 부르지 않는다(보내기는 가짜)."""
import logging

import pytest

from app.config import settings
from app.services import funnel, keystore, ops_alert
from app.services import prd_engine as E


@pytest.fixture
def sent(monkeypatch):
    out = []
    monkeypatch.setattr(ops_alert, "_dispatch", out.append)
    monkeypatch.setattr(keystore, "get", lambda name: "123:token" if name == "telegram_bot_token" else None)
    monkeypatch.setattr(settings, "telegram_chat_id", "42")
    monkeypatch.setattr(ops_alert, "_last", {})
    monkeypatch.setattr(ops_alert, "_skipped", {})
    return out


def test_off_without_chat_id(sent, monkeypatch):
    monkeypatch.setattr(settings, "telegram_chat_id", "")
    assert ops_alert.send("x", "안녕") is False and sent == []


def test_once_per_ten_minutes_then_count(sent):
    assert ops_alert.send("x", "첫째") is True
    assert ops_alert.send("x", "둘째") is False
    assert ops_alert.send("y", "다른 종류") is True
    ops_alert._last["x"] -= ops_alert.COOLDOWN_SEC + 1
    assert ops_alert.send("x", "셋째") is True
    assert sent == ["첫째", "다른 종류", "셋째\n(그사이 같은 알림 1건 더)"]


def test_masks_phone_numbers(sent):
    ops_alert.send("x", "손님 010-1234-5678")
    assert "010-1234-5678" not in sent[0] and "[전화]" in sent[0]


def test_funnel_events(sent):
    funnel.record("site_published", props={"site": "k1", "industry": "cafe", "variant": "v1"})
    funnel.record("design_shown", props={"site": "k1"})
    funnel.record("webhook_bad_signature", props={"reason": "sig"})
    assert sent == ["[공개] 새 사이트 k1 · cafe · v1안", "[결제] 웹훅 서명 실패 · sig"]


def test_blocked_request_alerts(sent):
    card = E.new_card("cafe")
    result = E.turn(card, "피싱 사이트 만들어 주세요")
    assert result.get("blocked") and len(sent) == 1 and sent[0].startswith("[대화] 금지 요청을 막았어요")


def test_error_logs_alert_but_not_its_own(sent):
    ops_alert.install()
    logging.getLogger("app.somewhere").error("저장 실패 %s", "x")
    logging.getLogger("app.services.ops_alert").error("텔레그램 알림 실패")
    logging.getLogger("httpx").error("연결 끊김")
    assert sent == ["[오류] app.somewhere · 저장 실패 x"]


def test_httpx_log_line_with_bot_token_is_dropped(caplog):
    with caplog.at_level(logging.INFO, logger="httpx"):
        logging.getLogger("httpx").info("HTTP Request: POST https://api.telegram.org/bot123:token/sendMessage")
        logging.getLogger("httpx").info("HTTP Request: POST https://example.com/x")
    assert "api.telegram.org" not in caplog.text and "example.com" in caplog.text
