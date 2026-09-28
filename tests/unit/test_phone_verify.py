"""문자 인증 바탕 (CUSTOMER_PLAN §4.2 V1): 개발 모드 발송·틀림·잠김·만료·재요청 제한·쿠키 서명."""
import datetime
import hashlib
import hmac
import logging
import re
import secrets

import pytest
from sqlalchemy import delete, select, update

from app.config import settings
from app.db.models import PhoneVerificationRow
from app.db.session import get_sessionmaker
from app.services import phone_verify, sms
from app.services.phone_verify import VerifyError


@pytest.fixture(autouse=True)
def _clean_settings(monkeypatch):
    monkeypatch.setattr(settings, "solapi_api_key", None)
    monkeypatch.setattr(settings, "solapi_api_secret", None)
    monkeypatch.setattr(settings, "sms_sender", None)
    monkeypatch.setattr(settings, "public_base_url", None)
    with get_sessionmaker()() as db, db.begin():
        db.execute(delete(PhoneVerificationRow))  # 하루 제한이 테스트끼리 섞이지 않게


def _site():
    return f"pv-{secrets.token_hex(4)}"


def _capture(monkeypatch):
    sent = {"texts": []}

    def fake_send(to, text):
        sent["texts"].append((to, text))
        return True

    monkeypatch.setattr(sms, "send", fake_send)
    return sent


def _code_of(text):
    return re.search(r"인증번호 (\d{6})", text).group(1)


def _row(token):
    with get_sessionmaker()() as db:
        return db.scalar(select(PhoneVerificationRow).where(PhoneVerificationRow.token == token))


def test_dev_mode_no_keys_returns_true_and_logs_only_last4(caplog):
    with caplog.at_level(logging.WARNING):
        assert sms.send("010-1234-5678", "인증번호 123456") is True
    assert "5678" in caplog.text
    assert "010-1234-5678" not in caplog.text and "01012345678" not in caplog.text


def test_start_check_roundtrip_deletes_row(monkeypatch):
    sent = _capture(monkeypatch)
    site = _site()
    payload = {"name": "김손님", "date": "2026-10-01"}
    token = phone_verify.start(site, "010-1234-5678", payload, "우리 가게")
    assert token
    to, text = sent["texts"][-1]
    assert to == "01012345678"
    assert "[우리 가게] 인증번호" in text
    assert phone_verify.check(token, _code_of(text)) == payload
    assert _row(token) is None
    with pytest.raises(VerifyError, match="인증 요청을 찾을 수 없어요"):
        phone_verify.check(token, "000000")


def test_start_default_shop_name(monkeypatch):
    sent = _capture(monkeypatch)
    phone_verify.start(_site(), "010-1234-5678", {"a": 1}, "")
    assert "[예약] 인증번호" in sent["texts"][-1][1]


def test_start_bad_phone_and_unknown_token(monkeypatch):
    _capture(monkeypatch)
    with pytest.raises(VerifyError, match="전화번호를 다시 확인해 주세요"):
        phone_verify.start(_site(), "abc", {}, None)
    with pytest.raises(VerifyError, match="인증 요청을 찾을 수 없어요"):
        phone_verify.check("no-such-token", "123456")


def test_start_send_failure(monkeypatch):
    monkeypatch.setattr(sms, "send", lambda to, text: False)
    with pytest.raises(VerifyError, match="인증번호를 보내지 못했어요"):
        phone_verify.start(_site(), "010-1234-5678", {}, None)


def test_second_start_within_60s_rejected(monkeypatch):
    sent = _capture(monkeypatch)
    site = _site()
    phone_verify.start(site, "010-1234-5678", {}, None)
    with pytest.raises(VerifyError, match="인증번호는 1분 뒤에"):
        phone_verify.start(site, "01012345678", {}, None)
    # 다른 번호는 같은 가게에서도 바로 받을 수 있다
    phone_verify.start(site, "010-9999-8888", {}, None)
    assert len(sent["texts"]) == 2


@pytest.mark.parametrize("nth,left", [(1, 4), (2, 3), (3, 2), (4, 1)])
def test_wrong_code_shows_remaining(monkeypatch, nth, left):
    sent = _capture(monkeypatch)
    token = phone_verify.start(_site(), "010-1234-5678", {}, None)
    for _ in range(nth - 1):
        with pytest.raises(VerifyError):
            phone_verify.check(token, "000000")
    with pytest.raises(VerifyError, match=rf"남은 횟수 {left}번"):
        phone_verify.check(token, "000000")
    assert _row(token) is not None


def test_five_wrong_locks_then_correct_also_locked(monkeypatch):
    sent = _capture(monkeypatch)
    token = phone_verify.start(_site(), "010-1234-5678", {}, None)
    code = _code_of(sent["texts"][-1][1])
    for _ in range(4):
        with pytest.raises(VerifyError, match="남은 횟수"):
            phone_verify.check(token, "000000")
    with pytest.raises(VerifyError, match="여러 번 틀려서 잠겼어요"):
        phone_verify.check(token, "000000")
    with pytest.raises(VerifyError, match="여러 번 틀려서 잠겼어요"):
        phone_verify.check(token, code)


def test_expired(monkeypatch):
    sent = _capture(monkeypatch)
    token = phone_verify.start(_site(), "010-1234-5678", {}, None)
    code = _code_of(sent["texts"][-1][1])
    past = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=5)
    with get_sessionmaker()() as db, db.begin():
        db.execute(update(PhoneVerificationRow).where(PhoneVerificationRow.token == token)
                   .values(expires_at=past))
    with pytest.raises(VerifyError, match="인증 시간이 지났어요"):
        phone_verify.check(token, code)


def test_resend_new_token_old_invalid(monkeypatch):
    sent = _capture(monkeypatch)
    site = _site()
    payload = {"name": "김손님"}
    old = phone_verify.start(site, "010-1234-5678", payload, "우리 가게")
    old_code = _code_of(sent["texts"][-1][1])
    with get_sessionmaker()() as db, db.begin():  # 다시 보내기 1분 제한을 지난 것으로
        db.execute(update(PhoneVerificationRow).where(PhoneVerificationRow.token == old)
                   .values(created_at=datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=2)))
    new = phone_verify.resend(old)
    assert new and new != old
    with pytest.raises(VerifyError, match="인증 요청을 찾을 수 없어요"):
        phone_verify.check(old, old_code)
    with pytest.raises(VerifyError, match="인증 요청을 찾을 수 없어요"):
        phone_verify.resend(old)
    assert phone_verify.check(new, _code_of(sent["texts"][-1][1])) == payload


def test_resend_unknown_token(monkeypatch):
    _capture(monkeypatch)
    with pytest.raises(VerifyError, match="인증 요청을 찾을 수 없어요"):
        phone_verify.resend("no-such-token")


def test_purge_deletes_only_day_old_expired(monkeypatch):
    sent = _capture(monkeypatch)
    old_token = phone_verify.start(_site(), "010-1111-2222", {}, None)
    fresh_token = phone_verify.start(_site(), "010-3333-4444", {"a": 1}, None)
    two_days_ago = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=2)
    with get_sessionmaker()() as db, db.begin():
        db.execute(update(PhoneVerificationRow).where(PhoneVerificationRow.token == old_token)
                   .values(expires_at=two_days_ago))
    assert phone_verify.purge() >= 1
    assert _row(old_token) is None
    assert phone_verify.check(fresh_token, _code_of(sent["texts"][-1][1])) == {"a": 1}


def test_sms_text_has_web_otp_suffix(monkeypatch):
    monkeypatch.setattr(settings, "public_base_url", "https://example.com")
    sent = _capture(monkeypatch)
    phone_verify.start(_site(), "010-1234-5678", {}, "우리 가게")
    text = sent["texts"][-1][1]
    code = _code_of(text)
    assert f"@example.com #{code}" in text


def test_sms_text_no_suffix_without_base_url(monkeypatch):
    sent = _capture(monkeypatch)
    phone_verify.start(_site(), "010-1234-5678", {}, None)
    assert "@" not in sent["texts"][-1][1]


def test_device_cookie_roundtrip_and_rejections(monkeypatch):
    monkeypatch.setattr(settings, "token_enc_key", "test-device-key")
    site = _site()
    cookie = phone_verify.device_cookie(site, "01012345678")
    assert cookie
    assert phone_verify.device_ok(cookie, site, "010-1234-5678")
    assert not phone_verify.device_ok(cookie, site, "010-9999-8888")
    assert not phone_verify.device_ok(cookie, "other-site", "010-1234-5678")
    tampered = cookie[:-1] + ("0" if cookie[-1] != "0" else "1")
    assert not phone_verify.device_ok(tampered, site, "010-1234-5678")
    assert not phone_verify.device_ok("junk", site, "010-1234-5678")
    assert not phone_verify.device_ok("", site, "010-1234-5678")
    phone, _, _ = cookie.split(".")
    past = str(int(datetime.datetime.now(datetime.timezone.utc).timestamp()) - 10)
    sig = hmac.new(b"test-device-key", f"{site}:{phone}:{past}".encode(), hashlib.sha256).hexdigest()
    assert not phone_verify.device_ok(f"{phone}.{past}.{sig}", site, "01012345678")


def test_device_cookie_falls_back_to_kakao_secret(monkeypatch):
    monkeypatch.setattr(settings, "token_enc_key", None)
    monkeypatch.setattr(settings, "kakao_client_secret", "kakao-secret")
    cookie = phone_verify.device_cookie("s1", "01012345678")
    assert cookie and phone_verify.device_ok(cookie, "s1", "010-1234-5678")


def test_device_no_key_configured(monkeypatch):
    monkeypatch.setattr(settings, "token_enc_key", None)
    monkeypatch.setattr(settings, "kakao_client_secret", None)
    assert phone_verify.device_cookie("s1", "01012345678") is None
    assert phone_verify.device_ok("a.b.c", "s1", "01012345678") is False


def test_daily_cap_and_resend_wait(monkeypatch):
    """한 번호로 하루 5번까지(가게 상관없이), 다시 보내기도 1분 제한을 따른다."""
    sent = _capture(monkeypatch)
    token = phone_verify.start(_site(), "010-5555-0000", {"a": 1})
    with pytest.raises(VerifyError, match="1분 뒤"):
        phone_verify.resend(token)
    for _ in range(4):
        phone_verify.start(_site(), "010-5555-0000", {"a": 1})
    with pytest.raises(VerifyError, match="오늘은"):
        phone_verify.start(_site(), "010-5555-0000", {"a": 1})
    assert len(sent["texts"]) == 5


def test_resend_keeps_shop_name(monkeypatch):
    sent = _capture(monkeypatch)
    site = _site()
    token = phone_verify.start(site, "010-5555-1111", {"a": 1}, shop_name="단정손끝")
    with get_sessionmaker()() as db, db.begin():
        db.execute(update(PhoneVerificationRow).where(PhoneVerificationRow.token == token)
                   .values(created_at=datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=2)))
    new = phone_verify.resend(token)
    assert sent["texts"][-1][1].startswith("[단정손끝]")
    assert phone_verify.check(new, _code_of(sent["texts"][-1][1])) == {"a": 1}
