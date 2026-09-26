from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=PROJECT_ROOT / ".env", extra="ignore")

    nim_api_key: str
    nim_chat_model: str = "nvidia/nemotron-3-super-120b-a12b"
    # 주 모델이 과부하(503)·요청 제한(429)·시간 초과일 때 차례로 쓸 대비 모델 (D28). 실측 2026-09-26:
    # ultra 2.2초(기능 칸까지 정확), lightning 1.7초. 쉼표로 구분.
    nim_chat_fallback_models: str = "nvidia/nemotron-3-ultra-550b-a55b,nvidia/nemotron-3.5-lightning-30b-a3b"
    # 실패한 모델은 이 시간 동안 건너뛰고 다음 모델로 바로 간다(매 요청마다 실패를 기다리지 않게).
    nim_fallback_cooldown_sec: float = 60.0
    # 모든 모델이 실패했을 때 한 번 더 돌기 전에 쉬는 시간
    nim_all_fail_backoff_sec: float = 2.0
    nim_base_url: str = "https://integrate.api.nvidia.com/v1"
    nim_embed_model: str = "nvidia/nemotron-3-embed-1b"
    # 타임아웃이 없으면(openai 기본값은 수 분) NIM이 멈출 때 요청 스레드가 같이 묶인다.
    nim_timeout_sec: float = 25.0

    project_root: Path = PROJECT_ROOT
    generated_dir: Path = PROJECT_ROOT / "generated"
    static_dir: Path = PROJECT_ROOT / "static"
    # React 빌드 결과 (frontend/, `npm run build`). 없으면 "/"는 기존 static/index.html로 폴백한다.
    frontend_dist_dir: Path = PROJECT_ROOT / "frontend" / "dist"
    templates_dir: Path = PROJECT_ROOT / "templates"

    rag_top_k: int = 1
    # nemotron-3-embed-1b, 기능 사례집 51개 자료 실측(2026-09-26): 관련 0.76~0.80, 무관 0.61~0.757(지도).
    rag_sim_threshold: float = 0.76
    precompute_embeddings: bool = True

    design_screenshot_timeout_ms: int = 15000

    codegen_timeout_sec: int = 90
    hermes_sandbox_image: str = "reqpipe-hermes-sandbox:latest"
    nvidia_api_key: Optional[str] = None
    # 백엔드가 컨테이너 안에서 돌면 `docker run -v`는 호스트 데몬으로 가므로 마운트 소스는
    # 호스트 경로여야 한다. docker-compose가 호스트의 프로젝트 루트를 넘겨준다.
    host_project_dir: Optional[str] = None

    # NVIDIA 호스팅 음성 인식(Parakeet 1.1B RNNT 다국어). docs/product/VOICE_INPUT_PLAN.md 부록 실측.
    stt_enabled: bool = True
    stt_server: str = "grpc.nvcf.nvidia.com:443"
    stt_function_id: str = "71203149-d3b7-4460-8231-1be2543a1fca"
    stt_timeout_sec: float = 20.0

    # NVIDIA 호스팅 음성 합성(Magpie TTS 다국어). 키는 인식과 같은 nim_api_key를 쓴다.
    tts_enabled: bool = True
    tts_function_id: str = "877104f7-e885-42b9-8de8-f6e4c6303969"
    tts_voice: str = "Magpie-Multilingual.KO-KR.Aria"
    tts_timeout_sec: float = 15.0

    # 카카오·구글 로그인 (1-2). 값은 scripts/set_oauth_secrets.sh로 서버 .env에만 넣는다 (D10).
    kakao_rest_api_key: Optional[str] = None
    kakao_client_secret: Optional[str] = None
    google_client_id: Optional[str] = None
    google_client_secret: Optional[str] = None
    login_session_days: int = 30
    # 카카오 알림 토큰 암호화 키. 비우면 카카오 Client Secret에서 만든다(app/services/kakao_talk.py).
    # 관리자 화면 키 교체(D50)는 이 값이 따로 있을 때만 열린다(화면에서 바꾸는 카카오 비밀값에서 파생되면 안 되므로).
    token_enc_key: Optional[str] = None

    # 관리자 사이트 (D49·D50). 명단은 서버 .env에만 둔다(화면에서 못 바꿈). 우리 users.id를 쉼표로.
    admin_user_ids: str = ""
    # 키 교체처럼 민감한 일은 이 시간 안에 로그인한 세션만 할 수 있다(최근 로그인 재확인).
    admin_reauth_minutes: int = 10
    # 디자인 단계 유료 모델 비교(D39), 운영 알림. 관리자 화면에서 교체할 수 있다(D50).
    zen_api_key: Optional[str] = None
    telegram_bot_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None

    # 채팅방 타이머·인원 (D7·D8, ROOM_POLICY §4.2). 점검 작업 대신 방을 읽거나 쓸 때 판정한다.
    room_vote_reset_hours: float = 24
    room_quote_expire_days: float = 7
    room_close_days: float = 30
    room_max_members: int = 10
    # 새 방은 초대 링크로만 들어온다(ROOM_POLICY §3). 이전 방은 그대로 주소로 들어온다.
    room_invite_required: bool = True

    # 설정하면 배포 URL을 요청 호스트 대신 이 값으로 만든다 (예: https://example.com).
    public_base_url: Optional[str] = None
    # 생성 사이트·시안을 앱과 다른 주소(출처)에서 연다 (S-1). 예: 144-24-91-250.sslip.io
    # 설정하면 앱 주소의 /site·/design은 이 주소로 보내고, 이 주소에서는 생성물·문의 접수만 연다.
    preview_host: Optional[str] = None

    # compose에서는 db 서비스를 가리킨다. 로컬 개발은 .env에서 덮어쓴다.
    database_url: str = "postgresql+psycopg://agt001:agt001@localhost:5432/agt001"
    # 기동 시 alembic upgrade head를 실행한다. 테스트는 픽스처가 직접 실행하므로 끈다.
    run_migrations_on_startup: bool = True


settings = Settings()
