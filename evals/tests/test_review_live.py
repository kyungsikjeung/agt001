"""실대화 평가 도구 시험. DB·NIM 없이 가짜 대화 + 가짜 채점자로만 검사한다."""

import datetime

import pytest

from evals import live_metrics as M
from evals.review_live import build_report, group_rows, judge_session, transcript

NOW = datetime.datetime(2026, 9, 26, 12, 0, tzinfo=datetime.timezone.utc)


def turn(user, ai="네.", before="GATHERING", after="GATHERING", meta=None, ts=NOW,
         session_id="s1"):
    return {"session_id": session_id, "user_text": user, "ai_text": ai,
            "state_before": before, "state_after": after, "meta": meta, "ts": ts}


def trace(**kw):
    base = {"answered_by_rule": False, "extract_ok": True, "extract_ms": 100,
            "extracted": ["shop_name"], "applied": ["shop_name"],
            "skip": False, "asked_slot": "phone", "next_slot": "phone"}
    base.update(kw)
    return base


def fake_judge(transcript_text):
    assert "010-1234-5678" not in transcript_text  # 채점자에게는 가린 기록만 간다
    return {"q_ok": 4, "heard": 5, "missed": ["주차 안내가 카드에 없음"], "weird": [],
            "burden": 2, "fix": "전화번호를 한 번에 묻기", "reason": "대체로 잘 알아들음"}


# ── 가림 ─────────────────────────────────────────────────────────────────

def test_mask_phone_patterns():
    assert M.mask_pii("전화는 010-1234-5678이에요") == "전화는 [전화]이에요"
    assert M.mask_pii("010 1234 5678") == "[전화]"
    assert M.mask_pii("01012345678") == "[전화]"
    assert M.mask_pii("02-123-4567로 주세요") == "[전화]로 주세요"
    assert M.mask_pii("가격 15000원, 2026년 9월") == "가격 15000원, 2026년 9월"


def test_mask_email_and_address():
    assert M.mask_pii("메일 hong@test.com 으로") == "메일 [이메일] 으로"
    masked = M.mask_pii("서울시 강남구 테헤란로 123에 있어요")
    assert "테헤란로 123" not in masked and "[주소]" in masked
    assert M.mask_pii("카페를 하고 싶어요") == "카페를 하고 싶어요"
    assert M.mask_pii(masked) == masked  # 멱등


def test_mask_korean_digit_phone():
    assert M.mask_pii("번호는 공일공 일이삼사 오육칠팔 입니다") == "번호는 [전화] 입니다"


# ── 세션 지표 ────────────────────────────────────────────────────────────

def test_summary_reached_and_questions():
    turns = [turn("바다정원 펜션이에요", meta=trace(next_slot="shop_name", asked_slot=None)),
             turn("강릉에 있어요", meta=trace(next_slot="phone")),
             turn("010-1234-5678", before="GATHERING", after="AWAIT_APPROVAL",
                  meta=trace(next_slot=None, extracted=["phone"], applied=["phone"]))]
    m = M.session_metrics("s1", turns, NOW)
    assert m["reached_summary"] and m["turns_to_summary"] == 3
    assert m["num_questions"] == 2 and m["churned"] is False


def test_churn_old_vs_recent():
    old = [turn("펜션 하고 싶어요", ts=NOW - datetime.timedelta(minutes=40),
                meta=trace(next_slot="shop_name", extracted=[], applied=[]))]
    assert M.session_metrics("s1", old, NOW)["churned"] is True
    recent = [turn("펜션 하고 싶어요", ts=NOW - datetime.timedelta(minutes=10),
                   meta=trace(next_slot="shop_name", extracted=[], applied=[]))]
    assert M.session_metrics("s1", recent, NOW)["churned"] is False
    no_ts = [turn("펜션 하고 싶어요", ts=None, meta=trace(next_slot="shop_name"))]
    assert M.session_metrics("s1", no_ts, NOW)["churned"] is None


def test_skip_rule_extract_stats():
    turns = [turn("시안 먼저 보여주세요", meta=trace(skip=True, extracted=[], applied=[],
                                                        next_slot=None, asked_slot=None,
                                                        extract_ok=None, extract_ms=None)),
             turn("네", meta={"answered_by_rule": True, "extract_ok": None, "extract_ms": None,
                              "extracted": [], "applied": [], "skip": False, "next_slot": "phone"}),
             turn("강릉시 어쩌구", meta=trace(extract_ok=False, extract_ms=100,
                                              extracted=[], applied=[], next_slot="phone")),
             turn("전화요", meta=trace(extract_ok=True, extract_ms=300, next_slot="hours")),
             turn("10시부터요", meta=trace(extract_ok=True, extract_ms=200, next_slot="hours")),
             turn("21시까지요", meta=trace(extract_ok=True, extract_ms=400, next_slot=None))]
    m = M.session_metrics("s1", turns, NOW)
    assert m["used_skip"] is True
    assert m["rule_ratio"] == pytest.approx(1 / 6)  # 규칙 판단 흔적이 있는 6턴 중 1턴이 버튼 답
    assert m["extract_fail_rate"] == pytest.approx(0.25)
    assert m["extract_p50_ms"] == pytest.approx(250.0)
    assert m["extract_p95_ms"] == pytest.approx(385.0)


def test_repeat_stuck_confusion():
    turns = [turn("펜션이에요", meta=trace(next_slot="phone", extracted=[], applied=[])),
             turn("글쎄요", meta=trace(next_slot="phone", extracted=[], applied=[])),
             turn("무슨 말이에요?", meta=trace(next_slot="phone", extracted=[], applied=[]))]
    m = M.session_metrics("s1", turns, NOW)
    assert m["repeat_count"] == 1 and m["repeat_slots"] == ["phone"]
    assert m["empty_twice"] == 2
    assert m["confusion_hits"] == [3] and m["confusion_slots"] == ["phone"]


def test_missed_candidates():
    long_missed = "바비큐장과 불멍존도 꼭 넣어주세요"
    turns = [turn(long_missed, meta=trace(extracted=[], applied=[])),
             turn("네", meta=trace(extracted=[], applied=[])),  # 15자 미만 제외
             turn("주차장도 넓게 써주세요", meta={"answered_by_rule": True, "extracted": [],
                                                 "applied": ["phone"], "skip": False}),  # 규칙 처리 제외
             turn("넓은 단체석도 꼭 부탁드려요", meta=trace(skip=True, extracted=[],
                                                          applied=[]))]  # 건너뛰기 제외
    m = M.session_metrics("s1", turns, NOW)
    assert m["missed"] == [long_missed]


def test_group_rows():
    rows = [turn("a", session_id="s2"), turn("b", session_id="s1"), turn("c", session_id="s2")]
    g = group_rows(rows)
    assert set(g) == {"s1", "s2"}
    assert [t["user_text"] for t in g["s2"]] == ["a", "c"]


# ── 보고서 ───────────────────────────────────────────────────────────────

def test_build_report_with_fake_judge():
    reached = [turn("바다정원 펜션이에요", meta=trace(next_slot="shop_name", asked_slot=None)),
               turn("010-1234-5678으로 연락주세요", before="GATHERING", after="AWAIT_APPROVAL",
                    meta=trace(next_slot=None, extracted=["phone"], applied=["phone"]))]
    churned = [turn("카페 하고 싶은데요 바비큐장도 꼭 넣어주세요",
                    ts=NOW - datetime.timedelta(hours=2),
                    meta=trace(next_slot="phone", extracted=[], applied=[]))]
    sessions = group_rows(
        [dict(t, session_id="ok") for t in reached] + [dict(t, session_id="bad") for t in churned])
    md, summary = build_report(sessions, judge_fn=fake_judge, now=NOW, date_str="2026-09-26")
    assert summary["aggregate"]["n_sessions"] == 2
    assert summary["aggregate"]["summary_rate"] == pytest.approx(0.5)
    assert summary["judge"]["avg_q_ok"] == pytest.approx(4.0)
    assert summary["judge"]["improvements"][0]["fix"] == "전화번호를 한 번에 묻기"
    assert any("주차 안내" in m for m in summary["judge"]["missed"])
    assert len(summary["examples"]) == 2
    assert "010-1234-5678" not in md and "[전화]" in md
    assert "## 전체 요약" in md and "## 대화 예시 3개" in md


def test_build_report_without_judge_and_judge_error():
    sessions = group_rows([turn("펜션 하고 싶어요", meta=trace(next_slot="phone"))])
    md, summary = build_report(sessions, now=NOW)
    assert summary["judge"] is None and "--judge" in md

    def boom(t):
        raise RuntimeError("망가짐")

    md2, summary2 = build_report(sessions, judge_fn=boom, now=NOW)
    assert summary2["judge"]["n_errors"] == 1 and summary2["judge"]["n_judged"] == 0
    assert "망가짐" not in md2  # 에러 내역은 보고서에 노출하지 않는다


def test_judge_session_normalizes_bad_shape():
    j = judge_session("…", lambda t: {"q_ok": 99, "heard": "x", "missed": "문자열",
                                      "weird": None, "burden": 3, "fix": "", "reason": ""})
    assert j["q_ok"] == 5 and j["heard"] is None and j["missed"] == [] and j["burden"] == 3
    assert "error" in judge_session("…", lambda t: "{깨진 json")
    t = transcript([turn("010-1234-5678")])
    assert "010-1234-5678" not in t
