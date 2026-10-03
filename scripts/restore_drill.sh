#!/usr/bin/env bash
# 복구 연습 (로드맵 P2-6, 백로그 L-4, USER_DB_PLAN §A-3 "복구 연습 절차").
#
# 백업 덤프 하나를 **버리는 임시 DB**에 복원해 보고, 결과를 1쪽 기록(마크다운)으로 낸다.
# 운영 DB·운영 볼륨에는 절대 닿지 않는다: 새 컨테이너(agt001-restore-drill)를 띄워 거기에만
# 복원하고, 끝나면 컨테이너를 지운다(덤프에 사용자 데이터가 있으므로 남기지 않는다).
#
# 확인하는 것:
#   ① 덤프가 읽히는가 (pg_restore --list)
#   ② 오류 없이 복원되는가, 걸린 시간
#   ③ 스키마 버전(alembic_version)이 저장소의 최신 버전과 같은가 (다르면 경고)
#   ④ 핵심 테이블 행 수, 마지막 채팅 시각(덤프가 얼마나 최근 것인지)
#   ⑤ (--migrate) 저장소 코드로 alembic upgrade head가 통과하는가
#
# 사용법:
#   scripts/restore_drill.sh <덤프파일> [-o 기록.md] [--migrate] [--keep]
#     예: scripts/restore_drill.sh ~/agt001-backups-offsite/agt001-20261001T183000Z.dump \
#           -o docs/product/evals/restore-drill-2026-10-02.md
#
# 환경변수:
#   DOCKER       docker 명령 (기본: docker, 서버에서는 "sudo docker")
#   DOCKER=none  docker 없이 이미 떠 있는 빈 PostgreSQL에 복원 (PGHOST·PGPORT·PGUSER로 지정,
#                로컬 pg_restore·psql 필요). 그 서버에 agt001_restore_drill DB를 만들고 끝나면 지운다.
#   PG_IMAGE     임시 컨테이너 이미지 (기본: postgres:16-alpine, 운영과 같은 16)
#
# 기록 파일에는 사용자 데이터를 넣지 않는다(행 수·시각·버전만).
set -euo pipefail

usage() { sed -n '2,27p' "$0" | sed 's/^# \{0,1\}//'; }

DUMP="" OUT="" MIGRATE=0 KEEP=0
while [ $# -gt 0 ]; do
  case "$1" in
    -h|--help) usage; exit 0 ;;
    -o) OUT="${2:?-o 뒤에 기록 파일 경로가 필요합니다}"; shift 2 ;;
    --migrate) MIGRATE=1; shift ;;
    --keep) KEEP=1; shift ;;
    -*) echo "모르는 옵션: $1" >&2; usage >&2; exit 2 ;;
    *) DUMP="$1"; shift ;;
  esac
done
[ -n "$DUMP" ] || { usage >&2; exit 2; }
[ -s "$DUMP" ] || { echo "덤프 파일이 없거나 비어 있습니다: $DUMP" >&2; exit 1; }

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DOCKER="${DOCKER:-docker}"
PG_IMAGE="${PG_IMAGE:-postgres:16-alpine}"
NAME="agt001-restore-drill"
DB="agt001_restore_drill"
PASS="drill-$(date +%s)-$RANDOM"
TABLES="users rooms sessions room_messages chat_turns inquiries bookings shops funnel_events"
started=$(date +%s)
fail=""

# ── 임시 DB 준비 ──
if [ "$DOCKER" = "none" ]; then
  : "${PGHOST:?DOCKER=none이면 PGHOST가 필요합니다}"
  export PGUSER="${PGUSER:-postgres}"
  psql_() { psql -X -q -v ON_ERROR_STOP=1 -d "$DB" "$@"; }
  restore_() { pg_restore --no-owner --no-acl -d "$DB" "$DUMP"; }
  list_() { pg_restore --list "$DUMP"; }
  psql -X -q -d postgres -c "DROP DATABASE IF EXISTS $DB" -c "CREATE DATABASE $DB"
  cleanup() { [ "$KEEP" = 1 ] || psql -X -q -d postgres -c "DROP DATABASE IF EXISTS $DB" >/dev/null 2>&1 || true; }
  DB_URL="postgresql+psycopg://${PGUSER}${PGPASSWORD:+:$PGPASSWORD}@${PGHOST}:${PGPORT:-5432}/$DB"
else
  if $DOCKER ps -a --format '{{.Names}}' | grep -qx "$NAME"; then
    echo "이전 연습 컨테이너($NAME)가 남아 있습니다. 지운 뒤 다시 실행하세요: $DOCKER rm -f $NAME" >&2
    exit 1
  fi
  PORT=55499
  # 127.0.0.1에만 연다(--migrate용). 운영 compose 네트워크·볼륨과 이어지지 않는다.
  $DOCKER run -d --name "$NAME" -e POSTGRES_USER=agt001 -e POSTGRES_PASSWORD="$PASS" -e POSTGRES_DB="$DB" \
    -p "127.0.0.1:$PORT:5432" "$PG_IMAGE" >/dev/null
  cleanup() { [ "$KEEP" = 1 ] || $DOCKER rm -f "$NAME" >/dev/null 2>&1 || true; }
  for _ in $(seq 1 60); do
    $DOCKER exec "$NAME" pg_isready -U agt001 -d "$DB" >/dev/null 2>&1 && break
    sleep 1
  done
  $DOCKER cp "$DUMP" "$NAME:/tmp/drill.dump"
  psql_() { $DOCKER exec -i "$NAME" psql -X -q -v ON_ERROR_STOP=1 -U agt001 -d "$DB" "$@"; }
  restore_() { $DOCKER exec "$NAME" pg_restore --no-owner --no-acl -U agt001 -d "$DB" /tmp/drill.dump; }
  list_() { $DOCKER exec "$NAME" pg_restore --list /tmp/drill.dump; }
  DB_URL="postgresql+psycopg://agt001:$PASS@127.0.0.1:$PORT/$DB"
fi
trap cleanup EXIT

q() { psql_ -At -c "$1" 2>/dev/null || echo "?"; }

# ① 목록
entries=$(list_ 2>/dev/null | grep -vc '^;' || true)
[ "${entries:-0}" -gt 0 ] || fail="${fail}덤프 목록을 읽지 못함. "

# ② 복원
t0=$(date +%s)
if restore_ > /tmp/agt001-restore-drill.err 2>&1; then
  restore_ok="통과"
else
  restore_ok="오류 $(grep -c 'error' /tmp/agt001-restore-drill.err || true)건"
  fail="${fail}pg_restore 오류. "
fi
restore_sec=$(( $(date +%s) - t0 ))

# ③ 스키마 버전
db_rev=$(q "SELECT version_num FROM alembic_version")
repo_rev=$(grep -h '^revision = ' "$ROOT"/alembic/versions/*.py | sed 's/revision = "\(.*\)"/\1/' | sort | tail -1)
rev_note="같음"
[ "$db_rev" = "$repo_rev" ] || rev_note="다름(덤프가 저장소보다 예전이면 기동 때 자동 마이그레이션으로 올라감 → --migrate로 확인)"

# ④ 행 수, 마지막 채팅 시각
rows=""
total=0
for t in $TABLES; do
  n=$(q "SELECT count(*) FROM $t")
  rows="${rows}| \`$t\` | $n |
"
  case "$n" in ''|*[!0-9]*) ;; *) total=$((total + n)) ;; esac
done
[ "$total" -gt 0 ] || fail="${fail}핵심 테이블이 모두 비어 있음. "
last_msg=$(q "SELECT max(ts) FROM room_messages")
db_size=$(q "SELECT pg_size_pretty(pg_database_size(current_database()))")

# ⑤ 마이그레이션
mig="건너뜀(--migrate 없음)"
if [ "$MIGRATE" = 1 ]; then
  if (cd "$ROOT" && python3 - "$DB_URL" <<'PY'
import sys
from alembic import command
from alembic.config import Config
cfg = Config("alembic.ini")
cfg.set_main_option("sqlalchemy.url", sys.argv[1])
command.upgrade(cfg, "head")
PY
  ) > /tmp/agt001-restore-drill-mig.log 2>&1; then
    mig="통과 (지금 버전 $(q "SELECT version_num FROM alembic_version"))"
  else
    mig="실패 (/tmp/agt001-restore-drill-mig.log)"
    fail="${fail}마이그레이션 실패. "
  fi
fi

total_sec=$(( $(date +%s) - started ))
result="합격"
[ -z "$fail" ] || result="불합격: $fail"

report=$(cat <<EOF
# 복구 연습 기록 $(date +%Y-%m-%d)

> \`scripts/restore_drill.sh\`로 만든 기록. 사용자 데이터는 넣지 않는다(행 수·시각·버전만).

| 항목 | 값 |
|---|---|
| 결과 | **$result** |
| 덤프 | \`$(basename "$DUMP")\` ($(du -h "$DUMP" | cut -f1)) |
| 덤프 항목 수 | $entries |
| 복원 | $restore_ok, ${restore_sec}초 |
| 복원된 DB 크기 | $db_size |
| 스키마 버전 | 덤프 \`$db_rev\` / 저장소 \`$repo_rev\` → $rev_note |
| 마이그레이션 | $mig |
| 마지막 채팅 시각 | $last_msg |
| 전체 소요 | ${total_sec}초 |

| 테이블 | 행 수 |
|---|---|
$rows
## 사람이 적을 것

- 덤프를 어디서 가져왔나(서버 / Mac 오프사이트):
- 실패점과 고칠 것:
EOF
)

if [ -n "$OUT" ]; then
  mkdir -p "$(dirname "$OUT")"
  printf '%s\n' "$report" > "$OUT"
  echo "기록: $OUT"
fi
printf '%s\n' "$report"
[ -z "$fail" ]
