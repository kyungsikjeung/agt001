"""tests/unit 공용 가짜 값 (conftest 이름 충돌 회피용 별도 모듈).

`from conftest import ...`는 tests/engine/conftest.py와 이름이 겹쳐
부분 실행(`pytest tests/unit tests/engine`) 때 수집 오류를 냈다.
이 모듈은 이름이 겹치지 않아 어디서든 안전하게 가져올 수 있다.
"""
import json

VALID_QUOTE_JSON = json.dumps(
    {
        "options": [
            {"id": "A", "weeks": 2, "amount": 1500000, "desc": "기본안"},
            {"id": "B", "weeks": 1, "amount": 1000000, "desc": "최소안"},
            {"id": "C", "weeks": 3, "amount": 2500000, "desc": "고급안"},
        ],
        "recommended": "B",
    },
    ensure_ascii=False,
)


def _finish_codegen(session_id, result):
    from app import store

    # 실제 start()처럼 요청 트랜잭션 커밋 뒤에 결과를 기록한다.
    store.after_commit(lambda: store.set_codegen(session_id, result))


def fake_codegen_done(session_id, requirement_id, spec_text):
    from app.config import settings

    web_dir = settings.generated_dir / requirement_id / "web"
    web_dir.mkdir(parents=True, exist_ok=True)
    (web_dir / "index.html").write_text("<html>fake done</html>", encoding="utf-8")
    _finish_codegen(session_id, {"status": "done", "dir": str(web_dir), "files": ["index.html"]})


def fake_codegen_timeout(session_id, requirement_id, spec_text):
    from app.config import settings

    workdir = settings.generated_dir / requirement_id / "web"
    workdir.mkdir(parents=True, exist_ok=True)
    _finish_codegen(session_id, {"status": "timeout", "dir": str(workdir)})


def fake_codegen_unavailable(session_id, requirement_id, spec_text):
    _finish_codegen(session_id, {"status": "unavailable", "note": "fake unavailable"})


def fake_png_screenshot(html_content, out_path, width=800, height=600):
    from pathlib import Path

    Path(out_path).write_bytes(b"\x89PNG\r\n\x1a\nfakepng")
