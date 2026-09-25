"""AI 답장 읽어주기: WAV 머리말·길이 제한·상태 코드. 실제 호출 없이 가짜 Riva로."""
import struct
import sys
import types

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import tts as tts_api
from app.config import settings
from app.services import tts

FAKE_PCM = b"\x01\x02" * 2205  # 날것 PCM 흉내 (2205개 샘플)


@pytest.fixture
def tts_client():
    # app/main.py 라우터 등록은 건드리지 않고 테스트 안에서 직접 붙인다.
    app = FastAPI()
    app.include_router(tts_api.router)
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def _reset_limit():
    tts_api._hits.clear()
    yield
    tts_api._hits.clear()


def _post(client, text="안녕하세요", member="m1"):
    headers = {"X-Member-Id": member} if member else {}
    return client.post("/api/tts", json={"text": text}, headers=headers)


def _fake_riva(monkeypatch, on_synthesize=None):
    """SpeechSynthesisService 흉내 모듈을 sys.modules에 꽂는다. 실제 호출 없음."""
    seen = {}

    class FakeFuture:
        def __init__(self, resp):
            self._resp = resp

        def result(self, timeout=None):
            assert timeout == settings.tts_timeout_sec
            return self._resp

    class FakeResp:
        def __init__(self, audio):
            self.audio = audio

    class FakeSvc:
        def __init__(self, auth):
            seen["auth"] = auth

        def synthesize(self, text, **kwargs):
            seen["text"] = text
            seen.update(kwargs)
            if on_synthesize is not None:
                return on_synthesize(text, kwargs)
            return FakeFuture(FakeResp(FAKE_PCM))

    fake_client = types.ModuleType("riva.client")
    fake_client.Auth = lambda **kwargs: ("auth", kwargs)
    fake_client.AudioEncoding = types.SimpleNamespace(LINEAR_PCM="LINEAR_PCM")
    fake_client.SpeechSynthesisService = FakeSvc
    fake_pkg = types.ModuleType("riva")
    fake_pkg.client = fake_client
    monkeypatch.setitem(sys.modules, "riva", fake_pkg)
    monkeypatch.setitem(sys.modules, "riva.client", fake_client)
    return seen


def test_success_returns_wav_with_header(tts_client, monkeypatch):
    monkeypatch.setattr(tts, "_synthesize_pcm", lambda text: FAKE_PCM)
    r = _post(tts_client)
    assert r.status_code == 200
    assert r.headers["content-type"] == "audio/wav"
    assert r.headers["cache-control"] == "no-store"
    body = r.content
    assert body[:4] == b"RIFF"
    assert body[8:12] == b"WAVE"
    (rate,) = struct.unpack("<I", body[24:28])
    assert rate == 22050
    (bits,) = struct.unpack("<H", body[34:36])
    assert bits == 16
    assert body[44:] == FAKE_PCM


def test_fake_riva_service_call_shape(monkeypatch):
    seen = _fake_riva(monkeypatch)
    wav = tts.synthesize("안녕하세요")
    assert wav[:4] == b"RIFF"
    assert wav[44:] == FAKE_PCM
    assert seen["text"] == "안녕하세요"
    assert seen["voice_name"] == settings.tts_voice
    assert seen["language_code"] == "ko-KR"
    assert seen["sample_rate_hz"] == 22050


def test_rejects_missing_member_and_empty_text(tts_client, monkeypatch):
    monkeypatch.setattr(tts, "_synthesize_pcm", lambda text: FAKE_PCM)
    assert _post(tts_client, member=None).status_code == 400
    assert _post(tts_client, text="").status_code == 400
    assert _post(tts_client, text="   ").status_code == 400


def test_truncates_to_300_chars(tts_client, monkeypatch):
    seen = {}

    def fake_pcm(text):
        seen["text"] = text
        return FAKE_PCM

    monkeypatch.setattr(tts, "_synthesize_pcm", fake_pcm)
    r = _post(tts_client, text="가" * 350)
    assert r.status_code == 200
    assert len(seen["text"]) == 300


def test_unavailable_returns_503(tts_client, monkeypatch):
    # 꺼짐·키 없음은 진짜 synthesize 경로로 확인한다 (가짜 PCM이 검사를 우회하지 않게).
    monkeypatch.setattr(settings, "tts_enabled", False)
    assert _post(tts_client).status_code == 503
    monkeypatch.setattr(settings, "tts_enabled", True)
    monkeypatch.setattr(settings, "nvidia_api_key", None)
    monkeypatch.setattr(settings, "nim_api_key", "")
    assert _post(tts_client).status_code == 503


def test_upstream_error_returns_502(tts_client, monkeypatch):
    def down(text):
        raise tts.TtsUpstream("down")

    monkeypatch.setattr(tts, "_synthesize_pcm", down)
    assert _post(tts_client).status_code == 502


def test_riva_exception_becomes_502(monkeypatch):
    def boom(text, kwargs):
        raise RuntimeError("riva down")

    _fake_riva(monkeypatch, on_synthesize=boom)
    with pytest.raises(tts.TtsUpstream):
        tts.synthesize("안녕하세요")


def test_rate_limit(tts_client, monkeypatch):
    monkeypatch.setattr(tts, "_synthesize_pcm", lambda text: FAKE_PCM)
    monkeypatch.setattr(tts_api, "RATE_LIMIT_PER_MIN", 2)
    assert [_post(tts_client).status_code for _ in range(3)] == [200, 200, 429]
