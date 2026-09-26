# 공개 사이트 품질 자동 점검 (2026-09-26)

대상 36쪽(6업종 × 정보 다 줌/거의 안 줌 × 3안), 휴대폰 390×844, 공개본(`publish_choice`). 사진·AI 문구 초안 없음. 실행: `.venv/bin/python -m evals.run_site_quality`

## 문제가 있는 쪽 수

| 항목 | 기준 | 쪽 수 |
|---|---|---|
| 가로 넘침 | 화면보다 넓으면 X | 0/36 |
| 작은 글자 | 14px 미만 글자가 있음 | 0/36 |
| 글자 대비 | WCAG AA(4.5:1, 큰 글자 3:1) 미달 | 0/36 |
| 누름 칸 크기 | 44×44px 미만 버튼·링크·입력칸 | 0/36 |
| 깨진 그림 | 불러오지 못한 이미지 | 0/36 |
| 빈칸 노출 | 공개본에 `[… 입력]`·'예시' | 0/36 |
| 사실 누락 | 카드의 이름·전화·시간·주소·상품이 화면에 없음 | 0/36 |
| 첫 화면 이름 | 첫 화면에 가게 이름 없음 | 0/36 |
| 첫 화면 행동 | 첫 화면에 문의·전화·예약 버튼 없음 | 0/36 |
| 제목 구조 | h1이 정확히 1개가 아님 | 0/36 |

## 3안 첫 화면 차이 (가장 비슷한 두 안의 픽셀 차이, 0=같음, 8 이상 통과·미만 X)

| 업종-조건 | 최소 차이 | 판정 |
|---|---|---|
| cafe-full | 12.3 | O |
| cafe-min | 12.2 | O |
| restaurant-full | 12.9 | O |
| restaurant-min | 14.4 | O |
| pension-full | 5.8 | X |
| pension-min | 5.5 | X |
| salon-full | 7.1 | X |
| salon-min | 8.5 | O |
| academy-full | 7.2 | X |
| academy-min | 8.7 | O |
| workshop-full | 8.1 | O |
| workshop-min | 9.0 | O |

## 6요소 점수 (D37 매일 회귀)

### 요약 (항목별 통과 쪽 수)

| 항목 | 기준 | 통과 |
|---|---|---|
| 제목 대비(title_ratio) | h1/본문 2.0 이상 | 36/36 |
| 여백 리듬(spacing_steps) | section 상·하 padding 종류 3개 이하 | 36/36 |
| 사진(hero_visual) | 첫 화면 그림 넓이 비율(참고값, 판정 없음) | - |
| 색(color_count) | 유채색 3개 이하 | 36/36 |
| 카드·버튼(cta_shape) | 첫 화면 첫 버튼 높이 48px 이상·둥근 모서리 | 36/36 |
| 첫 화면 한 가지 행동(first_screen_actions) | 행동 버튼 1~2개 | 36/36 |

### 쪽별

| 쪽 | 제목비율 | 여백종류 | 첫화면그림 | 색수 | 버튼모양 | 첫화면행동 |
|---|---|---|---|---|---|---|
| cafe-full-v1 | 2.75 O | 1 O | 0.10 | 1 O | O(62px,999px) | 1 O |
| cafe-full-v2 | 2.75 O | 1 O | 0.39 | 1 O | O(62px,999px) | 1 O |
| cafe-full-v3 | 2.75 O | 1 O | 0.00 | 0 O | O(62px,2px) | 1 O |
| cafe-min-v1 | 2.75 O | 1 O | 0.10 | 1 O | O(62px,999px) | 1 O |
| cafe-min-v2 | 2.75 O | 1 O | 0.48 | 1 O | O(62px,999px) | 1 O |
| cafe-min-v3 | 2.75 O | 1 O | 0.00 | 0 O | O(62px,2px) | 1 O |
| restaurant-full-v1 | 2.75 O | 1 O | 0.00 | 1 O | O(62px,999px) | 1 O |
| restaurant-full-v2 | 2.75 O | 1 O | 0.39 | 1 O | O(62px,999px) | 1 O |
| restaurant-full-v3 | 2.75 O | 1 O | 0.00 | 0 O | O(62px,2px) | 1 O |
| restaurant-min-v1 | 2.75 O | 1 O | 0.10 | 1 O | O(62px,999px) | 1 O |
| restaurant-min-v2 | 2.75 O | 1 O | 0.48 | 1 O | O(62px,999px) | 1 O |
| restaurant-min-v3 | 2.75 O | 1 O | 0.00 | 0 O | O(62px,2px) | 1 O |
| pension-full-v1 | 2.75 O | 1 O | 0.09 | 1 O | O(62px,999px) | 1 O |
| pension-full-v2 | 2.75 O | 1 O | 0.39 | 1 O | O(62px,999px) | 1 O |
| pension-full-v3 | 2.75 O | 1 O | 0.00 | 1 O | O(62px,2px) | 1 O |
| pension-min-v1 | 2.75 O | 1 O | 0.09 | 1 O | O(62px,999px) | 1 O |
| pension-min-v2 | 2.75 O | 1 O | 0.48 | 1 O | O(62px,999px) | 1 O |
| pension-min-v3 | 2.75 O | 1 O | 0.00 | 1 O | O(62px,2px) | 1 O |
| salon-full-v1 | 2.75 O | 1 O | 0.00 | 0 O | O(62px,999px) | 1 O |
| salon-full-v2 | 2.75 O | 1 O | 0.41 | 1 O | O(62px,999px) | 1 O |
| salon-full-v3 | 2.75 O | 1 O | 0.00 | 1 O | O(62px,2px) | 1 O |
| salon-min-v1 | 2.75 O | 1 O | 0.10 | 0 O | O(62px,999px) | 1 O |
| salon-min-v2 | 2.75 O | 1 O | 0.48 | 1 O | O(62px,999px) | 1 O |
| salon-min-v3 | 2.75 O | 1 O | 0.00 | 1 O | O(62px,2px) | 1 O |
| academy-full-v1 | 2.75 O | 1 O | 0.00 | 1 O | O(62px,2px) | 1 O |
| academy-full-v2 | 2.75 O | 1 O | 0.41 | 1 O | O(62px,999px) | 1 O |
| academy-full-v3 | 2.75 O | 1 O | 0.00 | 0 O | O(62px,2px) | 1 O |
| academy-min-v1 | 2.75 O | 1 O | 0.10 | 1 O | O(62px,2px) | 1 O |
| academy-min-v2 | 2.75 O | 1 O | 0.48 | 1 O | O(62px,999px) | 1 O |
| academy-min-v3 | 2.75 O | 1 O | 0.00 | 0 O | O(62px,2px) | 1 O |
| workshop-full-v1 | 2.75 O | 1 O | 0.00 | 1 O | O(62px,999px) | 1 O |
| workshop-full-v2 | 2.75 O | 1 O | 0.41 | 1 O | O(62px,999px) | 1 O |
| workshop-full-v3 | 2.75 O | 1 O | 0.00 | 1 O | O(62px,2px) | 1 O |
| workshop-min-v1 | 2.75 O | 1 O | 0.09 | 1 O | O(62px,999px) | 1 O |
| workshop-min-v2 | 2.75 O | 1 O | 0.48 | 1 O | O(62px,999px) | 1 O |
| workshop-min-v3 | 2.75 O | 1 O | 0.00 | 1 O | O(62px,2px) | 1 O |

## 쪽별

| 쪽 | 넘침 | 작은 글자 | 대비 | 작은 칸 | 깨진 그림 | 빈칸 | 없는 사실 | 첫화면 이름 | 첫화면 버튼 | h1 | 높이 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| cafe-full-v1 | - | 0 | 0 | 0 | 0 | - | - | O | O | 1 | 3015 |
| cafe-full-v2 | - | 0 | 0 | 0 | 0 | - | - | O | O | 1 | 3035 |
| cafe-full-v3 | - | 0 | 0 | 0 | 0 | - | - | O | O | 1 | 2414 |
| cafe-min-v1 | - | 0 | 0 | 0 | 0 | - | - | O | O | 1 | 1714 |
| cafe-min-v2 | - | 0 | 0 | 0 | 0 | - | - | O | O | 1 | 1644 |
| cafe-min-v3 | - | 0 | 0 | 0 | 0 | - | - | O | O | 1 | 1326 |
| restaurant-full-v1 | - | 0 | 0 | 0 | 0 | - | - | O | O | 1 | 2884 |
| restaurant-full-v2 | - | 0 | 0 | 0 | 0 | - | - | O | O | 1 | 3086 |
| restaurant-full-v3 | - | 0 | 0 | 0 | 0 | - | - | O | O | 1 | 2471 |
| restaurant-min-v1 | - | 0 | 0 | 0 | 0 | - | - | O | O | 1 | 1639 |
| restaurant-min-v2 | - | 0 | 0 | 0 | 0 | - | - | O | O | 1 | 1644 |
| restaurant-min-v3 | - | 0 | 0 | 0 | 0 | - | - | O | O | 1 | 1326 |
| pension-full-v1 | - | 0 | 0 | 0 | 0 | - | - | O | O | 1 | 3172 |
| pension-full-v2 | - | 0 | 0 | 0 | 0 | - | - | O | O | 1 | 3220 |
| pension-full-v3 | - | 0 | 0 | 0 | 0 | - | - | O | O | 1 | 2572 |
| pension-min-v1 | - | 0 | 0 | 0 | 0 | - | - | O | O | 1 | 1686 |
| pension-min-v2 | - | 0 | 0 | 0 | 0 | - | - | O | O | 1 | 1644 |
| pension-min-v3 | - | 0 | 0 | 0 | 0 | - | - | O | O | 1 | 1326 |
| salon-full-v1 | - | 0 | 0 | 0 | 0 | - | - | O | O | 1 | 2403 |
| salon-full-v2 | - | 0 | 0 | 0 | 0 | - | - | O | O | 1 | 2543 |
| salon-full-v3 | - | 0 | 0 | 0 | 0 | - | - | O | O | 1 | 2035 |
| salon-min-v1 | - | 0 | 0 | 0 | 0 | - | - | O | O | 1 | 1634 |
| salon-min-v2 | - | 0 | 0 | 0 | 0 | - | - | O | O | 1 | 1644 |
| salon-min-v3 | - | 0 | 0 | 0 | 0 | - | - | O | O | 1 | 1326 |
| academy-full-v1 | - | 0 | 0 | 0 | 0 | - | - | O | O | 1 | 2821 |
| academy-full-v2 | - | 0 | 0 | 0 | 0 | - | - | O | O | 1 | 2995 |
| academy-full-v3 | - | 0 | 0 | 0 | 0 | - | - | O | O | 1 | 2408 |
| academy-min-v1 | - | 0 | 0 | 0 | 0 | - | - | O | O | 1 | 1639 |
| academy-min-v2 | - | 0 | 0 | 0 | 0 | - | - | O | O | 1 | 1644 |
| academy-min-v3 | - | 0 | 0 | 0 | 0 | - | - | O | O | 1 | 1326 |
| workshop-full-v1 | - | 0 | 0 | 0 | 0 | - | - | O | O | 1 | 2559 |
| workshop-full-v2 | - | 0 | 0 | 0 | 0 | - | - | O | O | 1 | 2578 |
| workshop-full-v3 | - | 0 | 0 | 0 | 0 | - | - | O | O | 1 | 2030 |
| workshop-min-v1 | - | 0 | 0 | 0 | 0 | - | - | O | O | 1 | 1686 |
| workshop-min-v2 | - | 0 | 0 | 0 | 0 | - | - | O | O | 1 | 1644 |
| workshop-min-v3 | - | 0 | 0 | 0 | 0 | - | - | O | O | 1 | 1326 |

## 세부


