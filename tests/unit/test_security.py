from app.security import sanitize_spec, sanitize_token


def test_sanitize_token_removes_traversal():
    out = sanitize_token("../../etc/passwd")
    assert ".." not in out
    assert "/" not in out
    assert out == "etcpasswd"


def test_sanitize_token_allows_only_safe_chars():
    out = sanitize_token("abc-XYZ_019; rm -rf /x")
    assert out == "abc-XYZ_019rm-rfx"


def test_sanitize_token_truncates_to_64():
    out = sanitize_token("a" * 100)
    assert len(out) == 64


def test_sanitize_token_empty_and_none():
    assert sanitize_token("") == ""
    assert sanitize_token(None) == ""


def test_sanitize_spec_removes_control_chars():
    out = sanitize_spec("a\x00b\x01c\x07d\x1f e")
    assert out == "abcd e"


def test_sanitize_spec_keeps_newline_and_strips():
    out = sanitize_spec("  hello\nworld  ")
    assert out == "hello\nworld"


def test_sanitize_spec_truncates_to_800():
    out = sanitize_spec("x" * 1000)
    assert len(out) == 800


def test_sanitize_spec_empty():
    assert sanitize_spec("") == ""
    assert sanitize_spec(None) == ""
