"""채팅방 사진 (contracts/ROOM_FEATURES_API.md §4, 보안 S-6).

- 올린 사진은 위치 정보(EXIF)를 지우고 긴 변 MAX_SIDE로 줄여 JPEG로 다시 저장한다. 원본은 보관하지 않는다.
- 파일은 generated/uploads/<방>/<id>.jpg, 주소는 /uploads/<방>/<id>.jpg (생성물 전용 주소에서 열림).
- 요구사항 카드(card["photos"])에도 넣어 시안·공개 사이트의 대표 사진·사진첩에 쓴다.
"""
import io
import secrets
from typing import Optional

from app import store
from app.config import settings
from app.db.models import AttachmentRow
from app.db.session import get_sessionmaker
from app.security import sanitize_token

MAX_BYTES = 10 * 1024 * 1024
MAX_SIDE = 1600
MAX_PER_ROOM = 30
ALLOWED_FORMATS = ("JPEG", "PNG", "WEBP")


class PhotoError(Exception):
    """사용자에게 보여 줄 한 줄."""


def _dir(room_id: str):
    return settings.generated_dir / "uploads" / room_id


def url_for(room_id: str, photo_id: str) -> str:
    return f"/uploads/{room_id}/{photo_id}.jpg"


def _clean_image(data: bytes) -> tuple[bytes, int, int]:
    from PIL import Image, ImageOps

    if len(data) > MAX_BYTES:
        raise PhotoError("사진은 10MB까지 올릴 수 있어요.")
    try:
        img = Image.open(io.BytesIO(data))
        fmt = img.format
        img.load()
    except Exception:
        raise PhotoError("사진 파일을 읽을 수 없어요. JPEG·PNG·WebP로 올려 주세요.")
    if fmt not in ALLOWED_FORMATS:
        raise PhotoError("JPEG·PNG·WebP 사진만 올릴 수 있어요.")
    img = ImageOps.exif_transpose(img)  # 돌려 찍은 사진을 바로 세운 뒤 EXIF는 버린다
    img = img.convert("RGB")
    img.thumbnail((MAX_SIDE, MAX_SIDE))
    out = io.BytesIO()
    img.save(out, "JPEG", quality=85, optimize=True)  # 새로 쓴 파일에는 EXIF·GPS가 없다
    return out.getvalue(), img.width, img.height


# AI 예시 이미지 전용 후처리 (업로드 사진 기준과 분리).
# 히어로는 넓은 화면에 크게 깔리므로 1920px·q90으로 보존하고 가볍게 샤픈한다.
AI_MAX_SIDE = 1920
AI_JPEG_QUALITY = 90


def _clean_ai_image(data: bytes) -> tuple[bytes, int, int]:
    """AI 생성 바이트 → EXIF 없는 JPEG 1920px·q90. 원본 형식은 검사만 한다."""
    from PIL import Image, ImageEnhance, ImageOps

    if len(data) > MAX_BYTES:
        raise PhotoError("사진은 10MB까지 올릴 수 있어요.")
    try:
        img = Image.open(io.BytesIO(data))
        fmt = img.format
        img.load()
    except Exception:
        raise PhotoError("사진 파일을 읽을 수 없어요. JPEG·PNG·WebP로 올려 주세요.")
    if fmt not in ALLOWED_FORMATS:
        raise PhotoError("JPEG·PNG·WebP 사진만 올릴 수 있어요.")
    img = ImageOps.exif_transpose(img)
    img = img.convert("RGB")
    img.thumbnail((AI_MAX_SIDE, AI_MAX_SIDE))
    img = ImageEnhance.Sharpness(img).enhance(1.15)
    out = io.BytesIO()
    img.save(out, "JPEG", quality=AI_JPEG_QUALITY, optimize=True)
    return out.getvalue(), img.width, img.height


def add(room_id_raw: str, member_id_raw: str, data: bytes, caption: Optional[str] = None,
        tag: Optional[str] = None) -> dict:
    from app.services import rooms

    room_id = sanitize_token(room_id_raw or "")
    member_id = sanitize_token(member_id_raw or "")
    clean, width, height = _clean_image(data)
    photo_id = secrets.token_hex(8)
    caption = (caption or "").strip()[:80] or None
    tag = (tag or "").strip()[:80] or None  # 항목 이름이 한글이라 sanitize_token을 쓰지 않는다
    with store.room_tx(room_id) as (room, session):
        if room is None or not any(m["member_id"] == member_id for m in room["members"]):
            raise rooms.RoomNotFound(room_id)
        card = session.get("prd") or {}
        if tag and session.get("prd"):
            # 항목 태그는 지금 카드 후보 안에 있을 때만 둔다. 아니면 버린다.
            from app.services import photo_needs
            if not photo_needs.valid_tag(session["prd"], tag):
                tag = None
        elif tag:
            tag = None
        if len(card.get("photos") or []) >= MAX_PER_ROOM:
            raise PhotoError(f"사진은 한 방에 {MAX_PER_ROOM}장까지예요.")
        folder = _dir(room_id)
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"{photo_id}.jpg").write_bytes(clean)
        with get_sessionmaker()() as db, db.begin():
            db.add(AttachmentRow(id=photo_id, room_id=room_id, member_id=member_id, caption=caption,
                                 width=width, height=height))
        url = url_for(room_id, photo_id)
        if session.get("prd") is not None:
            photo = {"id": photo_id, "url": url, "caption": caption}
            if tag is not None:
                photo["tag"] = tag
            session["prd"].setdefault("photos", []).append(photo)
        from app.services import funnel as _funnel
        _funnel.record("photo_uploaded", session_id=session.get("id"))  # D48·D45: 실제 업로드 기록
        if session.get("design_url") and session.get("prd"):
            # 시안이 이미 있으면 사진을 넣어 다시 만든다(스크린샷 때문에 몇 초 걸려 커밋 뒤 뒤에서).
            store.after_commit(lambda: _refresh_designs_async(room_id, session["requirement_id"]))
        nickname = next(m["nickname"] for m in room["members"] if m["member_id"] == member_id)
        rooms._append(room, member_id, nickname, "사진을 올렸어요" + (f": {caption}" if caption else ""),
                      kind="photo", meta={"photo": {"id": photo_id, "url": url}})
    return {"id": photo_id, "url": url}


def remove(room_id_raw: str, member_id_raw: str, photo_id_raw: str) -> None:
    from app.services import rooms

    room_id = sanitize_token(room_id_raw or "")
    member_id = sanitize_token(member_id_raw or "")
    photo_id = sanitize_token(photo_id_raw or "")
    with get_sessionmaker()() as db:
        row = db.get(AttachmentRow, photo_id)
    if row is None or row.room_id != room_id:
        raise rooms.InvalidRequest("photo not found")
    with store.room_tx(room_id) as (room, session):
        if room is None or not any(m["member_id"] == member_id for m in room["members"]):
            raise rooms.RoomNotFound(room_id)
        if member_id not in (row.member_id, rooms.owner_id(room)):
            raise rooms.NotOwner(room_id)  # 올린 사람 또는 방장만
        (_dir(room_id) / f"{photo_id}.jpg").unlink(missing_ok=True)
        with get_sessionmaker()() as db, db.begin():
            db.execute(AttachmentRow.__table__.delete().where(AttachmentRow.id == photo_id))
        if session.get("prd"):
            session["prd"]["photos"] = [p for p in session["prd"].get("photos") or [] if p["id"] != photo_id]
            if session.get("design_url"):
                # 지운 사진이 시안·공개본에 깨진 이미지로 남지 않게 다시 만든다(올릴 때와 같은 길).
                store.after_commit(lambda: _refresh_designs_async(room_id, session["requirement_id"]))
        if session.get("design_url") and session.get("prd"):
            # 지운 사진이 시안·공개본에 남지 않게 다시 만든다 (올릴 때와 같은 경로).
            store.after_commit(lambda: _refresh_designs_async(room_id, session["requirement_id"]))


def _refresh_designs_async(room_id: str, requirement_id: str) -> None:
    import threading
    threading.Thread(target=refresh_designs, args=(room_id, requirement_id), daemon=True).start()


def refresh_designs(room_id: str, requirement_id: str) -> None:
    """올린 사진을 넣어 시안 3안을 다시 만들고, 공개했으면 공개본도 바꾼 뒤 방에 알린다."""
    import logging
    from app.services import design, rooms
    log = logging.getLogger(__name__)
    try:
        room = store.read_room(room_id)
        session = store.read_session(room["session_id"]) if room else None
        card = (session or {}).get("prd")
        if not card:
            return
        design.render_variants(requirement_id, card)
        announced = "사진·영상을 시안에 넣었어요."
        if card.get("published"):
            from app.services.publish_check import PublishBlockedError
            try:
                design.publish_choice(requirement_id, card, card["published"])
                announced += " 공개 사이트에도 바로 반영했어요."
            except PublishBlockedError as e:
                announced += " 공개 전에 걸려서 공개 사이트는 그대로 뒀어요: " + "; ".join(e.reasons)
        with store.room_tx(room_id) as (r, _s):
            if r is not None:
                text = announced
                rooms._append(r, "system", "시스템", text, kind="system")
    except Exception:
        log.exception("사진 반영 실패 room=%s", room_id)
