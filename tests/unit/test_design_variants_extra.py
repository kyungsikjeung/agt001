"""목록 밖 추가 항목(extra)의 안내 묶음 표시."""
from app.services import design_variants as DV
from app.services import prd_engine as E
from app.services.site_render import render_site


def _묶음카드(selected, extra, note=""):
    # 화면에서 고른 값과 목록 밖 추가 값을 그대로 둔 카드
    카드 = E.new_card("pension")
    숨김 = {"asked": True, "selected": list(selected)}
    if extra is not None:
        숨김["extra"] = list(extra)
    if note:
        숨김["note"] = note
    카드["hidden"] = 숨김
    return 카드


def _안내묶음(카드):
    명세 = DV.base_spec(카드)
    return next(묶음 for 묶음 in 명세["sections"] if 묶음["type"] == "features")


def test_추가만있어도_묶음이_생긴다():
    # 고른 항목이 없어도 사장님이 더한 항목만으로 이용 안내를 만든다
    묶음 = _안내묶음(_묶음카드([], ["바비큐", "테라스석"]))
    assert [항목["title"] for 항목 in 묶음["content"]["items"]] == ["바비큐", "테라스석"]


def test_고른것이_추가보다_먼저온다():
    # 고른 항목 먼저, 목록 밖 추가 항목은 뒤에 별 모양으로 잇는다
    묶음 = _안내묶음(_묶음카드(["parking", "pet"], ["바비큐", "테라스석"]))
    항목들 = 묶음["content"]["items"]
    assert [항목["title"] for 항목 in 항목들] == ["주차", "반려동물 동반", "바비큐", "테라스석"]
    assert [항목["icon"] for 항목 in 항목들[2:]] == ["star", "star"]


def test_덧붙인말은_내용키로_따로둔다():
    # 덧붙인 말은 첫 항목 설명에 붙이지 않고 내용의 note 키로 둔다
    묶음 = _안내묶음(_묶음카드(["parking"], ["바비큐"], "소형견만 가능해요"))
    assert 묶음["content"]["note"] == "소형견만 가능해요"
    assert all(항목["desc"] == "" for 항목 in 묶음["content"]["items"])
    본문 = render_site(DV.base_spec(_묶음카드(["parking"], ["바비큐"], "소형견만 가능해요")),
                       kind="pension", public=True)
    assert "소형견만 가능해요" in 본문


def test_추가항목은_그대로_붙이지않고_빠져나간다():
    # 사장님 입력이 꺾쇠와 함께 들어와도 결과 문서에는 탈출된 채로 보인다
    카드 = _묶음카드([], ["<script>alert(1)</script>"])
    본문 = render_site(DV.base_spec(카드), kind="pension", public=True)
    assert "<script" not in 본문
    assert "&lt;script" in 본문
