"""기동 시·테스트에서 Alembic 마이그레이션을 코드로 실행한다."""
import logging
from typing import Optional

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine

from app.config import PROJECT_ROOT, settings

log = logging.getLogger(__name__)


def _config(url: Optional[str] = None) -> Config:
    cfg = Config(str(PROJECT_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    # ConfigParser 보간(%)과 충돌하지 않게 이스케이프한다 (비밀번호에 %가 들어갈 수 있음).
    cfg.set_main_option("sqlalchemy.url", (url or settings.database_url).replace("%", "%%"))
    return cfg


def _current_revisions(url: Optional[str] = None) -> set[str]:
    """DB에 적힌 지금 마이그레이션 번호들(처음이면 빈 집합)."""
    engine = create_engine(url or settings.database_url)
    try:
        with engine.connect() as conn:
            return set(MigrationContext.configure(conn).get_current_heads())
    finally:
        engine.dispose()


def upgrade_head(url: Optional[str] = None) -> None:
    """DB를 이 코드의 마지막 마이그레이션까지 올린다.

    DB가 이 코드보다 앞서 있으면(새 배포가 올린 뒤 옛 코드로 되돌린 경우) 올리지 않고 건너뛴다.
    전엔 Alembic이 'Can't locate revision'으로 멈춰 되돌린 옛 코드가 아예 뜨지 못했다(REHEARSAL_1015 §0).
    마이그레이션은 더하기만 하므로(tests/unit/test_migrations_expand_only.py) 옛 코드는 새 표·칸을 모른 채 그대로 돈다.
    운영자가 알아야 하므로 ERROR로 남긴다(운영 알림으로 간다)."""
    cfg = _config(url)
    known = {rev.revision for rev in ScriptDirectory.from_config(cfg).walk_revisions()}
    ahead = sorted(r for r in _current_revisions(url) if r not in known)
    if ahead:
        log.error("DB 마이그레이션 %s가 이 코드보다 앞서 있어요(되돌린 배포?). 마이그레이션을 건너뛰고 그대로 띄웁니다. "
                  "다시 배포하면 정상으로 돌아와요.", ", ".join(ahead))
        return
    command.upgrade(cfg, "head")
