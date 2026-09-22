import math
import os
import uuid

from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_from_directory
from openai import OpenAI

load_dotenv()

NIM_API_KEY = os.environ["NIM_API_KEY"]
NIM_CHAT_MODEL = os.environ.get("NIM_CHAT_MODEL", "nvidia/nemotron-3-super-120b-a12b")
NIM_BASE_URL = os.environ.get("NIM_BASE_URL", "https://integrate.api.nvidia.com/v1")
NIM_EMBED_MODEL = os.environ.get("NIM_EMBED_MODEL", "nvidia/nemotron-3-embed-1b")

# TODO(Hermes): 팀C(코드생성) 단계에서만 Hermes 게이트웨이(http://127.0.0.1:8642/v1)를 쓴다.
# 팀A(이 파일의 대화/RAG/견적 로직)는 NIM을 직접 호출하는 구조를 유지한다 (설계 결정, 2026-09-22).

app = Flask(__name__, static_folder="static", static_url_path="")
nim_client = OpenAI(api_key=NIM_API_KEY, base_url=NIM_BASE_URL)

# 뼈대(1차 관통) 단계: 세션 상태를 메모리에 보관한다. 재시작하면 날아간다 — 프로덕션용 아님.
SESSIONS = {}

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


def build_quote(user_text):
    """⑤견적 스텁: 3안 + 추천을 NIM에게 생성시킨다. 실제 단가표 연동은 2차 이후."""
    prompt = (
        "너는 소프트웨어 외주 견적 담당자다. 아래 고객 요청을 보고, "
        "예산/일정이 다른 3가지 안(A/B/C)과 그중 추천안을 간단히 제시해라. "
        "각 안은 한 줄로, 마지막에 '추천: <A/B/C>'를 명시해라.\n\n"
        f"고객 요청: {user_text}"
    )
    return call_nim([{"role": "user", "content": prompt}])


def stub_mockup():
    """⑥UI 시안 생성 스텁 (팀B). 고정 placeholder만 반환."""
    return {"mockup_url": "https://placehold.co/600x400?text=UI+Mockup+(stub)"}


def stub_codegen(requirement_id):
    """⑧코드생성 스텁 (팀C). 실제 Hermes 플래너 대신 고정 템플릿 프로젝트로 대체."""
    return {
        "web_repo": f"stub://generated/{requirement_id}/web-template",
        "android_repo": f"stub://generated/{requirement_id}/android-template",
    }


def stub_deploy(requirement_id):
    """⑨배포 스텁. 실제로는 OCI agt001-hermes-backend 또는 Render로 이어질 자리."""
    return {"deploy_url": f"https://deploy.stub.local/{requirement_id}"}


@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/health")
def health():
    return {"status": "ok"}, 200


@app.route("/chat", methods=["POST"])
def chat():
    body = request.get_json(force=True)
    session_id = body.get("session_id") or str(uuid.uuid4())
    user_text = (body.get("message") or "").strip()

    session = SESSIONS.setdefault(session_id, {"state": "GREETING", "requirement_id": str(uuid.uuid4())[:8]})
    state = session["state"]

    if not user_text:
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
            session["state"] = "QUOTED"
            reply = f"승인 감사합니다. 견적안입니다:\n\n{quote}\n\n이 견적으로 진행할까요? (진행/취소)"
        elif user_text in ("거절", "아니오", "no", "reject"):
            session["state"] = "GATHERING"
            reply = "알겠습니다. 요구사항을 다시 말씀해 주세요."
        else:
            reply = "승인 또는 거절로 답해주세요."

    elif state == "QUOTED":
        if user_text in ("진행", "네", "yes", "proceed", "예"):
            mockup = stub_mockup()
            codegen = stub_codegen(session["requirement_id"])
            deploy = stub_deploy(session["requirement_id"])
            session["state"] = "DONE"
            session["deploy_url"] = deploy["deploy_url"]
            reply = (
                "진행합니다! (아래는 뼈대 단계 스텁 결과입니다)\n\n"
                f"- UI 시안: {mockup['mockup_url']}\n"
                f"- 웹 코드: {codegen['web_repo']}\n"
                f"- 안드로이드 코드: {codegen['android_repo']}\n"
                f"- 배포 링크: {deploy['deploy_url']}\n\n"
                "파이프라인 뼈대 관통 완료."
            )
        else:
            session["state"] = "GATHERING"
            reply = "알겠습니다. 처음부터 다시 요청해 주세요."

    else:  # DONE
        reply = "이미 완료된 요청입니다. 새 프로젝트를 원하시면 다시 말씀해 주세요."
        session["state"] = "GATHERING"

    payload = {"session_id": session_id, "state": session["state"], "reply": reply}
    if session["state"] == "DONE" and session.get("deploy_url"):
        # ⑦카카오링크(팀B)용: 프론트가 완료 시점에 카카오톡 공유 버튼을 띄울 수 있도록 링크를 함께 내려준다.
        payload["deploy_url"] = session["deploy_url"]
    return jsonify(payload)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8643))
    app.run(host="0.0.0.0", port=port)
