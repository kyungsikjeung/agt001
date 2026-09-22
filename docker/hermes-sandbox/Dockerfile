# Hermes 코드생성 샌드박스 이미지.
#
# 목적: backend.py 팀C 코드생성(Hermes)을 호스트와 격리된 Docker 컨테이너 안에서 실행.
# 발견된 문제: 호스트에서 `hermes -z ...` 를 cwd=generated/<id>/web 로 실행해도
# `--in DIR --no-restore-cwd` 옵션을 줘도 Hermes가 작업 디렉토리를 무시하고
# 호스트 홈(~/index.html)에 파일을 쓰는 격리 실패가 재현됨.
# 해결: 요청별 디렉토리만 /workspace 로 bind mount 하고, 컨테이너 WORKDIR를
# /workspace 로 고정 + 매번 --rm 으로 새로 띄웠다 지운다. Hermes가 /workspace
# 안에 쓰면 호스트 generated/<id>/web 에 보이고, 밖에 쓰면 컨테이너와 함께 사라진다.
#
# 빌드 시점에는 API 키가 필요 없다. 실행 시점에 backend.py가 호스트 프로세스의
# os.environ(NIM_API_KEY 또는 NVIDIA_API_KEY)에서 읽어 -e NVIDIA_API_KEY=... 로 주입한다.
# 이미지 안에 비밀값을 절대 넣지 말 것.
FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive \
    HERMES_HOME=/root/.hermes

# install.sh 필요물: curl(다운로드) + git(리포 클론) + ca-certificates(tls) +
# build-essential(node-pty 등 네이티브 모듈 컴파일용) + xz-utils(node tar.xz 해제용).
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        git \
        build-essential \
        xz-utils \
    && rm -rf /var/lib/apt/lists/*

# 공식 Hermes 설치 스크립트 (출처: github.com/NousResearch/hermes-agent, 검증된 URL).
# --skip-setup: 대화식 설정 마법사 생략 (빌드 시 API 키 없음, 실행 시 환경변수로 주입).
# --non-interactive: stdin이 터미널이 아닌 빌드 환경에서 read -p EOF로 중단되는 것 방지.
# --skip-browser: 코드생성 샌드박스에는 Playwright/Chromium 불필요 → 이미지 축소 + 공격표면 감소.
RUN curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash -s -- --skip-setup --non-interactive --skip-browser

# 빌드 시점에 NIM 연동 기본값만 시드 (키 없이도 동작해야 함).
# model.default는 설치 기본값 유지 — backend.py NIM_CHAT_MODEL과 표기가 다를 수 있어
# 프로바이더+base_url만 고정하고 모델 선택은 Hermes 기본에 맡긴다.
RUN hermes config set model.provider nvidia \
    && hermes config set model.base_url https://integrate.api.nvidia.com/v1 \
    && hermes --version

# 격리 핵심: 컨테이너 기본 작업 디렉토리를 /workspace 로 고정.
# backend.py는 generated/<requirement_id>/web 를 /workspace 에 bind mount 한다.
# hermes가 --in 같은 옵션을 무시해도 프로세스 cwd 자체가 /workspace라 산출물이
# 마운트 안으로 떨어진다. 마운트 밖 쓰기는 컨테이너와 함께 --rm으로 폐기된다.
WORKDIR /workspace

CMD ["hermes", "--version"]
