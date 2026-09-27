# 요구사항 엔진 대화 시뮬레이션 성적표 (2026-09-27)

대상 36개 시나리오 · 통과 5/36 · 평균 질문 5.056회 · 지어낸 값 8건(전화·주소·가격 0건) · 평균 IRE 0.833 · 평균 TKQR 0.257

## 시나리오별

| 시나리오 | 채움률 | 정확도 | 지어냄 | 질문 | 중복 | IRE | TKQR | 위반 | 통과 |
|---|---|---|---|---|---|---|---|---|---|
| academy-changes_mind | 1.0 | 0.833 | goal | 4 | 0 | 1.0 | 0.139 | 0 | X |
| academy-group | 1.0 | 0.833 | - | 6 | 0 | 1.0 | 0.353 | 0 | X |
| academy-let_ai | 1.0 | 1.0 | goal,target | 4 | 0 | 1.0 | 0.25 | 0 | X |
| academy-talkative | 1.0 | 1.0 | - | 2 | 0 | 1.0 | 0.0 | 0 | O |
| academy-terse | 0.833 | 1.0 | - | 6 | 0 | 1.0 | 0.353 | 0 | X |
| academy-unordered | 1.0 | 0.5 | - | 4 | 0 | 0.0 | 0.347 | 0 | X |
| cafe-changes_mind | 1.0 | 1.0 | - | 6 | 0 | 1.0 | 0.172 | 0 | O |
| cafe-group | 0.833 | 0.8 | - | 6 | 0 | 1.0 | 0.353 | 0 | X |
| cafe-let_ai | 1.0 | 1.0 | - | 7 | 2 | 1.0 | 0.056 | 0 | X |
| cafe-talkative | 1.0 | 1.0 | features | 2 | 0 | 1.0 | 0.0 | 0 | X |
| cafe-terse | 0.833 | 1.0 | - | 6 | 0 | 1.0 | 0.353 | 0 | X |
| cafe-unordered | 1.0 | 0.833 | - | 4 | 0 | 0.0 | 0.347 | 0 | X |
| pension-changes_mind | 0.833 | 0.6 | goal | 6 | 0 | 1.0 | 0.181 | 0 | X |
| pension-group | 0.833 | 0.8 | - | 6 | 0 | 1.0 | 0.353 | 0 | X |
| pension-let_ai | 1.0 | 1.0 | - | 8 | 2 | 1.0 | 0.417 | 0 | X |
| pension-talkative | 1.0 | 1.0 | - | 2 | 0 | 1.0 | 0.0 | 0 | O |
| pension-terse | 0.833 | 0.8 | - | 6 | 0 | 1.0 | 0.353 | 0 | X |
| pension-unordered | 0.833 | 0.8 | - | 5 | 0 | 0.0 | 0.381 | 0 | X |
| restaurant-changes_mind | 1.0 | 0.833 | - | 5 | 0 | 1.0 | 0.181 | 0 | X |
| restaurant-group | 0.833 | 1.0 | - | 6 | 0 | 1.0 | 0.353 | 0 | X |
| restaurant-let_ai | 1.0 | 1.0 | - | 8 | 2 | 1.0 | 0.381 | 0 | X |
| restaurant-talkative | 1.0 | 1.0 | target | 2 | 0 | 1.0 | 0.0 | 0 | X |
| restaurant-terse | 0.833 | 1.0 | - | 6 | 0 | 1.0 | 0.353 | 0 | X |
| restaurant-unordered | 1.0 | 0.667 | - | 4 | 0 | 0.0 | 0.347 | 0 | X |
| salon-changes_mind | 1.0 | 0.833 | - | 5 | 0 | 1.0 | 0.181 | 0 | X |
| salon-group | 0.833 | 1.0 | - | 6 | 0 | 1.0 | 0.353 | 0 | X |
| salon-let_ai | 1.0 | 1.0 | goal | 7 | 2 | 1.0 | 0.417 | 0 | X |
| salon-talkative | 1.0 | 1.0 | - | 2 | 0 | 1.0 | 0.0 | 0 | O |
| salon-terse | 0.833 | 1.0 | - | 6 | 0 | 1.0 | 0.353 | 0 | X |
| salon-unordered | 1.0 | 0.833 | - | 4 | 0 | 0.0 | 0.347 | 0 | X |
| workshop-changes_mind | 1.0 | 0.833 | goal | 3 | 0 | 1.0 | 0.083 | 0 | X |
| workshop-group | 0.833 | 1.0 | - | 6 | 0 | 1.0 | 0.353 | 0 | X |
| workshop-let_ai | 1.0 | 1.0 | - | 10 | 2 | 1.0 | 0.444 | 0 | X |
| workshop-talkative | 1.0 | 1.0 | - | 2 | 0 | 1.0 | 0.0 | 0 | O |
| workshop-terse | 0.833 | 1.0 | - | 6 | 0 | 1.0 | 0.353 | 0 | X |
| workshop-unordered | 1.0 | 0.667 | - | 4 | 0 | 0.0 | 0.347 | 0 | X |

## 유형별 평균

| 유형 | 채움률 | 정확도 | 평균 질문 | IRE | TKQR | 통과율 |
|---|---|---|---|---|---|---|
| changes_mind | 0.972 | 0.822 | 4.833 | 1.0 | 0.156 | 1/6 |
| group | 0.861 | 0.905 | 6.0 | 1.0 | 0.353 | 0/6 |
| let_ai | 1.0 | 1.0 | 7.333 | 1.0 | 0.328 | 0/6 |
| talkative | 1.0 | 1.0 | 2.0 | 1.0 | 0.0 | 4/6 |
| terse | 0.833 | 0.967 | 6.0 | 1.0 | 0.353 | 0/6 |
| unordered | 0.972 | 0.717 | 4.167 | 0.0 | 0.353 | 0/6 |

## 업종별 평균

| 업종 | 채움률 | 정확도 | 평균 질문 | IRE | TKQR | 통과율 |
|---|---|---|---|---|---|---|
| academy | 0.972 | 0.861 | 4.333 | 0.833 | 0.24 | 1/6 |
| cafe | 0.944 | 0.939 | 5.167 | 0.833 | 0.213 | 1/6 |
| pension | 0.889 | 0.833 | 5.5 | 0.833 | 0.281 | 1/6 |
| restaurant | 0.944 | 0.917 | 5.167 | 0.833 | 0.269 | 0/6 |
| salon | 0.944 | 0.944 | 5.0 | 0.833 | 0.275 | 1/6 |
| workshop | 0.944 | 0.917 | 5.167 | 0.833 | 0.263 | 1/6 |

## 합격선 대비 (PLAN §4.1, 질문 상한은 §7 v2=8회 병기)

| 지표 | 합격선 | 이번 결과 | 판정 |
|---|---|---|---|
| 필수 칸 채움률 | 95% 이상 | 94.0% | X |
| 정확도 | 95% 이상 | 90.2% | X |
| 지어낸 값 | 0개 (전화·주소·가격 1건이면 불합격) | 8건 | X |
| 질문 수 | 평균 3회 이하, 최대 5회 (§7 v2: 최대 8회) | 평균 5.056회, 최대 10회 | X |
| 중복 질문 | 0회 | 10회 | X |
| 규칙 위반 | 0회 | 0회 | O |

## 틀린 칸 (정확도 미달·지어냄)

| 시나리오 | 칸 | 기대 | 실제 | 상태 |
|---|---|---|---|---|
| academy-changes_mind | goal | 상담 신청 늘리기 | 상담 받기 | filled |
| academy-changes_mind | goal | (근거 없음) | ['상담 받기'] | filled |
| academy-group | contact_method | 전화 | 카카오톡 채널 | filled |
| academy-let_ai | goal | (근거 없음) | ['수강 신청 받기'] | filled |
| academy-let_ai | target | (근거 없음) | ['초등학생'] | filled |
| academy-unordered | target | 유치원생, 초등학생 | 가게 이름는 도레미 피아노예요. 고쳐 주세요. | filled |
| academy-unordered | offerings | 피아노 개인반, 그룹반 | ['개인반'] | filled |
| academy-unordered | goal | 상담 신청 늘리기 | 예약·문의 늘리기 | assumed |
| cafe-group | contact_method | 카카오톡 채널 | 전화 | filled |
| cafe-talkative | features | (근거 없음) | ['카카오톡 채널로 문의 받기'] | filled |
| cafe-unordered | hours | 매일 09~22시 | 아침 9시부터 밤 10시 | filled |
| pension-changes_mind | offerings | 객실 3개 | ['3개'] | filled |
| pension-changes_mind | goal | 예약 문의 늘리기 | 예약 받기 | filled |
| pension-changes_mind | goal | (근거 없음) | ['예약 받기'] | filled |
| pension-group | offerings | 객실 6개 | ['6개'] | filled |
| pension-terse | offerings | 객실 3개 | ['3개'] | filled |
| pension-unordered | goal | 펜션 알리기 | 예약·문의 늘리기 | assumed |
| restaurant-changes_mind | goal | 가게 알리기 | 일요일은 쉬는 걸로 바꿔주세요 | filled |
| restaurant-talkative | target | (근거 없음) | ['전주 한옥마을 근처 방문객'] | filled |
| restaurant-unordered | hours | 월~토 11~21시, 일요일 휴무 | 오전 11시부터 밤 9시 | filled |
| restaurant-unordered | contact_method | 네이버 예약 | 전화 | assumed |
| salon-changes_mind | goal | 예약 문의 늘리기 | 예약은 카톡 말고 전화로 바꿔주세요 | filled |
| salon-let_ai | goal | (근거 없음) | ['메뉴판 구성'] | filled |
| salon-unordered | hours | 매일 10~20시 | 오전 10시부터 저녁 8시 | filled |
| workshop-changes_mind | goal | 수업 신청 받기 | 수강 신청 받기 | filled |
| workshop-changes_mind | goal | (근거 없음) | ['수강 신청 받기'] | filled |
| workshop-unordered | offerings | 플라워 원데이 클래스 | ['원데이는'] | filled |
| workshop-unordered | goal | 수업·가격 안내 | 예약·문의 늘리기 | assumed |

## 실패 대화 전문 (최대 3개)

### academy-changes_mind

- **사장님**: 영어 학원 사이트요. 고등 내신반 있고 차량 운행 안내도 넣고 전화로 상담 받으려구요.
- **엔진**: 해당되는 것을 모두 골라 주세요. 사이트에 안내해 드릴게요. [차량 운행 · 체험 수업 · 보강 · 없음] (질문 1)
- **사장님**: 차량 운행, 체험 수업
- **엔진**: 가게 이름이 무엇인가요? 1) 알아서 해주세요 (질문 2)
- **사장님**: 차량 운행 안내는 빼주세요
- **엔진**: 주로 어떤 학생을 가르치시나요? 1) 초등학생  2) 중·고등학생  3) 성인  4) 알아서 해주세요 (질문 3)
- **사장님**: 중·고등학생
- **엔진**: 각 메뉴·시술 가격은 어떻게 되나요? 예: 컷트 2만원, 염색 8만원. 모르면 '나중에 넣을게요'라고 해주세요. 1) 나중에 넣을게요 (질문 4)
- **사장님**: 상담은 전화 말고 카톡 채널로 바꿔주세요
- **사장님**: 가게 이름는 합격영어 학원예요. 고쳐 주세요.
- **사장님**: 반 구성는 고등 영어 내신반예요. 고쳐 주세요.

채점: {"scenario_id": "academy-changes_mind", "fill_rate": 1.0, "accuracy": 0.833, "mismatches": [{"slot": "goal", "expected": "상담 신청 늘리기", "got": "상담 받기", "status": "filled"}], "invented": [{"slot": "goal", "values": ["상담 받기"]}], "critical_invented": [], "questions": 4, "max_questions": 8, "duplicates": 0, "ire": 1.0, "tkqr": 0.139, "violations": [], "confirmed": false, "turns": 7, "passed": false}

### academy-group

- **원장님**: 강사님이랑 같이 학원 사이트 만들려고요.
- **엔진**: 가게 이름이 무엇인가요? 1) 알아서 해주세요 (질문 1)
- **강사**: 알아서 해주세요
- **엔진**: 주로 어떤 학생을 가르치시나요? 1) 초등학생  2) 중·고등학생  3) 성인  4) 알아서 해주세요 (질문 2)
- **원장님**: 초등학생
- **엔진**: 해당되는 것을 모두 골라 주세요. 사이트에 안내해 드릴게요. [차량 운행 · 체험 수업 · 보강 · 없음] (질문 3)
- **강사**: 체험 수업
- **엔진**: 어떤 것을 소개하고 싶으세요? 1) 알아서 해주세요 (질문 4)
- **원장님**: 알아서 해주세요
- **엔진**: 상담 신청은 어떻게 받으시나요? 1) 전화  2) 카카오톡 채널  3) 방문 상담  4) 알아서 해주세요 (질문 5)
- **강사**: 카카오톡 채널
- **엔진**: 사이트로 가장 이루고 싶은 것은 무엇인가요? 1) 상담 신청 늘리기  2) 학원 알리기  3) 시간표·수업 안내  4) 알아서 해주세요 (질문 6)
- **원장님**: 상담 신청 늘리기
- **사장님**: 가게 이름는 색연필 미술학원예요. 고쳐 주세요.
- **사장님**: 반 구성는 초등 미술반예요. 고쳐 주세요.

채점: {"scenario_id": "academy-group", "fill_rate": 1.0, "accuracy": 0.833, "mismatches": [{"slot": "contact_method", "expected": "전화", "got": "카카오톡 채널", "status": "filled"}], "invented": [], "critical_invented": [], "questions": 6, "max_questions": 8, "duplicates": 0, "ire": 1.0, "tkqr": 0.353, "violations": [], "confirmed": false, "turns": 9, "passed": false}

### academy-let_ai

- **사장님**: 학원 하는데 알아서 해주세요. 반 구성 같은 건 뭘 넣어야 할지 모르겠어요.
- **엔진**: 해당되는 것을 모두 골라 주세요. 사이트에 안내해 드릴게요. [차량 운행 · 체험 수업 · 보강 · 없음] (질문 1)
- **사장님**: 보강
- **엔진**: 가게 이름이 무엇인가요? 1) 알아서 해주세요 (질문 2)
- **사장님**: 알아서 해주세요
- **엔진**: 어떤 것을 소개하고 싶으세요? 1) 알아서 해주세요 (질문 3)
- **사장님**: 알아서 해주세요
- **엔진**: 상담 신청은 어떻게 받으시나요? 1) 전화  2) 카카오톡 채널  3) 방문 상담  4) 알아서 해주세요 (질문 4)
- **사장님**: 전화
- **사장님**: 가게 이름는 푸른솔 수학학원예요. 고쳐 주세요.
- **사장님**: 확정합니다

채점: {"scenario_id": "academy-let_ai", "fill_rate": 1.0, "accuracy": 1.0, "mismatches": [], "invented": [{"slot": "goal", "values": ["수강 신청 받기"]}, {"slot": "target", "values": ["초등학생"]}], "critical_invented": [], "questions": 4, "max_questions": 8, "duplicates": 0, "ire": 1.0, "tkqr": 0.25, "violations": [], "confirmed": true, "turns": 6, "passed": false}

