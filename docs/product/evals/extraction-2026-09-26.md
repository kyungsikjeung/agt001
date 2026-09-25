# T2 추출 평가 결과 (2026-09-26)

## 요약

- 판정: **불합격**
- 칸 정확도: **77.3%** (126/163) — 합격선 90% 이상
- 케이스 통과율: 56.7% (34/60)
- must_not 위반(지어낸 사실): **3건** (3개 케이스) — 0이어야 합격
- 평균 응답 시간: 2.604s, 최대: 34.459s

## 칸별 정확도

| 칸 | 일치/기대 | 정확도 |
|---|---|---|
| business_type | 18/19 | 94.7% |
| contact_method | 11/15 | 73.3% |
| detail | 2/3 | 66.7% |
| exclude | 8/8 | 100.0% |
| goal | 8/8 | 100.0% |
| hours | 3/15 | 20.0% |
| location | 9/9 | 100.0% |
| offerings | 23/31 | 74.2% |
| phone | 10/12 | 83.3% |
| price | 9/14 | 64.3% |
| sections | 6/6 | 100.0% |
| shop_name | 10/12 | 83.3% |
| target | 9/11 | 81.8% |

## 업종별

| 업종 | 케이스 통과 | 칸 정확도 | must_not 위반 |
|---|---|---|---|
| academy | 7/10 (70%) | 19/24 (79.2%) | 0 |
| cafe | 8/10 (80%) | 25/27 (92.6%) | 1 |
| pension | 4/10 (40%) | 20/28 (71.4%) | 0 |
| restaurant | 5/10 (50%) | 20/29 (69.0%) | 1 |
| salon | 5/10 (50%) | 21/29 (72.4%) | 0 |
| workshop | 5/10 (50%) | 21/26 (80.8%) | 1 |

## 실패 사례

| id | 업종 | 사유 | 기대 | 실제 |
|---|---|---|---|---|
| e002 | academy | slot-mismatch | `{"business_type": "학원", "contact_method": "카톡", "offerings": ["영어"], "target": "초등"}` | `{"business_type": ["학원"], "offerings": ["초등 영어"], "contact_method": ["카카오톡"]}` |
| e005 | pension | slot-mismatch | `{"business_type": "펜션", "contact_method": "전화", "detail": "바다가 보여", "goal": "예약 문의", "location": "강릉 경포", "offerings": ["객실"], "phone": "010-0000-1234", "shop_name": "바다정원 펜션"}` | `{"business_type": ["펜션"], "shop_name": ["바다정원"], "goal": ["예약 문의 늘리기"], "offerings": ["객실 세 개"], "contact_method": ["전화"], "phone": ["010-0000-1234"], "location": ["강릉 경포"], "detail": ["바다가 보이는 객실"]}` |
| e006 | pension | slot-mismatch | `{"business_type": "펜션", "hours": ["세 시"], "offerings": ["객실"], "phone": "010-0000-2345"}` | `{"business_type": ["펜션"], "offerings": ["객실 2개"], "hours": ["체크인 오후 3시부터"], "phone": ["010-0000-2345"]}` |
| e007 | pension | slot-mismatch | `{"hours": ["오후 세 시", "오전 열한 시"]}` | `{}` |
| e010 | pension | slot-mismatch | `{"target": "가족 여행객"}` | `{"target": ["아이들이랑 오는 집"]}` |
| e011 | pension | slot-mismatch | `{"contact_method": "전화", "phone": "010-0000-3456"}` | `{"contact_method": ["전화"]}` |
| e012 | pension | slot-mismatch | `{"contact_method": "카톡", "location": "양양", "shop_name": "파도소리"}` | `{"location": ["양양"], "shop_name": ["파도소리"], "contact_method": ["카카오톡"]}` |
| e013 | cafe | slot-mismatch | `{"business_type": "커피", "offerings": ["아메리카노", "라떼"], "price": ["5천원", "6천원"]}` | `{"offerings": ["아메리카노 5천원", "라떼 6천원"], "price": ["라떼 6천원"]}` |
| e019 | cafe | empty-expect-violated | `{}` | `{"contact_method": ["알아서 해주세요"]}` |
| e023 | restaurant | slot-mismatch | `{"business_type": "한식당", "offerings": ["김치찌개", "된장찌개"], "price": "9천원"}` | `{"business_type": ["한식당"], "price": ["된장찌개 9천원"]}` |
| e025 | restaurant | slot-mismatch | `{"business_type": "칼국수", "contact_method": "전화", "location": "해운대", "offerings": ["칼국수", "수육"], "phone": "010-0000-5678", "price": ["8천원", "2만원"], "shop_name": "할매손 칼국수", "target": "직장인"}` | `{"business_type": ["칼국수 집"], "shop_name": ["할매손 칼국수"], "phone": ["010-0000-5678"], "location": ["부산 해운대구 우동"], "price": ["칼국수 8천원, 수육 2만원"], "target": ["직장인"], "contact_method": ["전화"]}` |
| e026 | restaurant | slot-mismatch | `{"business_type": "고깃집", "hours": ["다섯 시", "열두 시"], "offerings": ["삼겹살", "목살"]}` | `{"business_type": ["고깃집"], "detail": ["삼겹살이랑 목살이 일품이여"]}` |
| e028 | restaurant | empty-expect-violated | `{}` | `{"hours": ["나중에 넣을게요"]}` |
| e032 | restaurant | slot-mismatch | `{"location": "한옥마을", "phone": "010-0000-6789"}` | `{"phone": ["공일공에 0000에 6789번"], "location": ["전주 한옥마을 근처"]}` |
| e033 | salon | slot-mismatch | `{"business_type": "네일", "offerings": ["젤네일"], "price": "5만원"}` | `{"business_type": ["네일"], "price": ["젤네일 5만원부터"]}` |
| e035 | salon | slot-mismatch | `{"business_type": "미용실", "contact_method": "전화", "goal": "예약 문의", "location": "강남", "offerings": ["컷트", "염색"], "phone": "010-0000-7890", "price": ["2만원", "8만원"], "shop_name": "빛나헤어", "target": "20대 여성"}` | `{"business_type": ["미용실"], "shop_name": ["빛나헤어"], "goal": ["예약 문의 늘리기"], "target": ["20대 여성"], "offerings": ["컷트 2만원", "염색 8만원"], "contact_method": ["전화"], "phone": ["010-0000-7890"], "location": ["강남"]}` |
| e036 | salon | slot-mismatch | `{"business_type": "미용실", "offerings": ["파마"], "target": "중년 아주머니"}` | `{"business_type": ["미용실"], "target": ["중년 아주머니"], "detail": ["파마 잘함"]}` |
| e037 | salon | slot-mismatch | `{"hours": ["월요일", "열 시", "여덟 시"]}` | `{}` |
| e041 | salon | slot-mismatch | `{"contact_method": "카톡", "phone": "010-0000-8901"}` | `{"contact_method": ["카카오톡 채널"], "phone": ["010-0000-8901"]}` |
| e044 | workshop | slot-mismatch | `{"business_type": "공방", "contact_method": "전화", "location": "성수동", "offerings": ["원데이 클래스", "정규반"], "phone": "010-0000-9012", "price": ["3만5천원", "12만원"], "sections": ["수업 안내", "작품 사진"], "shop_name": "손빛 도자기 공방"}` | `{"business_type": ["도자기 공방"], "shop_name": ["손빛 도자기 공방"], "offerings": ["원데이 클래스", "정규반"], "price": ["정규반 달 12만원"], "contact_method": ["전화"], "phone": ["010-0000-9012"], "sections": ["수업 안내", "작품 사진"], "location": ["성수동"]}` |
| e045 | workshop | slot-mismatch | `{"business_type": "도자기 공방", "hours": ["수요일", "두 시"], "target": "초보"}` | `{"business_type": ["도자기 공방"], "target": ["초보"]}` |
| e048 | workshop | empty-expect-violated | `{}` | `{"hours": ["알아서 해주세요"]}` |
| e050 | workshop | slot-mismatch | `{"price": "십이만원"}` | `{}` |
| e051 | workshop | slot-mismatch | `{"contact_method": "카톡"}` | `{"contact_method": ["카카오톡"]}` |
| e053 | academy | slot-mismatch | `{"business_type": "수학 학원", "contact_method": "전화", "goal": "상담 신청", "location": "대치동", "offerings": ["중등부", "고등부"], "phone": "010-0000-0123", "price": "20만원", "shop_name": "넘버원"}` | `{"business_type": ["수학 학원"], "location": ["대치동"], "offerings": ["중등부", "고등부"], "price": ["달에 20만원"], "goal": ["상담 신청 늘리기"], "contact_method": ["전화"], "phone": ["010-0000-0123"]}` |
| e059 | academy | slot-mismatch | `{"hours": ["네 시", "여덟 시"]}` | `{}` |

- e002: 실측 오분류 2: '초등 영어'는 대상·품목이지 사이트 목적이 아님. goal 추출 시 실패
- e005: 긴 첫 메시지: 여러 칸을 한 번에. 말하지 않은 hours 지어내면 실패
- e006: 사투리·구어체(경상): 칸 추출이 방언에 흔들리지 않는지
- e007: 숫자 한글 표현(세 시, 열한 시). 짧은 답과 함께
- e010: 목적 vs 대상 혼동: 손님 얘기는 target이지 goal이 아님
- e011: 숫자 말소리 표현(공일공): 전화번호 정규화 확인
- e012: 순서 없음: 위치·이름·연락이 뒤섞인 순서. 번호 말 안 함
- e013: 업종 혼동: '커피'는 업종이지 가게 이름이 아님. 가격 숫자 표현 포함
- e019: 알아서 해주세요: 빈 기대. 연락 방법도 추출하면 안 됨
- e023: 업종 + 대표 메뉴 + 가격 숫자 표현
- e025: 긴 첫 메시지: 위치·이름·메뉴·가격·대상·연락 한 번에
- e026: 사투리(전라도): 업종·메뉴·영업시간 한글 숫자 표현
- e028: '나중에 넣을게요': 빈 기대. hours 추출 시 실패
- e032: 숫자 말소리 표현(공일공) + 위치. 가격·시간 말 안 함
- e033: 업종 혼동: '네일'은 업종·품목이지 가게 이름이 아님
- e035: 긴 첫 메시지: 위치·이름·시술·가격·대상·목적·연락 한 번에
- e036: 구어체: '그냥'. 이름·가격·위치 말 안 함
- e037: 휴무일 + 한글 숫자 영업시간
- e041: 연락 방법 + 가짜 전화번호. 위치 말 안 함
- e044: 긴 첫 메시지: 이름·수업·가격·연락·담을 내용 한 번에
- e045: 사투리(경상): 업종·대상·수업 시간 한글 숫자
- e048: 알아서 해주세요: 빈 기대. 사실 칸 추출 시 실패
- e050: 가격 한글 숫자 표현(십이만원)
- e051: 짧은 답: '카톡으로요'는 방법이지 번호가 아님
- e053: 긴 첫 메시지: 위치·이름·반·수강료·목적·연락 한 번에
- e059: 수업 시간 한글 숫자 표현(네 시, 여덟 시)

## 응답 시간

- 평균: 2.604s, 최대: 34.459s
