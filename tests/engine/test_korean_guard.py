"""한국어 가드 (§2.1): foreign_words·KO_RULE 전송·추출 영어값 버리기."""
from app import llm
from app.services import prd_engine


def test_foreign_words_cases():
    assert llm.foreign_words("4 rooms") == ["rooms"]
    assert llm.foreign_words("Cafe Moon", "가게 이름은 Cafe Moon") == []
    assert llm.foreign_words("객실 4개") == []
    url = "https://pf.kakao.com/_abc"
    assert llm.foreign_words(url, url) == []
    assert llm.foreign_words("\u6771\u4eac") == ["\u6771", "\u4eac"]
    assert llm.foreign_words("") == []
    assert llm.foreign_words(None) == []


def test_chat_json_sends_ko_rule_first(monkeypatch):
    # 네트워크 없이 chat_json이 만드는 메시지를 확인한다
    sent = {}

    class _FakeMsg:
        content = "{}"

    class _FakeChoices:
        message = _FakeMsg()

    class _FakeCompletion:
        choices = [_FakeChoices()]

    class _FakeCreate:
        def create(self, **kw):
            sent.update(kw)
            return _FakeCompletion()

    class _FakeClient:
        def with_options(self, **kw):
            return self

        @property
        def chat(self):
            class _C:
                completions = _FakeCreate()
            return _C()

    monkeypatch.setattr(llm, "_client", lambda: _FakeClient())
    monkeypatch.setattr(llm, "_models", lambda: ["test-model"])
    out = llm.chat_json("JSON만 출력한다.", "안녕하세요")
    assert out == "{}"
    system = sent["messages"][0]["content"]
    assert system.startswith(llm.KO_RULE)
    assert "JSON만 출력한다." in system


def test_extract_detail_drops_english_value(monkeypatch):
    monkeypatch.setattr(
        llm, "chat_json",
        lambda system, user, **kw: '{"updates":[{"slot":"offerings","value":"4 rooms"},'
                                   '{"slot":"shop_name","value":"바다정원"}]}',
    )
    ups, ok, _ms, _n = prd_engine.extract_detail("객실은 4개고 이름은 바다정원이에요", None)
    assert ok
    assert [u["slot"] for u in ups] == ["shop_name"]
