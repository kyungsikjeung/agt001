"""제어 말 표 (app/data/control_words.json): 표의 모든 말이 classify로 제 id가 되고, 엔진이 쓰는 집합에 들어 있다."""
import pytest

from app.services import control_words as CW
from app.services import prd_engine as E
from app.services import prd_schema as S

# id → 엔진이 그 말을 알아보는 방법
FEEDS = {
    "skip": lambda p: CW.norm(p) in E.SKIP_NORMS,
    "let_ai_skip": lambda p: CW.norm(p) in E.LET_AI_SKIP_NORMS and E._is_let_ai_norm(CW.norm(p)),
    "let_ai_slot": lambda p: E._is_let_ai_norm(CW.norm(p)),
    "dontknow": lambda p: CW.norm(p) in E.DONTKNOW_NORMS and E._is_dontknow_norm(CW.norm(p)),
    "later": lambda p: CW.norm(p) in E.LATER_NORMS and E._is_later_norm(p, CW.norm(p)),
    "none": lambda p: CW.norm(p) in E.NONE_NORMS,
    "repeat": lambda p: CW.norm(p) in E.REPEAT_NORMS,
    "type_it": lambda p: CW.norm(p) == E._norm(S.TYPE_IT),
}
# 앞 순서의 id가 먼저 잡는 말: 문장 속 '알아서'의 표 말은 '알아서' 한 마디라 '알아서'만(let_ai_skip)이 된다
SHADOWED = {("let_ai_slot", "알아서"): "let_ai_skip"}
ROWS = [(i, p) for i, r in CW.table().items() for p in r["phrases"]]


def test_table_has_contract_ids():
    assert set(CW.table()) == set(CW.ORDER) == set(FEEDS)
    for r in CW.table().values():
        assert r["match"] in ("exact", "contains") and r["meaning"] and r["phrases"]


@pytest.mark.parametrize("id,phrase", ROWS)
def test_every_phrase_classifies_and_feeds_engine(id, phrase):
    assert CW.matches(id, phrase)
    assert CW.classify(phrase) == SHADOWED.get((id, phrase), id)
    assert FEEDS[id](phrase)


def test_control_norms_come_from_table():
    for r in CW.table().values():
        for p in r.get("control", ()):
            assert CW.matches(r["id"], p), p
            assert CW.norm(p) in E._CONTROL_NORMS
    assert E._CONTROL_NORMS == CW.control_norms()


def test_engine_constants_are_in_table():
    assert E._norm is CW.norm
    assert CW.classify(S.LET_AI) == "let_ai_skip"
    assert CW.classify(S.TYPE_IT) == "type_it"
    assert CW.classify(E.LATER) == "later"


@pytest.mark.parametrize("text,expected", [
    ("주차는 알아서 하시면 돼요", "let_ai_slot"),
    ("알아서", "let_ai_skip"),
    ("알아서 해주세요!", "let_ai_skip"),
    ("직접 입력", "type_it"),
    ("나머지는 알아서, 시안 먼저 볼게요", "skip"),
    ("잘 모르겠어요", "dontknow"),
    ("모퉁이커피", None),
    ("", None),
])
def test_classify_examples(text, expected):
    assert CW.classify(text) == expected


def test_sentence_let_ai_does_not_skip():
    n = E._norm("주차는 알아서 하시면 돼요")
    assert n not in E.LET_AI_SKIP_NORMS and E._is_let_ai_norm(n)
