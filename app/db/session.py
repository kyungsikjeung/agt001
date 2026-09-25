"""엔진·세션 팩토리. 엔진은 처음 쓸 때 만든다 (테스트가 DATABASE_URL을 바꾼 뒤 import해도 되게)."""
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from app.config import settings


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    # 동기 핸들러가 스레드풀(기본 40)에서 돈다. db의 max_connections(30)를 넘지 않게 연결 수는 작게 유지하고
    # 대기(pool_timeout)로 흡수한다. pre_ping은 DB 재시작 뒤 끊긴 연결을 걸러낸다.
    return create_engine(settings.database_url, pool_size=5, max_overflow=5, pool_timeout=30, pool_pre_ping=True)


@lru_cache(maxsize=1)
def get_sessionmaker() -> sessionmaker:
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


def reset_engine() -> None:
    """테스트 전용: 설정이 바뀐 뒤 엔진을 다시 만든다."""
    if get_engine.cache_info().currsize:
        get_engine().dispose()
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()
