"""보관 기간 정리가 서버가 떠 있는 동안 하루에 한 번 다시 돈다 (개인정보처리방침 3항)."""
import asyncio

from app import main


def test_purge_repeats_while_server_up(monkeypatch):
    calls = []
    monkeypatch.setattr(main, "_purge_all", lambda: calls.append(1))
    monkeypatch.setattr(main, "PURGE_EVERY_SEC", 0.01)

    async def run():
        task = asyncio.create_task(main._purge_daily())
        await asyncio.sleep(0.08)
        task.cancel()

    asyncio.run(run())
    assert len(calls) >= 2


def test_purge_failure_does_not_stop_the_loop(monkeypatch):
    calls = []

    def boom():
        calls.append(1)
        raise RuntimeError("db down")

    monkeypatch.setattr(main, "_purge_all", boom)
    monkeypatch.setattr(main, "PURGE_EVERY_SEC", 0.01)

    async def run():
        task = asyncio.create_task(main._purge_daily())
        await asyncio.sleep(0.08)
        task.cancel()

    asyncio.run(run())
    assert len(calls) >= 2
