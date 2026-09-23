# 그룹 요구사항 도출 채팅 UI/UX 디자인 레퍼런스 (agt001)

> 작성일: 2026-09-23 / 역할: UI/UX 디자인 컨설턴트 관점
> 전제: 현재 `static/index.html`은 1:1 단일 채팅창(`#log` + `.msg.user/.bot` 좌우 정렬)이다. 이를 여러 명이 함께 보는 그룹 요구사항 도출 채팅으로 확장할 때의 참고 패턴만 정리한다. 코드는 수정하지 않음.

## 우리 프로젝트에 가장 추천하는 디자인 방향 요약 (3~4줄)

**Slack식 "아바타+이름 좌측 정렬 + 스레드" + Slack AI Agent식 "전원에게 보이는 처리중 상태 + 단계별 진행 표시" + Slack식 "이모지 투표로 합의" 조합을 추천한다.** 발신자는 좌우 버블이 아니라 좌측 아바타+이름으로 구분하고, AI 작업은 요청자뿐 아니라 전원에게 동일한 스트리밍/단계 카드로 보여주며, "다음 단계로" 이동은 이모지 리액션 정족수로 확정한다. 카카오톡 그룹+봇은 공식 API로 구현이 불가하므로(1:1 채널 봇만 공식 지원), 카카오는 공유/알림용 보조 채널로 두고 메인 그룹 채팅은 웹에서 구현하는 것이 안전하다.

---

## 1. 그룹 채팅 UI 패턴: "누가 말했는지 / 동시 타이핑 / 순서·스레드"

### 1-1. Slack — 채널 메시지 + 스레드 + 다중 타이핑 문구

**참고 제품/패턴 이름:** Slack 채널 메시지 / Thread replies / Typing indicator ("Several people are typing")

**어떻게 동작하는지:**
- 1:1 DM과 달리 채널(그룹)에서는 좌우 버블을 쓰지 않는다. 모든 메시지가 좌측 정렬이며, 각 메시지마다 발신자 아바타 + 표시 이름 + 타임스탬프가 붙는다. 같은 사람이 연속으로 보내면 아바타를 묶어서(compaction) 보여준다.
- 스레드: 부모 메시지(parent)에 답글을 달면 우측 패널 또는 인라인 스레드로 묶인다. 채널 본문은 "부모 아이디어만" 보이고, 세부 논의는 스레드 안에 가둬서 본문 스크롤이 오염되지 않게 한다. Slack 개발자 문서의 공식 용어(parent message / threaded replies / thread) 그대로이다.
- 타이핑 표시: 입력창 하단에 "Jane is typing" (1명) / "Jane and John are typing" (2명) / "Several people are typing" (3명 이상) 형태로 표시한다. 5초간 입력이 없으면 사라진다. 참고로 Slack 공식 블로그 이름 자체가 "Several People Are Typing"이다.
- AI 요약/검색이 채널 안에 들어올 때도 같은 메시지 스트림 안에 표시되며, 멘션(@Agent)과 스레드로 호출 범위를 한정한다.

**우리(agt001)에 적용한다면 (와이어프레임 설명):**
- 현재 `.user {text-align:right}` / `.bot {text-align:left}` 구조를 버리고, 전원 좌측 정렬 + 아바타 원 + 이름표로 바꾼다.
- AI 요약 메시지는 보라색 계열 아바타(🤖 요구사항봇) + "AI" 뱃지로 고정한다.

```
텍스트 레이아웃 서술:
+--------------------------------------------------+
| [≡] 요구사항 도출방 (4)        [참여자 목록 보기]  |
+--------------------------------------------------+
| (●) 민수 10:31                                   |
|     로그인 없이 볼 수 있으면 좋겠어요              |
|                                                  |
| (●) 지현 10:32                                   |
|     저도요 + 관리자 승인 기능 필요해요             |
|     └─ 💬 스레드 3개 보기 (세부 논의는 여기로)     |
|                                                  |
| (🤖) 요구사항봇 10:33 [AI]                        |
|     ┌ 요구사항 정리 v2 ─────────────┐             |
|     │ 1. 비회원 조회 2. 관리자 승인 │             |
|     │ 👍 3  👀 1  [확정하기]        │             |
|     └──────────────────────────────┘             |
+--------------------------------------------------+
| 하단 상태줄: "지현, 민수님이 입력 중..."          |
| [메시지 입력........] [보내기]                    |
+--------------------------------------------------+

ASCII 대안:
  (M) 민수: 로그인 없이...
  (J) 지현: + 관리자 승인...
  (B) [AI] 봇: 정리 v2 ...
```

### 1-2. Discord — 아바타+유저명+타임스탬프 + 답글 인용 + 역할 색상

**참고 제품/패턴 이름:** Discord 텍스트 채널 / Reply(인용 답글) / 역할 색상 Username

**어떻게 동작하는지:**
- 메시지 행: 좌측 40px 원형 아바타, 우측에 유저명(16px medium) + 타임스탬프(12px 회색) + 본문. 같은 사람이 짧은 간격으로 연속 발화하면 아바타·이름을 생략하고 본문만 이어 붙인다(그룹핑).
- 답글(Reply): 특정 메시지에 답글을 달면 원문 미리보기가 작은 인용 블록으로 상단에 붙고, 클릭하면 원문으로 스크롤 점프한다. 후발주자인 Threads/포럼 채널은 주제별 분기용이다.
- 유저명은 서버 역할(Role) 색상을 그대로 쓴다. 예: 방장=주황, 참여자=회색, 봇=파란 배경 "BOT" 태그. 봇 메시지는 이름 옆에 파란 BOT 뱃지가 의무 표시된다.
- 그룹 DM은 최대 10명 제한이 있어 대규모 그룹 논의에는 서버 채널을 쓰도록 유도한다.

**우리(agt001)에 적용한다면:**
- Discord식 "BOT 태그"를 그대로 차용: AI 메시지 이름 옆에 `[BOT]` 칩을 붙여 사람과 확실히 구분한다.
- 요구사항 후보마다 답글 인용을 강제한다. 예: "민수님의 '비회원 조회'에 답글 → 스레드에서 찬반" 흐름.
- 역할 색상: 요청자(파랑), 방장(주황), AI(보라) 정도로만 최소 구분한다. 너무 많은 색은 피한다.

```
[J 방장]  지현 10:32
  └ "관리자 승인 필요"에 대한 스레드 (2)
      (M) 민수: 승인 없이 자동이면 안 되나요?
      (B) [BOT] 요구사항봇: 대안 2개를 정리했어요...
```

### 1-3. MS Teams — Fluent 아바타 그룹 + Post-and-Reply + 형광 반응

**참고 제품/패턴 이름:** MS Teams Chat / Channels Post-and-Reply / Avatar group / Fluent UI

**어떻게 동작하는지:**
- 디자인 시스템(Fluent) 기준: 아바타는 사람·팀·봇을 모두 원형으로 표현하고, 그룹 채팅 상단에는 아바타 그룹(겹쳐진 원 2~3개)으로 "누가 보고 있는지"를省공간으로 보여준다.
- 채널은 예전 "스레드 강제" 모델에서 "Post-and-Reply"(위에서부터 읽는 게시+댓글) 모델로 바뀌었다. 새 글은 위에서부터 시간순, 댓글은 접힌 상태로 둔다. "덜 복잡하고 읽기 쉽게(skim 가능)"가 목표였다고 공식 디자인 블로그에서 밝힌다.
- 타이핑은 말풍선 3점 애니메이션 + "OO님이 입력 중" 텍스트로 표시한다.
- Copilot/Agent 메시지는 본문 스트림 안에 "작업 중" 카드로 들어오며, 출처 링크와 함께 표시된다.

**우리(agt001)에 적용한다면:**
- 상단바에 아바타 그룹(겹친 원) + "4명 참여 중"을 둔다. 클릭하면 참여자 목록 패널이 열린다.
- 요구사항 확정글은 Teams식 Post(굵은 제목 + 본문 + 댓글 접힘)로 올린다. 논의는 댓글(스레드)에 가둔다.

```
상단: (M)(J)(+) 요구사항 도출방 — 4명 참여 중
본문 Post:
  [요구사항 정리 v2] (봇 게시, 댓글 5개 숨김)
  댓글 펼치기 ▾
```

### 1-4. 카카오톡 오픈채팅/그룹채팅 — 모바일 버블 + 프로필+이름 + 방장봇 말풍선

**참고 제품/패턴 이름:** 카카오톡 그룹채팅 / 오픈채팅 / 오픈채팅봇(구 방장봇)

**어떻게 동작하는지:**
- 내 메시지는 우측 노란 버블, 상대 메시지는 좌측 흰 버블 + 작은 프로필 이미지 + 닉네임. 오픈채팅에서는 본명 대신 오픈프로필 닉네임을 쓴다.
- 타이핑 인디케이터가 사실상 없다(입력 중 표시 미지원). 대신 읽음 숫자(예: 1, 2)가 사라지는 것으로 "읽었음"만 판단한다. 여러 명이 동시에 입력 중인지 알 방법이 없다.
- 방장봇 메시지는 일반 참여자 말풍선과 같은 형태로 중간에 끼워진다. 환영 메시지/알림 메시지/슬래시(`/질문`) 답변이 전부 일반 말풍선이다. "AI가 생각 중" 같은 중간 상태 UI가 없다.

**우리(agt001)에 적용한다면:**
- 카카오 스타일을 웹에 그대로 가져오지 마라. 좌우 버블은 1:1용이며, 4인 이상 그룹+AI 요약이 섞이면 "누가 AI인지" 구분이 어려워진다.
- 카카오 연동을 한다면 메인 회의 UI가 아니라 "입장 환영/마감 알림 발송용"으로만 쓰는 것이 맞다(4장 참조).

---

## 2. AI 처리 상태를 보여주는 UX 패턴: "지금 AI가 일하고 있음"을 전원에게

핵심 원칙(여러 출처 공통): **TTFT(첫 토큰까지의 침묵) 구간에 스켈레톤/상태문구를 먼저 보여주고, 토큰이 오면 스트리밍으로 붙이며, 중단(Stop) 버튼을 항상 둔다.** 스켈레톤은 스피너보다 약 20% 빠르게 느껴진다는 연구가 자주 인용된다.

### 2-1. ChatGPT / Claude — 스트리밍 텍스트 + 깜빡이는 커서 + Stop 버튼

**참고 제품/패턴 이름:** ChatGPT 스트리밍 / Claude 스트리밍 (SSE) / Vercel AI SDK `useChat`

**어떻게 동작하는지:**
- 서버는 SSE(Server-Sent Events)로 토큰을 조금씩 내려보내고, 클라이언트는 오는 대로 말풍선에 이어 붙인다. 총 시간은 같지만 체감 속도가 크게 빨라진다.
- 스트리밍 중에는 말풍선 끝에 깜빡이는 커서(▍)를 둔다. 커서가 없으면 중간 멈춤을 "완료/고장"으로 오해한다.
- 전송 버튼 자리에 ■ Stop 버튼이 나타난다. Stop은 진짜로 상류 API 호출까지 취소(AbortController 전달)해야 의미가 있으며, 중단된 부분 텍스트는 남기고 "생성 중단됨" 라벨을 붙인다.
- 입력창은 스트리밍 중 비활성화(중복 요청·순서 꼬임 방지)하되 Stop만은 항상 활성이다.

**우리(agt001)에 적용한다면:**
- AI 요약 버블이 나타나는 즉시 2~3줄짜리 회색 스켈레톤(둥근 막대)을 먼저 보여주고, 첫 토큰이 오면 텍스트로 교체한다.
- AI 버블 상단에 "🤖 요구사항봇이 정리 중... (요청: 민수)" 한 줄을 전원에게 동일하게 보여준다. 요청자만 보는 토스트가 아니라 메시지 스트림 안에 넣어야 전원이 본다.

```
(AI 버블, 전원에게 동일 노출)
┌─────────────────────────────┐
│ 🤖 요구사항봇이 정리 중...   │  ← 스켈레톤 단계
│ ▓▓▓▓▓▓▓░░░░                │
│ ▓▓▓▓░░░░░                  │
│ [■ 중단] (방장만 가능)       │
└─────────────────────────────┘
   ↓ 첫 토큰 도착 후
┌─────────────────────────────┐
│ 정리 v2: 1. 비회원 조회...▍  │  ← 스트리밍 + 커서
│ [■ 중단]                     │
└─────────────────────────────┘
```

### 2-2. ChatGPT Agent / Deep Research / Gemini — 단계별 진행 표시 (Plan + Task card)

**참고 제품/패턴 이름:** ChatGPT Agent mode / OpenAI Deep Research / Slack Agent `task_display_mode: plan`

**어떻게 동작하는지:**
- 긴 작업(5~30분 가능)은 빈 스켈레톤으로 버티지 않는다. "무엇을 하고 있는지"를 단계 리스트로 보여준다. 예: `웹 검색 중... → 문서 3개 읽는 중... → 표 만드는 중...`
- Slack 공식 Agent 개발 문서는 이를 API로 규격화했다: `agents.sessions.setStatus({status:"processing"})` 호출 즉시 로딩 UX 표시 → `chat.startStream(task_display_mode:"plan")` → `chat.appendStream`으로 task 상태(`pending/in_progress/complete/error`) 갱신 → `chat.stopStream`으로 종료 → `setStatus({status:"active"})`로 로딩 해제. 한 명이 호출해도 채널/스레드 안 전원이 같은 plan 카드를 본다.
- ChatGPT Agent는 중간에 멈춰서 "계속해도 될까요?"라고 확인을 요청하거나, 사용자가 중간에 가로채서 방향을 틀 수 있다(interrupt/steer). 완료 시 휴대폰 알림도 보낸다.

**우리(agt001)에 적용한다면 (가장 중요한 패턴):**
- 요구사항 정리를 3단계 고정 카드로 보여준다: `① 대화 수집 → ② 중복 제거·충돌 탐지 → ③ 요구사항 초안 작성`. 각 단계마다 상태 아이콘(○ 대기 / ◐ 진행중 / ● 완료 / ✖ 실패)을 둔다.
- 누가 시켰는지(요청자 이름)를 카드 제목에 명시한다: "민수님의 요청으로 정리 중". 그래야 나머지 참여자가 "왜 AI가 갑자기 일하지?"라고 혼란스러워하지 않는다.

```
┌ 민수님의 요청으로 정리 중 (전원에게 보임) ┐
│ ● ① 대화 24개 수집 완료                   │
│ ◐ ② 중복 제거·충돌 탐지 중...             │
│ ○ ③ 요구사항 초안 작성 대기               │
│ [자세히 보기 ▾] [■ 중단]                  │
└──────────────────────────────────────────┘
```

### 2-3. Notion AI / Claude Artifacts — "옆 패널에 결과물" + 인라인 상태줄

**참고 제품/패턴 이름:** Notion AI / Claude Artifacts (Split pane) / Perplexity "Searching..."

**어떻게 동작하는지:**
- 채팅 스레드는 "의도·맥락 기록"으로 두고, 실제 산출물은 우측 사이드 패널(Artifacts/페이지)에 둔다. 채팅+결과물을 나란히 보여서 맥락과 산출물을 동시에 볼 수 있게 한다.
- AI가 파일을 읽거나 검색하는 동안에는 인라인 상태줄 한 줄("문서 읽는 중...", "웹 검색 중...")을 스트림 안에 끼운다. 15초짜리 도구 호출을 스켈레톤 하나로 버티게 하지 않는다.
- Notion + Claude 연동(2026)은 공유 작업 보드에서 "Claude에게 할당"하면 팀 전원이 진행 상황과 산출물을 같은 워크스페이스에서 본다. "한 명이 시킨 AI 일을 팀이 함께 본다"는 점에서 우리와 가장 유사한 사례이다.

**우리(agt001)에 적용한다면:**
- 데스크탑(넓은 화면): 좌측=그룹 채팅, 우측=요구사항 캔버스(스플릿 패널). AI가 정리할 때마다 우측 패널이 실시간 갱신된다.
- 모바일(좁은 화면): 스플릿 대신 "요구사항 보기" 버튼 → 바텀시트/새 화면으로 전환한다(Claude 공식도 모바일 폴백을 권장).

```
[데스크탑]
+----------------------+------------------------+
| 그룹 채팅 (좌)        | 요구사항 캔버스 (우)      |
| 민수: 비회원...       | v2 (AI가 작성 중 ◐)       |
| 지현: 승인...         | 1. 비회원 조회            |
| [AI] 정리 중 ◐...    | 2. 관리자 승인 [충돌!]    |
+----------------------+------------------------+
[모바일] 채팅 하단 고정 버튼: [📋 요구사항 보기 (v2)]
```

### 2-4. 그룹에서 AI를 함께 보는 특별 케이스: ChatGPT 그룹채팅(파일럿, 2026-07 종료) / Slack Code "멀티플레이어 AI"

**참고 제품/패턴 이름:** ChatGPT Group Chats (파일럿) / Slack Code 채널 ("multiplayer AI")

**어떻게 동작하는지:**
- ChatGPT 그룹채팅(최대 20명, 초대 링크 입장): ChatGPT가 대화 참여자로 들어와 흐름을 따라가며 "언제 답할지 스스로 판단"한다. 답이 필요하면 누구든 "@ChatGPT" 멘션으로 호출한다. 개인 메모리·개인 설정은 그룹과 공유되지 않고, 그룹별 커스텀 지침을 따로 둔다. 2026-07-09부터 신규 생성 중단·읽기전용 전환 예정(파일럿 종료). "멘션 호출 + 스스로 끼어들기 자제" UX가 핵심 교훈이다.
- Slack Code(2026-08 발표): 코딩 에이전트에게 전용 프로젝트 채널을 만들어주고 팀 전원이 "AI가 일하는 과정"(계획·변경 미리보기·HTML 프리뷰)을 지켜보다가 중간에 방향을 틀 수 있게 한다. 작업이 끝나면 채널은 아카이브되고 검색 가능한 기록으로 남는다. "한 명의 터미널 작업 → 전원이 보는 채널 작업"으로 옮긴 사례이다.

**우리(agt001)에 적용한다면:**
- 기본은 "멘션 호출형"으로: `@요구사항봇 정리해줘`라고 친 사람(=요청자)의 요청으로만 AI가 일한다. AI가 매 메시지마다 자동 끼어들게 하지 마라(소음·비용 문제).
- AI 작업실(스레드/채널 분리) 패턴: 본문 채널은 사람 대화용, AI 정리 과정·충돌 검토는 별도 스레드(또는 우측 패널)에서 전원이 지켜보게 한다. 끝나면 "정리 v2 확정" Post만 본문에 남긴다.

---

## 3. 여러 명이 "합의"해서 다음 단계로 넘어가는 UX 패턴

### 3-1. Slack — 이모지 리액션 투표(reacji) + Simple Poll/Polly 앱

**참고 제품/패턴 이름:** Slack emoji reactions 투표 / Slack Help "Create a poll" / Polly·Simple Poll

**어떻게 동작하는지:**
- 공식 헬프가 안내하는 가장 가벼운 투표: 질문 메시지에 선택지별 이모지를 붙이고(`:one: 레이아웃 A` / `:two: 레이아웃 B`), 각 이모지를 리액션으로 미리 달아둔다. 참여자는 해당 리액션을 클릭만 하면 투표된다. 카운터가 리액션 옆에 실시간 표시된다.
- 사내 관용어(reacji) 예시: `:+1:`=찬성·추가 한 표, `:eyes:`=내가 맡아서 볼게, `:white_check_mark:`=완료·승인. 말풍선을 새로 쓰지 않고 의사표시를 끝낸다(스레드 오염 방지).
- 고급(익명·복수·정기) 투표는 Polly/Simple Poll 앱을 쓴다. 버튼·모달·결과 차트가 붙는다.

**우리(agt001)에 적용한다면 (추천):**
- AI 정리 카드 하단에 고정 투표 바를 둔다: `[👍 확정 3/4] [👀 보류] [🔁 다시 정리해줘]`. 정족수(예: 전원 또는 과반)가 차면 "확정" 상태로 바뀌고 다음 단계 버튼이 활성화된다.
- 투표 현황은 "누가 눌렀는지" 호버로 보여준다(투명성). 익명 투표는 쓰지 마라(요구사항 책임 소재가 흐려진다).

```
┌ 요구사항 정리 v2 ────────────┐
│ 1. 비회원 조회 2. 관리자 승인 │
│ 👍 3/4  👀 1                  │
│ [👍 확정하기] [🔁 다시 정리]  │
│ 호버: 👍 민수, 지현, 태호     │
└──────────────────────────────┘
```

### 3-2. Figma — 핀 코멘트 + Resolve + 이모지 승인

**참고 제품/패턴 이름:** Figma Comments (pins) / Resolve / @mention

**어떻게 동작하는지:**
- 캔버스 특정 위치에 핀을 꽂아 댓글을 남긴다. 댓글은 스레드(대댓글) 구조이며, 해결되면 Resolve해서 접는다(기록은 보관). 미해결 댓글은 핀이 계속 보여서 "남은 일"을 시각화한다.
- 빠른 승인은 댓글에 👍❤️✅ 이모지로 답한다. 정식 리뷰가 필요 없으면 이모지 하나로 종결한다.
- @멘션으로 특정인에게 알림을 보내고, "Unread로 표시"로 나중에 돌아올 수 있게 한다.

**우리(agt001)에 적용한다면:**
- 요구사항 항목마다 "댓글 스레드 + Resolve"를 붙인다. 예: "2. 관리자 승인 [충돌] — 댓글 3개, 미해결". 해결되면 체크(✅)하고 접는다.
- 전체 확정 전 "미해결 댓글 N개 남음" 경고를 띄워 성급한 확정을 막는다.

### 3-3. Notion — 페이지/블록 코멘트 + @멘션 + Resolve

**참고 제품/패턴 이름:** Notion Page comments / Block comments / Inbox

**어떻게 동작하는지:**
- 페이지 상단 코멘트(전체에 대한 의견)와 블록 코멘트(특정 문단·표·이미지에 대한 의견)를 구분한다. 요구사항 문서처럼 긴 산출물에는 블록 단위 코멘트가 필수이다.
- @멘션하면 상대방 Inbox에 알림이 가고, 그 자리에서 답글을 달 수 있다. 피드백 기한을 페이지 상단 코멘트로 못 박는다("금요일까지 의견 주세요").
- 논의가 끝나면 Resolve. 히스토리는 남는다.

**우리(agt001)에 적용한다면:**
- 우측 요구사항 캔버스(2-3 참조)의 각 항목에 블록 코멘트를 달 수 있게 한다. 채팅(빠른 대화)과 캔버스 코멘트(항목별 정밀 피드백)를 분리한다.
- 상단에 "의견 마감: 10분 후 자동 확정 투표" 같은 기한 바를 둔다(해커톤 시연용으로 효과적).

### 3-4. 그 외 그룹 의사결정 참고: Discord 투표 봇 / Teams Approvals / 이모지 가중치

**참고 제품/패턴 이름:** Discord Polls 봇 / MS Teams Approvals / Railsware식 reacji 스케일

**어떻게 동작하는지:**
- Discord는 네이티브 투표가 약해 Poll 봇(버튼+막대그래프)을 붙인다. Teams는 Approvals 앱으로 "승인 요청 → 승인/거절 버튼 → 감사 추적" 정식 플로우를 제공한다.
- Railsware(사례): 관심도·만족도를 이모지 스케일로 측정한다(예: "Really Want/Want/..." 6단계). 단순 찬반이 아니라 강도를 잰다.

**우리(agt001)에 적용한다면:**
- 해커톤 범위에서는 Teams Approvals 같은 무거운 결재 플로우를 만들지 마라. Slack식 가벼운 리액션 + 정족수 바면 충분하다.
- 다만 "확정"은 방장(또는 요청자) 1명이 버튼을 눌러 선언하게 하고, 그 로그("지현이 v2를 확정함 10:40")를 채팅에 남겨 책임을 명확히 한다.

---

## 4. 카카오톡 오픈채팅 봇의 실제 모습과 그룹+봇 조합의 제약

### 4-1. 오픈채팅봇(구 방장봇)이 실제로 어떻게 생겼는지

**참고 제품/패턴 이름:** 카카오톡 오픈채팅봇(방장봇) — 환영 메시지 / 알림 메시지 / 질문 답변(`/슬래시`)

**어떻게 동작하는지 (실제 스크린샷·설명 자료 기준):**
- 그룹 오픈채팅방에서만 활성화 가능하며(1:1 방 불가), 방장만 설정할 수 있다. 채팅방 우측 상단 ≡ 메뉴 → "오픈채팅봇 활성화" → 봇 프로필이 참여자로 추가된다.
- 기능 3종만 있다:
  1. **환영 메시지(최대 1개):** 신규 입장자에게 자동 인사·규칙 전송.
  2. **알림 메시지(최대 3개):** 지정 시각에 자동 발송(최대 30자, 생성 후 수정 불가, 인원 많으면 지연 가능).
  3. **질문 답변(최대 10~20개, 자료마다 상이):** 키워드-답변 쌍을 등록해두고, 참여자가 `/규칙`처럼 슬래시+키워드를 치면 봇이 저장된 답변을 말풍선으로 보낸다. 기본 키워드 `/오픈채팅봇`, `/가이드`가 내장.
- 보이는 모습은 일반 참여자 말풍선과 동일하다. "입력 중..." 표시, 스레드, 리액션 투표 같은 그룹 협업 UI가 없다.

**우리(agt001)에 적용한다면:**
- 오픈채팅봇을 "요구사항 정리 AI"로 쓰려고 하지 마라. 정적 FAQ 자동응답기이지 LLM 에이전트가 아니다.
- 쓸모 있는 용도 2가지: ① 입장 시 환영+규칙 자동 발송("이 방은 요구사항 도출용입니다. `/규칙`을 쳐보세요") ② 마감 10분 전 알림 메시지 자동 발송.

### 4-2. 그룹+봇 조합의 제약 (공식 API 기준 — 반드시 숙지)

**참고 제품/패턴 이름:** 카카오 디벨로퍼스 공식 스펙 — 카카오톡 채널 봇(1:1) / 메시지 API / 공유하기(카카오링크)

**어떻게 동작하는지 (제약 사항):**
- **공식 챗봇(카카오톡 채널 + 스킬서버)은 1:1 대화 전용이다.** 카카오 챗봇 관리자센터·스킬서버 구조는 "사용자가 채널 1:1 채팅에서 말함 → 스킬서버가 응답 생성 → 1:1 채팅으로 반환" 흐름이며, 그룹채팅방에 공식 봇을 초대해 발화시키는 기능은 제공하지 않는다. 데브톡 공식 답변도 "채널+챗봇" 1:1 연동을 안내한다.
- **메시지 API는 친구 간 발송용이며 쿼터가 있다.** "나에게 보내기/친구에게 보내기"는 최대 5명, 일·월 쿼터 적용, 친구 목록·동의(plusfriends 등) 필요. 그룹채팅방 전체에 브로드캐스트하는 API가 아니다.
- **비공식 봇(알림 읽기·자동 답장 앱: 메신저봇R 등)은 카카오 운영정책 위반·차단 리스크가 있다.** 안드로이드 Notification을 가로채 답장하는 방식이며, 카카오톡 버전 의존성·계정 제재 가능성이 따른다. 해커톤 시연용 꼼수로는 쓸 수 있으나 정식 방향으로 문서화하지 마라.
- **현재 agt001이 쓰는 카카오 JS SDK 공유하기(`Kakao.Share.sendDefault`, feed 템플릿)는 "결과를 카톡으로 공유"용이지 그룹 대화용이 아니다.** 버튼을 누른 1명의 카톡으로 결과 링크를 보내는 1회성 공유이다.

**우리(agt001)에 적용한다면 (권장 아키텍처):**
- 메인 그룹 요구사항 채팅은 **자사 웹(현재 `static/index.html` 확장)** 에서 구현한다: 발신자 구분 + 전원용 AI 상태 + 투표 합의를 모두 웹에서 처리한다.
- 카카오는 **보조 채널**로만 쓴다: ① 결과 요약 공유하기(feed 템플릿, 현재 코드 재사용) ② 오픈채팅봇 환영·알림으로 방 운영 보조. "카톡 그룹 안에서 AI가 정리해준다"를 공약하지 마라 — 공식 API로 안 된다.
- 시연 멘트 예시: "그룹 논의와 AI 정리는 웹에서 실시간으로 진행하고, 확정된 요구사항은 카카오톡 공유하기로 전파합니다."

```
권장 구성도 (텍스트):
[웹 그룹채팅: 논의+AI정리+투표확정] ──공유하기──▶ [카카오톡: 결과 전파]
[오픈채팅봇: 환영/알림/FAQ] (보조, LLM 아님)
공식 API로 불가: [카톡 그룹방 안에서 LLM이 중간상태 보여주기]
```

---

## 출처 (URL)

### 1. 그룹 채팅 UI
- Slack 메시징·스레드 공식 문서: https://docs.slack.dev/messaging
- Slack 디자인: https://slack.design/articles/a-new-visual-language-for-slack
- Slack 타이핑 표시 동작 (Gizmodo 정리, Slack 공식 답변 인용): https://gizmodo.com/what-the-someone-is-typing-bubbles-in-messaging-apps-ac-1827744443
- "Several people are typing" 유래 (Slate): https://slate.com/human-interest/2018/01/slack-and-the-office-chat-several-people-are-typing-whos-working.html
- Ably Typing indicators (임계값 넘으면 "Multiple people are typing" 패턴): https://github.com/ably/docs/blob/main/src/pages/docs/chat/rooms/typing.mdx
- MS Teams 앱 디자인 기초 (아바타·아바타 그룹): https://learn.microsoft.com/en-us/microsoftteams/platform/concepts/design/design-teams-app-fundamentals
- MS Teams 새 디자인·Post-and-Reply (Microsoft Design): https://microsoft.design/articles/designing-the-new-era-of-teams
- Teams 채널 스레드 안내: https://adoption.microsoft.com/en-us/microsoft-teams/new-chat-and-channels-experience/threads-in-channels
- Discord 디자인 시스템 정리 (아바타 40px·유저명·타임스탬프): https://github.com/Khalidabdi1/design-ai/blob/main/design-md/discord/DESIGN.md
- Discord Display Name·그룹채팅: https://support.discord.com/hc/en-us/articles/33833879643927-Discord-Display-Name-Styles-FAQ
- Discord 답글(Reply) 요청 스레드 (인용 미리보기 UX): https://support.discord.com/hc/en-us/community/posts/360032582852-Two-Functions-Reply-Function-Last-DM-Function

### 2. AI 처리 상태
- LLM 지연 UX (스켈레톤·스트리밍·Stop 버튼): https://ai-tldr.dev/learn/building-ai-apps/ai-ux-patterns/designing-for-llm-latency
- Streaming AI UX 패턴: https://www.aiuxplayground.com/pattern/streaming
- Claude 스트리밍 기초 (SSE): https://claude3p.com/articles/sdk-streaming-basics
- Slack AI Agent 개발 가이드 (setStatus processing/active·plan·스트리밍): https://docs.slack.dev/ai/developing-agents
- Slack assistant.threads.setStatus ("is thinking..." 표시): https://docs.slack.dev/reference/methods/assistant.threads.setStatus/
- Slack Agents & Assistants (shimmer·타이핑 상태): https://slack.dev/resource-solutions/solution-ai-agents-assistants
- Slack AI 소개 (채널 요약·스레드 요약): https://api.slack.com/features/ai
- Slack Code "multiplayer AI" (그룹 채널에서 에이전트 작업 공개, 2026-08): https://www.theregister.com/saas/2026/08/20/slack-code-taps-into-collective-vibe-puts-ai-agents-into-the-group-chat/5290413
- ChatGPT Agent 소개 (중단·가로채기·승인): https://openai.com/index/introducing-chatgpt-agent
- ChatGPT Agent 도움말: https://help.openai.com/en/articles/11752874
- ChatGPT 그룹채팅 도움말 (멘션 호출·최대 20명·그룹 지침): https://help.openai.com/ko-kr/articles/12703475-chatgpt%EC%9D%98-%EA%B7%B8%EB%A3%B9-%EC%B1%84%ED%8C%85
- ChatGPT 그룹채팅 종료 공지 (2026-07-09~ 단계적 종료): https://help.openai.com/ko-kr/articles/12703475-group-chats-in-chatgpt
- Notion + Claude 협업 (팀 공유 보드에서 에이전트 진행 공개): https://www.notion.com/es-es/partners/claude
- Claude Artifacts 스플릿 패널 UX: https://ai-tldr.dev/learn/building-ai-apps/ai-ux-patterns/designing-for-llm-latency
- Claude Artifacts 티어다운: https://aiuxplayground.com/teardowns/claude/artifacts/

### 3. 합의 UX
- Slack 투표 만들기 공식 헬프 (이모지 투표): https://slack.com/intl/en-au/help/articles/229002507-Conversations--Create-a-poll-in-Slack
- Slack 이모지·리액션 공식 헬프: https://slack.com/intl/en-au/help/articles/202931348-Use-emoji-and-reactions
- Slack 스마트 활용 10선 (이모지 승인·투표): https://slack.com/blog/collaboration/beyond-chat-10-smart-ways-to-work-in-slack
- Slack 사내 이모지 사용법 (reacji·:+1:·:eyes:·:white_check_mark:): https://slack.com/intl/zh-tw/blog/productivity/some-of-the-ways-we-use-emoji-at-slack
- Railsware 커스텀 이모지 투표 스케일: https://railsware.com/blog/how-we-use-slack-custom-emoji-to-poll-groups-quickly
- Figma 코멘트 리디자인: https://www.figma.com/blog/stay-in-the-flow-with-redesigned-comments
- Figma 코멘트 가이드 (Resolve·멘션·이모지): https://help.figma.com/hc/en-us/articles/360039825314-Guide-to-comments-in-Figma
- Notion 팀 코멘트 협업 (페이지·블록 코멘트): https://www.notion.so/help/guides/how-teams-can-use-comments-for-better-collaboration
- Notion 코멘트·토론: https://www.notion.com/fi/help/guides/comments-and-discussions

### 4. 카카오톡 봇·제약
- 오픈채팅봇(방장봇) 설정·사용법 (환영·알림·질문답변, 스크린샷): https://hlife-ing.tistory.com/entry/%EC%B9%B4%EC%B9%B4%EC%98%A4%ED%86%A1-%EC%98%A4%ED%94%88%EC%B1%84%ED%8C%85%EB%B4%87%EB%B0%A9%EC%9E%A5%EB%B4%87-%EC%84%A4%EC%A0%95-%EB%B0%8F-%EC%82%AC%EC%9A%A9%ED%95%98%EB%8A%94-%EB%B0%A9%EB%B2%95
- 방장봇 활성화·자동응답 설정 (네이버 블로그, 스크린샷): https://m.blog.naver.com/ggidkkh/222194115689
- IT동아 방장봇 기능 소개 (그룹채팅방만 가능·방장만 설정): https://v.daum.net/v/AE3OfPoMug
- 카카오 방장봇 도입 보도 (조선비즈, 2020-11-12): https://biz.chosun.com/site/data/html_dir/2020/11/12/2020111201099.html
- 오픈빌더 봇의 오픈채팅 초대 (지식iN, 봇 참여자 초대 방식): https://m.kin.naver.com/qna/dirs/113/docs/484304237?d1id=1
- 카카오톡 채널 REST API (1:1 채널 관계 확인·웹훅): https://developers.kakao.com/docs/latest/en/kakaotalk-channel/rest-api
- 카카오톡 메시지 REST API (친구 발송·최대 5명·쿼터): https://developers.kakao.com/docs/en/kakaotalk-message/rest-api
- 카카오톡 채널 안내 (비즈니스 홈·1:1 채팅 중심): https://developers.kakao.com/docs/en/kakaotalk-channel
- 데브톡 "Kakaotalk API chat bot" (채널+챗봇 1:1 연동 안내): https://devtalk.kakao.com/t/kakaotalk-api-chat-bot/137970
- 비공식 카톡봇 구현 reference (메신저봇R·Notification 가로채기 — 리스크 근거): https://github.com/youhogeon/kakao-bot
