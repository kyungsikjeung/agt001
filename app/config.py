from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=PROJECT_ROOT / ".env", extra="ignore")

    nim_api_key: str
    nim_chat_model: str = "nvidia/nemotron-3-super-120b-a12b"
    nim_base_url: str = "https://integrate.api.nvidia.com/v1"
    nim_embed_model: str = "nvidia/nemotron-3-embed-1b"
    # 타임아웃이 없으면(openai 기본값은 수 분) NIM이 멈출 때 요청 스레드가 같이 묶인다.
    nim_timeout_sec: float = 25.0

    project_root: Path = PROJECT_ROOT
    generated_dir: Path = PROJECT_ROOT / "generated"
    static_dir: Path = PROJECT_ROOT / "static"
    templates_dir: Path = PROJECT_ROOT / "templates"

    rag_top_k: int = 1
    # nemotron-3-embed-1b 실측: 관련 0.75~0.85, 무관 0.45~0.65(가끔 0.72). 소규모 코퍼스 분리점.
    rag_sim_threshold: float = 0.70
    precompute_embeddings: bool = True

    design_screenshot_timeout_ms: int = 15000

    codegen_timeout_sec: int = 90
    hermes_sandbox_image: str = "reqpipe-hermes-sandbox:latest"
    nvidia_api_key: Optional[str] = None
    # 백엔드가 컨테이너 안에서 돌면 `docker run -v`는 호스트 데몬으로 가므로 마운트 소스는
    # 호스트 경로여야 한다. docker-compose가 호스트의 프로젝트 루트를 넘겨준다.
    host_project_dir: Optional[str] = None

    # 설정하면 배포 URL을 요청 호스트 대신 이 값으로 만든다 (예: https://example.com).
    public_base_url: Optional[str] = None


settings = Settings()
