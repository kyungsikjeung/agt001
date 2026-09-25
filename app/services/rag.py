"""기존 프로젝트 유사도 사전확인 (contracts/rag_query.schema.json).

벡터 DB 없이 소수의 과거 프로젝트 문서를 NIM 임베딩으로 비교한다.
"""
import logging
import math
from typing import Optional

from app import llm
from app.config import settings

log = logging.getLogger(__name__)

FAKE_RAG_DOCS = [
    {"source": "SRS-2025-014.md", "text": "쇼핑몰 리뉴얼 프로젝트. React + Node.js, 결제 연동 포함, 예산 800만원."},
    {"source": "SRS-2025-021.md", "text": "사내 재고관리 시스템. Android 앱, 바코드 스캔, 예산 500만원."},
    {"source": "SRS-2026-003.md", "text": "카페 예약 서비스. 웹+카카오 알림톡 연동, 예산 350만원."},
]

_doc_embeddings: Optional[list[list[float]]] = None


def cosine_sim(a, b) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def ensure_doc_embeddings() -> list[list[float]]:
    global _doc_embeddings
    if _doc_embeddings is None:
        _doc_embeddings = [llm.embed(d["text"]) for d in FAKE_RAG_DOCS]
    return _doc_embeddings


def reset_cache() -> None:
    global _doc_embeddings
    _doc_embeddings = None


def precompute() -> None:
    """기동 시 선계산. NIM 장애면 첫 조회 때 재시도하도록 캐시를 비워 둔다."""
    try:
        ensure_doc_embeddings()
    except Exception:
        reset_cache()
        log.exception("문서 임베딩 선계산 생략 (첫 조회 때 재시도)")


def query(text: str, top_k: int = 1) -> dict:
    """request{query, top_k} -> response{chunks: [{text, source, score}]}, score는 코사인 유사도."""
    doc_embeddings = ensure_doc_embeddings()
    q_emb = llm.embed(text)
    scored = [
        {"text": doc["text"], "source": doc["source"], "score": cosine_sim(q_emb, d_emb)}
        for doc, d_emb in zip(FAKE_RAG_DOCS, doc_embeddings)
    ]
    scored.sort(key=lambda c: c["score"], reverse=True)
    return {"chunks": scored[: max(1, top_k)]}


def precheck(user_text: str) -> str:
    """상위 1개 문서의 유사도로 기존/신규를 판정한다. 임베딩 장애 시 신규로 폴백한다."""
    try:
        result = query(user_text, top_k=settings.rag_top_k)
    except Exception:
        log.exception("임베딩 검색 실패, 신규로 폴백")
        return "신규 프로젝트"
    if not result["chunks"]:
        return "신규 프로젝트"
    top = result["chunks"][0]
    if top["score"] < settings.rag_sim_threshold:
        return "신규 프로젝트"
    return f"기존 프로젝트: {top['source']}"
