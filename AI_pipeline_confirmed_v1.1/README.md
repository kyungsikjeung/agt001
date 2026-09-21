# 확정 산출물 패키지 v1.1 — 2026-09-21

## 이 패키지의 성격 (먼저 읽으십시오)

이 zip은 **두 종류의 파일**로 구성됩니다. 섞어 쓰면 안 되므로 폴더로 분리했습니다.

| 폴더 | 성격 | 신뢰도 |
|---|---|---|
| `10_confirmed_originals/` | 직전 턴에 생성된 **원본 파일 그대로** | 정본 |
| `20_reconstructed/` | 대화 기록에서 **재구성한 통합 인덱스** | 요약 — 원본 델타 문서를 대체하지 않음 |

### 왜 일부만 원본인가

작업 세션이 중간에 초기화되어, v0.1~v1.0 시기에 생성했던 델타 문서 파일들(`SRS_ai_driven_pipeline_v0.2.md`,
`SYS_SRS_v0.4.md` ~ `v0.7_delta.md`, `SWR_security_egress_v1.0.md`, `egress_policy.yaml`,
`classification.yaml`, `deploy.yaml`, `policy.yaml`, `reqcollector.zip` 등)의 실체가
작업 디렉터리에 남아 있지 않습니다. 이 파일들은 **대화의 첨부 파일로는 그대로 남아 있으므로**
개별 다운로드가 가능합니다. 목록은 `00_index/MANIFEST_missing_originals.md` 를 보십시오.

`20_reconstructed/` 의 문서들은 그 공백을 메우기 위해 **대화 본문에 기록된 확정 사실만으로** 다시 쓴 것입니다.
- 확정된 결정, 확정 파라미터, 요구사항 건수, 미해결 항목 — 대화에 명시된 값만 기재
- 대화 본문에 남지 않은 항목(예: D19·D22·D27의 제목)은 값을 지어내지 않고 `원본 참조 필요`로 표기

## 구성

```
00_index/
  MASTER_INDEX.md                  전체 경위·현재 위치·다음 단계
  MANIFEST_missing_originals.md    이 zip에 없는 원본 파일 목록 + 대화 첨부 안내
10_confirmed_originals/
  S2_decisions_locked_v1.1.md      D29~D35 확정 정본
  decisions_v1.1.csv
  locked_params_v1.1.csv           확정 파라미터 11종
  SWR_additions_v1.1.csv           확정 파생 신규 SWR 6건
20_reconstructed/
  decision_log_all.csv             1턴~현재 전체 확정 결정 로그
  requirements_inventory.md        계층별 요구사항 건수 대장
  open_items.md                    미해결·차단 항목
  process_pipeline.md              12단계 5게이트 프로세스 정의
```
