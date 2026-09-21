import os

from dotenv import load_dotenv
from flask import Flask, jsonify, request
from openai import OpenAI

load_dotenv()

NIM_API_KEY = os.environ["NIM_API_KEY"]
NIM_CHAT_MODEL = os.environ.get("NIM_CHAT_MODEL", "nvidia/nemotron-3-super-120b-a12b")
NIM_BASE_URL = os.environ.get("NIM_BASE_URL", "https://integrate.api.nvidia.com/v1")

# TODO(Hermes): Hermes 게이트웨이가 별도 프로세스로 설치되면(nemohermes, docs/hackathon/LOCAL_SETUP.md §6),
# HERMES_GATEWAY_URL(기본 http://127.0.0.1:8642/v1)을 바라보도록 nim_client 생성부를 전환할 것.
# 전환 조건: Hermes 샌드박스 status ready + curl -sf http://127.0.0.1:8642/health 통과 후.
# 그 전까지는 아래 NIM 직접 호출 구조를 유지한다. 로직 변경 없음.

app = Flask(__name__)
nim_client = OpenAI(api_key=NIM_API_KEY, base_url=NIM_BASE_URL)


@app.route("/health")
def health():
    return {"status": "ok"}, 200


@app.route("/chat", methods=["POST"])
def chat():
    body = request.get_json(force=True)
    messages = body.get("messages")
    if not messages:
        return jsonify({"error": "messages is required"}), 400

    completion = nim_client.chat.completions.create(
        model=NIM_CHAT_MODEL,
        messages=messages,
    )
    return jsonify({"reply": completion.choices[0].message.content})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8643))
    app.run(host="0.0.0.0", port=port)
