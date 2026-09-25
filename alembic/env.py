from alembic import context
from sqlalchemy import create_engine, pool

from app.config import settings
from app.db.models import Base

target_metadata = Base.metadata


def _url() -> str:
    # 호출부(테스트, 기동 처리)가 config에 URL을 넣었으면 그것을 우선한다.
    return context.config.get_main_option("sqlalchemy.url") or settings.database_url


def run_migrations_offline() -> None:
    context.configure(url=_url(), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
