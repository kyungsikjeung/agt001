import html
import json
import math
import os
import re
import shutil
import subprocess
import threading
import uuid
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, abort, jsonify, request, send_file, send_from_directory
from openai import OpenAI

load_dotenv()

NIM_API_KEY = os.environ["NIM_API_KEY"]
NIM_CHAT_MODEL = os.environ.get("NIM_CHAT_MODEL", "nvidia/nemotron-3-super-120b-a12b")
NIM_BASE_URL = os.environ.get("NIM_BASE_URL", "https://integrate.api.nvidia.com/v1")
NIM_EMBED_MODEL = os.environ.get("NIM_EMBED_MODEL", "nvidia/nemotron-3-embed-1b")

# TODO(Hermes): 팀C(코드생성) 단계에서만 Hermes 게이트웨이(http://127.0.0.1:8642/v1)를 쓴다.
# 팀A(이 파일의 대화/RAG/견적 로직)는 NIM을 직접 호출하는 구조를 유지한다 (설계 결정, 2026-09-22).

app = Flask(__name__, static_folder="static", static_url_path="")
# NIM_TIMEOUT_SEC: 타임아웃 없으면(openai 기본값은 수 분) NIM이 hang될 때
# 요청 스레드가 같이 물려 전체가 무응답이 될 수 있다 (EFFICIENCY_PLAN.md §1-①).
NIM_TIMEOUT_SEC = float(os.environ.get("NIM_TIMEOUT_SEC", "25"))
nim_client = OpenAI(api_key=NIM_API_KEY, base_url=NIM_BASE_URL, timeout=NIM_TIMEOUT_SEC, max_retries=1)

# 세션 상태 저장소. 인메모리 dict가 원본이고, SESSIONS_FILE은 재시작 복구용 백업일 뿐이다
# (EFFICIENCY_PLAN.md §3-①: 재배포·재시작 한 번이면 진행 중 대화가 전부 증발하는 문제).
# 여러 스레드(요청 핸들러 + 코드생성 백그라운드 스레드)가 동시에 건드리므로 락으로 감싼다.
SESSIONS = {}
SESSIONS_LOCK = threading.Lock()
SESSIONS_FILE = Path(__file__).parent / "generated" / "sessions.json"


def save_sessions():
    """SESSIONS를 파일에 원자적으로(tmp+rename) 저장한다. 실패해도 /chat은 죽지 않는다."""
    try:
        SESSIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = SESSIONS_FILE.with_suffix(".json.tmp")
        with SESSIONS_LOCK:
            data = json.dumps(SESSIONS, ensure_ascii=False)
        tmp_path.write_text(data, encoding="utf-8")
        tmp_path.replace(SESSIONS_FILE)
    except Exception as e:
        print(f"[save_sessions] 세션 저장 실패(무시하고 계속 진행): {e}")


def load_sessions():
    """기동 시 SESSIONS_FILE을 복구한다.

    GENERATING 상태는 백그라운드 스레드가 재시작과 함께 죽었으므로 복구 불가 —
    QUOTED로 되돌려서 사용자가 '진행'을 다시 보내면 재시도되게 한다.
    """
    if not SESSIONS_FILE.is_file():
        return
    try:
        data = json.loads(SESSIONS_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[load_sessions] 세션 복구 실패(빈 상태로 시작): {e}")
        return
    for session in data.values():
        if session.get("state") == "GENERATING":
            session["state"] = "QUOTED"
            session["codegen"] = None
    with SESSIONS_LOCK:
        SESSIONS.update(data)
    print(f"[load_sessions] 세션 {len(data)}개 복구")

# ②RAG 스텁: 진짜 벡터DB 없이, 과거 프로젝트 문서 몇 개를 하드코딩해서 흉내만 낸다.
FAKE_RAG_DOCS = [
    {"source": "SRS-2025-014.md", "text": "쇼핑몰 리뉴얼 프로젝트. React + Node.js, 결제 연동 포함, 예산 800만원."},
    {"source": "SRS-2025-021.md", "text": "사내 재고관리 시스템. Android 앱, 바코드 스캔, 예산 500만원."},
    {"source": "SRS-2026-003.md", "text": "카페 예약 서비스. 웹+카카오 알림톡 연동, 예산 350만원."},
]


# RAG 임계값: 코사인 유사도가 이 값 미만이면 '신규 프로젝트'로 판단.
# nemotron-3-embed-1b 실측 기준: 관련 쿼리 0.75~0.85, 무관 쿼리 0.45~0.65(가끔 0.72까지).
# 3개 문서의 소규모 코퍼스에서 실측 분리점 ≈ 0.70.
RAG_TOP_K = 1
RAG_SIM_THRESHOLD = 0.70


def call_nim(messages):
    completion = nim_client.chat.completions.create(model=NIM_CHAT_MODEL, messages=messages)
    return completion.choices[0].message.content


def get_embedding(text):
    """NIM 임베딩 API(POST /v1/embeddings) 단일 텍스트 임베딩."""
    resp = nim_client.embeddings.create(model=NIM_EMBED_MODEL, input=text)
    return resp.data[0].embedding


def _cosine_sim(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


# 서버 기동 시 1회 계산되는 인메모리 문서 임베딩 캐시.
_DOC_EMBEDDINGS = None


def _ensure_doc_embeddings():
    """FAKE_RAG_DOCS 각 문서의 임베딩을 1회 계산해 인메모리에 캐시한다."""
    global _DOC_EMBEDDINGS
    if _DOC_EMBEDDINGS is not None:
        return _DOC_EMBEDDINGS
    _DOC_EMBEDDINGS = [get_embedding(d["text"]) for d in FAKE_RAG_DOCS]
    return _DOC_EMBEDDINGS


def rag_query(query, top_k=1):
    """contracts/rag_query.schema.json 규격의 진짜 벡터 검색.

    request{query, top_k} -> response{chunks: [{text, source, score}]}
    score는 코사인 유사도다.
    """
    doc_embeddings = _ensure_doc_embeddings()
    q_emb = get_embedding(query)
    scored = []
    for doc, d_emb in zip(FAKE_RAG_DOCS, doc_embeddings):
        scored.append(
            {"text": doc["text"], "source": doc["source"], "score": _cosine_sim(q_emb, d_emb)}
        )
    scored.sort(key=lambda c: c["score"], reverse=True)
    return {"chunks": scored[: max(1, top_k)]}


def rag_precheck(user_text):
    """진짜 벡터 검색 기반 사전확인: top_k=1 문서의 source/score로 기존/신규를 판정한다."""
    try:
        result = rag_query(user_text, top_k=RAG_TOP_K)
    except Exception as e:
        # 임베딩 API 장애 시 /chat 플로우가 죽지 않도록 신규로 폴백.
        print(f"[rag_precheck] embedding search failed, fallback to 신규: {e}")
        return "신규 프로젝트"
    if not result["chunks"]:
        return "신규 프로젝트"
    top = result["chunks"][0]
    if top["score"] < RAG_SIM_THRESHOLD:
        return "신규 프로젝트"
    return f"기존 프로젝트: {top['source']}"


# 서버 기동 시 문서 임베딩을 미리 계산한다. NIM 장애 시에는 크래시 대신
# 첫 rag_query 호출 때 재시도하도록(None 유지) 한다.
try:
    _ensure_doc_embeddings()
except Exception as e:
    _DOC_EMBEDDINGS = None
    print(f"[startup] doc embedding precompute skipped (retry on first query): {e}")

load_sessions()


# NIM 호출 자체가 실패(타임아웃/장애)할 때 쓰는 정적 견적 폴백. quote.amount/basis를
# 시안 페이지(⑨)가 그대로 노출하므로, "산정 실패"류 문구가 아니라 그럴듯한 구조화된
# 값을 준다 (EFFICIENCY_PLAN.md §3-②).
STATIC_QUOTE_FALLBACK = {
    "ok": True,
    "options": [
        {"id": "A", "weeks": 2, "amount": 3500000, "desc": "표준 웹 프로젝트 기본안"},
        {"id": "B", "weeks": 1, "amount": 2000000, "desc": "최소 기능 우선 구현"},
        {"id": "C", "weeks": 3, "amount": 5500000, "desc": "고급 커스터마이징 포함"},
    ],
    "recommended": "B",
    "raw": (
        "⚠ 견적 엔진(NIM) 연결이 원활하지 않아 기본 견적을 보여드립니다. "
        "실제 견적은 담당자가 다시 확인 후 안내드립니다.\n\n"
        "A: 2주, 3,500,000원 – 표준 웹 프로젝트 기본안\n"
        "B: 1주, 2,000,000원 – 최소 기능 우선 구현\n"
        "C: 3주, 5,500,000원 – 고급 커스터마이징 포함\n\n"
        "추천: B"
    ),
}


def build_quote(user_text):
    """⑧견적: 3안(A/B/C) + 추천을 NIM에게 구조화된 JSON으로 생성시킨다.

    팀B의 시안 페이지(⑨/⑩)가 quote.amount/basis를 그대로 노출해야 하므로
    (contracts/quote_to_design.schema.json), 자유 텍스트가 아니라 JSON으로 받는다.
    NIM 호출 자체가 실패하면 STATIC_QUOTE_FALLBACK으로, JSON 파싱만 실패하면
    자유 텍스트로 폴백한다 — 어느 쪽이든 /chat 플로우가 500으로 죽지 않는다.
    """
    prompt = (
        "너는 소프트웨어 외주 견적 담당자다. 아래 고객 요청을 보고, "
        "예산/일정이 다른 3가지 안(A/B/C)과 그중 추천안을 JSON으로만 응답해라. "
        "마크다운 코드블록이나 설명 문구 없이 JSON 객체 하나만 출력해라. 형식:\n"
        '{"options": [{"id": "A", "weeks": 2, "amount": 1500000, "desc": "..."}, '
        '{"id": "B", "weeks": 1, "amount": 1000000, "desc": "..."}, '
        '{"id": "C", "weeks": 3, "amount": 2500000, "desc": "..."}], "recommended": "B"}\n\n'
        f"고객 요청: {user_text}"
    )
    try:
        raw = call_nim([{"role": "user", "content": prompt}])
    except Exception as e:
        print(f"[build_quote] NIM 호출 실패, 정적 견적으로 폴백: {e}")
        return STATIC_QUOTE_FALLBACK
    try:
        cleaned = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
        data = json.loads(cleaned)
        options = {o["id"]: o for o in data["options"]}
        if data["recommended"] not in options:
            raise ValueError("recommended id not in options")
        return {"ok": True, "options": data["options"], "recommended": data["recommended"], "raw": raw}
    except Exception as e:
        print(f"[build_quote] JSON 파싱 실패, 자유 텍스트로 폴백: {e}")
        return {"ok": False, "raw": raw}


def format_quote_text(quote):
    """견적 dict를 채팅창에 보여줄 텍스트로 만든다."""
    if not quote["ok"]:
        return quote["raw"]
    lines = []
    for o in quote["options"]:
        lines.append(f"{o['id']}: {o['weeks']}주, {o['amount']:,}원 – {o['desc']}")
    lines.append(f"\n추천: {quote['recommended']}")
    return "\n".join(lines)


# ⑨UI 시안 생성기(팀B) 실구현: Figma API 없이 정적 HTML/CSS 템플릿 렌더링.
# (docs/hackathon/TEAM_B_SPEC.md §2 결정 그대로 — 개발 순서상 1차는 템플릿 1종 고정.)
DESIGN_TEMPLATE_PATH = Path(__file__).parent / "templates" / "variant-1.html"
DESIGN_SCREENSHOT_TIMEOUT_MS = 15000


def _screenshot_html(html_content, out_path, width=800, height=600):
    """렌더링된 시안 HTML을 헤드리스 크로미움으로 스크린샷 찍어 PNG로 저장.

    playwright는 무거운 의존성이라 import를 함수 안으로 미뤄서, 모듈 로드
    시점에는(=서버 기동/폴백 경로에는) 영향이 없게 한다.
    """
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": width, "height": height})
            page.set_content(html_content, timeout=DESIGN_SCREENSHOT_TIMEOUT_MS)
            page.screenshot(path=str(out_path))
        finally:
            browser.close()


def render_design(requirement_id, platform, features, quote_amount, quote_basis):
    """features/quote를 템플릿에 채워 generated/<id>/design/index.html로 저장.

    contracts/design_to_link.schema.json(BND-4) 규격의 design_variants를 반환한다.
    미리보기 이미지(카카오링크용)는 아직 헤드리스 브라우저 스크린샷이 아니라
    placehold.co 플레이스홀더다 — TEAM_B_SPEC.md §2 개발순서상 다음 단계.
    """
    template = DESIGN_TEMPLATE_PATH.read_text(encoding="utf-8")
    features_html = "\n".join(f"      <li>{html.escape(f)}</li>" for f in features) or "      <li>(기능 미지정)</li>"
    rendered = (
        template
        .replace("{{TITLE}}", html.escape(f"{platform} 프로젝트 시안"))
        .replace("{{PLATFORM}}", html.escape(platform))
        .replace("{{FEATURES_HTML}}", features_html)
        .replace("{{QUOTE_AMOUNT}}", html.escape(f"{quote_amount:,}원"))
        .replace("{{QUOTE_BASIS}}", html.escape(quote_basis))
        .replace("{{REQUIREMENT_ID}}", html.escape(requirement_id))
    )

    design_dir = GENERATED_DIR / requirement_id / "design"
    design_dir.mkdir(parents=True, exist_ok=True)
    (design_dir / "index.html").write_text(rendered, encoding="utf-8")

    # 헤드리스 브라우저 스크린샷: 카카오링크 미리보기 이미지로 쓴다.
    # 실패해도(브라우저 미설치 등) 시안 페이지 자체는 살아있어야 하므로 폴백만 하고 넘어간다.
    preview_path = design_dir / "preview.png"
    try:
        _screenshot_html(rendered, preview_path)
        preview_url = f"/design/{requirement_id}/preview.png"
    except Exception as e:
        print(f"[render_design] 스크린샷 실패, placeholder로 폴백: {e}")
        preview_url = f"https://placehold.co/600x400?text={platform}+UI+시안"

    return {
        "requirement_id": requirement_id,
        "design_variants": [{"id": "v1", "preview_url": preview_url}],
        "design_url": f"/design/{requirement_id}",
        "preview_url": preview_url,
    }


# ⑧코드생성(팀C) 실구현: Hermes CLI를 Docker 샌드박스 컨테이너 안에서, 백그라운드로, 타임아웃과 함께 실행한다.
# 보안/설계 원칙(2026-09-22 시니어 리뷰 + Docker 격리 강화):
#  1) 사용자 원문이 아니라 정제·길이제한된 스펙 텍스트만 프롬프트에 넣는다.
#  2) 실측된 격리 실패: 호스트에서 hermes를 cwd=generated/<id>/web 로 직접 실행해도
#     `--in DIR --no-restore-cwd`를 무시하고 호스트 홈(~/index.html)에 파일을 씀.
#     그래서 로컬 서브프로세스 대신 Docker 컨테이너로 격리한다. 요청별 디렉토리만
#     /workspace에 bind mount하고, 그 외 호스트 파일시스템은 컨테이너에서 보이지 않는다
#     (마운트하지 않은 것은 Docker 기본 격리로 차단 — 별도 read-only 마운트 불필요).
#  3) 컨테이너 WORKDIR=/workspace 고정 + 매 요청 --rm으로 새로 띄웠다 지움.
#     hermes가 --in 같은 옵션을 무시해도 cwd 자체가 /workspace라 산출물은 마운트 안으로
#     떨어지고, 마운트 밖 쓰기는 컨테이너와 함께 폐기된다.
#  4) 네트워크는 차단하지 않는다 (--network none 미사용). Hermes가 NIM 추론 API
#     (https://integrate.api.nvidia.com/v1)를 호출해야 코드생성이 되므로, 네트워크를
#     끊으면 아무것도 생성하지 못한다. 외부 요청 방지는 프롬프트 지시 수준에서만 한다.
#  5) 90초 하드 타임아웃.
#  6) Flask에게 "성공했다"는 텍스트를 믿지 않고, 실제로 파일이 생겼는지 확인한다.
#  7) 동기 blocking을 피하려고 백그라운드 스레드 + 폴링(GENERATING 상태)으로 처리한다.
#     이 비동기 구조는 유지 — 격리 방식(docker run)만 바뀜.
GENERATED_DIR = Path(__file__).parent / "generated"
CODEGEN_TIMEOUT_SEC = 90
# docker build: docker build -t reqpipe-hermes-sandbox:latest docker/hermes-sandbox
HERMES_SANDBOX_IMAGE = os.environ.get("HERMES_SANDBOX_IMAGE", "reqpipe-hermes-sandbox:latest")
# backend.py가 컨테이너 안에서 돌 때(OCI 배포), `docker run -v`는 docker.sock을 통해
# 호스트 데몬으로 전달되므로 마운트 소스는 컨테이너 내부 경로가 아니라 "호스트" 경로여야
# 한다. docker-compose.yml이 프로젝트 루트를 컨테이너의 /app에 마운트하므로, 호스트 쪽
# 실제 경로(${PWD} 등)를 HOST_PROJECT_DIR로 넘겨받아 그 기준으로 변환한다.
# 로컬에서 backend.py를 그냥 `python3 backend.py`로 띄울 때는 이 값이 없고, 그때는
# 컨테이너화가 아니므로 workdir.resolve()가 이미 올바른(호스트=실행 환경) 경로다.
HOST_PROJECT_DIR = os.environ.get("HOST_PROJECT_DIR")


def _sanitize_spec(text, max_len=800):
    """프롬프트 인젝션 표면을 줄이기 위해 제어문자를 제거하고 길이를 제한한다. 완벽한 방어는 아니다."""
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text or "")
    return text.strip()[:max_len]


def _sanitize_requirement_id(value, max_len=64):
    """경로 순회(../../) 및 docker 인자 주입 방지를 위해 영숫자/하이픈/언더스코어만 남긴다."""
    cleaned = re.sub(r"[^A-Za-z0-9_-]", "", value or "")
    return cleaned[:max_len]


def _run_hermes_codegen_job(session_id, requirement_id, spec_text):
    """백그라운드 스레드에서 실행. 결과를 SESSIONS[session_id]['codegen']에 기록한다."""
    session = SESSIONS.get(session_id)
    if session is None:
        return

    docker_bin = shutil.which("docker")
    if not docker_bin:
        session["codegen"] = {
            "status": "unavailable",
            "note": "이 환경에 docker가 없어 코드생성을 건너뛰었습니다.",
        }
        return

    # .env 파일을 직접 읽지 않고, 호스트 프로세스의 환경변수에서만 읽는다.
    # NVIDIA_API_KEY 우선, 없으면 NIM_API_KEY(같은 키 값, 변수명만 다름)로 폴백.
    # 비밀값을 코드·로그에 하드코딩하지 않는다.
    api_key = os.environ.get("NVIDIA_API_KEY") or os.environ.get("NIM_API_KEY")
    if not api_key:
        session["codegen"] = {
            "status": "unavailable",
            "note": "NVIDIA_API_KEY/NIM_API_KEY 환경변수가 없어 코드생성을 건너뛰었습니다.",
        }
        return

    safe_req_id = _sanitize_requirement_id(requirement_id)
    if not safe_req_id:
        session["codegen"] = {"status": "error", "message": "invalid requirement_id"}
        return

    workdir = GENERATED_DIR / safe_req_id / "web"
    workdir.mkdir(parents=True, exist_ok=True)

    spec = _sanitize_spec(spec_text)
    prompt = (
        "다음 스펙을 바탕으로 최소한의 정적 웹 프로젝트(index.html 하나만 있어도 됨)를 "
        "지금 이 작업 디렉토리(/workspace) 안에만 생성해라. "
        "반응형 웹(모바일/데스크톱에서 모두 잘 보이게, viewport meta 태그 포함)으로 만들어라. "
        "이 디렉토리 밖의 파일은 절대 읽거나 쓰지 말고, "
        "생성되는 프로젝트가 외부 네트워크나 패키지 설치를 필요로 하지 않게(단일 정적 파일 권장) 만들어라. "
        "(참고: 너 자신이 모델 API를 호출하는 것은 정상 동작이니 계속해라.)\n\n"
        f"스펙: {spec}"
    )

    # 격리 실행: 요청 전용 컨테이너를 매번 새로 띄웠다 지운다(--rm).
    # -v workdir:/workspace(유일한 호스트 마운트, 읽기/쓰기), -w /workspace 고정.
    # 네트워크는 열어둔다: Hermes가 NIM API를 호출해야 해서 --network none을 쓰면
    # 코드생성 자체가 불가능해진다. 값 전달은 `-e NVIDIA_API_KEY`(값 없이 이름만) +
    # env=... 로 해서 키가 `ps` 인자 목록에 노출되지 않게 한다.
    if HOST_PROJECT_DIR:
        # workdir은 컨테이너 내부 기준 GENERATED_DIR(/app/generated/...) 하위이므로,
        # /app을 HOST_PROJECT_DIR로 바꿔치기해서 호스트 데몬이 이해하는 실제 경로를 만든다.
        rel = workdir.resolve().relative_to(Path(__file__).parent.resolve())
        mount_src = str(Path(HOST_PROJECT_DIR) / rel)
    else:
        mount_src = str(workdir.resolve())

    cmd = [
        docker_bin,
        "run",
        "--rm",
        "-v",
        f"{mount_src}:/workspace",
        "-w",
        "/workspace",
        "-e",
        "NVIDIA_API_KEY",
        HERMES_SANDBOX_IMAGE,
        "hermes",
        "-z",
        prompt,
    ]
    child_env = dict(os.environ)
    child_env["NVIDIA_API_KEY"] = api_key

    try:
        subprocess.run(
            cmd,
            timeout=CODEGEN_TIMEOUT_SEC,
            capture_output=True,
            text=True,
            env=child_env,
        )
    except subprocess.TimeoutExpired:
        session["codegen"] = {"status": "timeout", "dir": str(workdir)}
        save_sessions()
        return
    except Exception as e:
        session["codegen"] = {"status": "error", "message": str(e), "dir": str(workdir)}
        save_sessions()
        return

    created_files = [str(p.relative_to(workdir)) for p in workdir.rglob("*") if p.is_file()]
    if not created_files:
        # "성공했다"는 모델의 주장을 믿지 않고, 실제 산출물이 없으면 실패로 기록한다.
        session["codegen"] = {"status": "no_files_created", "dir": str(workdir)}
        save_sessions()
        return

    session["codegen"] = {"status": "done", "dir": str(workdir), "files": created_files}
    # 백그라운드 스레드 완료 시점에도 저장 — 사용자가 폴링하기 전에 서버가 재시작되면
    # /chat 응답 때만 저장하는 경로로는 이 결과가 유실된다.
    save_sessions()


def start_codegen(session_id, requirement_id, spec_text):
    """동기 blocking을 피하려고 백그라운드 스레드로 던지고 바로 리턴한다."""
    thread = threading.Thread(
        target=_run_hermes_codegen_job,
        args=(session_id, requirement_id, spec_text),
        daemon=True,
    )
    thread.start()


def deploy_generated_site(requirement_id):
    """⑰배포 실구현: 팀C(Hermes)가 만든 정적 산출물을 백엔드 자신이 직접 서빙한다.

    별도 호스팅(Render/Netlify 등) 없이 GENERATED_DIR/<id>/web을
    /site/<id>/ 로 바로 서빙 — 로컬에서도, OCI 배포본(sslip.io 도메인)에서도
    추가 설정 없이 바로 접속 가능한 실제 URL이 나온다.
    request.url_root를 써서 지금 접속한 호스트 기준으로 절대 URL을 만든다.
    """
    web_dir = GENERATED_DIR / requirement_id / "web"
    if not web_dir.is_dir() or not any(web_dir.iterdir()):
        return {"deploy_url": None}
    deploy_url = request.url_root.rstrip("/") + f"/site/{requirement_id}/"
    return {"deploy_url": deploy_url}


@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/health")
def health():
    return {"status": "ok"}, 200


@app.route("/design/<requirement_id>")
def design_page(requirement_id):
    """⑩시안 확인 링크 페이지: render_design()이 만든 정적 HTML을 그대로 서빙."""
    safe_id = _sanitize_requirement_id(requirement_id)
    path = GENERATED_DIR / safe_id / "design" / "index.html"
    if not safe_id or not path.is_file():
        abort(404)
    return path.read_text(encoding="utf-8")


@app.route("/design/<requirement_id>/preview.png")
def design_preview(requirement_id):
    """render_design()이 헤드리스 브라우저로 찍은 시안 스크린샷(카카오 미리보기용)."""
    safe_id = _sanitize_requirement_id(requirement_id)
    path = GENERATED_DIR / safe_id / "design" / "preview.png"
    if not safe_id or not path.is_file():
        abort(404)
    return send_file(path, mimetype="image/png")


@app.route("/site/<requirement_id>/")
@app.route("/site/<requirement_id>/<path:filename>")
def serve_site(requirement_id, filename="index.html"):
    """⑰배포 실구현: 팀C 코드생성 산출물을 그대로 서빙. deploy_generated_site() 참고."""
    safe_id = _sanitize_requirement_id(requirement_id)
    web_dir = GENERATED_DIR / safe_id / "web"
    if not safe_id or not web_dir.is_dir():
        abort(404)
    # send_from_directory가 path traversal(../)을 자체적으로 막는다.
    return send_from_directory(web_dir, filename)


@app.route("/chat", methods=["POST"])
def chat():
    body = request.get_json(force=True)
    session_id = body.get("session_id") or str(uuid.uuid4())
    user_text = (body.get("message") or "").strip()

    with SESSIONS_LOCK:
        session = SESSIONS.setdefault(session_id, {"state": "GREETING", "requirement_id": str(uuid.uuid4())[:8]})
    state = session["state"]

    if state == "GENERATING":
        # 팀C 코드생성 백그라운드 작업 폴링. 빈 메시지(자동 폴링)든 아니든 이 상태에선 진행상황만 본다.
        codegen = session.get("codegen")
        if codegen is None:
            reply = "코드 생성 중입니다... 잠시만 기다려주세요."
        elif codegen["status"] == "done":
            deploy = deploy_generated_site(session["requirement_id"])
            session["state"] = "DONE"
            session["deploy_url"] = deploy["deploy_url"]
            files_list = ", ".join(codegen["files"][:5])
            reply = (
                "코드 생성이 완료됐습니다!\n\n"
                f"- 생성된 파일: {files_list}\n"
                f"- 배포 링크: {deploy['deploy_url']}\n\n"
                "파이프라인 뼈대 관통 완료 (팀C 실구현)."
            )
        elif codegen["status"] == "unavailable":
            # docker/키 미탑재 등으로 코드생성 자체를 못 돌린 경우 — 산출물이 없으니 배포도 없다.
            session["state"] = "DONE"
            reply = (
                f"{codegen['note']}\n\n"
                f"- UI 시안: {session.get('design_url', '(없음)')}\n"
                "- 배포 링크: (코드생성을 건너뛰어 배포할 산출물이 없습니다)\n\n"
                "파이프라인 뼈대 관통 완료 (팀C 스텁 폴백)."
            )
        else:  # timeout / error / no_files_created
            session["state"] = "QUOTED"
            reply = f"코드 생성에 실패했습니다 ({codegen['status']}). 다시 '진행'을 보내 재시도할 수 있습니다."

    elif not user_text:
        reply = "안녕하세요! 어떤 프로젝트를 원하시나요? (예: 예산, 원하는 기능을 알려주세요)"
        session["state"] = "GATHERING"

    elif state in ("GREETING", "GATHERING"):
        # ②RAG 사전확인 + ③검증/질의를 한 번에: 관련 과거 프로젝트 안내 후 승인 게이트로 진입
        rag_result = rag_precheck(user_text)
        session["last_request"] = user_text
        reply = (
            f"{rag_result}\n\n"
            f"요청하신 내용을 검토했습니다. 이 요구사항으로 견적을 진행할까요? (승인/거절로 답해주세요)"
        )
        session["state"] = "AWAIT_APPROVAL"

    elif state == "AWAIT_APPROVAL":
        if user_text in ("승인", "네", "yes", "approve", "예"):
            quote = build_quote(session.get("last_request", ""))
            session["quote"] = quote
            session["state"] = "QUOTED"
            reply = f"승인 감사합니다. 견적안입니다:\n\n{format_quote_text(quote)}\n\n이 견적으로 진행할까요? (진행/취소)"
        elif user_text in ("거절", "아니오", "no", "reject"):
            session["state"] = "GATHERING"
            reply = "알겠습니다. 요구사항을 다시 말씀해 주세요."
        else:
            reply = "승인 또는 거절로 답해주세요."

    elif state == "QUOTED":
        if user_text in ("진행", "네", "yes", "proceed", "예"):
            # ⑨/⑩ 팀B 시안 생성 — 코드생성 시작 전에 먼저 만들어서 고객이 먼저 확인할 수 있게 한다
            # (TEAM_B_SPEC.md §0.1 전송 순서: 시안이 최종 배포보다 먼저 나가야 함).
            quote = session.get("quote") or {"ok": False, "raw": ""}
            if quote["ok"]:
                rec = next(o for o in quote["options"] if o["id"] == quote["recommended"])
                amount, basis = rec["amount"], rec["desc"]
            else:
                amount, basis = 0, "견적 산정 실패 — 자유 텍스트 견적 참고"
            design = render_design(
                session["requirement_id"], "web", [session.get("last_request", "")], amount, basis
            )
            session["design_url"] = design["design_url"]
            session["design_preview_url"] = design["preview_url"]
            session["design_url_unsent"] = True

            session["codegen"] = None
            session["state"] = "GENERATING"
            start_codegen(session_id, session["requirement_id"], session.get("last_request", ""))
            reply = (
                f"진행합니다! UI 시안이 준비됐어요: {design['design_url']}\n\n"
                "팀C 코드생성 에이전트(Hermes)를 백그라운드로 시작했습니다. "
                "완료까지 최대 90초 정도 걸릴 수 있어요 — 잠시 후 아무 메시지나 보내시면 진행상황을 알려드립니다."
            )
        else:
            session["state"] = "GATHERING"
            reply = "알겠습니다. 처음부터 다시 요청해 주세요."

    else:  # DONE
        reply = "이미 완료된 요청입니다. 새 프로젝트를 원하시면 다시 말씀해 주세요."
        session["state"] = "GATHERING"

    payload = {"session_id": session_id, "state": session["state"], "reply": reply}
    if session["state"] == "DONE" and session.get("deploy_url"):
        # ⑪카카오링크(팀B)용: 프론트가 완료 시점에 카카오톡 공유 버튼을 띄울 수 있도록 링크를 함께 내려준다.
        payload["deploy_url"] = session["deploy_url"]
    if session.pop("design_url_unsent", False):
        # ⑪카카오링크(팀B)용: 시안 링크는 배포 링크보다 먼저 나가야 하므로(전송 순서),
        # 시안이 막 만들어진 이번 응답에서만 한 번 내려주고, 폴링 응답에서는 반복해서 보내지 않는다.
        payload["design_url"] = session["design_url"]
        payload["design_preview_url"] = session.get("design_preview_url")
    save_sessions()
    return jsonify(payload)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8643))
    app.run(host="0.0.0.0", port=port, threaded=True)
