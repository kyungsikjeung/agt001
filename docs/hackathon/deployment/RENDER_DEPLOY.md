# Render 배포 가이드 (AI 에이전트 온보딩용)

> 대상: 사람 팀원 + 배포를 대신 수행하는 AI 에이전트(Hermes 플래너/코드생성 에이전트) 모두
> 목적: 백엔드(RAG/게이트/오케스트레이션 서버)를 Render 컨테이너로 상시 배포. 프론트(Netlify)는 변경 없음
> 전제: [ARCHITECTURE.md](../ARCHITECTURE.md) §6-2에서 컨테이너 PaaS(A안) 중 **Render**를 채택함

## 1. 배경 (왜 Render인가, 왜 콜드스타트를 감수하는가)

- 참조 리포(`hackathon-agent-chatbot`)는 로컬 macOS + ngrok을 발표 시간에만 켜는 구조였다. 이번 요구사항 5)는 "고객이 접속했을 때 최종산출물이 동작해야 한다"이므로, 상시 접속 가능한 고정 URL이 필요하다.
- Render 무료/저가 플랜은 일정 시간(기본 15분) 요청이 없으면 컨테이너가 잠들고, 다음 요청 시 **콜드스타트(수십 초 지연)**가 발생한다. 이번 프로젝트는 GPU 연산을 PaaS가 아니라 NVIDIA 호스티드 NIM API가 담당하므로, 콜드스타트는 "백엔드 컨테이너 재기동" 지연일 뿐이며 데이터 손실이나 재구축은 없다.
- 콜드스타트를 없애려면 유료 플랜(상시 기동)이 필요하지만, 해커톤 예산/일정상 **1차는 무료 플랜 + 워밍업 절차로 감수**하고, 심사 직전에만 유료 전환하는 전략을 취한다. 이 문서는 그 절차를 AI/사람 모두 그대로 재현할 수 있도록 기록한다.

## 2. 목적 (이 문서가 하는 일)

이 문서 하나만 따라가면(사람이든 Hermes 코드생성 에이전트든) 아래를 할 수 있다.
1. 백엔드를 Dockerfile로 패키징
2. Render에 Web Service로 배포하고 환경변수를 설정
3. 무료 플랜 콜드스타트를 감수하되, 데모/심사 전 워밍업으로 지연을 없앰
4. 배포 상태를 헬스체크로 검증

## 3. 상세 핸즈온 가이드

### 3-1. 사전 준비물 (체크리스트)

- [ ] GitHub에 백엔드 코드가 푸시되어 있을 것 (이 레포 또는 별도 백엔드 레포)
- [ ] `Dockerfile`이 레포 루트(또는 백엔드 서브디렉터리)에 있을 것 — §3-2 참고
- [ ] NVIDIA NIM API 키 확보 (build.nvidia.com에서 발급)
- [ ] Render 계정 (GitHub OAuth로 가입 가능)

### 3-2. Dockerfile 준비 (없다면 이 템플릿 사용)

```dockerfile
# templates/Dockerfile.backend 로도 저장되어 있음 (§5 참고)
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Render는 PORT 환경변수를 런타임에 주입한다. 반드시 이 변수를 읽어서 바인딩할 것.
ENV PORT=8643
EXPOSE 8643

CMD ["python", "backend.py"]
```

> **AI 에이전트 주의사항**: `backend.py`(또는 동등한 서버 진입점)는 하드코딩된 포트가 아니라 `os.environ.get("PORT", 8643)`으로 포트를 읽어야 한다. Render는 컨테이너 기동 시 `PORT` 환경변수를 주입하고, 이 포트로 리스닝하지 않으면 헬스체크가 실패해 배포가 롤백된다.

### 3-3. Render Web Service 생성

1. https://dashboard.render.com → **New +** → **Web Service**
2. GitHub 레포 연결 (Render OAuth 앱 권한 승인 필요 — 이 단계는 팀원이 직접 승인해야 함, AI 에이전트는 대행 불가)
3. 설정값:

| 항목 | 값 |
|---|---|
| Environment | Docker |
| Region | Singapore (한국에서 가장 가까움) |
| Instance Type | Free (1차) → 심사 전 Starter($7/월)로 전환 |
| Health Check Path | `/health` (§3-5에서 엔드포인트 추가) |
| Auto-Deploy | Yes (main 브랜치 push 시 자동 재배포) |

4. 환경변수(Environment → Add Environment Variable):

| Key | Value | 비고 |
|---|---|---|
| `NIM_API_KEY` | (NVIDIA NIM 발급 키) | 절대 레포에 커밋 금지, Render 대시보드에만 입력 |
| `NIM_CHAT_MODEL` | `nemotron-3-super-120b` (또는 실제 사용 모델명) | |
| `NIM_EMBED_MODEL` | `nemotron-3-embed-1b` | |
| `VECTOR_DB_URL` / `VECTOR_DB_API_KEY` | (Pinecone 등) | RAG 인덱스(SRS.md/SPEC.md) 조회용 |
| `KAKAO_LINK_API_KEY` | (카카오 디벨로퍼스 발급 키) | 시안/산출물 전송용 |
| `PORT` | 자동 주입됨 (직접 설정하지 않음) | Render가 런타임에 넣어줌 |

5. **Create Web Service** 클릭 → 첫 빌드/배포 대기 (5~10분)

### 3-4. 배포 확인

```bash
curl -i https://<서비스명>.onrender.com/health
```

기대 응답: `200 OK` + `{"status": "ok"}` 형태. 콜드 상태였다면 첫 요청은 10~50초 정도 걸릴 수 있다 (정상).

### 3-5. 백엔드에 헬스체크 엔드포인트 추가 (AI 에이전트가 코드생성 시 반드시 포함할 것)

```python
# backend.py 에 추가
@app.route("/health")
def health():
    return {"status": "ok"}, 200
```

이 엔드포인트는 Render의 자동 헬스체크뿐 아니라, §4의 워밍업 스크립트에서도 사용한다.

### 3-6. 발표/심사 전 워밍업 절차 (콜드스타트 감수 전략의 핵심)

발표 10~15분 전, 아래 스크립트로 컨테이너를 깨워둔다.

```bash
# scripts/warmup.sh
#!/usr/bin/env bash
URL="https://<서비스명>.onrender.com/health"
echo "워밍업 시작: $URL"
for i in $(seq 1 5); do
  code=$(curl -s -o /dev/null -w "%{http_code}" "$URL")
  echo "시도 $i: HTTP $code"
  if [ "$code" = "200" ]; then
    echo "워밍업 완료"
    exit 0
  fi
  sleep 5
done
echo "경고: 워밍업 실패, 수동 확인 필요"
exit 1
```

> 팀원 B 또는 발표 담당자가 발표 직전 이 스크립트를 실행한다. Hermes 플래너 에이전트가 배포 자동화를 맡는다면, 이 워밍업 호출을 배포 파이프라인의 마지막 단계로 포함시킬 것.

### 3-7. 무료 → 유료 전환 (심사 당일 권장)

1. Render 대시보드 → 서비스 선택 → **Settings** → **Instance Type** → `Starter` 선택
2. 전환 즉시 콜드스타트 없이 상시 기동으로 전환됨
3. 심사 종료 후 다시 `Free`로 되돌려 비용 절감 가능

## 4. AI 에이전트가 이 문서를 사용할 때 지켜야 할 규칙

- 3-3의 **GitHub OAuth 권한 승인**과 **환경변수에 API 키 입력**은 사람의 명시적 조작이 필요하다 (자격증명 입력은 대행 금지 — 세션 전역 규칙과 동일). AI 에이전트는 "무엇을 어디에 입력해야 하는지"까지만 안내하고, 실제 키 입력은 팀원에게 요청한다.
- Dockerfile/헬스체크 엔드포인트 코드 작성은 AI 에이전트(팀 C의 코드생성 에이전트)가 자동 생성해도 된다. 단 §3-2의 `PORT` 환경변수 규칙을 반드시 준수해야 배포가 실패하지 않는다.
- 배포 자동화(예: `render.yaml`을 통한 IaC 방식)를 원하면 `templates/render.yaml` 예시를 확장해서 사용한다 (아래 §5).

## 5. 템플릿 파일 위치

- `templates/Dockerfile.backend` — §3-2 Dockerfile 원본
- `templates/render.yaml` — Render Blueprint(IaC) 예시, 대시보드 수동 설정 대신 코드로 재현 가능
- `scripts/warmup.sh` — §3-6 워밍업 스크립트

> 위 템플릿 파일들은 아직 생성 전이면 이 문서의 코드 블록을 그대로 복사해 해당 경로에 만들어 사용한다.
