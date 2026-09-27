# PRD — 요구사항 도출( elicitation ) UX 개선 (GATHERING 상태)

> 작성일: 2026-09-23 / 작성자: 작업자(기획 문서 담당, PM 지시 수행)
> PM 지시: `docs/hackathon/REQUIREMENTS_ELICITATION_UX_REACT_REVIEW.md`(ReAct 자문 리뷰)의 요청사항을 하나도 빠짐없이 PRD 형태로 정리
> 범위: GATHERING 상태 개선 (대화·요구사항 도출 UX). 코드 수정 없음(본 PRD는 설계 문서).
> 1차 완성 목표: 2026-09-28
> 근거 우선순위: (1) 원본 A/B/ReAct 문서 최우선, (2) 스키마 실측값, (3) `docs/hackathon/REQUIREMENTS.md` 스타일 준용.
> 참고: PM 지시문에 언급된 `docs/hackathon/PM_REACT_PLAN_REPORT.md` 파일은 리포에 존재하지 않음(2026-09-23 glob 실측). 따라서 본 PRD는 A/B/ReAct 원본 3종을 근거로 작성했으며, PM 보고서 요약이 아님.

## 0. 스타일·스키마 기준 (실측)

- 본 PRD의 REQ 서술 형식은 `docs/hackathon/REQUIREMENTS.md` §0(요약 / 요약 상세 / Input / Output / 완료 조건(DoD) / Description)을 그대로 재사용하고, PRD용으로 `우선순위`·`마감 전/후`·`출처` 3개 필드를 추가한다.
- REQ-ID 네이밍은 `REQ-<영역>-<번호>` 패턴을 따라 `REQ-ELICIT-<번호>`를 사용한다.
- 스키마 실측값 (PRD에서 "이 필드가 바뀐다/추가된다" 서술의 근거):
  - BND-3 `contracts/gate_to_spec.schema.json`: required=`requirement_id, confirmed_items, platform, acceptance_criteria` / `platform` enum=`web|android` / `additionalProperties: true`.
  - BND-1 `contracts/gate_to_quote.schema.json`: required=`requirement_id, confirmed_items, customer_id` / `additionalProperties: true`.
  - BND-2 `contracts/quote_to_design.schema.json`: required=`requirement_id, platform, features, quote{amount, basis}` / `platform` enum=`web|android` / `additionalProperties: true`.
  - `additionalProperties: true`이므로 세션·페이로드 확장은 스키마 개정 없이 가능하다. 단, `platform` 복수값(웹+앱)은 enum 단일값이므로 개정이 필요하면 마감 후 과제(REQ-ELICIT-021)로 둔다.

---

## 1. 개요 (이 PRD가 다루는 범위 — GATHERING 상태 개선)

현 `backend.py:731-744`의 GATHERING은 `rag_precheck` 1회 후 원문 그대로 `AWAIT_APPROVAL`로 직행하므로(후속 질문 루프 0회), ④접수·⑤검증·⑥질의가 생략되고 `platform="web"` 고정·`features=[원문 1건]`으로 BND-2/BND-3 필수값이 무너진다(A §1.1, B §0.1, ReAct §1). 본 PRD는 이 진단을 전제로, ReAct 리뷰 §3(A 자문 7항)·§4(B 자문 7항)·§5(통합안 S0~S6, P0/P1 11항)와 원본 A/B의 세부사항을 하나도 빠짐없이 요구사항으로 전환한다. 처방 코어는 "빠진 것만 되묻기 + 선택형(옵션 3개+추천) + 승인 시 슬롯 조립값 하류 전달 + 반려 시 해당 항목 복귀"이며, 수단은 "B의 결정적 체크리스트를 게이트로, A의 NIM 추출·스마트디폴트·fast-track을 가속기로, B의 self-check는 폴백 첨부 2차망으로" 결합한다(ReAct §1-4).

---

## 2. 출처 대조표 (A/B/ReAct에서 나온 모든 제안 — 원문 요약 + 출처)

> 이 표가 "빠짐없이"의 출발 체크리스트다. §4에서 각 행이 어느 REQ-ID로 매핑됐는지 1:1로 검증한다.

### 2.1 ReAct §3 — A에게 주는 자문 7항

| 대조ID | 제안 원문 요약 | 출처 |
|---|---|---|
| C-A1 | NIM-우선 순서를 규칙-우선으로 뒤집기. 1차 판정은 키워드·정규식 결정적 규칙, NIM 추출은 2차 보완. B §1.2의 4상태(`empty\|partial\|filled\|confirmed`)+규칙표가 출발점 | ReAct §3-1, B §1.2, PARALLEL_1_SPEC §4, REQ-VALIDATE-001 |
| C-A2 | 매턴 NIM 호출의 지연·비용 가드 정량화. `NIM_TIMEOUT_SEC=25` 하에서 "GATHERING 턴당 최대 1회, 실패 시 현행 동작 폴백", 1차는 규칙만으로 다음 질문 선정 | ReAct §3-2, A §2 방법1, B §3.2 |
| C-A3 | 스마트디폴트 환각 대책을 B 3층 구조에. `assumed` 표기 유지 + 추정값은 `basis`·확인요약에 "(가정)" 표기 + 승인 전 self-check 1회 재검증. 고위험 슬롯 제외(A §3.2) 유지 | ReAct §3-3, A §2 방법3·§3.2 |
| C-A4 | required 집합을 스키마 역산으로 고정. 게이트 하드조건은 `platform + features≥1 + existing_ref 확정 + customer_id(대표)`로 좁히고 예산/일정은 선택질문으로. 병렬작업 3와 합의 | ReAct §3-4, B §1.1, A §3.2 |
| C-A5 | RAG 내부 파일명 노출 수정. `rag_precheck` 반환(`SRS-2025-014.md` 등)을 그대로 붙이는 현행(`backend.py:739`) 대신 사람말 템플릿("비슷한 ○○ 프로젝트가 있었어요. 확장/신규 중 어느 쪽인가요?(1/2)")으로 감싸기 | ReAct §3-5, B §2.4 |
| C-A6a | 공유방 보완. B §2.5의 `pending_question` 단일화 + `seq` 인용 귀속 + 질의중 투표바 숨김 수용 | ReAct §3-6, B §2.5 |
| C-A6b | QUOTED/DONE 리셋 통일. 거절 복귀는 AWAIT(`:757-759`)뿐 아니라 QUOTED(`:790-792`)·DONE 후 재입장(`:794-796`)까지 "해당 슬롯으로 복귀, 슬롯 유지·`asked_keys` 재사용"으로 통일 | ReAct §3-6, A §1.1-4, B §0.1-5, ReAct Thought 3-7a·7b |
| C-A7 | 질문 상한 + 게이트 일괄확인. B의 "상한 3회(조정가능) 초과 시 잠정확정 후 게이트에서 한 번에 확인"을 안전밸브로 채택, "한 턴 1개(기본)/최대 2개(연관 슬롯 묶음일 때만)" 절충 | ReAct §3-7, A §2 방법2, B §2.1-5 |

### 2.2 ReAct §4 — B에게 주는 자문 7항

| 대조ID | 제안 원문 요약 | 출처 |
|---|---|---|
| C-B1 | fast-track 단축경로 추가. 명시적 키워드(`그냥 진행/충분해/빨리/견적 먼저` → `platform`만 확보 후 확인요약과 함께 즉시 게이트, 생략 전제는 견적 근거에 명시). REQ-GATE-001 "확인 없이 BND-3 금지" 하드 가드 유지. 암묵신호(NIM 보조판정)는 required 생략에 사용 금지 | ReAct §4-1, A §4.1 |
| C-B2 | 스마트디폴트 수용. A §2 방법3의 "추정값 묶음 확인요약 1개 + 맞음 한 마디 확정"을 고위험 제외(플랫폼·예산상한은 추정확정 금지)와 함께 도입 | ReAct §4-2, A §2 방법3 |
| C-B3 | 6슬롯 전체를 게이트 하드조건에 걸지 않기. B §1.2의 "6개 모두 `filled` 이상"은 과도하므로 하드조건은 `platform/features/existing_ref/customer_id`로 좁히고 나머지는 선택·추정확정(A §3.2 등급안과 절충) | ReAct §4-3, B §1.2, A §3.2 |
| C-B4 | `platform` 단일값 전제 예외 경로를 스키마 개정과 묶기. "웹+앱 둘 다" 응답 시 1차는 단일 선택 + 확인요약에 전제 명시, 개정(배열화)은 마감 후 과제로 미루는 2단계 계획 | ReAct §4-4, B §5-3(추정) |
| C-B5 | self-check 가드 고정. B §3.2 대책(사소한 것 지적금지·`missing` 최대 2건·전이당 1회·실패 시 생략·`session["self_check"]` 로그)에 추가: `build_quote` JSON 강제 패턴(`backend.py:233-253`) 재사용, 지적 수용은 "첫 1건만 질문, 나머지는 게이트 확인요약에 (미확인) 표기로 이관" | ReAct §4-5, B §3.1·§3.2 |
| C-B6 | 질문 상한 초과 시 문구 구체화. A §3.1 확인요약 형식(확정값+추정값 구분 표기)을 빌린 예시 1개 고정. 예: `지금까지: 웹(확정) / 예약·결제(확정) / 알림톡(가정·제외 전제) (3/4). 이대로 견적 낼까요? (진행/수정)` | ReAct §4-6, B §2.1-5, A §3.1 |
| C-B7 | 반려 시 "어느 항목" 선택지 4지선다 고정: `1번 기능 2번 플랫폼 3번 예산/일정 4번 기타(자유서술→슬롯 재추출 입력으로만 사용)`. 자유서술 직확인 금지(REQUIREMENTS §9) 한 줄 추가 | ReAct §4-7, B §4.3, A §4.2 |

### 2.3 ReAct §5.1 — 통합 설계 S0~S6

| 대조ID | 제안 원문 요약 | 출처 |
|---|---|---|
| C-S0 | 세션 확장(로직 무변경, `additionalProperties` 허용·`setdefault` 마이그레이션): `slots` 6종(platform required·고위험 / features required ≥1 / existing_ref required / customer_id filled=세션·방대표 / budget_or_time 선택 / acceptance 선택) + `slots_assumed` + `pending_question`{slot,options,seq} + `asked_keys` + `ask_count`(상한 3, 추정·조정가능) + `self_check` | ReAct §5.1-S0, B §4.1 |
| C-S1 | `update_slots(slots, user_text)` 신규 헬퍼, 결정적 규칙만·LLM 없음(B안 우선, A안 2차). platform 키워드 매칭(혼재·전무→partial), features 불릿·쉼표 분리 ≥1개("관리자/통계/알림"+"~도/~있었으면"→partial), existing_ref는 rag 1회+고객 선택 시 confirmed, budget_or_time 숫자+단위 패턴(없어도 게이트 가능). 자유서술은 슬롯에 직접 쓰지 않고 재추출 입력으로만(REQUIREMENTS §9) | ReAct §5.1-S1, B §1.2, A §2 방법1 |
| C-S2 | `next_question(slots)` 신규 헬퍼. 한 턴 1개 기본·최대 2개, 옵션 3개+추천. 순서: platform → existing_ref(RAG hit 시만) → features 쪼개기(예/아니오, confirmed_items 1개 단위) → budget_or_time(선택·"건너뛰셔도 됩니다" 명시). 형태: 닫힌=번호 객관식+추천, 반열린=예/아니오 쪼개기, 열린=예시값 선제시(`300만원대/2주`). 한 응답 300자·불릿 4개 이내(추정). "지금까지 요약 + 다음 질문" 2단 + 진행률 `(n/m)`(B §2.3). RAG source명 사람말 래핑, 노출 금지 | ReAct §5.1-S2, B §2.1·§2.2·§2.3, A §2 방법2 |
| C-S3 | `self_check_nim(slots_summary)` 신규 헬퍼, `call_nim` 재사용·전이당 최대 1회. `{"ok": true}` 또는 `{"ok": false, "missing": [...]}` JSON만 반환. 실패·타임아웃 시 `{"ok": true}` 폴백(검사 생략, 대화 차단 금지). 프롬프트에 "사소한 것은 지적 금지", `missing` 최대 2건 수용·첫 1건만 질문·나머지는 확인요약에 (미확인) 이관 | ReAct §5.1-S3, B §3.1·§3.2 |
| C-S4 | `_process_chat_turn` GATHERING 분기(`backend.py:731-744`) 교체. (1) fast-track 키워드 → platform만 확보(없으면 platform 1문만) 후 확인요약 + AWAIT_APPROVAL, 생략 슬롯은 디폴트+(가정) 표기·견적 basis에 전제 명시. (2) 첫 진입이면 rag_precheck 1회 → existing_ref 후보 기록 → platform 질문 1개만 하고 잔류(게이트 직행 금지). (3) 그 외 update_slots 반영 → 미충족 슬롯 1개 질문 + 요약(ask_count+1). (4) required 충족이면 확인요약(확정/(가정) 구분) → self-check 최대 1회 → ok면 AWAIT_APPROVAL / missing이면 해당 슬롯 복귀(상한 초과 시 잠정확정 후 게이트) | ReAct §5.1-S4, A §3.1·§4.1, B §4.2 |
| C-S5a | 승인 시 슬롯 조립 텍스트(`platform+features+acceptance+budget_or_time+(가정) 전제`)를 `build_quote`에 전달. `build_quote` 본체 무수정 | ReAct §5.1-S5, B §4.3, A §3.3 |
| C-S5b | 거절 시(AWAIT/QUOTED 공통) 슬롯 유지 + "어느 항목을 고칠까요? 1번 기능 2번 플랫폼 3번 예산/일정 4번 기타"로 해당 슬롯만 복귀(처음부터 전체 재질문 금지) | ReAct §5.1-S5, A §4.2, B §4.3 |
| C-S5c | QUOTED 진행 시 `render_design(id, "web", [원문], ...)`(`:773-774`) 고정값을 슬롯값(`platform`, `features`/`confirmed_items`)으로 교체, `start_codegen` 입력도 슬롯 조립 스펙으로 교체. 함수 본체 무수정 | ReAct §5.1-S5, A §3.3, B §4.3 |
| C-S5d | DONE 후(`:794-796`) 새 요청이면 슬롯 초기화 후 GATHERING (신규 규칙, 추정) | ReAct §5.1-S5, ReAct Thought 3-7b |
| C-S6 | 공유방 최소 추가(B안 그대로): `pending_question`+`seq` 인용 귀속, 질의중 투표바 숨김·투표중 질의입력 분리(`updateActionBars`에 질의바 1종 추가), `ai_status` 재사용 또는 `ASKING` 1종 추가(추정·프론트 1줄) | ReAct §5.1-S6, B §2.5·§4.4 |

### 2.4 ReAct §5.2 — 구현 우선순위 P0/P1 (11항, 1차 완성 목표 2026-09-28 기준)

| 대조ID | 제안 원문 요약 | 출처 |
|---|---|---|
| C-P0a | P0-1. S1 `update_slots` + S2 `next_question` + S4 게이트 조건(required 3종) — 1턴 직행 누락을 막는 최소 장치 | ReAct §5.2 |
| C-P0b | P0-2. 확인요약(확정/(가정) 구분) + S5의 `platform`/`features` 하류 교체 — BND-2/BND-3 위반 해소 | ReAct §5.2 |
| C-P0c | P0-3. A §4.1 명시 키워드 fast-track — 마찰 체감 개선 중 최저비용 | ReAct §5.2, A §4.1 |
| C-P0d | P0-4. 거절 시 항목별 복귀(AWAIT+QUOTED) + 슬롯 유지 — REQ-GATE-001 충족 | ReAct §5.2 |
| C-P0e | P0-5. RAG 파일명 사람말 래핑 — 5줄 템플릿 수정 수준 | ReAct §5.2, B §2.4 |
| C-P1a | P1-6. S3 self-check 2차망 — 규칙+질의 안정 후. 단독 도입 시 과잉지적·지연 리스크 | ReAct §5.2, B §3 |
| C-P1b | P1-7. 스마트디폴트 고도화(전 슬롯 추정·`acceptance_criteria` 템플릿+NIM 다듬기) — P0 확인요약의 확장판 | ReAct §5.2, A §2 방법3·§3.1-3 |
| C-P1c | P1-8. 암묵신호(장문·단답연속) 판정 + thorough 모드(한 턴 1항목 늦추기) — 실측 로그 후 조정 | ReAct §5.2, A §4.1-2 |
| C-P1d | P1-9. 타이머 기반 에스컬레이션(reqpipe G12, PARALLEL_1_SPEC §9) — 현 코드에 타이머 없음 확인. 공수 별도 | ReAct §5.2, A §3.1, PARALLEL_1_SPEC §9 |
| C-P1e | P1-10. `platform` 배열화(웹+앱 둘 다) 스키마 개정(BND-2·BND-3) — 1차는 단일선택+전제명시로 대응 | ReAct §5.2, B §5-3 |
| C-P1f | P1-11. 질문 상한·300자·불릿수 등 임계값 튜닝 — 파일럿 대화 로그(A/B) 후 확정 | ReAct §5.2, B §5-1 |

### 2.5 원본 A 고유 세부 (ReAct 요약 외부 — 원본 대조로 추가 발굴)

| 대조ID | 제안 원문 요약 | 출처 |
|---|---|---|
| C-AO1 | 침묵·무응답 시 에스컬레이션은 PARALLEL_1_SPEC §9 + reqpipe G12 개념 준용 (추정: 현 코드에 타이머 없음 — 신규 필요) | A §3.1 |
| C-AO2 | optional 생략 시 디폴트로 확정 + 견적 근거에 "제외 전제"로 기록. "생략된 항목의 디폴트"를 문서화·고지하지 않으면 분쟁 소지. 생략된 optional은 반려 시 다시 꺼낼 수 있게 보관 | A §2 방법4, A §4.2 |
| C-AO3 | 모드 전환 언제든 가능. "아까 생략한 것도 물을게" 한 마디면 thorough로 복귀, `asked_keys` + 보관된 optional 슬롯 재사용 | A §4.2 |
| C-AO4 | fast-track 견적서에는 생략 전제 반드시 노출(예: "관리자 페이지 제외 전제"). `build_quote(slots, assumed_notes)` 확장 방향(추정), 추정 전제는 `basis`에 "(플랫폼: 웹으로 가정)"처럼 기록 | A §3.3, A §4.2 |
| C-AO5 | A 원안 required 초안(추정·작업자 합의 필요): `platform(web\|android)` + `features ≥ 1개(핵심 동사 포함)` + `budget_band 또는 deadline 중 ≥1`. optional: `admin_page 유무, notification 종류, design_tone, rag_reuse_confirmed`(유사 발견 시 required 승격). 고위험(스마트디폴트 제외·선택형으로만): `platform`, `budget 상한` | A §3.2 |
| C-AO6 | 매 GATHERING 턴 누적 대화 전체로 NIM 슬롯 추출(`{platform, features[], budget_limit, deadline, has_admin, rag_reuse_confirmed}`), `slots{}`·`slots_assumed{}`(출처 표기)·`asked_keys[]`(중복 방지) 누적. `last_request` 단일 저장 대신 누적 대화 + 슬롯 함께 보관. NIM 실패 시 현행 동작(원문 게이트)으로 폴백 | A §2 방법1, A §3.1 |

### 2.6 원본 B 고유 세부 (ReAct 요약 외부 — 원본 대조로 추가 발굴)

| 대조ID | 제안 원문 요약 | 출처 |
|---|---|---|
| C-BO1 | B 원안 게이트 조건(기록용·절충 대상): 6슬롯 모두 `filled` 이상일 때만 AWAIT_APPROVAL 전이. `acceptance`(기능당 1개 매핑 권장)와 `budget_or_time`(DoD상 필수 아님) 포함. → 본 PRD는 C-B3 절충안(하드조건 축소)을 채택하고, 본 항은 결의 근거로 보관 | B §1.2 |
| C-BO2 | 자유서술 대응: REQ-ASK-001대로 옵션 3개+추천 재질문, 재질문은 1회로 제한(무한 루프 방지). 그래도 안 맞으면 원문을 `partial` 메모로 붙여 게이트에서 사람이 확인 | B §2.2 |
| C-BO3 | 전문용어 금지: "BND", "acceptance_criteria" 같은 내부어를 사용자에게 노출하지 않는다 | B §2.4 |
| C-BO4 | AI 질문 메시지에 "○○ 슬롯 질문" 라벨 + `room.html` 아바타+닉네임+`BOT` 뱃지 유지로 "누가 무엇에 답해야 하는지" 방 전원이 보게 하기 | B §2.5-4 |
| C-BO5 | room 투표 로직(`backend.py:626-645`)은 그대로 두고 GATHERING 질의 답변은 투표 판정에서 제외 | B §4.3 |
| C-BO6 | 진행률 표시를 `room.html` `#statusBar` 패턴에 재사용 (추정: 프론트 1줄 확장 수준) | B §2.1-4 |
| C-BO7 | `save_sessions()`/`load_sessions()` 직렬화에 자동 포함(저장 로직 변경 불필요). 구 세션(필드 없음)은 `setdefault`로 마이그레이션 | B §4.1 |
| C-BO8 | `rag_precheck`·`build_quote`·`render_design` 본체는 손대지 않는다. 바뀌는 것은 호출 시점과 입력(원문→슬롯 조립값)뿐 | B §4.2 |
| C-BO9 | `acceptance`는 features 각 항목 대응 문장 기계적 카운트. 없으면 질의 생략 가능하되 §3 self-check에서 보완 | B §1.2 |
| C-BO10 | 질문 순서·완화책: 첫 질문은 가장 쉬운 것(`platform`)부터, 예산 같은 민감·추상 질문은 뒤로. 예산/일정은 "건너뛰셔도 됩니다" 명시. 이미 답한 것(`filled`)은 다시 묻지 않음(반려 시 해당 항목만) | B §2.1-1·2·3 |

### 2.7 ReAct §5.3 DoD 매핑·§5.4 추정 (수용 선언)

| 대조ID | 제안 원문 요약 | 출처 |
|---|---|---|
| C-D1 | DoD 닫힘 선언 6건: REQ-INTAKE-001→S0 slots+원문발췌 note / REQ-VALIDATE-001→S1 규칙+S4 required→self-check→게이트 / REQ-ASK-001→S2 형태별 질문+재질문 1회 상한 / REQ-GATE-001→승인 본체 유지+S5 해당 슬롯 복귀 / REQ-QUOTE-001→S5 슬롯 조립 입력+(가정) basis+self_check 로그 / REQ-RAG-001→첫 진입 1회+실패 시 신규 폴백 유지+사람말 래핑 → §3 각 REQ의 DoD·§6 매핑표로 수용 | ReAct §5.3 |
| C-E1 | 추정 5건(미확정으로 수용·§7 기록): required 하드조건 절충(병렬작업 3 합의 후 확정) / "1개·3회·300자·불릿4" 수치(실측 후 확정) / platform 단일·budget 선택 취급("둘 다" 수요 빈도는 추정) / self-check·NIM 추출 지연 체감(실측 전 확정 불가) / DONE 초기화·asked_keys 수명·경계 utterance("네"가 답변인지 투표인지)(방 로그로 검증) | ReAct §5.4 |

---

## 3. PRD 요구사항 목록 (REQ-ELICIT-001 ~ 024)

### REQ-ELICIT-001 — 세션 슬롯 확장 + 영속

- **요약**: 세션에 6슬롯 + 질의 bookkeeping 필드를 추가하고 저장/복원에 포함한다.
- **요약 상세**: `platform`(required·고위험) / `features`(required ≥1) / `existing_ref`(required) / `customer_id`(filled=세션·방 대표) / `budget_or_time`(선택) / `acceptance`(선택) 각 `{status, value, note}` + `slots_assumed`(추정 출처) + `pending_question`{slot,options,seq} + `asked_keys` + `ask_count` + `self_check`를 둔다. BND-3/BND-1/BND-2 스키마가 `additionalProperties: true`이므로 계약 개정 없이 확장 가능하다.
- **Input**: 기존 세션 dict(`state`+`requirement_id`만 있는 구 세션 포함)
- **Output**: 확장 필드를 갖춘 세션. `save/load_sessions` 직렬화에 자동 포함, 구 세션은 `setdefault` 마이그레이션
- **완료 조건 (DoD)**:
  - [ ] 6슬롯 + 5 bookkeeping 필드가 세션에 존재하고 저장 후 복원된다
  - [ ] 구 세션(필드 없음)이 오류 없이 마이그레이션된다
  - [ ] 스키마 required 실측값(BND-3 4종·BND-1 3종·BND-2 4종)과 슬롯 커버리지가 §6 매핑표와 일치한다
- **Description**: 상태값은 `empty|partial|filled|confirmed` 4값. `customer_id`는 BND-1 required이므로 1:1은 session, 공유방은 대표+`approved_by`로 둔다(설계 제안). `requirement_id`는 이미 발급되므로 수집 대상이 아니다.
- **우선순위**: P0 / **마감 전**
- **출처**: C-S0, C-BO7, C-BO1(슬롯 집합), C-D1(INTAKE)

### REQ-ELICIT-002 — 결정적 규칙 `update_slots` (LLM 없음, 규칙-우선)

- **요약**: 사용자 발화를 키워드·정규식 결정적 규칙으로만 슬롯에 반영한다. NIM 추출은 2차 보완이다.
- **요약 상세**: PARALLEL_1_SPEC §4·REQ-VALIDATE-001 "전부 LLM 판단에 맡기지 않는다" 원칙에 따라 1차 판정은 규칙이 맡는다. 규칙은 "확정"이 아니라 "질의 트리거"까지만 담당하고 최종 해소는 질의+self-check 3층 구조로 맡긴다.
- **Input**: `slots` + 당 턴 `user_text`
- **Output**: 갱신된 `slots`(상태 전이만, 질문문 생성 없음)
- **완료 조건 (DoD)**:
  - [ ] `platform`: "웹/홈페이지/사이트"→web, "앱/안드로이드/플레이스토어"→android, 혼재·전무→`partial`
  - [ ] `features`: 불릿·쉼표 분리 ≥1개. "관리자/통계/알림"+"~도/~있었으면" 패턴은 `partial`로 질의행
  - [ ] `existing_ref`: `rag_precheck` 결과 + 고객 확장/신규 선택이 둘 다 있어야 `confirmed`
  - [ ] `budget_or_time`: 숫자+단위(만원·원·주·일) 패턴. 없어도 게이트 가능
  - [ ] 규칙 판정에 LLM 호출이 0회다
- **Description**: A의 "매 턴 NIM 추출 우선"안은 폴백이 있어도 단독 수단으로는 REQ-VALIDATE 원칙과 충돌하므로(ReAct Thought 3-3 검증), B안(규칙 우선)이 스펙 정합성이 높다. 동의어·은유 변형은 규칙이 못 잡을 수 있으므로(추정) 질의 트리거 용도로만 쓴다.
- **우선순위**: P0 / **마감 전**
- **출처**: C-A1, C-S1, C-P0a, C-D1(VALIDATE)

### REQ-ELICIT-003 — NIM 호출 상한·폴백 (지연·500 가드)

- **요약**: NIM 호출(슬롯 추출·self-check 포함)에 횟수 상한과 실패 폴백을 못박아 지연 누적과 500을 막는다.
- **요약 상세**: `NIM_TIMEOUT_SEC=25` 실측 하에서 매턴 추출은 체감 지연을 누적시킨다(A안의 결함, 지연 대책 없음). 1차는 규칙만으로 다음 질문을 고른다.
- **Input**: GATHERING 턴 진입 / 전이 직전 self-check 시점
- **Output**: 성공 시 추출·점검 결과, 실패 시 현행 동작(원문 게이트)·검사 생략으로 폴백
- **완료 조건 (DoD)**:
  - [ ] 슬롯 추출용 NIM 호출은 GATHERING 턴당 최대 1회다
  - [ ] self-check 호출은 전이당 최대 1회다
  - [ ] NIM 실패·타임아웃 시 `/chat` 500 없이 현행 동작(원문 게이트)·검사 생략으로 폴백한다
- **Description**: B §3.2의 "검사 생략 폴백" 패턴을 추출에도 적용한다.
- **우선순위**: P0(상한·폴백 선언) / **마감 전**. 실측 기반 임계값 조정은 REQ-ELICIT-022로 미룬다.
- **출처**: C-A2, C-S3, C-AO6

### REQ-ELICIT-004 — `next_question` (한 턴 1개 기본·옵션 3개+추천)

- **요약**: 첫 번째 미충족 슬롯에 대한 질문 1개를 형태별 템플릿으로 생성한다.
- **요약 상세**: REQ-ASK-001 "옵션 3개+추천 1개, 자유 서술형 금지"를 질문 UI 규칙으로 강제한다. 한 턴 1개가 기본이며 연관 슬롯 묶음일 때만 최대 2개다.
- **Input**: `slots`(미충족 슬롯 존재)
- **Output**: 질문문 1개(옵션 3개+추천 포함)
- **완료 조건 (DoD)**:
  - [ ] 순서: `platform` → `existing_ref`(RAG hit 시만) → `features` 쪼개기(예/아니오, `confirmed_items` 1개 단위) → `budget_or_time`(선택·"건너뛰셔도 됩니다" 명시)
  - [ ] 형태: 닫힌 질문=번호 객관식+추천(예: `1번 웹 2번 안드로이드 — 보통은 1번 웹으로 시작하세요 (추천). 번호만 보내주세요.`), 반열린=예/아니오 쪼개기(`관리자 승인 기능이 필요하신가요? (네/아니오)`), 열린=예시값 선제시(`(예: 300만원대 / 2주)`)
  - [ ] 첫 질문은 가장 쉬운 것(`platform`)부터, 예산 같은 민감·추상 질문은 뒤로 미룬다
  - [ ] 한 응답 300자 이내·불릿 4개 이내(추정·조정가능), "BND"/"acceptance_criteria" 등 내부 전문용어를 사용자에게 노출하지 않는다
  - [ ] 모든 애매 항목에 옵션이 정확히 3개(+추천 1개)다(REQ-ASK-001 DoD)
- **Description**: A의 "최대 2개/턴"은 체감부하 대책으로 유효하나 무한질의 방지 상한이 없으므로 B의 상한과 결합한다(REQ-ELICIT-013). 옵션 설계가 부실하면 의도 왜곡이 생기므로 추천 표시는 필수다.
- **우선순위**: P0 / **마감 전**
- **출처**: C-S2, C-A7, C-BO3, C-BO10, C-P0a, C-D1(ASK)

### REQ-ELICIT-005 — 요약-확인 리듬 + 진행률

- **요약**: 매 질문을 "지금까지 정리 + 다음 질문" 2단 구조로 묶고 진행률을 매번 보여준다.
- **요약 상세**: 사용자는 "내 말이 반영되고 있다"는 피드백을 매 턴 받는다. 슬롯 요약문 누적 표시이므로 구현은 슬롯 테이블 렌더링 1개면 된다.
- **Input**: 당 턴 질문문 + 현재 슬롯 요약
- **Output**: 2단 메시지(예: `지금까지: 웹 / 쇼핑몰(로그인·장바구니·결제) (3/5)\n다음: 관리자 승인 기능도 넣을까요? (네/아니오)`)
- **완료 조건 (DoD)**:
  - [ ] 모든 질의 응답이 "지금까지 요약 + 다음 질문" 2단 구조다
  - [ ] 진행률 `(n/m)`이 매번 표시된다
  - [ ] 진행률 표시에 `room.html` `#statusBar` 패턴을 재사용한다(추정: 프론트 1줄 확장 수준)
- **Description**: REQ-CHAT-001 DoD의 "처리 중 안내"와 같은 맥락으로, 끝이 보이는 대화는 이탈이 적다.
- **우선순위**: P0 / **마감 전**
- **출처**: C-S2, C-BO6, B §2.3

### REQ-ELICIT-006 — 게이트 조건 + GATHERING 분기 교체 (1턴 직행 금지)

- **요약**: `backend.py:731-744`의 "rag→즉시 게이트"를 슬롯 충족 게이트 분기로 교체한다.
- **요약 상세**: 현재 구조의 실패 모드("못 들은 것을 모른 채 넘어감")를 뒤집어, 못 들은 것이 있으면 상태 전이 자체가 막히게 한다.
- **Input**: GATHERING 수신 메시지
- **Output**: 잔류(질문 1개) 또는 required 충족 시 확인요약 후 AWAIT_APPROVAL
- **완료 조건 (DoD)**:
  - [ ] 첫 진입(`pending_question` 없음 + slots 전부 empty)이면 `rag_precheck` 1회 → `existing_ref` 후보 기록 → `platform` 질문 1개만 하고 잔류한다(게이트 직행 금지)
  - [ ] 그 외: `update_slots` 반영 → 미충족 슬롯 1개 질문 + 요약(`ask_count`+1)
  - [ ] 하드조건(`platform` + `features`≥1 + `existing_ref` 확정 + `customer_id` 대표) 충족 시에만 확인요약 → self-check(마감 전에는 생략 가능, REQ-ELICIT-017) → AWAIT_APPROVAL. 하나라도 미충족이면 GATHERING에 잔류한다
  - [ ] 필수 항목이 모두 채워졌으면 질의 없이 바로 게이트로 진행한다(REQ-VALIDATE-001 DoD)
- **Description**: 하드조건을 `platform·features≥1·existing_ref`로 좁히는 것은 절충 제안이며 **(추정)** — 병렬작업 3 합의 후 확정(REQ-ELICIT-024). B 원안 "6슬롯 모두 filled"(C-BO1)는 과도하므로 본 PRD는 축소안을 채택한다.
- **우선순위**: P0 / **마감 전**
- **출처**: C-S4, C-P0a, C-A4, C-B3, C-BO1(결의), C-D1(VALIDATE)

### REQ-ELICIT-007 — 확인요약 (확정/(가정) 구분) + 스마트디폴트 묶음 확인

- **요약**: 게이트 전에 확정값과 추정값을 구분 표기한 확인요약 1개를 제시하고, "맞음" 한 마디로 확정받는다.
- **요약 상세**: "쓰는 노력"(타이핑)을 "읽고 OK하는 노력"으로 바꾼다. A §2 방법3 + B 상한 3회와 충돌 없이 턴을 압축한다.
- **Input**: required 충족 시점의 슬롯
- **Output**: 확인요약 메시지(예: "웹으로(앱 아님) 이해했어요. 알림톡 연동 포함, 관리자 페이지는 제외로 잡았는데 맞나요? (맞음/수정)")
- **완료 조건 (DoD)**:
  - [ ] 확정값과 추정값(`assumed`)이 구분 표기된다(추정값은 "(가정)" 표시)
  - [ ] 고위험 슬롯(`platform`, `budget 상한`)은 추정확정 대상에서 제외하고 반드시 명시적 선택으로 묻는다
  - [ ] 추정 전제는 `basis`에 "(플랫폼: 웹으로 가정)"처럼 기록된다(REQ-QUOTE-001 DoD "근거 없는 견적 금지")
  - [ ] "맞음" 한 마디면 전 슬롯 확정된다
- **Description**: "말하지 않은 내용을 채움" 위험은 `assumed` 표기만으로 부족하므로 확인요약 + 승인 전 self-check 2차망(마감 후)과 묶는다.
- **우선순위**: P0(기본 확인요약) / **마감 전**. 전 슬롯 추정 고도화는 REQ-ELICIT-018로 미룬다.
- **출처**: C-A3, C-B2, C-P0b, C-AO4, A §2 방법3

### REQ-ELICIT-008 — fast-track 키워드 단축경로

- **요약**: 서두르는 사용자의 명시적 신호를 결정적 규칙으로 받아 `platform`만 확보 후 즉시 게이트로 보낸다.
- **요약 상세**: B안은 성실 응답자를 전제로 하며 "빨리" 신호 대책이 "선택질문 건너뛰기" 수준에 머문다. A §4.1의 명시적 키워드가 서두르는 사용자 대책으로 더 구체적이므로 수용한다.
- **Input**: GATHERING 수신 메시지 중 fast-track 키워드(`그냥 진행/충분해/빨리/견적 먼저/대충`)
- **Output**: `platform` 확보(없으면 platform 1문만) 후 확인요약 + AWAIT_APPROVAL
- **완료 조건 (DoD)**:
  - [ ] 키워드 매칭은 결정적 규칙으로 판정한다(PARALLEL_1_SPEC §4 "LLM 판정 금지" 준용)
  - [ ] 생략된 슬롯은 디폴트 + 견적 근거에 전제 명시(예: "관리자 페이지 제외 전제")하고 견적서에 반드시 노출한다
  - [ ] REQ-GATE-001 "확인 없이 BND-3 금지" 하드 가드는 유지된다(확인요약 없이 발화 금지)
  - [ ] 암묵신호(NIM 보조판정)만으로는 required를 건너뛰지 않는다
- **Description**: 마찰 체감 개선 중 최저비용 개입(P0-3).
- **우선순위**: P0 / **마감 전**
- **출처**: C-B1, C-S4-1, C-P0c, A §4.1-1

### REQ-ELICIT-009 — 승인 시 슬롯 조립 입력 (`build_quote` 본체 무수정)

- **요약**: AWAIT_APPROVAL 승인 시 `last_request` 원문 대신 슬롯 조립 텍스트를 `build_quote`에 넘긴다.
- **요약 상세**: 현 `build_quote()`(`backend.py:225-256`)는 원문을 그대로 NIM 프롬프트에 넣어 항목별 단가가 아닌 막연한 총액 추정이 된다. 입력만 슬롯 조립값으로 교체해 품질·재현성을 올린다.
- **Input**: 승인 시점의 슬롯(`platform + features + acceptance + budget_or_time + (가정) 전제`)
- **Output**: `build_quote` 호출(본체 무수정) → `{amount, basis}` (BND-2 `quote`)
- **완료 조건 (DoD)**:
  - [ ] 승인 시 전달값이 원문 1건이 아니라 슬롯 조립 텍스트다
  - [ ] 모든 견적에 근거 문구가 함께 존재한다(REQ-QUOTE-001 DoD)
  - [ ] 같은 입력이면 같은 견적이 나온다(재현성 — `self_check` 로그 포함, REQ-ELICIT-017)
  - [ ] `build_quote`·`rag_precheck`·`render_design`·`start_codegen` 본체는 무수정이다
- **Description**: `build_quote(user_text)` → `build_quote(slots, assumed_notes)` 확장 방향은 **(추정)** — 현 함수는 원문 1인자다.
- **우선순위**: P0 / **마감 전**
- **출처**: C-S5a, C-BO8, C-D1(QUOTE)

### REQ-ELICIT-010 — 하류 슬롯값 교체 (`render_design`·`start_codegen`)

- **요약**: QUOTED 진행 시 `platform="web"` 고정·`features=[원문]`을 슬롯값으로 교체한다.
- **요약 상세**: 현 `render_design(..., "web", [원문 1건], ...)`(`:773-775`)는 `platform` 하드코딩과 `features` 1건 문제를 일으켜 BND-2/BND-3 스키마 위반 위험이 있다.
- **Input**: QUOTED 진행 시점의 슬롯
- **Output**: `render_design(requirement_id, platform 슬롯값, features/confirmed_items 슬롯값, ...)` + `start_codegen` 입력=슬롯 조립 스펙
- **완료 조건 (DoD)**:
  - [ ] `platform` 고정값 "web"이 제거되고 슬롯값이 전달된다(enum `web|android` 준수)
  - [ ] `features`가 원문 1건짜리 배열이 아니라 슬롯 조립 리스트다
  - [ ] BND-2 required(`requirement_id, platform, features, quote{amount,basis}`)를 만족한다
  - [ ] BND-3 required(`requirement_id, confirmed_items, platform, acceptance_criteria`)를 만족한다
  - [ ] 함수 본체는 무수정이다
- **Description**: 시안·견적 데모 품질에 직결(P0-2).
- **우선순위**: P0 / **마감 전**
- **출처**: C-S5c, C-P0b, A §3.3, B §4.3

### REQ-ELICIT-011 — 거절 시 항목별 복귀 (AWAIT+QUOTED 공통)

- **요약**: 거절 시 처음부터 다시 묻지 않고 슬롯을 유지한 채 해당 항목으로만 복귀한다.
- **요약 상세**: 현 거절 경로(AWAIT `:757-759`, QUOTED `:790-792` "처음부터 다시")는 REQ-GATE-001 DoD("원래 애매했던 항목으로 복귀")를 위반한다. QUOTED 거절 쪽은 양쪽 분석 모두 별도 대책이 없었으므로(ReAct Thought 3-7a) 통합안에서 함께 고친다.
- **Input**: AWAIT_APPROVAL 또는 QUOTED에서의 거절
- **Output**: 슬롯 유지 상태로 해당 슬롯 복귀 질문
- **완료 조건 (DoD)**:
  - [ ] 거절 시 슬롯이 유지되고 "어느 항목을 고칠까요? 1번 기능 2번 플랫폼 3번 예산/일정 4번 기타" 4지선다로 해당 슬롯만 복귀한다
  - [ ] 처음부터 전체 재질문하지 않는다(REQ-GATE-001 DoD)
  - [ ] AWAIT 거절과 QUOTED 거절이 동일 규칙으로 처리된다
  - [ ] 4번 기타의 자유서술은 슬롯에 직접 쓰지 않고 재추출 입력으로만 사용한다(REQUIREMENTS §9)
- **Description**: 평가 시나리오(반려 경로)에 노출되므로 P0-4.
- **우선순위**: P0 / **마감 전**
- **출처**: C-S5b, C-B7, C-A6b, C-P0d, B §4.3, A §4.2

### REQ-ELICIT-012 — RAG 내부 파일명 사람말 래핑

- **요약**: `rag_precheck` 반환의 내부 source명을 그대로 노출하지 말고 사람말 템플릿으로 감싼다.
- **요약 상세**: 현행(`backend.py:739`)은 `기존 프로젝트: SRS-2025-014.md` 같은 내부 파일명을 채팅에 그대로 붙이는 UX 결함이다(B §2.4, A는 놓침).
- **Input**: `rag_precheck` 반환 문자열
- **Output**: 사람말 질문(예: `비슷한 쇼핑몰 프로젝트가 있었어요. 확장하실래요, 새로 만드실래요? (1번 확장 2번 신규)`)
- **완료 조건 (DoD)**:
  - [ ] 내부 source명(파일명)이 채팅에 그대로 노출되지 않는다
  - [ ] RAG hit 시 확장/신규 선택이 `existing_ref` 슬롯에 기록된다
  - [ ] RAG 검색 실패 시에도 대화가 멈추지 않고(best-effort) "신규 건으로 임의 가정"하지 않는다(REQ-RAG-001 DoD)
- **Description**: 내부명 노출은 데모 감점 요인. 5줄 템플릿 수정 수준(P0-5).
- **우선순위**: P0 / **마감 전**
- **출처**: C-A5, C-P0e, C-D1(RAG)

### REQ-ELICIT-013 — 질문 상한 3회 + 잠정확정 게이트 일괄확인

- **요약**: 무한 질의를 막기 위해 질문 상한을 두고, 초과 시 잠정확정 후 게이트에서 한 번에 확인받는다.
- **요약 상세**: A의 "최대 2개/턴"은 체감부하 대책이나 상한이 없고, B의 상한+게이트 일괄확인이 무한질의 안전밸브로 더 완결되므로 채택한다.
- **Input**: `ask_count`(상한 3, 추정·조정가능)
- **Output**: 상한 내=다음 슬롯 질문 / 상한 초과=잠정확정 확인요약 + 게이트
- **완료 조건 (DoD)**:
  - [ ] 질문은 최대 3회(조정가능)까지만 하고, 초과 시 잠정확정 후 게이트에서 한 번에 확인받는다
  - [ ] 한 턴 1개(기본)/최대 2개(연관 슬롯 묶음일 때만)로 절충한다
  - [ ] 상한 초과 시 문구가 확정값+추정값 구분 표기 형식을 따른다. 예: `지금까지: 웹(확정) / 예약·결제(확정) / 알림톡(가정·제외 전제) (3/4). 이대로 견적 낼까요? (진행/수정)`
- **Description**: 수치(3회·1개·300자·불릿4)는 UX 일반론 기반 **(추정)** — 파일럿 로그 후 확정(REQ-ELICIT-022).
- **우선순위**: P0 / **마감 전**
- **출처**: C-A7, C-B6, C-P0a, B §2.1-5

### REQ-ELICIT-014 — 자유서술 답변 처리 (직확인 금지·재질문 1회·partial 이관)

- **요약**: 옵션 밖 자유서술 답변을 확정 슬롯에 직접 쓰지 않고 재추출 입력·재질문·게이트 이관 3단계로 처리한다.
- **요약 상세**: REQUIREMENTS §9("자유 서술을 그대로 확정안에 반영하지 않는다")·REQ-ASK-001 에러 처리의 직접 구현이다.
- **Input**: 옵션 밖 자유서술 답변
- **Output**: 슬롯 재추출 입력 반영 또는 `partial` 메모 + 게이트 확인
- **완료 조건 (DoD)**:
  - [ ] 자유서술 답변은 확정 슬롯에 직접 쓰지 않고 슬롯 재추출 입력으로만 사용한다
  - [ ] 고객이 옵션 밖 자유 서술로 답하면 옵션 3개+추천으로 재질문한다(REQ-ASK-001 DoD)
  - [ ] 재질문은 1회로 제한하고(무한 루프 방지), 그래도 안 맞으면 원문을 `partial` 메모로 붙여 게이트에서 사람이 확인한다
- **Description**: B §2.2의 "재질문 1회 + partial 메모 이관"은 B 원본 고유 세부다.
- **우선순위**: P0 / **마감 전**
- **출처**: C-S1(자유서술 행), C-BO2, C-B7(4번 기타 행), A §3.1, C-D1(ASK)

### REQ-ELICIT-015 — 공유방 질문-답변 매칭 (꼬임 방지 최소분)

- **요약**: 상태머신 복제 없이 `pending_question`+`seq` 인용 + 투표/질의 분리로 방 질문 꼬임을 막는다.
- **요약 상세**: `ROOMS`는 방당 상태머신 1개를 공유하므로(`rooms[room_id]`→`session_id` 1개) 여러 명이 동시에 답하면 귀속이 꼬인다. A는 공유방을 전혀 다루지 않았으므로 B안을 그대로 수용한다.
- **Input**: 공유방 내 동시 답변들
- **Output**: 단일 미결 질문에 귀속된 답변 처리
- **완료 조건 (DoD)**:
  - [ ] 미결 질문 단일화: `pending_question`{slot,options,seq} 1개만 둔다. 이전 질문 해소 전 새 질문 금지
  - [ ] 답변 귀속은 `messages[].seq` 인용으로 "가장 최근 미결 질문에 대한 답"으로 귀속한다. 판별 불가면 `partial`로 두고 재확인 1회("○○님의 답변이 어느 항목인지 모르겠어요. 번호로 다시 보내주세요")
  - [ ] 질의 중에는 투표 바를 숨기고, 투표 중에는 질의 입력을 투표 키워드로만 해석한다(`updateActionBars`에 질의바 1종 추가). GATHERING 질의 답변은 투표 판정에서 제외한다
  - [ ] AI 질문 메시지에는 "○○ 슬롯 질문" 라벨을 붙이고 아바타+닉네임+`BOT` 뱃지를 유지한다
  - [ ] `ai_status`는 재사용 또는 `ASKING` 1종 추가 (추정·프론트 1줄)
- **Description**: `ai_status` 현 값은 `IDLE/RAG_SEARCHING/QUOTING/GENERATING/DONE`만 있고 `ASKING` 없음이 실측 확인됨. B가 `ASKING` 추가를 "(추정)"으로 표기한 것도 정확하다.
- **우선순위**: P0(최소 매칭분) / **마감 전**
- **출처**: C-A6a, C-S6, C-BO4, C-BO5, B §2.5·§4.4

### REQ-ELICIT-016 — DONE 후 재입장 슬롯 초기화

- **요약**: DONE 후 새 요청이 오면 슬롯을 초기화하고 GATHERING으로 보낸다.
- **요약 상세**: 현 `DONE` 후 입력(`:794-796`)도 `GATHERING`으로 돌리면서 슬롯이 없으므로 새 대화와 이어짐 판별이 불가하다 — 양쪽 분석 모두 미언급이었으므로 본 리뷰의 신규 제안 **(추정)** 으로 수용한다.
- **Input**: DONE 상태에서의 사용자 입력
- **Output**: 새 요청이면 슬롯 초기화 후 GATHERING, 이어짐이면 슬롯 유지
- **완료 조건 (DoD)**:
  - [ ] DONE 후 새 요청이면 슬롯(REQ-ELICIT-001 필드 일체)이 초기화되고 GATHERING으로 간다
  - [ ] `asked_keys` 재사용 수명은 방 로그로 검증한다(추정 — REQ-ELICIT-022)
- **Description**: 신규 규칙이므로 구현 시 방 로그로 검증 필요.
- **우선순위**: P0 / **마감 전**
- **출처**: C-S5d, C-A6b, ReAct Thought 3-7b

### REQ-ELICIT-017 — 승인 전 NIM self-check 2차망 (마감 후)

- **요약**: GATHERING→AWAIT_APPROVAL 전이 직전에 NIM self-check 1회로 빠진 정보를 마지막 점검한다.
- **요약 상세**: 결정적 규칙이 못 잡는 모호함(은유·생략·상충)을 잡는 2차망이다. 규칙→질의→자가점검 3층 중 마지막 층이며, 단독 완전성 수단으로 쓰면 REQ-VALIDATE-001 "전부 LLM 판단에 맡기지 않는다"에 어긋나므로 반드시 REQ-ELICIT-002와 묶어 도입한다.
- **Input**: 슬롯 충족 시점의 슬롯 요약
- **Output**: `{"ok": true}` → 게이트 / `{"ok": false, "missing": [...]}` → 해당 슬롯 복귀
- **완료 조건 (DoD)**:
  - [ ] 프롬프트는 `build_quote` JSON 강제 패턴(`backend.py:233-253`)을 재사용하고 구조화 JSON만 반환한다
  - [ ] 호출은 전이당 최대 1회(무한 루프 방지). 타임아웃(`NIM_TIMEOUT_SEC`) 내 실패 시 "검사 생략하고 게이트로" 폴백한다(REQ-RAG-001 best-effort 철학과 동일)
  - [ ] 프롬프트에 "견적·시안·코드생성에 지장이 없는 사소한 것은 지적하지 마라"를 명시하고 `missing`은 최대 2건까지만 수용한다
  - [ ] 지적 수용은 "첫 1건만 질문, 나머지는 게이트 확인요약에 (미확인) 표기로 이관"한다(질문 증가 차단)
  - [ ] 지적 내용은 `session["self_check"]`에 로그로 남겨 재현·감사 가능하게 한다
  - [ ] self-check는 추가 질문이 아니라 게이트 가기 전 마지막 확인이며, `ok`면 즉시 게이트로 간다
- **Description**: 규칙+질의가 먼저 안정된 뒤 도입. 단독 도입 시 과잉지적·지연 리스크(P1-6).
- **우선순위**: P1 / **마감 후**
- **출처**: C-S3, C-B5, C-P1a, B §3

### REQ-ELICIT-018 — 스마트디폴트 고도화 + `acceptance_criteria` 템플릿 (마감 후)

- **요약**: P0 확인요약(REQ-ELICIT-007)을 전 슬롯 추정 + 기능별 인수조건 템플릿으로 확장한다.
- **요약 상세**: 빈 슬롯마다 NIM이 문맥 기반 추정값을 `assumed`로 채우고 확인용 요약 1개로 묶어 제시한다. `acceptance_criteria` 생성 경로가 현 코드에 없으므로(A §1.2표) 템플릿+NIM 다듬기 2단계가 안정적이다.
- **Input**: 미충족 선택 슬롯 + 누적 대화
- **Output**: 추정값 묶음 확인요약 + 기능별 인수조건 초안
- **완료 조건 (DoD)**:
  - [ ] `acceptance_criteria`는 기능별 템플릿("~가 가능")으로 생성하고 NIM 다듬기를 2단계로 둔다
  - [ ] `acceptance`는 features 각 항목 대응 문장을 기계적으로 카운트하고, 없으면 질의 생략 가능하되 REQ-ELICIT-017 self-check에서 보완한다
  - [ ] BND-3 required(`acceptance_criteria`)가 빈 배열로 발화되지 않는다
  - [ ] 고위험 제외(`platform`, `budget 상한` 추정확정 금지)는 유지된다
- **Description**: P0 확인요약의 확장판(P1-7).
- **우선순위**: P1 / **마감 후**
- **출처**: C-P1b, C-BO9, A §2 방법3·§3.1-3

### REQ-ELICIT-019 — thorough 모드 + 암묵신호 + 모드 전환 (마감 후)

- **요약**: 꼼꼼한 사용자를 위한 thorough 모드와 암묵신호 보조판정, 양방향 모드 전환을 제공한다.
- **요약 상세**: A §4.1의 2층 판정(명시 키워드 결정적 + 암묵신호 NIM 보조) 중 마감 전에는 fast-track 명시 키워드만 도입하고(REQ-ELICIT-008), 나머지는 실측 로그 후 도입한다.
- **Input**: thorough 키워드(`꼼꼼하게/자세히/다 물어봐`) / 암묵신호(초반 장문·2회 연속 단답)
- **Output**: thorough=optional까지 순차 질문(한 턴 1항목) / 암묵 fast-track 성향=확인요약 앞당김
- **완료 조건 (DoD)**:
  - [ ] thorough 키워드는 결정적 규칙으로 판정하고 optional까지 순차 질문 모드로 한 턴 1항목으로 늦춘다
  - [ ] 초반 장문(구체 예산·일정 포함) → 게이트 직행 가능(0-질문 경로). 2회 연속 단답·"응"/"다음" → fast-track 성향으로 보고 확인요약을 앞당긴다
  - [ ] 암묵신호만으로 required를 건너뛰지 않는다(BND-3 필수값 + REQ-GATE-001 하드 가드)
  - [ ] 모드 전환은 언제든 가능: "아까 생략한 것도 물을게" 한 마디면 thorough로 복귀하고 `asked_keys` + 보관된 optional 슬롯을 재사용한다
  - [ ] 생략된 optional은 반려 시 다시 꺼낼 수 있게 보관하고, 생략 디폴트는 문서화·고지한다
- **Description**: 실측 로그 후 조정(P1-8). 암묵신호 임계값은 추정.
- **우선순위**: P1 / **마감 후**
- **출처**: C-P1c, C-AO2, C-AO3, A §4.1-2·§4.2·§2 방법4

### REQ-ELICIT-020 — 침묵·무응답 에스컬레이션 타이머 (마감 후)

- **요약**: 침묵·무응답 시 에스컬레이션을 PARALLEL_1_SPEC §9 + reqpipe G12 개념으로 도입한다.
- **요약 상세**: 현 코드에 타이머/스케줄러 코드가 없음이 확인되므로 신규 필요 **(추정)** — 공수 별도 산정.
- **Input**: 무응답 경과 시간
- **Output**: 에스컬레이션 메시지(재촉 질문 또는 사람 개입)
- **완료 조건 (DoD)**:
  - [ ] 침묵·무응답 시 에스컬레이션 정책이 PARALLEL_1_SPEC §9 + reqpipe G12 개념을 따른다
  - [ ] 현 코드에 타이머가 없으므로 신규 구현 공수를 별도 산정한다
- **Description**: A §3.1 방어선 + ReAct P1-9.
- **우선순위**: P1 / **마감 후**
- **출처**: C-P1d, C-AO1, A §3.1

### REQ-ELICIT-021 — `platform` 복수 선택 예외 + 스키마 개정 2단계 (마감 후)

- **요약**: "웹+앱 둘 다" 수요에 1차 단일선택+전제명시로 대응하고, 배열화 개정은 마감 후 과제로 둔다.
- **요약 상세**: 현 스키마 enum(`web|android`) 실측에 근거하나 "둘 다" 수요 빈도는 **(추정)** — 로그 후 개정 판단. A는 이 문제를 다루지 않았다.
- **Input**: "웹+앱 둘 다" 응답
- **Output**: 1차=단일 선택 + 확인요약에 전제 명시 / 2차(마감 후)=BND-2·BND-3 `platform` 배열화 개정
- **완료 조건 (DoD)**:
  - [ ] "둘 다" 응답이 와도 enum 위반으로 깨지지 않고 단일 선택 + 전제명시로 처리된다
  - [ ] 마감 후 스키마 개정(BND-2·BND-3 `platform` 배열화) 판단이 로그 근거로 남는다
- **Description**: B §5-3 "(추정) 단일 선택, 둘 다 요구 시 스키마 개정" 수용.
- **우선순위**: P1(개정) / **마감 후**. 1차 대응(단일선택+전제명시)은 마감 전 REQ-ELICIT-004·007로 커버.
- **출처**: C-B4, C-P1e, B §5-3

### REQ-ELICIT-022 — 임계값 튜닝 (파일럿 로그 후)

- **요약**: 수치 임계값(질문 상한·300자·불릿수 등)을 파일럿 대화 로그(A/B) 후 확정한다.
- **요약 상세**: 아래 수치는 UX 일반론 기반 **(추정)** — 실측 없이 확정 불가.
- **Input**: 파일럿 대화 로그
- **Output**: 확정 임계값
- **완료 조건 (DoD)**:
  - [ ] 질문 상한 3회·한 턴 1개 기본/최대 2개·300자·불릿 4개가 로그 근거로 확정 또는 조정된다
  - [ ] `asked_keys` 재사용 수명이 확정된다
  - [ ] 경계 utterance("네"가 답변인지 투표인지) 판별 규칙이 방 로그로 검증된다(신규 제안·추정)
- **Description**: P1-11.
- **우선순위**: P1 / **마감 후**
- **출처**: C-P1f, C-E1, B §5-1·2, ReAct §5.4

### REQ-ELICIT-023 — 본체 무수정 + 폴백 철학 (구현 제약)

- **요약**: 하위 함수 본체를 수정하지 않고 호출 시점·입력만 바꾸며, NIM 실패 시 현행 동작으로 폴백한다.
- **요약 상세**: 양쪽 분석이 동의한 폴백 철학(A §3.1 방어선, B §3.2·§4.2). `/chat` 500 방지는 기존 `build_quote`/`rag_precheck` 폴백 철학과 동일하게.
- **Input**: 전 REQ 구현 전반
- **Output**: 무수정 본체 + 폴백 경로
- **완료 조건 (DoD)**:
  - [ ] `rag_precheck`·`build_quote`·`render_design`·`start_codegen` 본체는 손대지 않고 호출 시점과 입력(원문→슬롯 조립값)만 바뀐다
  - [ ] NIM 슬롯 추출 실패 시 현행 동작(원문 그대로 게이트)으로 폴백한다
  - [ ] self-check 실패 시 `{"ok": True}` 폴백(검사 생략, 대화 차단 금지)한다
  - [ ] room 투표 로직(`backend.py:626-645`)은 그대로 둔다
- **Description**: 전 REQ에 걸리는 횡단 제약.
- **우선순위**: P0(원칙 선언) / **마감 전부터 적용**
- **출처**: C-BO8, C-BO5(투표행), C-AO6(폴백행), A §3.1, B §3.2·§4.2

### REQ-ELICIT-024 — required 집합 최종 합의 (병렬작업 3 포함)

- **요약**: 게이트 하드조건의 정확한 집합을 팀 합의(특히 병렬작업 3: 스펙생성 최소입력)로 확정한다.
- **요약 상세**: A 원안(`platform` + `features≥1` + `budget_band 또는 deadline 중 ≥1`, §3.2 — 추정)과 B 원안(6슬롯 모두 filled, §1.2)은 서로 충돌하므로, 본 PRD는 절충안(하드조건=`platform`+`features≥1`+`existing_ref`+`customer_id`, 예산/일정·acceptance는 선택·추정확정)을 채택하고 합의를 요구한다. 예산 없이는 견적 3안 분별력이 떨어진다는 B 지적과 fast-track 필요라는 A 지적의 절충점이다. `rag_reuse_confirmed`는 유사 프로젝트 발견 시에만 required로 승격한다(PARALLEL_1_SPEC §3 분기).
- **Input**: 본 PRD + 병렬작업 3 스펙생성 최소입력 의견
- **Output**: 확정 required 집합 문서
- **완료 조건 (DoD)**:
  - [ ] A 원안·B 원안·절충안이 모두 기록되고(본 PRD §2 C-AO5·C-BO1·C-A4) 병렬작업 3 합의로 1개가 확정된다
  - [ ] 확정 전까지는 절충안(REQ-ELICIT-006 하드조건)을 잠정치로 사용한다
- **Description**: ReAct §5.4 추정 1항. 합의 전까지 개발이 막히지 않게 잠정치로 진행한다.
- **우선순위**: P0(합의) / **마감 전**
- **출처**: C-A4, C-B3, C-AO5, C-BO1, C-E1, A §3.2·§6, B §1.1

---

## 4. 빠짐없음 검증 (출처 대조표 ↔ REQ-ID 매핑)

> 성공 기준: §2의 대조ID 45개가 모두 아래 표에서 ≥1개의 REQ-ID에 매핑되고, 매핑 누락(`-`)이 0건일 것. 자가 재검토 결과 누락 0건.

| 대조ID | 매핑 REQ-ID | 비고 |
|---|---|---|
| C-A1 | REQ-ELICIT-002 | 규칙-우선 + 4상태 |
| C-A2 | REQ-ELICIT-003 | 턴당 1회·실패 폴백 |
| C-A3 | REQ-ELICIT-007 (+017 2차망) | assumed+(가정)+self-check |
| C-A4 | REQ-ELICIT-006 + 024 | 하드조건 축소 + 합의 |
| C-A5 | REQ-ELICIT-012 | 사람말 래핑 |
| C-A6a | REQ-ELICIT-015 | 공유방 수용 |
| C-A6b | REQ-ELICIT-011 + 016 | AWAIT/QUOTED/DONE 통일 |
| C-A7 | REQ-ELICIT-004 + 013 | 1개 기본/최대 2개 + 상한 3 |
| C-B1 | REQ-ELICIT-008 | fast-track 키워드 |
| C-B2 | REQ-ELICIT-007 (+018 고도화) | 묶음 확인요약 |
| C-B3 | REQ-ELICIT-006 + 024 | 하드조건 축소 결의 |
| C-B4 | REQ-ELICIT-021 | 2단계 계획 |
| C-B5 | REQ-ELICIT-017 | self-check 가드 전부 |
| C-B6 | REQ-ELICIT-013 | 문구 예시 고정 |
| C-B7 | REQ-ELICIT-011 | 4지선다 + 직확인 금지 |
| C-S0 | REQ-ELICIT-001 | 세션 확장 전부 |
| C-S1 | REQ-ELICIT-002 + 014 | 규칙표 + 자유서술 행 |
| C-S2 | REQ-ELICIT-004 + 005 + 012 | 질문·리듬·래핑 행 |
| C-S3 | REQ-ELICIT-003 + 017 | 상한 행 + 본체 행 |
| C-S4 | REQ-ELICIT-006 + 008 + 013 | 분기 4단계 전부 |
| C-S5a | REQ-ELICIT-009 | 슬롯 조립 전달 |
| C-S5b | REQ-ELICIT-011 | 항목 복귀 |
| C-S5c | REQ-ELICIT-010 | 하류 교체 |
| C-S5d | REQ-ELICIT-016 | DONE 초기화 |
| C-S6 | REQ-ELICIT-015 | 공유방 최소 추가 전부 |
| C-P0a | REQ-ELICIT-002 + 004 + 006 | P0-1 |
| C-P0b | REQ-ELICIT-007 + 010 | P0-2 |
| C-P0c | REQ-ELICIT-008 | P0-3 |
| C-P0d | REQ-ELICIT-011 | P0-4 |
| C-P0e | REQ-ELICIT-012 | P0-5 |
| C-P1a | REQ-ELICIT-017 | P1-6 |
| C-P1b | REQ-ELICIT-018 | P1-7 |
| C-P1c | REQ-ELICIT-019 | P1-8 |
| C-P1d | REQ-ELICIT-020 | P1-9 |
| C-P1e | REQ-ELICIT-021 | P1-10 |
| C-P1f | REQ-ELICIT-022 | P1-11 |
| C-AO1 | REQ-ELICIT-020 | 침묵 에스컬레이션 |
| C-AO2 | REQ-ELICIT-019 | optional 보관·고지 |
| C-AO3 | REQ-ELICIT-019 | 모드 전환 |
| C-AO4 | REQ-ELICIT-007 + 009 | basis (가정) 기록 |
| C-AO5 | REQ-ELICIT-024 | A 원안 기록·결의 |
| C-AO6 | REQ-ELICIT-001 + 002 + 003 | 누적대화·슬롯·폴백 |
| C-BO1 | REQ-ELICIT-006 + 024 | B 원안 기록·결의 |
| C-BO2 | REQ-ELICIT-014 | 재질문 1회 + partial 이관 |
| C-BO3 | REQ-ELICIT-004 | 전문용어 금지 |
| C-BO4 | REQ-ELICIT-015 | 슬롯 질문 라벨 |
| C-BO5 | REQ-ELICIT-015 + 023 | 투표 판정 제외 |
| C-BO6 | REQ-ELICIT-005 | #statusBar 재사용 |
| C-BO7 | REQ-ELICIT-001 | setdefault·직렬화 |
| C-BO8 | REQ-ELICIT-009 + 010 + 023 | 본체 무수정 |
| C-BO9 | REQ-ELICIT-018 | acceptance 카운트 |
| C-BO10 | REQ-ELICIT-004 | 순서·완화책 |
| C-D1 | REQ-ELICIT-001·002·004·009·011·012·014·017 (DoD 내 인용) + §6 | DoD 6건 수용 |
| C-E1 | §7 (미확정 사항) | 추정 5건 수용 |

**재검토 메모**: 초안 작성 후 §2 45행과 §3 24개 REQ를 양방향으로 대조했다. (1) 정방향: 대조ID 각 행이 §4 표에서 REQ를 갖는지 확인 → 45/45 매핑. (2) 역방향: REQ 각 항의 "출처" 필드가 가리키는 대조ID가 §2에 실재하는지 확인 → 24/24 유효. 특히 양쪽 분석이 모두 빠뜨린 QUOTED 거절 별도 대책(C-A6b·C-S5b→011), DONE 초기화(C-S5d→016), NIM 지연 가드(C-A2→003)는 통합안에서 추가됐음을 확인했고, A/B 원안 충돌(required 집합 C-AO5 vs C-BO1)은 024에서 결의 절차로 전환해 어느 쪽도 누락 없이 기록했다. 남은 미확정치 5건(C-E1)은 §7에 분리 보관했다.

---

## 5. 마감(2026-09-28) 전/후 구분

### 마감 전 필수 (P0 — 데모·DoD 직결, 16개)

| REQ-ID | 항목 | DoD 직결 |
|---|---|---|
| REQ-ELICIT-001 | 세션 슬롯 확장 + 영속 | REQ-INTAKE-001 |
| REQ-ELICIT-002 | 결정적 규칙 `update_slots` | REQ-VALIDATE-001 |
| REQ-ELICIT-003 | NIM 상한·폴백 선언 | 안정성(500 방지) |
| REQ-ELICIT-004 | `next_question` 옵션 3개+추천 | REQ-ASK-001 |
| REQ-ELICIT-005 | 요약-확인 리듬 + 진행률 | REQ-CHAT-001 |
| REQ-ELICIT-006 | 게이트 조건 + GATHERING 교체 | REQ-VALIDATE-001 |
| REQ-ELICIT-007 | 확인요약 확정/(가정) 구분 | REQ-QUOTE-001 |
| REQ-ELICIT-008 | fast-track 키워드 | 마찰 저감(최저비용) |
| REQ-ELICIT-009 | 승인 시 슬롯 조립 입력 | REQ-QUOTE-001 |
| REQ-ELICIT-010 | 하류 슬롯값 교체 | BND-2/BND-3 정합 |
| REQ-ELICIT-011 | 거절 시 항목별 복귀 | REQ-GATE-001 |
| REQ-ELICIT-012 | RAG 사람말 래핑 | REQ-RAG-001 |
| REQ-ELICIT-013 | 질문 상한 3 + 일괄확인 | 무한질의 방지 |
| REQ-ELICIT-014 | 자유서술 처리 | REQ-ASK-001·§9 |
| REQ-ELICIT-015 | 공유방 매칭 최소분 | 꼬임 방지 |
| REQ-ELICIT-016 | DONE 후 초기화 | 신규 규칙 |
| REQ-ELICIT-023 | 본체 무수정 + 폴백 (원칙) | 횡단 제약 |
| REQ-ELICIT-024 | required 집합 합의 | 잠정치로 진행 |

### 마감 후 (P1 — 안정화·고도화, 6개)

| REQ-ID | 항목 | 선행 조건 |
|---|---|---|
| REQ-ELICIT-017 | self-check 2차망 | 002+004 안정 후 |
| REQ-ELICIT-018 | 스마트디폴트 고도화 + acceptance 템플릿 | 007 확장 |
| REQ-ELICIT-019 | thorough + 암묵신호 + 모드 전환 | 로그 후 조정 |
| REQ-ELICIT-020 | 타이머 에스컬레이션 | 공수 별도 |
| REQ-ELICIT-021 | platform 배열화 개정 | 로그 후 판단 |
| REQ-ELICIT-022 | 임계값 튜닝 | 파일럿 로그 후 |

---

## 6. 기존 DoD 매핑 (통합안이 스펙을 닫는지 — ReAct §5.3 수용)

| DoD | 닫히는 지점 |
|---|---|
| REQ-INTAKE-001 (슬롯 정리+출처) | REQ-ELICIT-001 slots + 원문 발췌 `note` 보관 |
| REQ-VALIDATE-001 (불명확 검출/다 차면 직행) | REQ-ELICIT-002 결정적 규칙 + REQ-ELICIT-006 required 충족→(017)→게이트 |
| REQ-ASK-001 (3개+추천/자유서술 재질문) | REQ-ELICIT-004 형태별 질문 + REQ-ELICIT-014 재질문 1회 상한 |
| REQ-GATE-001 (확인 없이 BND-3 금지/동일 id/항목복귀) | 승인 본체 유지 + REQ-ELICIT-011 해당 슬롯 복귀. BND-2·BND-3 동일 `requirement_id` 동시 발화 유지 |
| REQ-QUOTE-001 (근거+재현성) | REQ-ELICIT-009 슬롯 조립 입력 + (가정) 전제의 `basis` 기록 + `self_check` 로그(017) |
| REQ-RAG-001 (best-effort, 임의가정 금지) | 첫 진입 1회 + 실패 시 신규 폴백 유지 + REQ-ELICIT-012 사람말 래핑 |

---

## 7. 미확정 사항 (추정 명시 — ReAct §5.4 + A §6 + B §5 수용)

1. required 하드조건 절충안(`platform·features≥1·existing_ref` + `customer_id`)은 본 PRD의 절충 제안이며 **(추정)** — REQ-ELICIT-024 병렬작업 3 합의 후 확정.
2. "한 턴 1개 기본·최대 2개", "질문 상한 3회", "300자·불릿 4개"는 UX 일반론 기반 **(추정)** — REQ-ELICIT-022 파일럿 로그 후 확정.
3. `platform` 단일값·`budget_or_time` 선택 취급은 현 스키마 enum 실측에 근거하나 "둘 다" 수요 빈도는 **(추정)** — REQ-ELICIT-021 로그 후 개정 판단.
4. self-check·NIM 추출 지연의 체감 영향은 `NIM_TIMEOUT_SEC=25` 실측과 폴백 설계로 완화 가능하나 실측 전 확정 불가 **(추정)**.
5. DONE 후 슬롯 초기화 규칙·`asked_keys` 재사용 수명·투표와 질의 분리 시 경계 utterance("네"가 답변인지 투표인지)는 신규 제안으로 **(추정)** — 구현 시 방 로그로 검증 필요(REQ-ELICIT-016·022).
6. A §6 추가 추정: 슬롯 추출용 NIM 프롬프트·JSON 스키마는 현 레포에 존재하지 않아(확인됨: `build_quote`/`rag_precheck` 외 NIM 호출 없음) 신규 설계 필요. `build_quote(slots, assumed_notes)` 시그니처 확장도 추정.
7. B §5 추가 추정: 동의어·은유 처리율(키워드 규칙 커버리지는 로그 후 확인). self-check 체감 지연은 폴백으로 상쇄 가능하나 실측 전 확정 불가. `ai_status` `ASKING` 추가 vs 기존 재사용도 추정.
