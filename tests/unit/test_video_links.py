"""영상 주소 추출 단위 테스트 (작업 P1). DB를 쓰지 않는다."""
from app.services.video_links import extract_video_links, parse_video_url


def test_유튜브_watch():
    info = parse_video_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    assert info["platform"] == "youtube"
    assert info["id"] == "dQw4w9WgXcQ"
    assert info["thumb"] == "https://i.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg"
    assert info["url"] == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


def test_유튜브_watch_추적값제거():
    info = parse_video_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=10s&si=abc")
    assert info["url"] == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


def test_유튜브_단축():
    info = parse_video_url("https://youtu.be/dQw4w9WgXcQ?t=30")
    assert info["platform"] == "youtube"
    assert info["thumb"] == "https://i.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg"
    assert info["url"] == "https://youtu.be/dQw4w9WgXcQ"


def test_유튜브_쇼츠():
    info = parse_video_url("https://www.youtube.com/shorts/dQw4w9WgXcQ?feature=share")
    assert info["platform"] == "youtube"
    assert info["url"] == "https://www.youtube.com/shorts/dQw4w9WgXcQ"
    assert "i.ytimg.com" in info["thumb"]


def test_인스타_릴스():
    info = parse_video_url("https://www.instagram.com/reel/C8abc123XYZ/?igsh=abc")
    assert info["platform"] == "instagram"
    assert info["url"] == "https://www.instagram.com/reel/C8abc123XYZ/"
    assert info["thumb"] == ""


def test_인스타_게시물():
    info = parse_video_url("https://www.instagram.com/p/C8abc123XYZ/")
    assert info["platform"] == "instagram"
    assert info["thumb"] == ""


def test_네이버TV():
    info = parse_video_url("https://tv.naver.com/v/12345?query=1")
    assert info["platform"] == "navertv"
    assert info["url"] == "https://tv.naver.com/v/12345"
    assert info["thumb"] == ""


def test_이상한주소_거부():
    assert parse_video_url("javascript:alert(1)") is None
    assert parse_video_url("http://www.youtube.com/watch?v=dQw4w9WgXcQ") is None
    assert parse_video_url("https://example.com/video/1") is None
    assert parse_video_url("https://www.youtube.com/watch?v=") is None
    assert parse_video_url("") is None
    assert parse_video_url(None) is None


def test_채팅글_추출_최대3개_중복제거():
    text = (
        "이거 봐 https://www.youtube.com/watch?v=AAA111AAA11&t=1 "
        "https://youtu.be/BBB222BBB22 "
        "https://www.instagram.com/reel/CCC333CCC33/ "
        "https://tv.naver.com/v/999 "
        "https://www.youtube.com/watch?v=AAA111AAA11"
    )
    links = extract_video_links(text)
    assert len(links) == 3
    assert links[0] == "https://www.youtube.com/watch?v=AAA111AAA11"
    assert links[1] == "https://youtu.be/BBB222BBB22"
    assert links[2] == "https://www.instagram.com/reel/CCC333CCC33/"


def test_채팅글_영상없음():
    assert extract_video_links("안녕하세요 가격 문의요") == []
    assert extract_video_links("") == []
    assert extract_video_links(None) == []
