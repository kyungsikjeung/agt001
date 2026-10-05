import asyncio
import datetime
import logging
import mimetypes
from contextlib import asynccontextmanager
from zoneinfo import ZoneInfo

from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app import store
from app.db import migrate as db_migrate
from app.api import admin, admin_keys, auth, bookings, callbot, card, chat, chat_agent, events, inquiries, live, members, orders, owner, projects, public, push, rooms, settings as owner_settings, start, stt, tts
from app.config import settings
from app.services import config_check, funnel, ops_alert, rag, stuck_report

# 서버 파이썬에 webp가 없어 예시 사진이 application/octet-stream으로 나갔다(카톡 미리보기가 그림으로 못 읽음)
mimetypes.add_type("image/webp", ".webp")
from app.services import accounts as accounts_svc
from app.services import bookings as bookings_svc
from app.services import chat_agent as chat_agent_svc
from app.services import guest_chat as guest_chat_svc
from app.services import customers as customers_svc
from app.services import inquiries as inquiries_svc
from app.services import phone_verify as phone_verify_svc

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger(__name__)

# 보관 기간이 지난 기록을 지우는 간격. 서버를 오래 안 껐다 켜도 개인정보처리방침 3항 기간을 넘기지 않게 한다.
PURGE_EVERY_SEC = 24 * 3600


def _purge_all() -> None:
    """보관 기간 지난 기록 지우기 (개인정보처리방침 3항): 서버가 뜰 때와 그 뒤 하루에 한 번."""
    funnel.purge_expired()
    store.purge_chat_turns()
    inquiries_svc.purge_expired()
    from app.services import guestbook as guestbook_svc  # 청첩장 방명록 1년
    guestbook_svc.purge_expired()
    bookings_svc.purge_expired()
    customers_svc.purge_orphans()
    phone_verify_svc.purge()
    chat_agent_svc.purge()
    guest_chat_svc.purge()
    accounts_svc.purge()
    from app.services import project_delete  # 지운 프로젝트: 7일 뒤 영구 삭제(대표 10/5)
    project_delete.purge_deleted()


async def _purge_daily() -> None:
    while True:
        await asyncio.sleep(PURGE_EVERY_SEC)
        try:
            await asyncio.to_thread(_purge_all)
        except Exception:
            log.exception("보관 기간 지난 기록을 지우지 못함 — 다음 날 다시 한다")


KST = ZoneInfo("Asia/Seoul")
MORNING_HOUR = 9  # 막힘 지표 아침 보고 (UX_GAP_PLAN Q4)


def seconds_until_next(hour: int, now: datetime.datetime | None = None) -> float:
    """다음 한국 시각 hour:00까지 남은 초. 지금이 딱 그 시각이면 다음 날."""
    now = (now or datetime.datetime.now(KST)).astimezone(KST)
    nxt = now.replace(hour=hour, minute=0, second=0, microsecond=0)
    if nxt <= now:
        nxt += datetime.timedelta(days=1)
    return (nxt - now).total_seconds()


def _send_morning() -> None:
    ops_alert.send("daily", stuck_report.morning_text(stuck_report.report(7)))


async def _morning_report() -> None:
    while True:
        # +1초: 잠이 몇 ms 일찍 깨도 9시를 넘긴 뒤 보내야 다음 계산이 내일로 간다(두 번 보내기 방지)
        await asyncio.sleep(seconds_until_next(MORNING_HOUR) + 1)
        try:
            await asyncio.to_thread(_send_morning)
        except Exception:
            log.exception("아침 보고를 보내지 못함 — 내일 다시 한다")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    ops_alert.install()  # ERROR 로그를 운영자 텔레그램으로 (OPS_ALERT_CONTRACT, 켜져 있을 때만)
    if settings.run_migrations_on_startup:
        db_migrate.upgrade_head()
    store.recover_on_startup()
    config_check.announce()  # 빠진 설정을 로그·운영 알림으로 (예외 없음, 알림은 뒤에서 보냄)
    _purge_all()
    if settings.precompute_embeddings:
        rag.precompute()
    purge_task = asyncio.create_task(_purge_daily())
    morning_task = asyncio.create_task(_morning_report())
    yield
    purge_task.cancel()
    morning_task.cancel()


# 미리보기 주소에서 여는 경로 (S-1). 나머지(로그인·채팅·API)는 앱 주소에서만.
_PREVIEW_PATHS = ("/site/", "/design/", "/uploads/", "/art/", "/art-lib/", "/api/inquiries/", "/api/rsvp/", "/api/guestbook/", "/api/bookings/", "/api/orders/", "/api/members/", "/health")
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
    app.include_router(push.router)
    app.include_router(members.router)
    app.include_router(owner.router)
    app.include_router(chat_agent.router)
    app.include_router(tts.router)
    app.include_router(card.router)
    app.include_router(live.router)
    app.include_router(start.router)
    app.include_router(callbot.router)
    app.include_router(admin.router)
    app.include_router(admin_keys.router)
    # 라우터 뒤에 마운트해야 API 경로가 우선한다. html=True로 "/"에서 index.html을 준다.
    # React 빌드 자산. 빌드 전에도 기동은 되도록 디렉터리 확인을 끈다.
    # 시안 공용 그림(D51 ① 추상·일러스트, 표시 없이 씀). 생성물과 같은 미리보기 주소에서 연다.
    app.mount("/art", StaticFiles(directory=settings.templates_dir / "art", check_dir=False), name="art")
    app.mount("/assets", StaticFiles(directory=settings.frontend_dist_dir / "assets", check_dir=False), name="assets")
    app.mount("/", StaticFiles(directory=settings.static_dir, html=True), name="static")
    return app


app = create_app()
