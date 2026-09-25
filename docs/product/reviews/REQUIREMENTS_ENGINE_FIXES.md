# 요구사항 엔진 결함 수정 기록 (E1) — REQUIREMENTS_ENGINE_FIXES

> 작업일: 2026-09-26 / 기준: `REQUIREMENTS_ENGINE_VERIFICATION.md`(B-1~B-16), `tests/engine/test_verification.py` 31개
> 수정 파일: `app/services/prd_engine.py`, `app/services/chat_flow.py`(B-1 빈 메시지 분기만)
> 결과: **tests/engine 31/31 통과**, tests/unit/test_prd_engine.py **14/14 통과**
> (단, unit은 작업 폴더 alembic 불량으로 `--noconftest` 우회 실행 — §5 참조)

## 1. 결함별 수정 내용

| ID | 수정 (파일:함수) | 내용 |
|---|---|---|
| B-1 | `chat_flow.py:process_turn` 빈 메시지 분기 | 상태별 유지로 변경. `GREETING`→인사+`GATHERING`, `GATHERING`→엔진 `turn(card,"")`으로 현재 질문 재송신(예산 미소모), `AWAIT_APPROVAL`→"승인 또는 거절로 답해주세요.", `QUOTED`→"이 견적으로 진행할까요? (진행/취소)", `DONE`→완료 유지(재시작 안 함). `GENERATING` 폴링(`get_messages` 빈 호출)은 그대로 최우선 |
| B-2 | `prd_engine.py:_answer_pending` multi | `NONE` 판정을 "정규화 후 메시지 전체가 없음 계열"로 한정. 고른 항목이 하나라도 있으면 선택을 먼저 살리고 없음 말은 무시 ("주차는 되는데 나머지는 없음"→parking 유지) |
| B-3 | `_answer_pending` multi + `NEG_NORMS` | 라벨(표시명·`·` 앞부분) 매칭 후 앞뒤 8자(정규화 기준)에 부정 패턴(`안돼/못해/없어/아니/별로/싫/불가/빼/제외` 등)이 있으면 제외. 한 글자 부분일치는 오탐(`안내`) 때문에 쓰지 않음 ("주차는 안 돼요"→미선택) |
| B-4 | `turn` + `_stuck_key`/`_assume_slot` | 빈 메시지는 예산 미소모·같은 질문 유지. 추출·규칙 모두 빈손인데 정규화 후 5자를 넘는 실내용이면 잡담으로 보고 예산 미소모·같은 질문 재송신. 5자 이하 짧은 답·감탄사(`음`)는 답 시도로 보고 예산 소모(§3 판단 ①). 진전 없는 턴은 칸별 stuck을 세어 3회째에 가정(사실·가게이름은 자리 표시)으로 두고 다음 칸으로 (`INTAKE_GATE_DESIGN.md` §5). 방장 확인 대기는 엔진에서 해소 불가라 stuck 대상에서 제외 |
| B-5 | `_norm_text`/`grounded`/`apply_updates` | `unicodedata NFKC`(전각→반각) + `app/services/stt.py`의 `normalize_digits`(한글 숫자→아라비아, 재사용 import)를 근거 판정과 사실 저장 전에 적용. 한글 전화는 `010-1111-2222` 형태로 저장돼 `grounded`를 통과 |
| B-6 | `_norm`/`_fuzzy_option_match`/YES·NO·LATER·SKIP | 비교 전 소문자·NFKC·공백/문장부호/이모지 제거. 단일 선택지는 정규화 동등 → 10자 이하 짧은 답의 선택지 포함(`전화요`→`전화`) → 선택지 낱말 포함 순으로 완화. 방장 확인은 `YES` 대소문자 무시, `네, 맞아요` 같은 혼합 공손답을 승인으로(거절 우선 판정). `알아서 해줘/알아서`→`알아서` 포함으로, `넵/네네/ㅇㅇ/웅/그래/오케이` 등 추가. 건너뛰기는 정규화 부분일치+`건너뛰/시안보여/먼저보여/패스/스킵` 추가 ("건너뛰고 시안 보여줘"→마무리). `chat_flow`/`rooms`의 승인·투표 단어 대조는 소유 밖이라 손대지 않음(§2 판단 ④) |
| B-7 | `_answer_pending` 거절 분기 + `apply_updates` exclude→REJECTED 연결 | `필요없/없어도…`(NEEDLESS)면 언급 칸(라벨 토큰 매칭, 없으면 대기 칸)을 `REJECTED`로. `빼주세요/제외`(REMOVE) 계열은 칸 이름이 함께 있을 때만 거절로 보고, 항목 제거는 추출 `exclude` 흐름에 맡긴다 ("바비큐는 빼주세요"가 대기 칸 거절이 되지 않게). `exclude` 값이 칸 라벨 자체면(예: `가격`) 해당 칸 `REJECTED`. 사실 칸 거절은 D23의 공개 전 "이 항목 빼기"로 해석해 허용 (§3 판단 ②). `next_question`·요약은 이미 `REJECTED`를 제외하므로 추가 변경 없음 |
| B-8 | `turn` | 방장 확인 대기 중 같은 칸의 방장 자유 대답(추출 적중)은 대기값을 새 값으로 갱신하되 상태를 `PENDING_OWNER`로 되돌려 확인 질문을 유지한다. 다른 칸 대답은 기존 우선순위(`PENDING_OWNER` 최우선)가 이미 확인 질문을 살린다 |
| B-11 | `next_question` 숨은 항목 | 표시 선택지를 상위 3개+없음(합계 4개, 조사 #9)으로. 판정 매칭은 전체 목록으로 해서 안 보인 항목을 말해도 인식된다 (§3 판단 ③) |
| B-12 | `apply_updates` + `_answer_pending` + `_refresh_assumed_sections` | `business_type` 반영으로 업종이 바뀌면 상태가 `ASSUMED`인 `sections`만 새 업종 기본값으로 교체. 사장님 직접 입력(`FILLED`)은 유지 |
| B-13 | `_clean_exclude_term` | `빼주세요/제외…` 접미사·조사·앞머리 감탄사(`아 ,`)를 벗겨 핵심어만 남긴다 ("바비큐는 빼주세요"→"바비큐"). 이후 기존 부분일치 제거가 동작 |
| B-16 | `apply_updates` 주석 | 부분일치 제거("바비큐"→"바비큐장" 제거)는 의도로 확정하고 주석으로 명시. 동작 변경 없음(기존 통과 테스트 유지) |

## 2. 테스트 기대와 계획이 어긋난다고 판단한 것 (테스트 미수정, 판단만 기록)

① **B-4 잡담 기준 — 5자 휴리스틱.**
`tests/unit/test_prd_engine.py::test_question_cap_is_eight`(반복 `음`으로 8회 상한 도달)와
`tests/engine` 잡담 테스트(긴 잡담은 예산 미소모)는 문자 그대로 양립하지 않는다.
판단: 5자 이하 짧은 답은 질문에 대한 답 시도로 보고 예산을 소모하고, 그보다 긴데도 추출·규칙에 안 걸리면
주제 이탈(잡담)로 보고 예산을 쓰지 않는다. 어느 쪽도 무한 반복은 stuck 3회 가정(§1 B-4)으로 끊는다.
`음`→소모, `오늘 날씨가 좋네요`→미소모, 빈 메시지→미소모가 모두 이 기준으로 통과한다.
더 principled한 잡담 분류(의도 분류기 등)는 T3 시뮬레이션(A2) 결과로 갈음할 일이다.

② **B-7 사실 칸 REJECTED 허용.**
D23은 사실을 자리 표시+공개 전 필수로 두지만, 같은 행에 "빈 자리를 채우거나 '이 항목 빼기'"를 둔다.
이 "빼기"를 `REJECTED`(요약·시안에서 숨김)로 해석했다. 공개 단계에서 `REJECTED` 사실 칸을
"빼기로 확정"으로 보여줄지는 공개 단계(엔진 범위 밖)에서 정할 일이다.

③ **B-11 숨은 항목 4·5번째.**
표시는 상위 3개+없음이지만 판정은 전체 목록이라, 말로 하면 4·5번째 항목도 선택된다.
버튼에만 없는 항목은 접근성이 떨어지므로, 사용 빈도가 보이면 순서 조정 또는 2페이지 분할을 후속으로 검토한다.

④ **B-6 승인·투표 단어(`chat_flow.py` APPROVE/REJECT/PROCEED, `rooms.py` VOTE_WORDS).**
검증이 지적한 대로 여전히 정확 일치다. 소유 파일 제한(B-1만)으로 손대지 않았고,
버튼 눌림이 그대로 전달되는 한 1:1·공유방의 정상 흐름은 깨지지 않는다. 후속 작업에서
엔진과 같은 `_norm` 비교로 완화할 것을 권장한다(버튼 값은 정규화해도 동일하므로 회귀 위험 낮음).

## 3. 남은 것 (소유 밖·범위 밖)

| ID | 내용 | 필요한 작업 |
|---|---|---|
| B-9 | 방장 확인 장기 미해결·방장 소실 | `rooms.py` 소유 밖. 방장 재지정(남은 멤버 중 최초 입장자 자동 승계) 또는 `owner_confirm` 3턴 타임아웃 후 과반 승인 폴백을 방 쪽에 구현해야 한다. 엔진은 `owner_confirm`를 stuck 대상에서 제외하고 계속 묻는 상태다 |
| B-10 | 견적 D25 배치 | `quote.py`·`chat_flow.py` 승인 흐름 소유 밖. 규칙 계산 1줄+베타 무료 문구로 교체 필요 |
| B-14 | `GREETING→AWAIT_APPROVAL` 전이 이벤트 | 죽은 전이(`_TRANSITION_EVENTS`)이나 무해하므로 유지. 정리 시 `chat_flow.py`에서 제거 |
| B-15 | 템플릿 시작 미연결 | 방 생성 시 `template_id`→`new_card(업종)` 배선. `chat_flow.py` 호출부(`new_card()` 무인자) 변경 필요 |
| P5/P9 | 첫 메시지 점수·매 턴 재계산 | 미구현 유지(고정 `required` 순서). 조사 #3 항목으로 후속 설계 필요 |
| P7 | 확인형 질문 | 미사용 유지(`test_confirm_shape_never_used` 통과 조건). 도입 시 질문 상한·예산과 함께 설계 |
| P14 | 의견 엇갈림 나란히+투표 | 마지막 말 덮어쓰기 유지. A7 실측 후 D24 후반 구현 여부 결정 |
| B-4 잔여 | 잡담 2턴 넛지("사이트 이야기로 돌아갈까요?") | 엔진은 같은 질문 재송신까지만 하고 문구 넛지는 붙이지 않았다. 필요하면 `chat_flow.py` 표시 단계에서 `trace`를 보고 덧붙인다 |

## 4. 테스트 결과

- `tests/engine`: **31/31 통과** (수정 전 15/31)
  `NIM_API_KEY=x DATABASE_URL=postgresql+psycopg://agt001:agt001@localhost:55432/agt001_test
  …/agent_project/.venv/bin/python -m pytest -q tests/engine -p no:cacheprovider`
- `tests/unit/test_prd_engine.py`: **14/14 통과**
- 실제 NIM 호출 없음(가짜 `chat_json`만), `.env` 미열람, 소유 외 파일 무수정, git 조작 없음.

## 5. 비고: tests/unit 전체 미실행 사유

`tests/unit/conftest.py`의 세션 autouse 픽스처(`db_migrate.upgrade_head()`)가 작업 폴더의
alembic 히스토리 불량(`Can't locate revision identified by '0005'`)으로 실패한다.
엔진 수정과 무관한 사전 결함이다(수정 파일은 `prd_engine.py`·`chat_flow.py`뿐, `git status` 확인).
DB 자체(55432)는 연결된다. 이에 엔진 단위 파일만 `--noconftest`로 분리 실행해 14/14을 확인했다.
alembic 히스토리를 고치는 것은 소유 밖이므로 손대지 않았다.
