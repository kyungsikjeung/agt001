import logging
import mimetypes
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app import store
from app.db import migrate as db_migrate
from app.api import auth, bookings, callbot, card, chat, chat_agent, events, inquiries, orders, owner, projects, public, rooms, settings as owner_settings, start, stt, tts
from app.config import settings
from app.services import funnel, rag

# 서버 파이썬에 webp가 없어 예시 사진이 application/octet-stream으로 나갔다(카톡 미리보기가 그림으로 못 읽음)
mimetypes.add_type("image/webp", ".webp")
from app.services import bookings as bookings_svc
from app.services import chat_agent as chat_agent_svc
from app.services import customers as customers_svc
from app.services import inquiries as inquiries_svc
from app.services import phone_verify as phone_verify_svc

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if settings.run_migrations_on_startup:
        db_migrate.upgrade_head()
    store.recover_on_startup()
    funnel.purge_expired()
    store.purge_chat_turns()
    inquiries_svc.purge_expired()
    bookings_svc.purge_expired()
    customers_svc.purge_orphans()
    phone_verify_svc.purge()
    chat_agent_svc.purge()
    if settings.precompute_embeddings:
        rag.precompute()
    yield


# 미리보기 주소에서 여는 경로 (S-1). 나머지(로그인·채팅·API)는 앱 주소에서만.
_PREVIEW_PATHS = ("/site/", "/design/", "/uploads/", "/art/", "/art-lib/", "/api/inquiries/", "/api/bookings/", "/api/orders/", "/health")
_GENERATED_PATHS = ("/site/", "/design/", "/uploads/", "/art/", "/art-lib/")


async def _split_hosts(request: Request, call_next):
    """생성물은 미리보기 주소로, 앱은 앱 주소로 (DESIGN_PIPELINE_PLAN §13.5 S-1).

    로그인 쿠키(__Host-)는 앱 주소에만 붙으므로, 생성물이 다른 출처에서 열리면 쿠키·저장소에 닿을 수 없다."""
    preview = settings.preview_host
    if preview:
        host = (request.headers.get("host") or "").split(":")[0].lower()
        path = request.url.path
        if host == preview.lower():
            if not path.startswith(_PREVIEW_PATHS):
                return PlainTextResponse("not found", status_code=404)
        elif path.startswith(_GENERATED_PATHS):
            query = f"?{request.url.query}" if request.url.query else ""
            return RedirectResponse(f"https://{preview}{path}{query}", status_code=308)
    return await call_next(request)


def create_app() -> FastAPI:
    app = FastAPI(title="agt001", lifespan=lifespan)
    app.middleware("http")(_split_hosts)
    app.include_router(public.router)
    app.include_router(chat.router)
    app.include_router(rooms.router)
    app.include_router(events.router)
    app.include_router(stt.router)
    app.include_router(projects.router)
    app.include_router(auth.router)
    app.include_router(inquiries.router)
    app.include_router(bookings.router)
    app.include_router(orders.router)
    app.include_router(owner_settings.router)
    app.include_router(owner.router)
    app.include_router(chat_agent.router)
    app.include_router(tts.router)
    app.include_router(card.router)
    app.include_router(start.router)
    app.include_router(callbot.router)
    # 라우터 뒤에 마운트해야 API 경로가 우선한다. html=True로 "/"에서 index.html을 준다.
    # React 빌드 자산. 빌드 전에도 기동은 되도록 디렉터리 확인을 끈다.
    # 시안 공용 그림(D51 ① 추상·일러스트, 표시 없이 씀). 생성물과 같은 미리보기 주소에서 연다.
    app.mount("/art", StaticFiles(directory=settings.templates_dir / "art", check_dir=False), name="art")
    app.mount("/assets", StaticFiles(directory=settings.frontend_dist_dir / "assets", check_dir=False), name="assets")
    app.mount("/", StaticFiles(directory=settings.static_dir, html=True), name="static")
    return app


app = create_app()
