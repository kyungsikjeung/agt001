# 요구사항 도출( elicitation ) UX 분석 — 분석가 B

> 작성일: 2026-09-23 / 작성자: 분석가 B (독립 분석, A의 결과물 미열람)
> 대상: agt001, `backend.py` 상태머신 GREETING→GATHERING→AWAIT_APPROVAL→QUOTED→GENERATING→DONE
> 제약: 코드 수정 없음, 본 문서는 분석·설계 제안만 담는다

## 핵심 결론 요약 (3~4줄)

**지금 GATHERING은 사용자가 뭐라고 말하든 `rag_precheck` 한 번 하고 곧바로 AWAIT_APPROVAL로 넘어가므로(후속 질문 없음), ④접수·⑤검증·⑥질의가 사실상 생략되어 요구사항 누락이 구조적으로 불가피하다.**
**그래서 완전성은 LLM 임기응변이 아니라 스키마(`gate_to_spec`/`gate_to_quote`/`quote_to_design`)에서 역산한 필수 슬롯 체크리스트 + 결정적 규칙 검증으로 기계적으로 보장하고,**
**불편함은 "한 번에 하나씩·객관식·예/아니오·진행률" 같은 대화 UX 패턴과 승인 전 NIM self-check 게이트로 줄이는 것을 제안한다.**
**공유방(room)은 상태머신을 복제하지 않고 질문-답변 매칭(pending_question + seq 인용) + 과반 투표 유지만으로 꼬임을 막는다.**

---

## 0. 현재 상태 정확히 파악 (실측 기반)

### 0.1 `backend.py` GATHERING 처리 — 후속 질문 없음 (확인됨)

`_process_chat_turn()` (`backend.py:689-805`)의 해당 분기 (`backend.py:731-744`):

```python
elif state in ("GREETING", "GATHERING"):
    ...
    rag_result = rag_precheck(user_text)
    session["last_request"] = user_text
    reply = (
        f"{rag_result}\n\n"
        f"요청하신 내용을 검토했습니다. 이 요구사항으로 견적을 진행할까요? (승인/거절로 답해주세요)"
    )
    session["state"] = "AWAIT_APPROVAL"
```

확인된 사실:

1. 사용자가 무슨 말을 하든(한 단어든 장문이든) `rag_precheck(user_text)`를 딱 한 번 호출하고, 원문 그대로 `session["last_request"] = user_text`에 저장한 뒤 즉시 `AWAIT_APPROVAL`로 전이한다.
2. 후속 질문 루프가 없다. `last_request`를 파싱해서 슬롯을 채우거나, 빠진 정보를 되묻는 코드가 전혀 없다.
3. `build_quote()` (`backend.py:225-256`)도 `session.get("last_request", "")` 원문을 그대로 NIM 프롬프트에 넣어 견적을 만든다. 즉 정제된 `confirmed_items`/`platform`/`acceptance_criteria`가 존재하지 않고, 견적·시안·코드생성 전부 원문 한 줄에 의존한다.
4. `render_design()` 호출 시 (`backend.py:773-775`)도 `features=[last_request 원문 1개]`, `platform="web"` 고정으로 넘긴다. 스키마상 `platform: "web"|"android"` 판별, `features` 분해가 생략되어 있다.
5. 거절 시 (`backend.py:757-759`, `790-792`) "처음부터 다시"로만 돌아가고, REQ-GATE-001 DoD의 "반려 시 원래 애매했던 항목으로 정확히 되돌아간다(처음부터 다시 묻지 않음)"를 만족하지 못한다.

한마디로 현 구현은 TEAM_A_SPEC의 ④접수·⑤검증·⑥질의를 건너뛰고 ③RAG→⑦게이트로 직행하는 단축 경로다. D0~D1 "고정 응답/가짜 통과" 단계의 잔재로 보이며(TEAM_A_SPEC §4~§6 "개발 순서" 참조), 스펙상 정식 동작이 아니다.

### 0.2 스펙이 요구하는 것 (DoD 정리)

| REQ | 핵심 DoD | 현재 충족 여부 |
|---|---|---|
| REQ-INTAKE-001 | 서로 다른 표현의 같은 요구가 같은 슬롯으로 정리 + 항목마다 원문 출처 | 미충족 (`last_request` 원문 저장만) |
| REQ-VALIDATE-001 | 범위 불명확 표현("관리자 페이지" 등)을 애매 항목으로 검출 / 필수 항목이 다 차면 질의 없이 게이트 직행 | 미충족 (검증 없음, 항상 게이트 직행이라 "질의 없이 직행"과 겉모습만 같음) |
| REQ-ASK-001 | 애매 항목마다 옵션 3개+추천 1개 / 옵션 밖 자유 서술에는 재질문 | 미충족 (질의 자체가 없음) |
| REQ-GATE-001 | 고객 확인 없이 BND-3 발화 금지 / BND-2·BND-3 동일 `requirement_id` / 반려 시 해당 항목으로 복귀 | 부분 충족 (승인 문자는 확인하나, 확정안 내용이 빈약 + 반려 시 처음부터) |
| REQ-QUOTE-001 | 모든 견적에 근거 문구 + 같은 입력→같은 견적(재현성) | 부분 충족 (`basis`는 있으나 원문 의존이라 재현성·정합성 약함) |

### 0.3 참고 문서와의 관계 (참고만, 답은 새로 작성)

- `UIUX_DESIGN_REFERENCE.md`: 그룹 채팅 UI(아바타+이름, 전원용 AI 상태, 이모지 투표) 패턴집. 본 문서는 그 UI 패턴이 아니라 **질문 내용·순서·완전성 보장 로직**에 집중하므로 겹치지 않는다.
- `MULTIUSER_CHAT_DESIGN.md`: 공유방(room) 데이터 모델·폴링·과반 투표 설계. 본 문서는 그 위에 얹는 **질문-답변 매칭 꼬임 방지** (§2.5)만 추가 제안한다.
- `static/room.html` + `backend.py` ROOMS (`590-686`): 방 생성·입장·4초 폴링·`ai_status` 브로드캐스트·과반 투표는 이미 구현되어 있다(확인됨). 본 설계는 이 기반을 전제로 한다.

---

## 1. 완전성 보장: 체크리스트/스키마 기반 접근

핵심 주장: **완전성은 LLM의 "눈치"가 아니라 스키마에서 역산한 체크리스트의 기계적充足 여부로 판단해야 한다.**

### 1.1 왜 스키마 역산인가

하류(BND-2→시안, BND-3→코드생성)가 요구하는 필드가 곧 "빠지면 사고 나는" 필드다. 세 스키마의 required를 합치면 최소 수집 집합이 그대로 나온다:

| 스키마 | required | 도출되는 필수 슬롯 |
|---|---|---|
| `gate_to_spec.schema.json` (BND-3) | `requirement_id`, `confirmed_items`, `platform`, `acceptance_criteria` | 플랫폼(web/android), 확정 항목 목록, 인수조건 |
| `gate_to_quote.schema.json` (BND-1) | `requirement_id`, `confirmed_items`, `customer_id` | 고객 식별자(1:1은 session, room은 대표+`approved_by`) |
| `quote_to_design.schema.json` (BND-2) | `requirement_id`, `platform`, `features`, `quote.{amount, basis}` | 핵심 기능 목록, 견적 근거 |

여기에 견적 산정(TEAM_A_SPEC §7 "항목별 공수/난이도 매핑")에 필요한 것을 더하면, 실전 최소 슬롯은 아래 6개로 닫힌다 (추정 아님 — 스키마+스펙의 합집합):

```
ELICIT_SLOTS = {
  "platform":       web | android | (추정: 둘 다 필요하면 web+android지만 현 스키마 enum은 단일값이라 1차는 단일 선택),
  "features":       confirmed_items와 동일 소스, 최소 1개 이상 (빈 리스트 금지),
  "acceptance":     acceptance_criteria, 최소 features당 1개 매핑 권장,
  "budget_or_time": 견적 basis 산정에 필요한 예산/일정 힌트 (없으면 견적 3안의 분별력이 떨어짐),
  "existing_ref":   RAG hit 여부 + 확장/신규 확정 (REQ-RAG-001 분기 확정값),
  "customer_id":    세션/방 대표 식별자 (BND-1 required),
}
```

`requirement_id`는 이미 발급되므로 수집 대상이 아니다.

### 1.2 수집 상태 기계 (결정적 규칙, LLM 이전에)

각 슬롯은 `empty | partial | filled | confirmed` 4값 중 하나를 갖고, 전이는 **정규식·스키마 검증 같은 결정적 규칙이 먼저** 판정한다 (TEAM_A_SPEC §4 "LLM 판정 금지, 결정적 규칙 우선" 원칙 그대로):

- `platform`: 메시지 내 "웹/홈페이지/사이트"→web, "앱/안드로이드/플레이스토어"→android 키워드 매칭. 양쪽 키워드 혼재·전무 → `partial` → ⑥질의로.
- `features`: 불릿·쉼표 분리 후 최소 1개. "관리자 페이지도 있었으면" 같은 범위 불명확 표현(REQ-VALIDATE-001 예시)은 키워드 리스트("관리자", "통계", "알림" 등 + "~도", "~있었으면" 종결 패턴)에 걸리면 `partial`로 표시하고 질의로 넘긴다.
- `acceptance`: features 각 항목에 대응 문장이 있는지 기계적으로 센다. 없으면 질의 생략 가능하되 self-check (§3)에서 보완.
- `budget_or_time`: 숫자+단위(만원·원·주·일) 패턴. 없어도 진행은 가능하나(DoD상 필수는 아님), 있으면 견적 품질이 올라가므로 "선택 질문"으로 분류 (§2.2).
- `existing_ref`: `rag_precheck` 결과 + 고객의 확장/신규 선택이 둘 다 있어야 `confirmed`.

게이트 통과 조건은 단순하다: **6개 슬롯이 모두 `filled` 이상일 때만 AWAIT_APPROVAL로 전이 가능.** 하나라도 `empty/partial`이면 GATHERING에 잔류하고 해당 슬롯의 질문만 한다. 이것이 "빠진 것만 되묻는" 방식의 정식 정의다.

### 1.3 "빠진 것만 되묻기"가 누락을 막는 이유

현재 구조의 실패 모드는 "못 들은 것을 모른 채 넘어감"이다. 체크리스트 방식은 실패 모드를 뒤집는다: **못 들은 것이 있으면 상태 전이 자체가 막힌다.** LLM이 똑똑해질 필요가 없고, 슬롯 테이블 한 줄이면 리뷰어가 완전성을 감사할 수 있다. `confirmed_items`가 원문 1개가 아니라 슬롯에서 조립된 리스트가 되므로, BND-2 `features`·BND-3 `acceptance_criteria` 유실(REQ-CODEGEN-001 DoD "요구사항 유실 없음")도 같은 지점에서 차단된다.

한계도 명시한다: 키워드 규칙은 표현 변형(동의어·은유)에 약하다. 그래서 규칙은 "확정"이 아니라 "질의 트리거"까지만 담당하고, 최종 해소는 §2의 객관식 질문 + §3의 self-check가 맡는 3층 구조로 설계한다 (규칙→질의→자가점검).

---

## 2. 불편 최소화: 대화 흐름/텍스트 UX 설계

### 2.1 배치 원칙: 한 번에 하나씩, 부담이 가벼운 순서로

한 번에 여러 개를 묻는 것은 답변율을 떨어뜨린다. 제안하는 질문 배치 규칙:

1. **한 턴에 한 슬롯만 묻는다.** 특히 첫 질문은 가장 답하기 쉬운 것(`platform`: "웹으로 만드실까요, 앱으로 만드실까요?")부터. 예산 같은 민감·추상 질문은 뒤로 미룬다.
2. **이미 답한 것은 다시 묻지 않는다.** 슬롯이 `filled`가 되면 그 슬롯의 질문은 다시 꺼내지 않는다(반려 시에도 해당 항목만 — §0.1-5 지적의 수정).
3. **선택 질문과 필수 질문을 구분해 말한다.** 예산/일정은 "건너뛰셔도 됩니다"라고 명시한다. 필수인데 건너뛰려 하면 그때만 붙잡는다.
4. **진행률을 매번 보여준다.** 예: "(2/5) 핵심 기능은 알겠습니다. 다음은 …". REQ-CHAT-001 DoD의 "처리 중 안내"와 같은 맥락으로, 끝이 보이는 대화는 이탈이 적다. `room.html`의 `#statusBar` 패턴(확인됨)을 질문 진행률 표시에도 재사용할 수 있다 (추정: 프론트 1줄 확장 수준).
5. **질문은 최대 3회(추정: 임계값은 조정 가능)까지만 하고, 그 이상은 잠정 확정 후 게이트에서 한 번에 확인받는다.** 무한 질의가 "지루함"의 주범이므로, 회수 상한 + 게이트 일괄 확인이 안전밸브다.

### 2.2 답변 부담을 낮추는 질문 형태

TEAM_A_SPEC §5·REQ-ASK-001의 "옵션 3개+추천"을 그대로 쓰되, 형태를 슬롯 종류에 맞게 바꾼다:

- **플랫폼·확장/신규 같은 닫힌 질문** → 번호 객관식 + 추천 표시. 예:
  `1번 웹 2번 안드로이드 — 보통은 1번 웹으로 시작하세요 (추천). 번호만 보내주세요.`
- **기능 범위 같은 반열린 질문** → 예/아니오로 답할 수 있게 쪼갠다. "관리자 페이지도 있었으면"을 통째로 묻지 말고 `관리자 승인 기능이 필요하신가요? (네/아니오)` 로 쪼갠다. 쪼개는 단위는 `confirmed_items` 1개 단위.
- **예산/일정 같은 열린 질문** → 예시값을 먼저 준다. `(예: 300만원대 / 2주)` — 빈칸이 아니라 "고치기" 형태로 만들어 부담을 낮춘다.
- **자유 서술이 오면** REQ-ASK-001 에러 처리대로 옵션 3개+추천으로 재질문하되, 재질문은 1회로 제한하고(무한 루프 방지) 그래도 안 맞으면 그 원문을 `partial` 메모로 붙여 게이트에서 사람이 확인하게 한다.

### 2.3 지루함 방지: 요약-확인 리듬

매 질문을 단독으로 던지지 말고, **"지금까지 정리 + 다음 질문" 2단 구조**로 묶는다:

```
지금까지: 웹 / 쇼핑몰(로그인·장바구니·결제) (3/5)
다음: 관리자 승인 기능도 넣을까요? (네/아니오)
```

이렇게 하면 사용자는 "내 말이 반영되고 있다"는 피드백을 매 턴 받고, 대화가 앞으로 나간다는 감각이 유지된다. `session["last_request"]` 원문 누적 대신 슬롯 요약문을 누적 표시하는 것이므로, 구현도 슬롯 테이블 렌더링 1개면 된다.

### 2.4 텍스트 길이·어조 규칙 (채팅에 맞게)

- 한 응답 300자 이내, 불릿 4개 이내를 권장한다 (추정: 모바일 채팅 가독성 기준, 조정 가능).
- 전문용어 금지 ("BND", "acceptance_criteria" 같은 내부어를 사용자에게 노출하지 않는다).
- RAG 결과(`기존 프로젝트: SRS-2025-014.md` 같은 내부 source명)는 그대로 노출하지 말고 사람말로 바꾼다. 예: `비슷한 쇼핑몰 프로젝트가 있었어요. 확장하실래요, 새로 만드실래요? (1번 확장 2번 신규)`. 현재 `rag_precheck` 반환 문자열을 그대로 붙이는 방식(`backend.py:739`)은 내부 파일명이 노출되는 UX 결함이므로 함께 고칠 것을 제안한다.

### 2.5 공유방(room) 질문-답변 매칭 꼬임 방지

`ROOMS`는 방당 상태머신 1개를 공유하므로(확인됨: `rooms[room_id]`→`session_id` 1개), 여러 명이 동시에 답하면 "누가何에 답했는지"가 꼬인다. 제안:

1. **미결 질문 단일화 (`pending_question`)**: 세션에 `pending_question = {slot, options, seq}` 1개만 둔다. 새 질문을 내기 전에 이전 질문이 해소됐는지 먼저 본다. 방에 동시에 질문이 2개 이상 떠 있는 상태를 원천 금지한다.
2. **답변 귀속은 seq 인용으로**: 각 AI 질문 메시지에 `seq`(이미 `messages[].seq` 존재 — 확인됨)를 붙이고, 참여자 답변은 "가장 최근 미결 질문에 대한 답"으로 귀속한다. 엇갈린 답(질문 A가 떴는데 누군가 엇박자로 이전 화제에 답)이 오면, 키워드·번호 매칭으로 어느 질문에 대한 답인지 판별하고, 판별 불가면 `partial`로 두고 재확인 1회 ("○○님의 답변이 어느 항목인지 모르겠어요. 번호로 다시 보내주세요").
3. **투표와 질의의 분리**: AWAIT_APPROVAL의 과반 투표(구현됨 — `backend.py:626-645`)와 GATHERING의 슬롯 답변은 혼동되므로, 상태바·`voteBar`/`proceedBar`(구현됨 — `room.html:109-118`)처럼 **질의 중에는 투표 바를 숨기고, 투표 중에는 질의 입력을 투표 키워드로만 해석**한다. 이미 `updateActionBars(state)`가 상태별 바 표시를 하므로(확인됨), 질의 상태(`GATHERING`+`pending_question`)용 질문 바 1종만 추가하면 된다 (추정: 프론트 소규모 확장).
4. **화자 표시 유지**: `room.html`의 아바타+닉네임+`BOT` 뱃지(확인됨)를 그대로 쓰고, AI 질문 메시지에는 "○○ 슬롯 질문" 라벨을 붙여 "누가何에 답해야 하는지"를 방 전원이 보게 한다.

---

## 3. 승인 전 자동 완전성 검증: NIM self-check 패턴

### 3.1 제안: AWAIT_APPROVAL 전이 직전의 self-check 게이트

GATHERING→AWAIT_APPROVAL 전이 조건에 슬롯充足(§1.2) 외에 **NIM에게 "빠진 정보가 있는지 스스로 점검"시키는 1회 호출**을 추가한다. 순서:

```
슬롯充足(결정적) → NIM self-check 1회 → 통과면 AWAIT_APPROVAL / 지적 있으면 해당 슬롯으로 복귀
```

self-check 프롬프트는 구조화 JSON만 반환하게 한다 (기존 `build_quote`의 JSON 강제 패턴 — `backend.py:233-253` — 재사용):

```
너는 요구사항 검수자다. 아래 슬롯 요약을 보고 빠진/모호한 정보를 JSON으로만 답해라.
형식: {"ok": true} 또는 {"ok": false, "missing": [{"slot": "...", "question": "..."}]}
슬롯 요약: {...}
```

`ok:true`면 게이트로, `ok:false`면 `missing`의 첫 1건만 질문한다(한 번에 하나씩 — §2.1). 호출은 전이당 최대 1회로 제한해 무한 루프를 막는다.

### 3.2 검토: 이 패턴의 타당성과 위험

타당한 점:

- 결정적 규칙이 못 잡는 모호함(은유·생략·상충)을 잡는 2차망이 된다. 규칙→질의→자가점검 3층 중 마지막 층.
- `call_nim()` 1회 재사용이라 새 인프라가 필요 없고, JSON 파싱 실패 시 처리(자유 텍스트 폴백)도 `build_quote`에 이미 구현된 패턴이 있다.
- REQ-VALIDATE-001 DoD "필수 항목이 모두 채워졌으면 질의 없이 바로 게이트로"와 충돌하지 않는다: self-check는 추가 질문이 아니라 **게이트 가기 전 마지막 확인**이며, `ok`면 즉시 게이트로 간다.

위험과 대책:

- **NIM 장애·지연**: `/chat` 동기 경로에 호출 1회가 추가되므로 체감 지연이 는다. 대책: 타임아웃(`NIM_TIMEOUT_SEC`, 확인됨) 내 실패 시 "검사 생략하고 게이트로" 폴백한다. 검사가 대화를 막지 않게 한다(REQ-RAG-001 DoD의 best-effort 철학과 동일).
- **LLM 과잉 지적(지적하고 싶어하는 편향)**: 사소한 것까지 `missing`으로 돌려주면 질문이 다시 늘어 (§2의 불편과 정면 충돌). 대책: 프롬프트에 "견적·시안·코드생성에 지장이 없는 사소한 것은 지적하지 마라"를 명시하고, `missing`은 최대 2건까지만 수용·그 이상은 무시한다.
- **재현성(REQ-QUOTE-001 DoD)**: self-check가 매번 다른 지적을 하면 같은 입력→다른 흐름이 된다. 대책: 1차 판정은 결정적 슬롯(§1.2)이 하고 self-check는 보조로만 쓰며, 지적 내용은 로그(`session["self_check"]`)에 남겨 재현·감사 가능하게 한다.

종합: self-check는 **단독 완전성 수단이 아니라 결정적 체크리스트의 보완 2차망**으로 쓸 때 타당하다. 단독으로 쓰면 REQ-VALIDATE-001의 "전부 LLM 판단에 맡기지 않는다" 원칙에 어긋나므로, 반드시 §1과 묶어서 도입할 것을 권고한다.

---

## 4. 이 프로젝트에 구체적으로 어떻게 적용할지 (설계 수준)

코드 수정 없이, 바꿀 위치와 내용을 함수·상태 단위로 지정한다.

### 4.1 `session` 구조 확장 (스키마 추가, 로직 무변경 가능 — `additionalProperties` 허용)

```python
session["slots"] = {  # §1.1 ELICIT_SLOTS, 값: empty|partial|filled|confirmed + 메모
  "platform": {"status": "empty", "value": None, "note": ""},
  "features": {"status": "empty", "value": [], "note": ""},
  "acceptance": {"status": "empty", "value": [], "note": ""},
  "budget_or_time": {"status": "empty", "value": None, "note": ""},
  "existing_ref": {"status": "empty", "value": None, "note": ""},
  "customer_id": {"status": "filled", "value": session_id, "note": ""},
}
session["pending_question"] = None  # {"slot":..., "options": [...], "seq": ...} (§2.5-1)
session["ask_count"] = 0            # 질문 상한 (§2.1-5, 추정: 상한 3)
session["self_check"] = None        # §3 로그용
```

`save_sessions()`/`load_sessions()` 직렬화에 자동 포함되므로 저장 로직 변경 불필요. 구 세션(필드 없음)은 `setdefault`로 마이그레이션.

### 4.2 `_process_chat_turn()` GATHERING 분기 재설계 (`backend.py:731-744` 교체 대상)

현재 "rag→즉시 게이트"를 아래 순서로 바꾼다:

```
GATHERING 수신:
  1. 첫 진입(pending_question 없음 + slots 전부 empty)이면: rag_precheck 1회 → existing_ref 후보 기록
     → platform 질문 1개만 하고 잔류 (게이트로 가지 않음).
  2. 그 외: 들어온 답을 update_slots() (결정적 규칙, §1.2)로 반영
     → pending 해소되면 다음 빈 슬롯 질문 1개 (객관식/예·아니오/예시값, §2.2) + 지금까지 요약 (§2.3).
  3. 전부 filled 이상이면: self_check_nim() 최대 1회 (§3.1)
     → ok면 AWAIT_APPROVAL (승인 요청문 + 확정안 요약 첨부)
     → missing이면 해당 슬롯으로 복귀 (ask_count+1, 상한 초과 시 잠정 확정 후 게이트).
```

신규 함수 3개 (전부 `backend.py` 내, 상태머신 밖 헬퍼):

- `update_slots(slots, user_text) -> slots`: 키워드·숫자 패턴 등 결정적 규칙만. LLM 호출 없음.
- `next_question(slots) -> str | None`: 첫 번째 미충족 슬롯에 대한 질문문 1개 생성 (옵션 3개+추천 템플릿 포함).
- `self_check_nim(slots_summary) -> {"ok": bool, "missing": [...]}`: `call_nim` 재사용, 실패 시 `{"ok": True}` 폴백 (검사 생략).

`rag_precheck`·`build_quote`·`render_design` 본체는 손대지 않는다. 바뀌는 것은 호출 시점과 입력(원문→슬롯 조립값)뿐이다.

### 4.3 AWAIT_APPROVAL·QUOTED 분기 최소 수정

- AWAIT_APPROVAL 승인 시 (`backend.py:746-756`): `build_quote(last_request 원문)` 대신 슬롯 조립 텍스트(`platform + features + acceptance + budget_or_time`)를 넘긴다. `quote` 품질·재현성이 올라간다.
- 거절 시 (`backend.py:757-759`): `GATHERING`으로 돌리되 slots는 유지하고, 거절 사유 1개를 `pending_question`으로 ("어느 부분이 마음에 안 드셨나요? 1번 기능 2번 견적 방향 3번 기타") 물어 해당 슬롯만 되묻는다. REQ-GATE-001 DoD "처음부터 다시 묻지 않음" 충족.
- QUOTED 진행 시 (`backend.py:773-775`): `platform="web"` 고정·`features=[원문]` 대신 슬롯값(`platform`, `features`)을 `render_design`·`start_codegen`에 넘긴다. BND-2·BND-3 스키마 정합이 여기서 맞춰진다.
- room 투표 로직 (`backend.py:626-645`, 구현됨)은 그대로 두고, GATHERING 질의 답변은 투표 판정에서 제외한다(§2.5-3).

### 4.4 공유방(room) 최소 추가

- `pending_question` 1개 + 질문 메시지 `seq` 인용 귀속 (§2.5-1·2). `ROOMS` 구조·폴링·`ai_status`는 변경 없음.
- 질의 상태 표시 1종 추가 (추정: `ai_status`에 `ASKING`을 넣거나 기존 `THINKING` 재사용 — 어느 쪽이든 프론트 `#statusBar` 라벨 1줄).
- RAG source명 노출 제거 (§2.4): `rag_precheck` 반환을 그대로 붙이지 말고 사람말 템플릿으로 감싼다.

### 4.5 DoD 매핑 (이 설계가 스펙을 닫는지)

| DoD | 닫히는 지점 |
|---|---|
| REQ-INTAKE-001 (슬롯 정리+출처) | §4.1 slots + 원문 발췌를 `note`에 보관 |
| REQ-VALIDATE-001 (불명확 검출 / 다 차면 직행) | §1.2 결정적 규칙 + §4.2-3 전부 filled→self-check→게이트 |
| REQ-ASK-001 (3개+추천 / 자유서술 재질문) | §2.2 형태별 질문 + §4.2 `next_question` |
| REQ-GATE-001 (확인 없이 BND-3 금지 / 동일 id / 반려 시 복귀) | 승인 본체 유지 + §4.3 거절 시 해당 슬롯 복귀 |
| REQ-QUOTE-001 (근거+재현성) | §4.3 슬롯 조립 입력으로 `build_quote` 호출 |

---

## 5. 불확실한 점 (추정 명시)

1. **(추정)** 질문 상한 3회·응답 300자·불릿 4개 등 수치 임계값 — UX 일반론 기준이며 사용자 테스트로 조정 필요.
2. **(추정)** 동의어·은유 처리율 — 키워드 규칙의 실제 커버리지는 로그를 쌓아봐야 알 수 있음. 1차는 "질의 트리거" 용도로만 쓰고 확정은 사람에게 맡기는 구조로 위험 회피.
3. **(추정)** `platform` 단일값 전제 — 현 스키마 enum이 `web|android` 단일이라 1차는 단일 선택으로 설계. "둘 다" 요구가 실제로 오면 스키마 개정(BND-2·BND-3 `platform` 배열화)이 선행되어야 함.
4. **(추정)** self-check 추가 호출의 체감 지연 — NIM 지연 시 폴백(검사 생략)으로 상쇄 가능하나, 실측 전에는 확정 불가. `ai_status` 선기록(§3.4는 MULTIUSER 문서 설계, room에는 `RAG_SEARCHING`·`QUOTING` 대입 확인됨 — `backend.py:732-744, 748-756`) 패턴으로 "검사 중" 표시는 가능.
