"""NIM(OpenAI 호환) 호출의 단일 진입점. 모델 교체·병행은 이 모듈에서만 처리한다."""
from functools import lru_cache

from openai import OpenAI

from app.config import settings


@lru_cache(maxsize=1)
def _client() -> OpenAI:
    return OpenAI(
        api_key=settings.nim_api_key,
        base_url=settings.nim_base_url,
        timeout=settings.nim_timeout_sec,
        max_retries=1,
    )


def chat(messages: list[dict]) -> str:
    completion = _client().chat.completions.create(model=settings.nim_chat_model, messages=messages)
    return completion.choices[0].message.content


def embed(text: str) -> list[float]:
    resp = _client().embeddings.create(model=settings.nim_embed_model, input=text)
    return resp.data[0].embedding


def chat_json(system: str, user: str, timeout_sec: float = 20.0, max_tokens: int = 700) -> str:
    """정해진 JSON만 받아야 하는 호출(요구사항 추출 등).

    실측(docs/product/research/REQUIREMENTS_ENGINE_RESEARCH.md §5): 이 모델은 추론형이라 생각 과정을
    본문에 먼저 쓰고, guided_json·response_format 스키마 강제는 오히려 형식을 깨뜨린다.
    추론을 끄고 스키마는 system 프롬프트에 넣은 뒤, 호출한 쪽이 결과를 검증한다.
    """
    completion = _client().with_options(timeout=timeout_sec).chat.completions.create(
        model=settings.nim_chat_model,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=0,
        max_tokens=max_tokens,
        extra_body={"chat_template_kwargs": {"enable_thinking": False}},
    )
    return (completion.choices[0].message.content or "").strip()
