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
| 0-2a | DB 스키마·SQLAlchemy 모델·Alembic | 구현 / Claude | `app/db/**`, `alembic/**` | 0-1e | ✅ upgrade·downgrade·`alembic check` 통과 |
| 0-2b | `store.py`를 PostgreSQL 구현으로 교체 + JSON 이전 스크립트 | 구현 / Claude | `app/store.py`, `scripts/migrate_json_to_pg.py` | 0-2a | ✅ 운영 반영, 데이터 이전(세션 28·방 27·메시지 156) 일치, 일일 백업 cron |
| 0-2c | compose `db` 서비스·볼륨·일일 백업·CI PostgreSQL | 구현 / OpenCode H | `docker-compose.yml`, `scripts/backup_db.sh`, `ci.yml` | 0-2a | ✅ (서버 cron 등록은 배포 때) |
| 0-3a | 코드생성 작업 큐(Redis+RQ) + 워커 | 구현 / Claude | `app/services/codegen.py`, `app/worker.py` | 0-2b | ⏳ |
| 0-3b | 샌드박스 제어: 컨테이너 이름·`docker stop`·메모리/CPU 제한·타임아웃 후 산출물 판정 | 구현 / Claude | `app/services/codegen.py` | 0-3a | ⏳ (실측 버그: 파일 생성 후 90초 초과 시 실패 판정) |
| 0-4a | 배포 전 스냅샷 + `rollback.sh` | 구현 / OpenCode | `scripts/deploy.sh`, `scripts/rollback.sh` | — | ✅ 운영 배포에 적용 |
| 0-4b | 스테이징 compose(별도 포트·DB) | 구현 / OpenCode | `docker-compose.staging.yml` | 0-2c | ⏳ |
| 0-4c | 서버 GitHub 인증(읽기 전용 Deploy Key) + `deploy.sh` git 방식 전환 | 구현 / Claude | `scripts/deploy.sh` | — | ✅ 운영 적용, git 방식 배포 실측 |
| 0-5a | OCI 비용 모니터링 리포트 | 검증 / OpenCode I | `scripts/oci_cost_report.sh` | — | ✅ 30일 0원, 무료 한도 대비 OCPU 50%·스토리지 23.5% |
| 0-5b | 비용 일일 자동 점검 + 알림 | 구현 / Claude | cron·알림 | 0-5a | ⏳ |

### 1단계 — 계정·랜딩 (0단계와 겹쳐서 미리 준비)

| WP | 내용 | 레인/담당 | 소유 파일 | 의존 | 상태 |
|---|---|---|---|---|---|
| 1-0a | 카카오·구글 OAuth 조사: 엔드포인트, 콘솔 설정 절차, 리다이렉트 URI, 필요한 동의항목, 테스트 계정 방식 | 계획 / OpenCode | `docs/product/OAUTH_SETUP.md` | — | ✅ (구글은 sslip.io로 테스트 모드만 가능 → 공개 전 도메인 구매 필요) |
| 1-0b | 랜딩 페이지 정적 초안 (가치 제안, 예시, 시작하기, 로그인 버튼 자리) | 구현 / OpenCode | `static/landing.html` | — | ✅ `/landing.html` (예시 이미지 슬롯은 실제 결과물로 교체 예정) |
| 1-0c | 랜딩 기획(유입 구성요소·업종별 템플릿 6개·퍼널) — [DECISIONS.md](DECISIONS.md) D12~D16 반영 | 계획 / OpenCode K → Claude 검토 | `docs/product/LANDING_PLAN.md` | — | 🔄 |
| 1-0d | 유입 측정: `funnel_events` 테이블·수집 API·90일 정리 (D16) | 구현 / Claude | `app/db/**`, `app/api/events.py` | 0-2a | 🟢 |
| 1-0e | 프론트엔드 React+TS+Vite 골격, FastAPI 서빙, CI 빌드 (D5) | 구현 / Claude + OpenCode | `frontend/**`, Dockerfile, `ci.yml` | — | 🟢 |
| 1-0f | 예시 사이트 6개 생성(우리 엔진) + 템플릿 카탈로그 (D15) | 구현 / OpenCode → Claude 검토 | `app/templates_catalog.py`, `generated/examples/**` | 0-3b | ⏳ |
| 1-0g | 개인정보처리방침·이용약관 초안 (D14) | 계획 / Claude | `static/privacy.html` | — | 🟢 |
| 1-1 | users·oauth_accounts·room_members 스키마 | 구현 / Claude | `app/db/**` | 0-2a | ⏳ |
| 1-2 | OAuth 라우트(state 검증), 세션 쿠키, `/me`, `/logout` | 구현 / Claude | `app/auth/**`, `app/api/auth.py` | 1-1, 1-0a | ⏳ |
| 1-3 | 게스트 방 귀속(claim), 내 프로젝트 목록 | 구현 / Claude | `app/services/rooms.py`, `app/api/me.py` | 1-2 | ⏳ |
| 1-4 | 랜딩·로그인·내 프로젝트 화면 연결 | 구현 / OpenCode → Claude 검토 | `static/landing.html`, `static/projects.html` | 1-2, 1-0b | ⏳ |
| 1-5 | 인증 테스트(단위·E2E) | 검증 / OpenCode | `tests/**` | 1-2 | ⏳ |
| 1-6 | 사용자 작업(로그인 구현 C4와 병행): 카카오 로그인 활성화·Redirect URI 등록·동의항목(닉네임, 카카오톡 메시지 전송은 D32용), 구글 OAuth 클라이언트 발급(테스트 모드, D9) (절차: OAUTH_SETUP.md §5). 시크릿은 입력 스크립트로 서버에 넣는다(D10) | 사용자 | 콘솔 | 1-0a | 🟢 사용자 작업 대기 |

### 채팅방 정책 — 초대·기록·종료/초기화·알림 ([ROOM_POLICY.md](ROOM_POLICY.md) §7)

| WP | 내용 | 레인/담당 | 소유 파일 | 의존 | 상태 |
|---|---|---|---|---|---|
| R-0 | 보안: 비밀 토큰·공개 식별자 분리, 조회·전송 참여자 확인 | 구현 / Claude | `app/services/rooms.py`, `app/api/rooms.py`, `app/store.py` | 0-2b | ✅ 대신 투표 차단, 비참여자 조회 차단 (방 ID로 입장하는 경로는 R-2에서 차단) |
| R-1 | Alembic 0002 스키마 | 구현 / Claude | `app/db/**`, `alembic/**` | R-0 | 🟢 |
| R-2 | 초대 링크 API·입장 흐름·역할 | 구현 / Claude + OpenCode(화면) | `app/api/invites.py`, `static/room.html` | R-1 | 🟢 |
| R-3 | 기록 페이지네이션·읽음·안 읽은 수 | 구현 / Claude + OpenCode(화면) | `app/api/rooms.py`, `static/room.html` | R-1 | 🟢 |
| R-4 | 점검 작업·타이머 T1~T7 | 구현 / Claude | `app/services/lifecycle.py` | R-1 | 🟢 |
| R-5 | 알림·웹 푸시 | 구현 / Claude + OpenCode | `app/services/notify.py`, `static/sw.js` | R-4 | ⏳ |
| R-6 | 내 채팅방 목록·계정 귀속 | 구현 / Claude | `app/api/me.py` | 1-2, 1-3 | ⏳ |
| R-7 | 정책 테스트 | 검증 / OpenCode | `tests/**` | 각 WP | ⏳ |

### 개발자 결정 요청 (자동 개발 중 사람 결정 받기)

| WP | 내용 | 레인/담당 | 소유 파일 | 의존 | 상태 |
|---|---|---|---|---|---|
| 0-6a | 전화 발신 수단·에스컬레이션 조사 | 계획 / OpenCode J | `docs/product/DEV_DECISION_CALL.md` | — | ✅ 추천: 텔레그램 먼저 → 무응답 시 Twilio 전화·키패드, 월 약 $8 |
| 0-6b | 음성(TTS·STT) 결정 판정 프로토콜 조사 | 계획 / OpenCode J2 | `docs/product/DEV_DECISION_VOICE.md` | — | ✅ 복창 확인 필수, 돈·비가역 결정은 음성 확정 불가, 월 5천원대 |
| 0-6c | 결정 요청 시스템: 텔레그램 → 무응답 10분 뒤 전화(최대 2회), 음성+복창, 돈 드는 결정은 버튼 재확인, 월 $15 상한 (D11) | 구현 / Claude | `app/api/decisions.py`, `scripts/dev-decision-request.sh` | 0-6a, 0-6b | 🟢 착수 가능 (실통화는 사용자 Twilio 가입 후) |

2단계(PRD 엔진) 이후 WP는 1단계 구현이 시작될 때 계획 레인에서 이 표에 추가한다.

## 5. 현재 레인 배치 (2026-09-26 갱신)

핵심 경로: **P-1 요구사항 엔진 → P-2 명세 → P-3 부품 → P-4 렌더러 → P-5~P-7 시안 → P-8 제작 연결.** 아래는 이 경로와 겹치지 않아 병렬로 돌릴 수 있는 것.

### 5.1 지금 돌고 있는 것

| 레인 | 작업 | 담당 |
|---|---|---|
| 구현(핵심) | P-1a 칸 스키마·업종 표 ✅ → P-1c 엔진(추출·규칙·상태머신 연결) | Claude |
| 구현(주변) | P-1b 시나리오 36개 | OpenCode N |
| 계획 | 1-0g 개인정보처리방침·이용약관 초안 | OpenCode O |
| 계획 | P-3 준비: 섹션 부품 명세 초안(tokens·부품·patch 연산) | OpenCode P |

### 5.2 병렬로 시작할 수 있는 것 (핵심 경로와 무관)

| 순위 | 작업 | 왜 지금 | 담당 | 막는 것 |
|---|---|---|---|---|
| 1 | **S-1 미리보기 별도 호스트** | 로그인 쿠키 도입 전 필수(보안 P0) | Claude, 반나절 | 없음 |
| 2 | **1-1·1-2 로그인(카카오·구글)**: `users`+`oauth_accounts` 분리형(UQ-2), 가짜 제공자로 끝까지 테스트 | 사용자 콘솔 작업(1-6)이 끝나면 키만 넣으면 됨 | Claude | S-1, UQ-2 |
| 3 | **0-3 작업 큐 + 90초 오판정 버그** | P-8 전 필수, 현재 운영 버그 | Claude | 없음 |
| 4 | **0-6c 결정 요청 — 텔레그램 부분** | 개발 중 사람 결정 병목 해소. 전화는 Twilio 가입 뒤 | Claude | 전화만 사용자 가입 |
| 5 | 0-5b 비용 일일 점검 | 0-6c 텔레그램 채널을 재사용하면 반나절 | Claude | 0-6c |
| 6 | E-1 백업 서버 밖 보관(암호화 → OCI 무료 저장소) | 같은 서버에만 백업이 있음 | Claude | **OCI 저장소 생성 승인(UQ-5)** |
| 7 | R-1 초대·알림 스키마 → R-2 초대 링크 | 방 주소로 입장하는 경로 차단(R-0 잔여) | Claude | 마이그레이션 번호는 병합 순서대로 |
| 8 | 채팅방 화면 React 이전 | P-1f 카드·R-2/R-3 화면의 바탕 | OpenCode(화면) → Claude 검토 | **캔버스 안 선택(사용자)** |
| 9 | 고객 음성 입력(STT) 계획 | DEV_DECISION_VOICE 조사를 재사용 | OpenCode | 없음 |
| 10 | 0-4b 스테이징 | 마이그레이션 안전 규칙(USER_DB_PLAN)의 전제 | OpenCode | 없음 |

### 5.2a 2026-09-26 추가 (D29~D33)

| 순위 | 작업 | 담당 | 상태 |
|---|---|---|---|
| 1 | 대화 턴 기록(`chat_turns`: 원문 + 엔진 판단, 90일) — AI 성능 평가의 재료 | Claude | 진행 |
| 2 | 기능 사례집·문의 종류 프로필 초안 | OpenCode W | 진행 |
| 3 | 입구 게이트 구현: 종류 분류 → 프로필 → 질문 예산 → 기능 판정 → 막힘 처리 | Claude | W 결과 대기 |
| 4 | 공용 기능 ① 문의 받기 API + 문의 부품 + 사장님 알림(채팅방·텔레그램, 카카오 "나에게 보내기"는 카카오 콘솔 설정 뒤) | Claude(API) + OpenCode(부품) | 대기 |
| 5 | 로그 기반 AI 성능 평가기(실제 대화 → 규칙 지표 + AI 채점, 개인정보 가림, 결과는 저장소 밖) | OpenCode(도구) → Claude(실행) | 1 뒤 |
| 6 | 공용 기능 ② 예약·신청, ③ 사이트 회원가입, ④ 결제(다시 검토) | Claude | 대기 |

### 5.4 병렬 개발 방식과 다음 36시간 계획 (2026-09-26 ~ 09-28 마감)

**방식**

| 규칙 | 내용 |
|---|---|
| 작업 폴더 분리 | OpenCode 작업은 하나당 git worktree 하나(`../agt001-wt-<이름>`, 브랜치 `oc/<이름>`). 같은 파일을 건드려도 서로 막지 않는다 |
| 합치기 | Claude가 작업 폴더의 diff를 읽고 테스트를 돌린 뒤 patch로 main에 적용·커밋. OpenCode는 커밋하지 않는다 |
| 동시 개수 | OpenCode 최대 4개 + Claude 핵심 1줄. 끝나면 바로 다음 작업을 띄워 빈 레인이 없게 한다 |
| 계약 먼저 | 화면(OpenCode)과 서버(Claude)가 나뉘는 작업은 Claude가 API 요청·응답 형식을 먼저 정해 지시문에 넣는다 |
| 검증 | 매 합치기: 단위 테스트(CI) + 해당 기능 실측. 실제 NVIDIA 호출·운영 DB가 필요한 검증은 Claude가 한다 |
| 배포 | 2~3시간마다 모아서. 커밋된 main만, 스냅샷 + 자동 되돌리기 |
| README | 배포할 때마다 "지금 상태" 절을 갱신 |

**Claude 핵심 레인 (순서대로)**

| # | 작업 | 예상 |
|---|---|---|
| C1 | 요구사항 엔진 결함 16건 수정 → `tests/engine` 전부 통과 → CI 편입 | 3시간 |
| C2 | 입구 게이트 구현(문의 종류 분류, 종류별 프로필, 질문 예산, 기능 판정 — 기능 사례집 사용) | 4시간 |
| C3 | 실제 AI 평가 실행: 추출 60개(T2), 시나리오 36개(T3) → 성적표 → 프롬프트·규칙 개선 반복 | 2시간 + 반복 |
| C4 | 카카오·구글 로그인(1-1·1-2): `users`+`oauth_accounts`, state·PKCE, `__Host-` 세션 쿠키, `/me`·`/logout`, 상태 변경 API Origin 검사, 가짜 제공자로 전 과정 테스트. 실제 키는 사장님 콘솔 설정(1-6) 뒤 | 4시간 |
| C5 | 로그인 전 방을 계정으로 옮기기(1-3), 내 프로젝트 목록을 계정 기준으로 | 2시간 |
| C6 | 공용 기능 ① 문의 받기 API + 채팅방·텔레그램 알림(카카오 "나에게 보내기"는 C4 뒤) | 3시간 |
| C7 | 시안 3안 렌더러(섹션 부품 + 토큰) → 요구 7 충족 | 4시간 |
| C8 | 미리보기 별도 호스트(S-1) | 1시간 |

**OpenCode 레인 (동시 최대 4개)**

| # | 작업 | 의존 |
|---|---|---|
| O1 | 실제 대화 기록 AI 평가 도구(`evals/review_live.py`) | 진행 중 |
| O2 | 내 프로젝트 화면(React `/projects`, 서버 API 완료) + 랜딩 머리글 "내 프로젝트" | 없음 |
| O3 | 로그인 화면 연결(랜딩 로그인 메뉴 → `/auth/<제공자>/start`, 로그인 후 상태 표시) | C4 계약 |
| O4 | 문의 부품(`contact--form`) + 사이트용 문의 스크립트 없이 동작하는 방식 | C6 계약 |
| O5 | 시안 3안 선택 화면(채팅방 카드 3개 + 전체 화면) | C7 계약 |
| O6 | 질문 "듣기" 버튼(NVIDIA Magpie TTS) | Claude가 `/api/tts` 계약 |
| O7 | 문서 레인: README "지금 상태"·파이프라인 표 갱신 초안 | 배포마다 |

### 5.3 사용자 결정 대기

| 항목 | 무엇 | 문서 |
|---|---|---|
| 시안 캔버스 | 요구사항·시안·진행·수정 화면 각 3안 중 선택 | Design 캔버스 |
| UQ-1~6 | 토큰 미저장, 회원 테이블 분리형, 탈퇴 익명화 범위, 사이트 폼 베타 제외, 백업 버킷, 방침 AI 초안 | USER_DB_PLAN.md |
| RAG 5문항 | 벡터 연기, 임베딩 모델, 전화·주소 제외 등 | REQUIREMENTS_RAG_REVIEW.md §8 |
| 1-6 | 카카오·구글 콘솔 설정 | OAUTH_SETUP.md §5 |
| 0-6c 전화 | Twilio 가입·충전·번호 | DEV_DECISION_CALL.md |
| S-7 | 전용 도메인(D2 재검토) | DESIGN_PIPELINE_PLAN.md §13.5 |
