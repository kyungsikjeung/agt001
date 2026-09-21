# SRS 전체 정리 (System + Software Requirements)

> 작성일: 2026-09-21 / 기준: `AI_pipeline_confirmed_v1.1` + `ARCH_S3_v1.2` / 브랜치: `main`
> 상세 요구문 전문은 원본 CSV/MD 참조. 본 문서는 건수·버전·결정·게이트·마일스톤의 대장(인덱스)임.

## 1. SRS 계보 한눈표

| 버전 | 문서 | 건수 | 핵심 변경 | 상태 |
|---|---|---:|---|---|
| FR v0.1 | FR_spec (수집기 자체) | FR 63 + NFR 8 = 71 | 1~6턴 결정의 요구문 변환 | 이후 S1~S3에 흡수 |
| SRS v0.2 | 파이프라인 전체 | 132 (TRC 9 포함) | 12단계 5게이트 정의 | 정본(원본 첨부 참조) |
| SRS v0.3 | + audience/PRV 델타 | 누적 157 (신규 +25) | ASK 13건, PRV 5건, M1/M2/M3 경계 | 정본 |
| SYS v0.4 | SYS_SRS | 138 (기능 75 / 비기능 29 / IF 34) | NIM·EC2·BaaS 전제 반영 | 정본 |
| SYS v0.5 | 델타 | 신규 33 → 누적 171 | C0/C1/C2 신설, 외부송신 통제 | 정본 |
| SYS v0.6 | 델타 | 신규 37 → 누적 208 | D20-C 보상통제 23건, 벤더대응 | 정본 |
| SYS v0.7 | 델타 | 신규 25 → 누적 233 | 로컬/OCI 프로파일, 벽시계, 키분리 | 정본 |
| SWR v1.0 | SWR_security_egress | 73 | 상위 36건 전개 → 73건, 커버리지 36/36 | v1.1이 상위 정본 |
| SWR v1.1 | + D29~D35 파생 | 79 (신규 +6) | AUD/DET/EXC 6건 추가 | **현 정본** |
| ARCH v1.2 | S3 아키텍처 | 모듈 89 (M1 50 / M2 36 / M3 3) | 6층 레이어, 포트 11종, D36~D42 | **현 정본** |

## 2. 요구사항 건수 총괄표

| 계층 | 기준 문서 | 건수 | 비고 |
|---|---|---:|---|
| 수집기 FR | FR v0.1 | 71 | FR 63 + NFR 8 |
| 파이프라인 SRS | SRS v0.3 누적 | 157 | M1 46 / M2 92 / M3 19 |
| 시스템 SYS | SYS v0.7 누적 | 233 | 기능+비기능+IF 전체 |
| 소프트웨어 SWR | SWR v1.1 | 79 | 상위 36건 커버리지 100% |
| 아키텍처 모듈 | ARCH v1.2 | 89 | M1 50 / M2 36 / M3 3 |

## 3. SYS_SRS 구성표 (v0.4 기준 + 델타)

| 구분 | v0.4 | v0.5~v0.7 델타 내역 | 누적 (v0.7) |
|---|---|---|---:|
| 기능 | 75 | + C등급판정, 외부송신게이트, 보상통제 21, 배포프로파일 등 | 233에 포함 |
| 비기능 | 29 | + 보상통제 2, 벽시계타이머, 키분리, 보존기한 등 | 233에 포함 |
| 인터페이스 | 34 | + 호스티드/NIM, BaaS/SQLite, 알림(카카오 반자동) 등 | 233에 포함 |
| 합계 | 138 | +33 → 171 → +37 → 208 → +25 → 233 | **233** |

## 4. SWR 전개표 (S2, v1.1 정본)

| 상위 그룹 | 상위 건수 | 전개 SWR | 커버리지 |
|---|---|---:|---|
| SEC (보안/등급) | 10 | SEC 계열 포함 73건 중 일부 | 36/36 |
| EGR (외부송신) | 9 | EGR 계열 (게이트·브로커·전송) | 36/36 |
| AUD (감사) | 7 | AUD 계열 + v1.1 추가 2건 (AUD-011, 012) | 36/36 |
| DNY (하드금지) | 3 | DNY + DET 규칙 연계 | 36/36 |
| VEN (벤더) | 3 | VEN + 명부사전 연계 | 36/36 |
| KEY (키/암호) | 4 | KEY + AUD 암호화 연계 | 36/36 |
| D29~D35 파생 | - | AUD-011/012, DET-011/012, EXC-004/005 (6건) | 추가 |
| 합계 | **36** | **79** | **100%** |

### 4-1. v1.1 신규 SWR 6건표

| ID | modality | 요구문 요약 | AC 요약 |
|---|---|---|---|
| SWR-AUD-011 | must | 보존기한 경과 레코드 벽시계 파기 + 파기사실 체인기록 | 파기 후 chain verify 통과 |
| SWR-AUD-012 | must | 키 부재·복호실패 시 신규전송 거부 (fail-closed) | 키 제거 시 send 0건 |
| SWR-DET-011 | must | 명부 미로드 시 실명범주 미탐표기 + 배너경고 | 기동 시 경고 1건 |
| SWR-DET-012 | must_not | 명부부재를 이유로 자동통과 금지 | pass 기록 금지 |
| SWR-EXC-004 | must | TTL 만료 재기동 캐치업 회수 | 96h 후 기동 시 72h 만료 |
| SWR-EXC-005 | must | 예외 부여·사용·만료 각 체인기록 | 1건당 레코드 3종 |

## 5. 마일스톤 배치표

| 마일스톤 | SRS v0.3 (157건 기준) | ARCH v1.2 (89모듈 기준) | 성격 |
|---|---|---|---|
| M1 | 46건 | 50모듈 | LLM 없이 전부 동작. 추적·환경·요구코어·결정·질문큐 / kernel·policy·ports·sqlite·질문·추적·G1 |
| M2 | 92건 | 36모듈 | LLM런타임, 아키텍처~스캐폴딩~대시보드, 렌더링 / transport·BaaS·렌더·에스컬레이션 |
| M3 | 19건 | 3모듈 | 루프백자동판정·릴리스·평가·OCR·L3시뮬 / 루프백·릴리스·G5 |
| 합계 | 157 | 89 | - |

## 6. 프로세스 12단계 5게이트표

| 단계 | 이름 | 산출물 | 게이트 |
|---|---|---|---|
| S0 | 환경세팅·능력협상 | capabilities.json, deploy.yaml | - |
| S1 | 시스템요구사항 분석 | SYS_SRS | G1 요구완결성 |
| S2 | 소프트웨어요구사항 전개 | SWR (입출력·전제·사후·오류·AC) | G2 미확정 0건 |
| S3 | 구현결정 수집 | decisions.csv (3안+추천) | - |
| S4 | 아키텍처 설계 | architecture.md | G3 계약완비 |
| S5 | 인터페이스 계약 | interfaces.csv | G3 계약완비 |
| S6 | 유닛설계 | unit_design.md | - |
| S7 | 마일스톤 배치 | milestones.csv (S4와 병렬) | - |
| S8 | TODO 전개 | todo.csv | G4 TODO-테스트연결 |
| S9 | 검증·루프백판정 | verification report | G4 TODO-테스트연결 |
| S10 | 스캐폴딩 | 소스트리 | - |
| S11 | 시각화·릴리스 | 다이어그램, 최종산출물 | G5 AC100%+라인70% |

### 6-1. 루프백·질문 규칙표

| 항목 | 규칙 |
|---|---|
| 루프백 판정 | 규칙표 12케이스 고정, LLM판정 금지 / 동일상위 파생모순→상위원인 / 동일결함 2회→1계층 상위승격 |
| 질문 | Top-k 3+추천, score=w1영향+w2불확실+w3차단-w4비용, MMR 중복제거 |
| 가정 | 무응답 시 추천안 assumption 채택, 단 보안·법규·정합성은 BLOCKED 유지 |
| 에스컬레이션 | L0→L1→L2→L3 = 4h/24h/48h, 업무시간 정지 |
| 채널 | CLI 단독, internal CLI큐 / customer 카카오링크, customer 내부큐 노출금지 |

## 7. 핵심 결정표

| ID | 주제 | 확정 내용 | 상태 |
|---|---|---|---|
| A01~A07 | 전제(입력·산출물4종·CLI·도메인팩·RAG·Hermes·실측금지) | 문서·CLI·공통코어+3팩·승인문서RAG·ID하드코딩·최악값고정 | 확정 |
| Q2/Q3/Q5 | 승인·에스컬·수락 | 카카오링크+단일승인자 / 4h24h48h / AC100%+라인70% fail-closed | 확정 |
| Q12 | 기밀등급 | C0/C1/C2 신설, 미지정=C1 | 확정 |
| D20 | P0 외부전송 | P0 전면허용+사후감사, 하드금지3범주(개인정보/크리덴셜/실명+계약) 무조건차단 | 확정 |
| D21 | 추론배치 | 호스티드 유지, self-host 조건부전환 | 확정 |
| D25 | 실행호스트 | 로컬PC 단독, 벽시계 필수 | 확정 |
| D26 | 고객폼 | P0 반자동→M2 공개노드 | 확정 |
| D28 | NGC키 | 호스티드키만, NGC pull 보류 | 확정 |
| D29 | 게이트강제 | TransportPort.send(req, decision) 필수인자 | 확정(v1.1) |
| D30 | 판정우선순위 | deny_hard > allowlist > mode, 코드상수 | 확정(v1.1) |
| D31 | 원문보관 | 전량보관+암호화+90d파기 | 확정(v1.1) |
| D32 | 감사무결성 | SHA256체인+WAL, 실패 시 전송중단 | 확정(v1.1) |
| D33 | 정책로드실패 | 스키마·reviewed_on 검증, fail-closed | 확정(v1.1) |
| D34 | 탐지기 | 정규식+엔트로피+명부, NER/LLM 배제 | 확정(v1.1) |
| D35 | 오탐예외 | 단일승인자 건별, TTL72h 갱신1회 | 확정(v1.1) |
| D36~D42 | S3 신규(지문·스키마·체크포인터·동시성·mmd·마커·venv) | HMAC지문·마이그레이션정본·SqliteSaver·단일프로세스·mmd·영역마커·venv | 제안(ARCH v1.2) |

## 8. 확정 파라미터표 (11종)

| 파라미터 | 값 | 출처 | 상태 |
|---|---|---|---|
| AUD.retention_days | 90 | D31 | 잠정(사내규정 후 재설정) |
| AUD.encryption | AES-256-GCM | D31 | 확정 |
| AUD.key_location | OS키링, 부재 시 파일 mode600 | D31 | 확정 |
| AUD.purge_clock | wall_clock | D31 | 확정 |
| AUD.chain_algo | sha256(prev_hash\|\|record) | D32 | 확정 |
| AUD.write_ahead | intent→send→outcome 2단 | D32 | 확정 |
| EXC.ttl_hours | 72 | D35 | 잠정 |
| EXC.max_renewals | 1 | D35 | 잠정 |
| EXC.scope | (item_id, category, payload_hash) | D35 | 확정 |
| EXC.expiry_clock | wall_clock | D35 | 확정 |
| DET.roster_dict | 미확보 | D34 | 미해결 |
| SWR-DET-007 지연 | 500ms | v1.0 이월 | 잠정(5회 중앙값 교체) |

## 9. 아키텍처·인터페이스 요약표

| 층 | 패키지 | 허용참조 | 비고 |
|---|---|---|---|
| L0 kernel | 순수도메인 | 없음 | I/O·시간·난수 금지 |
| L1 policy | 규칙엔진 | kernel | 부작용 없음, Decision 유일발행 |
| L2 ports | 추상IF | kernel | Protocol 11종/22메서드 |
| L3 app | 오케스트레이션 | kernel,policy,ports | 유일송신통로 egress_broker |
| L4 adapters | 기술결합 | kernel,ports (policy금지) | 소켓은 transport_https만 |
| L5 cli | 합성루트 | 전부 | run/ask/audit/conformance |

| 포트 | 대표 메서드 | 핵심 계약 |
|---|---|---|
| StorePort | save/load/find/link/neighbors/transaction | 멱등ID, 선언순서고정, 순환거부 |
| TransportPort | send(req,decision)/health | Decision지문 불일치 시 거부 |
| LLMPort | structured/capabilities | 실패→unknown슬롯, 최악값고정 |
| Doc/Index | load/search | ID플레이스홀더, BM25+임베딩 결정적순서 |
| Notify | notify | customer는 생성까지만(반자동) |
| Clock | now() | 벽시계만, monotonic 미노출 |
| Audit | begin/commit/verify | WAL실패=전송중단 |
| Render/Scaffold/Metrics | render/plan·apply/record | SpecModel단일정본, 덮어쓰기금지 |

송신 순서: `classify → gate → audit.begin(WAL) → transport.send(req,decision) → audit.commit`

## 10. 미해결·차단표

| # | 항목 | 영향 | 필요한 것 |
|---|---|---|---|
| A1 | egress_policy.yaml reviewed_on 2건 TODO | fail-closed 기동거부 | 약관확인일자 기입 |
| A2 | 감사키 미설정 | 전송거부 | 키링 또는 mode600 파일 |
| B1 | 명부사전 미확보 | 실명탐지 공백 | 고객사·인명사전 |
| B2 | 기획서샘플 미확보 | 입도·파서튜닝 불가 | 샘플 1건 (합성대체 중) |
| B3 | 골든셋 미확보 | 지표기준선 없음 | 완료기능 3건 역산 |
| C | 90d/72h/1회/500ms 잠정값 | 운영 후 재설정 | 5회 관측값 |
| D | Q11 GPU한도 양의적 | 설계영향 없음 | self-host 시 재확인 |
| E | CR-09 상위역류 | SWR-EGR-013 SYS 미반영 | SYS_SRS 역반영 필요 |
| - | 추적ID 대조 | 커버리지검증 불가 | v0.4~v1.0 CSV 대조 |
| - | D19/D22/D27 제목 | 요약만 존재 | 원본 decisions CSV 참조 |

## 11. 원본 위치표

| 파일 | 위치 | 비고 |
|---|---|---|
| FR/SRS/SYS/SWR 원본 (v0.1~v1.0) | 대화첨부 (개별다운로드) | MANIFEST_missing_originals.md 참조 |
| v1.1 정본 | AI_pipeline_confirmed_v1.1/10_confirmed_originals/ | decisions/locked_params/SWR_additions |
| 재구성 대장 | AI_pipeline_confirmed_v1.1/20_reconstructed/ | 건수·파이프라인·미해결 |
| S3 설계 정본 | ARCH_S3_v1.2/ARCH_S3_v1.2.md + csv/toml/py/mmd | D36~D42, 6층, 89모듈 |
| 본 문서 | ./SRS.md (루트, main) | 대장용 요약, 요구문 전문 대체 불가 |
