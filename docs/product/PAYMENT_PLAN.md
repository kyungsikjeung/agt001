# 결제: 사장님 구독료 + 손님 결제(포트원 파트너 정산) (PAYMENT_PLAN)

> 2026-09-29 (KST) / Claude. 대표 질문: "나도 사장님에게 결제를 받아야 하고, 사장님도 손님에게 결제를 붙일 수 있을 텐데 구조를 어떻게 잡나?"
> **대표 결정(같은 날)**: ① 결제도 지금 같이 개발한다(D13·D32의 "검증 뒤"를 개발에는 적용하지 않음, 실결제 오픈은 계약·고지가 끝난 뒤) ② PG 연동은 **포트원**, 손님 결제는 **하위 판매자 정산(파트너 정산 자동화)** 방식 ③ 매출 DB는 여러 가게를 함께 담는 구조로 → [SALES_DB_PLAN](SALES_DB_PLAN.md).
> 먼저 읽은 것: [DECISIONS](DECISIONS.md) D13·D31·D32·D40·D41, [BUSINESS_STRATEGY §4](BUSINESS_STRATEGY.md), [BOOKING_RULES_PLAN](BOOKING_RULES_PLAN.md), [OWNER_SETTINGS_PLAN](OWNER_SETTINGS_PLAN.md), [DATA_ARCHITECTURE_REVIEW](DATA_ARCHITECTURE_REVIEW.md), `app/services/bookings.py`·`shop_settings.py`·`keystore.py`.

## 0. 한 줄 요약

**돈 흐름은 두 개(A 사장님 → 우리, B 손님 → 사장님).** 둘 다 포트원 V2 한 곳으로 붙이고, 우리 서버는 결제·매출을 [SALES_DB_PLAN](SALES_DB_PLAN.md)의 표에 기록한다. B는 **포트원 파트너 정산으로 가게별 정산을 맡기고, 우리는 정산 계산·송금을 직접 하지 않는다.** 개발자 연동은 된다(§2). 다만 **B의 법적 구조는 포트원 계약 상담에서 반드시 문서로 확인**해야 한다(§2.3).

## 1. 두 가지 돈 흐름

| | A. 구독료·제작비 | B. 손님 결제(예약금·수강료·숙박비) |
|---|---|---|
| 누가 → 누구에게 | 사장님 → 우리 | 손님 → 사장님 |
| 판매자 | 우리 | 사장님(하위 판매자 = 포트원 "파트너") |
| 포트원 기능 | 빌링키 + 결제 예약(정기결제) | 일반 결제 + 파트너 정산 자동화 |
| 우리 몫 | 구독료 | 0원 권장("수수료 0원", BUSINESS_STRATEGY §1). 받으려면 정산 계약의 중개수수료 칸 |
| 기록 표 | `subscriptions`, `payments` | `orders`, `order_items`, `payments`, `settlements` |

## 2. 포트원 확인 결과 (2026-09-29 조사)

### 2.1 개발자로 붙일 수 있나 → **된다**

| 항목 | 확인 내용 | 출처 |
|---|---|---|
| 결제창 | 브라우저 SDK(`@portone/browser-sdk`)로 우리 페이지에서 결제창 호출 | developers.portone.io |
| 서버 | REST API V2 + **공식 Python SDK `portone-server-sdk`**(PyPI 0.21.0, Python 3.9+, 내부 httpx — 우리가 이미 쓰는 라이브러리) | pypi.org/project/portone-server-sdk |
| 정기결제 | 빌링키 발급 + 결제 예약 `POST /payments/{paymentId}/schedule`(`timeToPay`) → **매달 결제를 우리 cron 없이 포트원이 실행** | developers.portone.io |
| 파트너 정산 API | 파트너 등록·조회, 계약(수수료·정산 주기) 등록, 주문 정산 등록 `POST /platform/transfers/order`, 취소 정산 `POST /platform/transfers/order-cancel`, 수기 정산 `POST /platform/transfers/manual`, 지급(payout)·일괄 지급, 정산 내역 조회·CSV | developers.portone.io/api/rest-v2/platform.transfer |
| 테스트 | V2 테스트 채널로 실제 결제창 테스트(Store ID·채널 키·V2 API Secret·웹훅 Secret) | developers.portone.io |
| 켜기 조건 | **파트너 정산 기능은 포트원에 따로 신청해 켜야 한다**("Platform features must be explicitly enabled") | 같은 API 문서 |

### 2.2 흐름 (포트원 문서 "서비스 프로세스")

1. 계약 등록: 우리 ↔ 파트너 계약 조건(중개수수료·정산 주기)
2. 파트너 등록: 가게(사장님)를 파트너로, 기본 계약 지정 — 사업자·예금주 조회 기능 있음
3. 주문 정보 전달: 결제 id·할인·상품·파트너 id
4. 정산 금액 계산 → 정산일에 지급(송금대행 일괄 지급), 세금계산서 역발행

### 2.3 법 — **가장 중요한 확인 사항**

- 전자금융거래법 개정(2024-09-15 시행): 플랫폼이 전자적 방법으로 재화·용역 대가를 **정산 대행·매개하면 PG 등록 대상**(자본금 10억 원 등). 미등록 운영은 3년 이하 징역 또는 2천만 원 이하 벌금. (헤럴드경제·ZDNet 2024-09 기사)
- 포트원 설명: 파트너 정산 자동화는 "정산금 이동 및 정산 처리"를 포트원이 대행해 **"별도의 3자 계약 없이도 합법적인 정산이 가능"**하도록 설계. (같은 기사)
- 하지만 포트원 헬프센터의 두 계약 방식 설명에는 **"PG사 ↔ 플랫폼 계약이면 결제 대금이 플랫폼 계좌로 입금되고, 플랫폼이 하위 상점에 정산해야 한다"**고 되어 있다. 즉 돈이 **우리 계좌를 한 번 거치는 구조일 수 있다.**
- → 포트원 상담에서 **문서로** 받을 것: ① 결제 대금이 우리 계좌를 거치는가 ② 거친다면 우리가 PG 등록 없이 운영해도 되는 근거(포트원 송금대행 구조·법률 검토서) ③ 우리 모델(사이트 빌더, 판매자는 사장님, 수수료 0원)이 대상인가 ④ 가게 입점 서류·심사 기간 ⑤ 결제·정산·송금 수수료(2026-01 "초기 플랫폼 정산 지원 패키지" 조건 포함) ⑥ 에스크로·환불 시 정산 차감 방식.
- **대안(상담 결과가 나쁠 때)**: "PG ↔ 가게 직접 계약"(돈이 가게로 바로, 우리는 정산 안 함). 포트원이 가게별 채널을 같이 관리하고, 우리 코드는 결제 부분이 거의 같다(채널 키만 가게별). 이 경우 `settlements`는 비워 둔다.

### 2.4 그 밖의 준비 (대표)

사업자등록·통신판매업 신고, 이용약관·환불 규정, 우리 랜딩과 가게 사이트 아래 사업자 정보 고지, 개인정보처리방침에 "포트원·PG사 결제 처리 위탁" 추가, 가게 입점 약관(파트너 약관).

## 3. 공통 구현

### 3.1 파일

| 파일 | 내용 |
|---|---|
| `app/services/payments.py` | 포트원 호출은 여기 한 곳만(`portone_server_sdk`). 여러 PG 추상화는 만들지 않는다 |
| `app/api/payments.py` | 결제 페이지·완료·웹훅 |
| `keystore.EDITABLE` | `portone_api_secret`, `portone_webhook_secret`, `portone_store_id`, 채널 키 추가(관리자 화면 D50) |
| `tests/test_payments.py` | §3.4 |

### 3.2 함수

| 함수 | 하는 일 |
|---|---|
| `start(order_id) -> payment_id` | `payments`에 `ready` 행. 금액은 `orders.total`(서버 값)에서 |
| `complete(payment_id)` | 포트원 `get_payment` 조회 → **금액·상태가 DB와 같을 때만** `paid`. `SELECT … FOR UPDATE`로 한 번만. B면 이어서 주문 정산 등록 |
| `refund(payment_id, amount, reason, by)` | 포트원 취소 API(부분 가능) → `refunds` 행 + B면 취소 정산 등록 |
| `handle_webhook(headers, body)` | 서명 확인(웹훅 Secret) → `complete`와 같은 경로. 멱등 |

### 3.3 API

| 경로 | 설명 |
|---|---|
| `GET /pay/{payment_id}` | **앱 주소**의 결제 페이지. 공개 사이트는 CSP·무JS라 결제창을 못 띄우므로 문자 인증 페이지(`/api/bookings/{site_key}/verify/{token}`)처럼 우리 페이지로 넘긴다 |
| `GET /pay/{payment_id}/done` | 결제창에서 돌아온 뒤 `complete` → 결과 화면 |
| `POST /api/payments/webhook` | 포트원 웹훅. 결제창을 닫고 떠나도 여기서 확정 |

### 3.4 지켜야 할 것

- 카드 정보는 우리 서버에 오지 않는다(포트원 결제창).
- 클라이언트가 보낸 금액·성공 표시는 믿지 않는다. 항상 포트원 조회로 확인.
- `payments.provider_payment_id` UNIQUE, 상태 변경은 `FOR UPDATE` 안에서만.
- 환불·결제 기록은 지우거나 고치지 않는다. 환불은 새 행(SALES_DB_PLAN §4 원칙).
- 테스트: 금액 불일치 거절 / 같은 결제 완료가 두 번 와도 `paid` 한 번 / 결제 대기 만료가 자리를 풀어 줌 / 가게 A가 가게 B 결제를 환불 못 함.

## 4. A. 구독료 (사장님 → 우리)

- **가게 단위** 요금(DATA_ARCHITECTURE_REVIEW ⑩ "shops가 결제 단위"). 내는 사람은 방장 계정.
- `/settings` → 요금제 고르기 → 포트원 빌링키 발급 창 → 첫 달 결제 → `active` → **다음 달 결제를 포트원 결제 예약으로 등록**. 결제 성공 웹훅이 올 때마다 그다음 달을 예약한다. 우리 cron 불필요.
- 실패: 포트원 실패 웹훅 → `past_due` + 사장님 카톡 알림, 1·3·5일째 다시 예약. 7일 뒤 `free`. **공개 사이트는 끄지 않는다**(유료 기능만 무료 한도로).
- 해지: 예약된 다음 결제 취소, 이번 달 끝까지 사용.
- 제작비 99,000원: 빌링키 없이 일반 결제 1회.
- 요금제 한도는 코드 안 표 하나(`PLAN_LIMITS`), D40 사용 장부가 읽는다. 중간 변경 일할 계산·연간 결제는 처음엔 안 한다.

## 5. B. 손님 결제 (손님 → 사장님)

### 5.1 가게 입점 (사장님 설정 페이지)

- `/settings`에 "온라인 결제 받기": 사업자번호·대표자·정산 은행/계좌·예금주 입력 → 포트원 사업자·예금주 조회 → 파트너 등록 → 상태 `pending → active`.
- 개인(사업자 없는) 가게는 포트원 파트너 유형 확인 필요(§2.3 ④).
- **OWNER_SETTINGS_PLAN 범위 변경**: 지금은 "솔라피 키만". 여기에 정산 정보가 들어간다(키가 아니라 가게 정보). 계좌번호는 암호화 저장, 화면엔 뒤 4자리.

### 5.2 예약금 결제 흐름

1. 손님 예약 신청 → 입력 검사(기존 `bookings.submit(check_only=True)`) → `bookings` `pending_payment` + `orders`·`order_items`(시술·가격 스냅샷) + `payments` `ready` → `303 /pay/{payment_id}`.
2. 결제 완료 → `payments.paid` → 포트원 **주문 정산 등록**(파트너 id·금액·할인) → `settlements` 행 `scheduled` → 예약은 `requested`(사장님 확정 대기, 가게 설정에 따라 바로 `confirmed`).
3. `pending_payment`는 **15분**만 자리를 잡는다. `availability.slot_taken`이 유효 시간 안의 `pending_payment`도 센다.
4. 사장님 거절 → 전액 자동 환불 + 취소 정산. 손님 취소 → 가게 규정(`refund_rule`, 예: 24시간 전 100%·이후 0%) 부분 환불. 노쇼 → 환불 없음, `orders.status = no_show`.
5. 시술 뒤 사장님이 "완료" + 실제 금액 입력(현장 결제분은 `provider = manual`) → 매출 DB에 전체 매출이 쌓인다(SALES_DB_PLAN §5). 인사이트의 핵심이라 온라인 예약금만 기록하지 않는다.

### 5.3 예약 상태 (지금 `requested·confirmed·declined`에 추가)

```
신청 ─┬─ 예약금 없음 ────────────→ requested ─→ confirmed / declined
      └─ 예약금 있음 → pending_payment ─ 결제 → requested ─→ confirmed / declined(자동 환불)
                                     └ 15분 초과 → expired
confirmed ─→ completed(매출 확정) / canceled(규정 환불) / no_show
```

### 5.4 만들지 않는 것

시술비를 사이트에서 전액 받기(현장 단말기가 한다 — 원데이클래스·펜션은 예약금 = 전액으로 설정하면 같은 흐름), 쿠폰·포인트, 우리 정산 대시보드(포트원 콘솔 사용), 여러 PG.

## 6. 대표 결정 필요

| # | 질문 | 추천 |
|---|---|---|
| P1 | 포트원 상담 §2.3 ①~⑥ | **개발 시작과 동시에 신청.** 결과에 따라 파트너 정산 / 가게 직접 계약 중 확정. 코드는 §3 공통이라 어느 쪽이든 버리지 않는다 |
| P2 | 손님 결제에 우리 수수료 | 0원(프로 요금제 기능으로) |
| P3 | 구독 실패 시 공개 사이트 | 끄지 않는다 |
| P4 | 예약금 없는 가게의 현장 매출 기록 | "완료 + 금액" 버튼 한 번. 매출 인사이트는 이 기록이 있어야 의미가 있다 |
| P5 | 가게 결제 기본 PG | 포트원 테스트 채널로 개발, 실결제 PG(토스페이먼츠 등)는 포트원 상담에서 파트너 정산을 지원하는 곳으로 |

## 7. 순서 (결제·매출 같이 개발)

| 단계 | 내용 | 조건 | 크기 |
|---|---|---|---|
| 0 | 포트원 가입·테스트 채널, 파트너 정산 신청·상담(§2.3), 사업자·통신판매업 | 지금(대표) | — |
| 1 | `shops`(DATA_ARCHITECTURE M1) + 매출 표(SALES_DB_PLAN §4) 마이그레이션 | 지금 | 1일 |
| 2 | `payments.py`·`/pay`·웹훅 + 제작비 일반 결제(테스트 채널) | 1 뒤 | 1~2일 |
| 3 | 구독(빌링키·결제 예약·실패 처리·`PLAN_LIMITS`) | 2 뒤 | 2일 |
| 4 | 예약금 결제 + 상태 확장 + 자동 환불 + 시술 완료 기록 | 2 뒤 | 2~3일 |
| 5 | 파트너 등록·주문 정산 등록 연결 | 포트원 기능 켜짐 | 1~2일 |
| 6 | 매출 인사이트 화면(SALES_DB_PLAN §6) | 4 뒤 | 1~2일 |
| 오픈 | 실결제 채널 전환 | 계약·고지·약관 끝 | — |

## 출처

- 포트원 파트너 정산 자동화 가이드: https://developers.portone.io/platform/ko/readme
- 서비스 프로세스: https://developers.portone.io/platform/ko/guides/process
- 파트너 정산 REST API: https://developers.portone.io/api/rest-v2/platform.transfer?v=v2
- 중개플랫폼 정산 계약 방식: https://help.portone.io/content/platform-contract-method
- 전금법 개정과 파트너 정산: https://biz.heraldcorp.com/article/3468495 , https://zdnet.co.kr/view/?no=20240910103753
- Python SDK: https://pypi.org/project/portone-server-sdk/
