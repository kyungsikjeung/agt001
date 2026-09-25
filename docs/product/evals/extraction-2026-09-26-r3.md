# T2 추출 평가 결과 (2026-09-26)

## 요약

- 판정: **불합격**
- 칸 정확도: **87.1%** (142/163) — 합격선 90% 이상
- 케이스 통과율: 76.7% (46/60)
- must_not 위반(지어낸 사실): **0건** (0개 케이스) — 0이어야 합격
- 평균 응답 시간: 2.184s, 최대: 11.966s

## 칸별 정확도

| 칸 | 일치/기대 | 정확도 |
|---|---|---|
| business_type | 18/19 | 94.7% |
| contact_method | 15/15 | 100.0% |
| detail | 2/3 | 66.7% |
| exclude | 8/8 | 100.0% |
| goal | 7/8 | 87.5% |
| hours | 14/15 | 93.3% |
| location | 7/9 | 77.8% |
| offerings | 24/31 | 77.4% |
| phone | 12/12 | 100.0% |
| price | 12/14 | 85.7% |
| sections | 6/6 | 100.0% |
| shop_name | 10/12 | 83.3% |
| target | 7/11 | 63.6% |

## 업종별

| 업종 | 케이스 통과 | 칸 정확도 | must_not 위반 |
|---|---|---|---|
| academy | 8/10 (80%) | 22/24 (91.7%) | 0 |
| cafe | 8/10 (80%) | 24/27 (88.9%) | 0 |
| pension | 8/10 (80%) | 25/28 (89.3%) | 0 |
| restaurant | 9/10 (90%) | 28/29 (96.6%) | 0 |
| salon | 5/10 (50%) | 19/29 (65.5%) | 0 |
| workshop | 8/10 (80%) | 24/26 (92.3%) | 0 |

## 실패 사례

| id | 업종 | 사유 | 기대 | 실제 |
|---|---|---|---|---|
| e002 | academy | slot-mismatch | `{"business_type": "학원", "contact_method": "카톡", "offerings": ["영어"], "target": "초등"}` | `{"business_type": ["영어 학원"], "target": ["초등학생"], "contact_method": ["카카오톡"]}` |
| e005 | pension | slot-mismatch | `{"business_type": "펜션", "contact_method": "전화", "detail": "바다가 보여", "goal": "예약 문의", "location": "강릉 경포", "offerings": ["객실"], "phone": "010-0000-1234", "shop_name": "바다정원 펜션"}` | `{"business_type": ["펜션"], "shop_name": ["바다정원"], "goal": ["예약 문의 늘리기"], "offerings": ["객실 세 개"], "detail": ["바다가 보이는 객실"], "contact_method": ["전화"], "phone": ["010-0000-1234"], "location": ["강릉 경포"]}` |
| e010 | pension | slot-mismatch | `{"target": "가족 여행객"}` | `{"target": ["아이들이랑 오는 집"]}` |
| e013 | cafe | slot-mismatch | `{"business_type": "커피", "offerings": ["아메리카노", "라떼"], "price": ["5천원", "6천원"]}` | `{"offerings": ["아메리카노 5천원", "라떼 6천원"], "price": ["라떼 6천원"]}` |
| e016 | cafe | slot-mismatch | `{"business_type": "카페", "shop_name": "작은숲", "target": ["동네 주민", "학생"]}` | `{"business_type": ["카페"], "shop_name": ["작은숲"], "target": ["학생"]}` |
| e025 | restaurant | slot-mismatch | `{"business_type": "칼국수", "contact_method": "전화", "location": "해운대", "offerings": ["칼국수", "수육"], "phone": "010-0000-5678", "price": ["8천원", "2만원"], "shop_name": "할매손 칼국수", "target": "직장인"}` | `{"business_type": ["칼국수"], "shop_name": ["할매손 칼국수"], "target": ["직장인"], "offerings": ["칼국수 8천원", "수육 2만원"], "contact_method": ["전화"], "phone": ["010-0000-5678"], "location": ["부산 해운대구 우동"], "price": ["수육 2만원"]}` |
| e033 | salon | slot-mismatch | `{"business_type": "네일", "offerings": ["젤네일"], "price": "5만원"}` | `{"business_type": ["네일샵"], "price": ["젤네일 5만원부터"]}` |
| e035 | salon | slot-mismatch | `{"business_type": "미용실", "contact_method": "전화", "goal": "예약 문의", "location": "강남", "offerings": ["컷트", "염색"], "phone": "010-0000-7890", "price": ["2만원", "8만원"], "shop_name": "빛나헤어", "target": "20대 여성"}` | `{"business_type": ["미용실"], "shop_name": ["빛나헤어"], "price": ["컷트 2만원, 염색 8만원"], "target": ["20대 여성 손님"], "contact_method": ["전화"], "phone": ["010-0000-7890"]}` |
| e036 | salon | slot-mismatch | `{"business_type": "미용실", "offerings": ["파마"], "target": "중년 아주머니"}` | `{"business_type": ["미용실"], "detail": ["파마 잘해요, 특히 중년 아주머니들이 많이 오셔요"]}` |
| e037 | salon | slot-mismatch | `{"hours": ["월요일", "열 시", "여덟 시"]}` | `{"hours": ["오전 열 시부터 저녁 여덟 시까지 해요"]}` |
| e042 | salon | slot-mismatch | `{"location": "홍대", "offerings": ["염색", "클리닉"], "shop_name": "컬러랩"}` | `{"business_type": ["염색 및 클리닉"], "shop_name": ["컬러랩"], "location": ["홍대"]}` |
| e044 | workshop | slot-mismatch | `{"business_type": "공방", "contact_method": "전화", "location": "성수동", "offerings": ["원데이 클래스", "정규반"], "phone": "010-0000-9012", "price": ["3만5천원", "12만원"], "sections": ["수업 안내", "작품 사진"], "shop_name": "손빛 도자기 공방"}` | `{"business_type": ["도자기 공방"], "shop_name": ["손빛 도자기 공방"], "offerings": ["원데이 클래스", "정규반"], "price": ["원데이 클래스 3만5천원, 정규반 월 12만원"], "contact_method": ["전화"], "phone": ["010-0000-9012"], "sections": ["수업 안내", "작품 사진"]}` |
| e045 | workshop | slot-mismatch | `{"business_type": "도자기 공방", "hours": ["수요일", "두 시"], "target": "초보"}` | `{"business_type": ["도자기 공방"], "hours": ["수요일 토요일 두 시부터"]}` |
| e053 | academy | slot-mismatch | `{"business_type": "수학 학원", "contact_method": "전화", "goal": "상담 신청", "location": "대치동", "offerings": ["중등부", "고등부"], "phone": "010-0000-0123", "price": "20만원", "shop_name": "넘버원"}` | `{"business_type": ["수학 학원"], "location": ["대치동"], "offerings": ["중등부", "고등부"], "price": ["달에 20만원"], "goal": ["상담 신청 늘리기"], "contact_method": ["전화"], "phone": ["010-0000-0123"]}` |

- e002: 실측 오분류 2: '초등 영어'는 대상·품목이지 사이트 목적이 아님. goal 추출 시 실패
- e005: 긴 첫 메시지: 여러 칸을 한 번에. 말하지 않은 hours 지어내면 실패
- e010: 목적 vs 대상 혼동: 손님 얘기는 target이지 goal이 아님
- e013: 업종 혼동: '커피'는 업종이지 가게 이름이 아님. 가격 숫자 표현 포함
- e016: 구어체: '그냥', '뭐'. 대상 손님 두 부류
- e025: 긴 첫 메시지: 위치·이름·메뉴·가격·대상·연락 한 번에
- e033: 업종 혼동: '네일'은 업종·품목이지 가게 이름이 아님
- e035: 긴 첫 메시지: 위치·이름·시술·가격·대상·목적·연락 한 번에
- e036: 구어체: '그냥'. 이름·가격·위치 말 안 함
- e037: 휴무일 + 한글 숫자 영업시간
- e042: 순서 없음: 주력 시술·이름·위치 뒤섞인 순서
- e044: 긴 첫 메시지: 이름·수업·가격·연락·담을 내용 한 번에
- e045: 사투리(경상): 업종·대상·수업 시간 한글 숫자
- e053: 긴 첫 메시지: 위치·이름·반·수강료·목적·연락 한 번에

## 응답 시간

- 평균: 2.184s, 최대: 11.966s
