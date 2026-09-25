"""비슷한 사례 찾기 (contracts/rag_query.schema.json).

자료는 우리가 직접 조사·관리하는 지식만 쓴다: 기능 사례집(app/data/feature_catalog.json)과
업종·문의 종류 프로필(prd_schema.INDUSTRIES). 다른 사장님의 대화·사실은 넣지 않는다(REQUIREMENTS_RAG_REVIEW 원칙).
예전에는 가짜 과거 프로젝트 3개로 "비슷한 이전 프로젝트가 있다"고 말했는데, 사실이 아니어서 바꿨다.
"""
import json
import logging
import math
from typing import Optional

from app import llm
from app.config import settings

log = logging.getLogger(__name__)

# 1위와 이 차이 안에 있는 사례까지 함께 보여 준다(최대 NOTE_MAX개).
NOTE_MARGIN = 0.045
NOTE_MAX = 2


def _build_docs() -> list[dict]:
    from app.services import prd_schema as S

    items = json.loads((settings.project_root / "app" / "data" / "feature_catalog.json").read_text(encoding="utf-8"))["items"]
    docs = [{"source": f"feature:{i['id']}", "name": i["name"],
             "text": f"{i['name']}. 이런 요청: {', '.join(i.get('aliases', [])[:6])}. 방법: {i.get('how', '')}"} for i in items]
    docs += [{"source": f"kind:{k}", "name": ind.name,
              "text": f"{ind.name} 사이트. 예: {', '.join(ind.aliases[:8])}. 주로 담는 내용: {', '.join(ind.default_sections)}"}
             for k, ind in S.INDUSTRIES.items() if k != "other"]
    return docs


DOCS = _build_docs()
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
        _doc_embeddings = llm.embed_many([d["text"] for d in DOCS])
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
        {"text": doc["text"], "source": doc["source"], "name": doc["name"], "score": cosine_sim(q_emb, d_emb)}
        for doc, d_emb in zip(DOCS, doc_embeddings)
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


def similar(text: str) -> list[str]:
    """기준(rag_sim_threshold)을 넘는 비슷한 사례 이름. 1위와 가까운 것만, 최대 NOTE_MAX개. 장애면 빈 목록."""
    try:
        # 업종 문서끼리는 점수 차가 작아 엉뚱한 업종이 섞인다(첼로 → 식당). 업종은 카드가 정하므로 기능 사례만 본다.
        chunks = [c for c in query(text, top_k=len(DOCS))["chunks"] if c["source"].startswith("feature:")]
    except Exception:
        log.exception("임베딩 검색 실패, 사례 없음으로 폴백")
        return []
    if not chunks or chunks[0]["score"] < settings.rag_sim_threshold:
        return []
    top = chunks[0]["score"]
    return [c["name"] for c in chunks if c["score"] >= max(settings.rag_sim_threshold, top - NOTE_MARGIN)][:NOTE_MAX]
