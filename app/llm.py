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
