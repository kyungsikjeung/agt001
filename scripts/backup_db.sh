#!/usr/bin/env bash
# PostgreSQL 일일 백업 스크립트 (WP 0-2c).
#
# 서버에서 cron으로 돌린다. 예시 (매일 03:30 KST = 18:30 UTC):
#   30 18 * * * ~/agt001/scripts/backup_db.sh >> ~/agt001-backups/backup.log 2>&1
#
# 동작: `db` 컨테이너에서 pg_dump(custom 형식)를 떠서
# ~/agt001-backups/agt001-<UTC타임스탬프>.dump 로 저장하고 최근 14개만 보관한다.
#
# 복원 방법 (custom 형식이므로 pg_restore 사용):
#   # 1. 덤프를 서버로 복사한 뒤 컨테이너 안으로 넣는다
#   sudo docker compose -f ~/agt001/docker-compose.yml cp ./agt001-<타임스탬프>.dump db:/tmp/restore.dump
#   # 2. 기존 객체를 지우고 복원한다 (--clean --if-exists: 있으면 지우고 없으면 넘어감)
#   sudo docker compose -f ~/agt001/docker-compose.yml exec -T db \
#     pg_restore -U agt001 -d agt001 --clean --if-exists /tmp/restore.dump
#
# 사용법: scripts/backup_db.sh [COMPOSE_DIR] [--help]
#   COMPOSE_DIR  docker-compose.yml이 있는 디렉토리 (기본: ~/agt001)
set -euo pipefail

usage() {
  echo "사용법: $(basename "$0") [COMPOSE_DIR]"
  echo "  COMPOSE_DIR  docker-compose.yml이 있는 디렉토리 (기본: ~/agt001)"
  echo "  --help       이 도움말을 출력한다"
  echo ""
  echo "서버 cron 예시 (매일 03:30 KST = 18:30 UTC):"
  echo "  30 18 * * * ~/agt001/scripts/backup_db.sh >> ~/agt001-backups/backup.log 2>&1"
}

if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
  usage
  exit 0
fi

COMPOSE_DIR="${1:-$HOME/agt001}"
BACKUP_DIR="$HOME/agt001-backups"
KEEP=14

# 빈 경로 가드 (빈 값으로 rm·덤프가 엉뚱한 곳을 건드리는 편집 실수 방지)
[ -n "${COMPOSE_DIR:-}" ] || { echo "COMPOSE_DIR이 비어 있습니다" >&2; exit 1; }
[ -n "${BACKUP_DIR:-}" ] || { echo "BACKUP_DIR이 비어 있습니다" >&2; exit 1; }
[ -f "$COMPOSE_DIR/docker-compose.yml" ] || { echo "compose 파일을 찾을 수 없습니다: $COMPOSE_DIR/docker-compose.yml" >&2; exit 1; }

mkdir -p "$BACKUP_DIR"

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_FILE="$BACKUP_DIR/agt001-$STAMP.dump"

# 서버의 docker는 sudo가 필요하다 (deploy.sh와 같음). cron에서 암호 입력이 없도록 -n.
DOCKER="${DOCKER:-sudo -n docker}"

# 덤프가 중간에 실패하면 불완전한 파일을 남기지 않는다.
trap 'rm -f "$BACKUP_FILE"' ERR
$DOCKER compose -f "$COMPOSE_DIR/docker-compose.yml" exec -T db \
  pg_dump -U agt001 -d agt001 --format=custom > "$BACKUP_FILE"
trap - ERR

# 0바이트 덤프는 실패로 처리하고 삭제한다 (디스크 가득 참·중단된 덤프가 보관되는 것을 방지)
if [ ! -s "$BACKUP_FILE" ]; then
  echo "백업 실패: 덤프 파일이 비어 있습니다: $BACKUP_FILE" >&2
  rm -f "$BACKUP_FILE"
  exit 1
fi

# 최근 KEEP개만 보관 (타임스탬프 파일명이라 사전식 정렬 = 시간순)
# shellcheck disable=SC2012
ls -1 "$BACKUP_DIR"/agt001-*.dump 2>/dev/null | sort | head -n -"$KEEP" | xargs -r rm -f --

echo "백업 완료: $BACKUP_FILE"
