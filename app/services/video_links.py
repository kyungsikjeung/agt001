"""채팅 글에서 영상 주소 추출 (작업 P1).

대상: 유튜브 watch / youtu.be / shorts, 인스타그램 reel / p,
  네이버TV. https만, 추적 값 제거, 최대 3개.
"""
import re
from urllib.parse import parse_qs, urlparse

_URL_RE = re.compile(r"https://[^\s\"'<>`]+")

_YT_HOSTS = ("youtube.com", "www.youtube.com", "m.youtube.com")
_YTU_HOSTS = ("youtu.be", "www.youtu.be")
_IG_HOSTS = ("instagram.com", "www.instagram.com")
_NAVER_HOSTS = ("tv.naver.com",)

_YT_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_IG_CODE_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

_PLATFORM_LABELS = {
    "youtube": "유튜브",
    "instagram": "인스타그램",
    "navertv": "네이버TV",
}

_TAIL_CHARS = ".,;:!?\"'()[]{}"


def _strip_tail(url: str) -> str:
    """문장 끝맺음 기호를 떼어낸다."""
    text = url.strip()
    while text and text[-1] in _TAIL_CHARS:
        text = text[:-1]
    return text


def _thumb_for(video_id: str) -> str:
    return f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"


def parse_video_url(url) -> dict | None:
    """영상 주소 1건을 {platform, platform_label, id, url, thumb}로 바꾼다.

    모르는 주소·https 아님·자바스크립트 주소는 None.
    """
    if not isinstance(url, str):
        return None
    text = _strip_tail(url)
    if not text.lower().startswith("https://"):
        return None
    try:
        parts = urlparse(text)
    except ValueError:
        return None
    if parts.scheme != "https":
        return None
    host = (parts.hostname or "").lower()
    path = parts.path or ""

    if host in _YT_HOSTS:
        segs = [seg for seg in path.split("/") if seg]
        if path == "/watch" or path.startswith("/watch/"):
            query = parse_qs(parts.query or "")
            vid = (query.get("v") or [""])[0]
            if _YT_ID_RE.match(vid):
                return {
                    "platform": "youtube",
                    "platform_label": _PLATFORM_LABELS["youtube"],
                    "id": vid,
                    "url": f"https://www.youtube.com/watch?v={vid}",
                    "thumb": _thumb_for(vid),
                }
            return None
        if len(segs) >= 2 and segs[0] == "shorts" and _YT_ID_RE.match(segs[1]):
            vid = segs[1]
            return {
                "platform": "youtube",
                "platform_label": _PLATFORM_LABELS["youtube"],
                "id": vid,
                "url": f"https://www.youtube.com/shorts/{vid}",
                "thumb": _thumb_for(vid),
            }
        return None

    if host in _YTU_HOSTS:
        segs = [seg for seg in path.split("/") if seg]
        if len(segs) >= 1 and _YT_ID_RE.match(segs[0]):
            vid = segs[0]
            return {
                "platform": "youtube",
                "platform_label": _PLATFORM_LABELS["youtube"],
                "id": vid,
                "url": f"https://youtu.be/{vid}",
                "thumb": _thumb_for(vid),
            }
        return None

    if host in _IG_HOSTS:
        segs = [seg for seg in path.split("/") if seg]
        if len(segs) >= 2 and segs[0] in ("reel", "p") and _IG_CODE_RE.match(segs[1]):
            kind = segs[0]
            code = segs[1]
            return {
                "platform": "instagram",
                "platform_label": _PLATFORM_LABELS["instagram"],
                "id": code,
                "url": f"https://www.instagram.com/{kind}/{code}/",
                "thumb": "",
            }
        return None

    if host in _NAVER_HOSTS:
        if len(path) < 2:
            return None
        clean_path = "/" + "/".join(seg for seg in path.split("/") if seg)
        return {
            "platform": "navertv",
            "platform_label": _PLATFORM_LABELS["navertv"],
            "id": "",
            "url": f"https://tv.naver.com{clean_path}",
            "thumb": "",
        }

    return None


def extract_video_links(text) -> list[str]:
    """채팅 글에서 영상 주소를 찾아 정규화해 돌린다 (최대 3개, 중복 제거)."""
    if not isinstance(text, str) or not text:
        return []
    found: list[str] = []
    seen: set[str] = set()
    for match in _URL_RE.finditer(text):
        info = parse_video_url(match.group(0))
        if info is None:
            continue
        canonical = info["url"]
        if canonical in seen:
            continue
        seen.add(canonical)
        found.append(canonical)
        if len(found) >= 3:
            break
    return found
