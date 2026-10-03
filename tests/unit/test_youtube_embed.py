"""유튜브 배경 영상 예외 정책 (YOUTUBE_EMBED_POLICY): 정해진 틀 하나만, 그 페이지에만 유튜브 전용 헤더."""
from app.config import settings
from app.services import publish_check
from app.services import site_render
from app.services import youtube_embed as Y

YT = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


def _page(video_url, public=True):
    spec = {"version": 3,
            "tokens": {"palette": "coffee", "font_pair": "serif-warm", "density": "comfortable",
                       "radius": "soft", "image_style": "card"},
            "sections": [{"id": "hero", "type": "hero", "variant": "video",
                          "content": {"title": "바다카페", "subtitle": "카페", "image": "/art/x.webp",
                                      "video_url": video_url}}]}
    return site_render.render_site(spec, title="바다카페", kind="cafe", public=public)


def test_youtube_hero_renders_muted_loop_background_and_sound_link():
    html = _page(YT)
    assert Y.IFRAME_RE.search(html)
    assert "mute=1" in html and "loop=1" in html and "playlist=dQw4w9WgXcQ" in html and "controls=0" in html
    assert "youtube-nocookie.com" in html and "s-hero__sound" in html and "i.ytimg.com" in html  # 썸네일이 아래에 깔림
    assert publish_check.check_html(html) == [] and Y.page_uses_youtube(html)


def test_drafts_and_previews_show_thumbnail_without_player():
    html = _page(YT, public=False)  # 시안·실시간 미리보기는 격리돼 재생이 안 되므로 틀을 넣지 않는다
    assert "<iframe" not in html and "i.ytimg.com" in html and "s-hero__sound" in html


def test_non_youtube_video_keeps_cover_without_iframe():
    html = _page("https://www.instagram.com/reel/AbCdEf12345/")
    assert "<iframe" not in html and not Y.page_uses_youtube(html)
    html = _page("")
    assert "<iframe" not in html and "s-hero__play is-empty" in html


def test_any_change_to_the_embed_is_blocked():
    html = _page(YT)
    for old, new in (("controls=0", "controls=1"),
                     ("allow-presentation", "allow-presentation allow-top-navigation"),
                     ("www.youtube-nocookie.com", "www.youtube.com"),
                     ("playlist=dQw4w9WgXcQ", "playlist=AAAAAAAAAAA"),
                     (' sandbox="allow-scripts allow-same-origin allow-presentation"', "")):
        bad = html.replace(old, new)
        assert not Y.page_uses_youtube(bad), old
    assert publish_check.check_html(html.replace("allow-presentation", "allow-presentation allow-top-navigation"))
    assert publish_check.check_html(html.replace(' sandbox="allow-scripts allow-same-origin allow-presentation"', ""))


def test_youtube_csp_only_allows_youtube_frames():
    csp = Y.SITE_CSP_YOUTUBE
    assert csp.startswith("sandbox allow-scripts allow-same-origin")
    assert "frame-src https://www.youtube-nocookie.com;" in csp and "object-src 'none'" in csp
    assert "allow-top-navigation" not in csp


def test_site_serving_switches_headers_only_for_youtube_pages(client, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "generated_dir", tmp_path)
    (tmp_path / "ytsite" / "published").mkdir(parents=True)
    (tmp_path / "ytsite" / "published" / "index.html").write_text(_page(YT), encoding="utf-8")
    (tmp_path / "plain" / "published").mkdir(parents=True)
    (tmp_path / "plain" / "published" / "index.html").write_text(_page(""), encoding="utf-8")
    yt = client.get("/site/ytsite/")
    plain = client.get("/site/plain/")
    assert yt.status_code == 200 and yt.headers["content-security-policy"] == Y.SITE_CSP_YOUTUBE
    assert "allow-same-origin" not in plain.headers["content-security-policy"]
    # 정해진 틀을 고친 파일은 예외 헤더를 받지 못한다
    (tmp_path / "ytsite" / "published" / "index.html").write_text(
        _page(YT).replace("controls=0", "controls=1"), encoding="utf-8")
    assert "allow-same-origin" not in client.get("/site/ytsite/").headers["content-security-policy"]
