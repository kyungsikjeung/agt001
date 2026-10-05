"""NIM(OpenAI 호환) 호출의 단일 진입점. 모델 교체·병행은 이 모듈에서만 처리한다."""
import logging
import re
import threading
import time
from functools import lru_cache
from typing import Callable

import openai
from openai import OpenAI

from app.config import settings

log = logging.getLogger(__name__)

# 사람에게 보이는 글은 모두 한국어 (BETA_FLOW_PLAN §2.1).
KO_RULE = ("사람에게 보이는 글(값·설명·이유·답·문구)은 모두 한국어로 쓴다. 영어로 번역하지 않는다. "
           "사장님이 영어로 쓴 가게 이름·주소·링크·이메일은 그대로 둔다. JSON 키와 정해진 목록의 영문 값은 그대로 쓴다.")

# 다음 모델로 넘어갈 오류: 과부하·요청 제한·서버 오류·시간 초과·연결 실패. 요청이 틀린 경우(400 등)는 넘기지 않는다.
_RETRYABLE = (openai.APITimeoutError, openai.APIConnectionError, openai.RateLimitError, openai.InternalServerError)
# 없어진 모델(404·410, 예: 2026-10-03 nemotron-3-super 서비스 종료)도 다음 모델로 넘기고 하루 쉬게 한다.
_GONE_STATUS = (404, 410)
_GONE_COOLDOWN_SEC = 86400.0
_cooldown: dict[str, float] = {}
_gone: dict[str, float] = {}  # 없어진 모델 → 쉬는 끝 시각 (설정 점검이 읽는다, config_check)
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


def gone(model: str) -> bool:
    """이 모델이 최근 404·410(없어진 모델)으로 답해 쉬는 중인가. 읽기만 한다."""
    with _lock:
        return _gone.get(model, 0) > time.monotonic()


def _alert_gone(model: str, status: int) -> None:
    """없어진 모델을 운영자에게 알린다(10/3 서비스 종료를 아무도 몰랐다). 알림이 실패해도 대비 모델로 간다."""
    try:
        from app.services import ops_alert
        env = "NIM_CHAT_MODEL" if model == settings.nim_chat_model else "NIM_CHAT_FALLBACK_MODELS"
        moved = " · 대비 모델로 넘겼어요" if len(_models()) > 1 else ""
        # 모델마다 따로: 같은 종류 알림은 10분에 한 건이라 둘째 모델 이름이 묻힌다
        ops_alert.send(f"model_gone:{model}", f"[AI] 모델 {model} 응답 없음({status}){moved} · 서버 .env {env} 확인")
    except Exception:
        pass


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
        except openai.APIError as e:
            is_gone = isinstance(e, openai.APIStatusError) and e.status_code in _GONE_STATUS
            if not (is_gone or isinstance(e, _RETRYABLE)):
                raise
            last_exc = e
            with _lock:
                _cooldown[model] = time.monotonic() + (_GONE_COOLDOWN_SEC if is_gone else settings.nim_fallback_cooldown_sec)
                if is_gone:
                    _gone[model] = _cooldown[model]
            log.warning("NIM 모델 %s 실패(%s) → 다음 모델", model, type(e).__name__)
            if is_gone:
                _alert_gone(model, e.status_code)
            continue
        with _lock:
            _gone.pop(model, None)  # 다시 답하면 관리자 화면의 '응답 없음'을 내린다 (쉬기는 그대로)
        if model != settings.nim_chat_model:
            log.info("NIM 대비 모델 %s로 응답", model)
        return out
    assert last_exc is not None
    raise last_exc


def foreign_words(value: str, source: str = "") -> list[str]:
    """값 안의 한국어 아닌 말: source에 없는 영문 낱말·한자·가나를 순서대로 (중복 없이)."""
    if not value:
        return []
    src = source or ""
    src_low = src.lower()
    hits: list[tuple[int, str]] = []
    for m in re.finditer(r"[A-Za-z]{3,}", value):
        w = m.group(0)
        if w.lower() not in src_low:
            hits.append((m.start(), w))
    for m in re.finditer(r"[\u3040-\u30ff\u4e00-\u9fff]", value):
        ch = m.group(0)
        if ch not in src:
            hits.append((m.start(), ch))
    hits.sort(key=lambda h: h[0])
    out, seen = [], set()
    for _, w in hits:
        if w not in seen:
            seen.add(w)
            out.append(w)
    return out


def chat(messages: list[dict]) -> str:
    send = list(messages or [])
    if not send or send[0].get("role") != "system":
        send = [{"role": "system", "content": KO_RULE}, *send]

    def call(model: str) -> str:
        opts = _client().with_options(max_retries=0) if len(_models()) > 1 else _client()
        return opts.chat.completions.create(model=model, messages=send).choices[0].message.content
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
            messages=[{"role": "system", "content": KO_RULE + "\n" + system}, {"role": "user", "content": user}],
            temperature=0,
            max_tokens=max_tokens,
            extra_body={"chat_template_kwargs": {"enable_thinking": False}},
        )
        return (completion.choices[0].message.content or "").strip()
    return _with_fallback(call)
