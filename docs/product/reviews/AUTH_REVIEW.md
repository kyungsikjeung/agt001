# AUTH_REVIEW - 카카오/구글 로그인 보안 검토 (작업 A1)

- 날짜: 2026-09-25
- 대상: app/services/auth.py, app/api/auth.py, app/db/models.py(UserRow, OAuthAccountRow, LoginSessionRow, OAuthStateRow, UserRoomRow), alembic/versions/0005_accounts.py, tests/unit/conftest.py, tests/unit/test_rooms.py, frontend/src/auth.ts
- 방법: 가짜 제공자로 전체 흐름을 테스트하는 tests/unit/test_auth.py 23개 작성 및 통과 확인, 코드 읽기. 실제 카카오/구글/NIM 호출 없음. 시크릿 실측을 피하려고 설정값은 전부 가짜 문자열만 썼고 .env는 열지 않았다. app/ 코드는 고치지 않았다.

## 테스트 매핑

| 항목 | 테스트 |
|---|---|
| 키 미설정 안내 | test_start_not_ready_without_keys |
| start 리다이렉트, state 쿠키 | test_start_redirect_and_state_cookie[kakao/google] |
| 정상 콜백, 세션 쿠키, /api/me | test_callback_success_sets_session_and_me[kakao/google] |
| state 쿠키 없음/불일치/재사용 | test_callback_state_cookie_missing, test_callback_state_mismatch, test_callback_state_reuse_rejected (각 kakao/google) |
| 제공자 거부 | test_callback_denied[kakao/google] |
| 열린 리다이렉트 방지 | test_next_open_redirect_blocked (//evil.com, https://evil.com, /\evil) |
| 재로그인 동일 사용자 | test_repeat_login_same_user_updates_nickname |
| 미인증/만료 세션 | test_me_without_cookie_401, test_me_expired_session_401 |
| 로그아웃 Origin 검사 | test_logout_origin_rejected, test_logout_success_clears_session |
| claim 권한/중복/Origin | test_claim_counts_only_participant_and_idempotent, test_claim_origin_rejected |

## 1. 로그인 CSRF

- 판정: 문제 없음
- 재현: state 쿠키를 지우거나 쿼리/쿠키 값을 변조한 뒤 콜백을 호출하면 /?login_error=kakao_state (또는 google_state)로 돌아간다. 테스트 d-1, d-2 통과.
- 고칠 방법: 해당 없음. state 원문은 쿠키와 DB(해시 저장)에 이중으로 두고 콜백에서 secrets.compare_digest로 비교하며, 제공자 일치와 만료를 확인한 뒤 바로 삭제하므로 공격자가 만든 로그인 흐름을 피해자에게 강요할 수 없다. 쿠키 이름의 __Host- 접두사가 서브도메인에서 쿠키를 덮어쓰는 공격도 막는다.

## 2. 열린 리다이렉트

- 판정: 문제 없음
- 재현: next=//evil.com, https://evil.com, /\evil 로 시작해도 로그인 뒤 Location이 / 가 된다. 테스트 f 통과.
- 고칠 방법: 해당 없음. safe_next가 같은 출처의 절대 경로만 허용하고 //, 백슬래시, ://, 300자 초과를 / 로 바꾼다. 정상 경로(/projects 등)는 그대로 유지된다.

## 3. 세션 고정

- 판정: 문제 없음
- 재현: 로그인에 성공할 때마다 서버가 secrets.token_urlsafe로 새 토큰을 발급하고, 로그인 전에는 세션이 존재하지 않으므로 공격자가 미리 심은 세션을 쓸 수 없다. 테스트 c, g 경유 확인.
- 고칠 방법: 해당 없음. 참고로 로그아웃은 현재 세션만 끊고 다른 기기의 세션은 유지되는데, 다기기 지원을 의도한 것으로 보이므로 그대로 둔다. 필요하면 "모든 기기에서 로그아웃" 기능을 추가할 수 있다.

## 4. 쿠키 속성

- 판정: 문제 없음
- 재현: start 응답의 __Host-agt001_oauth 쿠키와 콜백 응답의 __Host-agt001_session 쿠키가 모두 Secure, HttpOnly, SameSite=Lax, Path=/ 로 설정된다. 테스트 b, c에서 Set-Cookie 확인. __Host- 규칙(Domain 미지정, Path=/, Secure)을 지킨다.
- 고칠 방법: 해당 없음. 주의할 점으로, Secure 속성 때문에 http 환경에서는 쿠키가 오가지 않으므로 배포는 https가 전제되어야 한다. 테스트도 base_url=https://testserver 로 만들 때만 세션이 유지된다.

## 5. state 재사용과 만료

- 판정: 문제 없음
- 재현: 쓴 state로 다시 콜백을 호출하면 *_state 로 거부되고, state 유효기간은 10분이며 begin 때마다 만료된 행을 정리한다. 테스트 d-3 통과.
- 고칠 방법: 해당 없음. 동시에 같은 state를 쓰는 경우는 10번 항목을 본다.

## 6. PKCE

- 판정: 문제 없음
- 재현: 구글 start 주소에 code_challenge_method=S256 이 포함되고, 검증값(verifier)은 48바이트 무작위 값으로 DB에만 둔다. 카카오는 client_secret + state 방식을 쓴다. 테스트 b 통과.
- 고칠 방법: 해당 없음.

## 7. 제공자 토큰 비저장

- 판정: 문제 없음
- 재현: 액세스 토큰은 사용자 정보를 한 번 읽는 데만 쓰고 어디에도 저장하지 않으며, DB 스키마(0005)에도 토큰 컬럼이 없다. 가짜 exchange_code/fetch_profile 로 흐름 확인. 테스트 c 통과.
- 고칠 방법: 해당 없음.

## 8. claim 권한 검사

- 판정: 문제(낮음) 1건 포함. 서버 검사는 정상이다.
- 재현: 참여자(member_id 일치)인 방만 claimed에 셈하고, 남의 방과 없는 방은 0이며, 두 번째 호출은 ON CONFLICT DO NOTHING으로 0이다. Origin 검사도 있다. 테스트 j-1, j-2 통과.
- 문제: 프런트 계약(frontend/src/auth.ts의 claim())이 X-Member-Id 헤더를 보내지 않아, 실제 브라우저에서는 member_id가 빈 값으로 처리되어 항상 {"claimed": 0}이 된다. 서버는 스펙대로 동작하므로 테스트는 통과하고 xfail은 없다.
- 고칠 방법: 프런트가 방 입장 때 쓴 member_id를 X-Member-Id 헤더로 함께 보내거나, 서버가 바디에서 member_id를 받도록 계약을 바꾼다. 참고로 member_id는 스스로 주장하는 값이라 (room_id, member_id) 쌍을 아는 사람이 다른 계정으로 방을 가져갈 수 있지만, member_id는 참여자에게만 보이고 무작위 값이어서 위험은 낮다.

## 9. 오류 메시지 노출

- 판정: 문제 없음
- 재현: 실패하면 사용자에게 ?login_error=<제공자>_<코드>만 나가고 상세가 포함되지 않으며, 자세한 사유는 서버 로그로만 남는다(AuthError 코드 체계). 테스트 a, d, e 통과.
- 고칠 방법: 해당 없음.

## 10. 경쟁 조건

- 판정: 문제(낮음) 1건. 순차 재사용은 막히므로 관련 테스트는 통과하고 xfail은 없다.
- 재현: finish()가 state 조회와 삭제(트랜잭션 1) 뒤에 외부 토큰 교환을 하고 다시 로그인(트랜잭션 2)을 하므로, 같은 (code, state) 콜백이 동시에 들어오면 둘 다 state 행을 읽고 통과할 수 있다. 실제로는 제공자 인가 코드가 1회용이라 두 번째 토큰 교환이 실패할 가능성이 크고, state 유효기간도 10분이라 악용이 어렵다.
- 고칠 방법: state 행을 SELECT FOR UPDATE로 잠그고 콜백 처리가 끝날 때까지 한 트랜잭션으로 묶거나, state 사용 표시와 삭제를 원자적으로 처리한다.

## 결론

- 새 테스트 23개 전부 통과, 기존 포함 tests/unit 112개 전부 통과, xfail 0개.
- 발견한 문제 2건, 모두 낮음: 8번 프런트와 서버의 claim 계약 불일치, 10번 state 동시 재사용의 이론적 가능성. app/ 코드는 고치지 않았다.

## 조치 (Claude, 2026-09-26)

- #8 고침: `claim(roomIds, memberId)`가 `X-Member-Id`를 보낸다. 내 프로젝트 화면은 로그인하면 이 기기에 방이 없어도 목록을 부른다.
- #10 고침: state를 `DELETE … RETURNING` 한 문장으로 꺼내 동시 콜백 중 하나만 통과. 틀린 제공자·만료여도 state는 소모된다.
