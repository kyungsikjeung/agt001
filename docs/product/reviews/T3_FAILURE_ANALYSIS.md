# T3 대화 평가 실패 분석 (성적표 2026-09-26, 34개 중 10개 통과)

- 자료: docs/product/evals/simulation-2026-09-26.md, evals/run_simulation.py, evals/sim_owner.py, evals/scenarios/*.json, app/services/prd_engine.py, app/services/prd_schema.py, docs/product/evals/extraction-2026-09-26-r3.md
- 전체 수치: 통과 10/34, 평균 질문 5.912회, 지어낸 값 9건(전화·주소·가격 0건), 중복 15회, 평균 IRE 1.0, 평균 TKQR 0.276, 위반 0회, 채움률 100%
- 통과 10개: academy-changes_mind, academy-let_ai, cafe-let_ai, pension-group, pension-terse, restaurant-let_ai, salon-let_ai, workshop-changes_mind, workshop-let_ai, workshop-unordered
- 실패 24개: 아래 묶음에 전부 들어간다(겹침 있음). 대화 발췌는 성적표에 전문이 있는 3개에서만 인용한다.
- 코드 수정 없음. 이 파일만 새로 쓴다.

## 0. 먼저 볼 사실 4가지

1. 통과식은 `채움률 0.95 이상 and 정확도 0.95 이상 and 지어냄 없음 and 질문수 <= max_q(8) and 중복 0 and 위반 없음`이다 (run_simulation.py score_dialogue). IRE·TKQR은 참고 지표이며 통과식과 무관하다.
2. 필수 칸이 보통 6개 + 숨은 항목 질문 1개라서, 빈 상태에서 시작하면 정상 진행만으로 6~7 질문이 나온다. 합격선 "평균 3회 이하, 최대 5회"는 이 구조와 처음부터 맞지 않는다. required가 3개인 let_ai만 5/6 통과한 것이 증거다.
3. 사실표 전체에 features 키가 하나도 없고, required에 features가 들어간 시나리오도 없다. target도 pension·restaurant·cafe·salon·workshop talkative 중 일부는 사실표에 키 자체가 없다. 엔진이 이 칸들을 FILLED로 채우면 지어냄 판정을 피하기 어렵다.
4. 시나리오 폴더에는 JSON이 36개 있는데 성적표는 34개다. cafe-unordered와 restaurant-unordered가 성적표에 없다. 건너뜀 사유 기록이 없어서 완전성에 의문이 남는다.

## 1. 실패 24개 묶음

### G1. 정확도 미달 (19건)

- 해당: academy-talkative(0.667), academy-unordered(0.833), cafe-changes_mind(0.667), cafe-group(0.5), cafe-talkative(0.667), cafe-terse(0.5), pension-talkative(0.667), pension-unordered(0.667), restaurant-changes_mind(0.667), restaurant-group(0.333), restaurant-talkative(0.667), restaurant-terse(0.667), salon-changes_mind(0.5), salon-group(0.5), salon-talkative(0.667), salon-terse(0.667), salon-unordered(0.333), workshop-talkative(0.667), workshop-terse(0.833)
- 정확도 1.0인데 다른 사유로 떨어진 5건은 여기 제외: academy-group, academy-terse, pension-changes_mind, pension-let_ai, workshop-group
- 발췌 1 (academy-talkative, 정확도 0.667, 확정 실패):
  - 사장님 첫 메시지: "목동 근처에서 슬기영어 학원 해요. 초등학생 가르치고 저학년반 고학년반 있어요. 한 달 18만원이고 소수 정원이에요. 수업은 평일 3시부터 9시까지고, 상담 신청이 늘었으면 해요. 전화로 상담 받고 반 구성이랑 시간표 넣고 싶어요."
  - 엔진은 숨은 항목 1문 + 가게 이름 1문만 묻고 끝났다(질문 2회). 이후 "반 구성는 초등 영어 반 (저학년, 고학년)예요. 고쳐 주세요."가 두 번 반복되고 확정 없이 끝났다. 채점: accuracy 0.667, questions 2, tkqr 0.083, confirmed false.
- 발췌 2 (academy-terse, 정확도 1.0이지만 중복으로 실패, G3과 겹침):
  - "어떤 것을 소개하고 싶으세요? 1) 알아서 해주세요 (질문 4)"에 "중등 수학 반"이라 답했는데도 같은 질문이 (질문 5)로 반복됐다. 이후 "알아서 해주세요"가 아니라면 채워졌어야 할 답이 증발한 셈이다.
- 원인 판정: 1차 엔진 결함. 추출 오분류(T2 추출 평가에서도 offerings 77.4%, target 63.6%로 가장 낮음: 메뉴+가격 뭉침, 대상·품목·목적 혼동)와 수정 발화 미반영이 겹친다. 2차 채점·시나리오. 수정 기회가 최대 2회로 고정이라 틀린 칸이 3개 이상이면 확정 단계에서 다 못 고친다.

### G2. 지어냄 판정 (8개 시나리오, 9건)

- 해당: academy-unordered(offerings), cafe-changes_mind(offerings), cafe-group(offerings), cafe-talkative(offerings), cafe-terse(offerings), pension-changes_mind(features), pension-talkative(target, features), restaurant-talkative(target)
- 전화·주소·가격은 0건이다. 전부 offerings·target·features다.
- 성적표에 이 8개의 대화 전문이 없어서 값 단위 인용은 못 한다. 사례별 진짜/오판 판정은 §4에서 다룬다.
- 원인 판정: 1차 엔진 결함(오분류·불필요 칸 채움), 2차 시나리오·채점 설계. 사실표에 없는 칸을 채우도록 엔진이 열려 있고, 채점은 대화 전체에 근거 문자열이 없으면 지어냄으로 센다. 특히 features는 사실표 키가 전무해서 채우면 거의 자동으로 지어냄이 된다.

### G3. 중복 질문 (9개 시나리오, 15회)

- 해당: academy-group 1, academy-terse 1, pension-changes_mind 1, pension-let_ai 2, restaurant-group 2, salon-changes_mind 4, salon-group 2, salon-unordered 1, workshop-group 1
- 발췌 (academy-group, 정확도 1.0·채움률 1.0인데 중복 1로 실패):
  - "(질문 4) 어떤 것을 소개하고 싶으세요?" → "초등 미술반" → "(질문 5) 어떤 것을 소개하고 싶으세요?" → "알아서 해주세요". 답한 칸을 그대로 다시 물었다. 채점: accuracy 1.0, questions 7, duplicates 1, passed false.
- 원인 판정: 엔진 결함 + 채점 규칙 불일치. 개방형 질문(offerings처럼 선택지가 "알아서 해주세요"뿐인 칸)은 추출에 의존하는데, 짧은 답이 다른 칸으로 오분류되거나 근거 판정에서 떨어지면 pending이 그대로 남아 같은 질문이 나간다. 엔진의 stuck·same-question 재시도 설계와 채점의 "중복 0" 합격선이 정면 충돌한다. salon-changes_mind(중복 4, 질문 10)는 이 고리가 가장 심한 사례다.

### G4. 질문 수 상한 초과 (2건이 max 8 초과, 평균은 suite 차원 실패)

- 해당: salon-changes_mind 10회, workshop-talkative 9회 (max_questions 8)
- suite 차원: 평균 5.912회라 "평균 3회 이하" 미달. 유형별 changes_mind 7.0, group 7.0, let_ai만 6.167이 아니라 required 3개 덕에 통과가 난다.
- 원인 판정: 채점 규칙이 현재 설계와 안 맞는다. D20 예산 8 + 종류별 예산 + 기능 확인 보너스(최대 +4, 예산이 12까지 늘어남)인데 합격선은 평균 3·최대 5(§7 v2 병기 최대 8)다. 빈 시작 6필수+숨김 1 구조에서 평균 3은 정상 엔진으로도 불가능하다. per-시나리오 통과식은 max 8이라 2건만 직접 떨어지지만, suite 판정은 구조적으로 실패한다.

### G5. talkative 조기 종료·미확정 (5건, G1·G6과 겹침)

- 해당: academy-talkative(2문), cafe-talkative(2문), pension-talkative(1문), restaurant-talkative(1문), salon-talkative(1문). workshop-talkative는 반대(9문)로 별도.
- 공통점: 첫 메시지에 정보가 몰려 있는데 엔진이 1~2문만 묻고 끝났다. TKQR 0~0.083, 정확도 0.667.
- 발췌 (academy-talkative): 질문 2회 후 수정 발화 2회 반복, confirmed false, turns 5. "고쳐 주세요"를 엔진이 두 번 다 못 받아먹었다.
- 원인 판정: 1차 엔진 결함. 첫 메시지 다량 추출이 빗나가면(표기 변형·칸 오분류) 이후 질문이 너무 적어 만회 기회가 없다. 확정 단계 수정 발화도 같은 추출 경로를 타서 실패가 반복된다. 2차 가짜 사장님 문구 문제: 수정 발화가 `라벨 + "는"` 고정이라 "반 구성는" 같은 어색한 말이 나온다(run_simulation.py _find_corrections). 사람 말투가 아니라 추출이 더 못 알아들을 수 있다.

### G6. TKQR 낮음 (talkative 유형 평균 0.014, 전체 평균 0.276)

- 해당: talkative 6건이 주도. workshop-talkative는 질문 9회인데 TKQR 0.0이다.
- 원인 판정: 채점 규칙이 설계와 안 맞는다. TKQR은 required 각 칸의 첫 질문 순번으로 재는데, 첫 메시지로 이미 채운 칸은 다시 묻지 않으므로 기여 0이 된다. 잘한 추출일수록 TKQR이 깎인다. workshop-talkative(9문·TKQR 0)는 required가 아닌 질문(숨김·기능·확인 등)으로 턴을 쓴 사례로 보인다. TKQR은 통과식과 무관한 참고 지표라 직접 실패 사유는 아니다.

### 묶음 요약표

| 묶음 | 건수 | 시나리오 id |
|---|---|---|
| G1 정확도 미달 | 19 | academy-talkative, academy-unordered, cafe-changes_mind, cafe-group, cafe-talkative, cafe-terse, pension-talkative, pension-unordered, restaurant-changes_mind, restaurant-group, restaurant-talkative, restaurant-terse, salon-changes_mind, salon-group, salon-talkative, salon-terse, salon-unordered, workshop-talkative, workshop-terse |
| G2 지어냄 | 8개 시나리오 9건 | academy-unordered, cafe-changes_mind, cafe-group, cafe-talkative, cafe-terse, pension-changes_mind, pension-talkative(2건), restaurant-talkative |
| G3 중복 | 9개 시나리오 15회 | academy-group, academy-terse, pension-changes_mind, pension-let_ai, restaurant-group, salon-changes_mind, salon-group, salon-unordered, workshop-group |
| G4 질문 상한 초과 | 2 | salon-changes_mind(10), workshop-talkative(9) |
| G5 talkative 조기 종료 | 5 | academy-talkative, cafe-talkative, pension-talkative, restaurant-talkative, salon-talkative |
| G6 TKQR 낮음 | talkative 6 주도 | academy-talkative, cafe-talkative, pension-talkative, restaurant-talkative, salon-talkative, workshop-talkative |

## 2. 원인 판정 (엔진 / 채점 / 가짜 사장님)

### 엔진 결함

1. 개방형 칸(offerings) 반복 질문: 선택지가 "알아서 해주세요"뿐이라 추출 실패가 곧 재질문이다. academy-group·terse 전문에서 동일 질문이 연속으로 나갔다. G3의 직접 원인.
2. 수정 발화 미반영: "반 구성는 ... 고쳐 주세요"를 두 번 받고도 카드가 안 고쳐졌다(academy-talkative). 확정 단계가 같은 추출 경로라 실패가 반복된다. G1·G5의 직접 원인.
3. 칸 오분류: T2 추출 평가와 같은 패턴(가격 딸린 메뉴 뭉침, 대상·품목·목적 혼동, 이름·업종 혼동). G1 정확도와 G2 offerings·target의 1차 원인.
4. 묻지도 사실표에도 없는 칸 채움: target·features를 FILLED로 두면 지어냄이 된다. pension·restaurant talkative가 해당한다. 리뷰어(review)는 시뮬 경로에서 호출되지 않으므로(run_dialogue에 review 호출 없음), 원인은 턴 내 추출·정규화·저장 쪽이다.
5. talkative 첫 메시지 처리: 많이 말한 첫 턴을 제대로 못 먹으면 이후 질문이 1~2개로 끝나 만회가 없다. 반대로 workshop-talkative는 9문이나 묻고 TKQR 0이라 required가 아닌 곳에 예산을 쓴 것으로 보인다.

### 채점 규칙이 현재 설계와 안 맞음

1. 질문 합격선 vs D20·required 구조: 평균 3·최대 5(병기 최대 8) vs 예산 8(+기능 보너스 최대 4)·필수 6+숨김 1. 정상 진행만으로 6~7문이니 suite 판정은 구조적 실패다. per-시나리오 통과식(max 8)은 그나마 정합적이라 직접 낙제는 salon-changes_mind·workshop-talkative 2건뿐이다.
2. 중복 정의 vs 재시도 설계: stuck·same-question 재묻기는 엔진 설계인데 채점은 1회라도 있으면 탈락이다. 짧은 실패 답·구어체·멤버 엇갈림이 많은 terse·group·changes에서 반복된다.
3. TKQR 정의 vs 좋은 추출: 이미 채운 칸을 안 묻는 것이 정답인데 점수는 0점을 준다. talkative가 구조적으로 깎인다. 통과식 무관이라 참고 지표로만 볼 일이다.
4. 지어냄 정의 vs 사실표: features처럼 사실표 키가 없는 칸은 채우는 순간 지어냄이 된다. 표기 변형(예: "바비큐장" vs "바비큐·취사")도 문자열 미포함이면 지어냄이다. 진짜 지어냄과 표기 차이를 가르는 관대화가 없다.
5. 수정 기회 2회 고정: 틀린 칸이 3개 이상이면 확정 단계에서 다 못 고친다(restaurant-group 정확도 0.333 같은 사례).

### 가짜 사장님(sim_owner·하네스) 문제

1. 수정 발화 조사 고정: `f"{label}는 {want}예요. 고쳐 주세요."`라서 "반 구성는"처럼 어색해진다. 추출 실패를 키울 수 있는 하네스 문제. 효과는 작다.
2. talkative 이후 답: 규칙상 묻는 것에만 짧게 답한다. live LLM이 선택지 글자 그대로를 안 지키거나 바꿔 말하면 추출이 빗나간다. academy-talkative의 "형제 할인, 체험 수업" 같은 답이 숨김 외 칸으로 새면 이후가 꼬인다.
3. group 비방장: 방장만 아는 사실(owner_decides)을 물으면 "잘 모르겠어요"가 나온다. required에 전화번호는 없지만 상담 방법 의견 충돌(전화 vs 카카오톡 채널)은 정확도를 흔든다.
4. 숨은 항목은 규칙 답변이라 IRE 1.0으로 깨끗하다. 가짜 사장님 쪽은 여기서는 문제가 아니다.
5. 성적표 완전성: 36개 중 34개만 있다. cafe-unordered·restaurant-unordered 누락 사유(건너뜀·오류)가 기록에 없다.

## 3. 고칠 것 표

예상 효과 +N은 겹침이 있어서 합산 불가다. 중복 제거+정확도 수정이 겹치는 시나리오가 많다.

### 엔진

| 순위 | 무엇 | 어디(파일·함수) | 예상 효과(통과 +N) | 위험 |
|---|---|---|---|---|
| 1 | 수정 발화 반영: 확정 단계 "라벨+값+고쳐 주세요"를 추출 실패와 별개 경로로 직접 파싱·적용한다 | app/services/prd_engine.py turn·apply_updates (수정 패턴 정규식 추가) | +3~5 (talkative·changes 계열) | 오수정: 라벨 오탐이 멀쩡한 칸을 덮을 수 있음. 적용 전 _value_matches 수준 확인 필요 |
| 2 | offerings·target·goal 오분류 수정: 추출 프롬프트 칸 정의와 grounded 판정을 T2 실패 패턴(가격 딸린 메뉴, 대상 vs 목적, 이름 vs 업종)에 맞춰 다듬는다 | app/services/prd_engine.py _system_prompt·grounded, app/services/prd_schema.py Slot.describe | +4~6 (정확도·지어냄 동시 개선) | 추출 회귀: 고친 정의가 다른 업종에서 빗나갈 수 있음. T2 60케이스 재측정 필요 |
| 3 | 사실표 없는 칸 채우지 않기: required도 아니고 사실 근거도 없는 target·features를 FILLED로 두지 않는다 | app/services/prd_engine.py apply_updates·finalize | +2 (G2 features·target 제거) | 정보 손실: 사장님이 진짜 말한 요구를 버릴 수 있음. 근거 문자열이 있으면 유지하는 예외 필요 |
| 4 | 중복 재질문 차단: 답한 칸 재질문을 금지하고, stuck 3회 대신 1~2회 만에 가정·자리 표시로 넘긴다 | app/services/prd_engine.py next_question·turn·_ask_next | +5~7 (G3 9개 시나리오) | 성급한 가정: 못 알아들은 답을 가정으로 덮어 정확도가 더 떨어질 수 있음 |
| 5 | 첫 메시지 흡수: 첫 턴 추출로 채운 칸은 묻지 않고 남은 칸만 묻는다. talkative 조기 종료 시 최소 확인 질문을 둔다 | app/services/prd_engine.py turn·next_question | +2~3 (talkative 계열) | 누락: 잘못 채운 칸을 확인 없이 통과시킬 수 있음. 낮은 신뢰 칸만 확인하는 방식 필요 |

### 채점

| 순위 | 무엇 | 어디(파일·함수) | 예상 효과(통과 +N) | 위험 |
|---|---|---|---|---|
| 6 | 질문 합격선-설계 일치: suite 평균 3회 기준을 required 구조(6필수+숨김 1)에 맞게 고치거나, per-시나리오 max 준수율로 바꾼다 | evals/run_simulation.py passed·write_markdown | 판정 정의 변경 (직접 +N은 정의에 따름) | 기준 완화 비판: 숫자만 고치면 품질 신호가 약해짐. 예산·required와 함께 문서로 묶어야 함 |
| 7 | TKQR 보정: 첫 메시지로 이미 채운 칸은 만점 또는 제외로 처리한다 | evals/run_simulation.py score_dialogue (tkqr) | 참고 지표 개선 (통과식 무관이라 +0) | 과거 성적과 단절: 이전 TKQR과 비교 불가 |
| 8 | 지어냄 판정 관대화: 표기 변형(정규화·부분일치)을 허용하고, required 외 칸은 별도 집계한다 | evals/run_simulation.py _value_matches·score_dialogue (invented) | +1~2 (표기 차이 오판 제거) | 진짜 지어냄 은폐: 관대화가 실제 창작을 가릴 수 있음 |

### 시나리오·하네스

| 순위 | 무엇 | 어디(파일·함수) | 예상 효과(통과 +N) | 위험 |
|---|---|---|---|---|
| 9 | features 사실표 정리: 시나리오에 features 사실을 넣거나, 요구하지 않는 칸임을 명시하고 엔진이 채우지 않게 한다 | evals/scenarios/*.json (facts·required·expect) | +2 (G2 features) | 시나리오 손질이 성적 부풀리기로 보일 수 있음. 엔진 3번과 함께 가야 함 |
| 10 | 수정 문구 조사: "는" 고정을 "은/는"으로 바꾼다 | evals/run_simulation.py _find_corrections | +0~1 (미세) | 효과 미미. 그래도 사람 말투에는 맞춘다 |
| 11 | 누락 2개 규명: cafe-unordered·restaurant-unordered가 왜 성적표에 없는지 확인하고 재포함한다 | evals/scenarios, 성적표 생성 과정 | 완전성 (통과수 변동 가능) | 추가 실패가 드러날 수 있음 |

## 4. "지어냄 9건" 사례별 판정

값 문자열이 성적표에 없어서 슬롯·사실표·대화 규칙으로 판정한다. 확정 표시는 ☆(확실), ◇(추정, 전체 로그 확인 필요)다.

| # | 시나리오·칸 | 판정 | 근거 |
|---|---|---|---|
| 1 | academy-unordered offerings ◇ | 실제 오기입 가능성 큼 | 사실 offerings "피아노 개인반, 그룹반". 첫 메시지 "개인반은 한 달 20만원"처럼 가격·시간이 뒤섞인 순서라 가격 딸린 뭉침·시간 오분류가 나기 쉽다. T2 동일 패턴(e013·e025)이 있다. transcript에 없는 값이면 리뷰어가 아닌 턴 추출의 오분류다. |
| 2 | cafe-changes_mind offerings ◇ | 실제 오기입 가능성 큼 | 사실 "아메리카노, 라떼". changes 패치(상담 방법 변경)와 별개로 offerings가 지어냄이라 변경 반영 실패가 아니라 추출·저장 문제다. |
| 3 | cafe-group offerings ◇ | 실제 오기입 가능성 큼 | 사실 "아메리카노, 한라봉차". 공유방이라 비방장 답·의견 충돌이 끼지만 offerings는 의견 대상이 아니라 추출 오분류 쪽이다. |
| 4 | cafe-talkative offerings ◇ | 실제 오기입 가능성 큼 | 사실 "아메리카노, 라떼, 수제청". 첫 메시지에 메뉴가 다 있는데도 지어냄이라, "수제청" 같은 사실값이 카드에서 빠지고 다른 말이 들어간 것으로 보인다. 표기 차이("카페라떼" 등)만이면 지어냄이 아니라 정확도 문제여야 해서, transcript 무근거 값이라는 점에서 오기입 쪽이다. |
| 5 | cafe-terse offerings ◇ | 실제 오기입 가능성 큼 | 첫 메시지 "카페요."라 추출 단서가 없다. 이후 짧은 답들의 칸 귀속이 빗나가면 offerings에 엉뚱한 값이 들어간다. academy-terse 전문의 offerings 증발 패턴과 같은 계열이다. |
| 6 | pension-changes_mind features ☆ | 구조적 오기입 (엔진+시나리오) | 사실표 전체에 features 키가 없다. 카드 features가 FILLED이면 근거가 transcript에만 있어야 하는데, "바비큐장" 같은 말은 sections·숨은 항목이지 기능이 아니라서 슬롯 귀속이 빗나간 것이다. 채점 오판이 아니다. |
| 7 | pension-talkative target ☆ | 실제 지어냄에 가까움 | 이 시나리오 사실표에 target 키가 없다. 카드에 target이 FILLED로 있다는 것 자체가 묻지도 않은 칸을 채운 것이다. transcript에 "가족실·커플실" 언급이 있어도 값 문자열이 없으면 근거가 안 된다. |
| 8 | pension-talkative features ☆ | 구조적 오기입 (엔진+시나리오) | 6번과 동일. 사실 키가 없는데 채워졌다. |
| 9 | restaurant-talkative target ☆ | 실제 지어냄에 가까움 | 이 시나리오 사실표에 target 키가 없다. 첫 메시지에 손님 언급이 없는데 target이 채워졌다면 근거 없는 값이다. 채점 오판이 아니다. |

- 종합: 9건 중 채점 오판으로 볼 만한 것은 없다. 5건의 offerings는 추출 오분류(실제 오기입) 추정, 4건의 target·features는 사실표에 키가 없어서 생긴 구조적 오기입이다. offerings 5건의 최종 확정에는 전체 transcript와 카드 값이 필요하다(성적표에 값 미포함).
- 확인 방법: 각 시나리오의 result transcript와 final_card slots를 덤프해서 invented values와 all_text 대조를 재실행한다. 오프라인 --smoke가 아니라 저장된 live 로그 기준이다.

## 부록

- 34 vs 36: 성적표 34개, 폴더 36개. 빠진 cafe-unordered·restaurant-unordered의 건너뜀 사유를 run_all의 "[건너뜀]" 기록에서 찾는다.
- IRE 1.0 전 시나리오는 숨은 항목 규칙 답변 덕분이라 엔진 성과로 읽기 어렵다. 위반 0회·채움률 100%는 진짜 성과다.
- Claude에게 요청: 없음. 이 분석 범위에서는 소유 파일 외 수정이 필요 없다.

요약: 실패 24건은 정확도 19·지어냄 8시나리오·중복 9시나리오·질문초과 2·talkative 조기종료 5가 겹친 것이고, 1차 원인은 엔진의 offerings 오분류·수정 미반영·재질문이며, 질문 합격선·TKQR·features 사실표는 설계와 채점이 어긋난 것이고, 지어냄 9건은 오판이 아니라 실제 오기입이다. P3 exit 0
