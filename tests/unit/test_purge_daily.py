"""보관 기간 정리가 서버가 떠 있는 동안 하루에 한 번 다시 돈다 (개인정보처리방침 3항)."""
import asyncio

from app import main

WANT = 2  # 두 번 돌면 "다시 돈다"가 확인된다
TIMEOUT_SEC = 5.0  # 느린 기계에서도 넉넉히 (CI에서 고정 0.08초로 재다가 흔들렸다)


def _run_until(calls: list) -> None:
    """정리 반복을 띄우고 WANT번 돌 때까지(또는 시간이 다 될 때까지) 기다린다.

    고정된 시간만큼 자고 횟수를 세면 러너가 느릴 때 흔들린다(_purge_all은 thread로 돈다).
    그래서 시간이 아니라 **조건**을 기다린다.
    """
    async def run():
        task = asyncio.create_task(main._purge_daily())
        loops = int(TIMEOUT_SEC / 0.01)
        for _ in range(loops):
            if len(calls) >= WANT:
                break
            await asyncio.sleep(0.01)
        task.cancel()

    asyncio.run(run())


def test_purge_repeats_while_server_up(monkeypatch):
    calls = []
    monkeypatch.setattr(main, "_purge_all", lambda: calls.append(1))
    monkeypatch.setattr(main, "PURGE_EVERY_SEC", 0.01)

    _run_until(calls)
    assert len(calls) >= WANT


def test_purge_failure_does_not_stop_the_loop(monkeypatch):
    calls = []

    def boom():
        calls.append(1)
        raise RuntimeError("db down")

    monkeypatch.setattr(main, "_purge_all", boom)
    monkeypatch.setattr(main, "PURGE_EVERY_SEC", 0.01)

    _run_until(calls)
    assert len(calls) >= WANT  # 한 번 터져도 다음 날 다시 돈다
