"""빌더에서 사진 고치기 (PHOTO_EDIT_CONTRACT §1~§4, P1a 서버 묶음).

- 미리보기에서 누른 사진의 칸(slot)과 종류(owner·ai·example)를 찾는다.
- 사장님 사진은 보정(Pillow)만, AI·예시 사진은 AI 고치기 + 보정.
- 고친 결과는 후보로만 만들고, "이걸로 쓰기" 때 카드에 쓴다. 되돌리기 1단계.
"""
import datetime
import io
import re
import secrets
import time
from pathlib import Path

from app.config import settings
from app.security import sanitize_token
from app.services import ai_images
from app.services import photos

# 한국 날짜 기준 (하루 제한용)
KST = datetime.timezone(datetime.timedelta(hours=9))
# 하루 AI 고치기 상한 (가게당)
DAY_LIMIT = 10
# 후보 유효 시간 (30분)
CANDIDATE_TTL_SEC = 30 * 60

UNKNOWN = "이 사진은 여기서 고칠 수 없어요"
OWNER_ONLY = ("실제 사진은 밝기·색감·선명도·자르기만 바꿀 수 있어요. "
              "내용을 바꾸려면 AI 예시 사진으로 바꿔 주세요")
FORBIDDEN = "사람·글자·간판·로고는 넣을 수 없어요"
NO_UNDO = "되돌릴 게 없어요"
EXPIRED = "후보가 만료됐어요. 다시 만들어 주세요"

ACTIONS = ("brighter", "warmer", "sharper", "square", "wide")

# 사진첩 구역 bind (gallery-N 칸)
_GALLERY_BINDS = ("space_photos", "style_photos", "menu_photos")

# 말 거르기 금지 낱말 (§3)
_FORBIDDEN_WORDS = ("얼굴", "사람", "인물", "글자", "글씨", "문구", "간판",
                    "로고", "상호", "이름", "브랜드", "text", "logo", "face", "person")


def _entries(sec: dict) -> list:
    """구역 안 사진 목록 [(주소, 이름)]. 이름은 항목 칸(item:<이름>)용."""
    content = sec.get("content") or {}
    if isinstance(content.get("image"), str) and content["image"]:
        return [(content["image"], None)]
    out = []
    items = content.get("items")
    if isinstance(items, list):
        for item in items:
            if not isinstance(item, dict):
                continue
            src = item.get("src")
            if isinstance(src, str) and src:
                name = item.get("caption") or item.get("alt") or item.get("name") or None
                out.append((src, str(name) if name else None))
            elif str(item.get("name") or "").strip() and isinstance(item.get("image"), str):
                out.append((item["image"], str(item["name"])))
    rooms = content.get("rooms")
    if isinstance(rooms, list):
        for room in rooms:
            if isinstance(room, dict) and isinstance(room.get("image"), str) and room["image"]:
                out.append((room["image"], str(room.get("name") or "")))
    cats = content.get("categories")
    if isinstance(cats, list):
        for group in cats:
            if not isinstance(group, dict):
                continue
            if isinstance(group.get("image"), str) and group["image"]:
                out.append((group["image"], str(group.get("name") or "")))
    return out


def _path_for_url(url: str) -> Path | None:
    """/uploads/·/art/ 주소 → 읽을 파일 경로. 밖이면 None."""
    if not isinstance(url, str):
        return None
    if url.startswith("/uploads/"):
        rest = [p for p in url[len("/uploads/"):].split("/") if p not in ("", ".", "..")]
        if not rest:
            return None
        return settings.generated_dir / "uploads" / Path(*rest)
    if url.startswith("/art/"):
        rest = [p for p in url[len("/art/"):].split("/") if p not in ("", ".", "..")]
        if not rest:
            return None
        return settings.templates_dir / "art" / Path(*rest)
    return None


def _owner_urls(card: dict) -> set:
    return {str(p.get("url")) for p in (card.get("photos") or [])
            if isinstance(p, dict) and str(p.get("url") or "").startswith("/uploads/")}


def _ai_urls(card: dict) -> set:
    out = set()
    for entry in ((card.get("ai_images") or {}).values() or []):
        if isinstance(entry, dict) and str(entry.get("url") or "").startswith("/uploads/"):
            out.add(str(entry["url"]))
    return out


def resolve_target(card: dict, spec: dict, section: str, src: str, index: int) -> dict:
    """누른 사진의 칸·종류·지금 주소·파일 경로. 모르면 ValueError."""
    node = next((s for s in (spec.get("sections") or [])
                 if isinstance(s, dict) and s.get("id") == section), None)
    if node is None:
        raise ValueError(UNKNOWN)
    found = _entries(node)
    if not found:
        raise ValueError(UNKNOWN)
    pos = next((i for i, (url, _name) in enumerate(found) if url == src), None)
    if pos is None:
        if isinstance(index, int) and 0 <= index < len(found):
            pos = index
        else:
            raise ValueError(UNKNOWN)
    url, name = found[pos]
    bind = node.get("bind") or "none"
    if node.get("id") == "hero" or bind == "hero":
        target = "hero"
    elif bind in _GALLERY_BINDS or node.get("type") == "gallery":
        target = f"gallery-{pos + 1}"
    else:
        item_name = (name or "").strip()
        if not item_name:
            raise ValueError(UNKNOWN)
        target = "item:" + item_name
    if url in _owner_urls(card):
        kind = "owner"
    elif url in _ai_urls(card):
        kind = "ai"
    elif url.startswith("/art/"):
        kind = "example"
    else:
        raise ValueError(UNKNOWN)
    return {"target": target, "kind": kind, "current_url": url,
            "current_path": str(_path_for_url(url) or "")}


def actions_for(kind: str) -> list[str]:
    """보정 버튼 5개 (종류와 관계없이 같다)."""
    del kind
    return list(ACTIONS)


def adjust(image_bytes: bytes, action: str) -> bytes:
    """보정 1회 (Pillow만, §2). 결과는 _clean_image와 같은 규칙으로 저장."""
    from PIL import Image, ImageEnhance

    try:
        img = Image.open(io.BytesIO(image_bytes))
        img.load()
    except Exception:
        raise ValueError("사진 파일을 읽을 수 없어요.")
    if action == "brighter":
        img = ImageEnhance.Brightness(img).enhance(1.15)
    elif action == "warmer":
        img = img.convert("RGB")
        red, green, blue = img.split()
        red = red.point(lambda v: min(255, int(v * 1.06)))
        blue = blue.point(lambda v: min(255, int(v * 0.94)))
        img = Image.merge("RGB", (red, green, blue))
    elif action == "sharper":
        img = ImageEnhance.Sharpness(img).enhance(1.5)
        img = ImageEnhance.Contrast(img).enhance(1.05)
    elif action in ("square", "wide"):
        width, height = img.size
        if action == "square":
            side = min(width, height)
            want_w, want_h = side, side
        else:
            if width / height > 4 / 3:
                want_w, want_h = int(height * 4 / 3), height
            else:
                want_w, want_h = width, int(width * 3 / 4)
        left, top = (width - want_w) // 2, (height - want_h) // 2
        img = img.crop((left, top, left + want_w, top + want_h))
    else:
        raise ValueError("그런 고치기는 없어요.")
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "JPEG", quality=90)
    clean, _w, _h = photos._clean_image(buf.getvalue())
    return clean


def action_from_words(text: str) -> str | None:
    """말에서 보정 낱말 찾기. 못 찾으면 None."""
    words = str(text or "")
    if "밝" in words:
        return "brighter"
    if "따뜻" in words:
        return "warmer"
    if "선명" in words:
        return "sharper"
    if "정사각" in words:
        return "square"
    if "가로" in words:
        return "wide"
    return None


def clean_instruction(text: str) -> str:
    """AI에 보낼 말 거르기 (§3). 금지 낱말이면 ValueError."""
    words = re.sub(r"\s+", " ", str(text or "").replace("\n", " ")).strip()
    if not words or len(words) > 100:
        raise ValueError("고칠 말은 1~100자로 한 줄로 말해 주세요.")
    lowered = words.lower()
    if any(bad in (lowered if bad.isascii() else words) for bad in _FORBIDDEN_WORDS):
        raise ValueError(FORBIDDEN)
    # 숫자·전화·주소 모양은 뺀다 (숫자가 든 토큰 제거)
    words = re.sub(r"\S*\d\S*", "", words)
    words = re.sub(r"\s+", " ", words).strip()
    if not words:
        raise ValueError("고칠 말은 1~100자로 한 줄로 말해 주세요.")
    return words


def _kst_today() -> str:
    return datetime.datetime.now(KST).date().isoformat()


def _check_ai_limits(card: dict, slot: str) -> None:
    """쿨다운(칸마다 10분, 후보를 만든 시각 기준) + 하루 10번. 넘으면 ValueError."""
    at = max(((card.get("ai_images") or {}).get(slot) or {}).get("at") or 0,
             (card.get("ai_edit_at") or {}).get(slot) or 0)
    left = int(ai_images.COOLDOWN_SEC - (time.time() - at))
    if left > 0:
        raise ValueError(f"같은 사진은 {left // 60 + 1}분 뒤에 다시 고칠 수 있어요.")
    rec = card.get("ai_edit_day") or {}
    if rec.get("date") != _kst_today():
        rec = {"date": _kst_today(), "n": 0}
        card["ai_edit_day"] = rec
    if int(rec.get("n") or 0) >= DAY_LIMIT:
        raise ValueError("오늘 AI 사진 고치기를 다 썼어요(하루 10번). 내일 다시 해 주세요.")


def _prune_candidates(session: dict) -> None:
    """지난 후보 파일·기록 지우기."""
    cands = session.get("photo_candidates") or {}
    now = time.time()
    for cid in [k for k, v in cands.items()
                if not isinstance(v, dict) or now - (v.get("at") or 0) > CANDIDATE_TTL_SEC]:
        try:
            file = (cands[cid] or {}).get("file")
            if file:
                Path(file).unlink(missing_ok=True)
        except OSError:
            pass
        del cands[cid]


def make_candidate(room_id: str, session: dict, target: dict, *,
                   action: str | None = None, instruction: str | None = None) -> dict:
    """후보 1개 만들기. 카드는 그대로 두고 후보 파일만 쓴다."""
    card = session.get("prd")
    if not isinstance(card, dict):
        raise ValueError(UNKNOWN)
    slot = target.get("target") or ""
    before_url = target.get("current_url") or ""
    if not slot or not before_url:
        raise ValueError(UNKNOWN)
    # 종류·읽을 파일은 넘겨받은 값이 아니라 주소로 서버가 직접 정한다 (검토 9/30):
    # kind를 믿으면 사장님 사진에 AI 편집(D57 위반), 경로를 믿으면 서버의 아무 파일이나 AI로 보낼 수 있다.
    if before_url in _owner_urls(card):
        kind = "owner"
    elif before_url in _ai_urls(card):
        kind = "ai"
    elif before_url.startswith("/art/"):
        kind = "example"
    else:
        raise ValueError(UNKNOWN)
    _prune_candidates(session)
    if kind == "owner":
        use_action = action or (action_from_words(instruction or "") if instruction else None)
        if use_action is None:
            raise ValueError(OWNER_ONLY)
        if use_action not in ACTIONS:
            raise ValueError("그런 고치기는 없어요.")
        use_ai = False
        cleaned = ""
    else:
        if action is not None:
            if action not in ACTIONS:
                raise ValueError("그런 고치기는 없어요.")
            use_action, use_ai, cleaned = action, False, ""
        elif instruction:
            use_action, use_ai = None, True
            cleaned = clean_instruction(instruction)
        else:
            raise ValueError("보정 버튼이나 고칠 말 중에서 골라 주세요.")
    room = sanitize_token(room_id)
    current = _path_for_url(before_url)
    if current is None:
        raise ValueError(UNKNOWN)
    try:
        image_bytes = current.read_bytes()
    except OSError:
        raise ValueError("지금 사진을 읽을 수 없어요.")
    if use_ai:
        _check_ai_limits(card, slot)
        raw = ai_images.edit_bytes(image_bytes, cleaned, slot)
        clean, _w, _h = photos._clean_ai_image(raw)
        rec = card.setdefault("ai_edit_day", {"date": _kst_today(), "n": 0})
        if rec.get("date") != _kst_today():
            rec["date"], rec["n"] = _kst_today(), 0
        rec["n"] = int(rec.get("n") or 0) + 1
        card.setdefault("ai_edit_at", {})[slot] = time.time()  # 적용하지 않고 후보만 거듭 만들어도 10분 제한
    else:
        clean = adjust(image_bytes, use_action)
    folder = photos._dir(room)
    folder.mkdir(parents=True, exist_ok=True)
    fid = "cand-" + secrets.token_hex(4)
    (folder / f"{fid}.jpg").write_bytes(clean)
    after_url = photos.url_for(room, fid)
    cid = "c" + secrets.token_hex(4)
    session.setdefault("photo_candidates", {})[cid] = {
        "target": slot, "kind": kind, "before_url": before_url,
        "after_url": after_url, "file": str(folder / f"{fid}.jpg"), "at": time.time()}
    return {"candidate_id": cid, "before_url": before_url, "after_url": after_url}


def _owner_photo(card: dict, slot: str, before_url: str) -> dict | None:
    """before 주소와 같은 사장님 사진. 없으면 None."""
    del slot
    for photo in card.get("photos") or []:
        if isinstance(photo, dict) and photo.get("url") == before_url:
            return photo
    return None


def apply_candidate(session: dict, candidate_id: str) -> dict:
    """후보를 카드에 쓰기. 30분 지나면 거절. 원래 주소는 prev로 보관."""
    cands = session.get("photo_candidates") or {}
    entry = cands.get(candidate_id)
    if not isinstance(entry, dict):
        raise ValueError(EXPIRED)
    if time.time() - (entry.get("at") or 0) > CANDIDATE_TTL_SEC:
        try:
            Path(entry.get("file") or "").unlink(missing_ok=True)
        except OSError:
            pass
        del cands[candidate_id]
        raise ValueError(EXPIRED)
    card = session.get("prd")
    if not isinstance(card, dict):
        raise ValueError(EXPIRED)
    slot, after_url = entry.get("target") or "", entry.get("after_url") or ""
    before_url = entry.get("before_url") or ""
    if not slot or not after_url:
        raise ValueError(EXPIRED)
    photo = _owner_photo(card, slot, before_url)
    if photo is not None:
        photo["prev_url"] = photo.get("url")
        photo["prev_slot"] = slot  # 되돌리기가 칸 위치를 추측하지 않고 이 사진을 찾게
        photo["url"] = after_url
    else:
        ai_images._record(card, slot, after_url, prev_url=before_url)
    del cands[candidate_id]
    _prune_candidates(session)
    return {"url": after_url}


def undo(session: dict, target: str) -> dict:
    """직전 사진으로 되돌리기 1단계."""
    card = session.get("prd")
    if not isinstance(card, dict):
        raise ValueError(NO_UNDO)
    entry = (card.get("ai_images") or {}).get(target)
    if isinstance(entry, dict) and entry.get("prev_url"):
        url = entry.pop("prev_url")
        entry["url"] = url
        return {"url": url}
    for photo in card.get("photos") or []:
        if isinstance(photo, dict) and photo.get("prev_slot") == target and photo.get("prev_url"):
            url = photo.pop("prev_url")
            photo.pop("prev_slot", None)
            photo["url"] = url
            return {"url": url}
    raise ValueError(NO_UNDO)
