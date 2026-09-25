# T2 추출 평가 결과 (2026-09-26)

## 요약

- 판정: **불합격**
- 칸 정확도: **90.2%** (147/163) — 합격선 90% 이상
- 케이스 통과율: 71.7% (43/60)
- must_not 위반(지어낸 사실): **5건** (5개 케이스) — 0이어야 합격
- 평균 응답 시간: 2.305s, 최대: 21.024s

## 칸별 정확도

| 칸 | 일치/기대 | 정확도 |
|---|---|---|
| business_type | 18/19 | 94.7% |
| contact_method | 14/15 | 93.3% |
| detail | 2/3 | 66.7% |
| exclude | 8/8 | 100.0% |
| goal | 7/8 | 87.5% |
| hours | 15/15 | 100.0% |
| location | 9/9 | 100.0% |
| offerings | 27/31 | 87.1% |
| phone | 11/12 | 91.7% |
| price | 10/14 | 71.4% |
| sections | 6/6 | 100.0% |
| shop_name | 10/12 | 83.3% |
| target | 10/11 | 90.9% |

## 업종별

| 업종 | 케이스 통과 | 칸 정확도 | must_not 위반 |
|---|---|---|---|
| academy | 6/10 (60%) | 21/24 (87.5%) | 1 |
| cafe | 7/10 (70%) | 25/27 (92.6%) | 1 |
| pension | 7/10 (70%) | 23/28 (82.1%) | 1 |
| restaurant | 8/10 (80%) | 28/29 (96.6%) | 1 |
| salon | 7/10 (70%) | 25/29 (86.2%) | 0 |
| workshop | 8/10 (80%) | 25/26 (96.2%) | 1 |

## 실패 사례

| id | 업종 | 사유 | 기대 | 실제 |
|---|---|---|---|---|
| e002 | academy | slot-mismatch | `{"business_type": "학원", "contact_method": "카톡", "offerings": ["영어"], "target": "초등"}` | `{"business_type": ["영어 학원"], "target": ["초등학생"], "contact_method": ["카카오톡"]}` |
| e005 | pension | slot-mismatch | `{"business_type": "펜션", "contact_method": "전화", "detail": "바다가 보여", "goal": "예약 문의", "location": "강릉 경포", "offerings": ["객실"], "phone": "010-0000-1234", "shop_name": "바다정원 펜션"}` | `{"business_type": ["펜션"], "shop_name": ["바다정원"], "location": ["강릉 경포"], "offerings": ["객실 세 개"], "features": ["전화로 받아요"], "phone": ["010-0000-1234"]}` |
| e009 | pension | empty-expect-violated | `{}` | `{"goal": ["알아서 해주세요"]}` |
| e011 | pension | slot-mismatch | `{"contact_method": "전화", "phone": "010-0000-3456"}` | `{"phone": ["공일공에 0000에 3456번"], "contact_method": ["전화"]}` |
| e013 | cafe | slot-mismatch | `{"business_type": "커피", "offerings": ["아메리카노", "라떼"], "price": ["5천원", "6천원"]}` | `{"price": ["아메리카노 5천원, 라떼 6천원"], "offerings": ["아메리카노", "라떼"]}` |
| e016 | cafe | slot-mismatch | `{"business_type": "카페", "shop_name": "작은숲", "target": ["동네 주민", "학생"]}` | `{"business_type": ["카페"], "shop_name": ["작은숲"], "target": ["학생들"]}` |
| e019 | cafe | empty-expect-violated | `{}` | `{"contact_method": ["알아서 해주세요"]}` |
| e025 | restaurant | slot-mismatch | `{"business_type": "칼국수", "contact_method": "전화", "location": "해운대", "offerings": ["칼국수", "수육"], "phone": "010-0000-5678", "price": ["8천원", "2만원"], "shop_name": "할매손 칼국수", "target": "직장인"}` | `{"business_type": ["칼국수"], "shop_name": ["할매손 칼국수"], "target": ["직장인"], "offerings": ["칼국수 8천원", "수육 2만원"], "contact_method": ["전화"], "phone": ["010-0000-5678"], "location": ["부산 해운대구 우동"], "price": ["수육 2만원"]}` |
| e028 | restaurant | empty-expect-violated | `{}` | `{"hours": ["나중에 넣을게요"]}` |
| e033 | salon | slot-mismatch | `{"business_type": "네일", "offerings": ["젤네일"], "price": "5만원"}` | `{"business_type": ["네일"], "price": ["젤네일 5만원부터"]}` |
| e035 | salon | slot-mismatch | `{"business_type": "미용실", "contact_method": "전화", "goal": "예약 문의", "location": "강남", "offerings": ["컷트", "염색"], "phone": "010-0000-7890", "price": ["2만원", "8만원"], "shop_name": "빛나헤어", "target": "20대 여성"}` | `{"business_type": ["미용실"], "shop_name": ["빛나헤어"], "goal": ["예약 문의 늘리기"], "target": ["20대 여성"], "offerings": ["컷트 2만원", "염색 8만원"], "contact_method": ["전화"], "phone": ["010-0000-7890"], "location": ["강남"]}` |
| e036 | salon | slot-mismatch | `{"business_type": "미용실", "offerings": ["파마"], "target": "중년 아주머니"}` | `{"business_type": ["미용실"], "target": ["중년 아주머니"], "detail": ["파마 잘함"]}` |
| e044 | workshop | slot-mismatch | `{"business_type": "공방", "contact_method": "전화", "location": "성수동", "offerings": ["원데이 클래스", "정규반"], "phone": "010-0000-9012", "price": ["3만5천원", "12만원"], "sections": ["수업 안내", "작품 사진"], "shop_name": "손빛 도자기 공방"}` | `{"business_type": ["도자기 공방"], "shop_name": ["손빛 도자기 공방"], "offerings": ["원데이 클래스", "정규반"], "price": ["정규반 달에 12만원"], "contact_method": ["전화"], "phone": ["010-0000-9012"], "sections": ["수업 안내", "작품 사진"], "location": ["성수동"]}` |
| e048 | workshop | empty-expect-violated | `{}` | `{"hours": ["알아서 해주세요"]}` |
| e053 | academy | slot-mismatch | `{"business_type": "수학 학원", "contact_method": "전화", "goal": "상담 신청", "location": "대치동", "offerings": ["중등부", "고등부"], "phone": "010-0000-0123", "price": "20만원", "shop_name": "넘버원"}` | `{"business_type": ["수학 학원"], "location": ["대치동"], "offerings": ["중등부", "고등부"], "price": ["달에 20만원"], "goal": ["상담 신청 늘리기"], "contact_method": ["전화"], "phone": ["010-0000-0123"]}` |
| e056 | academy | slot-mismatch | `{"business_type": "영어 교습소", "offerings": ["파닉스"]}` | `{"business_type": ["영어 학원"], "offerings": ["체험 수업"], "detail": ["파닉스부터 가르쳐요"]}` |
| e058 | academy | empty-expect-violated | `{}` | `{"target": ["알아서 해주세요"]}` |

- e002: 실측 오분류 2: '초등 영어'는 대상·품목이지 사이트 목적이 아님. goal 추출 시 실패
- e005: 긴 첫 메시지: 여러 칸을 한 번에. 말하지 않은 hours 지어내면 실패
- e009: 알아서 해주세요: 빈 기대. 추출이 아무 칸도 내지 않아야 함
- e011: 숫자 말소리 표현(공일공): 전화번호 정규화 확인
- e013: 업종 혼동: '커피'는 업종이지 가게 이름이 아님. 가격 숫자 표현 포함
- e016: 구어체: '그냥', '뭐'. 대상 손님 두 부류
- e019: 알아서 해주세요: 빈 기대. 연락 방법도 추출하면 안 됨
- e025: 긴 첫 메시지: 위치·이름·메뉴·가격·대상·연락 한 번에
- e028: '나중에 넣을게요': 빈 기대. hours 추출 시 실패
- e033: 업종 혼동: '네일'은 업종·품목이지 가게 이름이 아님
- e035: 긴 첫 메시지: 위치·이름·시술·가격·대상·목적·연락 한 번에
- e036: 구어체: '그냥'. 이름·가격·위치 말 안 함
- e044: 긴 첫 메시지: 이름·수업·가격·연락·담을 내용 한 번에
- e048: 알아서 해주세요: 빈 기대. 사실 칸 추출 시 실패
- e053: 긴 첫 메시지: 위치·이름·반·수강료·목적·연락 한 번에
- e056: 구어체: '그냥'. 업종·수업만. 이름 말 안 함
- e058: 알아서 해주세요: 빈 기대. 대상 추출 시 실패

## 응답 시간

- 평균: 2.305s, 최대: 21.024s
