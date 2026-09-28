# 손님 명단·겹침 막기·문자 인증 — 계약·작업판 (CUSTOMER_PLAN)

> 2026-09-28 (KST). 근거: [research/RESEARCH_CUSTOMER_IDENTITY](research/RESEARCH_CUSTOMER_IDENTITY.md) 단계 1~3, 대표 결정(손님 회원가입 없음·본인인증 기본 끔·문자 인증은 기기 기억 + 자동 입력·보관은 지금 규칙과 같게).
> 운영 방식은 [BUILD_W1_W2 §0](BUILD_W1_W2.md)과 같다: 계약·검토·전체 테스트·커밋은 Claude, 구현은 OpenCode, 물결마다 소유 파일이 겹치지 않는다.

## 1. 계약

### 1.1 표 `customers` (Alembic 0011)

| 칸 | 형 | 설명 |
|---|---|---|
| id | bigint PK | |
| site_key | text | 가게(`sessions.requirement_id`) |
| phone | text | 정규화한 번호(숫자만, `+82` → `0`). `bookings.phone`처럼 평문 — 같은 DB에 암호화 사본을 따로 두지 않는다 |
| name | text null | 마지막으로 적은 이름 |
| first_seen, last_seen | timestamptz | |
| phone_verified_at | timestamptz null | 문자 인증 통과 시각(2물결) |

유일: `(site_key, phone)`. `inquiries.customer_id`, `bookings.customer_id`: bigint null, FK `customers.id` ON DELETE SET NULL, 색인.

### 1.2 `app/services/customers.py`

| 함수 | 계약 |
|---|---|
| `normalize_phone(raw) -> str \| None` | 숫자만 남김. `82`로 시작하고 11~12자리면 앞 `82`를 `0`으로. 결과가 `0`으로 시작하는 9~11자리가 아니면 None |
| `touch(db, site_key, phone_raw, name) -> int \| None` | 번호가 정규화되면 `INSERT … ON CONFLICT (site_key, phone) DO UPDATE SET last_seen = now(), name = COALESCE(EXCLUDED.name, customers.name) RETURNING id`. 안 되면 None. 호출한 트랜잭션 안에서 돈다 |
| `history(db, customer_id) -> dict` | `{"bookings": n, "inquiries": m}` — 그 손님에 붙은 기존 행 수(지금 넣는 행은 빼고 세도록, 붙이기 전에 부른다) |
| `visit_line(hist) -> str` | 둘 다 0이면 `"처음 오신 손님이에요."`, 아니면 `"이 번호로 예약 {n}번·문의 {m}번 있었어요."`(0인 쪽은 뺀다) |
| `purge_orphans(now=None) -> int` | 붙은 문의·예약이 하나도 없고 `last_seen`이 30일 지난 손님을 지운다 |

### 1.3 마감 검사 `availability.slot_taken(db, site_key, visit_date, visit_time, service) -> bool`

- 확정(`confirmed`) 예약만 센다. 정원은 `schedule(card)["capacity"]`(카드는 `_card_for_site`, 없으면 정원 1).
- 카드 구조 데이터에 객실(rooms)이 있으면 박 단위: `service`의 박 수(`_nights_of`)만큼 입실일부터 날마다, 확정 예약이 덮는 수가 정원 이상인 날이 하나라도 있으면 True.
- 아니면 시간 단위: 같은 날짜·같은 `visit_time` 확정 수가 정원 이상이면 True.
- 넘겨받은 `db` 세션으로 읽는다(확정 때 잠금 안에서 부르기 위해).

### 1.4 붙이기 (2물결 C)

| 곳 | 바뀌는 것 |
|---|---|
| `bookings.submit` | 저장 전에 `slot_taken`이면 `BookingError("이미 마감된 시간이에요. 다른 시간을 골라 주세요.")`. 저장 때 `touch` → `customer_id`, 채팅방·카톡 알림 끝에 `visit_line` 한 줄 |
| `bookings.decide` (confirm) | 트랜잭션 안에서 `pg_advisory_xact_lock(hashtext(site_key || ':' || visit_date))` 뒤 `slot_taken`이면 `SlotFull` → API 409 `slot full`, 상태는 그대로 requested |
| `inquiries.submit` | 연락처가 전화번호면 `touch` → `customer_id`, 알림에 `visit_line` |
| `app/main.py` | 시작 때 `customers.purge_orphans()` (문의·예약 삭제 뒤) |

## 2. 물결

### 1물결 (동시에)

| 작업 | 소유 파일 | 완료 확인 |
|---|---|---|
| **M1** 손님 명단 바탕 | `alembic/versions/0011_customers.py`(새), `app/db/models.py`(CustomerRow + customer_id 두 칸만), `app/services/customers.py`(새), `tests/unit/test_customers.py`(새, DB) | 전용 테스트 DB에서 자기 테스트 통과, `tests/engine` 통과 |
| **M2** 마감 검사 | `app/services/availability.py`(`slot_taken`만 추가), `tests/unit/test_slot_taken.py`(새, DB) | 전용 테스트 DB에서 자기 테스트 + `tests/unit/test_availability.py` 통과 |

### 2물결

| 작업 | 소유 파일 | 완료 확인 |
|---|---|---|
| **M3** 붙이기 | `app/services/bookings.py`, `app/services/inquiries.py`, `app/api/bookings.py`, `app/main.py`, `tests/unit/test_bookings.py`, `tests/unit/test_inquiries.py` | §1.4 전부 + 기존 테스트 통과 |

### 3물결 (문자 인증, 계약은 2물결 뒤에 쓴다)

기기 기억 90일 + 인증번호 자동 입력(리서치 §4.2). 문자 대행사 키가 오기 전에는 개발 모드(인증번호를 로그에만).

## 3. 진행 기록

| 물결 | 결과 | Claude 검토 |
|---|---|---|
| 1 (M1·M2) | `customers` 표·0011 마이그레이션·`customers.py` 5개 함수, `availability.slot_taken` | **수정**: 시간 없이 날짜만 받는 예약은 시간 칸이 없어 막지 않음 |
| 2 (M3) | 예약 신청 때 마감이면 거절 + 손님 연결 + 알림에 "처음 오신 손님이에요 / 이 번호로 예약 n번" 한 줄, 확정 때 날짜 잠금 + 마감이면 409 `slot full`(채팅방은 버튼을 남기고 안내), 전화번호 문의도 손님 연결, 시작 때 빈 손님 삭제 | 수용 |

**검증(2026-09-28)**: 전체 817개 통과, `draft_fit` 24건 PASS, `draft_score` 통과.

## 변경 이력

| 날짜 | 내용 |
|---|---|
| 2026-09-28 | 처음 작성 (계약 §1, 물결 3개) |
| 2026-09-28 | 1·2물결 완료 기록 |
