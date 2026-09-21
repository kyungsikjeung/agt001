# S3 아키텍처 설계 — reqpipe v1.2

확정 기준: D1~D35(v1.1 정본) + 본 문서에서 신규 제안하는 D36~D42.
본 문서는 레이어 구성, 파일별 역할, 컴포넌트 간 인터페이스 계약, 의존 규칙, 마일스톤 배치를 정의한다.

> 전제 고지 — 작업 세션 초기화로 v0.4~v1.0 원본 CSV를 재열람하지 못했다.
> 추적 컬럼의 상위 ID는 대화 본문에 명시적으로 등장한 것만 기재했고,
> 원본 CSV와 대조해 보정해야 한다(미해결 항목 참조).

## 1. 설계를 규정한 3개의 확정 사항

1. **D29-A (Decision 필수 인자)** — `TransportPort.send(req, decision)`. 게이트를 거치지 않은 외부 송신은
   정적검사로 적발하는 것이 아니라 **작성 자체가 불가능**하다. 이 한 줄이 레이어 경계를 결정한다.
2. **D25-A (로컬 PC 단독)** — 상시 가동이 아니다. 모든 시간 계산은 벽시계이며 재기동 캐치업이 필수다.
   상태는 단일 작업 디렉터리에 모여야 하고(SF-HOST-06), 코어는 클라우드 SDK를 알지 못한다(SF-HOST-01).
3. **D20-C (P0 전면 허용 + 사후 감사)** — 게이트를 제거하지 않고 `mode: audit|enforce`로 둔다.
   따라서 게이트·감사 경로는 P0부터 존재해야 하며, P1 전환은 설정 한 줄이어야 한다.

## 2. 레이어 구성 (6층, 단방향)

```
L5 cli        합성 루트 — 유일하게 adapters 를 안다
L4 adapters   외부 기술 결합(HTTP/DB/FS/LLM/렌더)
L3 app        오케스트레이션(LangGraph 노드·게이트·브로커·질문엔진)
L2 ports      추상 인터페이스(Protocol)
L1 policy     결정적 규칙 엔진(부작용 없음)
L0 kernel     순수 도메인 모델(I/O·시간·난수 금지)
```

| 층 | 패키지 | 허용 참조 |
|---|---|---|
| L0 | kernel | 없음 |
| L1 | policy | kernel |
| L2 | ports | kernel |
| L3 | app | kernel, policy, ports |
| L4 | adapters | kernel, ports (**policy 금지**) |
| L5 | cli | 전부 |

**adapters → policy 를 금지한 이유**가 이 설계의 핵심이다. 어댑터가 정책을 참조할 수 있으면
"이 경우는 예외로 그냥 보내자" 같은 우회가 어댑터 안에서 조용히 생긴다.
정책 판정 결과는 반드시 `EgressDecision` 이라는 **값**으로만 어댑터에 전달된다.

### 2.1 강제 장치 (선언이 아니라 검사)

- `dependency_rules.toml` — import-linter 계약 5종
- `checks/test_layering.py` — 외부 의존 없는 AST 검사. 위반 1건이면 exit 1
- `checks/test_socket_owner.py` — 네트워크 라이브러리 import 는 `adapters/transport_https.py` 만 허용
- `checks/test_leakage.py` — 코어에 도메인 어휘(web/aaos/mcu) 누출 검사, 단어 경계 매칭

## 3. 외부 송신 경로 — 단일 초크포인트

`app/egress_broker.py` 가 외부로 나가는 **유일한 통로**이며 순서를 강제한다.

```
classify → gate(evaluate) → audit.begin(WAL, 원문 포함) → transport.send(req, decision) → audit.commit
```

- `policy/egress_gate.py` 만 `EgressDecision` 을 생성할 수 있다(봉인형 생성자).
- Decision 은 **요청 바이트 지문**을 내장하고, `transport_https` 가 송신 직전 재계산해 대조한다(D36-A).
  지문이 다르면 송신하지 않는다 — 통과된 Decision 을 다른 요청에 재사용하는 TOCTOU 를 막는다.
- `audit.begin` 실패는 곧 송신 중단이다(D32-A). "사후 감사"는 기록이 전량 남을 때만 성립한다.
- 판정 우선순위는 코드 상수다: `deny_hard > allowlist > mode`. 정책 파일이나 P0 전면 허용 모드로
  하드 금지 3범주를 뒤집을 수 없다(D30-A).

## 4. 모듈 배치 (파일별 역할)

| path | layer | 역할 | 추적 | 마일스톤 |
|---|---|---|---|---|
| kernel/ids.py | L0 | 타입 있는 식별자(ReqId/EvId/RunId/NodeId)와 결정적 ID 생성 규칙(해시 기반, 난수 금지) | TRC-01, FR-E08 | M1 |
| kernel/model_project.py | L0 | ProjectContext: 배경·이해관계자·제약·용어. 프로젝트당 1개 | FR-C01 | M1 |
| kernel/model_requirement.py | L0 | Requirement(항목 N개) + SlotValue(dict 기반, 슬롯명 하드코딩 금지) + deps/conflicts | FR-C01, FR-C02 | M1 |
| kernel/model_evidence.py | L0 | Evidence: source_uri·snapshot·commit_sha·nature(normative/descriptive)·derivation(verbatim/derived/inferred) | FR-D01~D03 | M1 |
| kernel/model_assumption.py | L0 | Assumption(safe/risky) + Provisional 플래그와 전파 표식 | PRV-01~05 | M1 |
| kernel/model_question.py | L0 | Question(target, audience=internal\|customer, score 구성요소), Answer | ASK-01, ASK-16 | M1 |
| kernel/model_decision.py | L0 | DecisionRecord: 3안+추천+선택+근거+승인자+확정시각 | DEC-01~ | M1 |
| kernel/model_trace.py | L0 | TraceNode/TraceEdge/LinkType(derives/verifies/implements/conflicts/assumes) | TRC-01~09 | M1 |
| kernel/model_classification.py | L0 | Level(C0/C1/C2), ClassifiedPayload, 상속 규칙의 자료형(최댓값 연산) | SF-SEC-01~06 | M1 |
| kernel/model_egress.py | L0 | EgressRequest / EgressDecision(봉인형, 게이트만 생성) / Verdict / Fingerprint | D29-A, D30-A | M1 |
| kernel/model_artifact.py | L0 | SpecModel 단일 정본 + 4종 산출물 뷰의 식별자 | FR-B01 | M2 |
| kernel/errors.py | L0 | 도메인 예외 계층(정책 위반/무결성/계약 위반 구분) | - | M1 |
| policy/classify.py | L1 | 등급 판정. 미지정 입력은 C1 기본값(fail-safe) | SF-SEC-01,02 | M1 |
| policy/inherit.py | L1 | 파생 산출물 등급 = 입력 근거 등급의 최댓값 | SF-SEC-06 | M1 |
| policy/downgrade.py | L1 | 강등은 승인 레코드 없이는 불가(거부 반환) | SF-SEC-05 | M1 |
| policy/detectors/rules_pii.py | L1 | 개인정보 결정적 규칙(주민·연락처·계좌·이메일 패턴) | SF-DNY-01, D34-A | M1 |
| policy/detectors/rules_credential.py | L1 | 크리덴셜 규칙(키·토큰·PEM·커넥션 스트링) | SF-DNY-01 | M1 |
| policy/detectors/roster_match.py | L1 | 고객사·인명 명부 사전 매칭. 사전 부재 시 pass 반환 금지 | SWR-DET-011,012 | M1 |
| policy/detectors/normalize.py | L1 | 단위·조사·불용어 정규화, 수치 토큰 추출(4열 vs 6열 검출) | S0 결함 2,3 | M1 |
| policy/egress_gate.py | L1 | deny_hard > allowlist > mode(audit\|enforce) 우선순위 상수 고정. EgressDecision 발행 유일 지점 | D30-A, SWR-EGR-003 | M1 |
| policy/exception_ledger.py | L1 | 오탐 예외: 승인자 1인, TTL 72h, 갱신 1회, 벽시계 기준 | D35-A, SWR-EXC-004 | M1 |
| policy/retention.py | L1 | 원문 전량 보관의 보존기한 90일 및 파기 대상 산출(벽시계) | D31-A | M2 |
| policy/timer_policy.py | L1 | 에스컬레이션 4h/24h/48h, 업무시간 정지, 가동시간 기준 금지 | SF-TMR-01,02, ASK-28 | M1 |
| policy/gate_l1_rules.py | L1 | 구조 규칙 13종(근거 실재·스냅샷 일치·수치 일치·순환·충돌 대칭 등) | GATE-L1 | M1 |
| policy/rubric_l2.py | L1 | 루브릭 5축×3점의 채점 계약(프롬프트 비의존 자료형) | GATE-L2 | M2 |
| policy/loopback_rules.py | L1 | 루프백 12케이스 판정표. LLM 판정 금지, 2회 재발 시 상위 승격 | LB-01~12 | M2 |
| policy/profile_schema.py | L1 | 프로파일 YAML의 스키마 검증과 슬롯 속성(required/risk/depends_on) 해석 | FR-C02~C06 | M1 |
| ports/store_port.py | L2 | 영속 계약(StorePort). BaaS/SQLite 공통 | SF-DAT-01, SI-I-02 | M1 |
| ports/transport_port.py | L2 | 외부 송신 계약. send(req, decision) — Decision 필수 인자 | D29-A | M1 |
| ports/llm_port.py | L2 | structured/complete/capabilities. 반환은 kernel 타입 | SI-E-01 | M2 |
| ports/doc_port.py | L2 | 원본 문서 바이트·블록 접근 계약 | FR-A01 | M1 |
| ports/index_port.py | L2 | 하이브리드 검색 계약(BM25+임베딩) | FR-D05 | M2 |
| ports/notify_port.py | L2 | 알림 계약(콘솔/텔레그램/카카오 반자동) | ASK-05~ | M2 |
| ports/clock_port.py | L2 | 벽시계 시각 제공. monotonic 노출 안 함 | SF-TMR-01 | M1 |
| ports/audit_port.py | L2 | begin(WAL)/commit/append/verify_chain | D32-A, SF-AUD-02,07 | M1 |
| ports/render_port.py | L2 | 산출물 4종 및 다이어그램 렌더 계약 | FR-B01, VIZ | M2 |
| ports/scaffold_port.py | L2 | 폴더·파일 생성 계획과 적용 계약 | SCF-01~ | M2 |
| ports/metrics_port.py | L2 | 런 메트릭 기록 계약 | MET-01~04 | M1 |
| app/capability.py | L3 | 부팅 핸드셰이크. 프로브 실패 시 예외 없이 최악값 고정 | FR-H01,H02 | M2 |
| app/llm_call.py | L3 | 구조화 출력 사다리 S0~S3 + 새니타이저(무조건) + 4콜 분할 | FR-G01~, S2 결정 | M2 |
| app/egress_broker.py | L3 | 유일한 외부 송신 통로. gate→WAL→send→commit 순서 강제 | D29-A, D32-A | M1 |
| app/question_engine.py | L3 | Top-k 3개 + 추천. depends_on 보류, 동점은 선언 순서 | FR-E01~E08 | M1 |
| app/interview_session.py | L3 | 인터뷰 루프(최대 5턴). 답변을 interview:// 근거로 기록 | FR-E09 | M1 |
| app/provisional.py | L3 | 고객 대기 항목의 임시 확정과 파생 전파, 릴리스 차단 | PRV-01~05 | M2 |
| app/escalation.py | L3 | L0→L3 단계 진행, 재기동 캐치업, 알림 병합 | ASK-27,28 | M2 |
| app/trace_service.py | L3 | 추적 그래프 생성·질의·영향분석(무엇을 다시 봐야 하는가) | TRC-01~09 | M1 |
| app/metrics.py | L3 | 채움률·자동채택률·질문턴수·citation_miss 집계 | MET-01~04 | M1 |
| app/graph_build.py | L3 | LangGraph 조립. 노드/조건분기/체크포인터 주입 | S1~S12 | M2 |
| app/stages/s01_env.py | L3 | 환경 세팅 단계 노드 | ENV | M1 |
| app/stages/s02_sysreq.py | L3 | 시스템 요구사항 분석 노드 | SYS | M1 |
| app/stages/s03_swreq.py | L3 | 소프트웨어 요구사항 전개 노드 | SWR | M2 |
| app/stages/s04_decision.py | L3 | 결정 3안+추천 생성 노드 | DEC | M2 |
| app/stages/s05_arch.py | L3 | 아키텍처(레이어·컴포넌트·파일역할) 산출 노드 | ARC | M2 |
| app/stages/s06_iface.py | L3 | 인터페이스 계약 산출 노드 | IFC | M2 |
| app/stages/s07_unit.py | L3 | 유닛 설계 노드 | UNT | M2 |
| app/stages/s08_todo.py | L3 | TODO 구현 리스트 전개 노드 | TSK | M2 |
| app/stages/s09_verify.py | L3 | 검증 실행 및 결함 수집 노드 | VER | M2 |
| app/stages/s10_loopback.py | L3 | 루프백 계층 판정 노드(규칙 기반) | LB | M3 |
| app/stages/s11_scaffold.py | L3 | 폴더·파일 생성 및 역할 분리 적용 노드 | SCF | M2 |
| app/stages/s12_release.py | L3 | 최종 산출물 패키징 노드 | REL | M3 |
| app/gates/g1_reqready.py | L3 | 게이트1: 요구사항 완결성 | GATE | M1 |
| app/gates/g2_decided.py | L3 | 게이트2: 미확정 결정 0건 | GATE | M2 |
| app/gates/g3_archready.py | L3 | 게이트3: 인터페이스 계약 완비 | GATE | M2 |
| app/gates/g4_impl.py | L3 | 게이트4: TODO-테스트 연결 | GATE | M2 |
| app/gates/g5_accept.py | L3 | 게이트5: AC 100% + 신규코드 라인 70%, 측정 실패는 불통과 | VER-12, Q5 | M3 |
| adapters/store_sqlite.py | L4 | 로컬 단독 실행용 StorePort 구현(P0 기본) | D25-A | M1 |
| adapters/store_baas.py | L4 | BaaS StorePort 구현. 코어에 벤더 심볼 노출 금지 | SF-DAT-01~06 | M2 |
| adapters/transport_https.py | L4 | 유일한 소켓 보유 모듈. Decision 지문 검증 후 송신 | D29-A, SF-EGR-08 | M2 |
| adapters/llm_openai_compat.py | L4 | NIM 호스티드 /v1/chat/completions, ready/live 분리 확인 | SI-E-01, SF-AI-02 | M2 |
| adapters/llm_replay.py | L4 | 픽스처 재생. 소켓 생성 0건 | SF-EGR-08 | M1 |
| adapters/doc_loader.py | L4 | 표 평탄화·병합셀 forward-fill·이미지 ID 플레이스홀더·문장 ID 부여 | FR-A01~A08 | M1 |
| adapters/modality_tagger.py | L4 | 어미 사전 1차 분류 + 미해결분만 LLM 위임 | FR-A05,A06 | M1 |
| adapters/index_hybrid.py | L4 | BM25 + 임베딩 병행. 설정키·플래그 원형 보존 | FR-D05 | M2 |
| adapters/notify_console.py | L4 | 로컬 콘솔 알림(P0 기본) | ASK-05 | M1 |
| adapters/notify_telegram.py | L4 | 내부 담당자 알림 | ASK-06 | M2 |
| adapters/notify_kakao_manual.py | L4 | 고객 링크 반자동: 메시지·링크 생성까지, 발송은 사람 | D26-A | M2 |
| adapters/clock_system.py | L4 | 시스템 벽시계(타임존 고정) | SF-TMR-01 | M1 |
| adapters/audit_chain.py | L4 | append-only 해시 체인 + WAL 파일 | D32-A | M1 |
| adapters/render_markdown.py | L4 | 산출물 4종 렌더(단일 SpecModel에서 파생) | FR-B01 | M2 |
| adapters/render_diagram.py | L4 | 단계별 최적 다이어그램 생성(.mmd 텍스트 산출) | VIZ-01~04 | M2 |
| adapters/scaffold_fs.py | L4 | 파일 생성. 사람 수정 영역 덮어쓰기 금지 | SCF-02 | M2 |
| cli/__main__.py | L5 | 엔트리포인트. run/ask/audit/conformance 서브커맨드 | - | M1 |
| cli/wiring.py | L5 | DI 합성 루트. deploy.yaml 프로파일로 어댑터 선택 | SF-HOST-01 | M1 |
| cli/commands_run.py | L5 | 파이프라인 실행 | - | M2 |
| cli/commands_ask.py | L5 | 질문 큐 조회·응답 입력(내부 전용, customer 항목 비노출) | ASK-16 | M1 |
| cli/commands_audit.py | L5 | 감사 로그 조회·체인 검증·enforce 전환 시뮬레이션 | SWR-EGR-013 | M2 |
| checks/test_layering.py | L5 | 의존 방향 정적검사(AST). 위반 1건이면 실패 | D29-A 보조 | M1 |
| checks/test_leakage.py | L5 | 코어 도메인 어휘 누출 검사(단어 경계 매칭) | FR-C02 | M1 |
| checks/test_socket_owner.py | L5 | 소켓/HTTP 라이브러리 import는 transport_https.py만 허용 | SF-EGR-08 | M1 |

## 5. 인터페이스 계약 (무엇을 주고받는가)

포트 11종 / 메서드 22개. 모든 입출력은 kernel 타입이며 어댑터 타입이 경계를 넘지 않는다.

| port | method | 입력 | 출력 | 오류 | 비고 |
|---|---|---|---|---|---|
| StorePort | save(entity) -> EntityId | kernel 엔티티(등급 필드 포함) | EntityId | IntegrityError, PolicyError | 동일 입력 재호출 시 동일 ID(멱등) |
| StorePort | load(id, type) -> Entity \| None | EntityId, 타입 | 엔티티 | NotFound 없음(None 반환) | 읽기 전용 |
| StorePort | find(type, filter, order) -> list | 타입, 필드 필터, 정렬키 | 엔티티 목록 | QueryError | 정렬키 미지정 시 선언 순서 고정(난수 금지) |
| StorePort | link(src, dst, link_type) -> EdgeId | 두 노드 ID + LinkType | EdgeId | CycleError(requires 순환) | 멱등 |
| StorePort | neighbors(id, link_type, dir) -> list | 노드 ID, 링크 타입, 방향 | 노드 목록 | - | 영향분석의 기반 |
| StorePort | transaction() -> ctx | - | 컨텍스트 매니저 | TxError | BaaS/SQLite 양쪽에서 동일 의미 |
| StorePort | schema_version() -> str | - | 마이그레이션 버전 | - | 콘솔 수기 변경 감지에 사용 |
| TransportPort | send(request, decision) -> Response | EgressRequest + EgressDecision(필수) | Response | GateBypass, FingerprintMismatch, TransportError | Decision 지문이 요청 바이트와 불일치하면 송신 거부 |
| TransportPort | health(kind) -> Status | ready \| live | 상태 | - | 추론 성공 여부로 준비 판정 대체 금지 |
| LLMPort | structured(schema, prompt, budget) -> (obj, usage) | JSON 스키마, 프롬프트, 토큰 예산 | 검증된 객체 + 사용량 | StructuredFailure(→ unknown 슬롯) | S0~S3 사다리 내부 처리, 호출부 불변 |
| LLMPort | capabilities() -> Caps | - | ctx_len, json_schema, tool_parser | - | 프로브 실패 시 최악값(32768/S3/always) |
| DocPort | load(uri) -> RawDoc | 문서 URI | 블록 목록 + 페이지·문장 ID | DocError | 이미지는 ID 플레이스홀더로 보존 |
| IndexPort | search(query, k, filters) -> list[Chunk] | 질의, k, 등급 필터 | 청크 + source_uri/commit_sha/snapshot | - | BM25+임베딩 병행, 결과 순서 결정적 |
| NotifyPort | notify(channel, audience, message, link) -> Receipt | 채널, 대상, 본문, 링크 | 영수증(발송 여부 포함) | NotifyError | customer 대상은 반자동(생성까지만) |
| ClockPort | now() -> datetime(tz) | - | 벽시계 시각 | - | monotonic 미노출(정책이 오용 불가) |
| AuditPort | begin(record) -> WalId | 송신 예정 레코드(원문 포함) | WAL ID | AuditWriteError(→ 송신 중단) | 기록 실패 시 전송 금지 |
| AuditPort | commit(wal_id, result) -> None | WAL ID, 응답 요약 | - | AuditWriteError | 체인 해시 갱신 |
| AuditPort | verify_chain() -> Report | - | 무결성 리포트 | - | append-only 위반 탐지 |
| RenderPort | render(kind, spec) -> bytes | 산출물 종류, SpecModel | 파일 바이트 | RenderError | 4종 모두 동일 SpecModel에서 파생 |
| ScaffoldPort | plan(arch) -> FilePlan | 아키텍처 모델 | 생성/수정 계획 | - | 적용 전 사람 확인 가능 |
| ScaffoldPort | apply(plan, mode) -> Report | 계획, new_only\|merge | 결과 | OverwriteBlocked | 사람 수정 영역 덮어쓰기 금지 |
| MetricsPort | record(metric) -> None | 런 메트릭 | - | - | 임계 초과 시 CLI 경고 |

### 5.1 계약에서 특히 중요한 3가지

- **ClockPort 가 monotonic 을 노출하지 않는다.** 정책이 가동시간 기준 타이머를 만들 수단 자체를 제거한다(SF-TMR-01).
- **StorePort.find 는 정렬키 미지정 시 선언 순서를 쓴다.** 리플레이 재현성의 전제이며, 질문 순서 난수 금지(FR-E08)와 같은 원칙이다.
- **LLMPort.structured 는 실패를 예외로 던지지 않고 `unknown` 슬롯으로 귀결시킨다.** LLM 실패가
  "사람에게 묻기"라는 기존 정상 경로로 합류하므로, 별도 에러 분기가 필요 없다.

## 6. 상태 영속과 동시성

- 체크포인터는 SqliteSaver, 작업 디렉터리 하나에 DB·WAL·픽스처·산출물을 모은다(D38-A).
  로컬 단독 실행이라 재기동이 잦고, 디렉터리 복사만으로 OCI 로 이전 가능해야 한다.
- 동시성은 단일 프로세스 + 스레드풀이며 병렬은 **추출 4콜에 한정**한다(D39-A).
  전면 async 는 리플레이 재현성과 디버깅 비용만 키운다.

## 7. 마일스톤 배치 (아키텍처와 병렬)

| 단계 | 모듈 수 | 내용 | 외부 의존 |
|---|---|---|---|
| M1 | 50 | kernel·policy 전량, ports 전량, sqlite/doc_loader/audit_chain/replay, 질문엔진·추적그래프·게이트1 | **없음(GPU·네트워크 불요)** |
| M2 | 36 | LLM 런타임, transport, BaaS, 렌더·다이어그램·스캐폴딩, 에스컬레이션·provisional | 호스티드 엔드포인트 |
| M3 | 3 | 루프백 자동판정, 릴리스 패키징, 최종 수락 게이트 | 골든셋 필요 |

M1 50개 모듈은 네트워크 차단 상태에서 전량 테스트된다(NF-AVL-02). 실측을 하지 않기로 한 결정과
동일한 원리다 — 모르는 값에 의존하지 않는 범위를 먼저 완성한다.

## 8. 신규 결정 D36~D42 (3안 + 추천)

| id | 주제 | A안 | B안 | C안 | 추천 | 근거 |
|---|---|---|---|---|---|---|
| D36 | Decision 위조·재사용 방지 | A. 요청 바이트 지문(HMAC) 내장 + 어댑터 검증 | B. 타입 시스템만 의존(봉인 생성자) | C. 세션 토큰 방식 | A | B는 같은 Decision을 다른 요청에 재사용하는 TOCTOU를 막지 못함. A는 지문 불일치 시 어댑터가 거부. |
| D37 | 저장 스키마 정본 | A. 마이그레이션 파일이 정본(콘솔 변경 금지·검출) | B. ORM 모델이 정본 | C. BaaS 콘솔이 정본 | A | SF-DAT-04 준수. 콘솔 수기 변경은 schema_version 불일치로 기동 시 검출. |
| D38 | 그래프 상태 영속 | A. SqliteSaver 체크포인터 + 작업디렉터리 단일화 | B. 단계별 JSON 스냅샷 | C. 메모리(재시작 시 소실) | A | 로컬 단독(D25-A)에서 PC 재기동이 잦음. 캐치업 타이머와 동일 저장소에 둠. |
| D39 | 동시성 모델 | A. 단일 프로세스 + 스레드풀(추출 4콜 병렬만) | B. asyncio 전면 | C. 멀티프로세스 | A | 병렬이 필요한 지점은 LLM 4콜뿐. 전면 async는 리플레이 재현성과 디버깅 비용만 키움. |
| D40 | 다이어그램 생성 | A. .mmd 텍스트 산출 + 뷰어는 외부 | B. graphviz 바이너리 의존 | C. 직접 SVG 생성 | A | 텍스트라 diff·버전관리가 되고 추가 의존이 없음. 진행상황은 커밋 이력으로 추적. |
| D41 | 스캐폴딩 쓰기 안전장치 | A. 생성영역 마커 + 마커 밖 수정은 보존 | B. 신규 파일만 생성, 기존은 손대지 않음 | C. 전체 덮어쓰기 후 git diff 의존 | A | SCF-02(사람 코드 덮어쓰기 금지)를 파일 단위가 아니라 영역 단위로 지켜야 재생성이 실용적임. |
| D42 | 배포 형태 | A. 단일 파이썬 패키지 + venv(로컬) | B. 도커 이미지 | C. pipx 배포 | A | P0는 로컬 단독(D25-A)이고 GPU 불필요. 도커는 OCI 전환 시점(M2)에 재검토. |

## 9. 다이어그램

- `diagrams/01_layers.mmd` — 레이어 의존 구조(금지 화살표 포함)
- `diagrams/02_egress_sequence.mmd` — 외부 송신 1건의 시퀀스(게이트·WAL·지문검증)
- `diagrams/03_loopback_state.mmd` — 검증 결과에 따른 루프백 계층 전이

텍스트(.mmd)로 산출하므로 diff·버전관리가 되고 추가 바이너리 의존이 없다(D40-A).

## 10. 미해결 (S3 를 막지는 않으나 구현 전 해소 필요)

| 항목 | 성격 | 영향 |
|---|---|---|
| 추적 컬럼의 상위 ID 대조 | 세션 초기화로 원본 CSV 미열람 | 커버리지 검증 불가 — v0.4~v1.0 CSV 와 대조 필요 |
| `egress_policy.yaml` 의 `reviewed_on` 2건 | 실행 차단 | D33-A fail-closed 로 기동 거부 |
| 고객사·인명 명부 사전 | 기능 공백 | 하드 금지 3범주 중 1범주 실효 없음 |
| `retention 90d / TTL 72h / 500ms` | 근거 없는 잠정값 | 운영 5회 후 재설정 |
| CR-09 상위 역류 | 미반영 | SWR-EGR-013 이 SYS_SRS 에 없음 |
