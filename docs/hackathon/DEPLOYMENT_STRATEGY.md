# 배포 전략: 무중단 배포·롤백 조사/설계/비용 분석 (DEPLOYMENT_STRATEGY)

> 작성일: 2026-09-23 / 1차 완성 목표: 2026-09-28 (D-5)
> 성격: 조사·설계·비용분석 문서. **코드는 수정하지 않는다.**
> 조사 범위: `scripts/deploy.sh`, `docker-compose.yml`,
> `docs/hackathon/deployment/templates/Dockerfile.backend`, `docs/hackathon/ENVIRONMENT.md`,
> `docs/hackathon/EFFICIENCY_PLAN.md`, `backend.py`(서버 기동부), `requirements.txt`,
> `docs/hackathon/deployment/scripts/warmup.sh`, git 로그.
> 제약: `.env` 미열람, git add/commit/push 없음. 확실하지 않은 것은 "추정"으로 표기.

## 0. 결론 요약 (3줄)

- **무중단 배포 가능한가:** 단일 OCI 인스턴스에서도 blue-green(리버스 프록시 + 포트 분리 컨테이너 2개)으로 기술적으로 가능하나, 지금 구조(Flask dev server·바인드 마운트·파일 세션)와의 충돌 해소가 필요해서 **마감 전 도입은 비권장(작업량 중)** — 당장은 단일 컨테이너 재시작 최적화로 다운타임을 수 초로 묶는 것이 최소 비용이다.
- **롤백 가능한가:** 가능. 지금은 rsync 덮어쓰기라 롤백 수단이 없지만, SSH 기반으로 **배포 전 원격 스냅샷(tarball 1개) + `rollback.sh` 1개**만 추가하면 **무료·작업량 하**로 롤백이 된다 (권장 최소 구현).
- **비용 드는가:** 아래 모든 방향(리버스 프록시 추가·blue-green 2번째 컨테이너·버전 보관)은 **OCI Always Free 한도(2 OCPU/12GB, 부트볼륨 46~50GB(추정)) 안에서 $0으로 가능(추정)** — 유료가 필요한 것은 인스턴스 추가·관리형 LB 등 "인스턴스 바깥으로 나가는" 선택지뿐이다.

---

## 1. 현재 구조 (실측 기반)

### 1-1. 배포 경로: 왜 SSH+rsync인가

- `scripts/deploy.sh` (58줄): ① `rsync -avz --delete`로 로컬→원격(`ubuntu@144.24.91.250:~/agt001`) 코드 전송
  (`.git`/`.env`/`.env.local`/`generated`/`__pycache__`/`.venv`/`node_modules` 제외)
  → ② `Dockerfile.backend`+`requirements.txt` 해시를 원격 `.deploy_build_marker`와 비교해
  다르면 `docker compose up -d --build`, 같으면 `docker compose restart backend`
  → ③ `warmup.sh <HEALTH_URL>` 헬스체크.
- 배경 (git `29bb20b` 커밋 메시지 + `EFFICIENCY_PLAN.md` §4-③ 실측 기록):
  OCI 인스턴스에서 `git pull`이 GitHub API 404로 막히는 것을 실측 확인.
  원인 가설은 "Oracle 무료티어 egress IP 대역이 GitHub 쪽에서 차단/제한된 것으로 추정".
  **주의: `git` 프로토콜 자체가 막힌 건지 API만 막힌 건지는 미확인(추정)** — 본 문서 작성 시점에 재확인은 하지 않았다.
  어쨌든 현행 정식 경로는 **인스턴스 안에서 git/GitHub API를 쓰지 않고 로컬→인스턴스 rsync**이며,
  아래 모든 설계는 이 전제(SSH 기반, GitHub를 배포 경로에 두지 않음)를 유지한다.
- 관련 수정 이력: `f7e884b` — `Dockerfile.backend`에 `docker-cli` 패키지 추가
  (`docker.io`만으로는 CLI 바이너리가 없어 병렬작업 3 코드생성이 "docker가 없다"며 건너뛰어지던 버그 수정).
  즉 backend 이미지는 **python:3.11-slim + docker.io + docker-cli + pip 의존성 + Playwright Chromium(`--with-deps`)** 구성이다.

### 1-2. 런타임 구조와 다운타임의 정체

| 항목 | 현행 값 |
|---|---|
| 인스턴스 | `VM.Standard.A1.Flex` 2 OCPU / 12GB (Always Free 한도 정확히 일치, ENVIRONMENT.md §3-4) |
| 서비스 | `backend` 단일 컨테이너, `8643:8643` 포트 매핑, 보안리스트에 TCP 8643 오픈 |
| 서버 | `backend.py:832-834` — `app.run(host="0.0.0.0", port=port, threaded=True)` 즉 **Flask 개발 서버 단일 프로세스**(gunicorn/waitress 없음) |
| 코드 반영 | `.:/app` 바인드 마운트라 `.py` 변경은 재기동만으로 반영, `COPY . .`도 공존(dev/prod 미분리 — EFFICIENCY_PLAN §4-⑤) |
| 세션 | 인메모리 dict + `generated/sessions.json`·`rooms.json` 파일 백업 (원자적 tmp+rename, `GENERATING`은 `QUOTED`로 되돌려 복구) |
| 병렬작업 3 격리 | Docker-outside-of-Docker: backend 컨테이너가 호스트 `docker.sock`으로 형제 컨테이너(`hermes-sandbox`)를 띄움. `HOST_PROJECT_DIR=${PWD}` 환경변수로 호스트 실경로 전달 |

다운타임 메커니즘: `restart backend` 또는 `--build` 재배포 시 Flask 단일 프로세스가 죽고 다시 뜨는 사이
**수 초간 리스닝 소켓 자체가 없으므로 그 창에 들어온 요청은 실패**한다.
세션 데이터는 파일 백업으로 복구되지만, **재시작 창의 인플라이트 요청은 구제되지 않는다** — 이것이 무중단 배포가 해결해야 할 전부이자 핵심이다.

---

## 2. 무중단 배포 방향

### 2-1. 후보 나열과 이 규모에서의 판단

| 안 | 개요 | 단일 무료 인스턴스에서 가능한가 | 작업량(추정) |
|---|---|---|---|
| **A. Blue-green (동일 인스턴스, 권장 후보)** | 같은 인스턴스에 backend 2개(blue: 내부 8643, green: 내부 8644)를 띄우고, 앞단의 리버스 프록시(신규 컨테이너 nginx/caddy 또는 호스트 nginx)가 외부 8643을 받아 살아있는 쪽으로 전달. 배포 시: 새 쪽 기동→헬스 통과→프록시 전환→구 쪽 정지 | **가능(추정).** 추가 프로세스는 프록시 1개(수십 MB급) + backend 1개 중복뿐 | 중 |
| **B. Rolling (replica 2 이상)** | `docker compose up --scale backend=2` 식으로 replica를 늘려 하나씩 교체 | **비권장.** 아래 충돌 §2-2 참조. 세션 정합성이 깨진다 | 중~상 (된 뒤에도 버그) |
| **C. 현행 유지 + 재시작 최적화 (진짜 무중단은 아님)** | 단일 컨테이너 그대로, 다운타임 창을 최소화: 조건부 빌드 유지 + 사전 이미지 pull/빌드 후 순간 교체 + 저트래픽 시간 배포 + warmup | 가능. 지금 이미 절반 구현됨(`deploy.sh` 조건부 빌드) | 하 |
| **D. 인스턴스 2대 + LB/2차 무료 allowance** | 가용 인스턴스를 하나 더 파서 외부에서 분산 | 기술적으로 가능하나 Always Free allowance 초과 시 과금·계정별 한도 확인 필요. **마감 5일 과제 아님** | 상 + 비용 리스크 |

**이 규모(단일 무료 인스턴스, 1인 초기 개발, D-5)에서 애초에 무리인가?**
안 A는 무리 아니다(기술적으로 가능, §3에서 무료 판정). 그러나 작업량 "중" + 데모 직전 네트워크 경로 변경(프록시 삽입)이라는 리스크가 있어서 **마감 전에는 무리**에 가깝고 **마감 후 과제로 미루는 것을 권장**한다(§5 권장안).
진짜로 데모를 죽이는 것은 "수 초 다운타임"이 아니라 "수 초 다운타임 중에 요청이 와서 실패하는 것"인데,
시연 특성상 배포 타이밍을 시연 시간 밖으로 빼면(§5) 안 C만으로 사실상 회피 가능하기 때문이다.

### 2-2. 지금 구조와 충돌하는 지점 (안 A/B 공통 점검)

1. **리버스 프록시 신규 도입 필수 (안 A).** 현행은 클라이언트가 `144.24.91.250:8643`으로 backend에 직결.
   blue-green은 앞단에서 전환해줄 주체가 있어야 하므로 nginx/caddy 컨테이너 1개를 새로 추가해야 한다.
   외부 포트(8643, 보안리스트·sslip.io·카카오 도메인 등록이 전부 이 포트에 묶여 있음 — ENVIRONMENT.md §3-5/3-6)는
   프록시가 물고, backend들은 내부 포트(예: 127.0.0.1:8643/8644 또는 도커 네트워크 내부 포트)로 내려간다.
   즉 **카카오 도메인·보안리스트는 그대로(외부 8643 유지) 가능**하나, compose 파일과 포트 매핑을 손대야 한다.
2. **Flask dev server는 graceful 전환의 수혜를 제한한다.**
   `app.run(threaded=True)` 단일 프로세스는 시그널 드레인·소켓 계승이 없다.
   blue-green에서는 어차피 "구 컨테이너를 죽이고 신 컨테이너가 받는다"라 전환 순간 인플라이트 1~2개가 끊길 수 있으나,
   프록시가 헬스 통과 후에만 전환하므로 **실패 창은 재시작 수 초 → 전환 수백 ms급(추정)으로 축소**된다. 완전 제로는 아니다.
3. **바인드 마운트(`.:/app`)와 blue-green은 상성이 나쁘다.**
   현행은 "같은 디렉토리에 rsync 덮어쓰기 + 재시작"이라 코드가 즉시 반영되는 대신,
   blue/green이 같은 디렉토리를 마운트하면 **두 컨테이너가 같은 코드를 보게 되어 버전 분리가 안 된다.**
   안 A를 하려면 §4-A의 릴리스 디렉토리 분리(버전별 디렉토리 + 버전별 compose 기동)가 선행되어야 한다. **세트로 묶어서 봐야 한다.**
4. **파일 세션(`sessions.json`/`rooms.json`) 공유 문제 (안 A/B 공통).**
   현행 락(`SESSIONS_LOCK`)은 단일 프로세스 내에서만 유효하고,
   프로세스 2개가 같은 파일을 쓰면 경합으로 깨진다(AUTH_DB_COST_DECISION.md에도 동일 지적 있음).
   안 B(rolling, 동시 2 replica 서빙)는 이 문제를 정면으로 맞으므로 **비권장**이다.
   안 A는 "동시에 서빙하는 것은 전환 순간뿐, 평시 서빙은 1개"라 타협 가능:
   `generated/`를 릴리스 밖 공유 디렉토리로 두고 **서빙 중인 쪽만 쓴다**는 규칙 + 전환 시점에 신 쪽이 파일을 로드하도록
   재시작 순서를 설계한다. 그래도 전환 찰나의 동시 쓰기는 잔존 리스크(추정) — 마감 후 과제인 이유 중 하나다.
5. **docker.sock DooD + `HOST_PROJECT_DIR` (안 A).**
   병렬작업 3 샌드박스 기동은 호스트 데몬에 `HOST_PROJECT_DIR` 기준 경로를 넘긴다.
   blue-green에서 green의 compose 디렉토리가 blue와 다르면(릴리스 분리 시) `HOST_PROJECT_DIR`도 그에 맞게 달라져야 하고,
   샌드박스가 쓰는 `generated/<id>` 경로의 귀속(공유 vs 버전별)을 정해야 한다. 설계 시 결정 사항으로 남는다(§2-3 설계안에 반영).
6. **Playwright Chromium 무게.** `Dockerfile.backend:20`의 `playwright install --with-deps chromium`은
   OS 의존성까지 포함해 이미지 ~1GB+급(추정, EFFICIENCY_PLAN §2-③). blue-green 전환 시 **새 쪽 최초 기동이 느리다**
   (Chromium 레이어는 공유되므로 pull은 아니고 컨테이너 기동+Flask 기동+NIM 임베딩 프리컴퓨트 시간).
   전환 전 헬스+warmup을 충분히 두는 설계가 필요하다.

### 2-3. SSH 기반 구현 설계 (안 A, 마감 후용 스케치 — 구현 아님)

`scripts/deploy.sh`를 이렇게 바꾼다는 설계만 기술한다(코드 수정 없음):

```
원격 ~/agt001/
├── releases/<YYYYMMDD-HHMMSS>-<git-sha>/   # rsync 목적지가 여기로 변경 (버전별)
├── shared/generated/                        # 릴리스 밖 공유 (세션/산출물)
├── shared/.env                              # 원격 보관, rsync 제외 유지
├── docker-compose.blue-green.yml            # 프록시 + backend-blue + backend-green 정의 (신규)
└── CURRENT -> releases/<현행>               # 심볼릭 링크 (롤백과 공용, §4-A)
```

- 배포(신규 `scripts/deploy-bluegreen.sh` 이미지):
  1. 로컬에서 rsync → 원격 신규 릴리스 디렉토리로 전송 (`.env`/`generated` 제외는 현행 유지, 대신 `shared/`로 마운트).
  2. SSH로 원격에서 비서빙 쪽 색상(예: green)에 새 릴리스를 마운트한 컨테이너 기동
     (`HOST_PROJECT_DIR`은 해당 릴리스 경로로, `generated`는 `shared/generated` 바인드로).
  3. `warmup.sh`를 **새 쪽 내부 포트**에 대해 통과할 때까지 대기 (NIM 프리컴퓨트 포함이므로 여유 있게).
  4. 프록시 upstream을 새 쪽으로 전환 (caddy/nginx reload — 컨테이너 재시작 없이 설정 리로드).
  5. 구 쪽 컨테이너 정지(즉시 삭제하지 않고 1개 전 버전은 대기 = 즉시 롤백 여지).
  6. `CURRENT` 심볼릭 링크를 새 릴리스로 갱신.
- 롤백(전환 후 이상 감지 시): 프록시 upstream을 구 쪽으로 되돌리고 `CURRENT`를 되돌린다(§4와 공용).
- compose 변경 골격(개념만): `backend-blue`/`backend-green` 2 서비스 + `proxy` 1 서비스.
  외부 `8643`은 proxy만 점유, blue/green은 내부 포트. `docker.sock` 마운트와 `HOST_PROJECT_DIR`은 양쪽 모두 필요.

안 C(당장 할 일, §5 권장)의 `deploy.sh` 변경은 훨씬 작다: 현행 유지 + 아래 2줄 수준의 보강만 —
배포 전 스냅샷(§4-C)과 배포 시간대 규칙(시연 시간 밖) + `--build` 시에도 구 컨테이너를 유지한 채 빌드 후 교체하는 순서 정리.
새 스크립트 없이 현행 스크립트에 스냅샷 단계만 끼워 넣으면 된다.

---

## 3. 롤백 방향

### 3-1. 현행의 문제

- rsync `--delete` 덮어쓰기라 **원격에는 "이전 버전"이라는 개념이 없다.** 로컬 git 히스토리는 있지만 원격에 git이 없고,
  `generated/`는 제외되므로 세션 파일은 살아도 **코드는 되돌릴 수단이 없다.**
- `.deploy_build_marker`는 "마지막 빌드 해시"만 들고 있어 이전 해시를 모른다. 이미지 태그도 `latest` 단일(버전별 태그 없음).
- 결과: 배포 후 장애 시 수동으로 "로컬에서 예전 커밋 체크아웃 → rsync → 재시작"을 해야 하며, 그마저도 절차화되어 있지 않다.

### 3-2. SSH 기반 롤백 설계 후보

| 안 | 개요 | 장점 | 단점 | 작업량(추정) |
|---|---|---|---|---|
| **A. 릴리스 디렉토리 + 심볼릭 링크 (capistrano식, 권장 구조)** | `releases/<ts>-<sha>/`에 버전별 보관(N개, 예: 5개), `CURRENT` 심볼릭 링크만 교체 + `compose restart`. `shared/`에 `.env`·`generated` 분리 | 코드 롤백이 링크 교체+재시작이라 수 초. 이미지 문제와 무관하게 코드 레벨 롤백 가능 | 바인드 마운트 전제(`.:/app`)를 릴리스 경로 기준으로 고쳐야 함. 디스크에 릴리스 N개분 코드 보관(수 MB 수준, 미미) | 중 (blue-green과 세트) |
| **B. Docker 이미지 버전 태그** | 배포마다 `docker build -t backend:<ts>-<sha>`로 태그 보관, 롤백은 이전 태그로 `up -d`. `docker images`로 목록 확인 | 빌드 산출물(이미지) 단위라 "돌아가던 이미지"로 정확히 복귀. 릴리스 디렉토리 없이도 됨 | 현행은 코드 변경 시 빌드를 생략(바인드 마운트)하므로 **이미지 태그가 코드 버전을 대표하지 않는다**는 함정. 코드-이미지 대응을 강제하려면 "매 배포 빌드" 또는 "코드 스냅샷 병행"이 필요 → 안 A/C와 결합. 이미지는 개당 ~1-2GB급(추정)이라 N개 보관 시 디스크 압박이 안 A보다 큼 | 중 |
| **C. 배포 전 스냅샷 tarball + `rollback.sh` (최소 구현, D-5 권장)** | `deploy.sh` 시작 시 원격에서 코드 디렉토리를 `~/agt001-snapshots/<ts>-<sha>.tar.gz`로 1개 묶고(직전 N개, 예: 5개만 보관), `rollback.sh <스냅샷>`은 압축 해제→마커 복원→`restart`/`up -d --build`→warmup. 이미지 태그·디렉토리 구조 변경 없음 | **현행 구조 무변경.** 스크립트 2개(배포 스크립트에 5~10줄 추가 + 롤백 스크립트 1개)로 끝. 바인드 마운트·프록시·compose 변경 불필요 | 스냅샷 시점과 장애 발견 시점 사이에 쌓인 `generated/` 신규 산출물은 롤백 대상 아님(현행 rsync 제외 정책과 정합 — 세션은 살리고 코드만 되돌림). 이미지 레벨(Playwright 등) 변경의 롤백은 `--build` 재실행이므로 수 분 소요 가능 | **하** |

### 3-3. 이 프로젝트 규모에서의 "최소 구현" 추천: 안 C

1인 초기 개발·D-5 조건에서 안 A/B는 과하다. 안 C로 충분한 이유:

- 롤백 빈도(추정): 마감까지 배포는 수십 회, 롤백이 필요한 경우는 0~2회. 이를 위해 compose 구조를 뜯는 것은 EFFICIENCY_PLAN 톤("무리한 재설계는 권하지 마라")에 어긋난다.
- 코드가 바인드 마운트라 **tarball 복원 + `restart`면 수 초 내 복구**되는 경우(대부분의 `.py` 수정)가 주류다.
  `Dockerfile`/`requirements.txt`를 건드린 배포의 롤백만 `--build`라 느리다 — 그 경우는 어차피 마감 전 동결 권고(EFFICIENCY_PLAN §2-②③)라 발생 자체가 드물다.
- 스냅샷은 코드만(수 MB 수준 추정, `generated`/`.env` 제외)이라 디스크 부담이 없다.

`rollback.sh` 설계 스케치(구현 아님, SSH 기반·GitHub 불필요):

```
rollback.sh [<스냅샷명>]  # 인자 없으면 최신 이전 1개(=직전 버전) 자동 선택
1. SSH로 원격 스냅샷 목록 조회 (~/agt001-snapshots/*.tar.gz, 시간순)
2. 대상 스냅샷을 ~/agt001/ 에 해제 (같은 rsync 제외 규칙: .env/generated는 건드리지 않음)
3. 스냅샷에 동봉된 빌드 해시와 현재 마커 비교 → 다르면 `up -d --build`, 같으면 `restart backend`
4. warmup.sh 헬스체크 (실패 시 다음 이전 스냅샷 안내 메시지 출력)
```

안 A(릴리스 디렉토리)는 **마감 후**, 안 A의 blue-green(§2-3)과 세트로 도입하는 것을 권장 — 따로 하면 두 번 뜯는다.

---

## 4. 비용 분석 (OCI Always Free 기준)

전제: ENVIRONMENT.md §3 기준 — Compute A1.Flex 2 OCPU/12GB($0), VCN 등 네트워크($0), 월 예산 가드 $5.
부트볼륨은 본 조사에서 실측하지 못했으므로 **기본 46~50GB로 가정(추정)** — 아래 계산은 이 가정 위에서 "자리 여유가 있는가"만 본다.

### 4-1. 메모리: blue-green 2개 동시 기동이 가능한가

- backend 1개의 구성: python:3.11-slim + Flask + docker CLI + Playwright Chromium(`--with-deps`).
  Chromium 런타임 상주분이 수백 MB급(추정, EFFICIENCY_PLAN §2-①은 런치당 ~300-500MB로 추정),
  Flask 상주 + 스크린샷 순간 피크를 합쳐도 **개당 1~2GB 범위(추정)** 로 본다. 정확한 상주 RSS는 원격 실측(`docker stats`) 필요.
- blue-green 전환 찰나에는 backend 2개 + 프록시 1개(수십 MB급)가 동시에 뜬다 → **추가 ~1-2GB(추정)**.
  12GB 총량 대비 여유가 있고, 같은 호스트에 `hermes-sandbox` 요청 컨테이너(메모리 제한 없음, EFFICIENCY_PLAN §2-①)가
  동시에 돌 가능성을 감안해도 총량 초과 가능성은 낮다(추정). 단, 코드생성 동시 실행 상한(§2-① 권고)과 병행해야 안전하다.
- **판정: 메모리 추가 비용 $0. 유료 증설 불필요(추정).**

### 4-2. 디스크: 이미지·버전 보관

- 현행 디스크 사용자(추정): backend 이미지(~1-2GB급: slim + Chromium `--with-deps` + pip 패키지),
  `hermes-sandbox` 2.68GB(사용자 제보 기준, EFFICIENCY_PLAN §2 인용), 컨테이너 로그·`generated/` 누적분.
- 안 A blue-green: backend 이미지는 **blue/green이 같은 이미지(레이어 공유)** 면 추가 디스크 ≈ 0.
  코드만 다른 경우도 이미지 재빌드 없이 바인드/릴리스 분리면 이미지 1개 유지 가능. 프록시 이미지(nginx/caddy)는 수십~100MB급.
- 안 B 이미지 태그 보관: **태그 1개당 ~1-2GB(추정)** 추가. 3개만 쌓아도 수 GB — 46~50GB 볼륨에서 치명적이진 않으나
  안 A/C(코드만 보관, 개당 수 MB) 대비 100배 이상 무겁다. 태그 보관 시 개수 상한(예: 2개) + 구 태그 prune이 필수.
- 안 C 스냅샷 tarball: 코드만 묶으므로 **개당 수 MB(추정)**. 5개 보관해도 수십 MB. 무시 가능.
- **판정: 안 A/C는 디스크 추가 비용 $0(추정). 안 B는 prune 규칙 없이 방치하면 디스크 압박 → 그래도 과금은 아니고 운영 규칙 문제.**

### 4-3. 무료 vs 유료 경계

| 방향 | 비용 |
|---|---|
| 리버스 프록시 컨테이너 추가(nginx/caddy, 동일 인스턴스) | **$0** (동일 shape 내 프로세스 1개 추가, Always Free 범위) |
| blue-green용 2번째 backend 컨테이너(전환 찰나만, 동일 인스턴스) | **$0** (메모리 §4-1, 디스크 §4-2 모두 한도 내 추정) |
| 릴리스 디렉토리 N개 / 스냅샷 tarball N개 보관 | **$0** (코드만, 수십 MB 수준 추정) |
| 이미지 버전 태그 N개 보관 | **$0** (prune 규칙 전제, 디스크 한도 내) |
| 인스턴스 2대째 + 관리형 LB / Object Storage 백업 상시화 / 유료 도메인·인증서 | **유료 가능성** — Always Free allowance(앰퍼 인스턴스 총량 등) 초과 시 과금. 본 문서의 권장 범위 밖 |

**NIM API 과금은 별도**(ENVIRONMENT.md §5 명시 — "NIM은 이 문서 범위 밖"). 배포 전략 변경과 무관하게 호출량에 따르므로
캐시(EFFICIENCY_PLAN §1-②)로 줄이는 쪽이 본 문서의 비용 절감책이다.

---

## 5. 권장안 (D-5 기준)

EFFICIENCY_PLAN.md와 같은 톤으로: 무리한 재설계는 권하지 않는다.

### 5-1. 지금 당장 해볼 만한 것 (작업량 하, D-5 내)

1. **롤백 최소 구현 (안 C): `deploy.sh`에 배포 전 스냅샷 5~10줄 + `rollback.sh` 1개.**
   원격 `~/agt001-snapshots/`에 코드 tarball을 직전 5개만 보관, 롤백은 해제+재시작+warmup.
   예상 효과: 배포 공포 제거(데모 전일 밤 배포도 가능해짐). 리스크: 거의 없음(현행 경로에 단계 1개 추가).
2. **다운타임 회피를 운영으로 해결:** 시연·평가 시간대에는 배포 금지 + 배포는 `restart` 우선(현행 조건부 빌드 유지)
   + 배포 직후 `warmup.sh` 통과 확인을 체크리스트화. 기술적 무중단 없이도 데모 리스크는 제거된다.
3. **실측 1개만 추가:** 원격에서 `docker stats --no-stream` + `docker images` + `df -h` 1회 채취해서
   §4-1/§4-2의 "추정"을 실측으로 교체. 5분 작업으로 blue-green(마감 후)의 근거가 확정된다.

### 5-2. 마감 후 과제 (작업량 중~상)

1. **Blue-green + 릴리스 디렉토리(§2-3 + §4-A)를 세트로.** 따로 하면 compose·마운트·세션 경로를 두 번 뜯는다.
   전제 조건: Flask dev server → gunicorn/waitress 전환 검토(드레인 있는 서버),
   `generated/` 공유 규칙 확정, `HOST_PROJECT_DIR` 버전별 전달, 프록시(caddy 권장 — 설정 리로드가 가벼움) 도입.
2. **Rolling(replica 다중화)은 채택하지 않음.** 파일 세션 구조와 정합하지 않고,
   고치려면 세션 저장소를 파일 밖(ός SQLite/Redis — 유료 또는 상주 프로세스 추가)으로 옮겨야 해서
   이 프로젝트 규모 대비 대가가 크다.
3. **CI/CD 도입도 마감 후**(EFFICIENCY_PLAN §4-④와 동일 판단). OCI→GitHub 404가 해소되지 않는 한
   Actions self-hosted 러너도 같은 네트워크 제약 후보라, 로컬 `deploy.sh` + 스모크가 당분간 정식 경로다.

### 5-3. 하지 말아야 할 것 (마감 전 금지, 본 문서 추가분)

- 외부 포트(8643) 체계 변경(보안리스트·sslip.io·카카오 도메인 2곳 등록이 전부 묶여 있음 — 하나 틀리면 데모 링크 사망).
- compose의 `.:/app` 바인드 구조 변경(롤백·blue-green 모두 이 전제 위에서 설계됨 — 뜯으면 두 설계가 함께 흔들림).
- 이미지 버전 태그 무제한 보관(디스크 압박의 유일한 자초 요인 — 하려면 prune 상한과 세트로).
