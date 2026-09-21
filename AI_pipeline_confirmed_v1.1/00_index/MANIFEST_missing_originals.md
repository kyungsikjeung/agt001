# 이 zip에 포함되지 않은 원본 파일

세션 초기화로 작업 디렉터리에서 소실된 파일입니다.
**대화의 첨부 파일로는 그대로 남아 있으므로 개별 다운로드가 가능합니다.**
아래 순서는 생성 시점 순입니다.

| # | 파일명 | 내용 | 대체 요약 위치 |
|---|---|---|---|
| 1 | `FR_spec_requirements_collector_v0.1.md` / `.csv` | 수집기 자체 FR 63 + NFR 8 | requirements_inventory.md |
| 2 | `SRS_ai_driven_pipeline_v0.2.md` / `.csv` | 파이프라인 전체 요구사항 132건 | requirements_inventory.md |
| 3 | `decisions_3options_v0.2.csv` | 결정 9건(3안+추천) | decision_log_all.csv (일부) |
| 4 | `SRS_delta_v0.3.md` / `.csv`, `decisions_v0.3.csv`, `policy.yaml` | audience 축 도입, PRV 그룹, 누적 157건 | requirements_inventory.md |
| 5 | `SYS_SRS_v0.4.md`, `SYS_requirements_v0.4.csv`, `SYS_interfaces_v0.4.csv`, `decisions_v0.4.csv` | 시스템 요구사항 138건(기능75/비기능29/인터페이스34) | requirements_inventory.md |
| 6 | `SYS_SRS_v0.5_delta.md` / `.csv`, `decisions_v0.5.csv`, `classification.yaml` | 기밀 등급 C0/C1/C2 신설, 누적 171건 | requirements_inventory.md |
| 7 | `SYS_SRS_v0.6_delta.md` / `.csv`, `decisions_v0.6.csv`, `egress_policy.yaml` | 외부 송신 통제, 누적 208건 | requirements_inventory.md |
| 8 | `SYS_SRS_v0.7_delta.md` / `.csv`, `decisions_v0.7.csv`, `deploy.yaml` | 배포 프로파일(로컬/OCI), 누적 233건 | requirements_inventory.md |
| 9 | `SWR_security_egress_v1.0.md` / `.csv`, `decisions_v1.0.csv` | SWR 73건 전개 + D29~D35 제안 | 10_confirmed_originals/ (v1.1이 상위 정본) |
| 10 | `reqcollector.zip`, `schemas.py`, `gate.py`, `profile.py`, `generic.yaml` 등 | 초기 프로토타입 코드 | 폐기 대상 아님. 단 S0 스키마는 프로파일 기반으로 재작성됨 |

## 권고

위 10건 중 **4~9번은 요구사항 정본**이므로, 대화 첨부에서 내려받아
이 패키지의 `10_confirmed_originals/` 옆에 함께 보관하시는 것을 권합니다.
`20_reconstructed/` 문서는 건수와 결정만 담고 있어 **개별 요구문 전문을 대체하지 못합니다.**
