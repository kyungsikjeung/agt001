# 개발 파이프라인 — 계획·구현·검증이 멈추지 않고 도는 방식

> 작성일: 2026-09-25 / 상위: [PRODUCT_ROADMAP.md](PRODUCT_ROADMAP.md)
> 원칙: "지금 만드는 것은 곧 완성된다"는 가정으로 **다음 작업의 계획을 미리 끝내 둔다.** 어느 단계도 다른 단계를 기다리며 멈추지 않게 한다.

## 1. 역할

| 역할 | 담당 | 하는 일 |
|---|---|---|
| 계획·핵심 구현·통합 | Claude | 작업 패키지 설계, 핵심 코드(상태머신·DB·인증·보안), 모든 결과물 검토, 커밋·배포 |
| 작업자 (여러 명 병렬) | OpenCode CLI 백그라운드 | 테스트 작성, 검증 실행, 조사, 초안 작성, 스크립트, 문서 갱신 |
| 결정 | 사용자 | 결정 사항(D1~D5 등), 방향 전환 |

## 2. 3개 레인이 동시에 돈다

```
시간 →
계획 레인  [WP n+1 설계]      [WP n+2 설계]      [WP n+3 설계]
구현 레인  [WP n 구현]        [WP n+1 구현]      [WP n+2 구현]
검증 레인  [WP n-1 검증·배포] [WP n 검증·배포]   [WP n+1 검증·배포]
```

- 작업은 **작업 패키지(WP)** 단위로 쪼갠다. 한 WP는 반나절 안에 구현·검증할 수 있는 크기다.
- 구현 레인이 WP n을 하는 동안, 계획 레인은 WP n+1의 설계를 끝내고, 검증 레인은 WP n-1을 검증·배포한다.
- **구현 대기열에는 항상 "준비 완료" WP가 2개 이상 있어야 한다.** 1개 이하로 떨어지면 계획 레인을 우선한다.

## 3. 병목을 막는 규칙

1. **파일 소유권.** 동시에 도는 작업은 서로 다른 파일만 수정한다. 작업 지시문에 "소유 파일"을 반드시 적는다. `app/` 핵심 파일(상태머신, 저장소, 인증)은 한 번에 한 작업만 수정한다.
2. **준비 완료 기준(Definition of Ready).** 설계(무엇을·어느 파일에), 테스트 기준, 소유 파일, 의존 WP가 정해진 것만 구현에 들어간다.
3. **완료 기준(Definition of Done).** 단위 테스트 통과, E2E 통과, 로컬 실측, OCI 배포 후 실측, `STATUS.md` 갱신까지 끝나야 완료다.
4. **검증은 자동이 기본.** 단위 테스트(`tests/unit`), CI(`.github/workflows/ci.yml`), 브라우저 E2E(`tests/e2e`)를 매 WP마다 돌린다. 사람 확인은 자동화할 수 없는 것만 한다.
5. **동시 진행 상한(WIP).** 구현 레인에 핵심 WP는 동시에 1개, 주변 WP(프론트 초안, 스크립트, 문서)는 최대 3개까지.
6. **막히면 바로 다음 WP로.** 외부 요인(콘솔 설정, 사용자 결정)으로 막힌 WP는 대기열 뒤로 보내고 다음 준비 완료 WP를 시작한다. 막힌 이유는 `STATUS.md`에 적는다.
7. **운영 상태 변경 금지.** OpenCode는 `scripts/deploy.sh`, `scripts/rollback.sh`를 `--help`·`--list` 외에 실행하지 않는다. SSH·OCI CLI는 읽기 전용 명령만 허용한다. 배포·롤백은 Claude만 한다. (2026-09-25: 빈 `REMOTE_DIR` 방어 테스트가 기본값으로 대체되어 실제 운영 배포가 실행된 사고가 있었다.)
8. **검토는 diff 단위.** OpenCode 결과물은 Claude가 diff를 읽고 테스트를 돌린 뒤에만 커밋한다.

## 4. 작업 패키지 대기열

상태: ✅ 완료 · 🔄 진행 중 · 🟢 준비 완료 · ⏳ 설계 필요 · ⛔ 막힘

### 0단계 — 기반 정비

| WP | 내용 | 레인/담당 | 소유 파일 | 의존 | 상태 |
|---|---|---|---|---|---|
| 0-1a | Flask → FastAPI 이식, 모듈 분리 | 구현 / Claude | `app/**` | — | ✅ 로컬 실측(실제 NIM·투표·E2E 5/5) |
| 0-1b | 단위·API 테스트 스위트 | 검증 / OpenCode A | `tests/unit/**` | 0-1a | ✅ 47개 통과 |
| 0-1c | CI 워크플로 | 검증 / OpenCode B | `.github/workflows/ci.yml` | 0-1b | ✅ GitHub Actions 통과 |
| 0-1d | 브라우저 E2E | 검증 / OpenCode C | `tests/e2e/**` | 0-1a | ✅ 5/5 통과 |
| 0-1e | OCI 배포·실측 (uvicorn, https 배포 URL) | 검증 / Claude | 배포 | 0-1b | ✅ 운영 E2E 5/5, 실제 코드생성 → https 배포 URL 200 |
| 0-2a | DB 스키마·SQLAlchemy 모델·Alembic | 구현 / Claude | `app/db/**`, `alembic/**` | 0-1e | 🟢 설계 완료 (STAGE0_DESIGN §6) |
| 0-2b | `store.py`를 PostgreSQL 구현으로 교체 | 구현 / Claude | `app/store.py` | 0-2a | ⏳ |
| 0-2c | compose `db` 서비스·볼륨·일일 백업 | 구현 / OpenCode | `docker-compose.yml`, `scripts/backup_db.sh` | 0-2a | ⏳ |
| 0-3a | 코드생성 작업 큐(Redis+RQ) + 워커 | 구현 / Claude | `app/services/codegen.py`, `app/worker.py` | 0-2b | ⏳ |
| 0-3b | 샌드박스 제어: 컨테이너 이름·`docker stop`·메모리/CPU 제한·타임아웃 후 산출물 판정 | 구현 / Claude | `app/services/codegen.py` | 0-3a | ⏳ (실측 버그: 파일 생성 후 90초 초과 시 실패 판정) |
| 0-4a | 배포 전 스냅샷 + `rollback.sh` | 구현 / OpenCode | `scripts/deploy.sh`, `scripts/rollback.sh` | — | ✅ 운영 배포에 적용 |
| 0-4b | 스테이징 compose(별도 포트·DB) | 구현 / OpenCode | `docker-compose.staging.yml` | 0-2c | ⏳ |

### 1단계 — 계정·랜딩 (0단계와 겹쳐서 미리 준비)

| WP | 내용 | 레인/담당 | 소유 파일 | 의존 | 상태 |
|---|---|---|---|---|---|
| 1-0a | 카카오·구글 OAuth 조사: 엔드포인트, 콘솔 설정 절차, 리다이렉트 URI, 필요한 동의항목, 테스트 계정 방식 | 계획 / OpenCode | `docs/product/OAUTH_SETUP.md` | — | ✅ (구글은 sslip.io로 테스트 모드만 가능 → 공개 전 도메인 구매 필요) |
| 1-0b | 랜딩 페이지 정적 초안 (가치 제안, 예시, 시작하기, 로그인 버튼 자리) | 구현 / OpenCode | `static/landing.html` | — | ✅ `/landing.html` (예시 이미지 슬롯은 실제 결과물로 교체 예정) |
| 1-1 | users·oauth_accounts·room_members 스키마 | 구현 / Claude | `app/db/**` | 0-2a | ⏳ |
| 1-2 | OAuth 라우트(state 검증), 세션 쿠키, `/me`, `/logout` | 구현 / Claude | `app/auth/**`, `app/api/auth.py` | 1-1, 1-0a | ⏳ |
| 1-3 | 게스트 방 귀속(claim), 내 프로젝트 목록 | 구현 / Claude | `app/services/rooms.py`, `app/api/me.py` | 1-2 | ⏳ |
| 1-4 | 랜딩·로그인·내 프로젝트 화면 연결 | 구현 / OpenCode → Claude 검토 | `static/landing.html`, `static/projects.html` | 1-2, 1-0b | ⏳ |
| 1-5 | 인증 테스트(단위·E2E) | 검증 / OpenCode | `tests/**` | 1-2 | ⏳ |
| 1-6 | 사용자 작업: 카카오 로그인 활성화, 구글 OAuth 클라이언트 발급 (절차: OAUTH_SETUP.md §5) | 사용자 | 콘솔 | 1-0a | 🟢 사용자 작업 대기 |

2단계(PRD 엔진) 이후 WP는 1단계 구현이 시작될 때 계획 레인에서 이 표에 추가한다.

## 5. 현재 레인 배치 (2026-09-25 갱신)

- 계획 레인: 1-1·1-2 인증 설계(Claude, OAUTH_SETUP.md 기반)
- 구현 레인: 0-2a·0-2b PostgreSQL 전환(Claude)
- 검증 레인: OCI git pull 근본 원인 조사(OpenCode G)
- 사용자 대기: 1-6 카카오·구글 콘솔 작업, D2 도메인 구매 결정
