# PM 보고: ReAct 통합 권고안 실행 계획 (REQUIREMENTS_ELICITATION_UX)

> 작성일: 2026-09-23 (PM 관점) / 마감: 2026-09-28 / 코드 수정 없음 (계획 문서만)
> 입력: `REQUIREMENTS_ELICITATION_UX_REACT_REVIEW.md` §5 + 원본 A/B + `backend.py` 실측 + 기존 PM 일정 2종
> 제약 준수: `.env` 미열람, git add/commit/push 없음. 확실하지 않은 것은 **(추정)** 표기.

## TL;DR (PM 요약)

- ReAct 최종 권고의 핵심은 `_process_chat_turn` GATHERING 1턴 직행(`backend.py:731-744` 실측 확인)을 슬롯 기반 점진 질의(결정적 규칙 우선 + 옵션 3개+추천 + 확인요약)로 교체하는 것이며, 마감 전 P0 5항·마감 후 P1 6항으로 이미 우선순위가 분리되어 있다.
- 현 시점은 **D-5** (2026-09-23 18:56 KST 최종 커밋 기준, 마감 09-28까지 5일) — P0 전체를 마감 전 코드로 넣기에는 기존 backend 직렬 큐(⑱ 구현·안정화·버그픽스)와 경합하므로, **P0 중 P0-1~P0-2만 D-3 데모 가능 판정일에 맞추고 나머지는 문서·운영 규칙으로 대체**하는 절충안을 권고한다.
- 기존 PM 일정(`PM_NEXT_STRATEGY.md` 배치 1·2, `PM_PARALLEL_EXECUTION_STRATEGY.md` T-N/T-C/T-D/T-T)과 **트랙 간 병행은 가능하나, backend.py를 건드리는 모든 항목은 T-C 직렬 큐에 합류**해야 하며, ReAct 작업을 별도 병렬 코드 트랙으로 돌리면 머지 충돌·상태머신 회귀가 발생한다.
- PRD 작성자용으로 신규 요구사항 20건을 추출했다 (§5): 세션 상태 필드 6종, 신규 헬퍼 3개, UX 컴포넌트 6종, 스키마 개정 후보 2건 등 — PRD는 이 목록을 요구사항 ID로 그대로 인용하면 된다.
- 착수 순서는 세션 확장(S0) 설계 메모 → `update_slots`/`next_question` 스펙 → GATHERING/AWAIT/QUOTED 전이 스펙 → RAG 래핑·fast-track 문구 확정 순이며, 전부 **다음 작업 세션에서 문서 선행 → 코드 1세션 직렬** 원칙을 따른다.

---

## 1. 시점 확정 (D-day 실측)

- `git log -1`: `30bddec 2026-09-23 18:56:20 +0900` (PM 병행실행전략 문서 추가).
- 현재 UTC 2026-09-23 09:59 = KST 18:59. 마감 2026-09-28 → **잔여 D-5~D-0, 약 5일** (`PM_NEXT_STRATEGY.md`·`PM_PARALLEL_EXECUTION_STRATEGY.md`의 "D-5" 표기와 일치).
- ReAct 리뷰 §5.2의 "마감 전 필수(P0) 5항 / 마감 후(P1) 6항" 구분은 이 D-5 전제를 그대로 쓴 것이므로 유효하다. 단, 그 사이(9/23 18:56 커밋)에 ⑱ 설계 완료·외부접속 이슈 격리(T-N)라는 신규 변수가 추가됐으므로, P0 착수 판단은 §4에서 재조정한다.

## 2. ReAct 최종 통합 권고안 요약 (코드 실측 대조 완료)

아래는 ReAct §5.1(S0~S6) + §5.2(P0/P1)를 PM 집행 단위로 재정리한 것이다. 코드 위치는 본 보고서 작성 시점에 직접 열어 확인했다.

### 2.1 바꿀 위치 (실측 확인)

| ID | 내용 | 코드 위치 (실측) | 상태 |
|---|---|---|---|
| S0 | 세션 확장 (`slots`, `slots_assumed`, `pending_question`, `asked_keys`, `ask_count`, `self_check`) | `backend.py:815` `SESSIONS.setdefault` (현재 `state`+`requirement_id`만) + `save/load_sessions` 자동 직렬화 | 미구현 (grep 0건 — ReAct 검증과 일치) |
| S1 | `update_slots()` 신규 헬퍼 (결정적 규칙만, LLM 없음) | 신규 (backend.py 내 상태머신 밖) | 미구현 |
| S2 | `next_question()` 신규 헬퍼 (1개 기본·최대 2개, 옵션 3개+추천) | 신규 | 미구현 |
| S3 | `self_check_nim()` 신규 헬퍼 (`call_nim` 재사용, 전이당 1회, 실패 시 `{"ok": true}` 폴백) | 신규. `call_nim`+`NIM_TIMEOUT_SEC=25`(`backend.py:30-31` 실측) 재사용 | 미구현 |
| S4 | GATHERING 분기 교체 (fast-track → 첫 진입 RAG 1회+질문 잔류 → 점진 질의 → required 충족 시 확인요약+self-check 후 게이트) | `backend.py:731-744` (rag 1회→`last_request=원문`→즉시 AWAIT 실측 확인) | 현행 1턴 직행 |
| S5a | AWAIT 승인 시 슬롯 조립값 전달 | `backend.py:746-756` (`build_quote(last_request 원문)` 실측) | 원문 의존 |
| S5b | 거절 시 항목별 복귀 (AWAIT+QUOTED 공통, 슬롯 유지) | `backend.py:757-759` (AWAIT 거절→GATHERING 리셋), `backend.py:790-792` (QUOTED 거절→GATHERING 리셋) 실측 | 둘 다 "처음부터 다시" 결함 (ReAct §Thought 3-7a 지적대로 AWAIT뿐 아니라 QUOTED도) |
| S5c | QUOTED 진행 시 `platform`/`features` 슬롯값 교체 + DONE 후 슬롯 초기화 | `backend.py:773-774` (`render_design(id,"web",[원문])` 고정 실측), `backend.py:784` (`start_codegen(...,last_request)` 실측), `backend.py:794-796` (DONE→GATHERING) | 하드코딩 + 초기화 규칙 없음 |
| S6 | 공유방 최소 추가 (`pending_question`+`seq` 귀속, 질의중 투표바 숨김, `ASKING` 표시) | `backend.py:76-77,604-605` (방→세션 1개 공유), `:626-645` (과반투표), `room.html` `#statusBar`·`voteBar`·`updateActionBars` (B 실측 인용) | 미구현 |
| RAG 래핑 | `rag_precheck` 반환 사람말 템플릿화 | `backend.py:188` (`f"기존 프로젝트: {top['source']}"`) + `:739` 그대로 채팅에 붙임 — 실측 확인 | 내부 파일명 노출 중 |

스키마 실측: BND-3 required=`requirement_id, confirmed_items, platform(web|android), acceptance_criteria` (`gate_to_spec.schema.json:6`); BND-1 required=`requirement_id, confirmed_items, customer_id` (`gate_to_quote.schema.json:6`); BND-2 required=`requirement_id, platform, features, quote{amount,basis}` (`quote_to_design.schema.json:6`). ReAct "B 합집합 표 정확" 판정과 일치. `customer_id` 필드는 현 세션에 없음 → 신규 설계 타당.

### 2.2 P0 (마감 전 필수 5항 — ReAct §5.2 원문 유지)

1. S1+S2+S4 게이트 조건 (required 3종: `platform`·`features≥1`·`existing_ref`) — REQ-VALIDATE/ASK DoD 핵심.
2. 확인요약(확정/(가정) 구분) + S5 하류 교체 (`platform`/`features`) — BND-2/BND-3 위반 해소.
3. fast-track 명시 키워드 ("그냥 진행/충분해/빨리/견적 먼저" → platform 확보 후 즉시 게이트 + 생략 전제 명시).
4. 거절 시 항목별 복귀 (AWAIT+QUOTED) + 슬롯 유지 — REQ-GATE-001 충족.
5. RAG 파일명 사람말 래핑 (5줄 템플릿 수준).

### 2.3 P1 (마감 후 6항 — ReAct §5.2 원문 유지)

6. S3 self-check 2차망. 7. 스마트디폴트 고도화. 8. 암묵신호+thorough 모드. 9. 타이머 에스컬레이션. 10. `platform` 배열화 스키마 개정. 11. 임계값 튜닝 (상한 3회·300자·불릿 4개 — 전부 **(추정)**).

## 3. 착수 계획 (1인 프로젝트 → "다음 작업 세션" 단위)

원칙: **문서 선행 → 코드 1세션 직렬**. ReAct 작업물은 전부 `backend.py` 단일 파일을 건드리므로 병렬 코드 세션을 열지 않는다 (§4 규칙 인용).

| 순서 | 세션 | 산출물 (파일) | 내용 | 선행 조건 | 소요 (추정) |
|---|---|---|---|---|---|
| 1 | 다음 세션 A (문서, 즉시 착수 가능) | `docs/hackathon/ELICIT_SLOTS_SPEC.md` (신규) | S0 슬롯 테이블 확정: 6슬롯 키·상태 4값·required 하드조건(`platform·features≥1·existing_ref`)·선택(`budget_or_time`·`acceptance`)·`customer_id=세션/방 대표` 정의. ReAct §5.4의 "(추정) 팀C 합의 필요" 항목을 합의 대기 태그로 명시 | 없음 (T-D/T-T 문서와 병행 가능) | 0.5일 |
| 2 | 다음 세션 A 연계 (문서) | 동일 파일 부록 | S1 결정적 규칙표 (platform 키워드, features 불릿·쉼표+`partial` 패턴, budget 숫자+단위) + S2 질문 템플릿 4종 (platform 닫힌형·features 예/아니오 쪼개기·budget 예시값·확인요약 형식) + fast-track 키워드 4개 + RAG 사람말 템플릿 1개 | 순서 1 | 순서 1에 포함 |
| 3 | 다음 세션 B (문서, A와 병행 가능) | `docs/hackathon/ELICIT_TRANSITION_SPEC.md` (신규) 또는顺序 1 파일 §2부 | S4 전이 순서도 (fast-track→첫 진입→점진→확인요약→self-check 위치) + S5 AWAIT/QUOTED/DONE 분기별 교체 diff 초안 (행번호 지정: `:731-744`, `:746-761`, `:763-792`, `:794-796`) + S6 공유방 `pending_question`+`seq` 규칙 | 순서 1 | 0.5일 |
| 4 | 코드 세션 C (D-4~D-3, 직렬 큐 합류) | `backend.py` 1차분 | P0-1+P0-2+P0-5만 구현: S0 setdefault + S1/S2 헬퍼 + S4 분기 + 확인요약 + 하류 교체 + RAG 래핑. self-check·fast-track·항목복귀는 제외 (아래 §4 절충안) | 순서 1~3 문서 + T-C 큐 순서 (§4) | 0.5~1일 |
| 5 | 코드 세션 D (D-3 이후 여유 있을 때만) | `backend.py` 2차분 | P0-3 fast-track + P0-4 항목복귀. 없으면 운영 규칙(데모 시나리오에서 거절 경로 시연 제외 선언)으로 대체 | 순서 4 + 리허설 결과 | 0.5일 |
| 6 | 마감 후 백로그 | — | P1 6항 전체 (self-check→스마트디폴트→타이머→스키마 개정 순) | 마감 후 | 별도 산정 |

제외하지 않은 것: P0-5(RAG 래핑)는 코드 5줄 수준이라 순서 4에 포함해도 큐에 부담 없음.

## 4. 기존 PM 일정과의 충돌/병행 판정

### 4.1 판정 요약

| 기존 작업 | ReAct 작업과의 관계 | 판정 |
|---|---|---|
| T-N 네트워크/외부접속 해결 | 파일 겹침 없음 (읽기전용 검증·인프라) | ✅ 병행 가능. 순서 1~3 문서 세션과 동시 가동 |
| T-D 데모 준비 (스크립트·Q&A·슬라이드·백업영상) | 파일 겹침 없음 (신규 문서) | ✅ 병행 가능 |
| T-T 팀B 템플릿 스펙 (variant-2~N) | 파일 겹침 없음 (스펙 문서 단계) | ✅ 병행 가능. 단 배선 단계(`render_design` 배선)는 backend 공유이므로 ReAct 순서 4·5와 직렬 |
| T-C 코드 큐: ① OCI curl 버그픽스 → ② 세마포어+캐시+좀비정리 → ③ ⑱ 최소구현 | 전부 `backend.py` 단일 파일. ReAct 순서 4·5도 동일 파일 | ❌ **직렬 필수 — ReAct 코드를 T-C 큐 맨 뒤(③ 다음, 4번째)로 편입**. `PM_NEXT_STRATEGY.md` §3-1 "backend.py를 건드리는 모든 코드 수정은 순차 필수" 규칙 그대로 적용 |
| `PM_NEXT_STRATEGY.md` 배치 1 (B1-a OCI e2e 읽기전용 + B1-b ⑱ 설계 + B1-c 템플릿 스펙 + B1-d STATUS) | B1-a 읽기전용 검증 + B1-b/B1-c 문서는 ReAct 문서 세션(순서 1~3)과 파일이 다름 | ✅ 병행 가능 |
| 배치 2 (B2-1 버그픽스 → B2-2 템플릿 배선 → B2-3 ⑱ 구현) | ReAct 순서 4·5와 동일 파일 경합 | ❌ **직렬 — ReAct는 B2-3 다음(B2-4)으로 편입** |
| D-2(9/26) 코드 동결 · D-1 리허설만 · D-0 제출 | ReAct P0 전체(5항)를 D-2까지 다 넣으면 동결 원칙과 충돌 | ⚠️ **절충: P0 중 P0-1·P0-2·P0-5만 D-3 데모 판정일에 맞추고, P0-3·P0-4는 문서+운영 규칙으로 D-3을 넘기고 여유 있을 때만 구현** |

### 4.2 왜 P0 전체가 아니라 절충안인가 (PM 판단 근거 3개)

1. **큐 길이**: T-C에 이미 3개(버그픽스·안정화·⑱구현, 각 0.5~1일 추정)가 줄 서 있다. ReAct P0 5항(0.5~1일 추정)을 전부 앞에 넣으면 ⑱(유일 미착수 정식 요구)가 D-2 동결을 넘길 위험이 있다. 정식 DoD 미달(⑱ 없음)보다 UX 개선 미흡(GATHERING 거칠음)이 심사 감점이 작다는 판단 — **(추정)** (심사 배점 미공개이므로).
2. **데모 노출도**: P0-1·P0-2(질문 루프+확인요약+시안/견적 정상화)는 정상 경로(관객이 반드시 보는 흐름)에 노출되지만, P0-3·P0-4(fast-track·반려 복귀)는 분기 경로(시연자가 유도해야 보이는 흐름)라 스크립트·운영 규칙(예: "반려 경로는 Q&A에서 구두 설명")으로 커버 가능하다.
3. **회귀 위험**: S4·S5는 상태머신 전이를 직접 바꾸므로, D-2 이후에 손대면 전체 e2e 재검증(1:1+room 양쪽)을 다시 해야 한다. D-3までに P0-1·P0-2를 고정하고 동결하는 편이 리허설 안정성에 유리하다.

### 4.3 반영 후 일정 (D-5 기준, 기존 일정 유지 + B2-4 추가)

| 일자 | 할 일 (기존 + ReAct 태그) | 종료 조건 |
|---|---|---|
| 9/23 잔여 (D-5) | T-N 착수 + T-D 스크립트 v0 + T-T 스펙 + **[ReAct 순서 1~3 문서 착수]** | ReAct 슬롯·전이 스펙 초안 |
| 9/24 (D-4) | T-C ①② + **[ReAct 문서 완료·합의 대기 태그 확정]** | 로컬 선행검증 + ReAct 스펙 리뷰 완료 |
| 9/25 (D-3) | T-C ③ ⑱구현 + **[ReAct 순서 4 (P0-1·P0-2·P0-5)]** + 오후 리허설 1회 | 데모 가능 판정 (막힘 0건) |
| 9/26 (D-2) | 전체 e2e + **코드 동결**. [ReAct 순서 5는 동결 전 여유 있을 때만, 없으면 스킵] | 동결 + 백업영상 |
| 9/27 (D-1) | 리허설 + 버그픽스만 | 백업영상 완성 |
| 9/28 (D-0) | warmup 후 제출 | 제출 |

## 5. PRD 작성자용 신규 요구사항 목록 (ReAct 개선이 만들어내는 것)

PRD 작성자는 아래 ID를 그대로 인용하면 된다. 출처는 ReAct §5.1 S0~S6.

### 5.1 신규 세션 상태 필드 (REQ-ELICIT-STATE)

| ID | 필드 | 타입·초기값 | 용도 | 건드리는 코드 |
|---|---|---|---|---|
| REQ-ELICIT-STATE-01 | `session["slots"]` 6키 (`platform`, `features`, `existing_ref`, `customer_id`, `budget_or_time`, `acceptance`) | `{status: empty\|partial\|filled\|confirmed, value, note}` | 슬롯 축적·게이트 판정·확인요약 렌더 | `SESSIONS.setdefault` 마이그레이션 (`backend.py:815`) |
| REQ-ELICIT-STATE-02 | `session["slots_assumed"]` | dict (추정값+출처) | 확인요약·`basis`에 "(가정)" 표기 | 동상 |
| REQ-ELICIT-STATE-03 | `session["pending_question"]` | `{slot, options, seq} \| None` (단일화) | 공유방 질문-답변 매칭, 중복질문 금지 | 동상 + room 경로 |
| REQ-ELICIT-STATE-04 | `session["asked_keys"]` | list | 중복 질문 방지·thorough 복귀 시 재사용 | 동상 |
| REQ-ELICIT-STATE-05 | `session["ask_count"]` | int, 상한 3 **(추정)** | 무한질의 안전밸브, 초과 시 잠정확정 후 게이트 | 동상 |
| REQ-ELICIT-STATE-06 | `session["self_check"]` | JSON 로그 \| None (P1) | 감사·재현성 (REQ-QUOTE-001) | 동상 |

### 5.2 신규 API·함수 (REQ-ELICIT-FUNC)

| ID | 함수 | 시그니처 (제안) | LLM 사용 | 비고 |
|---|---|---|---|---|
| REQ-ELICIT-FUNC-01 | `update_slots(slots, user_text)` | `-> slots` | 없음 (정규식·키워드만) | B안 우선 원칙 (TEAM_A_SPEC §4 "LLM 판정 금지") |
| REQ-ELICIT-FUNC-02 | `next_question(slots)` | `-> str \| None` | 없음 (템플릿) | 옵션 3개+추천, 한 턴 1개 기본·최대 2개 **(추정)** |
| REQ-ELICIT-FUNC-03 | `self_check_nim(slots_summary)` (P1) | `-> {"ok": bool, "missing": [...]}` | `call_nim` 재사용, 전이당 1회, 실패 시 `{"ok": true}` 폴백 | 과잉지적 가드 (사소한 것 금지·missing 최대 2건) |
| REQ-ELICIT-FUNC-04 | `build_quote` 입력 변경 (본체 무수정) | `build_quote(슬롯 조립 텍스트)` | 기존 유지 | S5a. 추정 전제는 `basis`에 "(가정)" 기록 |
| REQ-ELICIT-FUNC-05 | `render_design`·`start_codegen` 입력 변경 (본체 무수정) | `platform=슬롯값`, `features=confirmed_items` | — | S5c. `"web"` 고정·`[원문]` 해소 |

### 5.3 신규 UX 컴포넌트·문구 (REQ-ELICIT-UX)

| ID | 컴포넌트 | 내용 | 건드리는 면 |
|---|---|---|---|
| REQ-ELICIT-UX-01 | 점진 질문 메시지 | "지금까지 요약 + 다음 질문" 2단 + 진행률 `(n/m)`, 300자·불릿 4개以内 **(추정)** | `/chat`·room 공통 reply |
| REQ-ELICIT-UX-02 | 확인요약 (게이트 전) | 확정값 vs (가정) 구분 표기 + "진행/수정" 분기. 예: `웹(확정) / 예약·결제(확정) / 알림톡(가정·제외 전제) (3/4). 이대로 견적 낼까요?` | AWAIT 전이 직전 |
| REQ-ELICIT-UX-03 | fast-track 분기 | 키워드 `그냥 진행/충분해/빨리/견적 먼저` → platform 확보 후 즉시 게이트 + 생략 전제 명시 | S4-1 |
| REQ-ELICIT-UX-04 | 항목별 복귀 질문 | `1번 기능 2번 플랫폼 3번 예산/일정 4번 기타(자유서술→재추출 입력)` 4지선다, 자유서술 직확인 금지 | AWAIT+QUOTED 거절 공통 |
| REQ-ELICIT-UX-05 | RAG 사람말 템플릿 | `비슷한 ○○ 프로젝트가 있었어요. 확장/신규 중 어느 쪽인가요?(1/2)` — 내부 source명 노출 금지 | `rag_precheck` 호출부 |
| REQ-ELICIT-UX-06 | 공유방 질의 바 (P1 범위 포함) | 질의중 투표바 숨김·투표중 질의입력 분리, `ai_status` 재사용 또는 `ASKING` 1종 추가 **(추정·프론트 1줄)** | `room.html` `updateActionBars` |

### 5.4 스키마·계약 개정 후보 (REQ-ELICIT-SCHEMA, 마감 후)

| ID | 내용 | 근거 |
|---|---|---|
| REQ-ELICIT-SCHEMA-01 | `platform` 배열화 (웹+앱 둘 다) — BND-2·BND-3 `enum [web, android]` 개정 | 현 단일값 전제 유지, 1차는 단일선택+전제명시로 대응 (ReAct P1-10) |
| REQ-ELICIT-SCHEMA-02 | BND-3 `acceptance_criteria` 생성 규칙 (기능별 "~가 가능" 템플릿 + NIM 다듬기) | A §3.1-3 제안, P1-7 범위 |

### 5.5 DoD 매핑 (ReAct §5.3 인용 — PRD 수락 조건으로 전환)

REQ-INTAKE-001→S0+`note`; REQ-VALIDATE-001→S1+S4; REQ-ASK-001→S2; REQ-GATE-001→S5; REQ-QUOTE-001→S5+`self_check` 로그; REQ-RAG-001→첫 진입 1회+폴백+래핑.

## 6. 리스크·미확정 항목 (추정 명시)

1. required 하드조건(`platform·features≥1·existing_ref`)은 ReAct 절충 제안 **(추정)** — 팀C 합의 후 확정 (순서 1 문서에 합의 대기 태그).
2. "1개 기본·최대 2개/턴", "상한 3회", "300자·불릿 4개"는 UX 일반론 **(추정)** — 파일럿 로그 후 튜닝 (P1-11).
3. `platform` 단일값·`budget_or_time` 선택 취급의 "둘 다" 수요 빈도는 **(추정)** — 로그 후 스키마 개정 판단.
4. NIM 지연 체감 (`NIM_TIMEOUT_SEC=25` 실측)은 폴백으로 완화하나 실측 전 확정 불가 **(추정)** — 호출 상한(턴당 1회·전이당 1회)으로 규율.
5. DONE 후 슬롯 초기화·`asked_keys` 수명·"네"의 답변/투표 경계 판별은 신규 제안 **(추정)** — 방 로그로 검증 필요.
6. 본 계획의 공수(문서 0.5+0.5일, 코드 0.5~1+0.5일)는 기존 PM 문서 인용 **(추정)** — 심사·재작업 버퍼 미포함.
7. P0-3·P0-4를 운영 규칙으로 대체할 경우 심사 질의 대비 멘트(데모 스크립트 Q&A에 1문 추가)가 필요 — T-D 트랙에 전달.

## 부록. 읽은 것 / 안 읽은 것

- 읽은 것: ReAct 리뷰 전체(207행) + A(149행) + B(274행) 전부, `backend.py:689-805`·`:225-256`·`:175-188`·`:815` 실측, 세 스키마 required 실측, `PM_NEXT_STRATEGY.md`·`PM_PARALLEL_EXECUTION_STRATEGY.md` 전부, `git log` D-day 대조.
- 안 읽은 것: `.env` (제약), `static/room.html` 원문 (B·ReAct의 인용을 신뢰 — `#statusBar`·`voteBar`·`updateActionBars` 존재 주장은 재검증하지 않았으므로 PRD 작성 시 1회 실측 권장), TEAM_A/B/C_SPEC 원문 (ReAct의 인용을 신뢰).
