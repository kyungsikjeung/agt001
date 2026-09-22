# Environment 관리 문서

> 이 프로젝트와 관련해 로컬/클라우드에 세팅된 모든 환경을 정리한다. 각 환경의 "무엇을, 왜, 어떻게" 확인하는지와 비용/보안 관련 주의사항을 한 곳에 모은다.

## 1. 개요

| 환경 | 용도 | 상태 |
|---|---|---|
| [로컬 개발 환경](#2-로컬-개발-환경) | 백엔드 + Hermes + NIM 개발/테스트 | 동작 중 |
| [OCI 클라우드 환경](#3-oci-클라우드-환경) | 상시 배포용 (Ampere A1 ARM64 검증 포함) | 인스턴스 RUNNING |
| [OpenCode CLI](#4-opencode-cli-보조-도구) | 코드 작업 위임용 보조 에이전트 | 설치됨 |

배포 전략: 지금은 **로컬 개발 → 나중에 배포** 순서로 진행 중 (Render 또는 이 문서의 OCI 인스턴스). 자세한 배경은 [LOCAL_SETUP.md](LOCAL_SETUP.md), [ARCHITECTURE.md](ARCHITECTURE.md) 참고.

---

## 2. 로컬 개발 환경

### 2-1. 프로젝트 백엔드

| 항목 | 값 |
|---|---|
| 코드 | [`backend.py`](../../backend.py) — Flask, `/health` + `/chat`(NIM 직접 호출) |
| 의존성 | [`requirements.txt`](../../requirements.txt) — flask, python-dotenv, openai, requests |
| 환경변수 | `.env` (from `.env.example`, `.gitignore`에 등록됨 — 커밋 안 됨) |
| 실행 | `docker compose up --build` → `curl http://localhost:8643/health` |

상세 셋업 절차는 [LOCAL_SETUP.md](LOCAL_SETUP.md) 참고.

### 2-2. Hermes Agent + NIM 연동

> ⚠️ **여기서 설치한 Hermes는 로컬 맥(macOS, Apple Silicon = ARM64) 기준이다.** 맥 자체가 ARM64라서 여기서 잘 동작하는 것과, 클라우드의 **Linux ARM64(OCI Ampere A1)** 에서 동작하는 것은 별개다 — OS가 다르면(Darwin vs Linux) 같은 CPU 아키텍처(ARM64)라도 바이너리 호환이 보장되지 않는다. Linux ARM64 검증은 [3-4. Compute 인스턴스](#3-4-compute-인스턴스)에서 별도로 진행해야 하며, 아직 미착수 상태다.

| 항목 | 값 |
|---|---|
| 설치 환경 | 로컬 macOS (Apple Silicon, ARM64) — `uname -m` = `arm64` |
| 설치 도구 | 공식 설치 스크립트 (`hermes-agent.nousresearch.com/install.sh`), 출처 검증 완료([github.com/NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent)) |
| 버전 | Hermes Agent v0.21.3 |
| 설치 위치 | `~/.hermes/hermes-agent` |
| 설정 파일 | `~/.hermes/config.yaml` |
| 비밀키 파일 | `~/.hermes/.env` — `NVIDIA_API_KEY` 채움 완료, `hermes -z` 실제 요청으로 `OK` 응답 확인됨 |
| Provider 설정 | `provider: nvidia`, `base_url: https://integrate.api.nvidia.com/v1`, `default: nvidia/nemotron-3-super-120b-a12b` (Hermes 측 설정명 — 리포 `.env`·`backend.py`의 `NIM_CHAT_MODEL`과 동일 ID로 통일함, [LOCAL_SETUP.md](LOCAL_SETUP.md) §6-3 참고) |
| Hermes API 포트 | `127.0.0.1:8642` (OpenAI 호환, API URL은 `http://127.0.0.1:8642/v1`) — 상세 포트 표는 [LOCAL_SETUP.md](LOCAL_SETUP.md) §6-5 참고 |
| Hermes 대시보드 포트 | `127.0.0.1:9119` |

리포의 `HERMES_GATEWAY_URL`(`.env.example`)은 `backend.py`가 나중에 Hermes 게이트웨이로 전환할 때 쓸 주소(`http://127.0.0.1:8642/v1`)를 미리 정의해 둔 것 — 아직 실제 전환은 안 함 (TODO 주석만 존재).

**남은 작업**: `~/.hermes/.env`에 실제 `NVIDIA_API_KEY` 채우기 → `hermes doctor`로 경고 해소 확인.

### 2-3. OCI CLI (클라우드 제어용)

| 항목 | 값 |
|---|---|
| 설치 | `brew install oci-cli` |
| 설정 파일 | `~/.oci/config` |
| API 키 | `~/.oci/oci_api_key.pem` (개인키, 600 권한) / `oci_api_key_public.pem` (OCI 콘솔에 등록됨) |
| 인증 확인 | `oci iam region list` |

이 키로 브라우저 없이 OCI 리소스(shape 재고 확인, 인스턴스 생성 등)를 CLI로 직접 조작할 수 있다.

---

## 3. OCI 클라우드 환경

### 3-1. 계정

| 항목 | 값 |
|---|---|
| Tenancy | `datamining7830` |
| 계정 유형 | Pay As You Go (Free Tier에서 업그레이드) — **Always Free 리소스는 업그레이드 후에도 계속 무료** |
| 리전 | South Korea North (Chuncheon), `ap-chuncheon-1` |
| 결제 이메일 | datamining7830@gmail.com |

### 3-2. 비용 안전장치

| 장치 | 설정값 | 비고 |
|---|---|---|
| Budget | `monthly-cost-guard`, 월 $5, 전체 계정(root) 대상 | 이미 생성됨 |
| Budget Alert Rule | Actual Spend 80%($4) 도달 시 이메일 | 발송 대상: datamining7830@gmail.com |
| Cost Anomaly Detection | **미설정** — 계정이 신규라 비용 데이터 부족으로 모니터 파라미터 선택 불가 | 며칠 뒤 사용 데이터 쌓이면 재시도 |

⚠️ Budget 사용량 반영은 최대 ~24시간 지연될 수 있음 — 실시간 차단이 아니라 사후 알림.

### 3-3. 네트워크 (VCN)

| 리소스 | 이름/값 |
|---|---|
| VCN | `agt001-vcn` (10.0.0.0/16) |
| Subnet | `agt001-public-subnet` (10.0.0.0/24), 퍼블릭 IP 허용 |
| Internet Gateway | `agt001-igw` |
| Route Table | 기본 라우트 테이블에 `0.0.0.0/0 → IGW` 규칙 추가 |
| Security List | 기본 보안리스트에 **SSH(22) + ICMP** 인그레스만 허용 |

### 3-4. Compute 인스턴스

| 항목 | 값 |
|---|---|
| 이름 | `agt001-hermes-backend` |
| Shape | `VM.Standard.A1.Flex` — **2 OCPU / 12GB, Always Free 한도 정확히 일치 → $0** |
| 이미지 | Canonical Ubuntu 20.04 (aarch64) |
| 아키텍처 | **Linux** ARM64 (Ampere Neoverse-N1) — 로컬 맥(macOS ARM64)과는 OS가 다른 별개의 검증 대상 |
| Public IP | `144.24.91.250` |
| SSH 키 | `~/.ssh/oci_agt001` (개인키) / `oci_agt001.pub` |
| SSH 접속 | `ssh -i ~/.ssh/oci_agt001 ubuntu@144.24.91.250` |
| 상태 | RUNNING |
| Docker | ✅ 설치 완료 (`get.docker.com` 스크립트, v28.1.1), `hello-world` 컨테이너 실행 확인 |
| Hermes Agent | ✅ 설치 완료 (v0.21.4, `hermes-agent.nousresearch.com/install.sh`) |
| NIM 연동 검증 | ✅ `hermes -z "..."` → `OK` 응답 확인 (Linux ARM64에서 실측) |

**검증 결론**: 로컬(macOS ARM64/Darwin)과 이 OCI 인스턴스(Linux ARM64) **양쪽 모두에서 Hermes Agent + NVIDIA NIM 연동이 정상 동작**함을 확인했다. 두 환경은 CPU 아키텍처(ARM64)는 같지만 OS(Darwin vs Linux)가 달라 별개로 검증이 필요했던 것 — 완료.

### 3-5. 챗봇 앱 배포 (실서비스)

| 항목 | 값 |
|---|---|
| 실행 방식 | 이 리포를 `git clone` 후 `docker compose up -d --build` (인스턴스 안 `~/agt001`) |
| 서비스 주소 | `http://144.24.91.250:8643` — `/health`, `/chat`, 웹 채팅 위젯(`/`) 전부 외부에서 접속 확인 |
| 보안리스트 | SSH(22)+ICMP에 더해 **TCP 8643(챗봇 API/웹) 인바운드 오픈** |
| 겪은 문제 | `openai==1.51.0`이 최신 `httpx`(0.28+)와 호환 안 됨(`Client.__init__() got an unexpected keyword argument 'proxies'`) → `requirements.txt`에 `httpx==0.27.2` 고정해서 해결 |
| 남은 일 | 카카오링크(팀B)는 보통 IP가 아니라 **도메인**을 요구함 — 이 IP에 도메인을 붙이는 작업이 팀B 진짜 구현의 전제조건 |

---

## 4. OpenCode CLI (보조 도구)

| 항목 | 값 |
|---|---|
| 설치 | `npm i -g opencode-ai` (v1.18.31) |
| 무료 모델 | `opencode/muse-spark-1.3-contributor-free` — 로그인 불필요 |
| 기본 사용법 | `opencode run -m opencode/muse-spark-1.3-contributor-free "지시문"` |
| 파일 수정 필요 시 | `--auto` 옵션 추가 (권한 자동 승인, 주의해서 사용) |

⚠️ 무료 모델은 제3자 게이트웨이를 거치므로, `.env`/API 키 등 비밀 파일은 항상 프롬프트에서 **읽기 금지**로 명시하고 플레이스홀더만 쓰게 했음.

---

## 5. 전체 비용 요약

| 리소스 | 비용 |
|---|---|
| OCI Compute (A1.Flex 2 OCPU/12GB) | $0 (Always Free) |
| OCI VCN/Subnet/IGW/보안리스트 | $0 (항상 무료) |
| Hermes Agent, OpenCode CLI, OCI CLI | $0 (로컬 설치, 소프트웨어 자체는 무료) |
| NIM API 사용량 | 별도 — NVIDIA NIM 요금제에 따름 (이 문서 범위 밖) |
| **현재 월 예상 비용** | **$0** (Budget 알림 $5 기준으로 안전장치 유지) |
