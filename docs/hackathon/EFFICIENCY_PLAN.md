# 효율화 계획 (EFFICIENCY_PLAN)

> 작성일: 2026-09-23 / 1차 완성 목표: 2026-09-28 (D+5)
> 성격: 분석 + 계획 문서. **코드는 수정하지 않는다.**
> 조사 범위: `backend.py` 전체(547줄), `docker-compose.yml`, `requirements.txt`,
> `docker/hermes-sandbox/Dockerfile`, `docs/hackathon/deployment/templates/Dockerfile.backend`,
> `static/index.html`, `templates/variant-1.html`, `scripts/check_oci_cost.sh`,
> `docs/hackathon/*.md` 전체(ARCHITECTURE / REQUIREMENTS / INTEGRATION_STRATEGY /
> PARALLEL_1·2·3_SPEC / PM_ORCHESTRATION / ENVIRONMENT / LOCAL_SETUP / RESPONSIVE_SPEC),
> `STATUS.md`, `contracts/`, git 로그.
> 제약: `.env` 미열람, git add/commit/push 없음.

## 0. 지금 당장 할 가치가 있는 것 Top 3

마감까지 5일, thin-slice 관통이 이미 끝난 상태(STATUS.md 전 단계 ✅)이므로
"데모 당일 죽는 위험"을 가장 싸게 제거하는 순서로 뽑았다.

| 순위 | 항목 | 이유 (한 줄) | 작업량 |
|---|---|---|---|
| **1** | **세션 파일 백업** — `SESSIONS`를 재시작해도 살아남게 (`generated/sessions.json` 주기 저장 + 기동 시 로드) | 재배포·컨테이너 재시작 한 번이면 진행 중 대화가 전부 증발하는 현재 구조는 데모 킬러. 파일 저장/로드 수십 줄로 완화 가능 | 하 |
| **2** | **NIM 호출 타임아웃 + 실패 폴백 통일** — `call_nim`/`get_embedding`에 타임아웃을 걸고, `build_quote`의 API 예외를 500이 아닌 폴백 응답으로 | `rag_precheck`에만 폴백이 있고 견적 단계는 NIM 장애 시 `/chat`이 500으로 죽는다. 데모 중 NIM 한 번 흔들리면 시연 중단 | 하 |
| **3** | **배포 스크립트화 + 조건부 빌드** — `scripts/deploy.sh`(SSH+rsync+compose)를 만들고 `Dockerfile`/`requirements.txt` 변경 없을 땐 `--build` 생략 | 지금 수동 절차는 실수 유발 + 매번 전체 리빌드. 스크립트 한 개로 마찰·소요시간 동시 감소 | 하 |

> 차순위(Top 3 밖이지만 권장): 코드생성 타임아웃 시 좀비 컨테이너 정리 (§3-④),
> Playwright 스크린샷을 요청 임계경로에서 분리 (§1-③). 둘 다 작업량은 하~중.

**하지 말아야 할 것 (마감 전 금지):** `backend.py` 파일 분리, 벡터DB(Pinecone/Qdrant) 도입,
Hermes 게이트웨이 전환(`HERMES_GATEWAY_URL`), 서버리스/K8s 이전, 시안 N종 확장 외
대규모 기능 추가. 전부 임팩트 대비 작업량이 상(상)이고 데모 리스크를 키운다.

---

## 1. 성능/응답시간

관측된 호출 구조 (`backend.py` 기준):

- `GREETING/GATHERING` → `rag_precheck` → `rag_query` → 임베딩 **1회**(쿼리) + 기동 시 캐시된 문서 임베딩 3개와 코사인 유사도. **동기 blocking** (`call_nim:47-49`, `get_embedding:52-55`에 타임아웃 없음).
- `AWAIT_APPROVAL` 승인 시 → `build_quote` → NIM chat **1회**, 동기 blocking.
- `QUOTED` 진행 시 → `render_design` → **Playwright Chromium을 요청 스레드에서 매번 launch** (`_screenshot_html:168-183`), 동기 blocking. 실패 시에만 placeholder 폴백.
- 코드생성은 백그라운드 스레드 + 4초 폴링 (`start_codegen:369-376`, `static/index.html:93-113`) — 이 부분은 잘 되어 있음.
- 기동 시 `_ensure_doc_embeddings()` 3회 임베딩 호출이 import 타임에 실행 (`115-119`, 실패 시 lazy 재시도 폴백 있음).

| # | 문제 | 원인 | 개선안 | 예상 임팩트 | 예상 작업량 |
|---|---|---|---|---|---|
| ① | NIM chat/embedding 호출이 전부 동기 blocking + 타임아웃 없음 | `nim_client`에 `timeout` 미지정 (openai 1.51 기본값은 수 분). NIM이 hang되면 Flask 스레드가 같이 hang, `threaded=True`라도 스레드 고갈 시 전체 무응답 | `OpenAI(api_key=..., base_url=..., timeout=20~30)` 지정 + `call_nim`에 1회 재시도. 응답 지연 시 "처리 중" 안내는 REQ-CHAT-001 DoD에도 이미 요구됨 | 상 | 하 |
| ② | 동일/유사 입력에 견적·임베딩 API를 매번 재호출 | 견적 결과·쿼리 임베딩 캐시 없음 (문서 임베딩만 캐시됨). 데모 리허설에서 같은 질문 반복 시 매번 과금+지연 | `functools.lru_cache` 또는 dict 기반 **인메모리 견적 캐시**(키: `last_request` 정규화 문자열, TTL 불필요·용량 상한만) + 쿼리 임베딩 단기 캐시. 재현성(REQ-QUOTE-001 DoD "같은 입력→같은 견적")도 덤으로 해결 | 중 | 하 |
| ③ | 시안 스크린샷(Chromium launch)이 `/chat` 응답을 수 초 블로킹 | `render_design` 안에서 `_screenshot_html` 동기 실행. 브라우저 기동(~1-3초)이 사용자 체감 지연에 직결 | (안 A, 권장) 스크린샷을 백그라운드로 미루고 1차 응답은 placeholder `preview_url`로 즉시 반환, 다음 폴링에서 실제 PNG URL로 갱신. (안 B) 브라우저 프로세스 재사용(싱글톤). 안 A가 payload 흐름 수정이 작음 | 중 | 중 |
| ④ | 매 코드생성마다 `docker run --rm` 새 컨테이너 기동 | 격리 설계상 의도된 것이므로 제거 불가. 다만 컨테이너 기동+Hermes 기동+NIM 호출이 순차라 체감 30-90초 | cold start를 없애려 하지 말고 **체감**을 줄이기: GENERATING 폴링 메시지에 진행 단계 표시(현 "코드 생성 중입니다" 고정문 개선), 데모용 입력 3-5개는 결과물 캐시(INTEGRATION_STRATEGY §5 폴백과 동일 맥락 — "좁혀서 안정화"를 캐시로 구현) | 중 | 하 |
| ⑤ | 기동 시 문서 임베딩 3회 호출이 콜드스타트에 가산 | `_ensure_doc_embeddings()`를 import 타임에 실행. NIM 장애/지연 시 기동 자체가 느려짐 (try/except 폴백은 있음) | 기동 시 프리컴퓨트 **시도하되 실패해도 통과**(현 상태 유지) + 성공 시 결과를 파일(`generated/doc_embeddings.json`)에 저장, 다음 기동엔 파일에서 로드하고 백그라운드에서 갱신. API 호출 3회 제거 | 하 | 하 |
| ⑥ | 프론트 폴링이 4초 고정 + 난수 메시지로 세션 오염 가능성 | `static/index.html:99`가 `message: '' + Math.random()`을 보내고, `GENERATING` 분기는 본문을 무시하므로 기능상 무해. 그러나 불필요한 요청 + 로그 노이즈 | 폴링용 쿼리 파라미터(`?poll=1`) 또는 빈 메시지 구분을 명시화. 데모 안정성과 무관하므로 **마감 후**로 미룸 | 하 | 하 |

---

## 2. 리소스/비용

관측된 환경: OCI `VM.Standard.A1.Flex` **2 OCPU / 12GB**(Always Free 한도 정확히 일치, ENVIRONMENT.md §3-4).
한 호스트(정확히는 호스트 Docker 데몬 공유 — `docker.sock` 마운트, "outside-of-Docker")에서
① Flask backend 컨테이너(python + Playwright Chromium 포함),
② 요청당 `hermes-sandbox` 형제 컨테이너(Hermes 풀스택: python venv + node)가 동시에 돈다.
이미지 크기 2.68GB(`hermes-sandbox`)는 사용자 제보 기준 — Dockerfile상 `python:3.11-slim` +
`build-essential` + Hermes managed venv이므로 타당.

| # | 문제 | 원인 | 개선안 | 예상 임팩트 | 예상 작업량 |
|---|---|---|---|---|---|
| ① | 코드생성+스크린샷 동시 실행 시 메모리 압박 (12GB 상한) | Chromium(~300-500MB/런치) + hermes-sandbox 컨테이너(메모리 제한 없음)가 같은 호스트 메모리 공유. 동시 요청 N개면 N개 컨테이너 병렬 기동 — 상한 없음 | `docker run`에 `--memory=2g --cpus=1` 제한 + 백엔드에서 **코드생성 동시 실행 수 상한**(예: 세마포어 2, 초과 시 "대기 중" 응답). OOM kill(호스트 전체 불안정) 방지 | 상 | 하 |
| ② | `hermes-sandbox` 2.68GB 이미지의 재빌드/재배포 시간 | `install.sh` 네트워크 설치 + `build-essential` 컴파일. Dockerfile 변경 시 전체 레이어 재빌드, OCI A1(느린 디스크/네트워크)에서 수 분~수십 분 | 이미지 **재빌드 금지 정책**(마감까지 Dockerfile 동결) + 배포 시 backend만 `--build`하고 샌드박스 이미지는 인스턴스에 상주시킨 채 재사용. `docker images` 존재 확인 후 빌드 스킷을 `deploy.sh`에 포함 | 중 | 하 |
| ③ | backend 이미지 자체도 무거움 (Chromium `--with-deps`) | `Dockerfile.backend:20`의 `playwright install --with-deps chromium`이 OS 의존성까지 포함 (~1GB+). `requirements.txt`/`Dockerfile` 수정 시마다 재다운로드 | ②와 동일: 마감까지 backend Dockerfile 동결 + 레이어 캐시 유지(`pip` 레이어와 `playwright` 레이어 순서 현행 유지 — 지금 순서가 맞음). 구조 변경은 마감 후 | 하 | 하 |
| ④ | `generated/<id>/{design,web}` 무한 누적 → 디스크 압박 | 요청마다 디렉토리 생성, 정리 로직 없음. OCI 부트볼륨(기본 46~50GB)은 크지만 방치 시 증가. `generated/` 현재 0B이나 데모 반복 시 증가 | 데모 픽스처 외 7일 경과 디렉토리 삭제하는 5줄 cron/스크립트 또는 기동 시 정리. **단, 마감 직전엔 삭제 로직이 데모 산출물을 지울 위험이 있으니 D+6 이후에만 실행** | 하 | 하 |
| ⑤ | NIM API 과금 (인스턴스는 $0이나 NIM은 별도 요금제) | 매 대화턴 임베딩 1회 + 견적 chat 1회 + 코드생성 Hermes NIM 호출. ENVIRONMENT.md §5도 "NIM은 범위 밖"으로 명시 | §1-② 캐시로 호출 수 절감. 별도 요금 대시보드(build.nvidia.com) D+6에 1회 확인을 체크리스트에 추가 | 중 | 하 |

---

## 3. 안정성/장애 대응

| # | 문제 | 원인 | 개선안 | 예상 임팩트 | 예상 작업량 |
|---|---|---|---|---|---|
| ① | `SESSIONS` 인메모리 → 재배포/재시작 시 진행 중 대화 전멸 | `backend.py:30` dict. compose 재기동·`--build` 재배포 때마다 초기화. `GENERATING` 중 재시작이면 백그라운드 스레드도 함께 사망 → 복구 불가 | **파일 백업**(Top 1): 매 `/chat` 응답 후 `generated/sessions.json`에 원자적 저장(`tmp+rename`), 기동 시 로드. `codegen` 스레드 객체는 저장 불가하므로 `GENERATING` 상태로 로드된 세션은 `QUOTED`로 되돌리고 "다시 진행을 눌러주세요"로 안내하는 복구 규칙 포함. dict 접근에 `threading.Lock` 추가(현 무잠금 — `setdefault`+백그라운드 쓰기 경합) | 상 | 하 |
| ② | NIM 장애 폴백이 RAG에만 있고 견적/채팅엔 없음 | `rag_precheck:99-104`는 try/except → "신규" 폴백. 반면 `build_quote:138`의 `call_nim` 예외는 그대로 500. `get_embedding`도 직접 호출부는 무방어 | **폴백 통일**(Top 2): `build_quote`를 `{"ok": False, "raw": <사전 정의된 정적 견적 안내문>}` 폴백으로 감싸기. 정적 안내문은 contracts 예시(`quote_to_design.example.json`의 amount/basis) 재사용 — "계약 우선" 전략과도 정합 | 상 | 하 |
| ③ | 코드생성 실패 시 재시도 로직이 수동 1회에 의존 | 실패(`timeout`/`error`/`no_files_created`) → `QUOTED`로 복귀 후 사용자가 "진행" 재전송(수동, 무제한). 자동 재시도 없음. REQ-BUILD-001 DoD는 "1회 재시도"를 요구하나 현재 자동 재시도가 없음 | `no_files_created`/`error`에 한해 **1회 자동 재시도**(스레드 내에서 카운터), `timeout`은 자동 재시도 금지(좀비 컨테이너 중복 기동 위험) 후 수동 안내. DoD 충족 + 리소스 폭주 방지 | 중 | 중 |
| ④ | 코드생성 타임아웃 시 좀비 컨테이너 잔류 가능 | `subprocess.run(timeout=90)` 만료 시 **docker CLI 클라이언트만 kill**되고, 호스트 데몬 위의 컨테이너(Hermes 프로세스)는 계속 실행 → 리소스 점유 + 뒤늦은 파일 쓰기 | `TimeoutExpired` 핸들러에서 컨테이너 이름(`--name codegen-<req_id>`) 지정 기동 + `docker stop -t 5 <name>` 정리. `--name` 추가로 동시성 충돌 방지를 위해 req_id suffix 필수(현 `--rm` 익명과의 차이점) | 중 | 하 |
| ⑤ | 데모 중 장애 가시성 없음 (`/health`만) | `/health`는 200 고정. NIM 도달성·디스크·좀비 컨테이너를 아는 수단 없음 | `/health`에 NIM reachability(가벼운 임베딩 1회 또는 TCP 체크, 타임아웃 5초) + `generated/` 디스크 사용량을 포함하는 **확장 헬스**(기존 필드 유지, 추가만). warmup.sh는 그대로 사용 | 중 | 하 |

---

## 4. 배포 파이프라인 효율

관측된 현행: 로컬 `git push` → OCI SSH → (인스턴스에서 pull 또는 로컬에서 rsync) →
`docker compose up -d --build`. CI/CD 없음. 사용자 제보: OCI 인스턴스에서 GitHub API 404
(Oracle 무료티어 IP 차단 추정).

| # | 문제 | 원인 | 개선안 | 예상 임팩트 | 예상 작업량 |
|---|---|---|---|---|---|
| ① | 수동 배포 절차 (순서 실수·빌드 누락 유발) | 스크립트 없음. 매번 사람이 명령 조합. 마감 주간 배포 빈도 증가 예상 | **Top 3**: `scripts/deploy.sh` 작성 — `rsync -avz --delete --exclude generated --exclude .env` + 조건부 `--build`(아래 ②) + `/health` 대기 확인(warmup.sh 재사용). 수동 절차를 코드화할 뿐이므로 리스크 최소 | 중 | 하 |
| ② | 매번 전체 리빌드 (`--build` 상시) | 습관적 `--build`. 캐시 있어도 playwright/pip 레이어 검증에 시간 소모, Dockerfile 변경 시 대참사 | `deploy.sh`에서 `git diff --name-only HEAD~1` 기준으로 `Dockerfile*`/`requirements.txt` 변경 시에만 `--build`, 그 외엔 코드만 rsync(바인드 마운트 `.:/app`라 `.py`는 재기동만으로 반영) 후 `compose restart backend` | 중 | 하 |
| ③ | OCI→GitHub API 404 (인스턴스에서 API 호출 차단 추정) | Oracle 무료티어 egress IP 대역이 GitHub API rate-limit/abuse 차단에 걸린 것으로 추정 (`git` 프로토콜과 API는 차단 정책이 다름) | 인스턴스에서 GitHub **API를 쓰지 않는 방향**으로 고정: ① 인스턴스에서 `git pull` 대신 로컬→인스턴스 `rsync`를 정식 경로로 (이미 부분 적용 중 — 문서화만), ② Hermes `install.sh`(nousresearch 도메인, GitHub API 아님)는 영향 없음 확인 처리 완료 취급, ③ 배포에 필요한 tarball은 로컬에서 묶어 `scp` 1회. API 우회용 프록시/토큰 추가 같은 꼼수는 도입하지 않음 | 중 | 하 |
| ④ | CI/CD 없음 | 3인·5일 일정에 Actions 자가러너/시크릿 관리 비용이 과함. OCI 차단 이슈와 겹치면 디버깅 지옥 | **마감 전 도입하지 않음.** 대신 `deploy.sh` + 푸시 전 로컬 스모크(`curl /health`, `/chat` 1턴)를 `STATUS.md` 체크리스트에 명문화. CI는 마감 후 과제 | 하 | 상(→보류) |
| ⑤ | dev/prod compose 미분리 (`.:/app` 바인드 + `COPY . .` 공존) | 로컬 개발 편의용 바인드가 프로덕션에도 그대로. rsync 실수 시 `.env`·`generated`까지 덮어쓸 위험 | `deploy.sh`의 rsync exclude로 방어(①에 포함). compose override 분리는 마감 후 | 하 | 하 |

---

## 5. 코드 구조 (`backend.py` 단일 파일)

전제 확인: 547줄 단일 파일에 병렬작업 1(대화/RAG/견적: `call_nim`~`format_quote_text`) +
병렬작업 2(시안/스크린샷: `render_design` 일대) + 병렬작업 3(코드생성/배포: `_run_hermes_codegen_job`~`deploy_generated_site`) +
라우트(`/chat` 상태머신)가 공존. "얇은 관통 우선" 의도적 선택이며 STATUS.md상 전 구간 관통 완료 —
**마감 전 분리는 권하지 않는다.** 이유는 (a) 분리는 동작 변경 없이 테스트만 느는 작업이라
데모 가치 0, (b) import 경로 변경이 데모 직전 최대 리스크, (c) 현재 547줄은 단일 파일로
읽기 가능한 상한 내.

| # | 문제 | 원인 | 개선안 | 예상 임팩트 | 예상 작업량 |
|---|---|---|---|---|---|
| ① | 상태머신(`/chat`, 100줄+)과 도메인 로직이 한 함수에 혼재 | 관통 우선 개발의 자연스러운 결과 | **마감 전: 손대지 않음.** 마감 후 1순위: `/chat` 분기만 `handlers.py`로, 세션 저장만 `store.py`로 — 2파일 분리로 충분. 그 이상(작업자별 패키지화)은 불필요 | 하(마감전) | 상(→보류) |
| ② | 매직값 산재 (`90`, `15000`, `0.70`, 상태 문자열) | 상수명은 이미 일부 존재(`CODEGEN_TIMEOUT_SEC` 등). 상태 문자열(`"GENERATING"` 등)은 하드코딩 | **허용 범위 내 최소 개입**: 상태 문자열만 모듈 상수로 (오타 방지, 데모 중 오타 수정 비용 절감). 그 외 리팩토링 없음 | 하 | 하 |
| ③ | 스레드 경합 (`SESSIONS` 무잠금) | §3-①과 동일 원인 | §3-①의 Lock 추가로 해결. 구조 분리 없이 해결 가능하므로 분리 명분이 안 됨 | 상 | 하 |
| ④ | 테스트 없음 (계약 테스트도 없음) | INTEGRATION_STRATEGY §4가 계약 테스트를 우선하라 했으나 미구현 | 마감 전: `/health`+`/chat` 1턴 스모크를 `deploy.sh`에 내장(§4-①). 정식 계약 테스트(`contracts/*.schema.json` 검증)는 마감 후 | 중(마감후) | 중(→보류) |

**우선순위 요약 (마감 2026-09-28 기준):** ③(Lock, §3-①에 포함) > ②(상수화, 30분) > ④(스모크, §4-①에 포함) > ①(분리, 마감 후).

---

## 6. 실행 순서 제안 (D+3 ~ D+7)

| 일자 | 할 일 | 대응 항목 |
|---|---|---|
| D+3 (9/24) | Top 1 세션 파일 백업 + Lock / Top 2 NIM 타임아웃·폴백 | §3-①②, §1-① |
| D+4 (9/25) | `deploy.sh` + 조건부 빌드 + rsync 정식화 / 코드생성 `--memory` 제한 + 좀비 정리 | §4-①②③, §2-①, §3-④ |
| D+5 (9/26) | 견적/쿼리 캐시 + 확장 `/health` + 자동 재시도(1회) | §1-②, §3-③⑤ |
| D+6 (9/27) | 리허설 + Dockerfile 동결 확인 + NIM 요금 1회 확인 + 백업 영상 | §2-②⑤ |
| D+7 (9/28) | warmup.sh 실행 후 제출. 코드 변경 금지 | — |

> 모든 항목은 "문제 → 원인 → 개선안 → 임팩트 → 작업량" 표의 작업량 하(하) 위주로 배치했다.
> 작업량 중(중)은 §1-③(스크린샷 비동기화)과 §3-③(자동 재시도) 둘뿐이며, 둘 다 리허설 결과에 따라
> 생략 가능(폴백: 현행 유지)하도록 설계했다.
