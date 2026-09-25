from app import llm
from app.services import rag


def _unit_vectors(monkeypatch, query_vec, doc_vec=(1.0, 0.0)):
    """문서는 doc_vec 고정, 쿼리는 query_vec로 → 유사도를 완전히 통제한다."""
    rag.reset_cache()
    monkeypatch.setattr(llm, "embed_many", lambda texts: [list(doc_vec) for _ in texts])
    monkeypatch.setattr(llm, "embed", lambda text: query_vec)


def test_docs_are_our_knowledge_not_fake_projects():
    sources = {d["source"].split(":")[0] for d in rag.DOCS}
    assert sources == {"feature", "kind"}
    assert len(rag.DOCS) >= 40


def test_precheck_existing_when_similar(monkeypatch):
    _unit_vectors(monkeypatch, [1.0, 0.0])
    out = rag.precheck("카카오톡으로 문의 받기")
    assert out.startswith("기존 프로젝트: ")
    assert out.split(": ")[1] in {d["source"] for d in rag.DOCS}


def test_precheck_novel_when_dissimilar(monkeypatch):
    _unit_vectors(monkeypatch, [0.0, 1.0])
    assert rag.precheck("전혀 무관한 쿼리") == "신규 프로젝트"
    assert rag.similar("전혀 무관한 쿼리") == []


def test_similar_limits_to_close_top_items(monkeypatch):
    rag.reset_cache()
    vecs = [[1.0, 0.0]] + [[0.0, 1.0]] * (len(rag.DOCS) - 1)  # DOCS[0]은 기능 사례
    monkeypatch.setattr(llm, "embed_many", lambda texts: vecs)
    monkeypatch.setattr(llm, "embed", lambda text: [1.0, 0.0])
    assert rag.similar("q") == [rag.DOCS[0]["name"]]


def test_precheck_novel_on_embed_error(monkeypatch):
    rag.reset_cache()

    def boom(*a):
        raise RuntimeError("embedding down")

    monkeypatch.setattr(llm, "embed", boom)
    monkeypatch.setattr(llm, "embed_many", boom)
    assert rag.precheck("anything") == "신규 프로젝트"
    assert rag.similar("anything") == []
