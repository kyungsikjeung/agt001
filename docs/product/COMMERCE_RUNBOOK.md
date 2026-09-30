# 온라인 주문·스탬프 운영 절차 (운영자용)

> 서버 명령은 모두 서버(`ssh ubuntu@144.24.91.250`)의 `~/agt001`에서 실행한다. 스크립트는 backend 컨테이너 안에서 돌린다:
> `sudo docker compose exec -T backend sh -c 'PYTHONPATH=/app python scripts/<스크립트>.py [인자]'`

## 1. 비상 스위치 (새 주문·결제 시작을 멈춤)

| 순서 | 할 일 | 설명 |
|---|---|---|
| 1 | 이상 발견 | 운영 신호(아래 3번), 사장님 연락, 포트원 콘솔 대조 |
| 2 | 스위치 | 서버 `.env`에 `COMMERCE_PAUSED=true` 한 줄 |
| 3 | 다시 만들기 | `sudo docker compose up -d backend` (**`restart`는 안 됨**: `.env`는 `env_file`이라 컨테이너를 다시 만들어야 새 값을 읽는다. 수 초) → `sudo docker compose exec -T backend printenv COMMERCE_PAUSED`로 `true` 확인 |
| 4 | 멈춤 확인 | 새 주문·결제 시작·쿠폰 잡기·내 스탬프가 멈춤 화면. 주문·결제 행이 새로 생기지 않음 |
| 5 | 계속 확인 | 결제 확정(`done`·웹훅)·사장님 환불·쿠폰 사용은 그대로 됨 |
| 6 | 다시 공개 | 위 컨테이너 명령으로 `scripts/republish_commerce.py` 한 번 실행 (주문을 켠 가게·스탬프 규칙이 켜진 가게의 공개본만 다시 만듦) |
| 7 | 결과 | 공개본은 "전화로 주문" 모양으로 돌아감. 가게 설정(`order_on`, 스탬프 규칙)은 그대로라 풀면 원래대로 |
| 8 | 되돌리기 | `.env`를 `false`로 → `sudo docker compose up -d backend` → 스크립트 → 다시 켜짐 |

`scripts/republish_commerce.py --dry-run`이면 대상 가게 키만 보여주고 바꾸지 않습니다.

## 2. 환불이 포트원엔 됐는데 우리 기록이 없을 때

1. 포트원 콘솔에서 결제 내역을 엽니다 (결제 번호·취소 금액·시각 확인).
2. DB `refunds` 표에서 같은 결제의 합계를 봅니다: `sudo docker compose exec -T db psql -U agt001 -d agt001 -c "select p.provider_payment_id, p.amount, coalesce(sum(r.amount),0) from payments p left join refunds r on r.payment_id=p.id where p.provider_payment_id='<결제 번호>' group by 1,2"`
3. 콘솔 취소 금액이 더 크면 **사장님 화면에서 다시 환불하지 않습니다**(포트원에 또 취소가 나가 이중 환불이 된다). 차액을 `refunds` 표에 기록하는 일은 개발자가 한다 — 포트원 취소 번호·금액·시각을 같이 넘긴다.
4. 그래도 안 맞으면 사장님께 "잠시 멈췄어요"를 안내하고 개발자에게 넘깁니다.

## 3. 운영 신호 보는 법

위 컨테이너 명령으로 `scripts/commerce_signals.py`를 실행합니다.

- 최근 24시간(한국 시간) `payment_mismatch`(포트원은 받았는데 금액·돈 종류가 다름)와 `webhook_bad_signature`(웹훅 서명 실패) 건수와 사유별 건수를 보여줍니다.
- 사건이 하나라도 있으면 종료 코드 1 (나중에 자동 알림에 붙이기 쉽게).
- 숫자가 보이면 포트원 콘솔 결제 내역과 대조합니다.

## 4. 웹훅이 안 올 때

1. 사장님 화면의 주문에서 "다시 확인"을 누릅니다 (포트원에 직접 물어봐서 확정합니다).
2. 그래도 안 되면 3번 스크립트로 서명 실패가 쌓이는지 봅니다.
3. 서명 실패가 계속되면 웹훅 비밀값이 바뀌었는지 확인하고 개발자에게 넘깁니다.
