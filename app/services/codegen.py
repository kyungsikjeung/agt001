"""코드생성: Hermes CLI를 요청 전용 Docker 샌드박스에서, 백그라운드로, 타임아웃과 함께 실행한다.

보안·설계 원칙
1. 사용자 원문이 아니라 정제·길이제한된 스펙만 프롬프트에 넣는다.
2. 호스트에서 hermes를 직접 실행하면 `--in DIR`을 무시하고 홈 디렉터리에 파일을 쓰는 것이
   실측됐다. 그래서 요청별 디렉터리만 /workspace에 bind mount한 컨테이너에서 실행하고,
   매 요청 --rm으로 폐기한다. 마운트 밖 쓰기는 컨테이너와 함께 사라진다.
3. 네트워크는 열어 둔다. Hermes가 NIM API를 호출해야 코드를 만들 수 있기 때문이다.
4. 하드 타임아웃을 건다.
5. 모델이 "성공했다"고 말하는 것을 믿지 않고 실제 파일이 생겼는지 확인한다.
6. 요청 트랜잭션이 커밋된 뒤 스레드로 던지고 즉시 반환한다. 결과는 세션의 codegen 필드에
   기록되고 폴링으로 확인한다. (0-3 단계에서 작업 큐로 교체한다.)
"""
import logging
import os
import shutil
import subprocess
import threading
from pathlib import Path

from app import store
from app.config import settings
from app.security import sanitize_spec, sanitize_token
from app.services import keystore

log = logging.getLogger(__name__)

_PROMPT = (
    "다음 스펙을 바탕으로 최소한의 정적 웹 프로젝트(index.html 하나만 있어도 됨)를 "
    "지금 이 작업 디렉토리(/workspace) 안에만 생성해라. "
    "반응형 웹(모바일/데스크톱에서 모두 잘 보이게, viewport meta 태그 포함)으로 만들어라. "
    "이 디렉토리 밖의 파일은 절대 읽거나 쓰지 말고, "
    "생성되는 프로젝트가 외부 네트워크나 패키지 설치를 필요로 하지 않게(단일 정적 파일 권장) 만들어라. "
    "(참고: 너 자신이 모델 API를 호출하는 것은 정상 동작이니 계속해라.)\n\n"
    "스펙: {spec}"
)


def _mount_source(workdir: Path) -> str:
    """docker.sock을 통해 호스트 데몬에 전달되므로 호스트 기준 경로를 만든다."""
    resolved = workdir.resolve()
    if settings.host_project_dir:
        try:
            rel = resolved.relative_to(settings.project_root.resolve())
            return str(Path(settings.host_project_dir) / rel)
        except ValueError:
            log.warning("산출물 경로가 프로젝트 루트 밖이라 HOST_PROJECT_DIR 변환을 생략: %s", resolved)
    return str(resolved)


def _set_result(session_id: str, result: dict) -> None:
    store.set_codegen(session_id, result)


def run_job(session_id: str, requirement_id: str, spec_text: str) -> None:
    docker_bin = shutil.which("docker")
    if not docker_bin:
        _set_result(session_id, {"status": "unavailable", "note": "이 환경에 docker가 없어 코드생성을 건너뛰었습니다."})
        return

    api_key = settings.nvidia_api_key or keystore.get("nim_api_key")
    if not api_key:
        _set_result(session_id, {
            "status": "unavailable",
            "note": "NVIDIA_API_KEY/NIM_API_KEY 환경변수가 없어 코드생성을 건너뛰었습니다.",
        })
        return

    safe_req_id = sanitize_token(requirement_id)
    if not safe_req_id:
        _set_result(session_id, {"status": "error", "message": "invalid requirement_id"})
        return

    workdir = settings.generated_dir / safe_req_id / "web"
    workdir.mkdir(parents=True, exist_ok=True)

    cmd = [
        docker_bin, "run", "--rm",
        "-v", f"{_mount_source(workdir)}:/workspace",
        "-w", "/workspace",
        # 값 없이 이름만 넘기고 실제 값은 env로 전달해 `ps` 인자 목록에 키가 노출되지 않게 한다.
        "-e", "NVIDIA_API_KEY",
        settings.hermes_sandbox_image,
        "hermes", "-z", _PROMPT.replace("{spec}", sanitize_spec(spec_text)),
    ]
    child_env = dict(os.environ)
    child_env["NVIDIA_API_KEY"] = api_key

    try:
        subprocess.run(cmd, timeout=settings.codegen_timeout_sec, capture_output=True, text=True, env=child_env)
    except subprocess.TimeoutExpired:
        _set_result(session_id, {"status": "timeout", "dir": str(workdir)})
        return
    except Exception as e:
        log.exception("코드생성 실행 실패")
        _set_result(session_id, {"status": "error", "message": str(e), "dir": str(workdir)})
        return

    created_files = [str(p.relative_to(workdir)) for p in workdir.rglob("*") if p.is_file()]
    if not created_files:
        _set_result(session_id, {"status": "no_files_created", "dir": str(workdir)})
        return
    _set_result(session_id, {"status": "done", "dir": str(workdir), "files": created_files})


def start(session_id: str, requirement_id: str, spec_text: str) -> None:
    def _launch() -> None:
        threading.Thread(target=run_job, args=(session_id, requirement_id, spec_text), daemon=True).start()

    # 커밋 전에 시작하면 스레드가 아직 GENERATING으로 저장되지 않은 세션에 결과를 쓰려다 버려진다.
    store.after_commit(_launch)
