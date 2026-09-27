# 해커톤 심사 질의 방어 스크립트 (초안)

> 원칙: 숫자와 사실은 저장소 파일에 있는 것만 말한다 (STATUS.md). 모르는 숫자는 지어내지 않고 `[측정 중: Claude가 채움]`으로 둔다 (STATUS.md). 약점은 인정하고 "어떻게 재고 있고, 무엇으로 막고 있는지"로 답한다 (STATUS.md).

## 0. 30초 요약 답변 (맨 위 한 장)

- 이 서비스는 소상공인이 채팅(글·음성·사진)으로 설명하면 AI가 요구사항을 정리해 확인받은 뒤 실제 사이트를 만들어 바로 공개해 주는 것이다 (README.md).
- 실제로 동작하는 것은 첫째 휴대폰 크기 자동 점검 11단계가 운영에서 모두 통과한 것이다 (STATUS.md).
- 둘째 카카오 로그인은 운영에서 실제 계정으로 로그인·내 프로젝트·로그아웃까지 확인했고, 구글은 테스트 모드라 버튼을 숨긴 것이다 (STATUS.md).
- 셋째 공개 사이트의 문의 폼으로 보낸 글이 공용 DB에 저장되고 채팅방 "문의 알림"과 사장님 카톡으로 전달되는 흐름이 배포돼 있다 (STATUS.md).
- 정직한 한계는 AI 대화 평가가 최신 측정(9/27 밤 z3) 32/35(91%)·지어낸 값 0건까지 올랐지만 질문 수가 평균 5.9회로 목표(3회)보다 많고, 실행마다 ±3씩 흔들린다는 것이다 (docs/product/evals/simulation-2026-09-27-zen-qwen-z3.md).

## 1. 예상 질문 표

| # | 예상 질문 | 30초 답 | 근거(파일) | 보여줄 화면·데모 |
|---|---|---|---|---|
| a | "AI 대화 평가 통과율이 58%(r5)인데 데모에서 엉뚱한 칸이 들어가지 않나?" | 58%(r5 21/36)는 9/27 오전 측정이다 (STATUS.md). 그 뒤 원인을 고쳐 같은 36개 시나리오로 다시 잰 최신 결과(9/27 밤 z3, Qwen)는 32/35(91%), 필수 칸 채움 100%·정확도 99%·지어낸 값 0건, 여러 명 방 6/6이다 (docs/product/evals/simulation-2026-09-27-zen-qwen-z3.md). 앞선 z1은 31/36이었고 (docs/product/evals/simulation-2026-09-27-zen-qwen-z1.md), 실행마다 ±3씩 흔들리는 것은 같은 36개 시나리오를 돌려 범위로 보고한다 (docs/product/evals/simulation-2026-09-27-zen-qwen-z1.md). 엉뚱한 값이 들어가도 공개 전에 네 겹으로 막는다 (README.md). 첫째 말하지 않은 전화·주소·가격은 추출 단계에서 버린다 (README.md). 둘째 틀린 값(자리수 틀린 전화·25시 등)은 저장하지 않고 다시 묻는다 (README.md). 셋째 요약 카드에서 사장님이 최종 확인한다 (docs/product/DECISIONS.md D22). 넷째 여러 명이 있는 방은 전원이 '동의'를 눌러야 다음 단계로 넘어간다 (docs/product/DECISIONS.md D52). | STATUS.md §4, docs/product/evals/simulation-2026-09-27-r5.md, docs/product/evals/simulation-2026-09-27-r6a.md, docs/product/evals/simulation-2026-09-27-zen-qwen-z1.md, docs/product/evals/simulation-2026-09-27-zen-qwen-z3.md, README.md, docs/product/DECISIONS.md (D22·D34·D52), app/services/validate.py | 채팅방 요약 카드 화면을 열고 "엉뚱한 칸이 있으면 여기서 고친 뒤 승인한다"고 말한다 (docs/product/DECISIONS.md D22). 데모는 1:1 방에서 한다 (docs/product/VOICE_QA_REQUIREMENTS.md §8). |
| b | "추출 정확도 87~90%, 합격선 걸침 아닌가?" | 1차 77.3%에 지어낸 값 3건에서 2차 90.2%, 3차 87.1%에 지어낸 값 0건까지 왔다 (docs/product/evals/extraction-2026-09-26.md). 합격선(90%·지어냄 0건)에 걸쳐 있는 것은 인정한다 (STATUS.md). 지어낸 값 0건을 정확도보다 먼저 둔 이유는 없는 전화·가격을 만들어 내면 사장님이 피해를 보기 때문이다 (README.md). 확인 단계는 요약 직전 리뷰어 에이전트가 원문과 카드를 대조하고, 어긋난 값은 고치지 않고 사장님께 묻는다 (docs/product/DECISIONS.md D34). 마지막으로 요약 카드에서 사장님이 확정한다 (docs/product/DECISIONS.md D22). | docs/product/evals/extraction-2026-09-26.md, docs/product/evals/extraction-2026-09-26-r2.md, docs/product/evals/extraction-2026-09-26-r3.md, STATUS.md §4, README.md, docs/product/DECISIONS.md (D22·D34) | 추출 실패 사례표(r3의 e002·e035 같은 긴 첫 메시지 사례)를 열고 "남은 실패는 표현 차이·긴 메시지"라고 말한다 (docs/product/evals/extraction-2026-09-26-r3.md). 데모에서는 한 번에 하나씩 말해 달라고 부탁한다 (docs/product/DECISIONS.md D20). |
| c | "카톡 알림 실제로 가나?" | 문의→사장님 카톡 코드는 배포돼 있고 talk_message 추가 동의와 리프레시 토큰 암호화 저장까지 돼 있다 (STATUS.md). 그러나 9/26 운영 DB에 동의한 계정이 0개라 아직 한 번도 나간 적이 없고 실제 수신은 실측 전이다. 확인 전에는 "채팅방 알림까지 확정, 카톡은 확인 중"이라고만 말한다 (STATUS.md). 확인 절차는 카카오 로그인 후 내가 방장인 방에서 "문의를 카톡으로 받기"에 동의하고 "카톡 알림 켜짐"을 본 뒤 테스트 문의 1건을 보내 서버 기록을 본다 (STATUS.md). 참고로 초대 공유 버튼의 검증 계획은 별도 문서에 있고, 사장님 알림 실수신 확인은 위 절차를 따른다 (docs/hackathon/KAKAO_VERIFICATION_PLAN.md). | STATUS.md §3⑨·§4, docs/hackathon/KAKAO_VERIFICATION_PLAN.md, README.md | 채팅방 "문의 알림" 말풍선을 보여주고 "카톡 수신은 아직 실측 전이라 채팅방 알림까지만 확정"이라고 말한다 (STATUS.md). 동의 화면이 있으면 "문의를 카톡으로 받기" 버튼을 보여준다 (STATUS.md). |
| d | "안드로이드 앱 아닌가? PWA면 네이티브 아니지 않나?" | 네이티브 앱이 아니라 설치형 PWA가 1차 답이며, 네이티브 앱은 나중에 다른 방식으로 낸다고 정해 두었다 (README.md). 홈 화면 설치는 display standalone·아이콘·바로가기로 돼 있다 (static/manifest.json). 오프라인은 대화·로그인·API를 저장하지 않고 화면 이동이 실패할 때만 안내 페이지를 보여준다 (static/sw.js). 9/26 실제 브라우저에서 서비스 워커 동작을 확인했다 (STATUS.md). 푸시 알림은 확인된 근거가 없어 된다고 말하지 않는다 (static/sw.js). 네이티브가 꼭 필요하면 같은 PWA를 그대로 감싸 플레이스토어에 올리는 방식(TWA)이 있지만 아직 계획일 뿐 만들지 않았다고 말한다 (README.md). | README.md, STATUS.md, static/manifest.json, static/sw.js | 휴대폰에서 "앱 설치"를 눌러 홈 화면에 두는 것을 보여준다 (README.md). 오프라인 안내 페이지(/offline.html)를 보여준다 (static/sw.js). |
| e | "목업 아닌가? 실제로 돌아가나?" | 실제 서버 주소는 https://144.24.91.250.sslip.io 이고 랜딩·내 프로젝트·시안 고르기·공개 사이트가 모두 이 주소에서 열린다 (STATUS.md). 실제 생성 사이트는 /site/<id>/ 로 열리고 고른 시안을 그대로 공개한다 (README.md). 문의·예약은 공용 DB에 쌓이고 채팅방 알림과 방장 확정·거절로 이어지는 흐름이다 (docs/product/BOOKING_PLAN.md). 9/26에 요청→2안→공개→문의 접수까지 한 바퀴를 확인했다 (STATUS.md). | STATUS.md §2·§3, README.md, docs/product/BOOKING_PLAN.md | 랜딩 입력→채팅방→시안 3안→공개 사이트→문의 폼 전송→채팅방 알림 순서로 보여준다 (README.md). /design/\<id\>와 /site/\<id\>/ 주소를 주소창에서 보여준다 (STATUS.md). |
| f | "AI가 만든 이미지로 가짜 가게 사진 만드는 것 아닌가?" | 사진은 사장님이 직접 올린 것만 쓰는 것이 원칙이다 (docs/product/DECISIONS.md D36). AI 그림은 추상 배경·선 그림만 표시 없이 쓰고, 실물 느낌 예시 사진은 공용으로 미리 만들어 사장님이 고르면 시안에 넣는다 (docs/product/DECISIONS.md D51). 실물처럼 보이는 그림은 공개 사이트에 반드시 "예시 이미지" 표시를 붙이고 사장님이 실제 사진을 올리면 그 사진이 우선이다 (docs/product/DECISIONS.md D51). 알아볼 수 있는 얼굴·간판 글자·로고·실제 상호는 넣지 않는다 (docs/product/DECISIONS.md D51). | docs/product/DECISIONS.md (D36·D51), README.md | 사진 없는 시안의 "예시 이미지" 표시를 보여준다 (docs/product/DECISIONS.md D51). 사진을 올리면 시안·공개본이 자동 갱신되는 것을 보여준다 (STATUS.md). |
| g | "전화 콜봇은?" | 콜봇은 1:1 방에서만 쓰고 여러 명이 있는 방에서는 쓸 수 없다고 정했다 (docs/product/VOICE_QA_REQUIREMENTS.md §8). 기술 검증은 Twilio 미국 번호(체험 계정)로 하려다 9/27 결정으로 브라우저 통화로 바꿨고, 구현은 통화권·TwiML·WebSocket API와 채팅방 통화 버튼이다 (docs/product/VOICE_QA_REQUIREMENTS.md §8.3). 서버·화면 작업(P-1·P-2)은 끝났고 실통화 5턴 시험(P-4)이 남았다 (docs/product/VOICE_QA_REQUIREMENTS.md §8.5). 한국 번호는 Twilio가 주지 않아 운영 단계에서는 국내 070으로 간다 (docs/product/VOICE_QA_REQUIREMENTS.md §8.4). | docs/product/VOICE_QA_REQUIREMENTS.md §8, docs/product/DECISIONS.md (D11·D24) | 더보기 시트의 "전화로 답하기" 버튼과 1:1이 아닐 때 흐리게 보이는 안내를 보여준다 (docs/product/VOICE_QA_REQUIREMENTS.md §8.2). 무전기 모드(누르고 말하기)를 대신 시연한다 (README.md). |
| h | "비용·확장은?" | 파일에 있는 것만 말한다 (docs/product/COST_MONITORING.md). OCI는 2026-09-25 실측으로 최근 30일과 이번 달 누계가 모두 0.0000 SGD이고 예산 monthly-cost-guard(금액 5)가 걸려 있다 (docs/product/COST_MONITORING.md). 디자인용 유료 모델은 월 $30 한도이며 닿으면 규칙 컨셉으로 자동 전환한다 (docs/product/DECISIONS.md D39). 사용자에게는 돈 대신 무료 횟수(AI 작업 1회: 시안 3회 + 고치기 20회)만 둔다 (docs/product/DECISIONS.md D40). 전화 PoC 비용은 5분 통화에 약 $0.3~1이다 (docs/product/VOICE_QA_REQUIREMENTS.md §8.4). 확장 위험은 NIM 무료 한도로 9/26에 실제 과부하·한도 소진이 있었고 대비 모델 3단(super→ultra→lightning)으로 넘긴 것이다 (README.md). | docs/product/COST_MONITORING.md, docs/product/DECISIONS.md (D16·D39·D40), docs/product/VOICE_QA_REQUIREMENTS.md §8.4, README.md, STATUS.md | 비용 보고서 스크립트 사용법 화면을 보여준다 (docs/product/COST_MONITORING.md). 대비 모델 전환이 적힌 README 표를 보여준다 (README.md). |

## 2. 절대 하지 말 말 목록

- "완벽하게", "100%", "모든 업종", "어떤 말이든 알아듣는다"라고 말하지 않는다 (STATUS.md).
- 최신 수치는 z3 32/35(91%)만 말한다. NVIDIA 공식 측정(r6)은 아직 없다고 말한다 (docs/product/evals/simulation-2026-09-27-zen-qwen-z3.md).
- "카톡 수신 확인됐다", "푸시 알림이 온다"고 말하지 않는다 (STATUS.md).
- "네이티브 안드로이드 앱"이라고 말하지 않고 "설치형 PWA가 1차"라고 말한다 (README.md).
- "영원히 무료"라고 말하지 않고 "베타 기간 무료"라고 말한다 (docs/product/DECISIONS.md D13).
- "AI가 알아서 다 한다"고 말하지 않고 "요약 카드에서 사장님이 최종 확인한다"고 말한다 (docs/product/DECISIONS.md D22).
- 예시 그림을 가리키며 "이 가게 사진"이라고 말하지 않고 "예시 이미지"라고 말한다 (docs/product/DECISIONS.md D51).
- "보안이 완벽하다"고 말하지 않고 파일에 적힌 조치(별도 주소·CSP sandbox·공개 전 검사)만 말한다 (README.md).

## 3. 데모 중 사고 대비

- 서버가 느리면: "지금 AI가 생각 중이네요, 그동안 시안 고르기 화면을 먼저 보여 드릴게요"라고 말하고 /design/\<id\>를 연다 (STATUS.md).
- AI가 엉뚱하게 답하면: "지금 엉뚱한 칸에 들어갔네요, 요약 카드에서 고치고 승인하는 흐름이 바로 이것입니다"라고 말하고 요약 카드를 연다 (docs/product/DECISIONS.md D22).
- 로그인이 막히면: "기본 흐름은 로그인 없이 시작합니다"라고 말하고 랜딩 입력창으로 돌아간다 (STATUS.md).
- 카톡·전화 질문이 나오면: "카톡 실수신은 아직 실측 전이고, 전화는 1:1방 브라우저 통화 PoC까지 돼 있다"고 말하고 채팅방 알림·무전기 모드를 보여준다 (STATUS.md).
