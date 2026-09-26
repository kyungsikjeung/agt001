# 채팅방 기능 API 계약 (2026-09-26, Claude 확정 — 화면 작업은 이 계약대로)

근거: docs/product/ROOM_POLICY.md(방장·초대·타이머), DECISIONS D23·D27(직접 편집), D32(문의 → 사장님 카톡), BACKLOG.
공통: 본인 확인은 헤더 `X-Member-Id: <이 기기 member_id>`(localStorage `agt001_member_id`). 방장만 되는 요청을 방장이 아닌 사람이 보내면 403.
남에게 보이는 참여자 식별자는 `member_handle`(member_id가 아님).

## 1. 방 조회 응답에 추가되는 칸 (`GET /room/{id}/messages`)

```json
{
  "members": [{"member_handle": "h1", "nickname": "사장님", "is_owner": true, "joined_at": "...", "last_seen": "..."}],
  "me": {"member_handle": "h1", "is_owner": true},
  "closed": false,
  "invite_required": true
}
```
메시지 `kind`에 추가: `"photo"`(글에 사진 주소, 아래 §4), `"warning"`(타이머 사전 경고, 시스템 메시지처럼 보이되 노란 톤).
`photo` 메시지: `{"kind": "photo", "text": "사진을 올렸어요", "photo": {"id": "...", "url": "/uploads/<room>/<id>.jpg"}}`

## 2. 방장·나가기

| 요청 | 본문 | 응답 | 비고 |
|---|---|---|---|
| `POST /room/{id}/owner` | `{"to": "<member_handle>"}` | `200 {"owner": "<member_handle>"}` | 방장만. 방에 "OO님이 방장이 됐어요" 시스템 메시지 |
| `POST /room/{id}/leave` | 없음 | `204` | 참여자 누구나. 방장이 나가면 가장 먼저 들어온 참여자가 방장. 마지막 한 명이면 방은 남고 참여자만 0명 |

## 3. 초대 링크

| 요청 | 본문 | 응답 |
|---|---|---|
| `POST /room/{id}/invites` | `{"days": 1 \| 7 \| 30 \| 0}` (0 = 무기한, 기본 7) | `201 {"invite_id", "url": "/room.html?room=<id>&invite=<token>", "expires_at": "...\|null"}` |
| `GET /room/{id}/invites` | — | `200 {"invites": [{"invite_id", "created_at", "expires_at", "revoked": false, "uses": 2}]}` |
| `DELETE /room/{id}/invites/{invite_id}` | — | `204` (폐기) |

- 모두 방장만. 토큰 원문은 발급 응답의 `url`에만 한 번 나온다(서버에는 해시만).
- 입장: 처음 들어오는 사람은 `POST /room/{id}/chat` 본문에 `"invite": "<token>"`을 함께 보낸다. 방에 이미 있는 사람·방을 만든 첫 사람은 필요 없다.
- 실패: `403 {"detail": "invite required"}`(없음), `403 {"detail": "invite invalid"}`(틀림·폐기·만료), `403 {"detail": "room full"}`(10명), `423 {"detail": "room closed"}`.
- 화면: `room.html?room=X&invite=T`로 열리면 invite를 기억했다가 첫 입장 메시지에 붙인다. 공유 버튼은 방 주소 대신 **초대 링크를 새로 발급해** 공유한다(방장만 보임). 방장이 아니면 "방장에게 초대 링크를 받아 주세요".

## 4. 사진

| 요청 | 본문 | 응답 |
|---|---|---|
| `POST /room/{id}/photos` | multipart `file`(JPEG·PNG·WebP, 10MB 이하), 선택 `caption` | `201 {"id", "url"}` |
| `DELETE /room/{id}/photos/{photo_id}` | — | `204` (올린 사람 또는 방장) |

- 서버가 위치 정보(EXIF)를 지우고 긴 변 1600px로 줄여 JPEG로 저장한다. 원본은 보관하지 않는다.
- 사진 주소 `/uploads/...`는 생성물 전용 주소(144-24-91-250.sslip.io)에서 열린다(앱 주소는 308로 보냄).
- 올린 사진은 요구사항 카드에 들어가 **시안과 공개 사이트의 대표 사진·사진첩에 쓰인다**(다음 시안·다음 공개부터).
- 방에 `photo` 메시지가 남는다.

## 5. 직접 편집 (`/editor?room=<id>`)

| 요청 | 응답·본문 |
|---|---|
| `GET /api/rooms/{id}/card` (참여자) | `{"title", "industry", "fields": [{"key", "label", "value", "status", "fact": true, "placeholder": true}], "photos": [{"id","url","caption"}], "choice": "v2"\|null, "published": "v2"\|null, "site_url": "...\|null", "can_edit": true}` |
| `PUT /api/rooms/{id}/card` (방장) | 본문 `{"fields": {"<key>": "<value>"}}` → `200` 위와 같은 모양. 값이 빈 문자열이면 그 칸을 자리 표시로 되돌린다. 공개했으면 사이트를 바로 다시 연다 |

- 편집할 수 있는 칸: shop_name, phone, hours, location, price, offerings(쉼표 구분), detail, target, contact_method.
- `status`: filled(사장님이 말함)·assumed(가정)·placeholder(입력 필요)·pending_owner(방장 확인 대기).

## 6. 문의를 사장님 카카오톡으로 (D32 ①)

| 요청 | 설명 |
|---|---|
| `GET /auth/kakao/start?talk=1&next=<방 주소>` | 카카오 로그인 + "카카오톡 메시지 전송" 추가 동의. 돌아오면 서버가 이 계정에 알림용 토큰(암호화)을 저장 |
| `GET /api/rooms/{id}/notify` (참여자) | `{"kakao": {"linked": true, "owner_linked": true}}` — 방장의 카톡 알림이 켜져 있는지 |
| `DELETE /api/me/notify/kakao` (로그인) | 알림 끄기(토큰 삭제) |

- 켜는 조건: 방장이 카카오로 로그인했고, 그 방이 방장 계정에 옮겨져 있음(`POST /api/me/claim`).
- 화면: 방장에게만 "문의를 카톡으로 받기" 버튼. 누르면 `/auth/kakao/start?talk=1&next=/room.html?room=<id>`로 이동, 돌아오면 `POST /api/me/claim`을 한 번 보낸다.
- 사이트 문의가 오면 채팅방 알림과 함께 방장 카톡 "나에게 보내기"로도 간다. 실패해도 채팅방 알림은 남는다.

## 7. 타이머 사전 경고 (ROOM_POLICY §4.2)

투표 20시간·견적 6일·닫힘 27일에 한 번씩 `warning` 메시지: "투표가 4시간 뒤 초기화돼요", "견적이 하루 뒤 만료돼요", "3일 뒤 방이 닫혀요(활동하면 연장)". 방장 카톡 알림이 켜져 있으면 카톡으로도.
