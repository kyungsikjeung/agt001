"""유튜브 배경 영상 예외 정책 (YOUTUBE_EMBED_POLICY, 2026-10-03 대표 결정).

공개 사이트는 원래 외부 화면 틀(iframe)을 막고, 모든 페이지를 "출처 없는 문서"로 격리한다(sandbox).
유튜브 플레이어는 이 격리 안에서는 재생되지 않으므로, 아래 조건을 **모두** 만족할 때만 유튜브 하나를 예외로 둔다.

1. 렌더러가 첫 화면(hero--video)에 그린 틀 하나만: 주소 www.youtube-nocookie.com/embed/<11자 ID>,
   고정된 재생 값(소리 끔·반복·조작 없음), 틀 자체에도 sandbox(allow-scripts allow-same-origin allow-presentation),
   referrerpolicy·allow 고정. 한 글자라도 다르면 게시 전 검사(publish_check)가 막는다.
2. 그 틀이 있는 페이지에만 유튜브 전용 보안 헤더(SITE_CSP_YOUTUBE)를 쓴다.
   - 페이지 격리에 allow-same-origin이 더해진다(유튜브 플레이어가 동작하려면 필요). 대신
   - frame-src를 youtube-nocookie 하나로 묶어 다른 외부 틀은 브라우저가 막고, object·base 주소도 막는다.
   - 외부 스크립트는 게시 전 검사가 계속 막는다(지도 SDK 한 주소만 예외, 기존 그대로).
3. 그 밖의 페이지는 기존 헤더 그대로.

남는 위험(문서화): 예외 페이지는 미리보기 주소의 브라우저 저장소에 닿을 수 있다. 공개 사이트에는 우리 렌더러 스크립트만
들어가고(게시 전 검사), 미리보기 주소의 쿠키는 httponly라 스크립트가 읽지 못한다.
"""
import re

HOST = "https://www.youtube-nocookie.com"
_ID = r"[A-Za-z0-9_-]{11}"
ID_RE = re.compile(rf"^{_ID}$")

# 템플릿(templates/sections/hero--video.mustache)과 글자 하나까지 같아야 한다.
_PARAMS = ("autoplay=1&amp;mute=1&amp;loop=1&amp;playlist={id}&amp;controls=0&amp;playsinline=1"
           "&amp;rel=0&amp;modestbranding=1&amp;iv_load_policy=3&amp;disablekb=1")
IFRAME_RE = re.compile(
    r'<iframe class="s-hero__yt" src="https://www\.youtube-nocookie\.com/embed/(' + _ID + r')\?'
    + re.escape(_PARAMS).replace(re.escape("{id}"), r"\1")
    + r'" title="배경 영상" allow="autoplay; encrypted-media; picture-in-picture"'
    r' sandbox="allow-scripts allow-same-origin allow-presentation"'
    r' referrerpolicy="strict-origin-when-cross-origin" tabindex="-1" aria-hidden="true" data-yt-bg></iframe>')

SITE_CSP_YOUTUBE = ("sandbox allow-scripts allow-same-origin allow-forms allow-popups allow-popups-to-escape-sandbox; "
                    f"frame-src {HOST}; child-src {HOST}; object-src 'none'; base-uri 'none'")


def video_id(info) -> str:
    """parse_video_url 결과에서 배경으로 틀 수 있는 유튜브 ID. 아니면 빈 값."""
    if not isinstance(info, dict) or info.get("platform") != "youtube":
        return ""
    vid = str(info.get("id") or "")
    return vid if ID_RE.match(vid) else ""


def strip_allowed(html_text: str) -> str:
    """정해진 모양의 유튜브 배경 틀만 지운 HTML (게시 전 검사가 나머지 틀을 그대로 보게)."""
    return IFRAME_RE.sub("", html_text or "")


def page_uses_youtube(html_text: str) -> bool:
    """유튜브 전용 헤더를 써도 되는 페이지인가: 정해진 틀이 있고, 게시 전 검사를 통과한다."""
    if "data-yt-bg" not in (html_text or "") or not IFRAME_RE.search(html_text):
        return False
    from app.services import publish_check
    return publish_check.check_html(html_text) == []
