# 계약서: 손님 ↔ 사장님 채팅 (GUEST_CHAT_CONTRACT)

> 2026-10-01 (KST) / Claude 작성, OpenCode 구현, Claude 검토. 계획 [OWNER_FEEDBACK_1001_PLAN](OWNER_FEEDBACK_1001_PLAN.md) §6, 결정 D58 ④(베타 전).
> **기존 예약 채팅을 넓힌다(새 주소를 만들지 않는다).** 이미 있는 `GET /chat/{site_key}`(static/chat.html)와 `POST /api/chat/{site_key}`(`chat_agent.respond`)가 있다. 손님 토큰은 가게별 HttpOnly 쿠키이고, 서버에는 해시(`AgentThreadRow.token_hash`)만 둔다. AI가 가게 정보로 먼저 답하고, 모르면 지금은 사장님 채팅방에 알림만 보낸다(`_ask_owner`). **사장님이 손님에게 답할 길이 없는 것**을 채운다.
> 재사용: `chat_agent`(쿠키 토큰·해시·요청 제한), 사장님 화면 `static/owner.html`의 탭, `app/api/owner.py`의 가게 권한 확인, `notify.owner_kakao`(카톡 나에게 보내기, 동의한 사장님만), `rooms._append`(채팅방 알림), 문의 보관 기간 규칙.

## 0. 결론

- 손님 채팅 페이지 대화(손님 글·AI 답·사장님 답)를 **저장**한다. AI가 모르는 질문이나 "사장님께 직접 물어보기"는 대화를 **사장님 대기**로 둔다.
- 사장님은 **내 가게 → 채팅 탭**에서 대화 목록을 보고 답한다. 차단할 수도 있다.
- 손님 페이지는 사장님 답을 **4초마다** 받아 온다(채팅방 `room.html`과 같은 방식). 실시간 연결은 쓰는 가게가 늘면 붙인다.
- 새 사장님 대기 대화가 생기면 알린다. 채팅방에는 한 줄을 남기고, 카톡은 동의한 사장님에게만 **글 원문 없이** "새 채팅이 왔어요 + 링크"를 보낸다. 같은 대화는 10분에 한 번만 알린다.
- 공개 사이트에는 **"채팅하기" 단추(새 탭 링크) 하나**만 둔다. 가게가 채팅을 켰을 때만 보인다(기본 켜짐, 사장님 화면에서 끌 수 있음). 외부 스크립트는 없다.

## 1. 데이터 (마이그레이션 0019)

| 표 | 칸 |
|---|---|
| `guest_chat_threads` | `id` bigserial PK, `shop_id` text FK shops.site_key, `token_hash` text, `status` text(`ai`·`owner`·`closed`·`blocked`), `owner_unread` int, `last_at` timestamptz, `notified_at` timestamptz null, `created_at`. 유일(shop_id, token_hash). 색인(shop_id, last_at desc) |
| `guest_chat_messages` | `id` bigserial PK, `thread_id` FK cascade, `sender` text(`guest`·`ai`·`owner`), `text` text(500자 제한), `created_at`. 색인(thread_id, id) |

- 보관: 마지막 글 뒤 30일이 지나면 지운다(`chat_agent.purge`와 같은 곳에서 부른다). 전화번호 모양은 저장 전 가리지 않는다. 손님이 사장님께 남기는 연락처라서다. 대신 화면에서만 보이고 로그에 찍지 않는다.
- 가게 설정: `shop_settings`의 `guest_chat_on`(기본 True).

## 2. 서버

| 번호 | 무엇 | 파일 |
|---|---|---|
| 1 | `guest_chat.log(site_key, token_hash, sender, text)`: 대화가 없으면 만들고 글 추가, `last_at` 갱신. owner 대기면 `owner_unread += 1` | `app/services/guest_chat.py`(신규) |
| 2 | `chat_agent.respond`: 손님 글과 돌려준 답을 `log`로 남긴다(글이 있는 요청만, 단추 action은 action 이름을 글로 남기지 않음). `_ask_owner`가 불릴 때 대화 `status = "owner"` + 알림(§0) | `app/services/chat_agent.py`(두세 줄) |
| 3 | 대화가 `owner`이면 손님 새 글은 AI를 거치지 않는다. 저장하고 답은 "사장님께 전했어요" 한 번(연달아 보낼 때는 답 없음) | 같은 파일 |
| 4 | 새 action `"owner"`: "사장님께 직접 물어보기" 단추 → `status = "owner"` + 안내 "무엇이든 적어 주세요. 사장님이 확인하면 여기로 답해요 · 영업시간 ○○" | 같은 파일 |
| 5 | `GET /api/chat/{site_key}/messages?after=<id>`(쿠키 토큰) → `{"messages":[{id,sender,text,at}], "status"}`. 토큰이 없거나 대화가 없으면 빈 목록. 요청 제한은 기존 `_allow` | `app/api/chat_agent.py` |
| 6 | 사장님: `GET /api/owner/shops/{site_key}/chats` → 대화 목록(최근 50, `id, status, owner_unread, last_at, last_text` 40자). `GET …/chats/{id}` → 글 전부 + `owner_unread = 0`. `POST …/chats/{id}` `{text}`(1~500자) → owner 글. `POST …/chats/{id}/block`·`/close`. 권한은 기존 owner 경로와 같게 | `app/api/owner.py` |
| 7 | `guest_chat_on`이 꺼지면 `/chat/{site_key}` 페이지는 "지금은 채팅을 받지 않아요 + 전화·문의 안내"를 보인다. 기존 예약은 그대로 | `app/api/chat_agent.py` |
| 8 | 공개 사이트 "채팅하기": 연락 구역(contact)과 행동 바에 `/chat/{site_key}` 새 탭 링크를 둔다(`guest_chat_on`일 때). 기존 예약 구역의 채팅 링크는 그대로 | `app/services/site_data.py`·`site_render.py`·템플릿 한 줄씩 |

## 3. 화면

| 번호 | 무엇 | 파일 |
|---|---|---|
| 1 | 손님 채팅 페이지: 첫 단추 줄에 "사장님께 직접 물어보기". 사장님 글은 다른 색 말풍선 + "사장님". `status`가 owner이면 4초마다 `messages?after=`를 부르고 탭이 숨으면 멈춘다. 처음 보낼 때 개인정보 안내 한 줄("적어 주신 글은 가게에 전달되고 30일 뒤 지워져요") | `static/chat.html` |
| 2 | 사장님 화면 "채팅" 탭: 목록(안 읽은 수 배지, 사장님 대기 먼저) → 대화 보기 → 답 입력(글 + 기존 마이크, 자동 전송 없음) → 보내기, 차단·닫기. 10초마다 목록 갱신(탭이 보일 때만). "손님 채팅 받기" 켜기·끄기 | `static/owner.html` |
| 3 | 빌더 기능 칩에 "채팅"을 둔다(공개 뒤 켜는 칩과 같은 종류: 누르면 "공개한 뒤 사장님 화면에서 켜고 끌 수 있어요, 기본 켜짐" 안내) | `app/api/start.py`의 features 목록 한 줄 |

## 4. 작업 묶음

| 묶음 | 파일(소유) | 선행 |
|---|---|---|
| G1 서버 | `alembic/versions/0019_guest_chat.py`, `app/db/models.py`(표 2개), `app/services/guest_chat.py`, `app/services/chat_agent.py`, `app/api/chat_agent.py`, `app/api/owner.py`, `app/services/shop_settings.py`(`guest_chat_on`), `tests/unit/test_guest_chat.py` | 없음 |
| G2 손님 페이지 | `static/chat.html` | G1 응답 모양(§2-5)만 |
| G3 사장님 탭 | `static/owner.html` | G1 응답 모양(§2-6)만 |
| G4 사이트 단추·칩 | `app/services/site_data.py`·`site_render.py`·`templates/sections/contact--*.mustache`(한 줄씩), `app/api/start.py` | G1, NOTICE N1·N2(같은 파일) |

**하지 말 것**: 공개 사이트 안에 채팅 창·스크립트 넣기, 손님 토큰 원문 저장, 카톡에 글 원문 보내기, 다른 가게 대화 보이기(모든 owner 경로는 site_key 권한 확인), 새 의존성, 새 LLM 호출.

## 5. 합격 테스트

| 번호 | 테스트 |
|---|---|
| 1 | 손님 글 → AI 답 → 둘 다 저장. 모르는 질문 → status owner + 채팅방 한 줄 + 알림(10분 안 두 번째는 알림 없음) |
| 2 | owner 상태에서 손님 글은 AI 없이 저장, 연달아 보내면 두 번째부터 답 없음. action owner로 바로 owner |
| 3 | 사장님 목록·보기(안 읽음 0으로)·답·차단. 다른 가게 사장님 403. 차단한 대화는 손님 글 저장 안 함 + "지금은 보낼 수 없어요" |
| 4 | `messages?after=` 쿠키 없음 → 빈 목록, 다른 손님 쿠키로 남의 글 못 봄 |
| 5 | 30일 지난 대화 삭제, `guest_chat_on` 끄면 페이지 안내 |
| 6 | 공개 사이트: 켜짐이면 "채팅하기" 새 탭 링크, 꺼짐이면 없음, `publish_check` 통과 |
| 7 | Claude: 390px로 손님 질문 → 사장님 답 → 손님 화면에 답 표시 흐름 캡처 |

## 변경 이력

| 날짜 | 내용 |
|---|---|
| 2026-10-01 | 처음 작성 (D58 ④). 새 주소 대신 기존 예약 채팅(`/chat/{site_key}`)을 넓힘 |
