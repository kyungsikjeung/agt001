"""S-5 게시 전 검사 + S-2 미리보기 sandbox iframe 자동 검사 (DESIGN §13.5).

우리 렌더러 결과물은 검사를 항상 통과한다 (외부 스크립트·외부 폼 없음,
문의 폼은 상대 주소, 자동 이동 없음, 비밀값 없음).
"""
import re

import pytest

from app.services import design
from app.services import design_variants as DV
from app.services import site_render
from app.services.publish_check import PublishBlockedError, check_html


def _card():
    from app.services import prd_engine as E
    from app.services import prd_schema as S

    card = E.new_card()
    E._put(card, "business_type", "카페", S.FILLED, 1)
    card["industry"] = "cafe"
    E._put(card, "shop_name", "작은숲", S.FILLED, 1)
    E._put(card, "offerings", ["아메리카노", "라떼"], S.FILLED, 1)
    E._put(card, "contact_method", "전화", S.FILLED, 1)
    E._put(card, "phone", "010-0000-1234", S.FILLED, 1)
    card["turn"] = 1
    return card


# ── S-5: 위반 4종 ────────────────────────────────────────────────────

def test_external_script_blocked():
    assert check_html('<script src="https://evil.example/x.js"></script>')


def test_external_form_blocked():
    assert check_html('<form action="https://evil.example/collect"> 암튼')


def test_auto_redirect_blocked():
    assert check_html('<meta http-equiv="refresh" content="0;url=https://evil.example">')
    assert check_html("<script>location='https://evil.example'</script>")


def test_secret_blocked():
    assert check_html("key = 'sk-abcdefgh12345678'")
    assert check_html("api_key = \"AKIAIOSFODNN7EXAMPLE\"")


def test_sandbox_bypass_blocked():
    """S-6: CSP sandbox 우회. sandbox 없는 내부 화면·격리를 푸는 토큰은 차단."""
    assert check_html('<iframe src="https://evil.example/"></iframe>')
    assert check_html('<iframe src="https://evil.example/" sandbox="allow-scripts allow-same-origin"></iframe>')
    assert check_html('<iframe src="https://evil.example/" sandbox="allow-top-navigation"></iframe>')
    # 빈 sandbox(우리 시안 고르기 페이지 방식)는 통과
    assert check_html('<iframe src="/design/abc/v1/" sandbox=""></iframe>') == []


def test_clean_renderer_output_passes():
    """우리 렌더러 공개본 3안은 검사를 통과해야 한다 (자기 차단을 막는다)."""
    card = _card()
    for v in DV.variants(card):
        page = site_render.render_site(v["spec"], site_key="t", title="t", kind="cafe", public=True)
        assert check_html(page) == [], v["id"]


def test_relative_inquiry_form_passes():
    assert check_html('<form action="/api/inquiries/abc123">') == []


# ── S-5: publish_choice 차단 ─────────────────────────────────────────

def test_publish_blocked_writes_nothing(client, monkeypatch, tmp_path):
    monkeypatch.setattr(site_render, "render_site", lambda *a, **kw: '<script src="https://evil.example/x.js">')
    with pytest.raises(PublishBlockedError):
        design.publish_choice("req-blocked", _card(), "v1")
    from app.config import settings
    assert not (settings.generated_dir / "req-blocked" / "published" / "index.html").is_file()


def test_publish_clean_writes_file(client):
    design.publish_choice("req-clean", _card(), "v1")
    from app.config import settings
    assert (settings.generated_dir / "req-clean" / "published" / "index.html").is_file()


# ── S-2: 미리보기 iframe은 sandbox, 금지 토큰 없음 ────────────────────

_FORBIDDEN = ("allow-same-origin", "allow-forms", "allow-top-navigation")


def test_concept_board_iframes_sandboxed(client):
    design.render_variants("req-sb", _card())
    r = client.get("/design/req-sb")
    assert r.status_code == 200
    frames = re.findall(r"<iframe[^>]*>", r.text)
    assert frames, "시안 고르기 페이지에 미리보기 iframe이 있어야 한다"
    for f in frames:
        m = re.search(r'\bsandbox(?:="([^"]*)")?', f)
        assert m is not None, f"sandbox 없는 iframe: {f[:80]}"
        tokens = m.group(1) or ""
        assert not any(t in tokens for t in _FORBIDDEN), f"금지 토큰: {f[:120]}"


def test_served_pages_keep_sandbox_headers(client):
    """S-5: 서빙 계층(public.py) CSP sandbox 유지·우회 토큰 없음 + S-6 통과본만 deploy로."""
    from app.services import deploy
    from app.services.publish_check import check_html as _check

    card = _card()
    design.render_variants("req-hdr", card)
    design.publish_choice("req-hdr", card, "v1")
    from app.config import settings
    page = (settings.generated_dir / "req-hdr" / "published" / "index.html").read_text(encoding="utf-8")
    assert _check(page) == []
    assert deploy.site_url("req-hdr", "http://testserver") is not None
    for path in ("/design/req-hdr", "/design/req-hdr/v1/", "/site/req-hdr/"):
        r = client.get(path)
        assert r.status_code == 200, path
        csp = r.headers.get("content-security-policy", "")
        assert "sandbox" in csp, f"CSP sandbox 없음: {path}"
        assert "allow-same-origin" not in csp, f"sandbox 우회 토큰: {path}"
        assert "allow-top-navigation" not in csp, f"sandbox 우회 토큰: {path}"
