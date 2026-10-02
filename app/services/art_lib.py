"""메뉴·항목 태그 사진 창고 (ART_LIB_CONTRACT §1·§2, D58 ③).

항목 이름 → 태그(낱말표, 모르면 LLM) → 창고에 사진이 있으면 쓰고, 없으면 태그 낱말만으로 한 장 만들어 넣는다.
가게 정보(이름·전화·주소·사진)는 창고에도 AI 요청에도 넣지 않는다. 그리기 중(pick)에는 LLM·생성을 부르지 않는다.
"""
import datetime
import io
import json
import logging
import re
import threading
from functools import lru_cache
from pathlib import Path
from typing import Optional

from app.config import settings

log = logging.getLogger(__name__)

KST = datetime.timezone(datetime.timedelta(hours=9))
TAG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+){0,3}$")
_TAGS_FILE = Path(__file__).resolve().parent.parent / "data" / "art_tags.json"
# 이름에서 빼는 것: 괄호 안, 숫자+바로 붙은 단위("500ml"·"2인분"), 따로 떨어진 크기 글자(S·M·L)
# 단위만 따로 지우면 '와인'의 '인'처럼 낱말 끝이 잘린다 → 숫자 뒤에 붙은 것만 지운다
_QTY = re.compile(r"\d+(?:[.,]\d+)?\s*(?:ml|kg|oz|cc|pcs|개|잔|인분|인|l|g)?", re.I)
_SIZE = re.compile(r"(?<![0-9a-z가-힣])(?:xs|s|m|l|xl|size|사이즈)(?![0-9a-z가-힣])", re.I)
_RULES = ("no people, no faces, no hands, no text, no letters, no signage, no logos, no watermark. "
          "shot on 35mm, f/2.8, soft window light, natural materials, editorial composition, square 1:1")
_index_lock = threading.Lock()
_making: set = set()          # 지금 만드는 태그 (같은 태그는 한 번만)
_workers = threading.BoundedSemaphore(3)  # ponytail: 프로세스 안 동시 생성 3개, 서버가 여러 대면 파일 잠금이 필요


def _dir() -> Path:
    return settings.generated_dir / "art-lib"


def _today() -> str:
    return datetime.datetime.now(KST).date().isoformat()


@lru_cache(maxsize=1)
def _table() -> dict:
    """낱말표 {tag: {words, industry, prompt}}."""
    try:
        return json.loads(_TAGS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        log.exception("art_tags.json을 읽지 못했어요")
        return {}


def _load() -> dict:
    """창고 목록 {"tags": {tag: {...}}, "aliases": {정규화 이름: tag}}."""
    try:
        data = json.loads((_dir() / "index.json").read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data.setdefault("tags", {})
            data.setdefault("aliases", {})
            return data
    except (OSError, ValueError):
        pass
    return {"tags": {}, "aliases": {}}


def _update(fn) -> dict:
    """목록을 잠그고 읽고-고치고-쓴다(여러 스레드가 덮어쓰지 않게). 새 목록을 돌려준다."""
    with _index_lock:
        data = _load()
        fn(data)
        _dir().mkdir(parents=True, exist_ok=True)
        tmp = _dir() / "index.json.tmp"
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(_dir() / "index.json")
        return data


def normalize(name: str) -> str:
    """비교용 이름: 괄호 안·숫자·단위·공백을 빼고 소문자로. '아이스 아메리카노 (L)' → '아이스아메리카노'."""
    text = re.sub(r"[\(\[].*?[\)\]]", " ", str(name or ""))
    text = _SIZE.sub(" ", _QTY.sub(" ", text))
    return re.sub(r"[\s\-_/·,.]+", "", text).lower()


def _from_table(norm: str) -> Optional[str]:
    """낱말표에서 찾기: 낱말과 같거나, 이름 안에 낱말(2자 이상)이 들어 있으면. 긴 낱말이 이긴다."""
    best, best_len = None, 0
    for tag, row in _table().items():
        for word in row.get("words") or []:
            w = normalize(word)
            if len(w) < 2:
                continue
            if (w == norm or w in norm) and len(w) > best_len:
                best, best_len = tag, len(w)
    return best


def _ask_llm(name: str, industry: str, known: list) -> Optional[tuple]:
    """모르는 이름: 정해진 태그 중 하나, 없으면 새 태그와 영어 사진 설명 한 줄. 이름·업종만 보낸다."""
    from app import llm
    system = ("You map a Korean shop menu/service item name to a photo tag. Reply JSON only: "
              '{"tag": "<lowercase-words-with-hyphens>", "prompt": "<one English line describing an appetizing '
              'photo of the item alone, no people, no text>"}. Reuse an existing tag ONLY if it is the same item '
              "(e.g. 'iced americano' -> coffee-americano). If it is a different item, even a similar one "
              "(salt bread is not a scone), make a new specific tag like category-item.")
    user = json.dumps({"item": name, "industry": industry, "existing_tags": known[:200]}, ensure_ascii=False)
    try:
        raw = llm.chat_json(system, user, timeout_sec=15.0, max_tokens=200)
        data = json.loads(raw) if isinstance(raw, str) else raw
    except Exception:
        log.warning("태그 정하기(LLM) 실패")
        return None
    tag = str((data or {}).get("tag") or "").strip().lower()
    prompt = str((data or {}).get("prompt") or "").strip()[:300]
    if not TAG_RE.match(tag) or len(tag) > 40:
        return None
    return tag, prompt


def tag_for(name: str, industry: str, *, use_llm: bool = True) -> Optional[str]:
    """이름 → 태그. 순서: 전에 정한 것(aliases) → 낱말표 → LLM(use_llm일 때). 못 정하면 None(기록하지 않음)."""
    norm = normalize(name)
    if len(norm) < 2:
        return None
    known = _load()
    tag = known["aliases"].get(norm) or _from_table(norm)
    prompt = ""
    if tag is None and use_llm:
        got = _ask_llm(str(name)[:40], industry, sorted(set(_table()) | set(known["tags"])))
        if got:
            tag, prompt = got
    if tag is None:
        return None

    def save(data):
        data["aliases"][norm] = tag
        if tag not in _table() and tag not in data["tags"]:
            data["tags"][tag] = {"words": [str(name)[:40]], "industry": industry,
                                 "prompt": prompt or f"{tag.replace('-', ' ')} on a table", "made": "", "src": ""}
    if known["aliases"].get(norm) != tag:
        _update(save)
    return tag


def _prompt_of(tag: str) -> str:
    row = _table().get(tag) or _load()["tags"].get(tag) or {}
    return str(row.get("prompt") or f"{tag.replace('-', ' ')} on a table")


def url(tag: Optional[str]) -> Optional[str]:
    if not tag or not TAG_RE.match(tag) or len(tag) > 40:
        return None
    return f"/art-lib/{tag}.webp" if (_dir() / f"{tag}.webp").is_file() else None


def ensure(tag: str, industry: str = "") -> bool:
    """창고에 사진이 없으면 만든다. 있으면 True, 만들었으면 True, 못 만들면 False(예외 없음)."""
    if not tag or not TAG_RE.match(tag) or len(tag) > 40:
        return False
    if url(tag):
        return True
    cap = int(getattr(settings, "art_lib_daily_cap", 0) or 0)
    if cap and sum(1 for t in _load()["tags"].values() if t.get("made") == _today()) >= cap:
        log.info("태그 사진 하루 상한(%s)에 걸림", cap)
        return False
    with _index_lock:
        if tag in _making:
            return False
        _making.add(tag)
    try:
        from PIL import Image

        from app.services import ai_images, photos
        raw = ai_images._generate_bytes(f"{_prompt_of(tag)}. {_RULES}", slot="gallery-1")
        clean, _w, _h = photos._clean_ai_image(raw)
        img = Image.open(io.BytesIO(clean)).convert("RGB")
        img.thumbnail((1024, 1024))
        _dir().mkdir(parents=True, exist_ok=True)
        tmp = _dir() / f"{tag}.webp.tmp"
        img.save(tmp, "WEBP", quality=80, method=6)
        tmp.replace(_dir() / f"{tag}.webp")

        def save(data):
            row = data["tags"].setdefault(tag, {"words": [], "prompt": _prompt_of(tag)})
            row.update({"industry": row.get("industry") or industry, "made": _today(), "src": "gemini"})
        _update(save)
        return True
    except Exception:
        log.exception("태그 사진 만들기 실패 tag=%s", tag)
        return False
    finally:
        with _index_lock:
            _making.discard(tag)


def _has_own_photo(card: dict, name: str) -> bool:
    """사장님 사진이나 이 방의 AI 그림이 있으면 창고가 필요 없다."""
    try:
        from app.services import card_data
        hit = card_data.item_photo(card, name)
        if isinstance(hit, dict) and str(hit.get("url") or "").startswith("/uploads/"):
            return True
    except Exception:
        pass
    ai = (card.get("ai_images") or {}).get("item:" + name)
    return isinstance(ai, dict) and str(ai.get("url") or "").startswith("/uploads/")


def _has_site_photos(card: dict) -> bool:
    try:
        from app.services import photos as PH
        return bool(PH.site_photos(card))
    except Exception:
        return False


def prefetch(card: dict, room_id: str = "", requirement_id: str = "") -> None:
    """항목마다 태그를 정하고 창고에 없는 사진을 뒤에서 만든다. 하나라도 새로 생기면 시안·공개본을 다시 그린다."""
    if not isinstance(card, dict):
        return
    try:
        from app.services import keystore
        if not (keystore.get("gemini_api_key") or "").strip():
            return  # 사진을 만들 수 없으면 태그 정하기(LLM)도 하지 않는다
    except Exception:
        return
    try:
        from app.services import photo_needs, prd_engine
        names = [i["name"] for i in photo_needs.items(card) if i.get("name")]
        industry = prd_engine.industry_of(card).key
    except Exception:
        return
    names = [n for n in names if not _has_own_photo(card, n)]
    # 장면 사진: 기본 그림이 없는 종류이고 사장님 사진이 아직 없을 때만
    want_scenes = industry in SCENE_KINDS and not _has_site_photos(card) and len(_scene_key(card)) >= 2
    if not names and not want_scenes:
        return

    def run():
        made = False
        with _workers:
            for tag in (scene_tags(card) if want_scenes else []):
                if not url(tag) and ensure(tag, "scene"):
                    made = True
            for name in names:
                tag = tag_for(name, industry)
                if tag and not url(tag) and ensure(tag, industry):
                    made = True
        if made and room_id and requirement_id:
            from app.services import photos
            photos._refresh_designs_async(room_id, requirement_id,
                                          "예시 사진을 넣었어요(예시 표시가 붙어요). 사진을 올리면 그 사진이 먼저예요.")

    threading.Thread(target=run, daemon=True, name="art-lib-prefetch").start()


# ---- 장면 사진 (첫 화면·사진첩): 처음 보는 종류(청첩장 등)도 그 종류에 맞는 예시 사진을 보인다 ----
# 6업종은 목업·기본 그림이 있다. 그 밖(other·개인·단체·웹서비스)은 기본 그림이 카페 판화라
# 청첩장에 카페 그림이 나왔다(10/2 대표 지적) → 종류 낱말로 장면 5개(첫 장 = 대표)를 정해 만들어 둔다.
SCENE_KINDS = ("other", "individual", "group", "webservice", "event")
SCENE_COUNT = 5


def _scene_key(card: dict) -> str:
    """장면 묶음 이름 = 사장님이 말한 종류 낱말(가게 이름·사실은 쓰지 않는다)."""
    slot = ((card or {}).get("slots") or {}).get("business_type") or {}
    value = slot.get("value") if isinstance(slot, dict) else ""
    if isinstance(value, list):
        value = " ".join(str(v) for v in value)
    return normalize(str(value or ""))[:40]


def _ask_scenes(kind_words: str, known: list) -> list:
    """종류 → 방문자가 기대할 장면 사진 5개 [(tag, prompt)]. 첫 장은 대표(첫 화면)용. 종류 낱말만 보낸다."""
    from app import llm
    # 10/2 실측: '결혼청첩장'을 종이 청첩장으로 읽어 카드·봉투 사진만 골랐다 → 사이트가 다루는 '주제'를 그리게 한다
    system = ("You plan example photos for a small Korean website. site_kind says what the website is for. "
              "Picture the SUBJECT that the site's visitors care about, not the website, paper or card itself "
              "(e.g. a wedding invitation site shows the wedding: rings, bouquet, ceremony venue, aisle, reception table; "
              "a first-birthday party site shows the party table and decorations). "
              f"List {SCENE_COUNT} clearly different scenes, the first one being the hero image. "
              "Each scene must show objects or places only: no people, no faces, no hands, no text, no lettering. "
              'Reply JSON only: {"scenes": [{"tag": "<topic-scene, lowercase words with hyphens>", '
              '"prompt": "<one English line describing the photo>"}]}. '
              "Tags must start with one shared topic word (e.g. wedding-rings, wedding-bouquet). "
              "Reuse an existing tag only if it is exactly the same scene.")
    user = json.dumps({"site_kind": kind_words, "existing_tags": known[:200]}, ensure_ascii=False)
    try:
        raw = llm.chat_json(system, user, timeout_sec=15.0, max_tokens=500)
        data = json.loads(raw) if isinstance(raw, str) else raw
    except Exception:
        log.warning("장면 정하기(LLM) 실패")
        return []
    out = []
    for row in (data or {}).get("scenes") or []:
        if not isinstance(row, dict):
            continue
        tag = str(row.get("tag") or "").strip().lower()
        prompt = str(row.get("prompt") or "").strip()[:300]
        if TAG_RE.match(tag) and len(tag) <= 40 and prompt and tag not in (t for t, _ in out):
            out.append((tag, prompt))
    return out[:SCENE_COUNT]


def scene_tags(card: dict, *, use_llm: bool = True) -> list:
    """이 카드의 장면 태그들(처음 정한 걸 다시 쓴다). 못 정하면 []."""
    key = _scene_key(card)
    if len(key) < 2:
        return []
    known = _load()
    tags = known.get("scenes", {}).get(key)
    if tags or not use_llm:
        return list(tags or [])
    got = _ask_scenes(key, sorted(set(_table()) | set(known["tags"])))
    if not got:
        return []

    def save(data):
        data.setdefault("scenes", {})[key] = [t for t, _ in got]
        for tag, prompt in got:
            if tag not in _table() and tag not in data["tags"]:
                data["tags"][tag] = {"words": [key], "industry": "scene", "prompt": prompt, "made": "", "src": ""}
    _update(save)
    return [t for t, _ in got]


def pick_scenes(card: dict) -> list:
    """그리기용: 만들어 둔 장면 사진 주소들(첫 장 = 대표). LLM·생성은 부르지 않는다."""
    return [u for u in (url(t) for t in scene_tags(card, use_llm=False)) if u]


def pick(card: dict, name: str) -> dict:
    """그리기용: 창고에 사진이 있으면 예시 표시와 함께 돌려준다. LLM·생성은 부르지 않는다."""
    del card
    norm = normalize(name)
    if len(norm) < 2:
        return {}
    tag = _load()["aliases"].get(norm) or _from_table(norm)
    hit = url(tag)
    if not hit:
        return {}
    return {"image": hit, "image_alt": f"{name} 사진 (예시)", "image_example": True}
