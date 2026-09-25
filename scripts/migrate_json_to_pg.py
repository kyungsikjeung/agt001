"""0-1 시절 JSON 저장소(generated/sessions.json, rooms.json)를 PostgreSQL로 옮긴다 (STAGE0_DESIGN.md §6.5).

- 멱등: 이미 있는 행은 건너뛴다(ON CONFLICT DO NOTHING). 두 번 돌려도 중복이 생기지 않는다.
- 스키마에 없는 세션 키는 버리고 개수만 보고한다. 원본 파일은 건드리지 않는다.
- 옮긴 뒤 원본 보관(generated/legacy/)은 --archive를 줄 때만 한다.

사용법 (서버, backend 컨테이너 안):
  python scripts/migrate_json_to_pg.py --dry-run     키·건수 통계만 출력, DB 쓰기 없음
  python scripts/migrate_json_to_pg.py               이전 실행
  python scripts/migrate_json_to_pg.py --archive     이전 후 JSON을 generated/legacy/로 이동
"""
import argparse
import collections
import datetime
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import literal_column  # noqa: E402
from sqlalchemy.dialects.postgresql import insert as pg_insert  # noqa: E402

from app.config import settings  # noqa: E402
from app.db import migrate as db_migrate  # noqa: E402
from app.db.models import RoomMemberRow, RoomMessageRow, RoomRow, RoomVoteRow, SessionRow  # noqa: E402
from app.db.session import get_sessionmaker  # noqa: E402
from app.store import _SESSION_FIELDS  # noqa: E402


def _ts(value) -> datetime.datetime:
    if value:
        try:
            parsed = datetime.datetime.fromisoformat(value)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=datetime.timezone.utc)
        except (TypeError, ValueError):
            pass
    return datetime.datetime.now(datetime.timezone.utc)


def _load(path: Path) -> dict:
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit(f"{path.name}: 최상위가 객체가 아닙니다")
    return data


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--archive", action="store_true")
    args = parser.parse_args()

    sessions_path = settings.generated_dir / "sessions.json"
    rooms_path = settings.generated_dir / "rooms.json"
    sessions = _load(sessions_path)
    rooms = _load(rooms_path)

    dropped = collections.Counter(k for s in sessions.values() for k in s if k not in _SESSION_FIELDS)
    n_messages = sum(len(r.get("messages") or []) for r in rooms.values())
    print(f"세션 {len(sessions)}개, 방 {len(rooms)}개, 메시지 {n_messages}개")
    print(f"상태별 세션: {dict(collections.Counter(s.get('state') for s in sessions.values()))}")
    if dropped:
        print(f"스키마에 없어 버릴 세션 키: {dict(dropped)}")
    if args.dry_run:
        return 0

    db_migrate.upgrade_head()
    inserted = collections.Counter()
    skipped = collections.Counter()
    with get_sessionmaker()() as db, db.begin():
        def record(stmt, key):
            # ON CONFLICT DO NOTHING의 rowcount는 드라이버에 따라 -1이 나온다. RETURNING 행 유무로 판정한다.
            added = db.execute(stmt.returning(literal_column("1"))).first() is not None
            (inserted if added else skipped)[key] += 1

        def put(model, key, values, conflict_cols):
            record(pg_insert(model).values(**values).on_conflict_do_nothing(index_elements=conflict_cols), key)

        for session_id, s in sessions.items():
            if not s.get("requirement_id") or not s.get("state"):
                skipped["session_invalid"] += 1
                continue
            state = s["state"]
            codegen = s.get("codegen")
            if state == "GENERATING":  # 재시작 복구 규칙과 같다 (store.recover_on_startup)
                state, codegen = "QUOTED", None
            values = {k: s.get(k) for k in _SESSION_FIELDS}
            values.update(id=session_id, state=state, codegen=codegen,
                          design_url_unsent=bool(s.get("design_url_unsent")))
            # requirement_id 충돌(다른 id가 같은 값)도 건너뛴다 — 산출물 디렉터리가 겹치면 안 된다.
            record(pg_insert(SessionRow).values(**values).on_conflict_do_nothing(), "session")

        for room_id, r in rooms.items():
            if r.get("session_id") not in sessions:
                skipped["room_without_session"] += 1
                continue
            put(RoomRow, "room", {"id": room_id, "session_id": r["session_id"], "ai_status": "IDLE",
                                  "created_at": _ts(r.get("created_at"))}, ["id"])
            for pos, m in enumerate(r.get("members") or []):
                put(RoomMemberRow, "member", {
                    "room_id": room_id, "member_id": m["member_id"], "nickname": m.get("nickname") or "익명",
                    "joined_at": _ts(m.get("joined_at")), "last_seen": _ts(m.get("last_seen")), "position": pos,
                }, ["room_id", "member_id"])
            for idx, msg in enumerate(r.get("messages") or []):
                put(RoomMessageRow, "message", {
                    "room_id": room_id, "seq": msg.get("seq", idx), "member_id": msg.get("member_id") or "system",
                    "nickname": msg.get("nickname") or "", "text": msg.get("text") or "",
                    "kind": msg.get("kind") or "chat", "ts": _ts(msg.get("ts")),
                }, ["room_id", "seq"])
            for member_id, vote in (r.get("votes") or {}).items():
                put(RoomVoteRow, "vote", {"room_id": room_id, "member_id": member_id, "vote": vote},
                    ["room_id", "member_id"])

    print(f"추가: {dict(inserted)}")
    print(f"건너뜀(이미 있음/무효): {dict(skipped)}")

    if args.archive:
        legacy = settings.generated_dir / "legacy"
        legacy.mkdir(exist_ok=True)
        for path in (sessions_path, rooms_path):
            if path.is_file():
                path.replace(legacy / path.name)
                print(f"보관: {path.name} → legacy/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
