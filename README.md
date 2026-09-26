# agt001 — 말하면 가게 사이트가 된다

## 3분 안에 써 보기

1. https://144.24.91.250.sslip.io 를 연다. 휴대폰이면 "앱 설치"를 눌러 홈 화면에 둔다. → 입력창이 있는 첫 화면이 보인다.
2. 예시처럼 한 문장을 입력하고 "시작하기"를 누른다. → 채팅방이 열리면서 첫 질문이 보인다.
   - "망원동 분식 가게인데, 메뉴와 영업시간, 찾아오는 길을 알리는 한 페이지 사이트를 만들어 주세요"
   - "초등학생 대상 영어 개인 레슨을 하는데, 수업 소개와 시간표, 문의 방법이 담긴 한 페이지 사이트를 만들어 주세요"
3. 질문에 답하거나, 바로 보려면 "시안 먼저"라고 보낸다. → 답할 때마다 다음 질문이, "시안 먼저" 뒤에는 정리된 요약이 보인다.
4. 요약을 보고 "승인"이라고 보내면 참고 견적이, 이어서 "진행"이라고 보내면 시안 준비 안내가 보인다. → 참고 견적 한 줄과 시안 3안 안내가 보인다.
5. 시안 3안에서 마음에 드는 번호를 골라 "2안으로 할게요"라고 보내고, 이어서 "공개"라고 보낸다. → 고른 시안 그대로 열린 사이트 주소가 보인다.
6. 공개 사이트의 문의 폼으로 글을 보내 본다. → 채팅방에 "문의 알림"이 뜨고, 사장님 카톡으로도 전달된다.
- 로그인은 선택이다. 카카오는 누구나 쓸 수 있다. 구글은 테스트 모드라 버튼을 숨겼다(초대 계정만, 서버 경로는 유지).

소상공인이 채팅(글·음성·사진)으로 원하는 것을 설명하면, AI가 요구사항을 정리해 확인받은 뒤 실제로 동작하는 웹사이트를 만들어 바로 공개해 주는 서비스.

- 운영 주소: https://144.24.91.250.sslip.io
- 직접 편집 화면: https://144.24.91.250.sslip.io/editor (프로토타입, 목업 데이터)
- 1:1 채팅: https://144.24.91.250.sslip.io/ (정적 폴백) 또는 기존 채팅 위젯
- 다인원 공유방: https://144.24.91.250.sslip.io/room.html

## 30초 사용 흐름

1. 랜딩 입력 — 가게와 원하는 것을 한 문장으로 입력한다 (`frontend/src/Landing.tsx`).
2. 질문 몇 개 — 요구사항 엔진이 빈 칸 하나씩 최대 8회까지 되묻는다. 선택지 4개 이하 + 자유 입력 (`app/services/prd_engine.py`).
3. 요약 확인 — 요구사항 카드를 보고 확정한다. 공유방은 과반 투표 (`app/services/rooms.py`).
4. 견적 — 견적 3안과 산정 근거를 확인한다 (베타 무료, 외주를 맡길 때의 참고값) (`app/services/quote.py`).
5. 시안 — 분위기가 다른 시안 후보를 보고 하나를 고른다 (진행 중, 현재는 1종 정적 템플릿).
6. 코드생성 — 확정 요구사항으로 Hermes가 격리 샌드박스에서 사이트를 만든다 (`app/services/codegen.py`).
7. 공개 사이트 — `/site/<id>/` 로 실제 접속 가능한 결과물을 받는다 (`app/api/public.py`).

## 지금 상태 (2026-09-26 갱신)

운영 배포 HEAD: `1818401` (2026-09-26).

**운영에서 바로 확인할 수 있는 것**

| 기능 | 확인 방법 |
|---|---|
| 입력창 중심 랜딩 + 업종 템플릿 6개 | https://144.24.91.250.sslip.io |
| 입구 게이트: 문의 종류 분류(가게·개인·단체·웹서비스), 종류별 질문 예산, 기능 사례집 42개 판정, 금지 요청 거절 | 랜딩에 입력 → 채팅방 |
| 요구사항 질문 엔진: 선택지 버튼, 알아들은 내용 되짚기("이렇게 이해했어요"), 종류별 질문 예산, "시안 먼저" 건너뛰기, 요약 뒤 "고쳐 주세요" 반영, 짧은 답 재질문 방지 | 랜딩에 입력 → 채팅방 |
| 리뷰어 에이전트: 요약 직전 원문↔카드 대조 (D34) | 채팅방 요약 확인 전 |
| 음성 입력(NVIDIA Parakeet 한국어): 마이크 버튼 → 글자로 바뀌어 입력창에 들어감. 무전기 모드(누르고 말하기·자동 전송·답장 자동 읽기)도 됨. 여러 개 고르기에는 덧붙일 말이 있음 | 채팅방 입력줄의 마이크 버튼 |
| 질문 듣기 버튼(TTS) | 채팅방 질문 카드의 듣기 버튼 |
| 공유방: 방장 넘기기·나가기(먼저 들어온 사람이 승계), 초대 링크(기간·목록·폐기, 새 방은 초대로만 입장), 과반 투표, 본인 확인 값 비노출, 투표 24시간·견적 7일·30일 닫기 타이머 + 사전 경고(투표 20시간·견적 6일·닫힘 27일), 10명 상한 | `/room.html` |
| 사장님 직접 편집 화면: 실제 카드를 불러와 바뀐 칸만 저장, 공개본에 바로 반영(`/editor?room=`, 방장만 편집) | `/editor?room=<id>` |
| 사진 올리기: 위치 정보 제거·1600px JPEG, 시안·공개본 자동 갱신 | 채팅방 사진 버튼 |
| 영상 링크 → 영상 카드(유튜브·인스타·네이버TV, 소개 뒤에 썸네일) | 채팅에 링크 붙이기 |
| 카카오톡 채널 주소 자동 인식, 문의 → 사장님 카톡("나에게 보내기", 이용 중 동의) | 채팅방·공개 사이트 |
| 규칙 참고 견적 한 줄 + 베타 무료 (D25) | 채팅방에서 승인 → 견적 |
| 시안 3안(기본형·사진 강조형·간결형): 고르기 페이지, 채팅방 미리보기 카드와 "이걸로 할게요". 3안 구성 차별화(2안은 사진첩을 첫 화면 바로 뒤에, 3안은 상품 먼저·사진 없으면 사진첩 생략), 업종별 예시 그림, 디자인 다듬기(섹션 배경·그림자·나타나기) | `/design/<id>` → 채팅방 |
| RAG 자료를 기능 사례집·프로필로 교체(가짜 과거 프로젝트 제거) | 채팅방 유사 사례 안내 |
| NIM 대비 모델(super→ultra→lightning) | 요구사항 추출·대화 응답 (`app/llm.py`) |
| 카카오·구글 로그인. 카카오는 누구나, 구글은 테스트 모드라 버튼을 숨김(초대 계정만, 서버 경로·콘솔 설정은 유지). 운영 동작은 2026-09-26 실제 계정으로 확인: 로그인 → 내 프로젝트, `/api/me`, 로그아웃. state+PKCE, `__Host-` HttpOnly 세션 쿠키, 카카오는 닉네임만 받음 | 랜딩 로그인 메뉴 (카카오만 표시) |
| 내 프로젝트 목록 (`/projects`): 로그인하면 계정에 옮긴 방(다른 기기 포함)도 목록에 | `/projects` (로그인 뒤) |
| 사이트 문의 받기 (`POST /api/inquiries/{site_key}` → 채팅방 "문의 알림" + 사장님 카톡, 30일 보관, 스팸 숨김 칸, IP당 10분 5건, 생성 사이트 CSP에 allow-forms) | 공개 사이트의 문의 폼 |
| 공개 사이트 빈칸 감추기(빈 부품 빼기, 빈 줄 숨김, 빈 가격은 "가격 문의". 시안에서는 그대로 보임), AI 소개 문구 초안(첫 화면 한 줄·소개·상품 설명, 원문에 없는 숫자 문장은 버림), 문의 양식 기본 포함, 편의 안내 아이콘 칸 | 공개 사이트·시안 |
| 개인정보처리방침 초안 갱신 + 랜딩 아래 약관 링크 | 랜딩 하단 |
| 문의 부품 `contact--form`, `contact--kakao-channel` 추가 (섹션 22종) | 시안·공개 사이트 |

**남은 일 ([BACKLOG.md](docs/product/BACKLOG.md) 참조)**

| 작업 | 상태 |
|---|---|
| M-4 미리보기 별도 호스트: 생성 사이트·시안은 https://144-24-91-250.sslip.io 에서 열림(앱 주소는 308로 보냄) | 완료 |
| M-5 렌더러 계약 5건 결정 (`docs/product/reviews/RENDERER_NOTES.md` §4) | 완료 |
| M-10 방침 보호책임자·시행일 확정(사용자) | 사용자 대기 |
| M-12 저장소 공개(사용자) | 사용자 대기 |
| 테스트: 단위 236, 엔진 48, 프런트 36 전부 통과. 휴대폰 크기 자동 점검 `tests/e2e/mobile_flow.py` 11단계 통과(운영) | 완료 (2026-09-26) |
| 서버 밖 백업: `scripts/pull_backups.sh` + `scripts/install_backup_pull.sh` | 스크립트 완료, 사용자가 Mac에서 설치 실행 필요 |

**알려진 한계:** 다른 기기에서 방을 열면 새 참여자로 들어갑니다. 채팅방 아래 버튼이 휴대폰에서 많음(정리 예정). 사장님 카톡 실제 수신은 아직 실측 전. 서버 밖 백업은 사용자 설치 대기.

## NVIDIA 기술을 쓴 곳

| 기술 | 용도 | 코드·문서 위치 | 상태 |
|---|---|---|---|
| NIM 대화 모델 `nvidia/nemotron-3-super-120b-a12b` (주) | 요구사항 추출(`chat_json`), 리뷰어 에이전트(요약 직전 원문↔카드 대조, D34), 대화 응답 | `app/llm.py` (`chat`, `chat_json`), `app/services/prd_engine.py` (`extract_detail`, `review`), `app/services/chat_flow.py` | 동작 |
| NIM 대비 모델 `nvidia/nemotron-3-ultra-550b-a55b` → `nvidia/nemotron-3.5-lightning-30b-a3b` | 주 모델 과부하(503)·요청 제한·시간 초과 때 차례로 대신 응답. 실패 모델 60초 건너뛰기, 세 모델 동시 실패면 2초 쉬고 한 바퀴 더 | `app/llm.py` (`_with_fallback`), `app/config.py` (`nim_chat_fallback_models`) | 동작 (9/26 운영 과부하를 실제로 넘김. ultra 실측 2.2초) |
| NIM 임베딩 `nvidia/nemotron-3-embed-1b` | 비슷한 사례 찾기(RAG): 기능 사례집 42개 + 업종·종류 프로필 9개를 한 번에 임베딩(2.4초), 기준 0.76 | `app/llm.py` (`embed`, `embed_many`), `app/services/rag.py` | 동작 |
| Parakeet 1.1B RNNT 다국어 음성 인식 (NVIDIA 호스팅) | 채팅방 마이크 버튼: 녹음 → 16kHz 변환 → 한국어 전사 → 한글 숫자("공일공…")를 숫자로 → 입력창에 넣고 사장님이 고친 뒤 전송 | `app/services/stt.py`, `app/api/stt.py`(`POST /api/stt`), `static/voice.js`, `static/room.html` | 동작 |
| Magpie TTS 다국어 (NVIDIA 호스팅, `KO-KR.Aria`) | AI 답장 "듣기" 버튼(자동 재생 없음) | `app/services/tts.py`, `app/api/tts.py`(`POST /api/tts`), `static/voice.js` | 동작 (운영 실측 2.25초, 합성→재인식 왕복 확인) |
| Hermes 코드생성 에이전트 | 확정 스펙으로 정적 웹 프로젝트 생성, 요청별 Docker 컨테이너(`--rm`, `/workspace`만 마운트)로 격리. 공개 사이트는 이제 사장님이 고른 시안(정해진 부품)을 우선 쓴다(D31) | `app/services/codegen.py`, `app/config.py` (`hermes_sandbox_image`) | 동작 (선택 기능) |

음성 실측 (부록 `docs/product/VOICE_INPUT_PLAN.md` 부록, 2026-09-26, Claude 실측):

- Parakeet 1.1B RNNT 다국어: 한국어 문장 약 9초 분량을 2.5초에 전사. "객실 세 개"를 "객실세계"로 오인식 1건, 전화번호는 한글 숫자("공일공 …")로 출력.
- Magpie TTS 다국어: 7.4초 분량을 1.4초에 합성 (한국어 목소리 6개).
- 합성 음성을 다시 전사한 왕복 확인: 원문과 거의 같음 (띄어쓰기만 차이).
- 계획 변경 기록: 3단계 서버 전사의 기본 엔진을 Parakeet로 하며, 전사 결과는 입력창에 넣고 사용자가 고친 뒤 전송한다. 녹음 파일은 전사 직후 삭제. 호스팅 API의 운영 규모 이용 조건·요금·호출 한도는 NVIDIA 약관 확인이 필요하다.

요구사항 추출 실측 (`docs/product/research/REQUIREMENTS_ENGINE_RESEARCH.md` §5):

- `guided_json`·`response_format` 스키마 강제는 이 모델에서 형식을 깨뜨려 사용하지 않는다.
- 채택: 추론 끔(`enable_thinking=false`) + 스키마를 프롬프트에 + 서버 검증. 발화 8개 시험에서 형식 통과 8/8, 지어낸 사실 0건, 평균 응답 3.4초.

## 주최 요구 1~11 대응표

원 요구 목록은 `docs/hackathon/REQUIREMENTS.md` §8, 상세 REQ는 같은 문서 §2~§7.

| 요구 | 어떻게 | 코드·문서 위치 | 상태 |
|---|---|---|---|
| 1. 인프라 설계 + Mermaid + 역할분담 | 본 README 구조도 + `ARCHITECTURE.md` 시스템 컨텍스트 | `docs/hackathon/ARCHITECTURE.md` §1~§3 | 완료 |
| 2. 채팅 요구사항 전달 | 1:1 `/chat` + 공유방 `/room/<id>/chat`, 4초 폴링 조회 | `app/api/chat.py`, `app/api/rooms.py`, `app/services/chat_flow.py`, `app/services/rooms.py`, `static/room.html` | 완료 |
| 3. 접수/검증/질의(옵션+추천)/게이트 | 입구 게이트(종류 분류·금지 거절) → PRD 엔진(추출→근거 검사→질문 1개, 종류별 예산) → 리뷰어 에이전트(D34) → 요약. 공유방 사실은 방장 확인 | `app/services/intake.py`, `prd_engine.py`, `tests/engine/` (45건) | 완료 (T2 추출 87~90%, T3 실행 중) |
| 4. RAG 사전확인 | NIM 임베딩 코사인 유사도, 임계값 미만은 신규, 실패해도 대화 중단 없음 | `app/services/rag.py`, `app/llm.py` (`embed`) | 완료 |
| 5. 동작하는 산출물 (웹/안드로이드) | 웹: 고른 시안을 `/site/<id>/`로 공개(문의 폼 동작). 안드로이드: **PWA**로 홈 화면에 앱처럼 설치(standalone, 아이콘·오프라인 안내). 네이티브 앱은 나중에 다른 방식으로 | `app/api/public.py` (`serve_site`), `static/manifest.json`, `static/sw.js`, `static/pwa.js` | 완료 (안드로이드는 PWA 1차) |
| 6. 채팅 확인 필수 + 견적 근거 | 공유방 과반 투표 승인 게이트. 견적은 규칙 계산 한 줄 + 근거(종류·담을 내용·기능 수) + 베타 무료(D25) | `app/services/rooms.py`, `app/services/quote.py` (`rule_quote`) | 완료 |
| 7. UI 시안 선택 | 카드 → 시안 3안(기본형·사진 강조형·간결형), 고르기 페이지, 채팅방 미리보기 카드와 "이걸로 할게요" | `app/services/design_variants.py`, `site_render.py`, `design.py`, `static/room.html` | 완료 |
| 8. 시안 링크 전송 | 시안(`/design/<id>`)·공개(`/site/<id>/`) 링크를 채팅방으로. 공개 전 빈 자리 확인(사람 최종 검토) 후 고른 안 그대로 공개. 생성물은 별도 주소 | `app/services/chat_flow.py` (`_publish`), `app/api/public.py`, `app/main.py` (`_split_hosts`) | 완료 |
| 9. 에이전트 분리 + Flow 검토 산출물 | 역할별 모듈(대화 진행·입구 게이트·요구사항 엔진·리뷰어·RAG·견적·시안·공개·코드생성·문의·음성) + 실행 흐름 산출물 | `docs/product/FLOWDOC.md` (시퀀스·상태도, 운영 실측 기준) | 완료 |
| 10. 동일 개발환경 | `docker compose up --build` 한 줄 기동, `.env.example` 템플릿, 비밀 키 미커밋 | `docker-compose.yml`, `.env.example`, `docs/hackathon/deployment/templates/Dockerfile.backend` | 완료 |
| 11. 온보딩 가이드 | 배경/목적/핸즈온 3단 구조 문서, 로컬 셋업·배포 가이드 | `docs/hackathon/LOCAL_SETUP.md`, `docs/hackathon/ENVIRONMENT.md`, `docs/hackathon/deployment/RENDER_DEPLOY.md` | 완료 |

추가 (REVIEW): 사람 최종 검토 게이트는 설계 문서(`docs/hackathon/REVIEW_GATE_DESIGN.md`)까지 완료, 구현은 미착수.

## 구조도

```mermaid
flowchart LR
    N1(["1 랜딩"]) --> N2(["2 1:1 채팅"])
    N1 --> N3(["3 공유방"])
    N2 --> N4["4 요구사항 엔진"]
    N3 --> N4
    N4 --> N5{"5 승인 게이트"}
    N5 -->|반려·수정| N4
    N5 -->|승인| N6["6 견적"]
    N6 --> N7["7 시안"]
    N7 --> N8["8 시안 선택"]
    N5 --> N9["9 Hermes 코드생성"]
    N9 --> N10["10 배포"]
    N10 --> N11["11 공개 사이트"]
    N11 --> N12["12 직접 편집"]
    N4 --> N13["13 NIM 대화·임베딩"]
    N9 --> N13
    N4 -.-> N14["14 음성 입력"]
    N3 --> N15["15 카카오 초대 링크"]
    N7 --> N15
    N11 --> N15
```

| 번호 | 노드 | 설명 |
|---|---|---|
| 1 | 랜딩 | 가치 제안 + 입력창. React (`frontend/src/Landing.tsx`), `/` 에서 서빙 |
| 2 | 1:1 채팅 | 개인 요청 흐름 (`app/api/chat.py`, `app/services/chat_flow.py`) |
| 3 | 공유방 | 다인원 방, 과반 투표, 4초 폴링 (`app/api/rooms.py`, `app/services/rooms.py`, `static/room.html`) |
| 4 | 요구사항 엔진 | 추출(NIM) + 규칙(질문 고르기·지어내기 차단). 최대 8회, 선택지 4개 이하 (`app/services/prd_engine.py`) |
| 5 | 승인 게이트 | 확정 또는 과반 투표 통과 시에만 다음 단계 (`app/services/rooms.py`) |
| 6 | 견적 | AI 3안 JSON + 추천. 규칙 계산 전환 결정됨 (D25) (`app/services/quote.py`) |
| 7 | 시안 | 정적 템플릿 1종 렌더링 + 스크린샷 (`app/services/design.py`) |
| 8 | 시안 선택 | 현재 단일 시안 확인. 3안 비교·투표는 진행 중 |
| 9 | Hermes 코드생성 | Docker 샌드박스(`--rm`, `/workspace`만) 격리 실행 (`app/services/codegen.py`) |
| 10 | 배포 | 산출물을 `generated/<id>/`에 기록, 백엔드가 직접 서빙 (`app/services/deploy.py`) |
| 11 | 공개 사이트 | `/site/<id>/`, CSP sandbox 격리 (`app/api/public.py`) |
| 12 | 직접 편집 | 명세 값 수정 프로토타입, 목업 데이터 (`frontend/src/editor/`, `/editor`) |
| 13 | NIM 대화·임베딩 | 모든 LLM 호출의 단일 진입점 (`app/llm.py`) |
| 14 | 음성 입력 | 1단계 키보드 안내부터. Parakeet 연동은 진행 중 (`docs/product/VOICE_INPUT_PLAN.md`) |
| 15 | 카카오 초대 링크 | 방 초대·시안·배포 링크 공유. 그룹채팅 내 봇 동작은 공식 API로 불가하여 링크 공유 방식 |

## 품질

테스트 수 (파일을 직접 세어 확인, 2026-09-26 기준):

- 단위 테스트: 89개 (`tests/unit`, 실제 PostgreSQL 위에서, CI에서 매 커밋 실행).
- 엔진 검증 테스트: 31개 (`tests/engine`, 경계 조건. 15개 통과·16개는 결함 재현 — 수정 중).
- 평가 도구 테스트: 17개 (`evals/tests`, 추출 평가·대화 시뮬레이션 실행기).
- E2E 테스트: 5개 (`tests/e2e/test_room_e2e.py`: 입장→요청→투표→견적→시안→코드생성→배포 URL 흐름).
- 프론트 테스트: 18개 (`frontend/src/editor/EditorPage.test.tsx` 3, `specReducer.test.ts` 15, vitest + jsdom).

CI (`.github/workflows/ci.yml`):

- 백엔드 잡: Python 3.11, PostgreSQL 16 서비스, `compileall` + `pytest -q`.
- 프론트 잡: Node 18, `tsc --noEmit` + `vite build` + `vitest run`.

보안 조치:

- 생성 사이트·시안은 CSP `sandbox` 헤더로 서빙하여 앱 출처로 취급되지 않게 하고 저장소·쿠키 접근을 차단 (`app/api/public.py`). 별도 미리보기 호스트 분리는 로그인 전 필수 과제로 남음 (`docs/product/DESIGN_PIPELINE_PLAN.md` §13.5 S-1).
- 방 참여자 본인 확인 값(`member_id`)은 응답에 노출하지 않고 SHA-256 앞 12자리 핸들로만 내보냄 (`app/services/rooms.py` `member_handle`).
- `requirement_id`·`room_id`·`member_id`는 영숫자·하이픈·밑줄로 정제, 생성 사이트 경로는 산출물 디렉터리 안으로 제한 (`app/security.py`, `app/api/public.py`).
- 코드생성 프롬프트에는 정제·길이제한된 스펙만 넣고, API 키는 환경변수로만 전달하여 프로세스 인자에 노출하지 않음 (`app/services/codegen.py`).
- 말하지 않은 전화·주소·가격은 추출 단계에서 버리고, 확정 칸은 확인 없이 바꾸지 않음. `test_prd_engine.py`에서 규칙을 검사 (`app/services/prd_engine.py`).

운영:

- HTTPS: Caddy가 `144.24.91.250.sslip.io`로 들어오는 요청을 백엔드(8643)로 전달, 인증서 자동 발급 (`deploy/Caddyfile`).
- DB: PostgreSQL 16 컨테이너 + Alembic 마이그레이션. 기동 시 마이그레이션·세션 복구 (`app/db/migrate.py`, `app/main.py` lifespan, `docker-compose.yml`).
- 백업: `scripts/backup_db.sh` (cron 예시 포함, 최근 14개 보관). 복구 절차는 `docs/product/DB_OPERATIONS.md`.
- 롤백: `scripts/deploy.sh` 배포 전 스냅샷(최근 5개 보관) + `scripts/rollback.sh`, 헬스체크 실패 시 자동 롤백 옵션.

## 로컬 실행 방법

`.env.example` 기준. `.env` 파일은 읽거나 커밋하지 않는다.

```sh
cp .env.example .env
# .env에 POSTGRES_PASSWORD를 채운다 (로컬 개발용 임의 값, 예: openssl rand -hex 24)
# NIM을 쓰려면 NIM_API_KEY도 채운다. 없으면 폴백 동작으로 실행된다
docker compose up --build
```

- 1:1 채팅·랜딩: http://localhost:8643/
- 공유방: http://localhost:8643/room.html
- 편집기: 프론트 빌드 후 http://localhost:8643/editor (`frontend`에서 `npm ci && npm run build`)
- 헬스체크: http://localhost:8643/health
- 테스트: `pytest -q` (PostgreSQL 필요 시 `TEST_DATABASE_URL` 지정, CI 참고), 프론트는 `frontend`에서 `npm test`

## 폴더 구조 요약

```
agt001/
├── app/                  # 백엔드 (FastAPI)
│   ├── api/              # chat, rooms, public(시안·사이트 서빙), events
│   ├── services/         # chat_flow, prd_engine, rag, quote, design, codegen, deploy, rooms, funnel
│   ├── db/               # PostgreSQL 모델·세션·Alembic 마이그레이션
│   ├── llm.py            # NIM 호출 단일 진입점
│   └── security.py       # 토큰·스펙 정제
├── frontend/src/         # 랜딩·편집기 (React + TypeScript + Vite)
├── static/               # 기존 채팅·공유방 정적 화면 (index.html, room.html)
├── templates/            # 시안 템플릿 (현재 1종)
├── tests/unit, tests/engine, tests/e2e # 단위 89개·엔진 검증 31개·E2E 5개
├── evals/               # 시나리오 36개, 추출 평가 60개, 평가 실행기
├── contracts/            # 팀원 간 경계(BND) 스키마 + 예시
├── scripts/              # deploy.sh, rollback.sh, backup_db.sh
├── deploy/Caddyfile      # HTTPS 리버스 프록시
├── docker-compose.yml    # db + backend + caddy
└── docs/                 # 문서 (아래 목록)
```

## 문서 목록

- 진행 상황: `STATUS.md`
- 요구사항 정본·아키텍처: `docs/hackathon/REQUIREMENTS.md`, `docs/hackathon/ARCHITECTURE.md`
- 제품 로드맵·결정: `docs/product/PRODUCT_ROADMAP.md`, `docs/product/DECISIONS.md`
- 요구사항 엔진: `docs/product/REQUIREMENTS_ENGINE_PLAN.md`, `docs/product/research/REQUIREMENTS_ENGINE_RESEARCH.md`
- 시안 파이프라인: `docs/product/DESIGN_PIPELINE_PLAN.md` (§13이 우선)
- 음성 입력: `docs/product/VOICE_INPUT_PLAN.md` (부록에 Parakeet·Magpie 실측)
- 검토 게이트 설계: `docs/hackathon/REVIEW_GATE_DESIGN.md`
- 로컬 셋업·환경: `docs/hackathon/LOCAL_SETUP.md`, `docs/hackathon/ENVIRONMENT.md`
- 배포·DB 운영: `docs/hackathon/deployment/RENDER_DEPLOY.md`, `docs/product/DB_OPERATIONS.md`
