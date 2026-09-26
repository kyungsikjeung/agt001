"""NIM(OpenAI 호환) 호출의 단일 진입점. 모델 교체·병행은 이 모듈에서만 처리한다."""
import logging
import threading
import time
from functools import lru_cache
from typing import Callable

import openai
from openai import OpenAI

from app.config import settings

log = logging.getLogger(__name__)

# 다음 모델로 넘어갈 오류: 과부하·요청 제한·서버 오류·시간 초과·연결 실패. 요청이 틀린 경우(400 등)는 넘기지 않는다.
_RETRYABLE = (openai.APITimeoutError, openai.APIConnectionError, openai.RateLimitError, openai.InternalServerError)
_cooldown: dict[str, float] = {}
_lock = threading.Lock()


@lru_cache(maxsize=2)
def _client_for(api_key: str) -> OpenAI:
    return OpenAI(
        api_key=api_key,
        base_url=settings.nim_base_url,
        timeout=settings.nim_timeout_sec,
        max_retries=1,
    )


def _client() -> OpenAI:
    # 키는 관리자 화면에서 바뀔 수 있다(D50). 바뀐 키로 새 클라이언트를 만든다.
    from app.services import keystore
    return _client_for(keystore.get("nim_api_key") or "")


def reset_client() -> None:
    _client_for.cache_clear()


def _models() -> list[str]:
    fallbacks = [m.strip() for m in (settings.nim_chat_fallback_models or "").split(",") if m.strip()]
    return list(dict.fromkeys([settings.nim_chat_model, *fallbacks]))


def _with_fallback(call: Callable[[str], str]) -> str:
    """주 모델 → 대비 모델 차례로 부른다 (D28). 최근 실패한 모델은 쉬는 동안 뒤로 미룬다."""
    models = _models()
    now = time.monotonic()
    with _lock:
        ready = [m for m in models if _cooldown.get(m, 0) <= now]
    order = ready + [m for m in models if m not in ready]  # 다 쉬는 중이어도 한 번씩은 시도한다
    last_exc: Exception | None = None
    # 모든 모델이 한꺼번에 과부하일 때가 있다(평가 중 실측). 한 바퀴 실패하면 잠깐 쉬고 한 번 더 돈다.
    for model in order + ([None] + order if len(order) > 1 else []):
        if model is None:
            time.sleep(settings.nim_all_fail_backoff_sec)
            continue
        try:
            out = call(model)
        except _RETRYABLE as e:
            last_exc = e
            with _lock:
                _cooldown[model] = time.monotonic() + settings.nim_fallback_cooldown_sec
            log.warning("NIM 모델 %s 실패(%s) → 다음 모델", model, type(e).__name__)
            continue
        if model != settings.nim_chat_model:
            log.info("NIM 대비 모델 %s로 응답", model)
        return out
    assert last_exc is not None
    raise last_exc


def chat(messages: list[dict]) -> str:
    def call(model: str) -> str:
        opts = _client().with_options(max_retries=0) if len(_models()) > 1 else _client()
        return opts.chat.completions.create(model=model, messages=messages).choices[0].message.content
    return _with_fallback(call)


def embed(text: str) -> list[float]:
    resp = _client().embeddings.create(model=settings.nim_embed_model, input=text)
    return resp.data[0].embedding


def embed_many(texts: list[str]) -> list[list[float]]:
    """여러 문장을 한 번에 (기동 시 사례집 임베딩: 51개 한 번 호출 약 2.4초)."""
    resp = _client().embeddings.create(model=settings.nim_embed_model, input=texts)
    return [d.embedding for d in sorted(resp.data, key=lambda d: d.index)]


def chat_json(system: str, user: str, timeout_sec: float = 20.0, max_tokens: int = 700) -> str:
    """정해진 JSON만 받아야 하는 호출(요구사항 추출 등).

    실측(docs/product/research/REQUIREMENTS_ENGINE_RESEARCH.md §5): 이 모델은 추론형이라 생각 과정을
    본문에 먼저 쓰고, guided_json·response_format 스키마 강제는 오히려 형식을 깨뜨린다.
    추론을 끄고 스키마는 system 프롬프트에 넣은 뒤, 호출한 쪽이 결과를 검증한다.
    """
    def call(model: str) -> str:
        # 대비 모델이 있으면 같은 모델 재시도 대신 바로 다음 모델로 간다.
        client = _client().with_options(timeout=timeout_sec, max_retries=0 if len(_models()) > 1 else 1)
        completion = client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0,
            max_tokens=max_tokens,
            extra_body={"chat_template_kwargs": {"enable_thinking": False}},
        )
        return (completion.choices[0].message.content or "").strip()
    return _with_fallback(call)
