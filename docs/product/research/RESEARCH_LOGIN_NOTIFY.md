# 로그인·알림 웹 리서치 (W2)

> 작성일: 2026-09-26 / 소유 파일: 본 문서 1개
> 먼저 읽은 것: `app/services/auth.py`, `docs/product/OAUTH_SETUP.md`, `templates/sections/contact--kakao-channel.mustache`, `docs/product/DECISIONS.md` D9·D32
> 규칙: 모든 주장에 출처 URL + 확인 날짜. 공식 문서로 확인 못한 것은 "확인 필요".

## 1) Google OAuth 동의 화면: 테스트 → 프로덕션

| 항목 | 내용 | 출처 (확인 날짜 2026-09-26) |
|---|---|---|
| 비민감 범위만 쓸 때 앱 인증 필요 여부 | `openid`·`email`·`profile`은 비민감. 민감·제한 범위 없으면 범위 검수 불필요. 브랜드 표시(이름·로고)를 하려면 브랜드 인증은 별도로 필요 | https://developers.google.com/workspace/guides/configure-oauth-consent , https://developers.google.com/identity/protocols/oauth2/production-readiness/brand-verification |
| 브랜드 인증 요건 | 앱 이름·지원 이메일·홈페이지·개인정보처리방침이 앱 실체와 일치해야 함. 홈페이지에 기능 설명 + 개인정보처리방침 링크 필수. 개인정보처리방침은 홈페이지와 같은 도메인에 있어야 함 | https://support.google.com/cloud/answer/13464321 , https://developers.google.com/identity/protocols/oauth2/production-readiness/brand-verification |
| 승인된 도메인 요건 | 홈페이지·개인정보처리방침·약관·리다이렉트 URI·JS 출처에 쓰는 모든 도메인의 최상위 개인 도메인(top private domain)을 승인된 도메인에 등록해야 함. 본인 소유가 아닌 도메인은 쓰지 말 것 | https://developers.google.com/identity/protocols/oauth2/production-readiness/policy-compliance |
| 도메인 소유 확인(Search Console) 필요 여부 | 필요. 승인된 도메인 전부를 Search Console로 소유 확인. 프로젝트 소유자·편집자 권한 계정으로 확인해야 함 | https://developers.google.com/identity/protocols/oauth2/production-readiness/brand-verification , https://support.google.com/cloud/answer/13464321 |
| 테스트 모드 제약 | 테스트 사용자 최대 100명. 테스트 사용자 동의는 7일 뒤 만료(리프레시 토큰도 7일 만료). 단, 아래 예외 있음 → 다음 행 | https://support.google.com/cloud/answer/15549945 |
| 핵심 예외(우리 해당) | 요청 범위가 이름·이메일·프로필(`userinfo.email`, `userinfo.profile`, `openid` 계열)의 부분집합이면: 허용 목록에 없어도 누구나 접근 가능, 경고 화면 없음, 7일 만료 없음 | https://support.google.com/cloud/answer/15549945 , https://developers.google.com/identity/protocols/oauth2/production-readiness/overview , https://developers.google.com/identity/protocols/oauth2 |
| 남의 도메인(sslip.io)으로 프로덕션 공개 가능 여부 | 불가에 가까움. 정책이 본인 소유 도메인만 허용하고, `sslip.io` 최상위 개인 도메인은 우리가 Search Console로 소유 확인 불가 → 브랜드 인증 통과 불가 (정책 해석, 확인 필요) | https://developers.google.com/identity/protocols/oauth2/production-readiness/policy-compliance (소유 도메인만 사용) |
| 미검증 앱 경고·100명 상한 | 미검증 경고 화면과 100명 상한은 민감·제한 범위를 요청할 때 적용. 비민감 3개만 쓰면 해당 없음 | https://support.google.com/cloud/answer/7454865 , https://developers.google.com/identity/protocols/oauth2/production-readiness/overview |
| 현재 코드 정합 | `app/services/auth.py`는 `scope=openid email profile`, 리프레시 토큰 미저장. 위 예외 조건과 정확히 일치 | 코드 직접 확인 2026-09-26 |

## 2) 카카오 "나에게 보내기" (메시지 API)

| 항목 | 내용 | 출처 (확인 날짜 2026-09-26) |
|---|---|---|
| API·대상 | `POST https://kapi.kakao.com/v2/api/talk/memo/default/send` (기본 템플릿), `.../talk/memo/send` (사용자 정의). 로그인한 본인의 "나와의 채팅"에만 발송. 남에게 보낼 수 없음 | https://developers.kakao.com/docs/ko/kakaotalk-message/common |
| 필요 동의 항목 | 접근권한 `talk_message` (카카오톡 메시지 전송). 친구에게 보낼 때는 `friends`(친구 목록)도 필요 | https://developers.kakao.com/docs/ko/kakaotalk-message/common |
| 검수 여부 | 나에게 보내기: 검수 없이 제한 없이 발송 가능. 친구에게 보내기: 비즈 앱 전환 + 신청 자격 확인 + 비즈니스 정보 평가 + 추가 기능 신청(평가) 필요 | https://developers.kakao.com/docs/ko/kakaotalk-message/common , https://devtalk.kakao.com/t/api/139246 |
| 비즈 앱 필요 여부 | 나에게 보내기만 쓰면 불필요. 친구 발송·이메일 필수 동의는 비즈 앱 필요 | https://developers.kakao.com/docs/ko/kakaotalk-message/common , https://developers.kakao.com/docs/ko/app-setting/app |
| 발송 한도 | 나에게 보내기: 제한 없음(평가 전후 동일). 친구에게: 평가 전 일 30건, 평가 후 앱 기준 일 30,000건 + 발신자당 100건·수신자당 100건·같은 쌍 20건 | https://developers.kakao.com/docs/ko/kakaotalk-message/common |
| 기본 템플릿 형식 | 피드·리스트·위치·커머스·텍스트 (나에게/친구에게 공통). 사용자 정의 템플릿은 도구에서 구성 후 `template_id` 사용 | https://developers.kakao.com/docs/ko/kakaotalk-message/common |
| 사용자 토큰 필요 여부 | 필요. 본인(사장님) 카카오 로그인 액세스 토큰으로 호출. 리프레시 토큰 보관이 실용상 필수 | https://developers.kakao.com/docs/ko/kakaotalk-message/rest-api |
| 토큰 만료 기간 | REST API 액세스 토큰 6시간, 리프레시 토큰 2개월(만료 1개월 전부터 갱신 가능). 갱신 시 새 리프레시 토큰 발급 + 기존 폐기 | https://developers.kakao.com/docs/ko/kakaologin/common |
| 주의 | 나에게 보내기는 메모 용도라 알림(푸시)이 울리지 않을 수 있음. 알림 용도 적합성은 실측 필요 | https://devtalk.kakao.com/t/api/139246 (확인 필요: 실측) |
| 서버→사용자 자동 발송 | 메시지 API는 사용자 간 소셜용. 서비스가 사용자에게 일방 안내(주문·배송 등)는 알림톡(유료, 딜러사 경유) 용도. D32 "사장님 알림"은 사장님 본인 토큰으로 본인에게 보내는 형태라 가능 | https://developers.kakao.com/docs/ko/kakaotalk-message/common , https://developers.kakao.com/docs/ko/tutorial/message |

## 3) 카카오톡 채널 1:1 채팅 링크

| 항목 | 내용 | 출처 (확인 날짜 2026-09-26) |
|---|---|---|
| 채널 홈 URL | `https://pf.kakao.com/_xxxx` (`_xxxx`가 채널 프로필 ID) | https://developers.kakao.com/docs/ko/kakaotalk-channel/common |
| 1:1 채팅 URL | `https://pf.kakao.com/_xxxx/chat` (채널 홈 뒤에 `/chat`) | https://devtalk.kakao.com/t/url/145564 (관리자센터 표시 예시) |
| 채널 추가 링크 | 채널 홈 URL 자체가 추가 진입점. 또는 JS SDK `addChannel()`·`followChannel()`, 1:1 채팅은 `chat()` | https://developers.kakao.com/docs/ko/kakaotalk-channel/js , https://developers.kakao.com/docs/ko/kakaotalk-channel/common |
| 채널 ID 확인 위치 | 채널 관리자센터 > 채널 > 채널 정보 > 채널 URL에서 확인 | https://developers.kakao.com/docs/ko/kakaotalk-channel/common |
| 채널 없는 사장님 절차 | 카카오톡 채널 관리자센터에서 채널 개설 (확인 필요: 무료 여부·소요 시간은 공식 문서 미확인. 개설 자체는 무료로 알려짐 — 확인 필요) | 확인 필요 |
| 현재 템플릿 정합 | `templates/sections/contact--kakao-channel.mustache`는 `kakao_channel_url` 하나만 받아 1:1 채팅 링크로 연결. 위 URL 형식을 그대로 넣으면 됨 | 코드 직접 확인 2026-09-26 |

## 4) 카카오 로그인 이메일 동의 항목

| 항목 | 내용 | 출처 (확인 날짜 2026-09-26) |
|---|---|---|
| 이메일 항목 ID | `account_email` (카카오계정 대표 이메일). 필수·선택·이용 중 동의로 설정 가능 표기 | https://developers.kakao.com/docs/ko/kakaologin/utilize |
| 필요 조건 | 비즈 앱 (사업자 정보 등록). 개인 개발자 비즈 앱만으로는 개인정보 동의 항목 권한 신청 불가. 테스트 앱은 작업자 한정으로 미리 사용 가능 | https://developers.kakao.com/docs/ko/app-setting/app , https://developers.kakao.com/docs/ko/kakaologin/faq , https://devtalk.kakao.com/t/topic/139725 |
| 평가 | 개인정보 동의 항목 추가 기능 신청 → 영업일 기준 3~5일 평가. 신청 정보·제출 자료 일치, 회원가입 방식과 활용 범위 일치 검토 | https://developers.kakao.com/docs/ko/kakaologin/prerequisite |
| 주의 | 필수 동의로 해도 카카오계정에 이메일이 없으면 빈 값. `email_needs_agreement` 확인 + 수집 후 제공 옵션·추가 동의 요청으로 대응 | https://developers.kakao.com/docs/ko/kakaologin/faq |
| 현재 코드 정합 | `app/services/auth.py`는 이메일 없이 닉네임만으로 가입 가능(`email` NULL 허용). D32 문의 구현에 이메일 불필요 | 코드 직접 확인 2026-09-26 |

## 누구나 구글 로그인 가능 경로

| 단계 | 할 일 | 비고 |
|---|---|---|
| 1 | 동의 화면 사용자 유형 External + 게시 상태 테스트 유지 | 게시(프로덕션 전환) 불필요 |
| 2 | 범위 `openid email profile` 3개만 유지 (추가 금지) | `app/services/auth.py` 현 상태 유지 |
| 3 | 리프레시 토큰 저장 안 함 (서버 세션만) | 현 상태 유지. 7일 만료 예외 해당 |
| 4 | D9 폴백 유지: 초대 외 구글 거부 시 랜딩 복귀 + 카카오 유도 | `docs/product/DECISIONS.md` D9 |
| 5 | 자가 도메인 구매 후: 리다이렉트 URI 교체 + 브랜드 인증 → 게시 | `docs/product/OAUTH_SETUP.md` §2.3 대안 2와 동일 |

## 문의 → 사장님 카톡 구현 절차 (D32 ①)

전제: "나에게 보내기"는 본인에게만 발송. 사장님 본인 토큰으로 사장님 본인에게 보내는 구조.

| 단계 | 할 일 | 필요 데이터 | 출처 |
|---|---|---|---|
| 1 | 카카오 로그인 동의 항목에 `talk_message` 추가 | 동의 항목 설정 | https://developers.kakao.com/docs/ko/kakaotalk-message/common |
| 2 | 사장님이 1회 로그인 (온보딩) | 사장님 카카오 회원번호 | 코드·정책 기반 |
| 3 | 리프레시 토큰 암호화 저장 (신규) | 리프레시 토큰, 갱신 시각 | https://developers.kakao.com/docs/ko/kakaologin/common (2개월·회전) |
| 4 | 문의 접수 시 액세스 토큰 준비 (만료 시 리프레시 토큰으로 갱신) | 저장된 리프레시 토큰 | 상동 |
| 5 | `POST /v2/api/talk/memo/default/send` 호출 (텍스트 또는 피드 기본 템플릿) | 문의 내용, 사이트 주소 | https://developers.kakao.com/docs/ko/kakaotalk-message/rest-api |
| 6 | 실패 시 폴백: 채널 1:1 채팅 링크는 그대로 유지 (손님이 직접 문의) | `kakao_channel_url` | 현 템플릿 유지 |
| 7 | 토큰 무효·연결 해제 시 사장님 재로그인 유도 + 웹훅(연결 해제) 설정 권장 | 연결 해제 웹훅 | https://developers.kakao.com/docs/ko/kakaologin/common |

저장해야 할 토큰: 사장님 리프레시 토큰 1개(암호화) + 갱신 시각. 일반 방문자 토큰은 저장하지 않음(현 UQ-1 유지). 액세스 토큰(6시간)은 메모리에서만 사용.

주의: 나에게 보내기는 메모 용도라 푸시 알림이 안 울릴 수 있음 — 실측 후, 필요하면 나에게 보내기 + 채널 채팅 링크 병행 (확인 필요).

## 우리 프로젝트에 대한 추천

| 무엇을 | 왜 | 바꿀 파일/문서 |
|---|---|---|
| 구글 범위 3개 고정 + 테스트 모드 유지 | 누구나 로그인 예외 조건 유지, 검수·도메인 문제 회피 | `app/services/auth.py` (현 유지), `docs/product/OAUTH_SETUP.md` §2.3 |
| D9 폴백 문구 유지 | 테스트 모드 경고 대비 | 로그인 화면 파일 (후속 작업에서 지정) |
| 자가 도메인 구매를 브랜드 인증 선행 조건으로 기록 | sslip.io로 브랜드 인증 불가 | `docs/product/DECISIONS.md` D2 후속 행 |
| 문의 저장 시 D32로 UQ-4 변경 반영 확인 | 문의 저장(30일 등 보관) 정책 필요 | `docs/product/DECISIONS.md` D32, DB 설계 문서 |
| 사장님 리프레시 토큰 암호화 보관 설계 | 나에게 보내기 발송에 필수. 현 UQ-1(미저장)과 충돌하므로 사장님 토큰만 예외로 명시 | DB 설계 문서, `app/services/auth.py` (후속 작업) |
| `talk_message` 동의는 사장님 온보딩에서만 요청 | 방문자에게 불필요한 동의 노출 방지 | 로그인 플로우 문서 (후속 작업) |
| 채널 1:1 채팅 링크(`/_xxxx/chat`)를 문의 섹션 기본값 구조로 유지 | 토큰 없이 동작하는 문의 경로 | `templates/sections/contact--kakao-channel.mustache` (현 유지) |
| 이메일 동의(비즈 앱·평가)는 보류 | 문의 구현에 불필요, 사업자 등록 필요 | `docs/product/OAUTH_SETUP.md` §1.2 (현 권장 유지) |
| 나에게 보내기 푸시 울림 실측 | 메모 용도라 알림 보장 없음 | 후속 작업 검증 항목으로 기록 |
