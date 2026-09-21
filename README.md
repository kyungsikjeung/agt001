# agt001

이 저장소는 두 가지 문서 묶음을 담고 있다.

1. **`reqpipe`** — 기획서를 넣으면 요구사항 명세·아키텍처를 자동 생성하는 AI 드리븐 파이프라인의 기존 설계 문서
2. **NVIDIA 해커톤 프로젝트** — `reqpipe`의 개념(요구사항 접수→검증→질의→게이트→RAG)을 챗봇형 멀티에이전트 시스템으로 확장한 신규 프로젝트 (제출 기한 2026-09-28)

두 묶음은 서로 다른 목적을 갖지만, 해커톤 프로젝트는 `reqpipe`의 게이트·RAG·감사 개념을 재사용하므로 함께 보관한다.

## 시스템 블루프린트 (한눈에 보기)

해커톤 프로젝트(고객 채팅 → 코드 산출물) 전체를 압축한 그림이다. 번호(①~⑰)는 [docs/hackathon/ARCHITECTURE.md §1](docs/hackathon/ARCHITECTURE.md#1-시스템-컨텍스트-전체-그림)의 전체 번호 체계와 동일하며, 상세 설명·팀원별 담당은 그 문서를 본다.

```mermaid
flowchart LR
    CUST(("① 고객")) -->|채팅| CHAT["② 챗봇"]
    CHAT --> RAG["③ RAG\n기존요구 확인"]
    RAG --> INTAKE["④ 접수"] --> VALIDATE["⑤ 검증"] --> ASK["⑥ 질의\n3안+추천"]
    ASK --> GATE{"⑦ 승인게이트"}
    GATE -->|반려| ASK
    GATE -->|승인| QUOTE["⑧ 견적+근거"]
    QUOTE --> DESIGN["⑨ UI 시안"] --> LINK["⑩ 시안링크"]
    GATE --> SPEC["⑫ 스펙생성"] --> PLAN["⑬ Hermes 플래너"]
    PLAN --> WEB["⑭ 웹 코드"]
    PLAN --> AND["⑮ 안드로이드 코드"]
    WEB --> BUILD["⑯ 빌드/배포"]
    AND --> BUILD
    BUILD --> DEPLOY["⑰ 배포본"]
    LINK --> DELIVER["⑪ 카카오링크 전송"]
    DEPLOY --> DELIVER
    DELIVER --> CUST

    classDef teamA fill:#e8f0fe,stroke:#4285f4
    classDef teamB fill:#fef7e0,stroke:#f9ab00
    classDef teamC fill:#e6f4ea,stroke:#34a853
    class CHAT,RAG,INTAKE,VALIDATE,ASK,GATE,QUOTE teamA
    class DESIGN,LINK,DELIVER teamB
    class SPEC,PLAN,WEB,AND,BUILD,DEPLOY teamC
```

> 파랑=팀원 A, 노랑=팀원 B, 초록=팀원 C. 경계별 데이터 계약은 [INTEGRATION_STRATEGY.md §1](docs/hackathon/INTEGRATION_STRATEGY.md#1-계약-우선-원칙--경계boundary-정의)에 정의되어 있다.

## 사용자 시나리오 예시

같은 시스템이 상황에 따라 어떻게 다르게 움직이는지, 대표 시나리오 4가지를 시퀀스로 그렸다.

### 시나리오 1 — 정상 경로 (한 번에 승인, 신규 요구)

```mermaid
sequenceDiagram
    actor 고객
    participant 챗봇 as ②챗봇
    participant RAG as ③RAG
    participant 게이트 as ⑦게이트
    participant 견적 as ⑧견적
    participant 시안 as ⑨시안
    participant 배포 as ⑰배포

    고객->>챗봇: "쇼핑몰 웹사이트 만들고 싶어요"
    챗봇->>RAG: 기존 프로젝트 유사도 검색
    RAG-->>챗봇: 신규 요구 (유사 프로젝트 없음)
    챗봇->>게이트: 정리된 요구 + 확인 요청
    고객->>게이트: "네, 맞아요" (승인)
    게이트->>견적: 승인된 요구 전달
    견적-->>고객: 견적 + 산정 근거
    게이트->>시안: 개발 착수 트리거 (팀C 병렬 시작)
    시안-->>고객: 시안 링크 (카카오)
    고객->>시안: 시안 A 선택
    배포-->>고객: 최종 접속 링크 (카카오)
```

### 시나리오 2 — RAG가 기존 프로젝트를 발견 (재사용 경로)

```mermaid
sequenceDiagram
    actor 고객
    participant 챗봇 as ②챗봇
    participant RAG as ③RAG
    participant 질의 as ⑥질의

    고객->>챗봇: "지난번에 만든 예약 시스템에 결제만 추가해주세요"
    챗봇->>RAG: 기존 프로젝트 유사도 검색
    RAG-->>챗봇: 기존 요구 발견 (유사도 0.9, "예약 시스템 v1")
    챗봇->>질의: "기존 프로젝트를 확장하는 것이 맞습니까?" (옵션 3개+추천)
    Note right of 질의: 옵션1: 기존 확장(추천)<br/>옵션2: 신규 별도 구축<br/>옵션3: 기존 마이그레이션 후 확장
    고객->>질의: 옵션1 선택
    질의->>챗봇: 기존 요구 위에 결제 기능만 증분 접수
```

### 시나리오 3 — 검증 실패 → 재질의 → 승인 (반려 경로)

```mermaid
sequenceDiagram
    actor 고객
    participant 검증 as ⑤검증
    participant 질의 as ⑥질의
    participant 게이트 as ⑦게이트

    고객->>검증: "관리자 페이지도 있었으면 좋겠어요" (모호)
    검증-->>질의: 권한 범위 불명확
    질의->>고객: 옵션 3개 + 추천\n(1.전체관리자 2.제한관리자(추천) 3.관리자없음)
    고객->>질의: "2번이요"
    질의->>게이트: 확정안 제출
    고객->>게이트: 최종 확인 (승인)
    게이트-->>고객: 승인 완료, 다음 단계(견적) 진행
```

### 시나리오 4 — 배포 실패 처리 (실패 경로)

```mermaid
sequenceDiagram
    participant 빌드 as ⑯빌드/배포
    participant 배포 as ⑰배포본
    participant 전송 as ⑪전송
    actor 고객

    빌드->>빌드: 코드 빌드 시도
    Note over 빌드: 빌드 실패 (의존성 오류)
    빌드->>빌드: 1회 재시도
    Note over 빌드: 재시도도 실패
    빌드->>배포: status: "failed" 전파
    배포->>전송: 실패 상태 + 사유
    전송-->>고객: "죄송합니다, 배포 중 문제가 발생해 확인 중입니다" (깨진 링크 대신 상태 안내)
    Note over 전송,고객: 실패 시 링크를 보내지 않는 것이 핵심 (INTEGRATION_STRATEGY.md §5 리스크 참고)
```

## 폴더 구조

```
agt001/
├── README.md                          # 이 파일 — 전체 안내
├── docs/
│   ├── reqpipe/                       # 기존 reqpipe 시스템 문서 (읽는 순서: 01→02→03)
│   │   ├── 01_OVERVIEW_AND_HISTORY.md #   버전 이력·결정 근거 아카이브
│   │   ├── 02_REQUIREMENTS.md         #   ★ 정본 요구사항 ("시스템은 ~해야 한다", G01~G18)
│   │   ├── 03_SPEC.md                 #   구현 스펙 (API/데이터모델/상태/배포 + 부록 RAG·환경·구현전략)
│   │   └── archive/                   #   원본 근거자료 (CSV·mmd·toml 원문, 수정하지 않음)
│   │       ├── ARCH_S3_v1.2/          #     아키텍처 설계 원본 (모듈89·인터페이스22·다이어그램)
│   │       └── AI_pipeline_confirmed_v1.1/  # 결정 로그·파라미터 원본
│   └── hackathon/                     # NVIDIA 해커톤 신규 프로젝트 문서
│       ├── ARCHITECTURE.md            #   ★ 전체 아키텍처 (팀 역할분담·Mermaid·에이전트 구성)
│       ├── INTEGRATION_STRATEGY.md    #   팀원별 통합 전략 + 일자별 상세 마일스톤(D0~D7)
│       └── deployment/
│           ├── RENDER_DEPLOY.md       #     배포 가이드 (배경/목적/핸즈온, AI 에이전트 온보딩용)
│           ├── templates/             #     Dockerfile·render.yaml 템플릿
│           └── scripts/warmup.sh      #     콜드스타트 워밍업 스크립트
```

## 읽는 순서

### 처음 합류하는 팀원 (해커톤 작업을 할 사람)

1. 이 README — 전체 그림 파악
2. [docs/hackathon/ARCHITECTURE.md](docs/hackathon/ARCHITECTURE.md) — 시스템 컨텍스트, 팀원별 역할, 확정된 기술 결정
3. [docs/hackathon/INTEGRATION_STRATEGY.md](docs/hackathon/INTEGRATION_STRATEGY.md) — 내가 맡은 파트를 오늘부터 어떻게 시작할지(D0~D7 마일스톤)
4. [docs/hackathon/deployment/RENDER_DEPLOY.md](docs/hackathon/deployment/RENDER_DEPLOY.md) — 실제 배포를 맡았다면 여기까지
5. 필요 시 [docs/reqpipe/02_REQUIREMENTS.md](docs/reqpipe/02_REQUIREMENTS.md) — 재사용 중인 게이트/RAG/감사 개념의 원래 정의를 참고

### reqpipe 자체를 개발/검토할 사람

1. [docs/reqpipe/02_REQUIREMENTS.md](docs/reqpipe/02_REQUIREMENTS.md) — ★ 정본. "무엇을 만들어야 하는가"
2. [docs/reqpipe/03_SPEC.md](docs/reqpipe/03_SPEC.md) — "어떻게 코드로 옮기는가" (API·데이터모델·상태·배포)
3. [docs/reqpipe/01_OVERVIEW_AND_HISTORY.md](docs/reqpipe/01_OVERVIEW_AND_HISTORY.md) — 왜 지금 이 모습인지 근거가 필요할 때만
4. `docs/reqpipe/archive/` — 원본 CSV·다이어그램·결정 로그 (01/03 문서가 요약하며 링크하는 원본, 직접 열 필요는 거의 없음)

## 문서 작성 규칙 (이 저장소 공통)

- 각 문서는 상단에 **성격**(정본/아카이브/구현스펙 등)과 **개요**, **목차**, 필요 시 **용어집**을 둔다.
- 같은 표·다이어그램을 두 곳에 복사하지 않는다. 원본 위치를 정하고, 다른 문서에서는 링크만 한다 (`docs/reqpipe/01_OVERVIEW_AND_HISTORY.md` §8·§11 참고 — 아키텍처 원본은 `archive/ARCH_S3_v1.2/`가 정본).
- 용어는 [docs/reqpipe/02_REQUIREMENTS.md의 용어집](docs/reqpipe/02_REQUIREMENTS.md#02-용어집-한자어영어-약어-첫-등장-풀어쓰기)을 공통 정본으로 삼고, 각 하위 문서는 그 문서에서만 쓰는 용어만 추가로 정의한다 (예: [docs/hackathon/ARCHITECTURE.md §0.1](docs/hackathon/ARCHITECTURE.md#01-용어-이-문서-한정)).
