"""NIM 대비 모델 (D28): 과부하면 다음 모델, 요청 오류는 넘기지 않음, 실패 모델은 잠시 건너뜀."""
import httpx
import openai
import pytest

from app import llm
from app.config import settings


def _err(cls, status):
    req = httpx.Request("POST", "https://x/v1/chat/completions")
    return cls("boom", response=httpx.Response(status, request=req), body=None)


@pytest.fixture(autouse=True)
def _setup(monkeypatch):
    monkeypatch.setattr(settings, "nim_chat_model", "primary")
    monkeypatch.setattr(settings, "nim_chat_fallback_models", "second,third")
    llm._cooldown.clear()
    yield
    llm._cooldown.clear()


def test_overloaded_primary_falls_back():
    calls = []

    def call(model):
        calls.append(model)
        if model == "primary":
            raise _err(openai.InternalServerError, 503)
        return f"ok:{model}"

    assert llm._with_fallback(call) == "ok:second"
    # 주 모델은 쉬는 중이라 다음 호출은 대비 모델부터
    calls.clear()
    assert llm._with_fallback(call) == "ok:second"
    assert calls == ["second"]


def test_bad_request_is_not_retried_on_other_models():
    calls = []

    def call(model):
        calls.append(model)
        raise _err(openai.BadRequestError, 400)

    with pytest.raises(openai.BadRequestError):
        llm._with_fallback(call)
    assert calls == ["primary"]


def test_all_fail_raises_last_error():
    def call(model):
        raise _err(openai.RateLimitError, 429)

    with pytest.raises(openai.RateLimitError):
        llm._with_fallback(call)
    # 모두 쉬는 중이어도 다음 호출은 한 번씩 시도한다
    seen = []
    with pytest.raises(openai.RateLimitError):
        llm._with_fallback(lambda m: seen.append(m) or (_ for _ in ()).throw(_err(openai.RateLimitError, 429)))
    assert seen == ["primary", "second", "third"]
