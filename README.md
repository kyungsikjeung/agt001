# 한마디 — 말하면 가게 사이트가 된다

> 소상공인이 채팅(글·음성·사진)으로 원하는 것을 설명하면, AI가 요구사항을 정리해 확인받은 뒤 실제로 동작하는 웹사이트를 만들어 바로 공개해 주는 서비스. 베타 기간 무료.

## 배경 — 왜 이 서비스를 만들었나

**코드는 이제 AI가 금방 짠다. 어려운 건 "무엇을 만들지"를 여러 사람이 함께 정하는 일이다. 한마디는 그 일을 대화방에서 끝내고, 합의된 내용을 실제 사이트로 공개하는 데까지 잇는다.**

AI로 코드를 짜는 도구가 좋아지면서, 여러 사람이 함께 "바이브 코딩"을 해 본 일이 있다.
원하는 것을 말로 설명하면 AI가 코드를 짜 주는 방식이다.
코드는 금방 나왔다.
그런데 여러 사람이 함께 만들려고 하니, 코드보다 그 앞 단계가 더 어려웠다.
무엇을 만들지(요구사항)를 여러 사람이 함께 정하고 합의하는 일이 가장 느렸다.
각자 다른 말로 설명하고, 대화는 메신저 여기저기에 흩어졌다.
꼭 필요한 조건은 빠지고, 누가 무엇을 확정했는지도 알 수 없었다.

그래서 이런 모습을 바랐다.
여러 사람이 한 대화방에 모여 말로 요구사항을 함께 만들어 낸다.
AI가 그 말을 정리하고, 모자란 부분은 되묻고, 정리한 내용은 확인을 받는다.
합의가 되면 그 내용을 코드로 만들고, 만든 것을 바로 공개하는 데까지 이어진다.
말로 정하는 일과 실제로 만드는 일이 끊어지지 않는 흐름이다.

이 흐름을 만들면서, 일을 나누어 맡는 여러 에이전트로 직접 만들어 보고 싶었다.
요구사항 정리, 리뷰, 시안, 공개 전 검사, 음성처럼 역할을 나눈다.
에이전트 사이는 입력과 출력의 약속(`contracts/` 스키마)으로 잇는다.
고치는 기준은 느낌이 아니라 평가 도구로 재면서 정한다.
자세한 목록은 [docs/product/AGENTS.md](docs/product/AGENTS.md)에 있다.

왜 가게 사이트부터 시작했는지는 세 가지 이유다.
첫째, 이 흐름이 가장 절실한 사람은 코드를 모르는 가게 사장님이다.
둘째, 한 페이지 사이트는 결과가 작아서 "요구에서 구현, 공개까지" 한 바퀴를 끝까지 돌려 보기 좋다.
셋째, 가게 일은 사장님과 가족, 직원처럼 여러 사람이 함께 정하는 경우가 많다.

| 겪은 문제 | 제품에서의 답 | 근거 |
|---|---|---|
| 여러 사람이 따로 말함 | 공유방에서 함께 답하고, 요약 단계에서 전원 동의가 있어야 넘어감 | docs/product/DECISIONS.md D52, app/services/rooms.py |
| 빠진 조건, 지어낸 값 | 요구사항 엔진의 근거 검사와 리뷰어 에이전트로 걸러 다시 묻기 | docs/product/DECISIONS.md D34, app/services/prd_engine.py |
| 누가 확정했는지 모름 | 요약 카드에서 사장님 최종 확인을 한 번만 거침 | docs/product/DECISIONS.md D22 |
| 구현과 공개가 따로 놈 | 고른 시안을 그대로 공개 사이트로 열고, 공개 전 자동 검사로 막음 | app/services/publish_check.py |

앞으로는 가게 사이트에서 개인, 단체, 웹서비스로 넓힌다.
입구 게이트가 이미 가게, 개인, 단체, 웹서비스를 나눈다(app/services/intake.py).

## 왜 필요한가

| 문제 | 기존 방식의 한계 | 이 서비스의 답 |
|---|---|---|
| 외주는 비싸다 | 한 페이지에 수십만~수백만원, 수정 때마다 추가 비용 | AI가 정리·제작, 베타 무료 |
| 직접 만들기는 어렵다 | 개발 지식 없이 휴대폰만 있는 사장님 | 말과 사진만으로 완성 |
| AI만 쓰면 지어낸다 | 없는 전화·가격을 만들어냄 | 근거 검사 + 틀린 값 저장 차단, 확정 전 사람 확인 |

```mermaid
flowchart LR
    P1(["1 비싸다·어렵다·지어낸다"]) --> P2["2 말하기(채팅·음성·사진)"]
    P2 --> P3["3 AI 정리 + 사장님 확인"]
    P3 --> P4["4 시안 3안 중 선택"]
    P4 --> P5["5 공개 + 문의·예약 알림"]
```

| 번호 | 단계 | 설명 |
|---|---|---|
| 1 | 문제 | 외주는 비싸고, 직접 만들기는 어렵고, AI만 쓰면 없는 전화·가격을 지어낸다 |
| 2 | 말하기 | 글·음성(🎤, 답변 읽어주기, 손 안 쓰는 모드)·사진으로 설명한다 |
| 3 | 정리·확인 | 요구사항 엔진이 근거 있는 값만 칸에 넣고, 틀린 값(자리수 틀린 전화·25시 등)은 저장하지 않고 다시 묻는다 |
| 4 | 시안 | 분위기가 다른 3안 중 하나를 고른다 |
| 5 | 공개 | 공개 사이트에서 손님이 문의·예약을 신청하면 채팅방으로 알린다. 사장님 카톡 전달은 코드는 배포됐으나 실제 수신 확인 전이다(STATUS.md §4 3번) |

## 3분 안에 써 보기

1. https://144.24.91.250.sslip.io 를 연다. 휴대폰이면 "앱 설치"를 눌러 홈 화면에 둔다. → 입력창이 있는 첫 화면이 보인다.
2. 예시처럼 한 문장을 입력하고 "시작하기"를 누른다. → 채팅방이 열리면서 첫 질문이 보인다.
   - "망원동 분식 가게인데, 메뉴와 영업시간, 찾아오는 길을 알리는 한 페이지 사이트를 만들어 주세요"
   - "초등학생 대상 영어 개인 레슨을 하는데, 수업 소개와 시간표, 문의 방법이 담긴 한 페이지 사이트를 만들어 주세요"
3. 질문에 답하거나, 바로 보려면 "시안 먼저"라고 보낸다. → 답할 때마다 다음 질문이, "시안 먼저" 뒤에는 정리된 요약이 보인다.
4. 요약을 보고 "승인"이라고 보내면 참고 견적이, 이어서 "진행"이라고 보내면 시안 준비 안내가 보인다. → 참고 견적 한 줄과 시안 3안 안내가 보인다.
5. 시안 3안에서 마음에 드는 번호를 골라 "2안으로 할게요"라고 보내고, 이어서 "공개"라고 보낸다. → 고른 시안 그대로 열린 사이트 주소가 보인다.
6. 공개 사이트의 문의 폼으로 글을 보내 본다. → 채팅방에 "문의 알림"이 뜬다. 사장님 카톡 전달은 코드는 배포됐으나 실제 수신 확인 전이다(STATUS.md §4 3번).
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
4. 견적 — 규칙으로 계산한 참고 견적 한 줄과 산정 근거를 확인한다 (베타 무료, 외주를 맡길 때의 참고값) (`app/services/quote.py`).
5. 시안 — 분위기가 다른 시안 3안을 보고 하나를 고른다 (`app/services/design_variants.py`).
6. 코드생성 — 확정 요구사항으로 Hermes가 격리 샌드박스에서 사이트를 만든다 (`app/services/codegen.py`).
7. 공개 사이트 — `/site/<id>/` 로 실제 접속 가능한 결과물을 받는다 (`app/api/public.py`).

## 지금 상태 (2026-09-27 갱신)

운영 배포 커밋은 [STATUS.md](STATUS.md) 맨 위에 적는다(배포 스크립트가 확인한 값).

**운영에서 바로 확인할 수 있는 것**

| 기능 | 확인 방법 |
|---|---|
| 입력창 중심 랜딩 + 업종 템플릿 6개 | https://144.24.91.250.sslip.io |
| 입구 게이트: 문의 종류 분류(가게·개인·단체·웹서비스), 종류별 질문 예산, 기능 사례집 42개 판정, 금지 요청 거절 | 랜딩에 입력 → 채팅방 |
| 요구사항 질문 엔진: 선택지 버튼, 알아들은 내용 되짚기("이렇게 이해했어요"), 종류별 질문 예산, "시안 먼저" 건너뛰기, 요약 뒤 "고쳐 주세요" 반영, 짧은 답 재질문 방지 | 랜딩에 입력 → 채팅방 |
| 리뷰어 에이전트: 요약 직전 원문↔카드 대조 (D34) | 채팅방 요약 확인 전 |
| 음성 입력(NVIDIA Parakeet 한국어): 마이크 버튼 → 글자로 바뀌어 입력창에 들어감. 무전기 모드(누르고 말하기·자동 전송·답장 자동 읽기)도 됨. 여러 개 고르기에는 덧붙일 말이 있음 | 채팅방 입력줄의 마이크 버튼 |
| 질문 듣기 버튼(TTS) | 채팅방 질문 카드의 듣기 버튼 |
| 실시간 대화로 만들기: 업종을 말하면 화면 부품(첫 화면·메뉴·사진·지도·문의)을 하나씩 쉬운 말로 묻고, 정할 때마다 모바일·PC 미리보기에 바로 생김. 🔴 실시간 대화는 질문 읽기→말 끝 자동 감지→자동 전송 반복 (`docs/product/COMPOSE_INTERVIEW_CONTRACT.md`) | 채팅방 머리줄 "🎙 실시간 대화" → `/live.html?room=<id>` |
| 공유방: 방장 넘기기·나가기(먼저 들어온 사람이 승계), 초대 링크(기간·목록·폐기, 새 방은 초대로만 입장), 과반 투표, 본인 확인 값 비노출, 투표 24시간·견적 7일·30일 닫기 타이머 + 사전 경고(투표 20시간·견적 6일·닫힘 27일), 10명 상한 | `/room.html` |
| 사장님 직접 편집 화면: 실제 카드를 불러와 바뀐 칸만 저장, 공개본에 바로 반영(`/editor?room=`, 방장만 편집) | `/editor?room=<id>` |
| 사진 올리기: 위치 정보 제거·1600px JPEG, 시안·공개본 자동 갱신 | 채팅방 사진 버튼 |
| 영상 링크 → 영상 카드(유튜브·인스타·네이버TV, 소개 뒤에 썸네일) | 채팅에 링크 붙이기 |
| 카카오톡 채널 주소 자동 인식, 문의 → 사장님 카톡 전송 시도("나에게 보내기", 이용 중 동의, 실제 수신 확인 전) | 채팅방·공개 사이트 |
| 규칙 참고 견적 한 줄 + 베타 무료 (D25) | 채팅방에서 승인 → 견적 |
| 시안 3안(기본형·사진 강조형·간결형): 고르기 페이지, 채팅방 미리보기 카드와 "이걸로 할게요". 3안 구성 차별화(2안은 사진첩을 첫 화면 바로 뒤에, 3안은 상품 먼저·사진 없으면 사진첩 생략), 업종별 예시 그림, 디자인 다듬기(섹션 배경·그림자·나타나기) | `/design/<id>` → 채팅방 |
| RAG 자료를 기능 사례집·프로필로 교체(가짜 과거 프로젝트 제거) | 채팅방 유사 사례 안내 |
| NIM 대비 모델(super→ultra→lightning) | 요구사항 추출·대화 응답 (`app/llm.py`) |
| 카카오·구글 로그인. 카카오는 누구나, 구글은 테스트 모드라 버튼을 숨김(초대 계정만, 서버 경로·콘솔 설정은 유지). 운영 동작은 2026-09-26 실제 계정으로 확인: 로그인 → 내 프로젝트, `/api/me`, 로그아웃. state+PKCE, `__Host-` HttpOnly 세션 쿠키, 카카오는 닉네임만 받음 | 랜딩 로그인 메뉴 (카카오만 표시) |
| 내 프로젝트 목록 (`/projects`): 로그인하면 계정에 옮긴 방(다른 기기 포함)도 목록에 | `/projects` (로그인 뒤) |
| 사이트 문의 받기 (`POST /api/inquiries/{site_key}` → 채팅방 "문의 알림" + 사장님 카톡 전송 시도(실제 수신 확인 전, STATUS.md §4 3번), 30일 보관, 스팸 숨김 칸, IP당 10분 5건, 생성 사이트 CSP에 allow-forms) | 공개 사이트의 문의 폼 |
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

## 기본 요구사항 1~11 대응표

원 요구 목록은 `docs/hackathon/REQUIREMENTS.md` §8, 상세 REQ는 같은 문서 §2~§7.

| 요구 | 어떻게 | 코드·문서 위치 | 상태 |
|---|---|---|---|
| 1. 인프라 설계 + Mermaid + 병렬작업 나누기 | 본 README 구조도 + `ARCHITECTURE.md` 시스템 컨텍스트 | `docs/hackathon/ARCHITECTURE.md` §1~§3 | 완료 |
| 2. 채팅 요구사항 전달 | 1:1 `/chat` + 공유방 `/room/<id>/chat`, 4초 폴링 조회 | `app/api/chat.py`, `app/api/rooms.py`, `app/services/chat_flow.py`, `app/services/rooms.py`, `static/room.html` | 완료 |
| 3. 접수/검증/질의(옵션+추천)/게이트 | 입구 게이트(종류 분류·금지 거절) → PRD 엔진(추출→근거 검사→질문 1개, 종류별 예산) → 리뷰어 에이전트(D34) → 요약. 공유방은 요약 단계 전원 동의(D52) | `app/services/intake.py`, `prd_engine.py`, `tests/engine/` (65건) | 완료 (T2 추출 2차 90.2%·3차 87.1%·3차 지어낸 값 0건(`docs/product/evals/extraction-2026-09-26-r2.md`, `docs/product/evals/extraction-2026-09-26-r3.md`), T3 대화 평가 최신 z3 32/35(91%)·지어낸 값 0건(`docs/product/evals/simulation-2026-09-27-zen-qwen-z3.md`, 측정 모델 Qwen·운영 모델 NIM 기준 공식 측정 아직 없음)) |
| 4. RAG 사전확인 | NIM 임베딩 코사인 유사도, 임계값 미만은 신규, 실패해도 대화 중단 없음 | `app/services/rag.py`, `app/llm.py` (`embed`) | 완료 |
| 5. 동작하는 산출물 (웹/안드로이드) | 웹: 고른 시안을 `/site/<id>/`로 공개(문의 폼 동작). 안드로이드: **PWA**로 홈 화면에 앱처럼 설치(standalone, 아이콘·오프라인 안내). 네이티브 앱은 나중에 다른 방식으로 | `app/api/public.py` (`serve_site`), `static/manifest.json`, `static/sw.js`, `static/pwa.js` | 완료 (안드로이드는 PWA 1차) |
| 6. 채팅 확인 필수 + 견적 근거 | 공유방 과반 투표 승인 게이트. 견적은 규칙 계산 한 줄 + 근거(종류·담을 내용·기능 수) + 베타 무료(D25) | `app/services/rooms.py`, `app/services/quote.py` (`rule_quote`) | 완료 |
| 7. UI 시안 선택 | 카드 → 시안 3안(기본형·사진 강조형·간결형), 고르기 페이지, 채팅방 미리보기 카드와 "이걸로 할게요" | `app/services/design_variants.py`, `site_render.py`, `design.py`, `static/room.html` | 완료 |
| 8. 시안 링크 전송 | 시안(`/design/<id>`)·공개(`/site/<id>/`) 링크를 채팅방으로. 공개 전 빈 자리 목록을 보여주고 "그대로 공개"로 한 번 더 확인하는 사장님 확인 게이트는 구현(`app/services/chat_flow.py` `_publish`, D46 승인 전 게이트·D22 시안과 함께 한 번 확정) 후 고른 안 그대로 공개. 생성물은 별도 주소 | `app/services/chat_flow.py` (`_publish`), `app/api/public.py`, `app/main.py` (`_split_hosts`) | 완료 |
| 9. 에이전트 분리 + Flow 검토 산출물 | 역할별 모듈(대화 진행·입구 게이트·요구사항 엔진·리뷰어·RAG·견적·시안·공개·코드생성·문의·음성) + 실행 흐름 산출물 | `docs/product/FLOWDOC.md` (시퀀스·상태도, 운영 실측 기준) | 완료 |
| 10. 동일 개발환경 | `docker compose up --build` 한 줄 기동, `.env.example` 템플릿, 비밀 키 미커밋 | `docker-compose.yml`, `.env.example`, `docs/hackathon/deployment/templates/Dockerfile.backend` | 완료 |
| 11. 온보딩 가이드 | 배경/목적/핸즈온 3단 구조 문서, 로컬 셋업·배포 가이드 | `docs/hackathon/LOCAL_SETUP.md`, `docs/hackathon/ENVIRONMENT.md`, `docs/hackathon/deployment/RENDER_DEPLOY.md` | 완료 |

추가 (REVIEW): 공개 전 사장님 확인 게이트와 게시 전 검사(`app/services/publish_check.py`)는 구현됨. 원안(`docs/hackathon/REVIEW_GATE_DESIGN.md`)의 검토자 순번 사람이 배포본을 직접 열어 확인하는 절차는 코드로 강제되지 않아 미구현.

## 에이전트 구성

| 구분 | 맡은 일 | 코드 |
|---|---|---|
| 입구·요구·리뷰·승인 | 금지 거절·종류 분류, 추출·근거 검사·다음 질문, 요약 직전 대조, 요약·투표 통과 때만 진행 | `app/services/intake.py`, `app/services/prd_engine.py`, `app/services/chat_flow.py` |
| 시안·문구 | 컨셉·3안 렌더·소개 문구 초안·예시 그림 (사장님 사진이 오면 먼저 씀) | `app/services/design_concept.py`, `app/services/design_variants.py`, `app/services/design.py`, `app/services/copywriter.py`, `app/services/ai_images.py` |
| 공개·검사 | 빈 자리 확인·게시 전 위험 차단 뒤 고른 안을 `/site/<id>/`로 공개 | `app/services/chat_flow.py` (`_publish`), `app/services/publish_check.py`, `app/services/deploy.py` |
| 문의·알림 | 폼 저장·채팅방 알림·사장님 카톡 전송 시도 (실제 수신 확인 전, STATUS.md §4 3번) | `app/services/inquiries.py`, `app/services/bookings.py`, `app/services/notify.py`, `app/services/kakao_talk.py` |
| 음성·사진·공유방 | 말→글·답장 읽기·통화 PoC, 사진 정리·반영, 다인원 방·전원 동의 | `app/services/stt.py`, `app/services/tts.py`, `app/services/photos.py`, `app/services/rooms.py` |
| 기반 | 모든 NIM 호출 1곳·지표 기록·키 교체 기반 | `app/llm.py`, `app/services/funnel.py`, `app/services/keystore.py` |

자세히: [docs/product/AGENTS.md](docs/product/AGENTS.md)

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
| 6 | 견적 | 규칙 계산 한 줄 + 베타 무료 (D25) (`app/services/quote.py`) |
| 7 | 시안 | 카드 → 시안 3안(기본형·사진 강조형·간결형) 부품+토큰 렌더 (`design_variants.py`, `site_render.py`, `design.py`) |
| 8 | 시안 선택 | 현재 단일 시안 확인. 3안 비교·투표는 진행 중 |
| 9 | Hermes 코드생성 | Docker 샌드박스(`--rm`, `/workspace`만) 격리 실행 (`app/services/codegen.py`) |
| 10 | 배포 | 산출물을 `generated/<id>/`에 기록, 백엔드가 직접 서빙 (`app/services/deploy.py`) |
| 11 | 공개 사이트 | `/site/<id>/`, CSP sandbox 격리 (`app/api/public.py`) |
| 12 | 직접 편집 | 명세 값 수정 프로토타입, 목업 데이터 (`frontend/src/editor/`, `/editor`) |
| 13 | NIM 대화·임베딩 | 모든 NIM 호출의 단일 진입점 + super→ultra→lightning 폴백 (`app/llm.py`) |
| 14 | 음성 입력 | Parakeet STT(입력창 전달, 녹음 즉시 삭제) + Magpie TTS 듣기 + 무전기 모드 (`docs/product/VOICE_INPUT_PLAN.md`) |
| 15 | 카카오 초대 링크 | 방 초대·시안·배포 링크 공유. 그룹채팅 내 봇 동작은 공식 API로 불가하여 링크 공유 방식 |

## 품질

테스트 수 (2026-09-27 기준, CI 합계 334개 + 프론트·평가):

- 단위 테스트: 269개 (`tests/unit`, 실제 PostgreSQL 위에서, CI에서 매 커밋 실행).
- 엔진 검증 테스트: 65개 (`tests/engine`, 경계 조건·T3 후속 회귀·W1 저장 차단. 전부 통과).
- 평가 도구 테스트: 29개 (`evals/tests`, 추출 평가·대화 시뮬레이션·wrong 6개).
- E2E 테스트: 5개 (`tests/e2e/test_room_e2e.py`: 입장→요청→투표→견적→시안→코드생성→배포 URL 흐름).
- 프론트 테스트: 36개 (vitest + jsdom), 휴대폰 크기 자동 점검 `tests/e2e/mobile_flow.py` 11단계 통과(운영).

CI (`.github/workflows/ci.yml`):

- 백엔드 잡: Python 3.11, PostgreSQL 16 서비스, `compileall` + `pytest -q`.
- 프론트 잡: Node 18, `tsc --noEmit` + `vite build` + `vitest run`.

보안 조치:

- 생성 사이트·시안은 별도 미리보기 호스트(`144-24-91-250.sslip.io`, 앱 주소는 308 리다이렉트)에서 CSP `sandbox` 헤더로 서빙하여 앱 출처로 취급되지 않게 하고 저장소·쿠키 접근을 차단 (`app/api/public.py`, `app/main.py` `_split_hosts`). 시안 고르기 페이지의 미리보기 iframe도 `sandbox`로 묶는다 (S-2, `tests/unit/test_publish_check.py`가 자동 검사).
- 공개 전 검사: 외부 스크립트·외부로 보내는 폼·자동 이동·열쇠 패턴이 있으면 게시를 막고 사장님께 알린다 (S-5, `app/services/publish_check.py`).
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
├── tests/unit, tests/engine, tests/e2e # 단위 269개·엔진 검증 65개(CI 합계 334개)·E2E 5개
├── evals/               # 시나리오 36개, 추출 평가 60개, 평가 실행기
├── contracts/            # 병렬작업 간 경계(BND) 스키마 + 예시
├── scripts/              # deploy.sh, rollback.sh, backup_db.sh
├── deploy/Caddyfile      # HTTPS 리버스 프록시
├── docker-compose.yml    # db + backend + caddy
└── docs/                 # 문서 (아래 목록)
```

## 문서 목록 (최신순 전체는 [`docs/INDEX.md`](docs/INDEX.md))

- 외부 안내: `docs/external/FEATURES.md` (기능) · `SYSTEM_REQUIREMENTS.md` (SYS-1~28) · `SOFTWARE_REQUIREMENTS.md` (SW-1~21) · `TRACEABILITY.md` (추적표) · `GLOSSARY.md` (용어)
- 설계: `docs/hackathon/ARCHITECTURE.md` (v0.2) · `docs/product/FLOWDOC.md` (실행 흐름) · `docs/product/COMPONENT_CATALOG.md` (레이어·인터페이스) · `docs/product/DESIGN_RATIONALE.md` (설계 관점)
- 요구 정본: `docs/hackathon/REQUIREMENTS.md` (REQ) · `docs/reqpipe/02_REQUIREMENTS.md` (G01~G18)
- 진행 상황: `STATUS.md` · `docs/product/BACKLOG.md` · 결정 `docs/product/DECISIONS.md`
- 운영: `docs/product/DB_OPERATIONS.md` · `docs/product/COST_MONITORING.md` · 로컬 셋업 `docs/hackathon/LOCAL_SETUP.md`
