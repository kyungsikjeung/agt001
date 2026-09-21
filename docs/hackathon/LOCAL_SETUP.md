# 로컬 개발 환경 셋업

> 배포(Render/OCI)와 무관하게, 로컬에서 백엔드(Hermes 게이트웨이 + NIM 연동)를 바로 띄우고 개발하기 위한 가이드다.
> 배포 관련 내용은 [deployment/RENDER_DEPLOY.md](deployment/RENDER_DEPLOY.md)를 본다.

## 0. 사전 준비물

| 항목 | 확인 방법 | 비고 |
|---|---|---|
| Docker Desktop | `docker --version` | 없으면 [docker.com](https://www.docker.com/products/docker-desktop/)에서 설치 |
| NVIDIA NIM API 키 | - | [build.nvidia.com](https://build.nvidia.com)에서 발급 |

## 1. 저장소 클론 및 `.env` 생성

```bash
cp .env.example .env
```

`.env`는 `.gitignore`에 이미 등록되어 있어 커밋되지 않는다. 아래 값을 채운다.

| 변수 | 설명 |
|---|---|
| `NIM_API_KEY` | NVIDIA NIM API 키 (필수) |
| `NIM_CHAT_MODEL` | 기본값 `nvidia/nemotron-3-super-120b-a12b` (그대로 사용, `.env.example`·`backend.py` 기본값과 동일) |
| `NIM_EMBED_MODEL` | 기본값 `nvidia/nemotron-3-embed-1b` (RAG 붙일 때 사용) |
| `VECTOR_DB_URL` / `VECTOR_DB_API_KEY` | RAG 벡터DB 연동 시 필요, 아직 없으면 비워둬도 백엔드는 뜬다 |
| `KAKAO_LINK_API_KEY` | 카카오링크 전송 기능 붙일 때 필요 |
| `PORT` | 로컬 기본 `8643` (Render 배포 시엔 자동 주입되므로 무시됨) |

## 2. Docker로 실행

```bash
docker compose up --build
```

`docker-compose.yml`은 `docs/hackathon/deployment/templates/Dockerfile.backend`를 재사용해서 `backend.py`를 `8643:8643` 고정 매핑으로 바인딩한다(`backend.py`는 `PORT` 환경변수 기본값 8643 사용).

## 3. 정상 동작 확인

다른 터미널에서:

```bash
curl -i http://localhost:8643/health
# 기대 응답: HTTP 200, {"status": "ok"}
```

챗 엔드포인트 확인:

```bash
curl -X POST http://localhost:8643/chat \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "안녕"}]}'
```

## 4. 현재 코드 구조

| 파일 | 역할 |
|---|---|
| [`backend.py`](../../backend.py) | Flask 앱. `/health`(헬스체크), `/chat`(NIM OpenAI 호환 API 호출) |
| [`requirements.txt`](../../requirements.txt) | `flask`, `python-dotenv`, `openai`(NIM 호출용 클라이언트), `requests` |
| [`docker-compose.yml`](../../docker-compose.yml) | 로컬/배포 공통 컨테이너 정의 |

`backend.py`는 최소 골격이다. 실제 요구사항(RAG 사전확인, 검증/질의, 견적, Hermes 플래너 연동 등)은 [ARCHITECTURE.md](ARCHITECTURE.md)와 [TEAM_A_SPEC.md](TEAM_A_SPEC.md) / [TEAM_C_SPEC.md](TEAM_C_SPEC.md)를 참고해 위에 계속 확장한다.

## 5. 로컬 개발 중 알아둘 점

- **Hermes/NemoClaw 오케스트레이션 프레임워크**는 아직 이 골격에 붙어 있지 않다. 참조 리포([hackathon-agent-chatbot](https://github.com/kyungsikjeung/hackathon-agent-chatbot))의 RAG+Hermes 연동 패턴을 재사용할 때, 로컬 macOS 기준으로 만들어진 코드이므로 Docker(Linux) 환경에서 그대로 동작하는지 먼저 확인한다.
- 배포는 현재 보류 상태다(OCI는 Pay As You Go 업그레이드 완료·인스턴스 RUNNING이나, 해당 인스턴스에 SSH 접속 후 Docker 설치 + Hermes 동작 검증이 남음 — [ENVIRONMENT.md](ENVIRONMENT.md) §3-4 참고). 배포 없이도 위 방법으로 로컬 개발·테스트는 계속 가능하다.

## 6. Hermes Agent 별도 설치 (실측, 2026-09-22)

> `backend.py`(포트 8643, NIM 직접 호출)는 그대로 유지한다. Hermes 풀스택은
> `requirements.txt`나 `docs/hackathon/deployment/templates/Dockerfile.backend`에는 넣지 않는다.
> 이유: 공식 권장 경로는 `install.sh` + managed venv 방식이라 `requirements.txt` 한 줄 추가만으로는
> gateway/skills/browser 도구가 안 들어온다.
> 따라서 Hermes 플래너는 별도 프로세스(호스트)로 띄우고,
> OpenAI 호환 API로 통신하는 구조로 문서화만 해 둔다.
>
> ※ 이전에 적혀 있던 NemoClaw(`nemoclaw.sh`, `nemohermes`) 내용은 문서에서는 삭제함.
> 실제 공식 경로는 NousResearch/hermes-agent의 `install.sh` + `hermes` CLI다.
> 단, `backend.py` TODO 주석에 `nemohermes` 잔재가 남아 있다 — 코드 수정 범위 밖이라 문서만 정정한다.

### 6-1. 전제 조건

| 항목 | 요구 값 | 확인 방법 |
|---|---|---|
| Python | 3.11 (설치 스크립트가 venv 자동 생성) | `python3.11 --version` |
| Node.js | 브라우저 도구용 (설치 스크립트가 처리) | `node --version` |
| NVIDIA 추론 API 키 | `build.nvidia.com`에서 발급 | 이 리포 `.env`의 `NIM_API_KEY`와 같은 키 값을 Hermes 측에 별도 등록 (변수명은 아래 표 참고) |

### 6-2. 설치 스크립트 (검증됨)

```bash
curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash
source ~/.zshrc   # 또는 source ~/.bashrc — hermes 명령 PATH 적용
```

실측 결과 (macOS, 2026-09-22):

- `hermes --version` → `Hermes Agent v0.21.3 (2026.9.14)`
- `hermes doctor` → 설치 정상. `model.provider 'nvidia'` 설정 후 키 미등록 상태에서는
  `no API key is configured (add it to ~/.hermes/.env or run 'hermes setup')` 경고가 뜨는 게 정상이다.
- 설치 위치:
  - Config: `/Users/kyoungsikjeung/.hermes/config.yaml` (머신마다 `$HOME`만 다름, `hermes config path`로 확인)
  - API Keys: `~/.hermes/.env` (`hermes config env-path`로 확인)
  - Code: `~/.hermes/hermes-agent` (git checkout + managed venv)

### 6-3. NVIDIA NIM 연동 설정 (실측)

Hermes 공식 문서(`https://hermes-agent.nousresearch.com/docs/integrations/providers` §NVIDIA NIM,
§Custom & Self-Hosted) 기준, NIM integrate 엔드포인트를 쓰는 방법은 두 가지다.
이 리포에서는 (A) 1st-party `nvidia` 프로바이더 + `base_url` 오버라이드를 채택했다.
`nvidia` 프로바이더를 쓰면 NIM billing-origin 헤더가 자동 첨부된다.
※ 아래 `model.default`(`nemotron-3-super-120b`)는 Hermes 측 설정명이며,
이 리포 `.env`·`backend.py`의 `NIM_CHAT_MODEL`(`nvidia/nemotron-3-super-120b-a12b`)와 변수·표기가 다르다 — 혼동 주의.

```bash
# (A) 채택 — nvidia 프로바이더 + integrate 엔드포인트 (실제로 적용됨)
hermes config set model.provider nvidia
hermes config set model.default nemotron-3-super-120b
hermes config set model.base_url https://integrate.api.nvidia.com/v1
hermes config get model
# 기대 출력:
#   default: nemotron-3-super-120b
#   provider: nvidia
#   base_url: https://integrate.api.nvidia.com/v1
```

```bash
# (B) 대안 — 범용 custom 프로바이더 (미적용, 참고용)
# hermes model → "Custom endpoint" 선택 후 base URL / 키 / 모델명 입력, 또는
# config.yaml에 model: { provider: custom, base_url: https://integrate.api.nvidia.com/v1, ... }
```

API 키는 절대 리포에 커밋하지 않는다. 사용자가 직접 채워야 할 곳:

| 파일 | 항목 | 값 |
|---|---|---|
| `~/.hermes/.env` | `NVIDIA_API_KEY` | `<YOUR_NIM_API_KEY>` 자리에 실제 NIM 키를 붙여넣기 (이 리포 `.env`의 `NIM_API_KEY`와 같은 키 값, 변수명만 다름) |
| 이 리포 `.env` | `NIM_API_KEY`, `HERMES_GATEWAY_URL=http://127.0.0.1:8642/v1` | `backend.py` NIM 직접 호출용 + 향후 Hermes 전환용 (`.env.example` 참고) |

> Hermes 측 `.env`는 손대지 않았으므로(플레이스홀더 정책), `hermes doctor`의
> `No API key found` 경고는 사용자가 위 `NVIDIA_API_KEY`를 채우면 해소된다.

### 6-4. `hermes` 주요 명령어 (실측)

```bash
hermes --version            # 버전 확인 (실측: v0.21.3)
hermes doctor               # 설치/설정 진단
hermes config path          # config.yaml 경로 출력
hermes config env-path      # .env 경로 출력
hermes config get model     # 현재 모델/프로바이더/base_url 확인
hermes model                # 대화식 프로바이더·모델 선택 (신규 프로바이더 추가는 이걸로)
hermes setup                # 전체 설정 마법사
hermes gateway run          # 메시징 게이트웨이 포그라운드 실행
hermes gateway status       # 게이트웨이 상태 (실측: 미실행 시 "Gateway is not running")
hermes proxy start          # OpenAI 호환 프록시 (기본 127.0.0.1:8645)
hermes serve --status       # 백엔드 서버 상태
hermes dashboard --status   # 대시보드 상태
```

### 6-5. 포트 정리 (실측, 충돌 없음)

| 용도 | 주소/포트 | 설명 |
|---|---|---|
| 이 리포 `backend.py` | `0.0.0.0:8643` (`PORT`, `.env.example` 참고), Flask `/health`·`/chat` | NIM 직접 호출 유지 |
| Hermes 게이트웨이 OpenAI 호환 API (`api_server`) | `http://127.0.0.1:8642/v1` (`DEFAULT_PORT=8642`, 코드 실측) — `API_SERVER_KEY` 필요 | `backend.py`가 나중에 바라볼 주소. `HERMES_GATEWAY_URL` 기본값과 동일 |
| Hermes OpenAI 호환 프록시 (`hermes proxy start`) | `127.0.0.1:8645` (`--help` 실측 기본값) | OAuth 프로바이더(nous/xai)용. NIM 직접 연동에는 불필요 |
| Hermes 백엔드/대시보드 (`hermes serve`, `hermes dashboard`) | `127.0.0.1:9119` (`--help` 실측 기본값) | JSON-RPC/WebSocket + 웹 UI. 구 문서의 `18789`은 오기이므로 정정함 |

> 실측 당시 게이트웨이/serve/proxy 모두 미실행(`lsof`에 리스너 없음)이 정상이다.
> `backend.py` → Hermes 전환 조건: `hermes gateway run` (또는 service install+start) 후
> `curl -sf http://127.0.0.1:8642/v1/models -H "Authorization: Bearer $API_SERVER_KEY"` 통과,
> 그리고 `~/.hermes/.env`의 `NVIDIA_API_KEY` 등록 완료 후. 그 전까지 NIM 직접 호출 유지.
