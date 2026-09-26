# 개인정보 초안 작성 근거 · 법률 검토 필요 항목 (PRIVACY_NOTES)

> WP 1-0g. 성격: 초안 근거 메모. 법률 자문 아님. 공개용 문서가 아님.
> 사실은 아래 출처 문서에 있는 것만 사용. 모르는 것은 "확인 필요".

## 1. 초안 작성 근거 (문서 → 반영 위치)

| # | 출처 문서 | 값 | 반영 위치 |
|---|---|---|---|
| 1 | DECISIONS D14 (연락처 수집 안 함, 로그인이 곧 가입) | 연락처 별도 수집 없음 | privacy.html §1·§2, terms.html 제2조 |
| 2 | DECISIONS D9 (카카오·구글 둘 다 공개, 구글 테스트 모드) | 구글은 초대된 분만 가능 | privacy.html §1, terms.html 제2조 |
| 3 | DECISIONS D13 (베타 무료, AI 견적은 참고값) | 무료, 결제·환불 고지 불필요 | terms.html 제3조 |
| 4 | DECISIONS D16 + funnel.py (익명 기록, 90일 보관, IP/UA·이름·연락처·대화 미저장) | funnel_events 90일 자동 purge, 저장 항목 event/visitor_id/session_id/source/campaign/template_id | privacy.html §1·§2·§3 |
| 5 | DECISIONS D23·D24·D27 (자리 표시 필수, 사실은 방장 확인, 직접 편집) | 전화·주소·가격·영업시간은 사장님이 말한 것만 저장, 지어내기 금지 | privacy.html §1, terms.html 제4조 |
| 6 | OAUTH_SETUP §1.2·§1.4·§2 (동의항목·scope) | 카카오: 닉네임 필수, 사진 선택 가능, 이메일 미수집. 구글 scope openid email profile. 식별자는 sub/회원번호, email 아님. 공급자 토큰 저장 안 함 | privacy.html §1·§4 |
| 7 | OAUTH_SETUP §3 (세션 쿠키 ID만, state TTL 10분) | state 10분, 쿠키 HttpOnly·Secure·SameSite=Lax | privacy.html §3·§6 |
| 8 | USER_DB_PLAN §A-2 (개인정보 표 12행, 최소 수집·암호화·탈퇴·보관) | 이메일·프로필사진·전화·주소 등 개인정보 해당, 토큰은 해시만, 탈퇴 유예 30일, PRD·명세 익명 보관, 로그 30일 제안 | privacy.html §1·§3·§7 |
| 9 | ROOM_POLICY §4.2 T1~T7 (투표 24h·견적 7일·30일 닫힘·삭제 30일 뒤 영구 삭제·초대 7일·10명 상한) | 보관·삭제 타이머 값 그대로 | privacy.html §3, terms.html 제6조 |
| 10 | ROOM_POLICY §1·§6 + USER_DB_PLAN §A-1 (member_token 해시, 초대 해시, rooms 확장 열) | 비밀은 해시만, 응답에 공개 식별자만 | privacy.html §7 |
| 11 | COST_MONITORING (리전 ap-chuncheon-1) | 서버 위치: OCI 춘천 리전 | privacy.html §4 |
| 12 | 서비스 전제 (NVIDIA NIM API — 해외 사업자, 대화 내용 전송) | 국외 이전 고지 필요 | privacy.html §4 (확인 필요 표시) |

## 2. 법률 검토가 필요한 항목

| # | 항목 | 왜 필요한지 (조항 관점) | 상태 | 출처 URL |
|---|---|---|---|---|
| L1 | 개인정보처리방침 필수 기재 완성도 (수집 항목·목적·보관·파기·권리·책임자) | 개인정보보호법 제30조(처리방침 수립·공개), 정보통신망법 제27조의2(개인정보 처리방침 공개 — 확인 필요) | 초안 작성, 변호사 검토 전 | https://www.law.go.kr (개인정보 보호법), https://www.pipc.go.kr (개인정보보호위원회) |
| L2 | 국외 이전 고지 (NVIDIA NIM + OpenCode Zen 경유 디자인 단계 유료 모델 비교(D39): 이전 국가·항목·목적·보관 기간) | 개인정보보호법 제28조의8(국외 이전 시 고지·동의 — 확인 필요). NIM: 이전받는 곳 국가·보관 기간 미확인. Zen 경유 시: 미국 호스팅, 제공사 무보관·학습 안 함 표기(https://opencode.ai/docs/zen/ §Privacy)이나, 보내는 항목은 업종·분위기·상품 이름·사진만(전화·주소 제외, D39). 확인 필요: Zen 상업 이용 약관, 이전 국가·보관 기간 | 확인 필요 (업체 문서 확인) | https://www.pipc.go.kr, https://www.law.go.kr, https://opencode.ai/docs/zen/ |
| L3 | 구글 로그인 해외 이전 (Google LLC 인증 처리) | 위 L2와 동일. 구글 동의 화면 + 방침 링크로 충분한지 확인 | 확인 필요 | https://developers.google.com/identity/protocols/oauth2/policies, https://developers.google.com/identity/protocols/oauth2/production-readiness/brand-verification |
| L4 | 처리 위탁 고지 (OCI 보관 위탁 해당 여부) | 개인정보보호법 제26조(업무위탁 시 고지 — 확인 필요). 클라우드 인프라가 수탁자에 해당하는지 판단 필요 | 확인 필요 | https://www.law.go.kr, https://docs.oracle.com/en-us/iaas/Content/Block/Concepts/overview.htm |
| L5 | 만 14세 미만 아동 처리 | 개인정보보호법 제22조(만 14세 미만 법정대리인 동의 — 확인 필요). 소상공인 대상이나 방치 금지 (USER_DB_PLAN §A-2 조치 #6) | 확인 필요 (연령 제한 방식) | https://www.law.go.kr, https://www.pipc.go.kr |
| L6 | 안전성 확보조치·접속기록 보관 | 개인정보보호법 제29조(안전성 확보조치), 접속기록 1년 이상 보관 규정 존재 여부 (USER_DB_PLAN §A-2 조치 #4) | 확인 필요 (보관 기간 확정) | https://www.law.go.kr, https://www.pipc.go.kr |
| L7 | 토큰 해시 방식 (SHA-256 + 재발급 대응의 적절성) | OWASP 비밀번호 저장 지침 관점. 무작위 토큰이라 bcrypt/argon2 불필요하다는 설계의 타당성 (USER_DB_PLAN §A-2) | 확인 필요 (보안 검토) | https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html |
| L8 | 서버 로그(IP) 30일·디스크 암호화(OCI 기본 의존) | 로그 IP는 개인정보 해당 가능, 보존 기간·순환 근거. OCI 부트 볼륨 기본 암호화 의존의 적절성 (USER_DB_PLAN §A-2) | 확인 필요 | https://www.pipc.go.kr, https://docs.oracle.com/en-us/iaas/Content/Block/Concepts/overview.htm |
| L9 | 탈퇴 익명화 범위 (닉네임→"탈퇴한 회원", 첨부 원본 파일명 삭제 여부 — UQ-3 미결정) | 삭제·익명화 범위가 권리(삭제권) 충족에 충분한지 | 확인 필요 (UQ-3 결정 + 법률 검토) | https://www.law.go.kr, https://www.pipc.go.kr |
| L10 | 생성 사이트 방문자 데이터 (베타: 폼 백엔드 없음 — 전화·카톡 채널·외부 링크만) | 베타 뒤 폼 도입 시 방문자 연락처 보관·파기·열람·삭제 의무 발생 (USER_DB_PLAN §B). 베타 범위 문구로 충분한지 | 베타 미포함 명시, 도입 시 재검토 | https://www.pipc.go.kr |
| L11 | 이용약관: 생성물 권리 귀속·면책 한계·준거법·관할 | 약관 규제법·민법 관점. 베타 무료라도 면책이 유효한 범위, 생성물 권리 귀속, 관할법원 기재 | 확인 필요 (변호사 확정) | https://www.law.go.kr |
| L12 | 유출 통지·신고 절차 문서 | 개인정보보호법 제34조(유출 통지·신고 — 확인 필요). 1쪽 문서 별도 작성 권장 (USER_DB_PLAN §A-2 조치 #5) | 미작성 | https://www.pipc.go.kr |
| L13 | 동의 획득 방식 (카카오 동의항목·구글 scope 화면 + 방침 링크) | 콘솔 설정(K4·G3)과 함께 확인 (USER_DB_PLAN §A-2 조치 #2) | 콘솔 확인 필요 | https://developers.kakao.com/docs/ko/kakaologin/prerequisite, https://developers.google.com/identity/openid-connect/openid-connect |
| L14 | 구글 브랜드 검수 (sslip.io 도메인 소유 확인 불가 → 정식 게시 불가 추정) | 검수 통과 전 테스트 모드 운영의 약관·표시 의무 (OAUTH_SETUP §2.3) | 확인 필요 (도메인 구매 후 재검토) | https://developers.google.com/identity/protocols/oauth2/production-readiness/overview |

## 3. 모르는 것 처리 원칙

- 본 초안에서 문서에 없는 값(책임자 이름·연락처·시행일·관할법원·NIM 이전 국가 등)은 [자리표시자] 또는 "확인 필요"로 표기하고 임의로 창작하지 않았다.
- 실제 이름·전화·이메일을 기재하지 않았다.
