# 사장님 로그인·가게 설정 페이지 (OWNER_SETTINGS_PLAN)

> 2026-09-28 (KST). 대표 결정: ① 사이트 만들어 보기는 로그인 없이, **공개하기·설정 페이지부터 로그인 필수** ② 문자는 **플랫폼 키 기본 + 사장님 키 선택**(설정 페이지에서 솔라피 키·발신번호 입력).
> 운영 방식은 [BUILD_W1_W2 §0](BUILD_W1_W2.md)과 같다. 관련: [CUSTOMER_PLAN §4](CUSTOMER_PLAN.md)(문자 인증), `app/services/auth.py`(`claim_rooms`), `app/services/keystore.py`(암호화).

## 1. 계약

**범위(대표 확인 2026-09-28)**: 사장님이 설정 페이지에서 넣는 키는 **문자(솔라피) 키만**이다. 카카오·AI·결제 등 다른 키는 넣지 않는다(플랫폼 키, 관리자 화면 D50).

### 1.1 공개에 로그인 필수 (`chat_flow._publish`)

- 공개 조건: 그 방의 방장(`rooms.owner_id(room)`)이 로그인해서 방을 계정에 붙였다 = `user_rooms`에 `(room_id, member_id = 방장)` 행이 있다. `room.html`은 이미 로그인하면 `/api/me/claim`으로 방을 붙인다.
- 없으면 공개하지 않고 답한다: `"공개하려면 먼저 로그인해 주세요. 카카오나 구글로 1분이면 돼요: <base_url>/auth/kakao/start?next=/room/<room_id>"` (구글 링크도 한 줄). 시안 고르기·다듬기는 그대로 된다.
- 이미 공개된 사이트를 다시 그리는 경로(다듬기·확정 뒤 다시 그리기)는 막지 않는다(처음 공개만 막음).
- 함수: `rooms.owner_claimed(room_id) -> bool` (새, `app/services/rooms.py`).

### 1.2 표 `shop_settings` (Alembic 0013)

| 칸 | 형 | 설명 |
|---|---|---|
| site_key | text PK | 가게 |
| phone_verify | bool, 기본 false | 이 가게 예약에 문자 인증 |
| solapi_key_enc, solapi_secret_enc | text null | 사장님 솔라피 키(Fernet 암호화, `keystore._fernet()`) |
| sms_sender | text null | 사장님 발신번호(숫자만) |
| key_last4 | text null | 화면 표시용 키 뒤 4자리 |
| updated_by | text null | users.id |
| updated_at | timestamptz | |

### 1.3 `app/services/shop_settings.py`

| 함수 | 계약 |
|---|---|
| `owned_sites(user_id) -> list[dict]` | 계정에 붙은 방 중 **방장인 방**의 `{site_key, room_id, shop_name, published}` |
| `can_edit(user_id, site_key) -> bool` | 위 목록에 있으면 True |
| `get(site_key) -> dict` | `{phone_verify, own_key: bool, key_last4, sms_sender}` — 비밀값은 절대 돌려주지 않음 |
| `update(user_id, site_key, phone_verify=None, solapi_key=None, solapi_secret=None, sms_sender=None, clear_key=False)` | 권한 없으면 `PermissionError`. 키는 key·secret·발신번호 셋이 함께 올 때만 저장(`SettingsError` 한 줄 사유). `TOKEN_ENC_KEY`가 없으면 자기 키 저장 불가(`SettingsError("서버 설정 때문에 지금은 자기 키를 넣을 수 없어요.")`) |
| `sms_credentials(site_key) -> tuple \| None` | 복호화한 `(key, secret, sender)` — 서버 안에서만 씀 |
| `phone_verify_on(site_key) -> bool` | `phone_verify` 켜짐 **그리고** `sms.available(site_key)` |

### 1.4 `sms.py` 바뀜

- `send(to, text, site_key=None)`: 가게 키가 있으면 그것, 없으면 플랫폼 키(`settings.solapi_*`, `settings.sms_sender`), 둘 다 없으면 개발 모드(로그만, True).
- `available(site_key=None) -> bool`: 가게 키 또는 플랫폼 키가 있으면 True. 개발 모드(`settings.sms_dev_mode`, 기본 False)면 True.
- `check_key(key, secret) -> bool`: 솔라피 잔액 조회 `GET https://api.solapi.com/cash/v1/balance`가 200이면 True(연결 테스트).
- 전역 `booking_phone_verify` 설정은 없앤다 → 가게별 `shop_settings.phone_verify_on(site_key)`. `phone_verify.start`는 `sms.send(..., site_key=site_key)`.

### 1.5 설정 페이지·API (로그인 필수, 아니면 401 / 페이지는 로그인 안내)

| 경로 | 내용 |
|---|---|
| `GET /settings` | `static/settings.html`(스크립트는 우리 도메인이라 가능, room.html과 같은 방식). 내 가게 목록 → 가게마다: 문자 인증 켜기 스위치, "플랫폼 번호로 보내기(기본) / 내 솔라피 키로 보내기", 키·시크릿·발신번호 입력(저장 뒤에는 뒤 4자리만), 연결 테스트, 키 지우기, 솔라피 가입·발신번호 등록 안내 3줄 |
| `GET /api/me/shops` | `owned_sites` + 각 `get` |
| `PUT /api/me/shops/{site_key}/settings` | JSON `{phone_verify?, solapi_key?, solapi_secret?, sms_sender?, clear_key?}` → `update`. 403(남의 가게)·400(`SettingsError`) |
| `POST /api/me/shops/{site_key}/sms-test` | 저장 전 키로 `check_key` → `{ok}` |
| 모든 변경 | 기존 `_check_origin`(auth.py)으로 다른 사이트에서 보낸 요청 막기 |

`room.html` 머리에 로그인했으면 "가게 설정" 링크.

## 2. 물결

### 1물결 (동시에)

| 작업 | 소유 파일 | 완료 확인 |
|---|---|---|
| **S1** 공개 로그인 | `app/services/chat_flow.py`(`_publish`만), `app/services/rooms.py`(`owner_claimed`만 추가), `tests/unit/test_publish_login.py`(새, DB) | 안 붙은 방은 공개 안 됨 + 로그인 링크, 붙은 방은 공개. 설정 `publish_login_required`(기본 True, 테스트 conftest는 false — Claude가 미리 넣음) |
| **S2** 가게 설정 저장 | `alembic/versions/0013_shop_settings.py`(새), `app/db/models.py`(ShopSettingsRow만), `app/services/shop_settings.py`(새), `app/services/sms.py`, `app/services/phone_verify.py`(`site_key` 넘기기만), `tests/unit/test_shop_settings.py`(새, DB) | 암호화 저장·비밀값 안 나옴·권한·가게 키 우선·플랫폼 키 대체·개발 모드 |

### 2물결

| 작업 | 소유 파일 | 완료 확인 |
|---|---|---|
| **S3** 설정 API·페이지·예약 연결 | `app/api/settings.py`(새), `app/main.py`(라우터 한 줄), `app/api/public.py`(`/settings` 한 줄), `static/settings.html`(새), `static/room.html`(링크만), `app/api/bookings.py`(전역 설정 → `phone_verify_on`), `app/config.py`(`booking_phone_verify` 삭제, `sms_dev_mode` 추가), `tests/unit/test_settings_api.py`(새), `tests/unit/test_bookings_verify.py` | API 권한·400·403·401, 가게별 인증 켜기가 예약에 반영 |

## 3. 진행 기록

| 물결 | 결과 | Claude 검토 |
|---|---|---|
| 1 (S1·S2) | 처음 공개는 방장이 로그인해 방을 붙였을 때만(안 붙었으면 카카오·구글 로그인 링크), `shop_settings` 표(0013)·암호화 저장·가게 키 → 플랫폼 키 → 개발 모드 순서 | 계약 오류를 OpenCode가 잡음: 세션에 `id`가 없어 방을 `requirement_id`로 찾음(Claude가 쓰지 않는 갈래 삭제). 가게 키를 못 풀면 예약이 멈추지 않고 플랫폼 키로 |
| 2 (S3) | `/settings` 페이지(로그인 안내·가게별 문자 인증 스위치·보낼 번호 선택·솔라피 키 입력·연결 테스트·키 지우기), `/api/me/shops` API, 예약 문자 인증이 가게별로, 채팅방에 "가게 설정" 링크, 전역 `BOOKING_PHONE_VERIFY` 삭제 → `SMS_DEV_MODE` | 390px 캡처로 로그인 전후 화면 확인. 비밀값이 입력칸·응답에 다시 안 나옴 |

**검증(2026-09-28)**: 전체 876개 통과, `draft_fit` 24건 PASS.
**배포 주의**: 마이그레이션 0011·0012·0013. 사장님 키 저장에는 서버 `TOKEN_ENC_KEY` 필요.

## 변경 이력

| 날짜 | 내용 |
|---|---|
| 2026-09-28 | 처음 작성 |
| 2026-09-28 | 1·2물결 완료 기록 |
