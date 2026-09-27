#!/usr/bin/env bash
# OCI 배포 스크립트 (EFFICIENCY_PLAN.md §4-① Top 3).
#
# 기본 경로(git): 로컬 HEAD가 origin에 push돼 있는지 확인한 뒤, 서버가 읽기 전용 Deploy Key로
# fetch해서 **그 커밋(SHA)을 정확히** 체크아웃한다. 서버 코드 = 커밋된 코드가 되어 드리프트가 없다.
# (예전 "git pull이 IP 차단으로 막힌다"는 추정은 틀렸다. private 저장소에 대한 서버 인증이 없던 것이
# 원인이었다. docs/product/GIT_PULL_ROOT_CAUSE.md)
# 대체 경로(--rsync): GitHub 장애 등으로 fetch가 안 될 때 로컬 작업 트리를 rsync로 올린다.
#
# 조건부 빌드: Dockerfile.backend / requirements.txt가 바뀌지 않았으면 `--build`
# 없이 컨테이너만 재시작한다 (코드는 .:/app 바인드 마운트라 재기동만으로 반영됨).
# 바뀌었으면 새로 빌드한다. docker/hermes-sandbox/Dockerfile(병렬작업 3 샌드박스 이미지)은
# `docker compose build` 대상이 아니라 별도 `docker build`로 관리되므로 이 스크립트
# 범위 밖이다 — 그 파일을 바꿨으면 원격에서 직접 재빌드해야 한다.
#
# 배포 전 스냅샷 (WP 0-4a, DEPLOYMENT_STRATEGY.md §3-2 안 C 변형):
# rsync 전에 원격 현행본을 ~/agt001-releases/<UTC타임스탬프>/ 에 디렉토리 복사하고
# (generated/·.env 제외 — 사용자 데이터·비밀이므로 스냅샷·롤백 대상이 아님)
# 최근 5개만 보관한다. 헬스체크 실패 시 --auto-rollback이면 rollback.sh로 자동 복구한다.
#
# 사용법: scripts/deploy.sh [--auto-rollback] [--rsync]
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
MODE="git"
if [ "$#" -gt 0 ]; then
  for arg in "$@"; do
    case "$arg" in
      --auto-rollback) AUTO_ROLLBACK=1 ;;
      --rsync) MODE="rsync" ;;
      -h|--help)
        echo "사용법: scripts/deploy.sh [--auto-rollback] [--rsync]"
        echo "  --auto-rollback  헬스체크 실패 시 배포 전 스냅샷으로 자동 롤백 (기본: 안내만 출력)"
        echo "  --rsync          git 대신 로컬 작업 트리를 rsync로 전송 (GitHub 장애 시 대체 경로)"
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

DEPLOY_SHA=""
if [ "$MODE" = "git" ]; then
  # 커밋 안 된 변경이 있으면 "배포한 것 = 커밋된 것"이 깨지므로 거부한다.
  if ! git diff --quiet || ! git diff --cached --quiet; then
    echo "커밋되지 않은 변경이 있습니다. 커밋·push 후 배포하거나 --rsync를 쓰세요." >&2
    exit 1
  fi
  git fetch -q origin
  DEPLOY_SHA="$(git rev-parse HEAD)"
  if ! git merge-base --is-ancestor "$DEPLOY_SHA" origin/main; then
    echo "HEAD($DEPLOY_SHA)가 origin/main에 없습니다. 먼저 push하세요." >&2
    exit 1
  fi
fi

# 프론트엔드(React) 빌드. 결과(frontend/dist)는 git에 없으므로 배포할 커밋 그대로 여기서 빌드해 올린다.
# git 모드는 위에서 작업 트리가 깨끗한지 확인했으므로 빌드 입력 = 배포 커밋이다.
if [ -f frontend/package.json ]; then
  echo "0/4) 프론트엔드 빌드 (npm ci && npm run build)"
  (cd frontend && npm ci --no-audit --no-fund --silent && npm run build --silent) >/dev/null
  [ -f frontend/dist/index.html ] || { echo "프론트엔드 빌드 결과가 없습니다" >&2; exit 1; }
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

if [ "$MODE" = "git" ]; then
  echo "2/4) 서버에서 git fetch → $DEPLOY_SHA 체크아웃 (.env·generated는 추적 제외라 보존)"
  # shellcheck disable=SC2029
  ssh -i "$SSH_KEY" "$REMOTE_HOST" "
    set -euo pipefail
    cd $REMOTE_DIR
    git fetch -q --prune origin
    git reset -q --hard $DEPLOY_SHA
    echo \"   서버 HEAD: \$(git rev-parse --short HEAD)\"
  "
  if [ -d frontend/dist ]; then
    rsync -az --delete -e "ssh -i $SSH_KEY" frontend/dist/ "$REMOTE_HOST:$REMOTE_DIR/frontend/dist/"
    echo "   프론트엔드 빌드 결과 전송 완료"
  fi
else
  echo "2/4) rsync로 코드 전송 (.env/generated/.git 등 제외)"
  rsync -avz --delete \
    --exclude '.git' --exclude '.env' --exclude '.env.local' --exclude 'generated' \
    --exclude '__pycache__' --exclude '.venv' --exclude 'venv' --exclude 'node_modules' \
    --exclude '.DS_Store' --exclude "$BUILD_MARKER" \
    -e "ssh -i $SSH_KEY" \
    ./ "$REMOTE_HOST:$REMOTE_DIR/"
fi

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
  # up -d: compose 설정(환경변수 등)이 바뀐 서비스만 다시 만든다. 코드는 restart로 다시 읽힌다.
  ssh -i "$SSH_KEY" "$REMOTE_HOST" "cd $REMOTE_DIR && sudo docker compose up -d backend caddy && sudo docker compose restart backend"
fi
# Caddyfile은 바인드 마운트라 파일이 바뀌어도 다시 읽어야 반영된다(새 주소면 인증서도 이때 발급).
ssh -i "$SSH_KEY" "$REMOTE_HOST" "cd $REMOTE_DIR && sudo docker compose exec -T caddy caddy reload --config /etc/caddy/Caddyfile" \
  || echo "   (경고) Caddy 설정 다시 읽기 실패 — 기존 설정으로 계속 동작"

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
