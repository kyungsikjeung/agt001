"""기동 시·테스트에서 Alembic 마이그레이션을 코드로 실행한다."""
from typing import Optional

from alembic import command
from alembic.config import Config

from app.config import PROJECT_ROOT, settings


def _config(url: Optional[str] = None) -> Config:
    cfg = Config(str(PROJECT_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    # ConfigParser 보간(%)과 충돌하지 않게 이스케이프한다 (비밀번호에 %가 들어갈 수 있음).
    cfg.set_main_option("sqlalchemy.url", (url or settings.database_url).replace("%", "%%"))
    return cfg


def upgrade_head(url: Optional[str] = None) -> None:
    command.upgrade(_config(url), "head")
