from app import llm
from app.services import rag


def _unit_vectors(monkeypatch, query_vec):
    """문서는 [1,0] 고정, 쿼리는 query_vec로 → 유사도를 완전히 통제한다."""
    rag.reset_cache()
    monkeypatch.setattr(llm, "embed", lambda text: [1.0, 0.0] if text in {d["text"] for d in rag.FAKE_RAG_DOCS} else query_vec)


def test_precheck_existing_when_similar(monkeypatch):
    _unit_vectors(monkeypatch, [1.0, 0.0])  # cosine = 1.0 >= 0.70
    out = rag.precheck("쇼핑몰 리뉴얼")
    assert out.startswith("기존 프로젝트: ")
    assert out.split(": ")[1] in {d["source"] for d in rag.FAKE_RAG_DOCS}


def test_precheck_novel_when_dissimilar(monkeypatch):
    _unit_vectors(monkeypatch, [0.0, 1.0])  # cosine = 0.0 < 0.70
    assert rag.precheck("전혀 무관한 쿼리") == "신규 프로젝트"


def test_precheck_novel_on_embed_error(monkeypatch):
    rag.reset_cache()

    def boom(text):
        raise RuntimeError("embedding down")

    monkeypatch.setattr(llm, "embed", boom)
    assert rag.precheck("anything") == "신규 프로젝트"
