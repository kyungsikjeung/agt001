"""NIM 한도 감시: 한도에 걸린 채 측정하면 대비 모델이 답해 점수가 오염된다(r6)."""
import logging

from evals import run_simulation as R


def test_watch_counts_fallback_warnings():
    w = R.LimitWatch()
    log = logging.getLogger("app.llm")
    log.addHandler(w)
    try:
        log.warning("NIM 모델 %s 실패(%s) → 다음 모델", "super", "RateLimitError")
        log.warning("NIM 모델 %s 실패(%s) → 다음 모델", "ultra", "APITimeoutError")
        log.warning("다른 경고")
    finally:
        log.removeHandler(w)
    assert (w.fallbacks, w.rate_limits) == (2, 1)


def test_quota_check_fails_when_primary_falls_back(monkeypatch):
    from app import llm
    w = R.LimitWatch()

    def limited(*a, **k):
        w.fallbacks += 1  # 주 모델이 넘어간 것과 같다
        return '{"n": 1}'

    monkeypatch.setattr(llm, "chat_json", limited)
    assert not R.quota_ok(w)
    monkeypatch.setattr(llm, "chat_json", lambda *a, **k: '{"n": 1}')
    assert R.quota_ok(w)
