#!/usr/bin/env bash
# OCI 배포 롤백 스크립트 (WP 0-4a, DEPLOYMENT_STRATEGY.md §3-2 안 C 변형).
#
# deploy.sh가 배포 전에 떠둔 원격 스냅샷(~/agt001-releases/<UTC타임스탬프>/)을
# ~/agt001로 되돌린다. generated/·.env(.env.local)는 사용자 데이터·비밀이므로
# 스냅샷에도 들지 않고 롤백 때도 원격 현행본을 그대로 보존한다.
# 복원 후에는 backend를 --build로 띄우고 듀얼 헬스체크를 한다.
#
# 사용법:
#   scripts/rollback.sh --list        스냅샷 목록 출력 (읽기 전용, 원격 변경 없음)
#   scripts/rollback.sh               가장 최근 스냅샷으로 롤백
#   scripts/rollback.sh <타임스탬프>  지정 스냅샷으로 롤백 (예: 20260925-120000)
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

SSH_KEY="${SSH_KEY:-$HOME/.ssh/oci_agt001}"
REMOTE_HOST="${REMOTE_HOST:-ubuntu@144.24.91.250}"
REMOTE_DIR="${REMOTE_DIR:-~/agt001}"
REMOTE_RELEASES_DIR="${REMOTE_RELEASES_DIR:-${REMOTE_DIR}-releases}"
HEALTH_URL="${HEALTH_URL:-https://144.24.91.250.sslip.io}"
HEALTH_URL_DIRECT="${HEALTH_URL_DIRECT:-http://144.24.91.250:8643}"

# 파괴적 명령 가드. 위의 "${VAR:-기본값}"이 빈 값을 기본값으로 바꾸므로 보통은 통과한다.
# 이 가드는 기본값 자체를 지우는 식의 편집 실수를 막기 위한 마지막 안전장치다.
[ -n "${REMOTE_DIR:-}" ] || { echo "REMOTE_DIR이 비어 있습니다" >&2; exit 1; }
[ -n "${REMOTE_RELEASES_DIR:-}" ] || { echo "REMOTE_RELEASES_DIR이 비어 있습니다" >&2; exit 1; }
[ -n "${REMOTE_HOST:-}" ] || { echo "REMOTE_HOST가 비어 있습니다" >&2; exit 1; }

usage() {
  echo "사용법: scripts/rollback.sh [--list] [<타임스탬프>]"
  echo "  --list         스냅샷 목록 출력 (읽기 전용)"
  echo "  (인자 없음)    가장 최근 스냅샷으로 롤백"
  echo "  <타임스탬프>   지정 스냅샷으로 롤백 (예: 20260925-120000)"
}

MODE="rollback"
TARGET=""
if [ "$#" -gt 0 ]; then
  for arg in "$@"; do
    case "$arg" in
      --list) MODE="list" ;;
      -h|--help) usage; exit 0 ;;
      -*)
        echo "알 수 없는 옵션: $arg" >&2
        usage >&2
        exit 1
        ;;
      *)
        if [ -n "$TARGET" ]; then
          echo "인자가 너무 많습니다: $arg" >&2
          usage >&2
          exit 1
        fi
        TARGET="$arg"
        ;;
    esac
  done
fi

if [ "$MODE" = "list" ] && [ -n "$TARGET" ]; then
  echo "--list와 타임스탬프를 함께 쓸 수 없습니다" >&2
  usage >&2
  exit 1
fi

if [ ! -f "$SSH_KEY" ]; then
  echo "SSH 키가 없습니다: $SSH_KEY (SSH_KEY 환경변수로 경로를 지정할 수 있습니다)" >&2
  exit 1
fi

# 원격 스냅샷 목록 (시간순 정렬, 읽기 전용)
# shellcheck disable=SC2029
list_snapshots() {
  ssh -i "$SSH_KEY" "$REMOTE_HOST" "
    set -euo pipefail
    releases_dir=$REMOTE_RELEASES_DIR
    [ -n \"\$releases_dir\" ] || { echo 'REMOTE_RELEASES_DIR이 비어 있습니다' >&2; exit 1; }
    if [ ! -d \"\$releases_dir\" ]; then
      echo '스냅샷 없음 (디렉토리 없음)'
      exit 0
    fi
    ls -1 \"\$releases_dir\" | sort
  "
}

if [ "$MODE" = "list" ]; then
  list_snapshots
  exit 0
fi

# 스냅샷 이름 검증 (경로 탈출 방지: 빈 값·구분자·상위 참조·허용 외 문자 금지)
valid_name() {
  case "$1" in
    ""|*/*|*..*) return 1 ;;
  esac
  case "$1" in
    *[!0-9A-Za-z._-]*) return 1 ;;
  esac
  return 0
}

if [ -z "$TARGET" ]; then
  TARGET="$(list_snapshots | tail -n 1)"
  if [ -z "$TARGET" ] || [ "$TARGET" = "스냅샷 없음 (디렉토리 없음)" ]; then
    echo "롤백할 스냅샷이 없습니다" >&2
    exit 1
  fi
  echo "가장 최근 스냅샷으로 롤백: $TARGET"
fi

if ! valid_name "$TARGET"; then
  echo "잘못된 스냅샷 이름: $TARGET (scripts/rollback.sh --list 로 확인)" >&2
  exit 1
fi

echo "스냅샷 복원: $REMOTE_RELEASES_DIR/$TARGET → $REMOTE_DIR (generated·.env 보존)"
# shellcheck disable=SC2029
ssh -i "$SSH_KEY" "$REMOTE_HOST" "
  set -euo pipefail
  remote_dir=$REMOTE_DIR
  releases_dir=$REMOTE_RELEASES_DIR
  snapshot_name=$TARGET
  [ -n \"\$remote_dir\" ] || { echo 'REMOTE_DIR이 비어 있습니다' >&2; exit 1; }
  [ -n \"\$releases_dir\" ] || { echo 'REMOTE_RELEASES_DIR이 비어 있습니다' >&2; exit 1; }
  [ -n \"\$snapshot_name\" ] || { echo '스냅샷 이름이 비어 있습니다' >&2; exit 1; }
  case \"\$snapshot_name\" in *..*|*/*) echo \"잘못된 스냅샷 이름: \$snapshot_name\" >&2; exit 1 ;; esac
  if [ ! -d \"\$releases_dir/\$snapshot_name\" ]; then
    echo \"스냅샷 없음: \$releases_dir/\$snapshot_name\" >&2
    exit 1
  fi
  if [ ! -d \"\$remote_dir\" ]; then
    echo \"원격 배포 디렉토리 없음: \$remote_dir\" >&2
    exit 1
  fi
  rsync -a --delete --exclude='generated' --exclude='.env' --exclude='.env.local' \"\$releases_dir/\$snapshot_name/\" \"\$remote_dir/\"
  cd \"\$remote_dir\" && sudo docker compose up -d --build backend
"

echo "헬스체크 (https + http 직접, 둘 다 200이어야 성공)"
HEALTH_OK=1
if ! bash "$REPO_ROOT/docs/hackathon/deployment/scripts/warmup.sh" "$HEALTH_URL"; then
  HEALTH_OK=0
fi
if ! bash "$REPO_ROOT/docs/hackathon/deployment/scripts/warmup.sh" "$HEALTH_URL_DIRECT"; then
  HEALTH_OK=0
fi

if [ "$HEALTH_OK" = "1" ]; then
  echo "롤백 완료: $TARGET → $HEALTH_URL, $HEALTH_URL_DIRECT"
else
  echo "롤백 후 헬스체크 실패 — 더 이전 스냅샷으로 재시도: scripts/rollback.sh --list" >&2
  exit 1
fi
