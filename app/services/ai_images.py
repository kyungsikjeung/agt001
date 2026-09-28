"""포토리얼 예시 이미지 (Gemini 이미지 생성).

사장님 사진이 없을 때 시안·공개본의 빈 사진 칸을 AI 사진으로 채운다.
- 생성은 버튼을 눌러야만 일어난다(자동 생성 없음, 비용 통제).
- 프롬프트는 업종·용도 키워드만 쓴다. 가게 이름·전화·주소·가격 등 개인정보·사실은 절대 넣지 않는다(D26·D35).
- 사장님 사진이 오면 AI 사진보다 항상 먼저 쓴다(D36). AI 사진에는 "AI 예시 이미지" 배지가 붙는다.
- 파일은 generated/uploads/<방>/ai-<용도>.jpg, 주소는 /uploads/<방>/ai-<용도>.jpg (사진과 같은 서빙 경로).
"""
import base64
import hashlib
import logging
import time

import httpx

from app import store
from app.config import settings
from app.services import funnel

log = logging.getLogger(__name__)

# 사진 칸 용도: 대표 1장 + 사진첩 2장 (site_render._ILLU_NAMES와 같음).
SLOTS = ("hero", "gallery-1", "gallery-2")
# 한 가게의 항목 그림은 최대 4장 (비용 통제).
ITEM_MAX = 4
# 같은 칸 재생성 간격 (스팸·비용 방지).
COOLDOWN_SEC = 10 * 60


class ImageError(Exception):
    """사용자에게 보여 줄 한 줄."""


# 업종별 프롬프트 소재 (영문, 고유명사·문자·사람 얼굴 없음).
# hero는 넓은 첫 화면용, gallery는 정사각형에 가까운 사진첩용.
_SUBJECT = {
    "pension": "a cozy countryside guesthouse exterior at dusk, warm lights in windows",
    "cafe": "a warm cafe interior with wooden tables and cups of coffee",
    "restaurant": "a cozy Korean restaurant interior with wooden tables, warm lighting",
    "salon": "a bright modern hair salon interior with chairs and mirrors",
    "workshop": "a craft workshop table with pottery tools and clay works in progress",
    "academy": "a bright classroom interior with desks and a whiteboard",
    "individual": "a calm private lesson studio interior with an instrument",
    "group": "a welcoming community classroom interior with round tables",
    "webservice": "a clean modern office desk with a laptop showing a website mockup",
    "other": "a warm small shop interior with wooden shelves",
}
_GALLERY_EXTRA = {
    "hero": "wide banner composition, 16:9",
    "gallery-1": "close-up detail shot, square composition, 1:1",
    "gallery-2": "wide angle view from another corner, square composition, 1:1",
}
# 항목 kind별 구도 (이름은 프롬프트에 그대로 넣는다).
_ITEM_FRAMING = {
    "room": "interior of a guest room, natural light, tidy bedding",
    "menu": "the dish or drink on a table, close-up, appetizing",
    "style": "hairstyle result seen from behind or the side in a salon, face not visible",
    "class": "hands-on class scene, tools and materials on a table, faces not visible",
    "work": "the finished work or service result on a clean background",
}
# 저가 모델에서도 질감을 살리는 촬영 지시 (D26·D35: 사실·개인정보는 넣지 않는다).
_STYLE_SUFFIX = ("shot on 35mm, f/2.8, soft window light, natural materials, "
                 "editorial composition, ultra-detailed")
# 슬롯별 출력 규격 (지원 모델은 따르고, 구모델은 무시하고 만든다).
_IMAGE_CONFIG = {
    "hero": {"aspectRatio": "16:9", "imageSize": "2K"},
    "gallery-1": {"aspectRatio": "1:1", "imageSize": "1K"},
    "gallery-2": {"aspectRatio": "1:1", "imageSize": "1K"},
}


def _normalize_kind(kind) -> str:
    if isinstance(kind, str) and kind.strip().lower() in _SUBJECT:
        return kind.strip().lower()
    return "other"


def _is_item_slot(slot: str) -> bool:
    return isinstance(slot, str) and slot.startswith("item:")


def _file_id(slot: str) -> str:
    """저장 파일 이름(확장자 없음). 항목은 md5 앞 8자로 파일명에 콜론이 없게."""
    if _is_item_slot(slot):
        return "ai-item-" + hashlib.md5(slot[5:].encode("utf-8")).hexdigest()[:8]
    return "ai-" + slot


def prompt_for(kind: str, slot: str, item_kind: str = "work") -> str:
    """카드 사실을 넣지 않는 고정 프롬프트. (개인정보가 들어갈 자리가 없다.)"""
    safe_kind = _normalize_kind(kind)
    if _is_item_slot(slot):
        name = slot[5:].strip()
        if not name:
            raise ImageError("hero·gallery-1·gallery-2·items·all 중에서 골라 주세요.")
        subject = _SUBJECT[safe_kind]
        framing = _ITEM_FRAMING.get(item_kind, _ITEM_FRAMING["work"])
        if item_kind in ("style", "class"):
            suffix = "face not visible, no text, no letters, no logos, no watermarks"
        else:
            suffix = "no people, no faces, no text, no letters, no logos, no watermarks"
        return (f"{subject}, featuring {name}, {framing}, {_STYLE_SUFFIX}, photorealistic, "
                f"natural daylight tones, {suffix}")
    if slot not in SLOTS:
        raise ImageError("hero·gallery-1·gallery-2 중에서 골라 주세요.")
    subject = _SUBJECT[safe_kind]
    framing = _GALLERY_EXTRA[slot]
    return (f"{subject}, {framing}, {_STYLE_SUFFIX}, photorealistic, natural daylight tones, "
            "no people, no faces, no text, no letters, no logos, no watermarks")


def _model_for(slot: str) -> str:
    """슬롯별 이미지 모델. hero는 상위 모델 지정이 있으면 그걸, 나머지는 기본 모델."""
    base = (settings.gemini_image_model or "gemini-2.5-flash-image").strip()
    if slot == "hero":
        hero = (settings.gemini_image_model_hero or "").strip()
        if hero:
            return hero
    return base  # 항목 칸도 기본 모델 (갤러리 칸과 같다)


def _generate_bytes(prompt: str, timeout_sec: float = 120.0, slot: str = "hero") -> bytes:
    """Gemini 이미지 1장 생성. 실패하면 ImageError(사용자용 한 줄)."""
    from app.services import keystore
    key = (keystore.get("gemini_api_key") or "").strip()
    if not key:
        raise ImageError("AI 이미지 키가 아직 없어요. 관리자에게 문의해 주세요.")
    base = (settings.gemini_api_base or "https://generativelanguage.googleapis.com").rstrip("/")
    model = _model_for(slot)
    # 항목 칸은 갤러리 칸과 같은 규격으로 만든다.
    image_config = _IMAGE_CONFIG.get(slot, _IMAGE_CONFIG["gallery-1"])
    try:
        r = httpx.post(
            f"{base}/v1beta/models/{model}:generateContent",
            timeout=timeout_sec,
            # 키는 주소가 아니라 머리글로: httpx가 요청 주소를 INFO 로그에 남긴다
            headers={"x-goog-api-key": key},
            json={"contents": [{"parts": [{"text": prompt}]}],
                  "generationConfig": {"responseModalities": ["IMAGE"],
                                       "imageConfig": image_config}},
        )
    except httpx.HTTPError as e:
        log.warning("Gemini 이미지 연결 실패: %s", type(e).__name__)
        raise ImageError("지금은 AI 이미지를 만들 수 없어요. 잠시 뒤에 다시 시도해 주세요.")
    if r.status_code != 200:
        log.warning("Gemini 이미지 응답 %s: %s", r.status_code, r.text[:200])
        raise ImageError("지금은 AI 이미지를 만들 수 없어요. 잠시 뒤에 다시 시도해 주세요.")
    try:
        parts = r.json().get("candidates", [{}])[0].get("content", {}).get("parts", [])
    except (ValueError, AttributeError, IndexError):
        parts = []
    for p in parts:
        inline = (p or {}).get("inlineData") or {}
        data = inline.get("data")
        if data:
            try:
                return base64.b64decode(data)
            except (ValueError, TypeError):
                break
    log.warning("Gemini 이미지 내용 없음")
    raise ImageError("AI 이미지가 비어 나왔어요. 다시 눌러 주세요.")


def _save(room_id: str, slot: str, raw: bytes) -> str:
    """JPEG 1920px·q90으로 다듬어 저장하고 주소를 돌려준다 (업로드 사진 q85와 분리)."""
    from app.services import photos
    clean, _, _ = photos._clean_ai_image(raw)
    folder = photos._dir(room_id)
    folder.mkdir(parents=True, exist_ok=True)
    fid = _file_id(slot)
    (folder / f"{fid}.jpg").write_bytes(clean)
    return photos.url_for(room_id, fid)


def _cooldown_left(card: dict, slot: str) -> int:
    """재생성 대기 남은 초. 0이면 바로 만들 수 있다."""
    at = ((card.get("ai_images") or {}).get(slot) or {}).get("at") or 0
    left = int(COOLDOWN_SEC - (time.time() - at))
    return left if left > 0 else 0


def _record(card: dict, slot: str, url: str) -> None:
    imgs = card.setdefault("ai_images", {})
    imgs[slot] = {"url": url, "at": time.time()}


def _wants(slot: str, card: dict) -> list[str]:
    """만들 칸 목록. "items"는 사진 없는 항목만, "all"은 오늘 칸 + 항목."""
    from app.services import photo_needs
    if slot in ("items", "all"):
        existing = sum(1 for k in (card.get("ai_images") or {}) if str(k).startswith("item:"))
        room = max(0, ITEM_MAX - existing)
        item_slots = ["item:" + n for n in photo_needs.missing(card)[:room]]
        if slot == "items":
            return item_slots
        return list(SLOTS) + item_slots
    return [slot]


# 방 알림에 쓰는 칸 이름 (사장님께는 한국어로만 보인다).
_SLOT_LABELS = {"hero": "대표 사진", "gallery-1": "사진첩 1", "gallery-2": "사진첩 2", "all": "전체"}


def _label(slot: str) -> str:
    return slot[5:] if _is_item_slot(slot) else _SLOT_LABELS.get(slot, slot)


def _item_kind(card: dict, name: str) -> str:
    from app.services import photo_needs
    for item in photo_needs.items(card):
        if item["name"] == name:
            return item.get("kind") or "work"
    return "work"


def ensure(room_id: str, slot: str, *, by_owner: bool = True) -> dict:
    """버튼 생성 1회: 빠진 칸만 만들어 카드에 남기고 시안·공개본을 바꾼 뒤 방에 알린다.

    동기 함수라 API는 뒤 스레드에서 부른다(사진 _refresh_designs_async와 같은 모양).
    돌려주는 값: {"made": [slot], "skipped": {slot: 이유}}.
    """
    from app.services import design, rooms
    from app.services import prd_engine as E

    if slot not in (*SLOTS, "items", "all") and not _is_item_slot(slot):
        raise ImageError("hero·gallery-1·gallery-2·items·all 중에서 골라 주세요.")
    if not by_owner:
        raise rooms.NotOwner(room_id)
    room = store.read_room(room_id)
    session = store.read_session(room["session_id"]) if room else None
    card = (session or {}).get("prd")
    if room is None or card is None:
        raise rooms.RoomNotFound(room_id)

    made, skipped = [], {}
    kind = E.industry_of(card).key
    wants = _wants(slot, card)
    if card.get("photos"):
        # 사장님 사진이 있으면 대표·사진첩 칸은 건너뛴다. 항목 그림은 계속 만든다.
        for s in wants:
            if s in SLOTS:
                skipped[s] = "사장님 사진이 있어서 AI 이미지가 필요 없어요."
        wants = [s for s in wants if s not in SLOTS]
    for s in wants:
        if ((card.get("ai_images") or {}).get(s) or {}).get("url"):
            skipped[s] = "이미 있어요."
            continue
        left = _cooldown_left(card, s)
        if left > 0:
            skipped[s] = f"{left // 60 + 1}분 뒤에 다시 시도해 주세요."
            continue
        if _is_item_slot(s):
            prompt = prompt_for(kind, s, _item_kind(card, s[5:]))
        else:
            prompt = prompt_for(kind, s)
        raw = _generate_bytes(prompt, slot=s)
        url = _save(room_id, s, raw)
        with store.room_tx(room_id) as (_, session2):
            if session2 is None or session2.get("prd") is None:
                raise rooms.RoomNotFound(room_id)
            _record(session2["prd"], s, url)
        made.append(s)
        funnel.record("ai_image_made", session_id=room["session_id"],
                      props={"industry": kind, "kind": s})

    if made and session.get("design_url"):
        from app.services import photos
        photos.refresh_designs(room_id, session["requirement_id"])

    if made:
        text = "AI 예시 이미지를 넣었어요(" + ", ".join(_label(s) for s in made) + "). 사장님 사진을 올리시면 그 사진으로 바뀌어요."
    elif skipped:
        text = "AI 이미지는 만들지 않았어요: " + "; ".join(f"{_label(k)} {v}" for k, v in skipped.items())
    else:
        text = "AI 이미지는 만들지 않았어요: 사진이 필요한 항목이 없어요."
    with store.room_tx(room_id) as (r, _s):
        if r is not None:
            rooms._append(r, "system", "시스템", text, kind="system")
    return {"made": made, "skipped": skipped}


def _ensure_async(room_id: str, slot: str) -> None:
    import threading
    threading.Thread(target=_run_async, args=(room_id, slot), daemon=True).start()


def _run_async(room_id: str, slot: str) -> None:
    try:
        ensure(room_id, slot)
    except Exception:
        log.exception("AI 이미지 생성 실패 room=%s slot=%s", room_id, slot)
        try:
            from app.services import rooms
            with store.room_tx(room_id) as (r, _s):
                if r is not None:
                    rooms._append(r, "system", "시스템",
                                  "AI 이미지를 만들지 못했어요. 잠시 뒤에 다시 눌러 주세요.", kind="system")
        except Exception:
            pass
