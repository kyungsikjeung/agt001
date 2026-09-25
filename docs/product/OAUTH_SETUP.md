# OAuth 구현 준비 문서 — 카카오 + 구글 (WP 1-0a)

> 작성일: 2026-09-25 / WP: 1-0a (계획) / 소유 파일: 본 문서 1개
> 대상: agt001, FastAPI, `https://144.24.91.250.sslip.io` (Caddy + Let's Encrypt)
> 상위: [PRODUCT_ROADMAP.md](PRODUCT_ROADMAP.md) 1단계, [DELIVERY_PIPELINE.md](DELIVERY_PIPELINE.md) WP 1-0a → 1-2/1-6 입력 문서
> 근거: [LANDING_AUTH_DB_UPLOAD_PLAN.md](../hackathon/LANDING_AUTH_DB_UPLOAD_PLAN.md) §2.1~2.2 (인증 API·세션 설계), [ENVIRONMENT.md](../hackathon/ENVIRONMENT.md) §3-5·§3-6 (도메인·카카오 앱 현황)
> 표기 규칙: 웹 검색으로 확인한 사실은 출처 URL 병기. 확인하지 못한 것은 **(추정)** 표기.

## 0. 현재 상태 (읽은 문서 기준 — 추가 등록이 필요한 것만 뽑음)

| 항목 | 상태 |
|---|---|
| 카카오 앱 | `agt001` (ID 1585973) 존재. JS 키 발급됨 (ENVIRONMENT.md §3-6) |
| 카카오 등록 도메인 | `http://144.24.91.250.sslip.io:8643` — "웹 도메인" + "JS SDK 도메인" 2곳에만 등록됨 |
| 카카오 로그인 활성화 ON 여부 | 미확인 **(추정: 아직 안 했을 가능성 높음 — 직접 확인 필요)** |
| 카카오 Redirect URI (`https://144.24.91.250.sslip.io/auth/kakao/callback`) | 미등록 **(추정)** — REST API 로그인은 웹 도메인 등록과 별개로 Redirect URI 등록이 필수이며 KOE006 에러 원인이 됨 |
| 카카오 REST API 키 / Client Secret | 값 미확인 (본 문서는 키 이름만 제안, 값 기재 금지) |
| HTTPS (`https://144.24.91.250.sslip.io`) | Caddy + Let's Encrypt 전제. 카카오 콘솔·구글 콘솔에 HTTPS 기준 URI를 등록해야 함 |
| 구글 Cloud 프로젝트 / OAuth 클라이언트 | 없음 **(추정)** — 신규 생성 필요 |

---

## 1. 카카오 로그인 (REST API, 서버 사이드 authorization code flow)

공식 문서: https://developers.kakao.com/docs/latest/en/kakaologin/rest-api ,
설정 전제조건: https://developers.kakao.com/docs/ko/kakaologin/prerequisite

### 1.1 엔드포인트·파라미터

| 단계 | 메서드·URL | 파라미터 |
|---|---|---|
| ① 인가 코드 요청 | `GET https://kauth.kakao.com/oauth/authorize` | `client_id`={REST API 키} (필수), `redirect_uri`={등록된 URI와 정확히 일치} (필수, 불일치 시 KOE006), `response_type=code` (고정), `state`={난수, 권장}, `scope`={추가 동의항목 ID 목록, 선택} |
| ② 콜백 수신 | `GET {redirect_uri}?code={인가코드}&state={...}` (HTTP 302) | 실패 시 `error`, `error_description`으로 리다이렉트됨 |
| ③ 토큰 발급 | `POST https://kauth.kakao.com/oauth/token` (`Content-Type: application/x-www-form-urlencoded`) | `grant_type=authorization_code` (고정), `client_id`, `redirect_uri` (①과 동일해야 함), `code`, `client_secret` (아래 1.3 참고) |
| ④ 사용자 정보 조회 | `GET` 또는 `POST https://kapi.kakao.com/v2/user/me` (`Authorization: Bearer {access_token}`) | 응답: `id`(회원번호), `kakao_account`(profile/nickname, email 등 — 동의항목에 따라), `properties` |
| (참고) 토큰 정보 확인 | `GET https://kapi.kakao.com/v1/user/access_token_info` | 만료 검증용 |
| (참고) 로그아웃 | `POST https://kapi.kakao.com/v1/user/logout` (토큰 무효화), 카카오계정까지 로그아웃은 `GET https://kauth.kakao.com/oauth/logout` | 후자는 로그아웃 Redirect URI 별도 등록 필요 |
| (참고) 연결 끊기(탈퇴) | `POST https://kapi.kakao.com/v1/user/unlink` | 추후 탈퇴 기능용 |

- REST API 방식 access token 유효기간: **6시간**, refresh token 2개월(만료 1개월 전부터 갱신 가능). 출처: https://developers.kakao.com/docs/en/kakaologin/common
- 에러 코드: 로그인 OFF 상태 요청 시 **KOE004**, Redirect URI 불일치 시 **KOE006**. 출처: https://developers.kakao.com/docs/ko/kakaologin/prerequisite

### 1.2 카카오 개발자 콘솔 설정 (사용자가 할 일 — §5 체크리스트로 전개)

경로 기준: https://developers.kakao.com/console/app (내 애플리케이션 > `agt001`)

1. **[카카오 로그인] > [사용 설정] > 상태 ON** (필수. OFF면 KOE004).
2. **Redirect URI 등록** (필수): `https://144.24.91.250.sslip.io/auth/kakao/callback` — 정확히 일치해야 함 (末尾 슬래시·쿼리 유무까지 비교하므로 상수로 고정).
   등록 위치는 콘솔 UI 개편에 따라 [카카오 로그인] 메뉴 또는 [앱] > [플랫폼 키] > [REST API 키] 하단에 있음 **(추정 — 콘솔에서 직접 확인)**.
3. **동의항목** ([카카오 로그인] > [동의항목]):
   - 닉네임·프로필 사진: 기본 제공, 별도 심사 없이 필수/선택 동의로 설정 가능 **(추정 — 1단계는 닉네임 필수 동의만으로 충분)**.
   - 카카오계정(이메일): **비즈앱 전환 필요 (추정)**. 일반 앱은 선택 동의도 제한될 수 있으므로, 이메일이 필요하면 비즈앱 전환(사업자 정보 등록, 별도 심사 없음 — 출처: https://developers.kakao.com/docs/ko/kakaosync/prerequisite §1) 후 설정. 1단계 권장: **이메일 없이 닉네임만** (users.email NULL 허용 — LANDING_AUTH_DB_UPLOAD_PLAN §3.1 스키마와 정합).
   - 동의항목별 정확한 권한 표는 콘솔의 동의항목 설정 화면에서 직접 확인 (문서 개정이 잦으므로 콘솔 표시를 최종 기준으로).
4. 기존 등록(`http://144.24.91.250.sslip.io:8643` 웹 도메인·JS SDK 도메인)은 **유지** (카카오톡 공유 기능이 사용 중). HTTPS 도메인 추가 등록 필요 여부는 콘솔 안내에 따름 **(추정: 웹 도메인에도 `https://144.24.91.250.sslip.io` 추가 권장)**.

### 1.3 REST API 키 vs Client Secret

- 인가 코드 요청(①): **REST API 키** (`client_id`) 사용. JS 키 아님에 주의.
- 토큰 발급(③): 카카오 정책상 **REST API 키에 Client Secret 기능이 기본 활성화 상태로 추가**되므로, 대응 파라미터(`client_secret`)를 포함해야 함. 출처: https://developers.kakao.com/docs/latest/en/kakaologin/rest-api ("Caution: Default activation of Client secret for REST API key").
- 위치: [앱] > [플랫폼 키] > [REST API 키] > [클라이언트 시크릿]. 출처: https://developers.kakao.com/docs/ko/kakaologin/prerequisite
- 기존 앱(`agt001`, 생성 시기 오래됨)은 Secret이 비활성화 상태일 수 있음 **(추정)**. 콘솔에서 상태 확인 후, 활성화돼 있으면 `KAKAO_CLIENT_SECRET` 발급·보관, 비활성화면 토큰 요청에서 제외 (구현 시 양쪽 분기 또는 설정 플래그 권장 — WP 1-2 입력).

### 1.4 카카오톡 ID·친구 관련 권한 (전제: 별도 선택 옵션)

- 본 서비스의 "카카오톡 ID"는 **사용자가 직접 입력하는 별도 프로필 필드** (`users.kakao_talk_id`)이며 로그인 식별자로 쓰지 않음 (PRODUCT_ROADMAP 1단계, LANDING_AUTH_DB_UPLOAD_PLAN §2.1).
- 따라서 아래 API 권한은 **1단계에 불필요**. 참고용으로만 기재:
  - 카카오톡 친구 목록(`friends`): 이용 중 동의 + **사용 권한 신청(검수) 필요 (추정 — 출처: 2021년 기준 정리 https://kakao-tam.tistory.com/52, 콘솔에서 최신 조건 확인 요망)**. 필수 동의로는 설정 불가.
  - 카카오톡 메시지 발송: 검수 필요 (추정 — 카카오톡 공유 JS SDK는 이미 사용 중이므로 혼동 주의: 공유하기는 SDK 기능, 친구 API와 별개).
- 결론: WP 1-2 구현 범위에 친구·메시지 API를 포함하지 않음.

---

## 2. 구글 로그인 (OpenID Connect authorization code flow)

공식 문서: OIDC 개요 https://developers.google.com/identity/openid-connect/openid-connect ,
엔드포인트 레퍼런스 https://developers.google.com/identity/openid-connect/reference ,
클라이언트 생성 https://developers.google.com/identity/gsi/web/guides/get-google-api-clientid ,
정책 https://developers.google.com/identity/protocols/oauth2/policies

### 2.1 엔드포인트·파라미터

Discovery 문서: `https://accounts.google.com/.well-known/openid-configuration` (인가·토큰·userinfo·JWKS URI 포함 — 하드코딩 대신 discovery 사용 권장).

| 단계 | 메서드·URL | 파라미터 |
|---|---|---|
| ① 인가 요청 | `GET https://accounts.google.com/o/oauth2/v2/auth` | `client_id`, `redirect_uri`(등록값과 exact match — scheme·대소문자·末尾 슬래시까지 일치, 출처: https://developers.google.com/identity/protocols/oauth2/javascript-implicit-flow ), `response_type=code`, `scope=openid email profile`, `state`(필수, CSRF), `nonce`(권장, §3), `access_type=offline`+`prompt=consent` (refresh token이 필요할 때만 — 1단계는 불필요하므로 사용 안 함) |
| ② 콜백 수신 | `GET {redirect_uri}?code=...&state=...` | 실패 시 `error=access_denied` 등 |
| ③ 토큰 교환 | `POST https://oauth2.googleapis.com/token` | `code`, `client_id`, `client_secret`, `redirect_uri`(①과 동일), `grant_type=authorization_code` |
| ④ 신원 확인 | ③ 응답의 **`id_token`(JWT) 검증** (아래 2.4) | `sub`를 `provider_user_id`로 사용. userinfo 엔드포인트(`https://openidconnect.googleapis.com/v1/userinfo`) 호출은 보조 수단 (id_token 검증이 1순위) |

### 2.2 Google Cloud Console 절차 (사용자가 할 일 — §5 체크리스트로 전개)

경로 기준: https://console.cloud.google.com/ (2026-09-25 검색 확인).

1. 프로젝트 생성 (또는 기존 선택).
2. **OAuth 동의 화면(브랜딩) 설정**: 메뉴 > Google Auth Platform > Branding — 앱 이름·사용자 지원 이메일 입력. User type **External** 선택.
3. **Scope**: `openid`, `email`, `profile` 3개만 ( 셋 다 **non-sensitive**, 추가 검수 불필요 — 출처: https://developers.google.com/workspace/guides/configure-oauth-consent ). 민감·제한 scope를 추가하지 않는 것이 1단계 조건.
4. **테스트 사용자** (Audience > Test users): 초기에는 사용자 본인 Gmail 등록.
5. **클라이언트 생성**: Clients 페이지 > Create client > 유형 **웹 애플리케이션** > **승인된 리디렉션 URI**에 `https://144.24.91.250.sslip.io/auth/google/callback` 추가 (Authorized JavaScript origins는 서버 플로우만 쓰면 불필요 — GIS 버튼 사용 시에만 추가).
6. 발급된 **클라이언트 ID·클라이언트 보안 비밀번호**를 §6 환경변수에 보관.

### 2.3 sslip.io를 리다이렉트 URI로 쓸 수 있는지 (핵심 결론 — 반드시 읽을 것)

**결론: 기술적 등록·테스트 로그인은 가능 (추정 포함), 정식 게시(검수)는 불가에 가까움. 구글 로그인은 테스트 모드로 먼저 붙이고, 실서비스 전에는 직접 구매한 도메인으로 이전해야 함 (PRODUCT_ROADMAP D2와 정합).**

근거 (2026-09-25 확인):

- a) 구글 검증 규칙상 막히는 조건: scheme HTTPS 필수( `http` 불가, localhost만 예외), **raw IP 불가**, Host TLD가 public suffix list 소속이어야 함. 출처: https://developers.google.com/identity/protocols/oauth2/javascript-implicit-flow ("Validation rules"). `https://144.24.91.250.sslip.io/...`는 HTTPS·도메인 형태·TLD(`.io`) 정상이므로 이 규칙에는抵触하지 않음.
- b) PSL 실측: 2026-09-25 스냅샷(`publicsuffix.org` 다운로드 후 grep)에서 **`sslip.io`·`nip.io` 모두 미등재 확인**. 즉 top private domain은 `sslip.io` 자체(소유자: Brian Cunnie, 출처: https://www.whois.com/whois/sslip.io )가 되므로, **사용자는 Search Console로 `sslip.io`의 소유권을 확인할 수 없음** → 브랜드 검수(홈페이지·개인정보처리방침·도메인 확인 요구, 출처: https://developers.google.com/identity/protocols/oauth2/production-readiness/brand-verification )를 통과할 방법이 없음 **(추정 — 검수 정책 해석)**.
- c) 정책상 회색지대: "자신이 소유·사용 허가·라이선스를 받은 도메인의 URI만 사용" (출처: https://developers.google.com/identity/protocols/oauth2/policies ). sslip.io는 무료 공용 DNS 서비스이므로 엄밀한 '소유'가 아님 **(추정 — 테스트 용도 허용 여부는 구글 재량)**.
- d) 테스트 모드 완화: User type External + Publishing status **Testing**인 앱은 테스트 사용자 최대 **100명**까지 허용. 단, **기본 신원 scope(`openid`, `email`, `profile`)만 요청하는 앱은 allowlist에 없는 사용자도 접근 가능**이라는 예외가 명시돼 있음. 출처: https://developers.google.com/identity/protocols/oauth2/production-readiness/overview . 본 서비스가 요청하는 scope가 정확히 이 3개이므로 테스트 모드 제약이 가장 약한 조합임.
- e) 테스트 모드 refresh token은 7일 만료이나, 기본 scope만 쓰면 예외 (출처: https://developers.google.com/identity/protocols/oauth2 ). 1단계는 서버 세션만 쓰고 refresh token을 저장하지 않으므로 무관.
- f) 미검증 앱 경고 화면(Unverified app screen)이 표시될 수 있음 **(추정)**. 테스트 인원에게는 사전 안내 필요.

**대안 (우선순위 순):**
1. (당장) sslip.io + 테스트 모드로 구현·검증 진행 (WP 1-2).
2. (1단계 완료 전) 직접 도메인 구매 후 클라이언트 URI 교체 — 같은 Cloud 프로젝트의 클라이언트에 URI 추가/교체만으로 가능 **(추정)**. PRODUCT_ROADMAP D2·5단계(프로젝트별 주소·와일드카드 인증서)와 묶어 결정.

### 2.4 scope·id_token 검증

- scope: `openid email profile` (openid가 맨 앞에 오도록 — 출처: https://developers.google.com/identity/openid-connect/openid-connect ). 셋 다 non-sensitive → scope 검수 불필요, 브랜드 검수만 해당(테스트 모드에서는 생략 가능).
- 검증 방법 (권장 순서):
  1. `google-auth` 라이브러리의 `id_token.verify_oauth2_token(token, request, audience={GOOGLE_CLIENT_ID})` 사용. 서명(JWKS)·`aud`(클라이언트 ID 일치)·`iss`(`https://accounts.google.com`)·`exp`를 검증하고 `sub`·`email`·`name`·`picture`를 반환. 출처: https://googleapis.dev/python/google-auth/latest/reference/google.oauth2.id_token.html , https://developers.google.com/identity/gsi/web/guides/verify-google-id-token
  2. `nonce` 클레임이 요청 시 보낸 값과 일치하는지 확인 (authlib 사용 시 자동 처리 — 아래 §4).
  3. 디버깅 전용 `tokeninfo` 엔드포인트는 운영 검증용으로 쓰지 않음 (구글 권장).
- 식별자: `sub` (구글 계정 고유 ID, 재사용·변경 없음 — `users.provider_user_id`에 저장). **email을 식별자로 쓰지 않음** (변경 가능).

---

## 3. 공통 보안 요구 (WP 1-2 구현 입력)

| 항목 | 요구 (LANDING_AUTH_DB_UPLOAD_PLAN §2.2·§8 계승 + 구체화) |
|---|---|
| `state` (CSRF) | `secrets.token_urlsafe(32)` 이상 난수 → 서버 세션(또는 `oauth_states` 테이블, TTL 10분)에 저장 → 콜백에서 `secrets.compare_digest` 비교. 불일치·재사용·만료 시 로그인 중단. `redirect_uri`는 상수(동적 조립 금지). |
| PKCE | **사용 권장**. S256 (`code_challenge`/`code_verifier`). 서버(컨피덴셜) 클라이언트 + client_secret과 병행 사용 — OAuth 2.1 방향과 정합. authlib는 PKCE 지원 (추정 — WP 1-2에서 실측 확인). 카카오도 `code_challenge` 파라미터 지원 (추정 — 미지원 시 state만으로 진행, 콘솔·문서에서 실측 후 본 문서 갱신). |
| `nonce` (구글) | 인가 요청마다 난수 생성 → 세션 저장 → id_token의 `nonce` 클레임과 대조 (재생 공격 방지). authlib OIDC 사용 시 자동 처리 (추정). |
| 세션 쿠키 | `HttpOnly; Secure; SameSite=Lax; Path=/` (+ 만료). `Secure`는 HTTPS 배포 후 실측. 값은 세션 ID만 (서명 쿠키 또는 PG `sessions` 테이블 — LANDING_AUTH_DB_UPLOAD_PLAN §3.1). `SESSION_SECRET`은 32바이트 이상 난수. |
| 공급자 토큰 저장 | **권장: 저장 안 함**. 로그인 완료 후 access/refresh token 파기, `provider`·`provider_user_id`(카카오 id/구글 sub)·`nickname`·`email`만 DB(`users`) + 서버 세션에 보관. refresh token이 나중에 필요해지면(알림 등) 별도 WP에서 암호화(Fernet 등) 저장 설계. |
| 로그아웃 | `POST /logout` → 서버 세션 행 삭제 + 쿠키 무효화. (선택) 카카오 토큰 무효화 API 호출. 카카오계정 연동 로그아웃은 별도 URI 필요 — 1단계 범위 밖. |
| 실패 처리 | state 불일치·토큰 교환 실패·검증 실패는 모두 랜딩 로그인 화면으로 복귀 + 서버 로그 기록 (키·토큰·PII 미기록). 레이트리밋(로그인·콜백)은 WP 1-2/6단계에서 미들웨어로. |

---

## 4. FastAPI 구현 라이브러리 비교 (의존성 최소화 관점)

버전 확인일: 2026-09-25 (PyPI·공식 문서 검색).

| 후보 | 버전 | 평가 |
|---|---|---|
| **authlib (권장)** | **1.8.0** (2026-08-30, 출처: https://pypi.org/project/Authlib/ ) | Starlette/FastAPI OAuth 클라이언트 내장 (`authlib.integrations.starlette_client`, 출처: https://docs.authlib.org/en/v1.6.11/client/fastapi.html ). 카카오(plain OAuth2)·구글(OIDC discovery·nonce·id_token 검증)을 같은 인터페이스로 처리. Python 3.10+ 필요. 의존: `cryptography`, `httpx`/`requests` 등 (추정 — `pip show` 실측 요망). NLNet 지원으로 유지보수 활발 (출처: https://blog.authlib.org/2026/authlib-release-version-1-7-and-get-support-from-the-nlnet-foundation ). 단점: SessionMiddleware가 `itsdangerous`를 요구 (Starlette 기본 종속이므로 추가 부담은 사실상 없음 — 추정). |
| 최소 조합 (대안): `httpx` + `google-auth` + `itsdangerous` (+ `PyJWT`) | `google-auth` 2.58.0 문서 확인 (2026-09-19, 출처: https://googleapis.dev/python/google-auth/latest/_modules/google/oauth2/id_token.html ) | 코드 교환·검증을 직접 작성. 의존성은 authlib보다 작아질 수 있으나, state·PKCE·nonce·discovery·JWKS 캐시를 전부 손으로 구현 → 버그 표면이 넓음. 카카오/구글 분기 중복 발생. **1단계에는 비권장** (보안 타협 금지 원칙과 충돌). |
| `fastapi-users` 등 풀스택 인증 프레임워크 | 미조사 | 범위 과잉 (DB 어댑터·비밀번호 체계 포함). 비밀번호를 저장하지 않는 본 설계와 불일치 → 채택 안 함. |

- 권장: **authlib 1.8.0 pinned (`authlib>=1.8,<2`)** + Starlette `SessionMiddleware` (OAuth state 임시 보관용. 단, state는 §3 요구대로 서버 측 검증이 원칙이므로 세션 저장소 선택과 함께 WP 1-2에서 확정).
- 주의: ENVIRONMENT.md §3-5에서 `httpx==0.27.2` 핀으로 의존성 충돌을 해결한 전례 있음. authlib 추가 시 `httpx`·`openai`·`cryptography` 버전 충돌 여부를 로컬에서 실측 필요 (WP 1-2 선행 조건).
- 카카오 OIDC(OpenID Connect 활성화)는 1단계에 불필요 (access token + `/v2/user/me`로 충분). 활성화하면 id_token도 받을 수 있으나 동의화면·검증 경로가 늘어나므로 보류.

---

## 5. 사용자가 직접 해야 하는 콘솔 작업 체크리스트 (WP 1-6 입력)

### 5.1 카카오 (카카오 개발자 콘솔 — https://developers.kakao.com/console/app > `agt001`)

- [ ] K1. 내 애플리케이션 > `agt001` 선택 (ID 1585973 맞는지 확인).
- [ ] K2. [제품 설정] > [카카오 로그인] > [사용 설정] > 상태 **ON** (OFF면 KOE004).
- [ ] K3. 같은 메뉴에서 **Redirect URI 등록**: `https://144.24.91.250.sslip.io/auth/kakao/callback` 추가 (정확히 일치, 末尾 슬래시 없음).
- [ ] K4. [카카오 로그인] > [동의항목]: **닉네임 필수 동의** 설정 (프로필 사진은 선택 또는 미사용 — 1단계 최소). 이메일은 설정하지 않음 (필요해지면 비즈앱 전환 후 별도 WP).
- [ ] K5. [앱] > [플랫폼 키] > **REST API 키 값 복사** → §6 `KAKAO_REST_API_KEY`에 보관 (타인과 공유·커밋 금지).
- [ ] K6. 같은 화면 [클라이언트 시크릿] 상태 확인 → 활성화돼 있으면 **시크릿 값 복사** → `KAKAO_CLIENT_SECRET`에 보관. 비활성화면 그대로 두고 구현 담당(Claude)에게 통보 (토큰 요청 분기가 달라짐).
- [ ] K7. (권장) 웹 도메인에 `https://144.24.91.250.sslip.io` 추가 등록 (기존 `http://...:8643` 2곳은 유지).
- [ ] K8. HTTPS 배포 후 본인이 직접 로그인 1회 테스트 (WP 1-2 완료 후).

### 5.2 구글 (Google Cloud Console — https://console.cloud.google.com/)

- [ ] G1. 프로젝트 생성 (이름 예: `agt001`) 또는 기존 선택.
- [ ] G2. Google Auth Platform > **Branding**: 앱 이름·사용자 지원 이메일 입력, User type **External** 저장.
- [ ] G3. **Scopes(데이터 액세스)**: `openid`, `email`, `profile` 3개만 추가 (그 외 추가 금지).
- [ ] G4. **Audience > Test users**: 본인 Gmail 포함 테스트 계정 등록 (최대 100명).
- [ ] G5. **Clients > Create client** > 유형 **웹 애플리케이션** > 이름 `agt001-web` > **승인된 리디렉션 URI**에 `https://144.24.91.250.sslip.io/auth/google/callback` 추가 후 생성.
- [ ] G6. 발급된 **클라이언트 ID·클라이언트 보안 비밀번호 복사** → §6 `GOOGLE_CLIENT_ID`·`GOOGLE_CLIENT_SECRET`에 보관.
- [ ] G7. Publishing status를 **Testing 유지** (게시/검수는 직접 도메인 구매 후 — §2.3).
- [ ] G8. HTTPS 배포 후 본인 계정으로 로그인 1회 테스트 + 미검증 경고 화면 문구 확인 (WP 1-2 완료 후).

---

## 6. 환경변수 제안 + `.env.example` 추가 내용 (값 없이)

`.env` 읽기 금지·커밋 금지 원칙 유지 (LANDING_AUTH_DB_UPLOAD_PLAN §2.2). 아래는 WP 1-2 구현 담당이 `.env.example`에 추가할 스니펫 (값 없음):

```ini
# --- OAuth (Kakao + Google, WP 1-0a/1-6) ---
# 카카오: 개발자 콘솔 > agt001 > 플랫폼 키에서 복사 (체크리스트 K5/K6)
KAKAO_REST_API_KEY=
# 클라이언트 시크릿이 비활성화 상태면 비워 둠 (K6 결과에 따름)
KAKAO_CLIENT_SECRET=
# 고정값. 콘솔 등록 URI와 정확히 일치해야 함 (KOE006 주의)
KAKAO_REDIRECT_URI=https://144.24.91.250.sslip.io/auth/kakao/callback
# 구글: Cloud Console > Clients > agt001-web에서 복사 (체크리스트 G6)
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
# 고정값. 콘솔 등록 URI와 정확히 일치해야 함 (scheme·대소문자·末尾 슬래시까지)
GOOGLE_REDIRECT_URI=https://144.24.91.250.sslip.io/auth/google/callback
# 전 배포 공통
APP_BASE_URL=https://144.24.91.250.sslip.io
# 세션 서명용. 32바이트 이상 난수 (예: python -c "import secrets; print(secrets.token_hex(32))")
SESSION_SECRET=
```

- 구현 참고 (WP 1-2 입력): `redirect_uri`는 요청 시 조립하지 않고 위 상수 사용. `SESSION_SECRET`은 OAuth state 서명 + Starlette SessionMiddleware에 공용 (분리 필요 시 WP 1-2에서 결정).
- `.env.example` 파일 자체의 수정은 WP 1-2 소유 (본 WP는 문서만 작성 — DELIVERY_PIPELINE 파일 소유권 규칙).

---

## 부록. 출처 목록·불확실 목록

**출처 (2026-09-25 검색 확인):**
- 카카오 REST API 로그인: https://developers.kakao.com/docs/latest/en/kakaologin/rest-api
- 카카오 설정 전제조건(사용 설정·Redirect URI·Client Secret·동의항목): https://developers.kakao.com/docs/ko/kakaologin/prerequisite
- 카카오 토큰 수명: https://developers.kakao.com/docs/en/kakaologin/common
- 구글 OIDC 개요·scope 순서: https://developers.google.com/identity/openid-connect/openid-connect
- 구글 OIDC 레퍼런스(엔드포인트·nonce·redirect exact match): https://developers.google.com/identity/openid-connect/reference
- 구글 클라이언트 생성 절차: https://developers.google.com/identity/gsi/web/guides/get-google-api-clientid
- 구글 OAuth 정책(도메인 소유·HTTPS): https://developers.google.com/identity/protocols/oauth2/policies
- 구글 리다이렉트 검증 규칙(HTTPS·raw IP 불가·PSL): https://developers.google.com/identity/protocols/oauth2/javascript-implicit-flow
- 구글 테스트 모드 100명 + 기본 scope 예외: https://developers.google.com/identity/protocols/oauth2/production-readiness/overview
- 구글 브랜드 검수(도메인 확인): https://developers.google.com/identity/protocols/oauth2/production-readiness/brand-verification
- 구글 id_token 검증: https://developers.google.com/identity/gsi/web/guides/verify-google-id-token , https://googleapis.dev/python/google-auth/latest/reference/google.oauth2.id_token.html
- Authlib 버전·FastAPI 통합: https://pypi.org/project/Authlib/ , https://docs.authlib.org/en/v1.6.11/client/fastapi.html

**(추정) — WP 1-2 전 실측·확인 필요:**
- 카카오 로그인 ON 여부·Redirect URI 미등록 (콘솔 직접 확인).
- 카카오 이메일 동의항목의 비즈앱 요구 조건 (콘솔 표시가 최종 기준).
- 카카오 기존 앱의 Client Secret 활성화 여부 (K6).
- 카카오 PKCE(`code_challenge`) 지원 여부 (미지원 시 state만으로 진행).
- 구글 미검증 경고 화면 노출 여부·문구 (배포 후 실측).
- sslip.io + 테스트 모드 조합의 실제 동작 (배포 후 실측 — 등록 거절 시 §2.3 대안 2로 즉시 전환).
- authlib 1.8.0의 `httpx==0.27.2`·`openai`·Python 버전과의 충돌 여부 (로컬 실측).
