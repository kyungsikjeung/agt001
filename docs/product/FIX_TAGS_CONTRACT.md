# 계약서: 고칠 곳을 태그로 고르기 (FIX_TAGS_CONTRACT)

> 2026-10-01 (KST) / Claude 작성, OpenCode 구현, Claude 검토. 계획 [OWNER_FEEDBACK_1001_PLAN](OWNER_FEEDBACK_1001_PLAN.md) §1, 결정 D58 ⑤(가장 먼저, 10/17 베타 전).
> 재사용: 채팅방 요약 뒤 고치기(`chat_flow._apply_correction`, CONFIRMING 상태의 else 가지), 빌더 말로 고치기(`POST /api/rooms/{id}/say` → `builder_agent.say`), 채팅방 칩 줄(`#choiceBar`), 마이크(`static/room.html`의 기존 음성 입력, 빌더 `SayBar`의 마이크), `card_api._member_room`, `prd_schema.label_for`.

## 0. 결론

- "고칠 게 있어요"를 누르면 자유 글 대신 **고칠 곳 칩**이 뜬다. 칩 → (메뉴면 항목 칩) → 입력줄 하나 → 보내기.
- **서버에 새로 만드는 것은 목록 API 하나**다. 보낼 때는 칩 이름과 입력을 한 문장으로 합쳐(`"영업시간 매일 10시~9시"`) **기존 고치기 경로**로 보낸다.
  - 채팅방은 기존 채팅 메시지로 보낸다(요약 뒤 고치기).
  - 빌더는 기존 `/say`로 보낸다.
  - 그래서 말하지 않은 숫자 금지, 근거 검사, 되돌리기가 그대로 적용된다.
- 한계(ponytail): "그 칸만" 고치는 것을 서버가 강제하지 않는다. 칸 이름을 앞에 붙여 판단을 이끌 뿐이다. 다른 칸까지 바뀌는 사례가 나오면 `/say`에 `target`을 받아 명령을 그 칸으로 거르는 것을 더한다(§6 참고).

## 1. 흐름

| 번호 | 누가 | 무엇 |
|---|---|---|
| 1 | 사장님 | 요약 아래 "고칠 게 있어요"(채팅방) 또는 입력줄 옆 "고칠 곳"(빌더)을 누른다 |
| 2 | 화면 | `GET /api/rooms/{id}/fix-targets`로 칩 목록을 받아 칩 줄에 띄운다. 맨 끝에 "직접 말하기" 칩을 둔다 |
| 3 | 사장님 | 칩 하나를 누른다 |
| 4 | 화면 | 그 칩에 `parts`가 있으면(메뉴·가격) 항목 칩과 "+ 새 항목" 칩을 띄운다. 없으면 바로 5 |
| 5 | 화면 | 입력줄을 연다. 입력줄 위에 고른 곳을 보인다("영업시간 고치기"). 칸 안에 지금 값을 흐린 예시 글로 보인다. 글 + 마이크를 쓰고, 알아들은 음성은 입력에만 넣는다(자동 전송 없음) |
| 6 | 화면 | 보내면 `compose(target, part, text)`로 한 문장을 만들어 기존 경로로 보낸다(§4) |
| 7 | 서버 | 기존 결과 그대로. 채팅방은 "고쳤어요: …"와 요약을 다시 보이고, 빌더는 미리보기를 다시 부르고 되돌리기를 켠다 |
| 8 | 화면 | 칩 줄을 닫는다. 실패하거나 서버가 되물으면 그 답을 보이고 입력줄은 그대로 둔다 |

- "직접 말하기": 채팅방은 지금처럼 `'거절'`을 보내 "무엇을 고칠까요?"로 간다. 빌더는 입력줄에 초점만 옮긴다.
- "사진" 칩:
  - 채팅방은 기존 사진 올리기 단추를 누른 것과 같게 한다.
  - 빌더는 "미리보기에서 바꿀 사진을 눌러 주세요" 한 줄을 보이고 칩 줄을 닫는다.

## 2. API: `GET /api/rooms/{room_id}/fix-targets`

- 권한: 방 참여자(`X-Member-Id`, `card_api._member_room`)이면 누구나 본다. 고치기 권한은 기존 경로가 판단한다.
- 카드가 없으면 `{"targets": []}`.
- 응답:

```json
{"targets": [
  {"key": "shop_name", "label": "가게 이름", "current": "모퉁이 커피", "parts": []},
  {"key": "items", "label": "메뉴·가격", "current": "", "parts": [
    {"key": "아메리카노", "label": "아메리카노 4,500원"}, {"key": "라떼", "label": "라떼"}]},
  {"key": "hours", "label": "영업시간", "current": "매일 9시~8시", "parts": []},
  {"key": "photo", "label": "사진", "current": "", "parts": []}
]}
```

- 칸 순서: `shop_name` · `items` · `hours` · `location` · `phone` · `detail` · `contact_method` · `notice` · `photo`.
- **채워진 칸만** 보낸다(채움 판단은 요약 화면과 같은 기준). 예외 둘:
  - `photo`는 늘 보낸다.
  - `notice`는 공지가 켜져 있을 때만 보낸다.
- `label`은 업종 이름표(`prd_schema.label_for`)를 쓴다. 예: 학원은 `items`가 "반·수업", 펜션은 "객실".
- `items.parts`는 카드 항목 줄의 이름(`key`)과 "이름 + 가격"(`label`, 가격이 없으면 이름만)이다. 최대 30개.
- `current`는 한 줄로 줄인 지금 값이고 최대 40자다. 전화번호도 사장님 본인 화면이라 그대로 보인다.
- 캐시: `Cache-Control: no-store`.

## 3. 한 문장 만들기 `compose(target, part, text)` (화면, 채팅방·빌더 같은 규칙)

| 경우 | 보내는 말 |
|---|---|
| 일반 칸 | `"{label} {text}"` 예: `"영업시간 매일 10시~9시"` |
| 항목 고치기 | `"{part.key} {text}"` 예: `"아메리카노 5,000원으로"` |
| 새 항목 | `"{label}에 {text} 추가"` 예: `"메뉴·가격에 바닐라라떼 5,500원 추가"` |
| 입력이 이미 칸 이름으로 시작 | 그대로 보낸다(이름을 두 번 붙이지 않는다) |

- 빈 입력은 보내지 않는다(보내기 단추 꺼짐). 300자 제한은 기존과 같다.
- 채팅방은 `compose`를 `static/room.html` 안에 둔다. 빌더는 `frontend/src/builder/fixTags.ts`에 두고 같은 표를 테스트한다.

## 4. 화면

### 4.1 채팅방 (`static/room.html`)
- `#voteBar`의 "고칠 게 있어요"는 `vote('거절')` 대신 `openFixTags()`를 부른다.
  - `openFixTags()`는 목록을 받아 `#choiceBar`에 칩을 그린다. 기존 칩 모양(`#choiceBar button`)을 그대로 쓴다.
  - 목록 요청이 실패하면 예전처럼 `vote('거절')`로 돌아간다.
- 입력은 기존 메시지 입력칸을 쓴다.
  - 고른 곳은 입력칸 위 한 줄로 보인다(`고칠 곳: 영업시간 ✕`). ✕를 누르면 고르기를 취소한다.
  - 보내기는 기존 `sendRoomMessage(compose(...))`로 한다.
  - 음성은 기존 마이크를 쓰고 자동 전송은 하지 않는다.
- 보낸 뒤나 ✕를 누르면 고른 곳을 비운다.
- 요약 상태(CONFIRMING)가 아니면 "고칠 게 있어요" 단추가 없으므로 이 흐름도 없다.

### 4.2 빌더 (`frontend/src/builder/SayBar.tsx`)
- 입력줄 왼쪽에 "고칠 곳" 단추를 둔다. 누르면 입력줄 위에 칩 줄(`FixTags.tsx`, 가로로 밀기)이 열린다.
- 고르면 입력줄 위에 `고칠 곳: 영업시간 ✕`을 보이고, 입력줄의 흐린 예시 글을 그 칸의 지금 값으로 바꾼다.
- 보내기는 기존 `/say` 호출에 `compose(...)` 결과를 넣는다. 나머지(되돌리기·미리보기 다시 부르기·되묻기)는 그대로다.
- 누름 칸은 44px 이상이고, 칩 줄은 `role="group"`, `aria-label="고칠 곳"`을 단다.

## 5. 작업 묶음 (OpenCode)

| 묶음 | 파일(소유) | 선행 |
|---|---|---|
| T1 서버 | `app/api/card.py`(경로 1개), `tests/unit/test_fix_targets.py`(신규) | 없음 |
| T2 채팅방 | `static/room.html`만 | T1 응답 모양(§2)만. 가짜 응답으로 병렬 가능 |
| T3 빌더 | `frontend/src/builder/SayBar.tsx`, `frontend/src/builder/FixTags.tsx`(신규), `frontend/src/builder/fixTags.ts`(신규), `frontend/src/builder/*.test.tsx`, `frontend/src/editor/cardApi.ts`(함수 1개) | T1 응답 모양만 |

**하지 말 것**: `chat_flow`의 상태·의도 판단 수정, `builder_agent`의 검사·명령 목록 수정, 새 의존성, 새 LLM 호출, 칩 목록에 가게 정보가 아닌 것(내부 상태·다른 방) 넣기, 음성 자동 전송.

## 6. 합격 테스트

| 번호 | 테스트 | 파일 |
|---|---|---|
| 1 | 채워진 칸만, 정해진 순서, 업종 이름표(학원 `items` = "반·수업"). `photo`는 늘, `notice`는 켜졌을 때만 | `test_fix_targets.py` |
| 2 | `items.parts`: 이름·가격 label, 가격 없는 항목은 이름만, 30개 상한, `current` 40자 자름 | 같은 파일 |
| 3 | 참여자가 아니면 403, 카드 없으면 빈 목록, `Cache-Control: no-store` | 같은 파일 |
| 4 | 끝에서 끝: 목록의 `hours`로 만든 말 `"영업시간 매일 10시~9시"`를 CONFIRMING 상태 채팅으로 보내면 카드의 영업시간이 바뀌고 답에 "고쳤어요"가 있다. `"아메리카노 5,000원으로"`면 그 항목 가격이 바뀐다(LLM 없이 규칙 경로) | 같은 파일 |
| 5 | `compose` 표 4줄 + 이름 중복 방지 | `fixTags.test.ts` |
| 6 | SayBar: "고칠 곳" → 칩 → 고른 곳 표시·예시 글 → 보내기 본문이 compose 결과, ✕로 취소, 목록 실패 시 칩 없이 입력줄만 | `SayBar.test.tsx` |
| 7 | 채팅방: `node --check`로 room.html 스크립트 문법 확인. 390px 흐름은 Claude가 캡처(요약 → 고칠 게 있어요 → 영업시간 → 입력 → 요약 다시) | Claude |

- 모자라면(다른 칸까지 바뀌는 사례): `/say`에 `target`을 받아 `validate` 뒤 그 칸 명령만 남기는 것을 T4로 더한다. 이번에는 하지 않는다.

## 변경 이력

| 날짜 | 내용 |
|---|---|
| 2026-10-01 | 처음 작성 (D58 ⑤) |
