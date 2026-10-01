# 공개 사이트 품질 자동 점검 (2026-10-01)

대상 36쪽(6업종 × 정보 다 줌/거의 안 줌 × 3안), 휴대폰 390×844, 공개본(`publish_choice`). 사진·AI 문구 초안 없음. 실행: `.venv/bin/python -m evals.run_site_quality`

## 문제가 있는 쪽 수

| 항목 | 기준 | 쪽 수 |
|---|---|---|
| 가로 넘침 | 화면보다 넓으면 X | 0/36 |
| 작은 글자 | 14px 미만 글자가 있음 | 0/36 |
| 글자 대비 | WCAG AA(4.5:1, 큰 글자 3:1) 미달 | 0/36 |
| 사진 위 글자 | 첫 화면 사진 덮개 위 글자, CSS로 못 재서 판정 보류(참고, X 아님 — 밝은 사진이면 실측) | 12/36 |
| 누름 칸 크기 | 44×44px 미만 버튼·링크·입력칸 | 0/36 |
| 깨진 그림 | 불러오지 못한 이미지 | 0/36 |
| 빈칸 노출 | 공개본에 `[… 입력]`·'예시' | 0/36 |
| 사실 누락 | 카드의 이름·전화·시간·주소·상품이 화면에 없음 | 0/36 |
| 첫 화면 이름 | 첫 화면에 가게 이름 없음 | 0/36 |
| 첫 화면 행동 | 첫 화면에 문의·전화·예약 버튼 없음 | 0/36 |
| 제목 구조 | h1이 정확히 1개가 아님 | 0/36 |
| 죽은 버튼 | href="#"·빈 href·javascript:·빠진 # id·잘못된 폼, 1개라도 있으면 X | 0/36 (합계 0개) |
| 틀린 번호 | tel:/sms: 숫자가 카드 전화번호와 다름, 1개라도 있으면 X | 0/36 (합계 0개) |
| 모르는 링크 | 외부 링크가 카드 예약·채널·영상 주소가 아님(참고, X 아님) | 18/36 (합계 36개) |
| 누를 것 판정 | 죽은 버튼·틀린 번호가 1개라도 있으면 X | 0/36 |

## 3안 첫 화면 차이 (가장 비슷한 두 안의 픽셀 차이, 0=같음, 8 이상 통과·미만 X)

| 업종-조건 | 최소 차이 | 판정 |
|---|---|---|
| cafe-full | 24.1 | O |
| cafe-min | 27.0 | O |
| restaurant-full | 24.6 | O |
| restaurant-min | 27.0 | O |
| pension-full | 23.7 | O |
| pension-min | 25.7 | O |
| salon-full | 21.0 | O |
| salon-min | 24.5 | O |
| academy-full | 27.1 | O |
| academy-min | 26.1 | O |
| workshop-full | 25.3 | O |
| workshop-min | 27.3 | O |

## 6요소 점수 (D37 매일 회귀)

### 요약 (항목별 통과 쪽 수)

| 항목 | 기준 | 통과 |
|---|---|---|
| 제목 대비(title_ratio) | h1/본문 2.0 이상 | 24/36 |
| 여백 리듬(spacing_steps) | section 상·하 padding 종류 3개 이하 | 36/36 |
| 사진(hero_visual) | 첫 화면 그림 넓이 비율(참고값, 판정 없음) | - |
| 색(color_count) | 유채색 3개 이하 | 36/36 |
| 카드·버튼(cta_shape) | 첫 화면 첫 버튼 높이 48px 이상·둥근 모서리 | 14/36 |
| 첫 화면 한 가지 행동(first_screen_actions) | 행동 버튼 1~2개 | 12/36 |

### 쪽별

| 쪽 | 제목비율 | 여백종류 | 첫화면그림 | 색수 | 버튼모양 | 첫화면행동 |
|---|---|---|---|---|---|---|
| cafe-full-v1 | 2.75 O | 1 O | 0.81 | 0 O | O(52px,999px) | 1 O |
| cafe-full-v2 | 2.75 O | 1 O | 0.39 | 1 O | O(52px,999px) | 1 O |
| cafe-full-v3 | 1.70 X | 2 O | 0.28 | 2 O | X(52px,0px) | 1 O |
| cafe-min-v1 | 2.75 O | 1 O | 0.81 | 0 O | X(44px,999px) | 3 X |
| cafe-min-v2 | 2.75 O | 1 O | 0.44 | 1 O | X(44px,999px) | 3 X |
| cafe-min-v3 | 1.70 X | 2 O | 0.28 | 2 O | O(56px,999px) | 1 O |
| restaurant-full-v1 | 2.75 O | 1 O | 0.81 | 0 O | O(52px,999px) | 1 O |
| restaurant-full-v2 | 2.75 O | 1 O | 0.39 | 1 O | O(52px,999px) | 1 O |
| restaurant-full-v3 | 1.70 X | 2 O | 0.28 | 2 O | X(52px,0px) | 1 O |
| restaurant-min-v1 | 2.75 O | 1 O | 0.81 | 0 O | X(44px,999px) | 3 X |
| restaurant-min-v2 | 2.75 O | 1 O | 0.44 | 1 O | X(44px,999px) | 3 X |
| restaurant-min-v3 | 1.70 X | 2 O | 0.28 | 2 O | O(56px,999px) | 1 O |
| pension-full-v1 | 2.75 O | 1 O | 0.77 | 1 O | X(44px,999px) | 4 X |
| pension-full-v2 | 2.75 O | 1 O | 0.39 | 1 O | X(44px,999px) | 4 X |
| pension-full-v3 | 1.70 X | 2 O | 0.24 | 1 O | O(56px,999px) | 3 X |
| pension-min-v1 | 2.75 O | 1 O | 0.70 | 1 O | X(44px,999px) | 3 X |
| pension-min-v2 | 2.75 O | 1 O | 0.44 | 1 O | X(44px,999px) | 3 X |
| pension-min-v3 | 1.70 X | 2 O | 0.24 | 1 O | O(56px,999px) | 2 O |
| salon-full-v1 | 2.75 O | 1 O | 0.70 | 0 O | X(44px,999px) | 4 X |
| salon-full-v2 | 2.75 O | 1 O | 0.39 | 0 O | X(44px,999px) | 4 X |
| salon-full-v3 | 1.70 X | 2 O | 0.24 | 1 O | O(56px,999px) | 3 X |
| salon-min-v1 | 2.75 O | 1 O | 0.70 | 0 O | X(44px,999px) | 3 X |
| salon-min-v2 | 2.75 O | 1 O | 0.41 | 0 O | X(44px,999px) | 3 X |
| salon-min-v3 | 1.70 X | 2 O | 0.24 | 1 O | O(56px,999px) | 2 O |
| academy-full-v1 | 2.75 O | 1 O | 0.70 | 1 O | X(44px,999px) | 4 X |
| academy-full-v2 | 2.75 O | 1 O | 0.39 | 2 O | X(44px,999px) | 4 X |
| academy-full-v3 | 1.70 X | 2 O | 0.24 | 1 O | O(56px,999px) | 3 X |
| academy-min-v1 | 2.75 O | 1 O | 0.70 | 1 O | X(44px,999px) | 3 X |
| academy-min-v2 | 2.75 O | 1 O | 0.39 | 2 O | X(44px,999px) | 3 X |
| academy-min-v3 | 1.70 X | 2 O | 0.24 | 1 O | O(56px,999px) | 2 O |
| workshop-full-v1 | 2.75 O | 1 O | 0.70 | 1 O | X(44px,999px) | 5 X |
| workshop-full-v2 | 2.75 O | 1 O | 0.39 | 1 O | X(44px,999px) | 4 X |
| workshop-full-v3 | 1.70 X | 2 O | 0.24 | 1 O | O(56px,999px) | 3 X |
| workshop-min-v1 | 2.75 O | 1 O | 0.70 | 1 O | X(44px,999px) | 3 X |
| workshop-min-v2 | 2.75 O | 1 O | 0.44 | 1 O | X(44px,999px) | 3 X |
| workshop-min-v3 | 1.70 X | 2 O | 0.24 | 1 O | O(56px,999px) | 2 O |

## 쪽별

| 쪽 | 넘침 | 작은 글자 | 대비 | 작은 칸 | 깨진 그림 | 빈칸 | 없는 사실 | 첫화면 이름 | 첫화면 버튼 | h1 | 높이 | 죽은 버튼 | 틀린 번호 | 모르는 링크 | 누를 것 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| cafe-full-v1 | - | 0 | 0 | 0 | 0 | - | - | O | O | 1 | 2526 | 0 | 0 | 2 | O |
| cafe-full-v2 | - | 0 | 0 | 0 | 0 | - | - | O | O | 1 | 2652 | 0 | 0 | 2 | O |
| cafe-full-v3 | - | 0 | 0 | 0 | 0 | - | - | O | O | 1 | 2388 | 0 | 0 | 2 | O |
| cafe-min-v1 | - | 0 | 0 | 0 | 0 | - | - | O | O | 1 | 1767 | 0 | 0 | 0 | O |
| cafe-min-v2 | - | 0 | 0 | 0 | 0 | - | - | O | O | 1 | 1832 | 0 | 0 | 0 | O |
| cafe-min-v3 | - | 0 | 0 | 0 | 0 | - | - | O | O | 1 | 1637 | 0 | 0 | 0 | O |
| restaurant-full-v1 | - | 0 | 0 | 0 | 0 | - | - | O | O | 1 | 2526 | 0 | 0 | 2 | O |
| restaurant-full-v2 | - | 0 | 0 | 0 | 0 | - | - | O | O | 1 | 2652 | 0 | 0 | 2 | O |
| restaurant-full-v3 | - | 0 | 0 | 0 | 0 | - | - | O | O | 1 | 2388 | 0 | 0 | 2 | O |
| restaurant-min-v1 | - | 0 | 0 | 0 | 0 | - | - | O | O | 1 | 1767 | 0 | 0 | 0 | O |
| restaurant-min-v2 | - | 0 | 0 | 0 | 0 | - | - | O | O | 1 | 1832 | 0 | 0 | 0 | O |
| restaurant-min-v3 | - | 0 | 0 | 0 | 0 | - | - | O | O | 1 | 1637 | 0 | 0 | 0 | O |
| pension-full-v1 | - | 0 | 0 | 0 | 0 | - | - | O | O | 1 | 3366 | 0 | 0 | 2 | O |
| pension-full-v2 | - | 0 | 0 | 0 | 0 | - | - | O | O | 1 | 4132 | 0 | 0 | 2 | O |
| pension-full-v3 | - | 0 | 0 | 0 | 0 | - | - | O | O | 1 | 3267 | 0 | 0 | 2 | O |
| pension-min-v1 | - | 0 | 0 | 0 | 0 | - | - | O | O | 1 | 2447 | 0 | 0 | 0 | O |
| pension-min-v2 | - | 0 | 0 | 0 | 0 | - | - | O | O | 1 | 3123 | 0 | 0 | 0 | O |
| pension-min-v3 | - | 0 | 0 | 0 | 0 | - | - | O | O | 1 | 2300 | 0 | 0 | 0 | O |
| salon-full-v1 | - | 0 | 0 | 0 | 0 | - | - | O | O | 1 | 3643 | 0 | 0 | 2 | O |
| salon-full-v2 | - | 0 | 0 | 0 | 0 | - | - | O | O | 1 | 3786 | 0 | 0 | 2 | O |
| salon-full-v3 | - | 0 | 0 | 0 | 0 | - | - | O | O | 1 | 3182 | 0 | 0 | 2 | O |
| salon-min-v1 | - | 0 | 0 | 0 | 0 | - | - | O | O | 1 | 2786 | 0 | 0 | 0 | O |
| salon-min-v2 | - | 0 | 0 | 0 | 0 | - | - | O | O | 1 | 2867 | 0 | 0 | 0 | O |
| salon-min-v3 | - | 0 | 0 | 0 | 0 | - | - | O | O | 1 | 2503 | 0 | 0 | 0 | O |
| academy-full-v1 | - | 0 | 0 | 0 | 0 | - | - | O | O | 1 | 3101 | 0 | 0 | 2 | O |
| academy-full-v2 | - | 0 | 0 | 0 | 0 | - | - | O | O | 1 | 3533 | 0 | 0 | 2 | O |
| academy-full-v3 | - | 0 | 0 | 0 | 0 | - | - | O | O | 1 | 3425 | 0 | 0 | 2 | O |
| academy-min-v1 | - | 0 | 0 | 0 | 0 | - | - | O | O | 1 | 2380 | 0 | 0 | 0 | O |
| academy-min-v2 | - | 0 | 0 | 0 | 0 | - | - | O | O | 1 | 2751 | 0 | 0 | 0 | O |
| academy-min-v3 | - | 0 | 0 | 0 | 0 | - | - | O | O | 1 | 2674 | 0 | 0 | 0 | O |
| workshop-full-v1 | - | 0 | 0 | 0 | 0 | - | - | O | O | 1 | 3346 | 0 | 0 | 2 | O |
| workshop-full-v2 | - | 0 | 0 | 0 | 0 | - | - | O | O | 1 | 3473 | 0 | 0 | 2 | O |
| workshop-full-v3 | - | 0 | 0 | 0 | 0 | - | - | O | O | 1 | 3339 | 0 | 0 | 2 | O |
| workshop-min-v1 | - | 0 | 0 | 0 | 0 | - | - | O | O | 1 | 2686 | 0 | 0 | 0 | O |
| workshop-min-v2 | - | 0 | 0 | 0 | 0 | - | - | O | O | 1 | 2751 | 0 | 0 | 0 | O |
| workshop-min-v3 | - | 0 | 0 | 0 | 0 | - | - | O | O | 1 | 2647 | 0 | 0 | 0 | O |

## 세부

- **cafe-full-v1**
  - 누를 것: 모르는 링크 https://map.kakao.com/?q=%EA%B2%BD%EA%B8%B0%20%EC%88%98%EC%9; 모르는 링크 https://map.naver.com/p/search/%EA%B2%BD%EA%B8%B0%20%EC%88%9
- **cafe-full-v2**
  - 누를 것: 모르는 링크 https://map.kakao.com/?q=%EA%B2%BD%EA%B8%B0%20%EC%88%98%EC%9; 모르는 링크 https://map.naver.com/p/search/%EA%B2%BD%EA%B8%B0%20%EC%88%9
- **cafe-full-v3**
  - 누를 것: 모르는 링크 https://map.kakao.com/?q=%EA%B2%BD%EA%B8%B0%20%EC%88%98%EC%9; 모르는 링크 https://map.naver.com/p/search/%EA%B2%BD%EA%B8%B0%20%EC%88%9
- **restaurant-full-v1**
  - 누를 것: 모르는 링크 https://map.kakao.com/?q=%EA%B2%BD%EB%B6%81%20%EA%B2%BD%EC%A; 모르는 링크 https://map.naver.com/p/search/%EA%B2%BD%EB%B6%81%20%EA%B2%B
- **restaurant-full-v2**
  - 누를 것: 모르는 링크 https://map.kakao.com/?q=%EA%B2%BD%EB%B6%81%20%EA%B2%BD%EC%A; 모르는 링크 https://map.naver.com/p/search/%EA%B2%BD%EB%B6%81%20%EA%B2%B
- **restaurant-full-v3**
  - 누를 것: 모르는 링크 https://map.kakao.com/?q=%EA%B2%BD%EB%B6%81%20%EA%B2%BD%EC%A; 모르는 링크 https://map.naver.com/p/search/%EA%B2%BD%EB%B6%81%20%EA%B2%B
- **pension-full-v1**
  - 누를 것: 모르는 링크 https://map.kakao.com/?q=%EA%B0%95%EC%9B%90%20%ED%8F%89%EC%B; 모르는 링크 https://map.naver.com/p/search/%EA%B0%95%EC%9B%90%20%ED%8F%8
- **pension-full-v2**
  - 누를 것: 모르는 링크 https://map.kakao.com/?q=%EA%B0%95%EC%9B%90%20%ED%8F%89%EC%B; 모르는 링크 https://map.naver.com/p/search/%EA%B0%95%EC%9B%90%20%ED%8F%8
- **pension-full-v3**
  - 누를 것: 모르는 링크 https://map.kakao.com/?q=%EA%B0%95%EC%9B%90%20%ED%8F%89%EC%B; 모르는 링크 https://map.naver.com/p/search/%EA%B0%95%EC%9B%90%20%ED%8F%8
- **salon-full-v1**
  - 누를 것: 모르는 링크 https://map.kakao.com/?q=%EA%B2%BD%EA%B8%B0%20%EC%84%B1%EB%8; 모르는 링크 https://map.naver.com/p/search/%EA%B2%BD%EA%B8%B0%20%EC%84%B
- **salon-full-v2**
  - 누를 것: 모르는 링크 https://map.kakao.com/?q=%EA%B2%BD%EA%B8%B0%20%EC%84%B1%EB%8; 모르는 링크 https://map.naver.com/p/search/%EA%B2%BD%EA%B8%B0%20%EC%84%B
- **salon-full-v3**
  - 누를 것: 모르는 링크 https://map.kakao.com/?q=%EA%B2%BD%EA%B8%B0%20%EC%84%B1%EB%8; 모르는 링크 https://map.naver.com/p/search/%EA%B2%BD%EA%B8%B0%20%EC%84%B
- **academy-full-v1**
  - 누를 것: 모르는 링크 https://map.kakao.com/?q=%EA%B2%BD%EA%B8%B0%20%EC%95%88%EC%9; 모르는 링크 https://map.naver.com/p/search/%EA%B2%BD%EA%B8%B0%20%EC%95%8
- **academy-full-v2**
  - 누를 것: 모르는 링크 https://map.kakao.com/?q=%EA%B2%BD%EA%B8%B0%20%EC%95%88%EC%9; 모르는 링크 https://map.naver.com/p/search/%EA%B2%BD%EA%B8%B0%20%EC%95%8
- **academy-full-v3**
  - 누를 것: 모르는 링크 https://map.kakao.com/?q=%EA%B2%BD%EA%B8%B0%20%EC%95%88%EC%9; 모르는 링크 https://map.naver.com/p/search/%EA%B2%BD%EA%B8%B0%20%EC%95%8
- **workshop-full-v1**
  - 누를 것: 모르는 링크 https://map.kakao.com/?q=%EA%B2%BD%EA%B8%B0%20%EA%B3%A0%EC%9; 모르는 링크 https://map.naver.com/p/search/%EA%B2%BD%EA%B8%B0%20%EA%B3%A
- **workshop-full-v2**
  - 누를 것: 모르는 링크 https://map.kakao.com/?q=%EA%B2%BD%EA%B8%B0%20%EA%B3%A0%EC%9; 모르는 링크 https://map.naver.com/p/search/%EA%B2%BD%EA%B8%B0%20%EA%B3%A
- **workshop-full-v3**
  - 누를 것: 모르는 링크 https://map.kakao.com/?q=%EA%B2%BD%EA%B8%B0%20%EA%B3%A0%EC%9; 모르는 링크 https://map.naver.com/p/search/%EA%B2%BD%EA%B8%B0%20%EA%B3%A

## 채팅방 UX 3행 (P2, room.html 직접 읽기, 비용 0원)

| 행 | 장치 | 판정 |
|---|---|---|
| 대기 체감 | 있음 | O |
| 비교 용이 | 있음 | O |
| 신뢰 라벨 | 있음 | O |
