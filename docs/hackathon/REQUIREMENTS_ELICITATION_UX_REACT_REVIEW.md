# 요구사항 도출 UX 교차검토 — ReAct 자문 리뷰 (A × B 통합)

> 작성일: 2026-09-23 / 작성자: 에이전트 자문역 (ReAct 방식)
> 대상: `docs/hackathon/REQUIREMENTS_ELICITATION_UX_A.md` (분석가 A),
> `docs/hackathon/REQUIREMENTS_ELICITATION_UX_B.md` (분석가 B)
> 질문: "이 챗봇이 요구사항을 빠짐없이 도출하면서도 사용자가 불편하지 않게 하려면 어떻게 해야 하는가"
> 제약: 코드 수정 없음. `.env` 미열람. git add/commit/push 없음.
> 방식: 아래 Thought–Action–Observation 로그가 실제 사고 과정이다. 결론만 쓰지 않고 과정을 남긴다.

---

## 1. 경영진 요약 (TL;DR)

1. A와 B는 진단에서 완전히 일치: `backend.py:731-744`가 후속 질문 없이 1턴 만에 `AWAIT_APPROVAL`로 직행해 ④접수·⑤검증·⑥질의가 생략되고, `platform="web"` 고정(`:773-774`)·`features=[원문 1건]`으로 BND-2/BND-3 필수값이 무너진다.
2. 해법 방향도 일치: "빠진 것만 되묻기 + 객관식(옵션 3개+추천) + 반려 시 해당 항목 복귀"가 공통 코어다.
3. 차이는 수단이다: A=NIM 슬롯추출 우선+스마트디폴트+2등급+fast-track, B=결정적규칙 우선+한번에1개+질문상한3+self-check+공유방 매칭.
4. 최종 권고: B의 결정적 체크리스트를 게이트로, A의 NIM 추출·스마트디폴트·fast-track을 가속기로 결합하고, B의 self-check는 폴백 첨부 2차망으로만 쓴다.
5. 마감(2026-09-28) 전: 슬롯+한번에1~2개 질문+확인요약+거절시 항목복귀+`platform`/`features` 하류교체. 이후: self-check·타이머·acceptance 자동생성 고도화.

---

## 2. Thought–Action–Observation 로그 (6단계)

### Thought 1: A와 B가 각각 무엇을 핵심 주장으로 삼았는지 파악해야 한다.

**Action 1:** A, B 문서를 읽고 각각의 핵심 주장을 1~2줄로 요약.

**Observation 1:**

- **A의 핵심 주장:** 현 `GATHERING`은 후속 질문 없이 1턴 만에 승인 게이트로 넘어가 REQ-VALIDATE/ASK의 DoD를 우회하므로, 해법은 턴을 무작정 늘리는 게 아니라 "(1) NIM으로 빠진 슬롯만 자동 추출 + (2) 한 턴 1~2개 선택형 질문 + (3) 스마트디폴트(추정값 확인받기)" 조합과 서두르는 사용자를 위한 명시적 fast-track 이중 모드다 (A §0 결론박스, §2 방법 1~4, §4).
- **B의 핵심 주장:** 현 `GATHERING`은 ④접수·⑤검증·⑥질의를 생략한 단축 경로이므로, 완전성은 LLM 눈치가 아니라 세 스키마에서 역산한 6슬롯 체크리스트+결정적 규칙 검증으로 기계적으로 보장하고, 불편함은 "한 번에 하나·객관식·예/아니오·진행률·요약-확인 리듬" UX 패턴과 승인 전 NIM self-check 2차망으로 줄이며, 공유방은 `pending_question`+`seq` 인용으로 꼬임을 막는다 (B 핵심결론 3문단, §1~§3, §2.5).

### Thought 2: A와 B가 공통으로 동의하는 지점이 뭔지 확인해야 한다.

**Action 2:** 두 문서의 진단(§0~§1)과 DoD 매핑, 처방의 겹치는 부분을 비교.

**Observation 2 (공통점 — 6가지 확인됨):**

1. **진단 일치:** 둘 다 `backend.py:731-744`(`GREETING/GATHERING` → `rag_precheck` 1회 → `last_request=원문` → 즉시 `AWAIT_APPROVAL`)를 지목하고 "후속 질문 루프 0회, 검증 분기 없음"이라 판정 (A §1.1-1~2, B §0.1-1~2).
2. **하류 파급 일치:** 둘 다 `render_design(..., "web", [원문 1건], ...)`(`:773-775`)의 `platform` 하드코딩과 `features`/`confirmed_items` 1건 문제를 지적하고 BND-2/BND-3 스키마 위반 위험에 동의 (A §1.1-5·§1.2표, B §0.1-3~4).
3. **거절 경로 결함 일치:** 둘 다 거절 시 "처음부터 다시"(AWAIT_APPROVAL→GATHERING, `backend.py:757-759`)가 REQ-GATE-001 DoD("원래 애매했던 항목으로 복귀")를 위반한다고 판정 (A §1.1-4·§1.2표, B §0.1-5).
4. **DoD 해석 일치:** REQ-INTAKE-001(슬롯+출처)/VALIDATE-001(불명확 검출·다 차면 직행)/ASK-001(옵션 3개+추천·자유서술 재질문)/GATE-001(확인 없이 BND-3 금지·동일 id·항목복귀) 정리가 실질적으로 동일 (A §1.2표, B §0.2표).
5. **처방 코어 일치:** "빠진 것만 되묻기 + 선택형(옵션 3개+추천, 자유서술은 슬롯에 직접 쓰지 않음) + 승인 시 슬롯 조립값으로 `build_quote`/`render_design` 호출"이 양쪽 설계에 모두 존재 (A §3.1~§3.3, B §4.2~§4.3).
6. **폴백 철학 일치:** NIM 실패 시 현행 동작(원문 게이트)으로 폴백해 `/chat` 500을 막는다는 방어선에 동의 (A §3.1 방어선, B §3.2 검사생략 폴백·§4.2).

### Thought 3: A와 B가 서로 다르게 판단했거나, 한쪽이 놓친 부분이 있는지 확인해야 한다.

**Action 3:** `backend.py` 전체(특히 `:225-256 build_quote`, `:590-686 ROOM`, `:689-805 _process_chat_turn`, `:773-792 QUOTED`), `contracts/gate_to_spec.schema.json`·`gate_to_quote.schema.json`·`quote_to_design.schema.json`, `static/room.html`(`#statusBar`·`voteBar`·`updateActionBars`), `docs/hackathon/REQUIREMENTS.md`·`PARALLEL_1_SPEC.md`를 다시 열어 누가 더 정확한지, 둘 다 놓친 게 있는지 검증. `pending_question`·`slots`·`self_check`·`asked_keys`·`NIM_TIMEOUT_SEC` 존재 여부도 grep으로 확인.

**Observation 3 (실제 검증 결과):**

1. **기본 진단은 둘 다 정확.** `backend.py:731-744`를 직접 읽어 확인: `rag_precheck(user_text)` 1회 → `session["last_request"]=user_text` → 승인문구 → `state="AWAIT_APPROVAL"`. 슬롯 파싱·질문 루프 코드 없음. `pending_question`·`slots`·`self_check`·`asked_keys`·`update_slots`·`next_question`은 grep 0건(미구현)으로 양쪽 "미구현" 판정이 맞다.
2. **스키마 required는 B의 합집합 표가 정확하고 A의 표도 맞다.** 실측: BND-3 required=`requirement_id, confirmed_items, platform(enum web|android), acceptance_criteria`; BND-1 required=`requirement_id, confirmed_items, customer_id`; BND-2 required=`requirement_id, platform, features, quote{amount,basis}`. A §1.2표와 B §1.1표 모두 이 내용과 일치. B가 추가로 `customer_id=세션/방 대표 식별자`로 해석한 것은 설계 제안이며, 현 코드에 `customer_id` 필드 자체가 없음(`SESSIONS.setdefault`는 `state`+`requirement_id`만 생성, `:573`,`:815`)을 확인 — B의 "filled로 둔다"는 신규 설계라서 타당.
3. **수단의 우선순위가 정반대 — 검증상 B의 순서가 스펙에 더 가깝다.** A는 "매 턴 NIM 슬롯추출이 가장 자연스러움"(A §2 방법1)이라 하고, B는 "결정적 규칙이 먼저, LLM은 보조"(B §1.2, REQUIREMENTS REQ-VALIDATE-001 "전부 LLM 판단에 맡기지 않는다", PARALLEL_1_SPEC §4 "LLM 판정 금지, 결정적 규칙 우선")를 든다. REQUIREMENTS.md §REQ-VALIDATE-001과 PARALLEL_1_SPEC §4 원문을 열어본 결과 B의 인용이 정확하므로, 1차 판정은 B안(규칙 우선)이 스펙 정합성이 높다. A의 NIM 우선은 폴백·환각 대책(A §3.1 방어선)이 있어도 단독 수단으로는 REQ-VALIDATE 원칙과 충돌한다.
4. **질문 배치 숫자가 다르다 (A: 최대 2개/턴 vs B: 1개/턴 + 상한 3회).** 둘 다 "추정·조정 가능"을 명시(A §6, B §5)했으므로 틀린 쪽은 없다. 다만 B의 상한+게이트 일괄확인(B §2.1-5)이 무한질의 안전밸브로서 더 완결되고, A의 fast-track 키워드(A §4.1-1)가 서두르는 사용자 대책으로서는 더 구체적이다. 상호보완 관계.
5. **B만 다룬 영역 2건은 실측상 유효하다.**
   - (a) RAG 내부 파일명 노출: `rag_precheck`이 `f"기존 프로젝트: {top['source']}"`(`backend.py:188`)를 반환하고 GATHERING이 이를 그대로 채팅에 붙임(`:739`)을 확인 — B §2.4의 "사람말 템플릿으로 감싸라" 지적이 맞고, A는 이 UX 결함을 놓쳤다.
   - (b) 공유방 매칭: `rooms[room_id]→session_id` 단일 상태머신 공유(`:76-77`, `:604-605`), `messages[].seq` 존재(`:557-560`), 과반투표(`:626-645`), `room.html`의 `#statusBar`·`#voteBar`·`#proceedBar`·`updateActionBars(state)`(AWAIT_APPROVAL→voteBar, QUOTED→proceedBar) 존재, `ai_status` 값은 `IDLE/RAG_SEARCHING/QUOTING/GENERATING/DONE`만 있고 `ASKING` 없음 — B §2.5·§4.4의 서술과 일치하며, B가 `ASKING` 추가를 "(추정)"으로 표기한 것도 정확하다. A는 공유방을 전혀 다루지 않았다.
6. **A만 다룬 영역 2건도 실측상 유효하다.**
   - (a) 스마트디폴트+`assumed` 출처표기+고위험 제외(platform·예산상한)(A §2 방법3·§3.2): 현 코드에 없음이 확인되므로 신규 제안으로 유효. B는 `budget_or_time`을 "선택 질문"으로만 두고 추정확정은 다루지 않아, 타이핑 부담 저감책은 A가 더 구체적이다.
   - (b) 명시적 fast-track 키워드("그냥 진행/충분해/빨리…→platform만 확보 후 즉시 게이트", thorough 키워드)(A §4.1): 현 코드에 키워드 분기 없음이 확인되므로 신규 제안으로 유효. B는 "건너뛰셔도 됩니다" 언급만 있고 fast-track 단축경로는 없어 서두르는 사용자 대책이 약하다.
7. **둘 다 놓치거나 얕게 다룬 것 3건 (코드에서 추가 확인):**
   - (a) `QUOTED` 거절 경로(`backend.py:790-792`: 승인 외 입력 → `GATHERING` + "처음부터 다시")도 AWAIT 거절(`:757-759`)과 같은 리셋 결함인데, A는 AWAIT 거절만 명시하고 B는 두 줄번호를 함께 적었으되 QUOTED 쪽의 별도 대책을 명시하지 않았다. 통합안에서 함께 고쳐야 한다.
   - (b) `DONE` 후 입력(`:794-796`)도 `GATHERING`으로 돌리면서 슬롯이 없으므로 새 대화와 이어짐 판별이 불가 — 양쪽 모두 미언급. 슬롯 도입 시 "DONE 후 새 요청이면 슬롯 초기화" 규칙이 필요하다 (추정: 신규 설계).
   - (c) `NIM_TIMEOUT_SEC=25`(`backend.py:30-31`) 존재는 B만 언급하고 폴백(`self_check` 실패 시 `{"ok": True}`)과 연결했다. A의 매턴 NIM 추출안은 호출 횟수 증가→지연 누적 위험이 있는데 지연 대책이 없다. 통합안에서는 NIM 호출을 턴당 최대 1회·전이당 최대 1회로 제한해야 한다 (판정은 코드 실측+설계 판단, 임계값은 추정).

### Thought 4: A에게 줄 구체적 자문(이 부분은 이렇게 보완하면 좋겠다)이 뭔지 정리해야 한다.

**Action 4:** A 문서의 약점/보완점 도출 (B와의 대비 + Thought 3 검증 기반).

**Observation 4:** 아래 "3. A에게 주는 자문" 7개 항목으로 정리 (상세는 해당 섹션 참조). 요지: 규칙-우선 순서로 뒤집기, 지연·환각 가드 정량화, RAG 노출·공유방·QUOTED/DONE 리셋 보완, required 집합을 스키마 역산으로 고정.

### Thought 5: B에게 줄 구체적 자문이 뭔지 정리해야 한다.

**Action 5:** B 문서의 약점/보완점 도출 (A와의 대비 + Thought 3 검증 기반).

**Observation 5:** 아래 "4. B에게 주는 자문" 7개 항목으로 정리 (상세는 해당 섹션 참조). 요지: fast-track 단축경로 추가, 스마트디폴트로 타이핑 부담 저감, 6슬롯 중 게이트 하드조건 축소, self-check 과잉지적·지연 가드, 질문 상한 초과 시 잠정확정 문구.

### Thought 6: 이제 A와 B의 좋은 점을 합쳐서 하나의 최종 권고안을 만들어야 한다.

**Action 6:** 통합안 설계 — 실제로 `backend.py`의 어느 함수/상태를 어떻게 바꾸면 되는지 구체적으로 (마감 2026-09-28 고려, 우선순위 분리).

**Observation 6:** 아래 "5. 최종 통합 권고안"으로 정리. 핵심은 `_process_chat_turn` GATHERING 분기(`:731-744`) 교체 + AWAIT_APPROVAL 승인/거절(`:746-761`) + QUOTED 진행/거절(`:763-792`) 최소수정 + `update_slots`/`next_question` 헬퍼 2개(결정적, LLM 없음) + `self_check_nim` 1개(`call_nim` 재사용, 실패 시 생략) + `build_quote`·`render_design`·`start_codegen`은 본체 무수정·입력만 슬롯 조립값으로 교체. 상세·순서는 해당 섹션 참조.

---

## 3. A에게 주는 자문 (bullet point)

- **NIM-우선 순서를 규칙-우선으로 뒤집어라.** PARALLEL_1_SPEC §4와 REQ-VALIDATE-001 DoD("전부 LLM 판단에 맡기지 않는다")상 1차 판정은 키워드·정규식 결정적 규칙이 맡고, NIM 추출은 2차 보완으로 두는 편이 스펙 정합·감사·재현성에서 유리하다. B §1.2의 4상태(`empty|partial|filled|confirmed`)+규칙표가 좋은 출발점이다.
- **매턴 NIM 호출의 지연·비용 가드를 정량화하라.** 현 `NIM_TIMEOUT_SEC=25`(`backend.py:30-31`) 하에서 매턴 추출은 체감 지연을 누적시킨다. "NIM 호출은 GATHERING 턴당 최대 1회, 실패 시 현행 동작으로 폴백" 같은 상한을 명시하고, 1차는 규칙만으로 다음 질문을 고르게 하라 (B §3.2의 "검사 생략 폴백" 패턴을 추출에도 적용).
- **스마트디폴트의 환각 대책을 B의 3층 구조에 맞춰라.** "말하지 않은 내용을 채움" 위험(A §2 방법1 단점)은 `assumed` 표기만으로 부족하다. 고위험 슬롯 제외(A §3.2)는 유지하되, 추정값은 `basis`·확인요약에 "(가정)" 표기 + 승인 전 self-check 1회로 재검증하는 2차망을 추가하라.
- **required 집합을 스키마 역산으로 고정하라.** A §3.2의 `platform/features≥1/budget_band또는deadline 중 ≥1`은 좋은 초안이지만 "추정" 상태다. B §1.1처럼 BND-3/BND-1/BND-2 required 합집합에서 출발해, 게이트 하드조건은 `platform + features≥1 + existing_ref 확정 + customer_id(대표)`로 좁히고 예산/일정은 선택질문으로 두는 안을 병렬작업 3와 합의하라 (예산 없이는 견적 3안 분별력이 떨어진다는 B 지적과 fast-track 필요라는 A 지적의 절충점).
- **RAG 내부 파일명 노출을 고쳐라 (A가 놓친 B의 지적).** `rag_precheck` 반환(`SRS-2025-014.md` 등)을 그대로 붙이는 현행(`backend.py:739`) 대신 "비슷한 ○○ 프로젝트가 있었어요. 확장/신규 중 어느 쪽인가요?(1/2)" 사람말 템플릿으로 감싸라.
- **공유방·QUOTED/DONE 리셋을 보완하라 (A의 공백).** B §2.5의 `pending_question` 단일화+`seq` 인용 귀속+질의중 투표바 숨김을 수용하고, 거절 복귀는 AWAIT(`:757-759`)뿐 아니라 QUOTED(`:790-792`)·DONE 후 재입장(`:794-796`)까지 "해당 슬롯으로 복귀, 슬롯 유지·`asked_keys` 재사용"으로 통일하라.
- **질문 상한+게이트 일괄확인을 받아들여라.** A의 "최대 2개/턴"은 체감부하 대책으로 유효하지만 무한질의 방지 상한이 없다. B의 "상한 3회(조정가능) 초과 시 잠정확정 후 게이트에서 한 번에 확인"을 안전밸브로 채택하고, "한 턴 1개(기본)/최대 2개(연관 슬롯 묶음일 때만)"로 절충하라.

---

## 4. B에게 주는 자문 (bullet point)

- **서두르는 사용자용 fast-track 단축경로를 추가하라.** B안은 성실 응답자를 전제로 하며 "빨리" 신호 대책이 "선택질문 건너뛰기" 수준에 머문다. A §4.1의 명시적 키워드(`그냥 진행/충분해/빨리/견적 먼저` → `platform`만 확보 후 확인요약과 함께 즉시 게이트, 생략 전제는 견적 근거에 명시)를 하드 가드(REQ-GATE-001 "확인 없이 BND-3 금지" 유지)와 함께 수용하라. 암묵신호(NIM 보조판정)는 required 생략에 쓰지 않는다는 A의 단서도 그대로 가져가라.
- **타이핑 부담 저감책으로 스마트디폴트를 수용하라.** B의 "예시값 먼저 주기"(B §2.2)는 좋지만 여전히 사용자가 쓴다. A §2 방법3의 "추정값 묶음 확인요약 1개 + 맞음 한 마디 확정"을 고위험 제외(플랫폼·예산상한은 추정확정 금지)와 함께 도입하면, 질문 상한 3회와 충돌 없이 턴을 압축할 수 있다.
- **6슬롯 전체를 게이트 하드조건에 걸지 마라.** B §1.2의 "6개 모두 `filled` 이상일 때만 전이"는 스펙상 과도하다: `acceptance`(기능당 1개 매핑 권장)와 `budget_or_time`(DoD상 필수 아님)까지 막으면 fast-track이 성립하지 않고 REQ-VALIDATE-001 DoD("다 차면 질의 없이 게이트")의 "필수" 범위를 넓게 해석한 셈이 된다. 하드조건은 `platform/features/existing_ref/customer_id`로 좁히고 나머지는 선택·추정확정으로 두라 (A §3.2 등급안과 절충).
- **`platform` 단일값 전제의 예외 경로를 스키마 개정과 묶어라.** B §5-3의 "(추정) 단일 선택, 둘 다 요구 시 스키마 개정"은 정확하다. A는 이 문제를 다루지 않았다. "웹+앱 둘 다" 응답이 오면 현 enum(`web|android`)에서 제외되기 전에 1차는 단일 선택+확인요약에 전제 명시, 개정은 마감 후 과제로 미루는 2단계 계획을 명시하라.
- **self-check의 과잉지적·지연·재현성 가드를 설계에 고정하라.** B §3.2 대책(사소한 것 지적금지·`missing` 최대 2건·전이당 1회·실패 시 생략·`session["self_check"]` 로그)은 방향이 맞다. 여기에 A 관점의 한 줄을 추가하라: self-check 프롬프트에 `build_quote` JSON 강제 패턴(`backend.py:233-253`)을 재사용하고, 지적 수용은 "첫 1건만 질문, 나머지는 게이트 확인요약에 (미확인) 표기로 이관"으로 못박아 질문 증가를 차단하라.
- **질문 상한 초과 시 문구를 구체화하라.** "잠정 확정 후 게이트에서 한 번에 확인"(B §2.1-5)만 있고 문구가 없다. A §3.1의 확인요약 형식(확정값+추정값 구분 표기)을 빌려 예시 1개를 박아라. 예: `지금까지: 웹(확정) / 예약·결제(확정) / 알림톡(가정·제외 전제) (3/4). 이대로 견적 낼까요? (진행/수정)`.
- **반려 시 "어느 항목" 질문의 선택지를 고정하라.** B §4.3의 "1번 기능 2번 견적방향 3번 기타"는 좋은 시작이다. A §4.2의 "슬롯 상태 보여주기+번호 선택"과 합쳐 `1번 기능 2번 플랫폼 3번 예산/일정 4번 기타(자유서술→슬롯 재추출 입력으로만 사용)` 4지선다로 고정하고, 자유서술 직확인을 금지(REQUIREMENTS §9)하는 한 줄을 추가하라.

---

## 5. 최종 통합 권고안 (구현 우선순위 포함)

### 5.1 통합 설계 (바꿀 위치: 함수·상태 단위)

**S0. 세션 확장 (로직 무변경, `additionalProperties` 허용·`setdefault` 마이그레이션):**

```python
session["slots"] = {
  "platform":      {"status": "empty", "value": None, "note": ""},  # required·고위험(추정확정 금지)
  "features":      {"status": "empty", "value": [],   "note": ""},  # required(≥1)
  "existing_ref":  {"status": "empty", "value": None, "note": ""},  # required(확장/신규 확정)
  "customer_id":   {"status": "filled","value": session_id_or_room_rep, "note": ""},
  "budget_or_time":{"status": "empty", "value": None, "note": ""},  # 선택(건너뛰기 가능)
  "acceptance":    {"status": "empty", "value": [],   "note": ""},  # 선택(게이트에서 보완 가능)
}
session["slots_assumed"] = {}    # A안: 추정값 출처 표기 (확인요약·basis에 "(가정)" 표시)
session["pending_question"] = None  # B안: {"slot","options","seq"} 단일화
session["asked_keys"] = []       # A안: 중복 질문 방지
session["ask_count"] = 0         # B안: 상한 3 (추정·조정 가능)
session["self_check"] = None     # B안: 감사 로그용
```

**S1. `update_slots(slots, user_text)` (신규 헬퍼, 결정적 규칙만·LLM 없음 — B안 우선, A안은 2차):**

- `platform`: "웹/홈페이지/사이트"→web, "앱/안드로이드/플레이스토어"→android. 혼재·전무→`partial`.
- `features`: 불릿·쉼표 분리 ≥1개. "관리자/통계/알림"+"~도/~있었으면" 패턴은 `partial`로 질의행.
- `existing_ref`: `rag_precheck` 1회(첫 진입만) + 고객 확장/신규 선택 시 `confirmed`.
- `budget_or_time`: 숫자+단위(만원·원·주·일) 패턴. 없어도 게이트 가능.
- 자유서술은 슬롯에 직접 쓰지 않고 재추출 입력으로만 사용 (REQUIREMENTS §9).

**S2. `next_question(slots)` (신규 헬퍼 — 한 턴 1개 기본·최대 2개, 옵션 3개+추천):**

- 순서: `platform` → `existing_ref`(RAG hit 시만) → `features` 쪼개기(예/아니오, `confirmed_items` 1개 단위) → `budget_or_time`(선택·"건너뛰셔도 됩니다" 명시).
- 형태: 닫힌 질문=번호 객관식+추천, 반열린=예/아니오 쪼개기, 열린=예시값 선제시(`300만원대/2주`). 한 응답 300자·불릿 4개 이내(추정).
- 매 질문은 "지금까지 요약 + 다음 질문" 2단 + 진행률 `(n/m)` (B §2.3). RAG source명은 사람말 템플릿으로 감싸 노출 금지.

**S3. `self_check_nim(slots_summary)` (신규 헬퍼, `call_nim` 재사용·전이당 최대 1회):**

- `{"ok": true}` 또는 `{"ok": false, "missing": [...]}` JSON만 반환. 실패·타임아웃 시 `{"ok": true}` 폴백(검사 생략, 대화 차단 금지).
- 프롬프트에 "견적·시안·코드생성에 지장 없는 사소한 것은 지적 금지", `missing` 최대 2건 수용·첫 1건만 질문·나머지는 확인요약에 (미확인) 이관.

**S4. `_process_chat_turn` GATHERING 분기(`backend.py:731-744`) 교체:**

```
GATHERING 수신:
  1. fast-track 키워드("그냥 진행/충분해/빨리/견적 먼저") → platform만 확보(없으면 platform 1문만) 후 확인요약 + AWAIT_APPROVAL. 생략 슬롯은 디폴트+(가정) 표기, 견적 basis에 전제 명시.
  2. 첫 진입이면 rag_precheck 1회 → existing_ref 후보 기록 → platform 질문 1개만 하고 잔류 (게이트 직행 금지).
  3. 그 외: update_slots 반영 → 미충족 슬롯 1개 질문 + 요약 (ask_count+1).
  4. required(platform·features≥1·existing_ref) 충족이면: 확인요약(확정/(가정) 구분) → self_check 최대 1회 → ok면 AWAIT_APPROVAL / missing이면 해당 슬롯으로 복귀 (상한 초과 시 잠정확정 후 게이트).
```

**S5. AWAIT_APPROVAL(`:746-761`)·QUOTED(`:763-792`) 최소 수정:**

- 승인 시: `build_quote(last_request 원문)` 대신 슬롯 조립 텍스트(`platform+features+acceptance+budget_or_time+(가정) 전제`)를 전달. `build_quote` 본체 무수정.
- 거절 시(AWAIT/QUOTED 공통): 슬롯 유지 + "어느 항목을 고칠까요? 1번 기능 2번 플랫폼 3번 예산/일정 4번 기타"로 해당 슬롯만 복귀 (처음부터 전체 재질문 금지).
- QUOTED 진행 시: `render_design(id, "web", [원문], ...)`(`:773-774`)의 고정값을 슬롯값(`platform`, `features`/`confirmed_items`)으로 교체, `start_codegen` 입력도 슬롯 조립 스펙으로 교체. 함수 본체 무수정.
- DONE 후(`:794-796`): 새 요청이면 슬롯 초기화 후 GATHERING (신규 규칙).

**S6. 공유방 최소 추가 (B안 그대로):** `pending_question`+`seq` 인용 귀속, 질의중 투표바 숨김·투표중 질의입력 분리(`updateActionBars`에 질의바 1종 추가), `ai_status` 재사용 또는 `ASKING` 1종 추가 (추정·프론트 1줄).

### 5.2 구현 우선순위 (1차 완성 목표 2026-09-28 기준)

**마감 전 필수 (P0 — 데모·DoD 직결):**

1. S1 `update_slots` + S2 `next_question` + S4 게이트 조건(required 3종) — 1턴 직행 누락을 막는 최소 장치. REQ-VALIDATE/ASK DoD의 핵심.
2. 확인요약(확정/(가정) 구분) + S5의 `platform`/`features` 하류 교체 — BND-2/BND-3 스키마 위반 해소. 시안·견적 데모 품질에 직결.
3. A §4.1 명시 키워드 fast-track ("그냥 진행" → platform 확보 후 즉시 게이트 + 생략 전제 명시) — 마찰 체감 개선 중 최저비용.
4. 거절 시 항목별 복귀(AWAIT+QUOTED) + 슬롯 유지 — REQ-GATE-001 "처음부터 다시 묻지 않음" 충족. 평가 시나리오(반려 경로)에 노출됨.
5. RAG 파일명 사람말 래핑 — 내부명 노출은 데모 감점 요인. 5줄 템플릿 수정 수준.

**마감 후로 미뤄도 되는 것 (P1 — 안정화·고도화):**

6. S3 self-check 2차망 — 규칙+질의가 먼저 안정된 뒤. 단독 도입 시 과잉지적·지연 리스크.
7. 스마트디폴트 고도화(전 슬롯 추정·`acceptance_criteria` 템플릿+NIM 다듬기) — P0 확인요약의 확장판.
8. 암묵신호(장문·단답연속) 판정 + thorough 모드(한 턴 1항목 늦추기) — 실측 로그 후 조정.
9. 타이머 기반 에스컬레이션(reqpipe G12, PARALLEL_1_SPEC §9) — 현 코드에 타이머 없음이 확인됨. 공수 별도.
10. `platform` 배열화(웹+앱 둘 다) 스키마 개정(BND-2·BND-3) — 현 enum 단일값 전제 유지, 1차는 단일선택+전제명시로 대응.
11. 질문 상한·300자·불릿수 등 임계값 튜닝 — 파일럿 대화 로그(A/B) 후 확정.

### 5.3 DoD 매핑 (통합안이 스펙을 닫는지)

| DoD | 닫히는 지점 |
|---|---|
| REQ-INTAKE-001 (슬롯 정리+출처) | S0 slots + 원문 발췌 `note` 보관 |
| REQ-VALIDATE-001 (불명확 검출/다 차면 직행) | S1 결정적 규칙 + S4 required 충족→self-check→게이트 |
| REQ-ASK-001 (3개+추천/자유서술 재질문) | S2 형태별 질문 + 재질문 1회 상한 |
| REQ-GATE-001 (확인 없이 BND-3 금지/동일 id/항목복귀) | 승인 본체 유지 + S5 해당 슬롯 복귀 |
| REQ-QUOTE-001 (근거+재현성) | S5 슬롯 조립 입력 + (가정) 전제의 `basis` 기록 + `self_check` 로그 |
| REQ-RAG-001 (best-effort, 임의가정 금지) | 첫 진입 1회 + 실패 시 신규 폴백 유지 + 사람말 래핑 |

### 5.4 확실하지 않은 점 (추정 명시)

- required 하드조건을 `platform·features≥1·existing_ref`로 좁히는 것은 본 리뷰의 절충 제안이며 **(추정)** — 병렬작업 3(스펙생성 최소입력) 합의 후 확정 필요.
- "한 턴 1개 기본·최대 2개", "질문 상한 3회", "300자·불릿 4개"는 UX 일반론 기반 **(추정)** — 실측 없이 확정 불가.
- `platform` 단일값·`budget_or_time` 선택 취급은 현 스키마 enum 실측에 근거하나 "둘 다" 수요 빈도는 **(추정)** — 로그 후 스키마 개정 판단.
- self-check 지연·NIM 추출 지연의 체감 영향은 `NIM_TIMEOUT_SEC=25` 실측과 폴백 설계로 완화 가능하나 실측 전 확정 불가 **(추정)**.
- DONE 후 슬롯 초기화 규칙·`asked_keys` 재사용 수명·투표와 질의 분리 시 경계 utterance("네"가 답변인지 투표인지)는 본 리뷰의 신규 제안으로 **(추정)** — 구현 시 방 로그로 검증 필요.
