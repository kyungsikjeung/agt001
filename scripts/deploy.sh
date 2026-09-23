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
# 사용법: scripts/deploy.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

SSH_KEY="${SSH_KEY:-$HOME/.ssh/oci_agt001}"
REMOTE_HOST="${REMOTE_HOST:-ubuntu@144.24.91.250}"
REMOTE_DIR="${REMOTE_DIR:-~/agt001}"
HEALTH_URL="${HEALTH_URL:-http://144.24.91.250:8643}"
BUILD_MARKER=".deploy_build_marker"

if [ ! -f "$SSH_KEY" ]; then
  echo "SSH 키가 없습니다: $SSH_KEY (SSH_KEY 환경변수로 경로를 지정할 수 있습니다)" >&2
  exit 1
fi

echo "1/3) rsync로 코드 전송 (.env/generated/.git 등 제외)"
rsync -avz --delete \
  --exclude '.git' --exclude '.env' --exclude '.env.local' --exclude 'generated' \
  --exclude '__pycache__' --exclude '.venv' --exclude 'venv' --exclude 'node_modules' \
  --exclude '.DS_Store' --exclude "$BUILD_MARKER" \
  -e "ssh -i $SSH_KEY" \
  ./ "$REMOTE_HOST:$REMOTE_DIR/"

echo "2/3) 이미지 빌드가 필요한지 판단"
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

echo "3/3) 헬스체크"
bash "$REPO_ROOT/docs/hackathon/deployment/scripts/warmup.sh" "$HEALTH_URL"

echo "배포 완료: $HEALTH_URL"
