# BACKLOG (2026-09-26 기준, 마감 2026-09-28)

> 범위: 해커톤 제출까지 남은 일만. 읽은 문서: README, DELIVERY_PIPELINE §5, DECISIONS, USER_DB_PLAN, REQUIREMENTS_RAG_REVIEW, ROOM_POLICY, INTAKE_GATE_DESIGN §7, DESIGN_PIPELINE_PLAN, VOICE_INPUT_PLAN, reviews 7종, git log 40.
> 끝난 것: C1 엔진 16건, C2 입구 게이트, C4 로그인 코드, C5 계정별 프로젝트, C6 문의 받기, O4 문의 부품, T1 듣기 버튼 뼈대, R1 렌더러 모듈, NIM super-ultra-lightning. 진행 중: C7 시안 3안 연결.

## 1. 마감까지 반드시 (제출에 필요)

| # | 할 일 | 왜(근거 문서) | 담당(Claude / OpenCode / 사용자) | 의존 | 예상 시간 |
|---|---|---|---|---|---|
| M-1 | ✅ 완료(bf7a399) C7 시안 3안 연결: 고르기 페이지·v1~v3·채팅 "N안" 선택 | DELIVERY C7, DESIGN P-4/P-5 | Claude | R1 | 4시간 |
| M-2 | ✅ 완료 가짜 RAG 문구 교체 (기능 사례집 42 + 프로필 9, 기준 0.745 실측) | RAG_REVIEW §2.3, INTAKE §4 | Claude | C2 | 1시간 |
| M-3 | ✅ 완료 D25 규칙 견적 1줄로 교체 (AI 3안 제거). 운영 실측: 첼로에 150만~650만원·알림톡을 제안, 베타 무료(D13)와 모순 | DECISIONS D25, FIXES B-10 | Claude | 없음 | 2시간 |
| M-4 | S-1 미리보기 별도 호스트 분리 | DESIGN §13.5 S-1, DELIVERY §5.2 | Claude | 없음 | 3시간 |
| M-5 | RENDERER 계약 5건 확정 (토큰형, image, alt, intro, focus) | RENDERER_NOTES §2·§3 | Claude | R1 | 1시간 |
| M-6 | ✅ 완료 O5 시안 3안 선택 카드 연결 | DELIVERY O5, DESIGN P-5 | OpenCode | M-1 | 3시간 |
| M-7 | ✅ 완료 T1 듣기 버튼 (운영 배포, 실측 2.25초, 자동재생 없음) | VOICE 부록, DELIVERY O6 | OpenCode | Claude 계약 | 2시간 |
| M-8 | OAuth 키 서버 등록 (scripts/set_oauth_secrets.sh 실행) | DECISIONS D10, DELIVERY 1-6 | 사용자 | 없음 | 30분 |
| M-9 | 구글 동의 화면 마지막 단계 확인 | README, OAUTH_SETUP | 사용자 | 없음 | 30분 |
| M-10 | 개인정보처리방침·약관 공개 (static 초안 게시) | USER_DB_PLAN §A-2, DECISIONS D14 | Claude | 사용자 확인 | 2시간 |
| M-11 | ✅ 구현 T1 투표 24시간·T2 견적 7일·T4 30일 닫기·D8 10명 (읽기·쓰기 때 판정, 경고 알림은 아직) | ROOM_POLICY §4.2 | Claude | 없음 | 1시간, 확인 필요 |
| M-12 | 저장소 공개 전환 (마지막에) | 지시문 마감 항목 | 사용자 | 전부 | 10분 |

## 2. 마감 전 하면 좋음

| # | 할 일 | 왜(근거 문서) | 담당(Claude / OpenCode / 사용자) | 의존 | 예상 시간 |
|---|---|---|---|---|---|
| S-1 | B-6 승인·투표 단어 정규화 완화 | FIXES §2-④, ROOM_POLICY | Claude | 없음 | 1시간 |
| S-2 | B-9 방장 승계 (첫 입장자 자동 승계) | FIXES B-9, ROOM_POLICY §2 | Claude | 없음 | 2시간 |
| S-3 | B-15 템플릿 시작 배선 (template_id 연결) | FIXES B-15, DECISIONS D26 | Claude | 없음 | 1시간 |
| S-4 | B-4 잡담 2턴 넛지 문구 추가 | FIXES B-4 잔여, INTAKE §5 | Claude | 없음 | 1시간 |
| S-5 | S-2 sandbox iframe 자동 검사 | DESIGN §13.5 S-2 | Claude | 없음 | 1시간 |
| S-6 | S-5 게시 전 검사 (외부 스크립트·폼 차단) | DESIGN §13.5 S-5 | Claude | 없음 | 2시간 |
| S-7 | C3 평가 1회 실행 (추출 60개·시나리오 36개) | DELIVERY C3, DECISIONS D28 | Claude | O1 | 2시간 |
| S-8 | O1 실제 대화 평가 도구 마무리 | DELIVERY O1 | OpenCode | chat_turns | 3시간 |
| S-9 | D7·D8 타이머·인원 상한 설정값 분리 확인 | ROOM_POLICY §4·§8, DECISIONS D7·D8 | Claude | 없음 | 30분 |
| S-10 | 카카오 채널·전화 버튼 대체안 문구 손질 | INTAKE §4, DECISIONS D32 | OpenCode | 없음 | 1시간 |

## 3. 베타 뒤

| # | 할 일 | 왜(근거 문서) | 담당(Claude / OpenCode / 사용자) | 의존 | 예상 시간 |
|---|---|---|---|---|---|
| L-1 | R-1~R-4 구조 기억 (판·결정·요약·라우터) | RAG_REVIEW §7.3 R-1~R-4 | Claude | P-1 | 반나절씩 |
| L-2 | R-5 벡터 도입 (pgvector+trgm, R-0 실측 뒤) | RAG_REVIEW Q1·Q2, §7.3 | Claude | L-1 | 반나절씩 |
| L-3 | U-6 백업 외부화 E-1 (암호화 업로드) | USER_DB_PLAN U-6, DELIVERY §5.2 | Claude | 사용자 승인 | 반나절 2개 |
| L-4 | U-7 복구 연습 1회·U-8 시드·모니터 | USER_DB_PLAN U-7·U-8 | OpenCode | L-3 | 반나절 |
| L-5 | U-9 탈퇴 익명화·유출 대응 1쪽 | USER_DB_PLAN U-9, §A-2 | Claude | UQ-3 | 반나절 2개 |
| L-6 | R-2 초대 링크·R-3 기록·R-4 점검·R-5 푸시 | ROOM_POLICY §7 R-2~R-5 | Claude | R-1 | 반나절씩 |
| L-7 | P-6 탭해서 말하기·P-7 확정·P-8 제작 연결 | DESIGN §13.6 P-6~P-8 | Claude | M-1 | 반나절씩 |
| L-8 | P-9 참고 사이트·P-10 직접 편집·P-SSE 전환 | DESIGN §13.6, DECISIONS D27 | Claude | M-1 | 반나절씩 |
| L-9 | 0-3 작업 큐·0-4b 스테이징·0-5b 비용 점검 | DELIVERY 0-3·0-4b·0-5b | Claude | 없음 | 반나절씩 |
| L-10 | 0-6c 결정 요청 텔레그램·전화 (Twilio 뒤) | DELIVERY 0-6c, DECISIONS D11 | Claude | 사용자 가입 | 반나절 |
| L-11 | 공용 기능 ②예약 ③회원 ④결제 (수요 뒤) | DECISIONS D31·D32 | Claude | C6 | 반나절씩, 확인 필요 |
| L-12 | V-2b 인앱 안내·V-3 서버 STT (상한 뒤) | VOICE §7.1 V-2b·V-3 | OpenCode | 실측 | 반나절씩 |
| L-13 | S-7 전용 도메인·D2 재검토 | DESIGN §13.5 S-7, DECISIONS D2 | 사용자 | 없음 | 확인 필요 |

## 4. 사용자 결정 대기

| # | 질문 | 추천 답 |
|---|---|---|
| Q-1 | UQ-1 토큰 비저장 유지? | 유지, 필요시 암호화 별도 |
| Q-2 | UQ-2 users 분리형 확정? | 분리형 (구현됨, 추인만) |
| Q-3 | UQ-3 탈퇴 익명화 범위? | 닉네임 익명화, 원본명 삭제 |
| Q-4 | UQ-4 문의 저장 보관 기간? | D32로 포함 전환, 30일·1년 중 택일, 확인 필요 |
| Q-5 | UQ-5 백업 버킷 한도 초과 감수? | 감수 E-1 + 알림 |
| Q-6 | UQ-6 방침 AI 초안 공개? | AI 초안 + 사용자 확인 후 공개 |
| Q-7 | RAG Q1 벡터 미루기·Q2 모델 고정·Q3 마스킹·Q4 백업 명시·Q5 요약 주기? | 미루기·고정·마스킹·명시·50턴, 원문대로 |
| Q-8 | G1 범위·G2 분류·G3 범위밖·G4 창구·G5 문의폼·G6 예산? | §6 초안대로, G5는 포함으로 변경 |
| Q-9 | VOICE Q1 키보드·Q2 고지·Q3 상한·Q4 TTS·Q5 인앱? | 예·고지후·5달러안·보류·키보드 기본 |
| Q-10 | ✅ 결정·구현(D34) 요약 직전 리뷰어 에이전트 | 원문 인용 확인 후에만 채움, 어긋남은 묻기 |
| Q-11 | 대화 밖 조사 에이전트 도입? | 도입 (사례집 후보만), 확인 필요 |
| Q-12 | 이전 프로젝트 불러오기 (동의 후)? | 동의 후 도입, 확인 필요 |
| Q-13 | S-7 전용 도메인 구매? | 베타 뒤, D2 재검토 |
| Q-14 | 1-6 카카오·구글 콘솔·Twilio 가입? | 콘솔 먼저, 전화는 베타 뒤 |

## 5. 모순

| # | 서로 다른 말 | 판정 |
|---|---|---|
| X-1 | UQ-4 문의폼 베타 제외 vs C6 구현됨·D32 포함 변경 | D32 변경이 최신, UQ-4 갱신 필요 |
| X-2 | VOICE V-T TTS 보류 vs T1·O6 듣기 버튼 진행 중 | 부록 변경이 최신, 보류 문구 갱신 필요 |
| X-3 | S-1 로그인 전 필수 vs C4 코드 먼저 배포됨 | 순서 어김, M-4로 메움, 확인 필요 |
| X-4 | RAG 임계값 0.70·가짜 3개 vs 운영 문구 노출 | 실측 무효, M-2로 교체 |
| X-5 | D2 도메인 보류 vs S-7 전용 도메인 필수·구글 테스트 모드 제한 | 베타 뒤 재검토, 확인 필요 |
| X-6 | D20 8질문 vs INTAKE 웹서비스 12·+4 연장 | 가게 8 유지, 종류별 예산이 최신 |
| X-7 | ROOM T4 30일 닫기 정책 vs 구현 여부 미확인 | M-11에서 확인 필요 |
| X-8 | D22 확정 1회 vs 구 요구사항·시안 2회 게이트 문구 잔재 | D22 합침이 최신 |

D2 exit 0
