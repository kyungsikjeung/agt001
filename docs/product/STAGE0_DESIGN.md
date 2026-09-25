# 0단계 설계 — 기반 정비 (FastAPI 전환)

> 작성일: 2026-09-25 / 상위 문서: [PRODUCT_ROADMAP.md](PRODUCT_ROADMAP.md) §3 0단계
> 결정 D1: **FastAPI로 전환** (2026-09-25 확정)

## 1. 목표와 원칙

- 기존 기능(1:1 채팅, 공유방, 투표, 견적, 시안, 코드생성, 배포 서빙)을 **동작 변화 없이** 새 구조로 옮긴다.
- 프론트엔드(`static/index.html`, `static/room.html`)가 쓰는 API 계약(경로, 요청·응답 필드)은 그대로 유지한다. 프론트는 이 단계에서 수정하지 않는다.
- 한 번에 다 바꾸지 않는다. 아래 4개 하위 단계로 나누고, 각 하위 단계가 끝날 때마다 테스트와 실측 검증을 통과한 뒤 커밋·배포한다.

## 2. 하위 단계

| 단계 | 내용 | 저장소 | 완료 기준 |
|---|---|---|---|
| **0-1** | Flask → FastAPI 이식 + 모듈 분리 + 자동 테스트 | 기존 JSON 파일 그대로 | 기존 API 계약 전부 테스트 통과, 로컬·OCI에서 전체 흐름 실측 |
| **0-2** | PostgreSQL + SQLAlchemy + Alembic, 세션·방·메시지를 DB로 이전 | PostgreSQL | JSON 파일 제거, 재시작 후 상태 유지, 동일 테스트 통과 |
| **0-3** | 코드생성을 스레드에서 작업 큐로 이전, 샌드박스 자원 제한 | Redis | 재시작해도 작업 유실 없음, 동시 실행 상한, 타임아웃 시 컨테이너 정리 |
| **0-4** | CI, 스테이징 분리, 롤백, 구조화 로그 | — | PR마다 테스트 자동 실행, 스테이징 검증 후 운영 배포, 1명령 롤백 |

## 3. 모듈 구조 (0-1)

```
app/
  main.py            FastAPI 앱 생성, 라우터 등록, 정적 파일, 기동/종료 처리
  config.py          환경설정 (pydantic-settings, .env 로드)
  llm.py             NIM 클라이언트 (chat, embedding) — 교체 가능한 단일 진입점
  store.py           세션·방 저장소 (0-1: 인메모리+JSON / 0-2: PostgreSQL로 교체)
  security.py        입력 정제 (ID 토큰, 프롬프트 스펙)
  services/
    rag.py           기존 프로젝트 유사도 사전확인
    quote.py         견적 생성과 폴백
    design.py        시안 렌더링 + 스크린샷
    codegen.py       Hermes 샌드박스 코드생성
    deploy.py        생성물 공개 URL
    chat_flow.py     대화 상태머신 (1:1과 공유방이 공유)
    rooms.py         방 생성, 입장, 과반 투표
  api/
    chat.py          POST /chat
    rooms.py         POST /room, POST /room/{id}/chat, GET /room/{id}/messages
    public.py        GET /health, /design/{id}, /design/{id}/preview.png, /site/{id}/...
tests/
  conftest.py        가짜 LLM·코드생성 주입, 임시 저장 경로
  test_*.py
```

**모듈 경계 원칙**
- `api/`는 요청 검증과 응답 변환만 한다. 업무 로직은 `services/`에 둔다.
- `services/`는 저장소(`store.py`)와 LLM(`llm.py`)을 직접 import하지 않고 인자·주입으로 받는 쪽으로 점진 이동한다. 0-1에서는 이식 안전성을 위해 모듈 전역을 유지하되, 테스트에서 교체 가능한 형태로 둔다.

## 4. 동작 호환 규칙 (0-1)

| 항목 | Flask 동작 | FastAPI 이식 |
|---|---|---|
| 핸들러 | 동기 | 동기 `def` 유지 → 스레드풀에서 실행되어 NIM 동기 호출이 이벤트 루프를 막지 않음. 비동기 전환은 2단계(스트리밍)에서 |
| 정적 파일 | `static/`을 `/`에 서빙, `/`는 index.html | 라우터 등록 후 `StaticFiles(html=True)`를 `/`에 마운트 |
| 요청 본문 | `get_json(force=True)`, 필드 누락 허용 | 모든 필드 선택값인 Pydantic 모델 |
| 404/400 | HTML 에러 | JSON 에러 (프론트는 `res.ok`만 확인하므로 영향 없음) |
| 배포 URL | `request.url_root` 기준 절대 URL | `request.base_url` + uvicorn `--proxy-headers`. Caddy 뒤에서 `https://` 가 나오도록 개선 |
| `/site/{id}` | 슬래시 없는 경로는 리다이렉트 | 동일하게 리다이렉트 |
| 경로 순회 방어 | `send_from_directory` | 해석 경로가 산출물 디렉터리 안인지 명시적으로 검사 |
| 기동 시 | 문서 임베딩 선계산, JSON 복구 | 기동 처리(lifespan)에서 동일하게 수행, 테스트에서는 끔 |
| 실행 | `python backend.py` | `uvicorn app.main:app` |
| 음수 `since` | 음수 슬라이스로 끝에서부터 반환(의도치 않은 동작) | 0으로 고정해 전체 반환 (의도된 변경) |

## 5. 테스트 전략

- **단위:** 정제 함수, 견적 JSON 파싱과 폴백, 과반 투표 판정, 상태머신 전이.
- **API 통합:** TestClient로 1:1 전체 흐름(인사 → 요청 → 승인 → 견적 → 진행 → 생성 완료 → 배포 URL), 공유방 흐름(2인 입장 → 1표 대기 → 과반 통과 → GET 폴링만으로 완료 전이), 시안·사이트 서빙, 경로 순회 차단.
- **외부 의존 차단:** NIM, Docker, Playwright는 테스트에서 가짜로 교체한다. 실제 호출 검증은 로컬·OCI 실측으로 한다.
- **E2E(브라우저):** Playwright로 `room.html` 입장·전송·투표. 0-4에서 CI에 편입.

## 6. 0-2 상세 설계: PostgreSQL 전환

### 6.1 기술 선택

| 항목 | 선택 | 이유 |
|---|---|---|
| DB | PostgreSQL 16 (compose `db` 서비스, 이름 있는 볼륨) | OCI에서 실측 기동 확인, 유휴 27MB |
| 드라이버 | psycopg 3 (`psycopg[binary]`) | 현재 유지되는 표준 드라이버 |
| ORM | SQLAlchemy 2.0, **동기** 세션 | 핸들러가 동기(스레드풀)라 맞음. 비동기 전환은 2단계 스트리밍 때 함께 판단 |
| 마이그레이션 | Alembic | 스키마 변경 이력, 운영 적용 절차 고정 |
| 테스트 DB | 단위 테스트는 SQLite 메모리가 아니라 **실제 PostgreSQL**(로컬 compose, CI는 service container) | JSONB·잠금 동작이 달라 SQLite로는 검증이 안 됨 |

### 6.2 스키마

```
sessions(
  id TEXT PK, state TEXT NOT NULL, requirement_id TEXT UNIQUE NOT NULL,
  last_request TEXT, quote JSONB, codegen JSONB,
  design_url TEXT, design_preview_url TEXT, design_url_unsent BOOL DEFAULT false,
  deploy_url TEXT, created_at TIMESTAMPTZ, updated_at TIMESTAMPTZ)
rooms(id TEXT PK, session_id TEXT FK→sessions UNIQUE, ai_status TEXT, created_at TIMESTAMPTZ)
room_members(room_id FK, member_id TEXT, nickname TEXT, joined_at, last_seen, PK(room_id, member_id))
room_messages(id BIGSERIAL PK, room_id FK, seq INT, member_id, nickname, text, kind, ts,
              UNIQUE(room_id, seq), INDEX(room_id, seq))
room_votes(room_id FK, member_id, vote, PK(room_id, member_id))
```
1단계에서 `users`, `oauth_accounts`, `room_members.user_id`, 4단계에서 `attachments`가 추가된다 (`LANDING_AUTH_DB_UPLOAD_PLAN.md`).

### 6.3 동시성 규칙 (지금 코드의 잠재 버그를 함께 해결)

지금은 두 참여자가 같은 방에 동시에 메시지를 보내면, 락 밖에서 같은 dict를 고치고 파일 전체를 덮어쓴다. 메시지 순번(seq)이 겹치거나 한쪽 변경이 사라질 수 있다.

- **방 단위 직렬화:** 방에 쓰는 요청(`post_message`, 완료 전이를 일으키는 `get_messages`)은 트랜잭션 시작 시 `SELECT ... FROM rooms WHERE id=:id FOR UPDATE`로 방 행을 잠근다. 같은 방 요청은 순서대로, 다른 방은 병렬로 처리된다.
- **seq 부여:** 잠금 안에서 `max(seq)+1`. `UNIQUE(room_id, seq)`가 최종 안전장치다.
- **1:1 세션:** `sessions` 행을 `FOR UPDATE`로 잠근다.
- **코드생성 결과 기록:** 백그라운드 작업은 `UPDATE sessions SET codegen=... WHERE id=...`만 한다. 완료 전이(DONE)는 여전히 요청 경로가 잠금 안에서 수행한다.
- **긴 NIM 호출과 잠금:** RAG·견적 호출(수 초)을 잠금 안에서 하면 같은 방의 폴링이 그동안 대기한다. 이는 "한 방에서 AI 응답은 한 번에 하나"라는 현재 의미와 같으므로 허용한다. 폴링 GET은 완료 전이가 필요 없을 때 잠금 없이 읽는다.

### 6.4 코드 구조 변화

- `app/db/models.py`(테이블), `app/db/session.py`(엔진·세션 팩토리), `alembic/`.
- `store.py`는 "dict를 주고 저장"하는 방식에서 **저장소 함수**(`get_session_for_update`, `save_session`, `append_room_message`, ...)로 바뀐다. 서비스 계층은 요청마다 하나의 트랜잭션(unit of work) 안에서 동작한다.
- 상태머신(`chat_flow.process_turn`)은 계속 dict를 받아 고친다. 트랜잭션 경계에서 dict ↔ 행 변환을 한다. 이렇게 하면 0-1 테스트의 흐름 검증을 거의 그대로 재사용할 수 있다.

### 6.5 기존 데이터 이전

- 운영 `generated/sessions.json`, `rooms.json`을 읽어 DB에 넣는 일회성 스크립트(`scripts/migrate_json_to_pg.py`). 멱등(두 번 돌려도 중복 없음).
- 이전 후 JSON 파일은 `generated/legacy/`로 옮겨 보관하고 코드에서 참조를 없앤다.

### 6.6 완료 기준

- 0-1 단위·API·E2E 테스트가 PostgreSQL 위에서 전부 통과.
- 동시성 테스트: 같은 방에 20개 메시지를 병렬 전송 → seq가 0..N으로 빈틈·중복 없음.
- 재시작 후 대화·방·메시지 유지 (JSON 파일 없이).
- OCI에서 `db` 컨테이너 + 백업 스크립트 동작, 이전 스크립트로 운영 데이터 이전 확인.
