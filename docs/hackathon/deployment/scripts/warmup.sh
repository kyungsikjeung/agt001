#!/usr/bin/env bash
# Render 무료 플랜 콜드스타트 대응: 발표/심사 10~15분 전 실행
# 사용법: ./warmup.sh https://<서비스명>.onrender.com
# 참고: docs/deployment/RENDER_DEPLOY.md §3-6
set -euo pipefail

URL="${1:?사용법: warmup.sh <base-url>}/health"
echo "워밍업 시작: $URL"

for i in $(seq 1 5); do
  code=$(curl -s -o /dev/null -w "%{http_code}" "$URL" || echo "000")
  echo "시도 $i: HTTP $code"
  if [ "$code" = "200" ]; then
    echo "워밍업 완료"
    exit 0
  fi
  sleep 5
done

echo "경고: 워밍업 실패, 수동 확인 필요" >&2
exit 1
