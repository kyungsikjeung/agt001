"""마이그레이션은 '더하기만'(expand-only) — 되돌린 옛 코드가 새 DB 위에서 그대로 돌게 (REHEARSAL_1015 §0, DB_OPERATIONS §8).

배포를 되돌리면 DB는 그대로 두고 코드만 옛것으로 바뀐다. 그래서 새 마이그레이션은 옛 코드가 모르는 것을
'더하기'만 해야 한다: 새 표, 빈 값 허용 칸(또는 기본값 있는 칸), 색인, 더 넓힌 검사.
지우기·이름 바꾸기·NOT NULL 바꾸기는 두 번에 나눈다(먼저 코드가 안 쓰게 배포 → 다음 배포에서 지우기).
"""
import ast
import logging
from pathlib import Path

import pytest

from app.db import migrate

VERSIONS = Path(__file__).resolve().parents[2] / "alembic" / "versions"
BASELINE = "0019"  # 10/1 운영 DB. 이 뒤로 들어간 것부터 본다
FORBIDDEN = ("drop_table", "drop_column", "rename_table", "drop_index_with_data", "execute")
# 일부러 허용한 것(이유 필수). 0026: 검사를 지우고 '더 넓게' 다시 만든다(옛 값은 모두 여전히 통과)
ALLOWED = {("0026", "drop_constraint")}


def _upgrade_calls(path: Path) -> tuple[str, list[ast.Call]]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    rev = next(n.value.value for n in tree.body if isinstance(n, ast.Assign)
               and getattr(n.targets[0], "id", "") == "revision")
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "upgrade")
    return rev, [n for n in ast.walk(fn) if isinstance(n, ast.Call)]


def _name(call: ast.Call) -> str:
    f = call.func
    return f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")


def _kw(call: ast.Call, key: str):
    for k in call.keywords:
        if k.arg == key and isinstance(k.value, ast.Constant):
            return k.value.value
    return None


NEW = sorted(p for p in VERSIONS.glob("[0-9][0-9][0-9][0-9]_*.py") if p.name[:4] > BASELINE)


@pytest.mark.parametrize("path", NEW, ids=[p.name for p in NEW])
def test_migration_only_adds(path):
    rev, calls = _upgrade_calls(path)
    for call in calls:
        name = _name(call)
        if name in FORBIDDEN or name == "drop_constraint":
            assert (rev, name) in ALLOWED, f"{path.name}: {name}는 옛 코드를 깨뜨릴 수 있어요(두 번에 나눠 배포)"
        if name == "alter_column":
            assert _kw(call, "nullable") is not False and _kw(call, "new_column_name") is None, \
                f"{path.name}: 칸을 NOT NULL로 바꾸거나 이름을 바꾸면 옛 코드가 깨져요"
        if name == "add_column":
            col = next((a for a in call.args if isinstance(a, ast.Call) and _name(a) == "Column"), None)
            if col is not None and _kw(col, "nullable") is False:
                assert any(k.arg == "server_default" for k in col.keywords), \
                    f"{path.name}: 기본값 없는 NOT NULL 칸은 옛 코드의 넣기를 깨뜨려요"


def test_newer_db_than_code_starts_anyway(monkeypatch, caplog):
    """되돌린 옛 코드처럼 DB가 코드보다 앞서 있으면 멈추지 않고 건너뛴다(시끄럽게 알림)."""
    monkeypatch.setattr(migrate, "_current_revisions", lambda url=None: {"9999"})

    def boom(*a, **k):
        raise AssertionError("앞선 DB에 upgrade를 부르면 안 돼요")

    monkeypatch.setattr(migrate.command, "upgrade", boom)
    with caplog.at_level(logging.ERROR, logger="app.db.migrate"):
        migrate.upgrade_head()
    assert any("9999" in r.getMessage() and "앞서" in r.getMessage() for r in caplog.records)


def test_normal_db_still_upgrades(monkeypatch):
    called = []
    monkeypatch.setattr(migrate, "_current_revisions", lambda url=None: {"0019"})
    monkeypatch.setattr(migrate.command, "upgrade", lambda cfg, rev: called.append(rev))
    migrate.upgrade_head()
    assert called == ["head"]
