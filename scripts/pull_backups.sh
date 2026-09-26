#!/usr/bin/env bash
# 서버 밖 백업 가져오기 (Mac에서 실행, USER_DB_PLAN.md U-6 오프사이트).
#
# 서버의 매일 백업(~/agt001-backups/agt001-<UTC>.dump, backup_db.sh 14개 보관)을
# Mac의 ~/agt001-backups-offsite/로 rsync로 가져온다. 서버 원본은 지우지 않는다.
# 로컬은 최근 30개만 보관한다. 받은 뒤 파일이 멀쩡한지 확인한다.
#
# 사용법: scripts/pull_backups.sh [--dry-run] [--help]
#   --dry-run  실제로 가져오지 않고 rsync 대상만 보여준다
#   --help     이 도움말을 출력한다
#
# 환경변수 (deploy.sh와 같은 방식):
#   SSH_KEY      서버 접속 키 (기본: ~/.ssh/oci_agt001)
#   REMOTE_HOST  서버 주소 (기본: ubuntu@144.24.91.250)
set -euo pipefail

usage() {
  echo "사용법: $(basename "$0") [--dry-run] [--help]"
  echo "  --dry-run  실제로 가져오지 않고 rsync 대상만 보여준다"
  echo "  --help     이 도움말을 출력한다"
  echo ""
  echo "환경변수: SSH_KEY(기본 ~/.ssh/oci_agt001), REMOTE_HOST(기본 ubuntu@144.24.91.250)"
  echo "가져오기: 서버 ~/agt001-backups/ -> Mac ~/agt001-backups-offsite/ (서버 원본 유지, 로컬 30개 보관)"
}

DRY_RUN=0
if [ "$#" -gt 0 ]; then
  for arg in "$@"; do
    case "$arg" in
      --dry-run) DRY_RUN=1 ;;
      -h|--help)
        usage
        exit 0
        ;;
      *)
        echo "알 수 없는 인자: $arg (scripts/pull_backups.sh --help 참고)" >&2
        exit 1
        ;;
    esac
  done
fi

SSH_KEY="${SSH_KEY:-$HOME/.ssh/oci_agt001}"
REMOTE_HOST="${REMOTE_HOST:-ubuntu@144.24.91.250}"
REMOTE_BACKUP_DIR="${REMOTE_BACKUP_DIR:-~/agt001-backups}"
LOCAL_DIR="$HOME/agt001-backups-offsite"
KEEP=30

# 빈 경로 가드 (빈 값으로 rsync·rm이 엉뚱한 곳을 건드리는 편집 실수 방지)
[ -n "${REMOTE_BACKUP_DIR:-}" ] || { echo "REMOTE_BACKUP_DIR이 비어 있습니다" >&2; exit 1; }
[ -n "${LOCAL_DIR:-}" ] || { echo "LOCAL_DIR이 비어 있습니다" >&2; exit 1; }
[ -n "${REMOTE_HOST:-}" ] || { echo "REMOTE_HOST가 비어 있습니다" >&2; exit 1; }

if [ ! -f "$SSH_KEY" ]; then
  echo "SSH 키가 없습니다: $SSH_KEY (SSH_KEY 환경변수로 경로를 지정할 수 있습니다)" >&2
  exit 1
fi

mkdir -p "$LOCAL_DIR"
chmod 700 "$LOCAL_DIR"

# 덤프 파일만 가져오고 서버 원본은 남긴다 (--delete·--remove-source-files 사용 금지)
RSYNC_OPTS=(-a --include='agt001-*.dump' --exclude='*')
if [ "$DRY_RUN" = "1" ]; then
  echo "[미리보기] 서버 원본은 지우지 않는다. 가져올 목록:"
  rsync "${RSYNC_OPTS[@]}" -n --out-format='%n' -e "ssh -i $SSH_KEY" \
    "$REMOTE_HOST:$REMOTE_BACKUP_DIR/" "$LOCAL_DIR/"
  echo "미리보기 끝 (로컬 변경 없음, 최근 $KEEP개 보관 규칙도 적용하지 않음)"
  exit 0
fi

rsync "${RSYNC_OPTS[@]}" -e "ssh -i $SSH_KEY" \
  "$REMOTE_HOST:$REMOTE_BACKUP_DIR/" "$LOCAL_DIR/"

# 가져온 파일 권한을 소유자만 읽기로 맞춘다 (덤프에 사용자 데이터가 들어 있다)
chmod 600 "$LOCAL_DIR"/agt001-*.dump 2>/dev/null || true

# 로컬은 최근 KEEP개만 보관 (타임스탬프 파일명이라 사전식 정렬 = 시간순)
# shellcheck disable=SC2012
ls -1 "$LOCAL_DIR"/agt001-*.dump 2>/dev/null | sort | head -n -"$KEEP" | xargs -r rm -f --

# 받은 파일이 멀쩡한지 확인한다. pg_restore가 있으면 목록 읽기로, 없으면 크기로만 본다.
OK=0
FAIL=0
if command -v pg_restore >/dev/null 2>&1; then
  for f in "$LOCAL_DIR"/agt001-*.dump; do
    [ -e "$f" ] || continue
    if pg_restore --list "$f" >/dev/null 2>&1; then
      OK=$((OK + 1))
    else
      echo "깨진 덤프: $f (pg_restore --list 실패)" >&2
      FAIL=$((FAIL + 1))
    fi
  done
else
  echo "(알림) pg_restore가 없어 크기만 확인한다"
  for f in "$LOCAL_DIR"/agt001-*.dump; do
    [ -e "$f" ] || continue
    if [ -s "$f" ]; then
      OK=$((OK + 1))
    else
      echo "깨진 덤프: $f (빈 파일)" >&2
      FAIL=$((FAIL + 1))
    fi
  done
fi

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
COUNT="$(ls -1 "$LOCAL_DIR"/agt001-*.dump 2>/dev/null | wc -l | tr -d ' ')"
echo "$STAMP 가져오기 정상=$OK 깨짐=$FAIL 로컬보관=$COUNT" >> "$LOCAL_DIR/pull.log"

if [ "$FAIL" -gt 0 ]; then
  echo "가져오기는 끝났으나 깨진 파일 $FAIL개 (상세: $LOCAL_DIR/pull.log)" >&2
  exit 1
fi

echo "가져오기 완료: 정상 $OK개, 로컬 보관 $COUNT개 (최근 $KEEP개, 기록: $LOCAL_DIR/pull.log)"
