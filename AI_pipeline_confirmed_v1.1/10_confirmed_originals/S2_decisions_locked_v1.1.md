# S2 결정 확정 — v1.1 (D29~D35)

확정일: 2026-09-21 / 승인: 내부 단일 승인자

> 주: 세션 초기화로 v1.0 원본 CSV를 재열람하지 못했습니다. 아래 7건은 직전 턴 본문과 SWR 설계 근거에서 재도출한 것이며, 본 문서가 v1.1 정본입니다.

## 1. 확정 결정 7건

| ID | 주제 | 안 | 확정 내용 | 영향 SWR |
|---|---|---|---|---|
| D29 | 게이트 강제 지점 | A | TransportPort.send(req, decision) — Decision을 필수 인자로 두어 게이트 미경유 전송은 작성 자체가 불가. 정적검사·소켓가드는 보조. | SWR-EGR-001, SWR-EGR-002, SWR-CLS-013 |
| D30 | 판정 우선순위 | A | deny_hard > allowlist > mode(audit|enforce) 를 코드 상수로 고정. 정책파일·P0 전면허용 모드로 하드금지 3범주를 뒤집을 수 없음. | SWR-EGR-003, SWR-DNY-001~003 |
| D31 | 원문 보관 | A | 전송 본문 원문 전량 보관 + 저장 시 암호화 + 보존기한 경과 시 자동 파기. D20-C(사후 감사)의 성립 조건. | SWR-AUD-001, SWR-AUD-004 |
| D32 | 감사 무결성 | A | append-only 해시체인(SHA-256 prev_hash) + write-ahead. 기록 실패 시 전송 미수행. | SWR-AUD-002, SWR-AUD-006 |
| D33 | 정책 로드 실패 | A | 기동 시 egress_policy.yaml 스키마·reviewed_on 유효성 검사, 미로드/만료 시 fail-closed 기동 중단. | SWR-POL-005 |
| D34 | 탐지기 구성 | A | 결정적 규칙(정규식+엔트로피) + 사내 명부 사전 매칭만 사용. NER·LLM 분류기 배제(리플레이 재현성·근거 설명가능성 유지). | SWR-DET-001~007 |
| D35 | 오탐 예외 | A | 내부 단일 승인자 1인이 건별 예외 부여, TTL + 감사기록 필수. 전역 해제 불가. | SWR-EXC-001~003 |

## 2. 확정으로 값이 필요해진 파라미터

| 파라미터 | 값 | 출처 | 근거 | 상태 |
|---|---|---|---|---|
| `AUD.retention_days` | 90 | D31 | 보존기한. 감사 목적상 최소 1개 분기. 사내 규정 없음 → 잠정값 | 잠정 |
| `AUD.encryption` | AES-256-GCM | D31 | 저장 시 암호화 알고리즘 | 확정 |
| `AUD.key_location` | OS 키링, 부재 시 파일 mode 600 | D31 | 로컬 PC 단독(D25-A) 전제 | 확정 |
| `AUD.purge_clock` | wall_clock | D31 | SF-TMR-01 준수. 가동시간 기준 금지 | 확정 |
| `AUD.chain_algo` | sha256(prev_hash||record) | D32 | 해시체인 | 확정 |
| `AUD.write_ahead` | intent→send→outcome 2단 기록 | D32 | intent 기록 실패 시 send 금지 | 확정 |
| `EXC.ttl_hours` | 72 | D35 | 예외 유효기간. 근거 없는 초기값 | 잠정 |
| `EXC.max_renewals` | 1 | D35 | 무기한 연장 방지 | 잠정 |
| `EXC.scope` | (item_id, category, payload_hash) | D35 | 전역/카테고리 단위 해제 금지 | 확정 |
| `EXC.expiry_clock` | wall_clock | D35 | SF-TMR-01 준수 | 확정 |
| `DET.roster_dict` | 미확보 | D34 | 고객사·인명 명부 사전. 없으면 실명 탐지 공백 | 미해결 |

## 3. 확정에서 파생된 신규 SWR 6건

| ID | modality | 요구문 | 출처 | AC |
|---|---|---|---|---|
| SWR-AUD-011 | must | 보존기한 경과 감사 레코드를 벽시계 기준으로 파기하고, 파기 사실 자체를 체인에 기록한다 | D31 | 파기 후 chain verify가 여전히 통과 |
| SWR-AUD-012 | must | 감사 로그 암호화 키 부재·복호 실패 시 신규 전송을 거부한다(fail-closed) | D31/D33 | 키 제거 상태로 기동 시 send 0건 |
| SWR-DET-011 | must | 명부 사전 미로드 시 '고객사 실명' 범주를 미탐 상태로 표기하고 기동 배너에 경고한다 | D34 | 사전 없이 기동 시 경고 1건 출력 |
| SWR-DET-012 | must_not | 명부 사전 부재를 이유로 해당 범주를 자동 통과 처리해서는 안 된다 | D34 | 사전 없을 때 해당 범주 판정이 pass로 기록되지 않음 |
| SWR-EXC-004 | must | 예외 TTL 만료를 재기동 시 캐치업 검사하여 만료분을 즉시 회수한다 | D35/SF-TMR-02 | PC 종료 96h 후 기동 시 72h 예외가 만료 처리됨 |
| SWR-EXC-005 | must | 예외 부여·사용·만료 각각을 감사 체인에 별도 레코드로 남긴다 | D35/D32 | 예외 1건당 레코드 3종 존재 |

## 4. 해소된 차단
- v1.0에서 `DECISION_REQUIRED` 상태였던 SWR 7건이 `READY`로 전환됩니다.
- SWR 총계: 73 → **79건**(신규 6건 추가). 상위 커버리지 36/36 유지.

## 5. 남은 미해결
1. **고객사·인명 명부 사전 미확보** — D34-A의 실명 탐지를 떠받치는 데이터. 미확보 상태에서는 하드 금지 3범주 중 1범주가 사실상 비어 있습니다. SWR-DET-011/012로 "조용한 통과"만 차단했을 뿐, 탐지력 자체는 확보되지 않습니다.
2. **`egress_policy.yaml`의 `reviewed_on` 2건 TODO** — D33-A 확정으로 이제 **미기입 시 기동이 거부**됩니다. 벤더 약관 확인 일자 기입이 착수 전제조건이 되었습니다.
3. **잠정 파라미터 3종** — `AUD.retention_days=90`, `EXC.ttl_hours=72`, `EXC.max_renewals=1`은 근거 없는 초기값입니다.
4. **SWR-DET-007의 500ms** — 첫 5회 실행 중앙값으로 재설정 필요(v1.0에서 이월).
