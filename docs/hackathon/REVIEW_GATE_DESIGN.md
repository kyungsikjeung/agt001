# ⑱ 사람 최종 검토 게이트 (REQ-REVIEW-001) 설계 문서

> 작성일: 2026-09-23 / 1차 완성 목표: 2026-09-28 / 상태: 설계만 (코드 미수정)
> 관련 요구: `REQ-REVIEW-001` (유일 미착수 정식 요구) / 선행 힌트: `PM_NEXT_STRATEGY.md` "최소 범위: 순번표 + approved 강제 규칙 + 반려 기록 방식"
> 제약: `.env` 미열람, git add/commit/push 없음. 확실하지 않은 것은 "(추정)" 표기.

## 0. 요약 (TL;DR)

- **지금 문제**: `backend.py`의 `GENERATING → done` 분기(`_process_chat_turn`, 703~713행 부근 — 추정 아님, 실측)가 `deploy_generated_site()` 호출 직후 곧바로 `session["state"] = "DONE"`으로 보내고 `deploy_url`을 응답에 싣는다. 즉 **BND-5(배포→검토)와 BND-9(검토→전달)가 코드에 존재하지 않고**, `approved` 없이 최종 링크가 나간다 → `REQ-REVIEW-001` DoD 1번("approved 아니면 DELIVER 절대 실행 금지") 및 `REQ-DELIVER-001` DoD("rejected 배포는 어떤 경로로도 전송 금지", "최종이 시안보다 먼저 나가는 경우 0건") 위반 상태.
- **설계 핵심 (최소 변경안)**: `DONE`으로 바로 가는 대신 새 중간 상태 `REVIEW_PENDING`을 하나 추가하고, 배포 URL 노출(`deploy_url` 응답 포함)을 **승인 API가 호출된 뒤로** 미룬다. 반려 시에는 기존 실패 경로와 똑같이 `QUOTED`로 되돌려 "진행" 재시도를 재사용한다.
- **승인자**: 1인 초기 개발이므로 다인원 순번표는 운영하지 않는다. **사용자(=대표 1인) 본인이 검토자를 겸임**하는 단일 승인자 모델 + **별도 관리자용 엔드포인트** (`/admin/review`, room 투표와 분리)를 권장한다. room 과반투표(§4.2)와 연결하지 않는다 — 이유는 §2 참고.
- **공수 추정**: **하** (0.5~1일, 추정). 새 파일 1개(관리자 페이지) + `backend.py` 약 40~60줄 수정 + 수동 테스트 2케이스로 끝난다.

---

## 1. 요구사항 실체 확인 (조사 결과)

### 1-1. REQ-REVIEW-001 DoD (REQUIREMENTS.md §6, 원문 인용)

| # | DoD | 의미 |
|---|---|---|
| 1 | `approved` 상태가 아니면 `REQ-DELIVER-001`이 절대 실행되지 않는다 (구조적으로 강제, PARALLEL_2_SPEC §1) | 코드 경로상으로 막아야 함. "운영으로 조심한다"는 불합격 |
| 2 | 반려 사유가 기록되어 재작업하는 병렬작업 3가 참고할 수 있다 | `reason` 필드 + 조회 수단 필수 |
| 3 | 순번표가 확정되어 "검토자가 없어서 멈추는" 상황이 없다 | 1인 체제에서는 "순번표 = 대표 본인 상시 대기"로 대체 가능 (아래 §2) |

- Input: `REQ-DEPLOY-001` 출력 (BND-5). Output(통과): `{ requirement_id, review_status: "approved", deploy_url }` (BND-9) → `REQ-DELIVER-001`. Output(반려): `{ requirement_id, review_status: "rejected", reason }` (BND-9) → `REQ-BUILD-001` 재작업 트리거.
- 상세: "핵심 화면 로드 · 핵심 기능 1개 동작 · 에러 없음 3항목 확인. 문제 발견 시 빌드(REQ-BUILD-001)로 되돌아간다."

### 1-2. 파이프라인 위치 (ARCHITECTURE.md §1, §2)

```
⑯ BUILD → ⑰ DEPLOY → [BND-5] → ⑱ 사람 최종 검토 → [BND-9 approved] → ⑪ DELIVER(전송)
                                          └─ [BND-9 rejected] → ⑯ BUILD (재작업)
```

- ⑱은 어느 서브그래프(PAR_1·2·3)에도 속하지 않는 **유일한 사람 수동 단계**. 전담 에이전트 없음.
- §2 시퀀스 20~22번: 플래너가 검토자에게 "배포본 최종 검토 요청" → 통과 시 챗봇 게이트웨이로 "배포 완료 + 접속 링크 통지" → 반려 시 코드생성 에이전트에 "재작업 지시 (18번으로 복귀)".
- 현행 `backend.py`에는 이 20~22번에 해당하는 코드가 **없다** (실측 — `grep review/approve` 결과, room 투표 외 승인 경로 0건).

### 1-3. 입출력 계약 (이미 정의됨 — 실물 확인)

| 계약 | 파일 | 내용 (실측) |
|---|---|---|
| BND-5 (⑰→⑱) | `contracts/deploy_to_review.schema.json` | `required: [requirement_id, status]`, `status: "ready" \| "failed"`, `deploy_url`은 ready일 때만 존재. `additionalProperties: true` |
| BND-9 (⑱→⑪) | `contracts/review_to_deliver.schema.json` | `required: [requirement_id, review_status, reviewer, checked_at]`, `review_status: "approved" \| "rejected"`, `deploy_url`은 approved일 때만, `reason`은 rejected일 때 필수(관례). **`additionalProperties: false`** |

- **계약은 이미 완성돼 있으므로 새로 만들 필요가 없다.** 구현은 이 두 스키마를 그대로 따르면 된다.
- 주의: BND-9는 `additionalProperties: false`이므로 필드를 추가하려면 `PM_ORCHESTRATION.md` §5 거버넌스상 **스키마 변경 승인(PR + 상대 작업자 리뷰)이 먼저 필요**하다. 본 설계는 **필드 추가 없이** 기존 필드만으로 구현하므로 스키마 변경이 불필요하다 (아래 §3).
- 예시 파일: `contracts/examples/*review*.example.json` 존재 여부 — (추정) `PM_ORCHESTRATION.md` §2에서 "예시 9종 생성"이라 주장하므로 approved/rejected 예시가 있을 것으로 보이나, 본 설계 작업에서 예시 파일 목록은 재확인하지 않음. 구현 전 `ls contracts/examples/` 로 1분 확인 권장.

### 1-4. 순번표 관련 기존 기록

- `INTEGRATION_STRATEGY.md` §2 맨 끝에 요일별 1차/2차 표 존재 (월·목=병렬작업 1 / 화·금=병렬작업 2 / 수·토·일=가용자 / 발표 당일=3명 전원 대기). 단, 본문에 "이 표는 예시 배정이다 — D0 당일 아침 반드시 교체"라고 명시 → **실명 미기재 상태의 플레이스홀더** (추정: 교체된 적 없음).
- `PM_ORCHESTRATION.md` §2 findings #3에서 동일 문제를 지적 ("실제 이름·요일이 들어간 표는 어디에도 없었다")하고 §4 D0 게이트에 "검토 순번표를 실제 이름으로 교체"를 포함시켰으나, **1인 체제에서는 이 표 자체가 과도**하다 (§2에서 대체).
- `PM_NEXT_STRATEGY.md` 힌트: "최소 범위: 순번표 + approved 강제 규칙 + 반려 기록 방식" + "구현은 생략 가능, 설계+운영 규칙은 필수" (P1 설계 필수 / P2 최소 구현은 D-2에 맞추지 못하면 사람이 직접 눈으로 확인하는 운영으로 대체 가능). 본 문서는 그 P1 설계 산출물이다.

---

## 2. 승인자 결정 방식 (권장안: 대표 1인 + 별도 관리자 엔드포인트)

### 2-1. 판단: room 과반투표와 연결하지 않는다

`room_chat()` (backend.py 626~645행)에는 이미 ⑦ 승인 게이트용 과반투표(`approve_n > total/2`)가 있다. ⑱를 여기에 얹는안(예: room 참여자 중 누군가 "최종승인" 입력 시 통과)도 가능해 보이지만 **비권장**한다:

1. **의미 혼동**: ⑦ 투표는 "견적을 진행할까"이고 ⑱ 승인은 "배포물을 고객에게 보내도 되는가"이다. 같은 `"승인"` 문자열·같은 `room["votes"]` 딕셔너리를 공유하면, ⑦ 투표 잔재가 ⑱ 판정에 섞이는 버그가 생긴다 (현재 `room["votes"] = {}` 초기화는 ⑦ 통과 시 1회뿐).
2. **권한 문제**: room 참여자는 고객(외부인) 포함이다. 고객이 "최종승인"을 누르면 검토 게이트가 무력화된다. ⑱ 승인권은 내부자(대표)에게만 있어야 한다.
3. **상태 꼬임**: room은 하나의 `session_id`를 공유하므로, ⑱ 투표 대기 중에 다른 참여자가 일반 메시지를 보내면 `_process_chat_turn`이 `REVIEW_PENDING` 상태를 어떻게 처리할지 분기가 복잡해진다.

### 2-2. 권장안

- **승인자 = 대표 1인 (고정값)**. BND-9의 `reviewer` 필드에는 `"owner"` 고정 문자열을 넣는다. 순번표는 아래 운영 규칙 1줄로 대체한다:
  > "⑱ 검토자 = 대표 본인. 부재 시 배포 링크를 고객에게 구두/수동으로 전달하지 않고, 복귀 후 승인 API로 처리한다. 시연 당일(9/28)은 시연 10분 전 워밍업과 함께 승인 대기 건 0건임을 확인한다."
- **승인 수단은 room과 완전히 분리된 관리자용 엔드포인트**로 둔다 (아래 §4). 인증은 최소 수준(아래 §4-3)으로 충분 — 평가 시연용이 아니라 내부 프로세스이므로 화려한 로그인/권한 체계는 만들지 않는다.
- 기존 요일별 순번표(`INTEGRATION_STRATEGY.md` §2)는 **1인 체제에서 폐기**하고, 본 문서 §2-2의 1줄 규칙으로 대체함을 명시한다. (문서 정합성용 메모 — 계약 변경이 아니라 운영 규칙 변경이므로 PR 승인 불필요, 추정.)

---

## 3. 데이터 모델 (SESSIONS 상태머신 최소 변경안)

### 3-1. 현행 상태머신 (backend.py 실측)

- 상태 저장: `SESSIONS[session_id]` dict, `state` 값: `GREETING → GATHERING → AWAIT_APPROVAL → QUOTED → GENERATING → DONE`.
- 재시작 복구: `load_sessions()` (68~69행)에서 `GENERATING`만 `QUOTED`로 되돌림. 그 외 상태는 그대로 복구.
- 코드생성 완료 분기: `_process_chat_turn()` 내 `state == "GENERATING"` 분기 (698~725행):
  - `codegen["status"] == "done"` → `deploy_generated_site()` → **`state = "DONE"` + `deploy_url` 저장 + reply에 링크 포함** (704~713행). ← **게이트 삽입 지점**
  - `"unavailable"` → `state = "DONE"` (배포 없음, 시안만 안내).
  - `timeout/error/no_files_created` → `state = "QUOTED"` + "다시 '진행'을 보내 재시도" (723~725행). ← **반려 시 재사용할 경로와 동일 패턴**.
- 배포 URL 노출 지점 (전부 게이트 뒤로 옮겨야 함):
  1. `_process_chat_turn` GENERATING-done reply 본문 (711행 `배포 링크: ...`).
  2. `/chat` 응답 `payload["deploy_url"]` (819~822행, `state == "DONE"` 조건).
  3. `/room/<id>/messages` 응답 `"deploy_url": session.get("deploy_url")` (683행) — room 폴링이므로 고객 노출 경로.
  4. (참고) `design_url_unsent` 패턴 (778, 823~827행) — 시안 링크 1회성 전달 선례. 검토 승인 링크도 동일 패턴 재사용 권장.

### 3-2. 변경안 (신규 상태 1개 + 필드 2개)

| 변경 | 내용 |
|---|---|
| 신규 상태 | `REVIEW_PENDING` (GENERATING과 DONE 사이). 값 문자열은 대문자 스네이크 기존 관례 준수 |
| 신규 필드 | `session["pending_deploy_url"]`: 승인 전까지 고객에게 노출하지 않는 실제 URL 보관. `session["review"]`: `{ status: "pending"\|"approved"\|"rejected", reviewer, reason?, checked_at? }` (BND-9와 동형, `additionalProperties` 추가 없이 그대로 사용) |
| 기존 필드 재사용 | `session["deploy_url"]`: **승인된 URL만** 담는다 (의미 변경: "배포된 URL" → "승인되어 공개 가능한 URL"). 반려·대기 중에는 키를 두지 않거나 `None` |

상태 전이:

```
GENERATING (codegen done)
  → REVIEW_PENDING   [deploy_generated_site() URL을 pending_deploy_url에 보관, deploy_url은 세팅하지 않음]
  → REVIEW_PENDING -- [POST /admin/review/approve] --> DONE (deploy_url = pending_deploy_url, review.status=approved)
  → REVIEW_PENDING -- [POST /admin/review/reject + reason] --> QUOTED (review.status=rejected 기록 유지, "진행" 재시도)
```

- `unavailable` 분기(714~722행)는 산출물 자체가 없으므로 검토 대상이 없음 → 현행대로 `DONE` 직행 유지 (검토 게이트 적용 제외).
- `load_sessions()` 복구 규칙 추가: `REVIEW_PENDING`은 백그라운드 작업과 무관하므로 **그대로 복구** (GENERATING처럼 QUOTED로 되돌리지 않는다 — 승인 대기 중 재시작해도 대기 유지). 단, `pending_deploy_url`은 `GENERATED_DIR` 실물 기준이므로 재시작 후에도 유효 (정적 서빙이라 무효화 없음).
- room `ai_status` 매핑: `REVIEW_PENDING` 동안 `room["ai_status"] = "REVIEW_PENDING"` (신규 문자열). 기존 `ai_status`는 자유 문자열(IDLE/GENERATING/DONE 등)이므로 스키마 변경 불필요. 프론트(`static/room.html`)는 알 수 없는 문자열을 "대기 중"으로 표시하면 됨 — 표시 문구만 추가 (추정: 현재 room.html에 ai_status별 분기가 하드코딩돼 있다면 1줄 추가 필요, 미확인).

### 3-3. BND-5/BND-9 대응 (스키마 변경 없음)

- BND-5: `deploy_generated_site()` 반환 `{deploy_url}` + `codegen["status"]` → `{ requirement_id, status: "ready", deploy_url }`로 매핑해 `session["review"]` 대기 레코드로 보관. `status: "failed"`(빌드 실패)는 현행 `QUOTED` 복귀 경로와 동일 취급 — 즉 **빌드 실패는 사람 검토를 거치지 않고 자동 반려 취급** (`INTEGRATION_STRATEGY.md` §2 병렬작업 3 "자동으로 반려되는지" 확인 항목과 일치).
- BND-9: 승인/반려 API가 호출될 때 `{ requirement_id, review_status, reviewer: "owner", reason?, checked_at: _now_iso(), deploy_url? }`를 구성해 **서버 로그 1줄 + `session["review"]`에 그대로 저장**한다. 별도 전송 큐는 없음 — 병렬작업 2 최종 링크 발송이 현재 카카오 API가 아니라 "프론트가 `deploy_url`을 받아 카카오 공유 버튼을 띄우는" 방식(backend.py 820~827행 주석)이므로, **BND-9 ≒ "`deploy_url`을 응답에 싣는 조건"** 으로 구현된다 (§4-2 강제 규칙 참고). `additionalProperties: false`이므로 여분 필드 추가 금지.

---

## 4. 삽입 위치 + API + UI (파일명·함수명 수준)

### 4-1. 코드 삽입 위치 (backend.py)

1. **`_process_chat_turn()` GENERATING-done 분기 (현재 703~713행)**: `session["state"] = "DONE"` 1줄을 아래로 교체 —
   ```python
   # 변경 후 (의사코드)
   deploy = deploy_generated_site(session["requirement_id"])
   session["state"] = "REVIEW_PENDING"
   session["pending_deploy_url"] = deploy["deploy_url"]
   session["review"] = {"status": "pending", "reviewer": "owner",
                        "checked_at": None, "reason": None}
   reply = ("코드 생성이 완료됐습니다! 내부 검토 대기 중입니다.\n"
            f"- 생성된 파일: {files_list}\n"
            "- 배포 링크는 사람 최종 검토(⑱) 승인 후 공개됩니다.")
   ```
   `deploy_url`을 reply에 포함하지 않는다 (DoD 1 강제의 핵심).
2. **`_process_chat_turn()` 말미 room 매핑 (798~803행)**: `session["state"] == "DONE"` → `ai_status = "DONE"` 기존 분기에 `REVIEW_PENDING → "REVIEW_PENDING"` 1줄 추가.
3. **`/chat` 응답 (819~827행)**: `payload["deploy_url"]` 조건을 `state == "DONE"`에서 `"DONE" and session.get("review", {}).get("status") == "approved"`로 강화 (이중 잠금 — 아래 §4-2 규칙 A).
4. **`/room/<id>/messages` (677~686행)**: `"deploy_url": session.get("deploy_url")`를 승인된 경우에만 내려주도록 조건화 (규칙 A의 room 쪽).
5. **신규 엔드포인트** (backend.py 맨 끝, `/chat` 정의 부근에 추가 — 함수명 제안):
   - `GET /admin/review/pending` (`list_pending_reviews()`): `state == "REVIEW_PENDING"`인 세션 목록 `{requirement_id, pending_deploy_url, created 미리보기}` 반환. 관리자 페이지용.
   - `POST /admin/review/approve` (`approve_review()`): body `{requirement_id}` → 해당 세션을 `DONE`으로, `deploy_url = pending_deploy_url`, `review.status = "approved"`, `checked_at = _now_iso()` 기록. BND-9 approved 로그 1줄 출력.
   - `POST /admin/review/reject` (`reject_review()`): body `{requirement_id, reason(필수, 빈 문자열 거부)}` → `review.status = "rejected"` + `reason`·`checked_at` 기록 후 **`state = "QUOTED"`** (기존 "진행" 재시도 경로 재사용, §5). `pending_deploy_url`은 유지 (재검토 대비)하되 `deploy_url`은 세팅하지 않음.
   - 상태 검증: `REVIEW_PENDING`이 아닌 세션에 approve/reject가 오면 `409 Conflict` ("검토 대기 상태가 아님") — 실수 이중 승인 방지.
6. **`load_sessions()` (67~70행)**: `REVIEW_PENDING`은 손대지 않음 (주석 1줄 추가만).

### 4-2. approved 강제 규칙 (DoD 1의 "구조적 강제")

두 겹으로 잠근다 (둘 다 코드 조건이므로 운영 주의가 아닌 구조):

- **규칙 A (노출 차단)**: 고객 접점 응답(`/chat` payload, `/room/.../messages`, GENERATING-done reply)에 `deploy_url` 실URL이 포함되는 조건을 `review.status == "approved"`와 AND로 묶는다. 승인 전에는 `pending_deploy_url` 키 이름 자체가 달라서 기존 `session.get("deploy_url")` 조회에 걸리지 않는다 (키 분리 = 실수 노출 방지).
- **규칙 B (순서 보장)**: 시안 링크(`design_url_unsent` 1회성 패턴)는 현행 유지 + 최종 링크는 승인 후 첫 `/chat` 폴링/`/messages` 폴링에서만 내려준다. 즉 "시안 응답 → (시간차) → 승인 후 최종 응답" 순서가 코드상으로 강제되어 `REQ-DELIVER-001` DoD "최종이 시안보다 먼저 나가는 경우 0건"을 만족한다.
- 검증 방법: 승인 없이 `/chat` 폴링·`/site/<id>/` 직접 추측 접속을 해도 되는가? — `/site/<id>/` 정적 서빙(538~547행)은 URL을 알면 열리는 구조이므로, **"추측 불가성"은 `requirement_id` 8자리 랜덤에 의존**한다 (추정: 현행 `str(uuid.uuid4())[:8]`). 승인 전 URL을 reply·payload 어디에도 싣지 않으면 고객은 URL을 모른다. 관리자 페이지에서 URL을 직접 여는 것은 검토 행위 자체이므로 허용. (완전한 비공개가 필요하면 나중에 토큰 쿼리 추가 — 마감 후 백로그.)

### 4-3. 최소 UI (내부용, 1페이지)

- **신규 파일 1개**: `static/review.html` (버튼 몇 개짜리 관리자 페이지. 화려하게 만들지 않는다).
  - 내용: `GET /admin/review/pending` 목록 테이블 (requirement_id, 배포 URL 미리보기 링크, "승인" 버튼, "반려" 버튼 + 사유 텍스트박스). 승인 시 체크박스 3개(핵심 화면 로드 / 핵심 기능 1개 동작 / 에러 없음 — REQUIREMENTS DoD 상세의 3항목)를 **모두 체크해야 승인 버튼이 활성화**되도록 한다 (`INTEGRATION_STRATEGY.md` §1 BND-9 규칙의 "체크박스 3개 통과해야 approved" 구현).
  - 인증 최소안: 쿼리 파라미터 `?token=` + 서버 환경변수 `ADMIN_REVIEW_TOKEN` 1개 비교 (값은 hosting 대시보드에만 설정, 레포·문서에 기재 금지). 토큰 불일치 시 `403`. (추정: 현행 backend.py에 인증 미들웨어 없음 — 신규 5줄이면 충분.)
- 반려 사유 기록 UI: 반려 버튼 옆 `<input>` 1개 (필수 입력, 빈 값이면 API가 400). 저장 위치는 `session["review"]["reason"]` + `generated/rooms.json`·세션 파일과 같은 원자적 저장(`save_sessions()` 기존 함수 재사용).

---

## 5. 반려 시 재작업 흐름 (QUOTED 복귀 + 기존 재시도 재사용)

```
REVIEW_PENDING -- reject(reason 필수) --> QUOTED -- "진행" --> GENERATING --> REVIEW_PENDING ...
```

1. `reject_review()`가 `state = "QUOTED"`로 되돌린다. 이는 **기존 코드생성 실패 경로(723~725행)와 동일한 복귀점**이므로, 고객이 "진행"을 보내면 `QUOTED` 분기(763~789행)가 시안 재생성 → `start_codegen()` → `GENERATING`으로 가는 **검증된 경로를 그대로 재사용**한다. 신규 재시도 로직을 만들 필요가 없다.
2. 반려 사유는 두 곳에 남는다: (a) `session["review"] = {status: "rejected", reason, checked_at}` — 병렬작업 3(≒대표 본인)가 다음 "진행" 전에 `/admin/review/pending`에서 확인. (b) room이 있으면 시스템 메시지로 `_room_append(room, "system", "시스템", f"검토 반려: {reason} — '진행'으로 재시도해 주세요.", kind="system")` 1줄 (선택, 3줄 추가).
3. 재시도 횟수 제한은 두지 않는다 (마감 5일 체제에서 제한 로직은 과도). 단, 동일 `requirement_id`로 3회 연속 반려되면 스펙 자체를 의심하고 고객 요구로 되돌아갈 것 — 운영 메모로 관리자 페이지 하단에 1줄 표기.
4. BND-5 `status: "failed"`(빌드 실패, 산출물 없음)는 사람 검토 없이 `QUOTED` 직행 유지 (현행 723행 그대로) — "자동 반려"로 간주하고 `review.status = "rejected (auto: build failed)"`를 기록만 한다 (선택).

---

## 6. 최소 구현 공수 추정 (1차 완성 목표 2026-09-28 기준)

| 작업 | 내용 | 공수 (추정) |
|---|---|---|
| backend 상태 1개 + 필드 2개 | §4-1 항목 1~2, 6 (≈20줄) | 1~2시간 |
| 승인/반려/목록 API 3개 + 강제 규칙 2개 | §4-1 항목 3~5 (≈30줄) + 토큰 5줄 | 2~3시간 |
| `static/review.html` 1페이지 | 목록 + 승인(체크박스 3개) + 반려(사유 필수) | 1~2시간 |
| 테스트 2케이스 | (a) 승인 없이 deploy_url 노출 0건 (b) 반려→QUOTED→"진행" 재시도 1회 | 1시간 |
| **합계** | | **0.5~1일 → 작업량 "하"** |

- 스키마 변경 없음 → `PM_ORCHESTRATION.md` §5 계약 승인 절차 불필요.
- `backend.py` 단일 파일 직렬화 제약(`PM_NEXT_STRATEGY.md` §3-1: backend 수정은 순차 필수)에 따라 OCI 버그픽스(B2-1)·템플릿 배선(B2-2)과 **같은 배치에 넣지 말고 그 다음 순서(B2-3)로** 실행한다.
- 구현 생략 시 폴백 (PM_NEXT_STRATEGY P2 명시): 설계+운영 규칙(본 문서 §2-2 1줄 + 체크박스 3항목을 종이/메모로 확인)으로 데모 가능. 단 이 경우 DoD 1 "구조적 강제"는 미달이므로 평가 질의 대비 멘트("현재는 운영 게이트, 구조적 강제는 D+α 패치 예정") 준비 필요.

---

## 부록. 구현 체크리스트 (그대로 이슈로 옮겨 쓸 수 있음)

- [ ] `_process_chat_turn` GENERATING-done → `REVIEW_PENDING` + `pending_deploy_url` 보관, reply에서 실URL 제거
- [ ] `/chat`·`/messages`의 `deploy_url` 노출 조건에 `review.status == "approved"` AND 추가
- [ ] `POST /admin/review/approve`, `POST /admin/review/reject(reason 필수)`, `GET /admin/review/pending` + `ADMIN_REVIEW_TOKEN` 검사
- [ ] `static/review.html` (체크박스 3개 + 승인/반려 버튼)
- [ ] 반려 → `QUOTED` 복귀 + 사유 기록 확인, "진행" 재시도 1회 실측
- [ ] 승인 없이 최종 링크가 나가지 않음을 `/chat`·room 양쪽에서 실측 (DoD 1 증빙)
