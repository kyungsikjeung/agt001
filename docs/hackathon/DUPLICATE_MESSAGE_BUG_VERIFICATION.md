# 중복 메시지 버그 수정 검증 리포트

> 대상 제보: "다인원 공유채팅(room)에서 자신이 보낸 메시지가 자신에게 중복되어 표시된다."
> 수정 커밋: `460c5d1` — `static/room.html`의 `pollMessages()`에 `pollInFlight` 플래그로 상호배제
> 검증일: 2026-09-23 / 검증 방식: 코드 리뷰 + OCI 실서버(`http://144.24.91.250:8643`) curl 검증
> 원칙: 코드 수정 없음, `.env` 미열람, git add/commit/push 없음. 불확실한 내용은 "추정" 표기.

## 검증 결론: 수정이 충분한가 → 예

제보된 증상(자신이 보낸 메시지가 자신에게 중복 렌더링)에 대해서는 수정이 충분하다.
근거는 아래 셋이다:

1. 원인 진단(커밋 메시지의 설명)이 정확하다 — 아래 "원인 재구성" 참조.
2. `pollInFlight` 가드가 JS 실행 모델 안에서 해당 경쟁을 완전히 직렬화한다 — 아래 §1.
3. 서버는 동일 `since` 값에 대해 항상 결정적인(동일한) 목록을 반환하고, 중복을 만들어내지 않음을
   실서버 curl로 확인했다 — 즉 버그는 100% 클라이언트 렌더링 측이었고, 서버 버그는 섞여 있지 않다(아래 §3).

다만 "방어 깊이" 차원에서 나중에 고려할 만한 소규모 hardening 제안이 있다(§4). 어느 것도
현재 증상을 재현하는 경로는 아니므로, 긴급 수정이 아니라 후속 검토용이다.

---

## 원인 재구성 (수정 전 코드 기준, `460c5d1~1:static/room.html`)

수정 전 `pollMessages()`:

```js
async function pollMessages() {
  if (!roomId) return;
  const res = await fetch(`/room/${roomId}/messages?since=${lastSeq}`);
  if (!res.ok) return;
  const data = await res.json();
  for (const m of data.messages) addMessage(m);
  if (data.messages.length) lastSeq += data.messages.length;
  ...
}
```

호출자는 두 군데다:

- `setInterval(pollMessages, 4000)` — 4초 주기 자동 폴링
- `sendRoomMessage()` — `POST /room/<id>/chat` 직후 `await pollMessages()` 수동 호출

`fetch`는 비동기라 `await` 지점에서 실행이 양보된다. 타이머 틱과 전송 직후 수동 호출이
겹치면, 두 호출이 **같은 `lastSeq` 값으로** `GET .../messages?since=N`을 시작한다.
서버는 둘 다에게 같은 N건의 목록을 돌려주고, 각 호출이 각자 `addMessage()`로 DOM에
추가하므로 화면에 같은 메시지가 두 개씩 나타난다. `lastSeq += length`도 두 번 실행되어
`lastSeq`가 실제보다 크게 뛸 수 있고(후속 조회 누락/불일치 가능), 커밋 메시지가 지적한 대로다.

제보("자신이 보낸 메시지가 자신에게 중복")와 정확히 일치한다: 본인 전송 직후에는 수동
`pollMessages()`가 항상 실행되므로, 본인 메시지가 중복 대상 1순위다. 타인 메시지도 같은
경쟁에 걸리면 중복될 수 있지만, 타이밍상 본인 메시지가 가장 자주 걸린다 — 추정.

## §1. 수정 리뷰 — `pollInFlight` 방식은 올바른가

수정 후 (`static/room.html:241-257`):

```js
let pollInFlight = false;
async function pollMessages() {
  if (!roomId || pollInFlight) return;
  pollInFlight = true;
  try {
    ... (동일)
  } finally {
    pollInFlight = false;
  }
}
```

### 올바름 (장점)

- JS는 싱글 스레드 + 논블로킹 I/O이므로, `pollInFlight` 체크→설정은 `await` 없이 동기 구간에서
  실행되어 원자적이다. 모든 폴링 경로(`setInterval`, `sendRoomMessage`, `startRoom` 초기 호출)가
  동일한 `pollMessages()`를 경유하므로, 가드를 우회하는 조회 경로가 없다. → 해당 경쟁은 완전히 닫힌다.
- `finally`로 플래그를 내리므로, `fetch` 실패·네트워크 예외·`!res.ok` 조기 리턴 중 어느 경우에도
  플래그가 영구히 `true`에 갇히는(폴링 영구 정지) 데드락이 없다. 이 점이 이 수정에서 가장 잘 된 부분이다.
- 동작 변경이 조회 스케줄에만 국한되고 렌더링·상태머신 로직을 건드리지 않아 회귀 위험이 최소다.

### "조용히 건너뛴다"의 부작용 — 문제 없음 (이유 포함)

건너뛰기가 발생하면 그 틱의 상태 반영(`ai_status`, 액션바, 참여자 수)이 최대 한 주기(4초) 늦어진다.
문제없는 이유:

1. 스킵은 "진행 중인 조회가 있다"는 뜻이고, 그 진행 중인 조회 자체가 최신 상태를 가져오므로
   정보 손실이 아니라 최대 수 초의 지연일 뿐이다. 4초 폴링 채팅의 UX 허용 범위 안이다.
2. 메시지 유실은 없다: 스킵된 틱이 가져왔을 범위는 다음 틱(또는 다음 전송 후 수동 폴)이 같은
   `lastSeq`로 다시 조회하므로 반드시 회수된다. `lastSeq`는 성공한 조회에서만 전진한다.
3. 전송 직후 수동 폴이 스킵되는 경우(자동 폴 진행 중과 겹침): 수동 폴의 목적은 "내 메시지 즉시 반영"인데,
   진행 중인 자동 폴이 어차피 같은 범위를 포함한 최신 목록을 가져오므로 체감 지연은
   수백 ms 수준이다 — 추정 (네트워크 왕복 1회 분).

대안(큐잉: 스킵 대신 완료 후 1회 재실행)과 비교하면, 큐잉은 상태 반영 지연을 줄이는 대신
불필요한 요청을 늘린다. 현재 트래픽 규모(4초 폴링, 소규모 방)에서는 스킵이 합리적인 선택이다.

## §2. 다른 중복 발생 경로가 남아 있는가

### (a) `lastSeq += data.messages.length`의 비원자성 → 가드로 완전히 커버됨. 예.

우려: 읽기-수정-쓰기가 `await`을 사이에 두고 있어 경쟁 가능. 그러나 `pollInFlight` 가드 덕분에
`pollMessages()` 본문은 절대 동시에 두 개가 실행되지 않으며, `lastSeq`를 쓰는 곳은
`pollMessages()` 본문(250행) 단 한 곳뿐이다(`addMessage`, `sendRoomMessage`는 `lastSeq`를
건드리지 않음을 전수 확인). 따라서 읽기→가져오기→전진 전체가 직렬화되고, 이 경쟁은 닫혔다.

남는 것은 견고성(fragility) 차원의 메모뿐이다: `lastSeq`가 메시지 `seq`가 아니라
"지금까지 받은 개수"이다. 서버가 append-only인 한(현재 `backend.py:_room_append`는 오직
`append`만 하며 삭제·재정렬이 없음) 개수==오프셋이 성립한다. 서버가 언젠가 메시지 삭제·이력
압축을 도입하면 깨질 수 있으나, 현재 코드 기준으로는 live 버그가 아니다.

### (b) `startRoom()` 초기 시퀀스 → 중복 가능성 없음. 예.

```js
async function startRoom() {
  await ensureRoom();
  ...
  await sendRoomMessage('');
  pollTimer = setInterval(pollMessages, 4000);
}
```

`setInterval` 등록이 `await sendRoomMessage('')`(POST + 폴 1회 완료) **이후**에 일어나므로,
초기 폴과 타이머 폴이 겹칠 수 없다. 순차 `await` 체인이라 초기 시퀀스 자체는 안전하다.

단, 바로 아래 (d)의 연타 시나리오와 결합되면 타이머가 2개 등록될 수 있다(렌더 중복은 아니고
트래픽 2배 — 자세한 것은 §4 제안 1).

### (c) `vote()` / `proceed()` → 동일하게 안전. 예.

```js
function vote(choice) { sendRoomMessage(choice); }
function proceed(choice) { sendRoomMessage(choice); }
```

둘 다 `send()`와 동일한 `sendRoomMessage()` 경로(POST 후 가드된 폴 1회)라서,
(c-1) 조회 경쟁에 의한 렌더 중복은 `pollInFlight`로 동일하게 막힌다.
(c-2) POST 자체는 가드 대상이 아니라서, 버튼 연타 시 동일 내용 POST가 2건 나가면
서버에 2건의 투표/진행 메시지가 **의도된 별개 기록으로** 남는다. 이는 "중복 렌더링"이 아니라
"중복 액션" 문제이며, 제보된 증상과 무관하다. 버튼 비활성화는 §4 제안 2로 분리했다.

### (d) 전수 훑기 — 그 외 `addMessage()` 호출 경로

`addMessage` 호출자는 `pollMessages()` 본문의 루프 단 한 곳뿐이다(232행 이전 함수 정의,
호출은 249행). 가드된 단일 진입점이므로, 현재 코드에서 겹친 범위를 두 번 렌더링하는 경로는
남아 있지 않다. `addMessage` 자체에 seq 기반 중복 제거가 없는 것은 사실이나, 진입점이
직렬화된 이상 필수 방어막은 아니다(제안 3은 어디까지나 벨트-앤드-서스펜더 차원).

## §3. 서버 측 검증 (OCI 실서버 curl, 2026-09-23)

새 방을 만들어 검증했으므로 기존 방 데이터에 영향을 주지 않았다. (`POST /room` → `6db160bc`)

| # | 요청 | 결과 |
|---|------|------|
| 1 | `POST /room` | `{"room_id":"6db160bc"}` — 새 방 발급 정상 |
| 2 | `GET /room/6db160bc/messages?since=0` (빈 방) | `messages: []` — 정상 |
| 3 | `POST /room/6db160bc/chat` (입장+`중복검증 메시지1`) | `{"ai_status":"IDLE"}` — 정상 |
| 4 | `GET ...?since=0` | 3건 반환, `seq: [0, 1, 2]` (system 입장 / chat 본문 / ai_reply). seq 단조증가·중복 없음 확인 |
| 5 | 동일 `since=0` 2회 연속 호출 | 바이트 동일 응답(추정: 질의 간 AI 상태 전이 없음 전제 — 본 검증 방은 `AWAIT_APPROVAL` 안정 상태). 서버 결정적 |
| 6 | 동일 `since=0` 동시 5연타 (ThreadPool, 클라이언트 race 재현) | 5개 응답 전부 `seq [0,1,2]` 동일. **서버는 같은 목록을 반복 반환할 뿐 중복을 만들어내지 않음** — 두 번 렌더링하면 화면에 6개가 되는 것은 전적으로 클라이언트 책임임을 실증 |
| 7 | 두 번째 메시지 전송 후 `since=0` / `since=3` | 전체 5건 `seq 0..4` 단조증가·집합 중복 없음. `since=3`은 정확히 신규 2건(`seq 3,4`)만 반환 — 증분 슬라이싱 정상 |
| 8 | `since=9999` (범위 초과) | `[]` — 정상 (클라이언트가 과도 전진해도 서버는 빈 목록, 크래시 없음) |
| 9 | 배포본 대조 `GET /room.html` (참고: `/static/room.html`은 404 — 서빙 경로가 `/room.html`임) | `pollInFlight` 4건 포함, **배포본이 로컬 `static/room.html`과 바이트 동일** — 수정이 실제로 OCI에 반영됨 확인 |

결론: 서버 응답은 결정적 슬라이스(`room["messages"][since:]`, `backend.py:678`)이며, seq는
서버 append 시점(`_room_append`, `len` 기반)에 부여되어 단조·유일하다. 서버 버그는 섞여 있지 않다.

## §4. 추가 수정 제안 (코드 수정 없이 제안만 — 작성자가 후속 검토 후 직접 반영)

어느 것도 제보 증상의 재현 경로가 아니므로 우선순위는 모두 낮음이다.

1. **입장 버튼 연타 → `startRoom()` 2회 실행 가능 (트래픽 2배).**
   `joinRoom()`에 가드가 없어 입장 버튼을 빠르게 두 번 누르면(또는 Enter 연타와 결합)
   `ensureRoom()`이 두 번 `POST /room`을 날리고(방 2개 생성, 뒤쪽이 유효 방이 됨),
   `setInterval`도 2개 등록된다. 렌더 중복은 `pollInFlight`가 막아주지만 폴링 트래픽이
   영구히 2배가 된다. 제안: `joinRoom()`에 "입장 진행 중" 플래그 또는 버튼 disable 1회성 처리.
   페이지 리로드 시 플래그·타이머가 초기화되므로 영구 부작용은 없다.
2. **전송/vote/proceed 버튼 연타 → 동일 액션 POST 중복.**
   `send()`·`vote()`·`proceed()`가 연타를 막지 않아, 더블클릭 시 동일 텍스트 POST가 2건 나가
   서버에 2건이 기록된다(투표 메시지가 2개 달리는 식). 렌더 버그가 아니라 UX/도메인 문제.
   제안: 전송 후 응답(또는 폴) 완료까지 버튼 disable, 혹은 1초 디바운스. 투표는 1인 1표로
   서버가 이미 집계(`room["votes"][member_id]` 덮어쓰기)하므로, 시스템 투표 안내 메시지가 2개
   찍히는 것만 감수하면 둘 수도 있다 — 정책 판단 필요.
3. **(선택, 방어 깊이) `addMessage()` 측 seq 기반 중복 제거.**
   현재는 진입점 직렬화에만 의존한다.将来 다른 조회 경로가 추가되거나 가드가 우회되는
   실수가 생기면 중복이 부활한다. 제안: 렌더된 `seq` 집합(예: `Set`)을 유지하고
   이미 본 `seq`는 스킵. 단, 이 경우 `lastSeq` 전진 로직과 정합(스킵해도 `lastSeq`는 응답 길이만큼
   전진해야 함 — 응답 자체는 서버 슬라이스라 정합이므로 문제없음)을 함께UT로 확인할 것.
   비용 대비 효과가 작으므로 "여유 될 때" 등급.
4. **(선택) `lastSeq`를 개수 가산이 아니라 서버 `seq` 기준으로.**
   `lastSeq = 마지막으로 받은 메시지의 seq + 1` 형태로 바꾸면 서버 측 삭제·압축이 도입돼도
   깨지지 않는다. 현재 append-only 서버에서는 동작이 동일하므로 리팩터링 등급.
   단, `GENERATING` 폴(`room_messages`가 GET 중에 ai 메시지를 append할 수 있음, `backend.py:671-675`)과
   결합된 타이밍은 다시 따져봐야 한다 — 추정.
5. **관측 메모 (수정 아님): 서빙 경로 확인.**
   OCI에서 `static/room.html`은 404이고 실제 서빙 경로는 `/room.html`이다.
   배포 스크립트가 복사·매핑하는 구조로 보이며(추정), 이후 검증 시에는 `/room.html`을 대조할 것.
   본 검증에서는 둘의 바이트 동일을 확인済み.

---

## 검증 작업 로그 (재현 가능성)

- 커밋 diff: `git show 460c5d1` (수정 전: `git show 460c5d1~1:static/room.html`)
- 서버 검증 방: `6db160bc` (검증용 신규 방, 기존 방 무영향)
- 배포본 대조: `curl http://144.24.91.250:8643/room.html` ↔ 로컬 `static/room.html` 바이트 동일
- `.env` 미열람, 코드 무수정, git 쓰기 작업 없음
