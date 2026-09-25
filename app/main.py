import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app import store
from app.db import migrate as db_migrate
from app.api import chat, events, public, rooms
from app.config import settings
from app.services import funnel, rag

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if settings.run_migrations_on_startup:
        db_migrate.upgrade_head()
    store.recover_on_startup()
    funnel.purge_expired()
    if settings.precompute_embeddings:
        rag.precompute()
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="agt001", lifespan=lifespan)
    app.include_router(public.router)
    app.include_router(chat.router)
    app.include_router(rooms.router)
    app.include_router(events.router)
    # 라우터 뒤에 마운트해야 API 경로가 우선한다. html=True로 "/"에서 index.html을 준다.
    # React 빌드 자산. 빌드 전에도 기동은 되도록 디렉터리 확인을 끈다.
    app.mount("/assets", StaticFiles(directory=settings.frontend_dist_dir / "assets", check_dir=False), name="assets")
    app.mount("/", StaticFiles(directory=settings.static_dir, html=True), name="static")
    return app


app = create_app()
