# OCI 비용 모니터링 (WP 0-5a)

> 측정일: 2026-09-25 (UTC) / 리전: ap-chuncheon-1 / 스크립트: `scripts/oci_cost_report.sh`
> 원칙: 읽기 전용 조회만 수행한다. 상태를 바꾸는 명령은 실행하지 않는다.
> 보안: 이 문서에는 OCID·이메일·키를 적지 않는다. 필요한 곳은 `<TENANCY_OCID>`, `<BUDGET_OCID>`, `<EMAIL>` 같은 자리표시자를 쓴다.

## 1. 스크립트 사용법

```bash
./scripts/oci_cost_report.sh --help
./scripts/oci_cost_report.sh --days 30          # 최근 30일 + 이번 달 누계 (기본)
./scripts/oci_cost_report.sh --days 7           # 최근 7일 + 이번 달 누계
./scripts/oci_cost_report.sh --days 30 --json   # 기계용 요약 JSON
```

- 테넌시 OCID는 `~/.oci/config`의 `tenancy` 값에서 스크립트 안에서 읽어 CLI 호출에만 쓰고, 출력에는 포함하지 않는다.
- 출력에는 리소스 이름과 수치만 나온다 (OCID·키·이메일 없음).
- 종료코드: `0` 정상(합계 0원), `2` 경고: 과금 발생(합계 > 0, cron·알림용), `1` 조회 실패.

출력 구성:

1. 최근 N일 합계 / 이번 달 누계 + 통화 단위.
2. 서비스별 합계 (조회 기간), 일별 합계 (0이 아닌 날만).
3. 무료 한도 대비 현재 사용량 표 (인스턴스 OCPU/메모리, 블록 스토리지 GB, 예약 공인 IP, 버킷 수).

## 2. 실측 결과 요약 (2026-09-25)

### 비용

| 구간 | 합계 | 통화 |
|---|---|---|
| 최근 30일 (2026-08-26 ~ 2026-09-25) | 0.0000 | SGD |
| 이번 달 누계 (2026-09-01 ~ 2026-09-25) | 0.0000 | SGD |

서비스별 (두 구간 동일): Compute 0, Block Storage 0, Virtual Cloud Network 0, Telemetry 0.
일별 0이 아닌 날 없음. 스크립트 종료코드 `0` (텍스트·`--json` 모두 확인).

### 무료 한도 대비 사용률

공식 문서 기준 Always Free 한도 (불확실 항목은 "확인 필요" 표기):

| 항목 | 현재 | 한도 | 사용률 | 비고 |
|---|---|---|---|---|
| 인스턴스 | A1 Flex 1대 RUNNING, 2 OCPU / 12GB | Ampere A1 합계 4 OCPU / 24GB | 50% | E2.1.Micro 2대 한도는 별도 (현재 미사용) |
| 블록 스토리지 합계 | 47GB (부트 47GB + 블록 0GB) | 합계 200GB | 23.5% | 부트 볼륨 1개, 추가 블록 볼륨 0개 |
| 공인 IP | 임시(Ephemeral) 1개 부착, 예약(Reserved) 0개 | 임시 IP 부착 시 무료, 예약 IP는 과금 | 정상 | 예약 IP 생성 금지 |
| 오브젝트 스토리지 | 버킷 0개 | Always Free 범위 (용량 한도는 확인 필요) | 0개 | 사용 없음 |
| 아웃바운드 전송 | 미측정 | 월 10TB (확인 필요) | 확인 필요 | 스크립트 미집계, 콘솔 Cost Analysis로 별도 확인 권장 |

### 계정·예산 상태 (조회만)

- 구독 등급(subscription-tier): `FREE_AND_PAID` (유료 전환된 계정 + Always Free 공존).
  30일 400 SGD 체험 프로모션은 만료됨. 즉, 한도 초과분은 즉시 과금되므로 "0원 유지"는 현재 리소스가 전부 Always Free 안에 있을 때만 성립한다.
- 청구 통화: SGD (비용 조회 응답 기준).
- 예산: `monthly-cost-guard`, 금액 5, 월간 리셋(MONTHLY), 상태 ACTIVE, 실제 지출(actual-spend) 0, 예측 지출(forecasted-spend) 0.
- 알림 규칙: ACTUAL 기준 임계값 80% 1건 ACTIVE (수신자·OCID는 생략).

## 3. 발견된 과금 위험 요소

1. **유료 계정에서 Always Free 초과 시 즉시 과금.** 체험 크레딧이 만료된 상태이므로, A1 4 OCPU/24GB·스토리지 200GB를 넘는 순간부터 SGD로 청구된다.
2. **부트 볼륨 47GB.** 기본값보다 크며, 추가 볼륨 생성·볼륨 확장을 하면 200GB 한도에 가까워진다. 현재 23.5%로 여유는 있으나 변경 시 재측정 필요.
3. **예약 공인 IP.** 현재 0개로 정상. 실수로 예약 IP를 생성하고 인스턴스에 붙이지 않고 방치하면 과금된다.
4. **두 번째 A1 인스턴스.** 한도 내(합계 4 OCPU/24GB)에서는 가능하지만, 합계를 넘는 스펙으로 만들면 과금된다. 생성 전 스크립트로 여유분 확인 필요.
5. **아웃바운드 전송량 미모니터링.** 월 10TB 한도(확인 필요)는 현재 스크립트로 집계하지 않는다. 트래픽 급증 시 인지 지연 가능.
6. **예산 임계값이 5 기준 80%.** 소액 과금이 발생해도 80% 도달 전까지 알림이 오지 않는다. 더 촘촘한 예산(예: 월 1달러 + 낮은 임계값) 병행을 검토할 것 (아래 권장안).

## 4. 권장 조치안

### (a) OCI 예산 + 알림 규칙 (명령 예시만, 실행하지 마라)

이미 `monthly-cost-guard`(5 기준, 80% 알림)가 ACTIVE이므로, 아래는 **추가로 더 민감한 예산을 만들 경우의 예시**다. 실제 생성은 콘솔 또는 운영 담당자가 판단 후 실행한다.

```bash
# 예시 1: 월 1 단위 예산 생성 (자리표시자 치환 후 실행)
oci budgets budget budget create \
  --compartment-id <TENANCY_OCID> \
  --display-name monthly-cost-guard-1unit \
  --description "Alert when spend approaches 1 per month" \
  --amount 1 \
  --reset-period MONTHLY \
  --processing-period-type MONTH \
  --target-type COMPARTMENT \
  --targets '["<TENANCY_OCID>"]'

# 예시 2: 실제 지출 1% 초과 시 이메일 알림 (예산 생성 후 <BUDGET_OCID> 치환)
oci budgets budget alert-rule create \
  --budget-id <BUDGET_OCID> \
  --display-name actual-spend-1pct \
  --type ACTUAL \
  --threshold 1 \
  --recipients <EMAIL>

# 예시 3: 예측 지출 100% 초과 시 알림 (선택)
oci budgets budget alert-rule create \
  --budget-id <BUDGET_OCID> \
  --display-name forecast-spend-100pct \
  --type FORECAST \
  --threshold 100 \
  --recipients <EMAIL>
```

주의: 예산 금액의 통화 단위와 임계값 의미(ACTUAL 금액 기준 vs 비율 기준)는 콘솔에서 한 번 더 확인할 것. 위 예시는 문서 기준이며, 실제 동작은 "확인 필요"로 두고 생성 후 테스트 알림으로 검증한다.

### (b) 일일 자동 점검 방식 제안

- **cron (서버 또는 관리 PC):** 매일 아침 실행, 종료코드 `2`일 때만 알림.
  ```cron
  0 0 * * * /Users/kyoungsikjeung/Documents/agent_project/scripts/oci_cost_report.sh --days 1 --json >> /var/log/oci_cost_report.log 2>&1
  ```
  래퍼 스크립트에서 종료코드를 검사한다: `0` 무시, `2` → 메신저/이메일 발송, `1` → 조회 실패 별도 알림 (사일런트 실패 방지).
- **CI 스케줄 (대안):** GitHub Actions `schedule: cron('0 0 * * *')` 로 매일 실행. 시크릿에 OCI 키를 넣어야 하므로 키 관리 부담이 있으면 cron을 우선한다.
- **월 1회 수동 확인:** 매월 1일 `--days 30` 결과를 이 문서 §2 표에 추가 기록하고, 스토리지·OCPU 사용률 추이를 남긴다. 아웃바운드 전송량은 콘솔 Cost Analysis에서 별도 확인한다 (스크립트 미집계).
- **변경 전후 측정:** 인스턴스 스펙 변경·볼륨 확장·IP 추가 전후에는 반드시 스크립트를 실행하고, 무료 한도 사용률이 80%를 넘으면 원복을 검토한다.

## 5. 재현 정보

- 조회 명령 (읽기 전용): `oci usage-api usage-summary request-summarized-usages` (granularity DAILY, query-type COST, group-by `["service"]`, tenant-id는 config에서 읽음),
  `oci compute instance list`, `oci bv boot-volume list`, `oci bv volume list`,
  `oci network public-ip list --scope REGION`, `oci os bucket list`, `oci budgets budget budget list --target-type ALL`.
- 금지 사항 준수: 예산·리소스 생성/변경/삭제 없음, SSH 접속 없음, `deploy.sh`·`rollback.sh` 미실행, `.env`·`~/.oci/config` 내용 미출력, git add/commit/push 없음.
