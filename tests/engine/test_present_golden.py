"""질문·단추 계약 (present.py): 질문 글(format_question)과 단추(actions_for)를 그대로 고정한다."""
import pytest

from app.services import present
from app.services import prd_engine as E
from app.services import prd_schema as S

TAIL = "\n\n(질문 0/8 · '시안 먼저'라고 하시면 나머지는 알아서 채울게요)"
CONFIRM_TAIL = "\n\n(확인 질문이에요 · '시안 먼저'라고 하시면 나머지는 알아서 채울게요)"


def _send(*labels):
    return [{"label": x, "action": "send"} for x in labels]


LET_AI = {"label": "알아서 해주세요", "action": "skip_to_design"}


def _pension(*filled):
    card = E.new_card("pension")
    for k in filled:
        E._put(card, k, ["x"] if k == "offerings" else "x", S.FILLED)
    return card


def _shop_name():
    return _pension("business_type")


def _goal():
    card = _pension("business_type", "shop_name", "offerings", "price", "contact_method")
    card["hidden"]["asked"] = True
    return card


def _multi():
    return _pension("business_type", "shop_name", "offerings")


def _followup():
    card = _pension("business_type")
    card["followup"] = {"slot": "hours", "text": "몇 시부터 몇 시까지 여나요? 예: 10시~21시"}
    return card


def _owner_confirm():
    card = _pension("business_type")
    E._put(card, "hours", "10시~21시", S.PENDING_OWNER)
    return card


def _site_kind():
    card = E.new_card()
    E._put(card, "business_type", "우주정거장", S.FILLED)
    card["kind_inferred"] = True  # 종류 추론(LLM)은 건너뛰고 바로 묻게
    return card


GOLDEN = [
    (_shop_name, "single",
     "가게 이름이 무엇인가요?\n1) 직접 입력  2) 알아서 해주세요" + TAIL,
     [{"label": "직접 입력", "action": "type", "hint": "여기에 적어 주세요"}, LET_AI]),
    (_goal, "single",
     "사이트로 가장 이루고 싶은 것은 무엇인가요?\n1) 예약 문의 늘리기  2) 펜션 알리기  3) 객실·요금 안내  4) 알아서 해주세요" + TAIL,
     _send("예약 문의 늘리기", "펜션 알리기", "객실·요금 안내") + [LET_AI]),
    (_multi, "multi",
     "해당되는 것을 모두 골라 주세요. 목록에 없는 것도 적어 주시면 넣어 드릴게요.\n주차 · 반려동물 동반 · 바비큐·취사 · 없음" + TAIL,
     _send("주차", "반려동물 동반", "바비큐·취사") + [{"label": "없음", "action": "none"}]),
    (_followup, "followup",
     "몇 시부터 몇 시까지 여나요? 예: 10시~21시\n1) 나중에 넣을게요" + CONFIRM_TAIL,
     [{"label": "나중에 넣을게요", "action": "later"}]),
    (_owner_confirm, "owner_confirm",
     "체크인·아웃 시간을 '10시~21시'로 받았어요. 방장님, 맞나요?\n1) 네  2) 아니요" + CONFIRM_TAIL,
     _send("네", "아니요")),
    (_site_kind, "site_kind",
     "어떤 사이트를 만들고 싶으세요? 하나만 골라 주세요.\n1) 가게·매장  2) 개인·전문가  3) 단체·모임  4) 기능이 있는 웹서비스" + TAIL,
     _send("가게·매장", "개인·전문가", "단체·모임", "기능이 있는 웹서비스")),
]


@pytest.mark.parametrize("make,kind,text,actions", GOLDEN, ids=[g[0].__name__ for g in GOLDEN])
def test_question_text_and_actions(make, kind, text, actions):
    card = make()
    q = E.next_question(card)
    assert q["kind"] == kind
    assert E.format_question(card, q) == text
    assert present.actions_for(q) == actions


def test_actions_for_without_question():
    assert present.actions_for(None) == []


def _card_with_location(status=S.FILLED, geo=None):
    card = _pension("business_type")
    E._put(card, "location", "강릉시 주문진읍 해안로 1", status)
    if geo:
        card["location_geo"] = geo
    return card


ADDR = [present.ADDRESS_ACTION]


def test_reply_actions_address_when_location_changed():
    assert present.reply_actions(_card_with_location(), "", "GATHERING", "GATHERING") == ADDR
    assert present.reply_actions(_card_with_location(S.ASSUMED), "", "GATHERING", "GATHERING") == ADDR


def test_reply_actions_address_when_summary_entered():
    card = _card_with_location()
    loc = present.location_text(card)
    assert present.reply_actions(card, loc, "GATHERING", "AWAIT_APPROVAL") == ADDR
    # 주소도 그대로고 요약 단계도 이미 있었으면 다시 달지 않는다
    assert present.reply_actions(card, loc, "AWAIT_APPROVAL", "AWAIT_APPROVAL") == []
    assert present.reply_actions(card, loc, "GATHERING", "GATHERING") == []


def test_reply_actions_none_without_location_or_with_geo():
    assert present.reply_actions(_pension("business_type"), "", "GATHERING", "AWAIT_APPROVAL") == []
    assert present.reply_actions(_card_with_location(S.PLACEHOLDER), "", "GATHERING", "AWAIT_APPROVAL") == []
    saved = _card_with_location(geo={"road": "강릉시 주문진읍 해안로 1", "x": 128.8, "y": 37.9, "src": "postcode"})
    assert present.reply_actions(saved, "", "GATHERING", "AWAIT_APPROVAL") == []
    assert present.reply_actions(None, "", None, None) == []


def test_open_sheet_actions_always_have_hint():
    """규칙: 시트를 여는 단추는 무엇을 하는지 한 줄(hint)이 꼭 있다."""
    acts = present.reply_actions(_card_with_location(), "", "GATHERING", "AWAIT_APPROVAL")
    for make, *_ in GOLDEN:
        acts += present.actions_for(E.next_question(make()))
    sheets = [a for a in acts if a["action"] == "open_sheet"]
    assert sheets
    for a in sheets:
        assert (a.get("hint") or "").strip()
