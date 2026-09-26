# 요구사항 엔진 대화 시뮬레이션 성적표 (2026-09-26)

대상 36개 시나리오 · 통과 14/36 · 평균 질문 6.306회 · 지어낸 값 9건(전화·주소·가격 0건) · 평균 IRE 1.0 · 평균 TKQR 0.278

## 시나리오별

| 시나리오 | 채움률 | 정확도 | 지어냄 | 질문 | 중복 | IRE | TKQR | 위반 | 통과 |
|---|---|---|---|---|---|---|---|---|---|
| academy-changes_mind | 1.0 | 0.667 | - | 4 | 0 | 1.0 | 0.181 | 0 | X |
| academy-group | 1.0 | 1.0 | - | 6 | 0 | 1.0 | 0.353 | 0 | O |
| academy-let_ai | 1.0 | 1.0 | - | 8 | 2 | 1.0 | 0.381 | 0 | X |
| academy-talkative | 1.0 | 1.0 | features | 2 | 0 | 1.0 | 0.083 | 0 | X |
| academy-terse | 1.0 | 0.833 | - | 6 | 0 | 1.0 | 0.353 | 0 | X |
| academy-unordered | 1.0 | 1.0 | offerings | 6 | 0 | 1.0 | 0.353 | 0 | X |
| cafe-changes_mind | 1.0 | 1.0 | - | 8 | 0 | 1.0 | 0.249 | 0 | O |
| cafe-group | 1.0 | 0.833 | - | 8 | 0 | 1.0 | 0.336 | 0 | X |
| cafe-let_ai | 1.0 | 1.0 | - | 6 | 0 | 1.0 | 0.4 | 0 | O |
| cafe-talkative | 1.0 | 1.0 | features | 2 | 0 | 1.0 | 0.0 | 0 | X |
| cafe-terse | 1.0 | 1.0 | - | 7 | 0 | 1.0 | 0.343 | 0 | O |
| cafe-unordered | 1.0 | 1.0 | - | 6 | 0 | 1.0 | 0.353 | 0 | O |
| pension-changes_mind | 1.0 | 0.833 | features | 6 | 0 | 1.0 | 0.269 | 0 | X |
| pension-group | 1.0 | 0.833 | - | 6 | 0 | 1.0 | 0.353 | 0 | X |
| pension-let_ai | 1.0 | 1.0 | - | 6 | 0 | 1.0 | 0.417 | 0 | O |
| pension-talkative | 1.0 | 1.0 | target | 1 | 0 | 1.0 | 0.0 | 0 | X |
| pension-terse | 1.0 | 0.833 | - | 7 | 1 | 1.0 | 0.307 | 0 | X |
| pension-unordered | 1.0 | 1.0 | - | 6 | 0 | 1.0 | 0.353 | 0 | O |
| restaurant-changes_mind | 1.0 | 1.0 | - | 7 | 0 | 1.0 | 0.357 | 0 | O |
| restaurant-group | 1.0 | 1.0 | - | 8 | 0 | 1.0 | 0.336 | 0 | O |
| restaurant-let_ai | 1.0 | 1.0 | - | 10 | 4 | 1.0 | 0.381 | 0 | X |
| restaurant-talkative | 1.0 | 1.0 | target | 1 | 0 | 1.0 | 0.0 | 0 | X |
| restaurant-terse | 1.0 | 1.0 | - | 7 | 0 | 1.0 | 0.343 | 0 | O |
| restaurant-unordered | 0.5 | 1.0 | - | 12 | 8 | 1.0 | 0.292 | 0 | X |
| salon-changes_mind | 1.0 | 1.0 | - | 7 | 1 | 1.0 | 0.163 | 0 | X |
| salon-group | 1.0 | 1.0 | - | 7 | 0 | 1.0 | 0.349 | 0 | O |
| salon-let_ai | 1.0 | 1.0 | - | 7 | 1 | 1.0 | 0.4 | 0 | X |
| salon-talkative | 1.0 | 1.0 | features | 1 | 0 | 1.0 | 0.0 | 0 | X |
| salon-terse | 1.0 | 1.0 | - | 7 | 0 | 1.0 | 0.349 | 0 | O |
| salon-unordered | 1.0 | 1.0 | - | 5 | 0 | 1.0 | 0.297 | 0 | O |
| workshop-changes_mind | 1.0 | 0.667 | - | 4 | 0 | 1.0 | 0.181 | 0 | X |
| workshop-group | 1.0 | 1.0 | - | 9 | 1 | 1.0 | 0.344 | 0 | X |
| workshop-let_ai | 1.0 | 1.0 | offerings | 7 | 2 | 1.0 | 0.444 | 0 | X |
| workshop-talkative | 1.0 | 1.0 | features | 10 | 0 | 1.0 | 0.0 | 0 | X |
| workshop-terse | 0.833 | 0.8 | - | 11 | 2 | 1.0 | 0.317 | 0 | X |
| workshop-unordered | 1.0 | 1.0 | - | 6 | 0 | 1.0 | 0.353 | 0 | O |

## 유형별 평균

| 유형 | 채움률 | 정확도 | 평균 질문 | IRE | TKQR | 통과율 |
|---|---|---|---|---|---|---|
| changes_mind | 1.0 | 0.861 | 6.0 | 1.0 | 0.233 | 2/6 |
| group | 1.0 | 0.944 | 7.333 | 1.0 | 0.345 | 3/6 |
| let_ai | 1.0 | 1.0 | 7.333 | 1.0 | 0.404 | 2/6 |
| talkative | 1.0 | 1.0 | 2.833 | 1.0 | 0.014 | 0/6 |
| terse | 0.972 | 0.911 | 7.5 | 1.0 | 0.335 | 3/6 |
| unordered | 0.917 | 1.0 | 6.833 | 1.0 | 0.333 | 4/6 |

## 업종별 평균

| 업종 | 채움률 | 정확도 | 평균 질문 | IRE | TKQR | 통과율 |
|---|---|---|---|---|---|---|
| academy | 1.0 | 0.917 | 5.333 | 1.0 | 0.284 | 1/6 |
| cafe | 1.0 | 0.972 | 6.167 | 1.0 | 0.28 | 4/6 |
| pension | 1.0 | 0.916 | 5.333 | 1.0 | 0.283 | 2/6 |
| restaurant | 0.917 | 1.0 | 7.5 | 1.0 | 0.285 | 3/6 |
| salon | 1.0 | 1.0 | 5.667 | 1.0 | 0.26 | 3/6 |
| workshop | 0.972 | 0.911 | 7.833 | 1.0 | 0.273 | 1/6 |

## 합격선 대비 (PLAN §4.1, 질문 상한은 §7 v2=8회 병기)

| 지표 | 합격선 | 이번 결과 | 판정 |
|---|---|---|---|
| 필수 칸 채움률 | 95% 이상 | 98.1% | O |
| 정확도 | 95% 이상 | 95.3% | O |
| 지어낸 값 | 0개 (전화·주소·가격 1건이면 불합격) | 9건 | X |
| 질문 수 | 평균 3회 이하, 최대 5회 (§7 v2: 최대 8회) | 평균 6.306회, 최대 12회 | X |
| 중복 질문 | 0회 | 22회 | X |
| 규칙 위반 | 0회 | 0회 | O |

## 틀린 칸 (정확도 미달·지어냄)

| 시나리오 | 칸 | 기대 | 실제 | 상태 |
|---|---|---|---|---|
| academy-changes_mind | offerings | 고등 영어 내신반 | ['고등 내신반'] | filled |
| academy-changes_mind | goal | 상담 신청 늘리기 | 상담은 전화 말고 카톡 채널로 바꿔주세요 | filled |
| academy-talkative | features | (근거 없음) | ['전화로 상담 받기'] | filled |
| academy-terse | offerings | 중등 수학 반 | ['중등 수학'] | filled |
| academy-unordered | offerings | (근거 없음) | ['개인반 수업', '피아노 그룹반'] | filled |
| cafe-group | contact_method | 카카오톡 채널 | 전화 | filled |
| cafe-talkative | features | (근거 없음) | ['카카오톡 채널로 연락 받기'] | filled |
| pension-changes_mind | offerings | 객실 3개 | ['연락은 전화 말고 카카오톡 채널로 바꿔주세요', '3개'] | filled |
| pension-changes_mind | features | (근거 없음) | ['전화로 예약 받기'] | filled |
| pension-group | offerings | 객실 6개 | ['6개'] | filled |
| pension-talkative | target | (근거 없음) | ['가족 여행객'] | filled |
| pension-terse | offerings | 객실 3개 | ['3개'] | filled |
| restaurant-talkative | target | (근거 없음) | ['전주 한옥마을 근처 방문객'] | filled |
| salon-talkative | features | (근거 없음) | ['네이버 예약 연동'] | filled |
| workshop-changes_mind | hours | 토, 일 10~18시 | 주말 | filled |
| workshop-changes_mind | goal | 수업 신청 받기 | 수업 시간은 주말로 바꿔주세요 | filled |
| workshop-let_ai | offerings | (근거 없음) | ['캔들 만들기'] | filled |
| workshop-talkative | features | (근거 없음) | ['카카오톡 채널로 신청 받기'] | filled |
| workshop-terse | offerings | 가죽 카드지갑 클래스 | 원데이 클래스 | assumed |

## 실패 대화 전문 (최대 3개)

### academy-changes_mind

- **사장님**: 영어 학원 사이트요. 고등 내신반 있고 차량 운행 안내도 넣고 전화로 상담 받으려구요.
- **엔진**: 해당되는 것을 모두 골라 주세요. 사이트에 안내해 드릴게요. [차량 운행 · 체험 수업 · 보강 · 없음] (질문 1)
- **사장님**: 차량 운행, 체험 수업
- **엔진**: 가게 이름이 무엇인가요? 1) 알아서 해주세요 (질문 2)
- **사장님**: 차량 운행 안내는 빼주세요
- **엔진**: 주로 어떤 학생을 가르치시나요? 1) 초등학생  2) 중·고등학생  3) 성인  4) 알아서 해주세요 (질문 3)
- **사장님**: 알아서 해주세요
- **엔진**: 사이트로 가장 이루고 싶은 것은 무엇인가요? 1) 상담 신청 늘리기  2) 학원 알리기  3) 시간표·수업 안내  4) 알아서 해주세요 (질문 4)
- **사장님**: 상담은 전화 말고 카톡 채널로 바꿔주세요
- **사장님**: 가게 이름는 합격영어 학원예요. 고쳐 주세요.
- **사장님**: 대상는 고등학생예요. 고쳐 주세요.

채점: {"scenario_id": "academy-changes_mind", "fill_rate": 1.0, "accuracy": 0.667, "mismatches": [{"slot": "offerings", "expected": "고등 영어 내신반", "got": ["고등 내신반"], "status": "filled"}, {"slot": "goal", "expected": "상담 신청 늘리기", "got": "상담은 전화 말고 카톡 채널로 바꿔주세요", "status": "filled"}], "invented": [], "critical_invented": [], "questions": 4, "max_questions": 8, "duplicates": 0, "ire": 1.0, "tkqr": 0.181, "violations": [], "confirmed": false, "turns": 7, "passed": false}

### academy-let_ai

- **사장님**: 학원 하는데 알아서 해주세요. 반 구성 같은 건 뭘 넣어야 할지 모르겠어요.
- **엔진**: 가게 이름이 무엇인가요? 1) 알아서 해주세요 (질문 1)
- **사장님**: 푸른솔 수학학원
- **엔진**: 주로 어떤 학생을 가르치시나요? 1) 초등학생  2) 중·고등학생  3) 성인  4) 알아서 해주세요 (질문 2)
- **사장님**: 잘 모르겠어요
- **엔진**: 주로 어떤 학생을 가르치시나요? 1) 초등학생  2) 중·고등학생  3) 성인  4) 알아서 해주세요 (질문 2)
- **사장님**: 잘 모르겠어요
- **엔진**: 주로 어떤 학생을 가르치시나요? 1) 초등학생  2) 중·고등학생  3) 성인  4) 알아서 해주세요 (질문 2)
- **사장님**: 잘 모르겠어요
- **엔진**: 해당되는 것을 모두 골라 주세요. 사이트에 안내해 드릴게요. [차량 운행 · 체험 수업 · 보강 · 없음] (질문 3)
- **사장님**: 보강
- **엔진**: 어떤 것을 소개하고 싶으세요? 1) 알아서 해주세요 (질문 4)
- **사장님**: 알아서 해주세요
- **엔진**: 상담 신청은 어떻게 받으시나요? 1) 전화  2) 카카오톡 채널  3) 방문 상담  4) 알아서 해주세요 (질문 5)
- **사장님**: 전화
- **엔진**: 사이트로 가장 이루고 싶은 것은 무엇인가요? 1) 상담 신청 늘리기  2) 학원 알리기  3) 시간표·수업 안내  4) 알아서 해주세요 (질문 6)
- **사장님**: 알아서 해주세요
- **사장님**: 확정합니다

채점: {"scenario_id": "academy-let_ai", "fill_rate": 1.0, "accuracy": 1.0, "mismatches": [], "invented": [], "critical_invented": [], "questions": 8, "max_questions": 8, "duplicates": 2, "ire": 1.0, "tkqr": 0.381, "violations": [], "confirmed": true, "turns": 9, "passed": false}

### academy-talkative

- **사장님**: 목동 근처에서 슬기영어 학원 해요. 초등학생 가르치고 저학년반 고학년반 있어요. 한 달 18만원이고 소수 정원이에요. 수업은 평일 3시부터 9시까지고, 상담 신청이 늘었으면 해요. 전화로 상담 받고 반 구성이랑 시간표 넣고 싶어요.
- **엔진**: 해당되는 것을 모두 골라 주세요. 사이트에 안내해 드릴게요. [차량 운행 · 체험 수업 · 보강 · 없음] (질문 1)
- **사장님**: 형제 할인, 체험 수업
- **엔진**: 상담 신청은 어떻게 받으시나요? 1) 전화  2) 카카오톡 채널  3) 방문 상담  4) 알아서 해주세요 (질문 2)
- **사장님**: 전화
- **사장님**: 반 구성는 초등 영어 반 (저학년, 고학년)예요. 고쳐 주세요.
- **사장님**: 확정합니다

채점: {"scenario_id": "academy-talkative", "fill_rate": 1.0, "accuracy": 1.0, "mismatches": [], "invented": [{"slot": "features", "values": ["전화로 상담 받기"]}], "critical_invented": [], "questions": 2, "max_questions": 8, "duplicates": 0, "ire": 1.0, "tkqr": 0.083, "violations": [], "confirmed": true, "turns": 4, "passed": false}

