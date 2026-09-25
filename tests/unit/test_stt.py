"""음성 입력 API: 형식·크기·빈도 제한, 숫자 변환, 녹음 미저장, 외부 장애 시 503."""
import pytest

from app.api import stt as stt_api
from app.services import stt


@pytest.fixture(autouse=True)
def _reset_limit():
    stt_api._hits.clear()
    yield
    stt_api._hits.clear()


def _post(client, data=b"fake-audio", ctype="audio/webm", member="m1"):
    headers = {"X-Member-Id": member} if member else {}
    return client.post("/api/stt", files={"audio": ("a.webm", data, ctype)}, headers=headers)


def test_transcribes_and_normalizes_phone(client, monkeypatch):
    monkeypatch.setattr(stt, "to_wav16k", lambda data: b"wav")
    monkeypatch.setattr(stt, "_recognize", lambda wav: "번호는 공일공 공공공공 일이삼사입니다.")
    r = _post(client)
    assert r.status_code == 200
    assert r.json()["text"] == "번호는 010-0000-1234입니다."


def test_short_korean_words_are_not_converted():
    assert stt.normalize_digits("이 사진 일단 올릴게요") == "이 사진 일단 올릴게요"


def test_rejects_bad_type_size_and_missing_member(client, monkeypatch):
    monkeypatch.setattr(stt, "transcribe", lambda data: "x")
    assert _post(client, ctype="image/png").status_code == 415
    assert _post(client, data=b"0" * (stt.MAX_BYTES + 1)).status_code == 413
    assert _post(client, member=None).status_code == 400
    assert _post(client, data=b"").status_code == 400


def test_unavailable_returns_503(client, monkeypatch):
    def down(data):
        raise stt.SttUnavailable("down")
    monkeypatch.setattr(stt, "transcribe", down)
    assert _post(client).status_code == 503


def test_rate_limit(client, monkeypatch):
    monkeypatch.setattr(stt, "transcribe", lambda data: "x")
    monkeypatch.setattr(stt_api, "RATE_LIMIT_PER_MIN", 2)
    assert [_post(client).status_code for _ in range(3)] == [200, 200, 429]


def test_digit_run_with_multiple_spaces():
    # 실측: Parakeet가 "공일공  공공공공일이삼사"처럼 공백 두 칸을 넣는다
    assert stt.normalize_digits("번호는 공일공  공공공공일이삼사입니다.") == "번호는 010-0000-1234입니다."
