import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app import store
from app.api import chat, public, rooms
from app.config import settings
from app.services import rag

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    store.sessions.load()
    store.rooms.load()
    if settings.precompute_embeddings:
        rag.precompute()
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="agt001", lifespan=lifespan)
    app.include_router(public.router)
    app.include_router(chat.router)
    app.include_router(rooms.router)
    # 라우터 뒤에 마운트해야 API 경로가 우선한다. html=True로 "/"에서 index.html을 준다.
    app.mount("/", StaticFiles(directory=settings.static_dir, html=True), name="static")
    return app


app = create_app()
