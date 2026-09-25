#!/usr/bin/env bash
# OCI 배포 스크립트 (EFFICIENCY_PLAN.md §4-① Top 3).
#
# 배경: OCI 인스턴스에서 `git pull`이 GitHub API 404로 막히는 것을 실측 확인했다
# (Oracle 무료티어 IP 대역이 GitHub 쪽에서 차단/제한된 것으로 추정). 그래서 인스턴스
# 안에서 git을 쓰지 않고, 로컬에서 rsync로 직접 파일을 올리는 경로를 정식 경로로 쓴다.
#
# 조건부 빌드: Dockerfile.backend / requirements.txt가 바뀌지 않았으면 `--build`
# 없이 컨테이너만 재시작한다 (코드는 .:/app 바인드 마운트라 재기동만으로 반영됨).
# 바뀌었으면 새로 빌드한다. docker/hermes-sandbox/Dockerfile(팀C 샌드박스 이미지)은
# `docker compose build` 대상이 아니라 별도 `docker build`로 관리되므로 이 스크립트
# 범위 밖이다 — 그 파일을 바꿨으면 원격에서 직접 재빌드해야 한다.
#
# 배포 전 스냅샷 (WP 0-4a, DEPLOYMENT_STRATEGY.md §3-2 안 C 변형):
# rsync 전에 원격 현행본을 ~/agt001-releases/<UTC타임스탬프>/ 에 디렉토리 복사하고
# (generated/·.env 제외 — 사용자 데이터·비밀이므로 스냅샷·롤백 대상이 아님)
# 최근 5개만 보관한다. 헬스체크 실패 시 --auto-rollback이면 rollback.sh로 자동 복구한다.
#
# 사용법: scripts/deploy.sh [--auto-rollback]
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

SSH_KEY="${SSH_KEY:-$HOME/.ssh/oci_agt001}"
REMOTE_HOST="${REMOTE_HOST:-ubuntu@144.24.91.250}"
REMOTE_DIR="${REMOTE_DIR:-~/agt001}"
REMOTE_RELEASES_DIR="${REMOTE_RELEASES_DIR:-${REMOTE_DIR}-releases}"
HEALTH_URL="${HEALTH_URL:-https://144.24.91.250.sslip.io}"
HEALTH_URL_DIRECT="${HEALTH_URL_DIRECT:-http://144.24.91.250:8643}"
BUILD_MARKER=".deploy_build_marker"
KEEP_SNAPSHOTS=5

AUTO_ROLLBACK=0
if [ "$#" -gt 0 ]; then
  for arg in "$@"; do
    case "$arg" in
      --auto-rollback) AUTO_ROLLBACK=1 ;;
      -h|--help)
        echo "사용법: scripts/deploy.sh [--auto-rollback]"
        echo "  --auto-rollback  헬스체크 실패 시 배포 전 스냅샷으로 자동 롤백 (기본: 안내만 출력)"
        exit 0
        ;;
      *)
        echo "알 수 없는 인자: $arg (scripts/deploy.sh --help 참고)" >&2
        exit 1
        ;;
    esac
  done
fi

# 파괴적 명령 가드. 위의 "${VAR:-기본값}"이 빈 값을 기본값으로 바꾸므로 보통은 통과한다.
# 이 가드는 기본값 자체를 지우는 식의 편집 실수를 막기 위한 마지막 안전장치다.
[ -n "${REMOTE_DIR:-}" ] || { echo "REMOTE_DIR이 비어 있습니다" >&2; exit 1; }
[ -n "${REMOTE_RELEASES_DIR:-}" ] || { echo "REMOTE_RELEASES_DIR이 비어 있습니다" >&2; exit 1; }
[ -n "${REMOTE_HOST:-}" ] || { echo "REMOTE_HOST가 비어 있습니다" >&2; exit 1; }

if [ ! -f "$SSH_KEY" ]; then
  echo "SSH 키가 없습니다: $SSH_KEY (SSH_KEY 환경변수로 경로를 지정할 수 있습니다)" >&2
  exit 1
fi

SNAPSHOT_TS="$(date -u +%Y%m%d-%H%M%S)"

echo "1/4) 배포 전 스냅샷 ($REMOTE_RELEASES_DIR/$SNAPSHOT_TS, generated·.env 제외, 최근 $KEEP_SNAPSHOTS개 보관)"
# shellcheck disable=SC2029
ssh -i "$SSH_KEY" "$REMOTE_HOST" "
  set -euo pipefail
  remote_dir=$REMOTE_DIR
  releases_dir=$REMOTE_RELEASES_DIR
  snapshot_name=$SNAPSHOT_TS
  keep=$KEEP_SNAPSHOTS
  [ -n \"\$releases_dir\" ] || { echo 'REMOTE_RELEASES_DIR이 비어 있습니다' >&2; exit 1; }
  [ -n \"\$remote_dir\" ] || { echo 'REMOTE_DIR이 비어 있습니다' >&2; exit 1; }
  if [ ! -d \"\$remote_dir\" ]; then
    echo '원격 배포 디렉토리가 없어 스냅샷을 건너뜁니다 (첫 배포)'
  else
    mkdir -p \"\$releases_dir/\$snapshot_name\"
    rsync -a --exclude='generated' --exclude='.env' --exclude='.env.local' \"\$remote_dir/\" \"\$releases_dir/\$snapshot_name/\"
    ls -1 \"\$releases_dir\" | sort | head -n -\"\$keep\" | while IFS= read -r old; do
      [ -n \"\$old\" ] || continue
      case \"\$old\" in *..*|*/*) echo \"건너뜀(의심스러운 이름): \$old\" >&2; continue ;; esac
      rm -rf \"\$releases_dir/\$old\"
    done
    echo \"스냅샷 경로: \$releases_dir/\$snapshot_name\"
  fi
"

echo "2/4) rsync로 코드 전송 (.env/generated/.git 등 제외)"
rsync -avz --delete \
  --exclude '.git' --exclude '.env' --exclude '.env.local' --exclude 'generated' \
  --exclude '__pycache__' --exclude '.venv' --exclude 'venv' --exclude 'node_modules' \
  --exclude '.DS_Store' --exclude "$BUILD_MARKER" \
  -e "ssh -i $SSH_KEY" \
  ./ "$REMOTE_HOST:$REMOTE_DIR/"

echo "3/4) 이미지 빌드가 필요한지 판단"
# Dockerfile/requirements.txt의 해시를 원격에 저장해둔 마커와 비교한다.
# 마커가 없거나 다르면 --build, 같으면 재시작만.
LOCAL_HASH="$(cat docs/hackathon/deployment/templates/Dockerfile.backend requirements.txt 2>/dev/null | shasum -a 256 | cut -d' ' -f1)"

# shellcheck disable=SC2029
REMOTE_HASH="$(ssh -i "$SSH_KEY" "$REMOTE_HOST" "cat $REMOTE_DIR/$BUILD_MARKER 2>/dev/null || true")"

if [ "$LOCAL_HASH" != "$REMOTE_HASH" ]; then
  echo "   Dockerfile/requirements.txt 변경 감지 → 이미지 재빌드"
  ssh -i "$SSH_KEY" "$REMOTE_HOST" "cd $REMOTE_DIR && sudo docker compose up -d --build && echo '$LOCAL_HASH' > $BUILD_MARKER"
else
  echo "   변경 없음 → 컨테이너만 재시작 (코드는 바인드 마운트로 이미 반영됨)"
  ssh -i "$SSH_KEY" "$REMOTE_HOST" "cd $REMOTE_DIR && sudo docker compose restart backend"
fi

echo "4/4) 헬스체크 (https + http 직접, 둘 다 200이어야 성공)"
HEALTH_OK=1
if ! bash "$REPO_ROOT/docs/hackathon/deployment/scripts/warmup.sh" "$HEALTH_URL"; then
  HEALTH_OK=0
fi
if ! bash "$REPO_ROOT/docs/hackathon/deployment/scripts/warmup.sh" "$HEALTH_URL_DIRECT"; then
  HEALTH_OK=0
fi

if [ "$HEALTH_OK" = "1" ]; then
  echo "배포 완료: $HEALTH_URL, $HEALTH_URL_DIRECT (스냅샷: $REMOTE_RELEASES_DIR/$SNAPSHOT_TS)"
else
  echo "헬스체크 실패" >&2
  if [ "$AUTO_ROLLBACK" = "1" ]; then
    echo "자동 롤백 시작: scripts/rollback.sh $SNAPSHOT_TS" >&2
    bash "$REPO_ROOT/scripts/rollback.sh" "$SNAPSHOT_TS"
  else
    echo "롤백하려면: scripts/rollback.sh $SNAPSHOT_TS (목록: scripts/rollback.sh --list)" >&2
    exit 1
  fi
fi
