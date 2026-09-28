# 예약 봇 구현 계획: 내부 요구사항 + 물결 (BOOKING_BOT_IMPL_PLAN)

> 2026-09-29 (KST) / Claude. 대표 지시: "내부 요구사항을 정리하고 구체적인 구현 계획을 세우고, 빈틈이 없으면 구현 시작."
> 설계 근거: [OWNER_CONSOLE_PLAN](OWNER_CONSOLE_PLAN.md), [AI_BOOKING_AGENT_PLAN](AI_BOOKING_AGENT_PLAN.md), [BOTMAKER_PLAN](BOTMAKER_PLAN.md), [BOOKING_RULES_PLAN](BOOKING_RULES_PLAN.md). 가게 표는 [SALES_DB_PLAN §4.1](SALES_DB_PLAN.md)·DATA_ARCHITECTURE M1과 같은 모양으로 맞춘다.
> 브랜치: `booking-bot` (워크트리 `../agent_project-booking`). 관리자 화면(`admin-site`) 작업과 파일이 겹치지 않게 한다.

## 0. 확정된 대표 결정

| # | 결정 |
|---|---|
| E2 | 손님 입구는 **사이트 채팅 먼저**, 카카오 채널은 나중 |
| E3 | 사장님 L2(가게 확인)·L3(사업자 확인)는 **우리 고객센터 번호로 접수**, 운영자가 처리 |
| BM | 예약 봇은 **봇메이커 에이전트가 집요한 인터뷰**로 만든다 |
| F1(추천 채택) | 봇 = 공통 엔진 + 가게별 명세(JSON). 가게마다 코드를 만들지 않는다 |
| F4(추천 채택) | 첫 업종 모드: **slot(미용실·네일 등 1:1 시술)**, 다음 **table(식당 페이싱)**. class·night는 지금 방식 유지 |

## 1. 내부 요구사항

### 1.1 사장님·가게 (OWN)

| ID | 요구사항 | 확인 방법 |
|---|---|---|
| OWN-1 | 관리자 ID는 `users.id`. 가게는 `shops(id bigint PK, site_key UNIQUE)`, 권한은 `shop_members(shop_id, user_id, role owner·staff)` | 모델·마이그레이션 |
| OWN-2 | 권한 확인은 `shops.require_member(user_id, site_key, role)` 한 함수. 멤버 행이 없고 옛 방식(방장이 방을 계정에 붙임)으로 주인이면 그 자리에서 가게·owner 행을 만든다(지연 이행) | 기존 `/settings` 테스트 그대로 통과 + 새 테스트 |
| OWN-3 | 남의 가게는 404(존재를 알리지 않음) | 테스트 |
| OWN-4 | 로그인한 사장님은 **어느 기기에서든** 예약을 확정·거절한다 | `POST /api/owner/shops/{k}/bookings/{id}/{action}` 테스트 |
| OWN-5 | L2·L3 칸: `shops.phone_verified_at`, `biz_no`, `biz_verified_at`, `verified_by`. 처리 함수 `shops.mark_verified(admin_user_id, site_key, kind, biz_no?)` + `admin_audit` 기록. 화면은 `admin-site` 병합 뒤 | 단위 테스트 |
| OWN-6 | `/owner` 페이지에 고객센터 번호(`settings.support_phone`) 안내 | 페이지 |

### 1.2 예약 명세 (SPEC)

| ID | 요구사항 |
|---|---|
| SPEC-1 | 명세 모양은 `contracts/botmaker_to_bot.schema.json`. 모드 `slot`·`table` |
| SPEC-2 | `booking_spec.validate(spec) -> list[문제]`: 필수 칸(모드별), 시각 형식, 소요시간 > 0, 간격 ∈ {10,15,20,30,60}, 마감 − 소요시간 < 시작이면 모순 |
| SPEC-3 | 판 관리 `bot_specs(id, shop_id, version, spec, status draft·active·archived, created_by, created_at)`. 켜기 = 이 판 active, 이전 active는 archived. 되돌리기 = 옛 판을 다시 켜기 |
| SPEC-4 | 칸마다 출처 `provenance[path] = filled·assumed·default` (봇메이커가 채움) |

### 1.3 빈 시간 계산 (CAL)

| ID | 요구사항 |
|---|---|
| CAL-1 | `slots.find(spec, day, *, service, staff, party, busy, closures, now) -> list[후보]` 순수 함수(DB 없음) |
| CAL-2 | 요일별 영업 구간 여러 개(브레이크 = 구간 사이), 담당자별 근무 구간·휴무 요일, `step_min` 간격 시작, 끝(소요 + 정리) ≤ 구간 끝, `policy.last_start`, `lead_min`, `max_days` |
| CAL-3 | 휴무·막기(`booking_closures`, 가게 전체 또는 담당자별) |
| CAL-4 | slot: 담당자별 `staff_minutes` 덮어쓰기, 시술 가능 담당자만, "상관없음"이면 그날 예약이 가장 적은 담당자 |
| CAL-5 | table: 시작 칸마다 팀 수 ≤ `pace_teams`, 인원 합 ≤ `pace_people`, 식사 시간은 인원별(`meal_minutes`), 인원 범위 |
| CAL-6 | 결과가 없으면 `slots.next_days(...)`로 가까운 가능한 날 3개 |

### 1.4 예약 저장 (BOOK)

| ID | 요구사항 |
|---|---|
| BOOK-1 | `bookings` + `shop_id`, `start_at`, `end_at`, `resource_key`, `source`(web·chat·phone·owner), `hold_expires_at`, `chat_token_hash`. 상태 + `held`·`cancelled`·`no_show`·`expired`. `visit_date`·`visit_time`은 계속 채운다(보관 삭제·옛 화면이 쓰므로) |
| BOOK-2 | slot 모드 겹침은 DB가 막는다: `EXCLUDE USING gist (resource_key WITH =, tstzrange(start_at, end_at) WITH &&) WHERE status IN ('held','requested','confirmed') AND resource_key IS NOT NULL` (`btree_gist`) |
| BOOK-3 | table 모드는 가게·날짜 advisory 잠금 안에서 다시 세고 저장(지금 `decide`와 같은 방식) |
| BOOK-4 | `engine.hold()` 10분 → `engine.confirm_hold(name, phone)` → requested(또는 `auto_confirm`이면 confirmed). 잡기 전에 만료된 hold를 `expired`로 바꾼다 |
| BOOK-5 | `engine.change()`: 새 hold → 옛 예약 cancelled, 한 트랜잭션. 새 자리를 못 잡으면 옛 예약 그대로 |
| BOOK-6 | `engine.cancel()`: `cancel_deadline_hours` 전까지만. 사장님은 언제나 가능 |
| BOOK-7 | active 명세가 **없는** 가게는 지금 경로(`bookings.submit`, `availability`) 그대로 |
| BOOK-8 | 모든 상태 변경은 `booking_events(booking_id, shop_id, actor, action, detail, ts)`에 남긴다 |

### 1.5 봇메이커 (BM)

| ID | 요구사항 |
|---|---|
| BM-1 | 질문 은행: 모드별 `{id, path(채울 칸), ask, kind, suggest(추천 답 버튼), default, required}`. 시술·선생님마다 질문이 생기므로 JSON 파일이 아니라 `botmaker._questions(spec)`가 만든다(구현 때 변경) |
| BM-2 | 추출: `llm.chat_json`으로 `{"set": [{"path", "value"}]}`만 받는다. 숫자는 `numbers.grounded_numbers`로 사장님 말에 근거가 있을 때만 filled |
| BM-3 | 다음 질문 = ① 모순 ② 빈 필수 칸 ③ 조건이 켜진 파고들기 질문, 한 번에 하나. 버튼 답은 LLM 없이 바로 적용 |
| BM-4 | 출구: [추천대로]→default, [나중에]→건너뛰고 끝에 다시, [알아서]→assumed. 필수 칸이 assumed여도 켤 수 있지만 규칙 카드에 표시 |
| BM-5 | 모순 검사(마지막 시작 + 소요 > 마감, 담당자 0명, 시술을 할 수 있는 담당자 0명, 브레이크가 영업 밖) |
| BM-6 | 모의 손님 시험 `botmaker.simulate(spec)`: 정해진 7종(내일 예약·마지막 시각 넘김·겹침·휴무·인원 초과·마감 지난 취소·모르는 질문)을 계산기로 돌려 사장님이 읽을 문장 목록 |
| BM-7 | 켜기 조건: `validate` 문제 0 + `simulate` 실패 0 |
| BM-8 | 대화 상태는 `bot_specs`의 draft 판 `spec` + `spec._interview`(물은 것·건너뛴 것) |

### 1.6 손님 채팅 (CH)

| ID | 요구사항 |
|---|---|
| CH-1 | 우리 도메인 `/chat/{site_key}` 페이지(가게 이름·색). 생성 사이트는 스크립트가 없으므로 예약 부품에 "채팅으로 예약" 링크 |
| CH-2 | `POST /api/chat/{site_key}` `{text?, action?}` → `{reply, buttons[]}`. 버튼 `action`은 LLM을 거치지 않는다 |
| CH-3 | 의도 6개(예약·변경·취소·확인·문의·사장님께) — 규칙 먼저, 애매할 때만 LLM |
| CH-4 | 시각은 계산기 결과만 버튼으로. 채팅 답에 계산기 밖 시각이 들어가지 않는다(평가 기준) |
| CH-5 | 손님 식별: 예약 때 이 브라우저에 `chat_token`(쿠키, DB에는 해시) → 조회·변경·취소는 이 토큰으로 만든 예약만. 다른 기기면 문자 인증(가게에서 켰을 때) 뒤, 아니면 "가게로 전화" |
| CH-6 | 대화 상태 `agent_threads(token_hash PK, shop_id, draft JSONB, updated_at)`, 30분 지나면 초안 폐기, 7일 뒤 행 삭제. `chat_turns`에는 남기지 않는다(전화번호) |
| CH-7 | IP당 요청 제한(문의 `_allow` 재사용), 모르는 질문은 채팅방 알림(`ask_owner`) |

### 1.7 사장님 화면 (UI)

| ID | 요구사항 |
|---|---|
| UI-1 | `/owner` (정적 HTML + 우리 도메인 스크립트, `settings.html`과 같은 방식 — React 빌드 없이 빠르게. 달력은 목록형으로 시작) |
| UI-2 | 탭: 예약(대기·오늘·다가오는, 확정·거절·취소·노쇼) / 예약 봇(봇메이커 대화 + 규칙 카드 + 시험 결과 + 켜기) / 휴무·막기 / 가게 설정(기존 `/settings` 링크) |
| UI-3 | 모든 변경은 `_check_origin` + `require_member` |

## 2. 파일 계획

| 물결 | 새 파일 | 바꾸는 파일 |
|---|---|---|
| W1 가게·권한 | `alembic/versions/0014_shops.py`, `app/services/shops.py`, `tests/unit/test_shops.py` | `app/db/models.py`, `app/store.py`(reset), `app/services/shop_settings.py`(`owned_sites`→`shops`), `app/services/auth.py`(`claim_rooms` 뒤 멤버십) |
| W2 명세·계산 | `contracts/botmaker_to_bot.schema.json`, `app/services/booking_spec.py`, `app/services/slots.py`, `tests/unit/test_slots.py`, `tests/unit/test_booking_spec.py` | — |
| W3 저장 엔진 | `alembic/versions/0015_booking_engine.py`, `app/services/booking_engine.py`, `tests/unit/test_booking_engine.py` | `app/db/models.py`, `app/store.py`, `app/services/bookings.py`(active 명세면 엔진으로) |
| W4 봇메이커 | `app/services/botmaker.py`, `tests/unit/test_botmaker.py` | — |
| W5 API | `app/api/owner.py`, `app/api/chat_agent.py`, `app/services/chat_agent.py`, `tests/unit/test_owner_api.py`, `tests/unit/test_chat_agent.py` | `app/main.py`(라우터 두 줄), `app/config.py`(`support_phone`) |
| W6 화면 | `static/owner.html`, `static/chat.html` | `app/api/public.py`(`/owner`, `/chat/{k}`), `templates/sections/booking--slots.mustache`(채팅 링크) |

## 3. 빈틈 점검

| 걱정 | 답 |
|---|---|
| 기존 방장 기기 확정(`/room/.../decision`)이 깨지나 | 그대로 둔다. 새 계정 경로를 **더한다** |
| 옛 가게(명세 없음)의 공개 사이트 예약 | BOOK-7: 지금 경로 그대로. 명세를 켠 가게만 새 엔진 |
| 명세를 켠 가게에 사이트 폼으로 예약이 오면 | `bookings.submit`이 엔진의 `find`로 그 시각이 가능한지 확인하고 `start_at/end_at/resource_key`를 채워 저장(requested). 겹침은 DB가 막는다 |
| hold가 만료됐는데 배제 제약에 남음 | 잡기 전에 같은 가게의 만료 hold를 `expired`로 바꾸는 UPDATE를 같은 트랜잭션에서 먼저 |
| `btree_gist` 확장 권한 | PG13+에서 trusted 확장이라 DB 소유자가 만들 수 있다. 운영 DB 사용자로 0015 전에 `CREATE EXTENSION` 가능 여부 확인(배포 체크리스트) |
| 시간대 | 계산은 KST 벽시계, 저장은 timestamptz. `availability.KST` 재사용 |
| 30일 보관 삭제 | `visit_date`를 계속 채우므로 `purge_expired` 그대로 |
| 손님이 남의 예약을 봄 | CH-5 토큰·문자 인증 없이는 조회 불가 |
| 봇메이커 LLM이 숫자를 지어냄 | BM-2 grounded. 테스트는 가짜 LLM이 "150"을 내도 말에 없으면 assumed로 떨어지는지 |
| 동시 두 손님 | 배제 제약 테스트(두 트랜잭션) |
| 관리자 화면 작업과 충돌 | `app/main.py`·`app/api/public.py`는 한 줄씩만 더한다(병합 쉬움). 마이그레이션 번호 0014·0015는 지금 비어 있음(admin-site는 마이그레이션 없음) |
| 결제·매출 계획(SALES_DB)과 모양 | `shops`·`shop_members`는 같은 모양. `services` 표는 매출 작업 때 active 명세에서 만든다(지금은 명세가 진실) — 두 곳에 같은 값을 두지 않기 위해 |
| 10/15 배포 동결 | 브랜치에서 개발, 병합·배포 시점은 대표 결정 |

## 4. 완료 기준

- 새 테스트 + 기존 unit 전체 통과(`TEST_DATABASE_URL`은 전용 DB `agt001_booking`).
- 시나리오: 미용실 명세를 봇메이커 대화(가짜 LLM)로 만들고 켠 뒤, 손님 채팅으로 예약 → 사장님 계정으로 확정 → 손님 변경 → 취소까지 한 테스트에서 통과.
- 채팅 답에 계산기 밖 시각 0.

## 변경 이력

| 날짜 | 내용 |
|---|---|
| 2026-09-29 | 처음 작성 |
