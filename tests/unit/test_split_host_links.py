"""운영처럼 앱 주소와 미리보기 주소를 나눈 설정에서, 공개 사이트의 상대 링크는 미리보기 주소가 여는 경로뿐이어야 한다.

10/1 운영 버그: "채팅하기"가 상대 링크 /chat/<키>라 공개 사이트(미리보기 주소)에서 404였다.
로컬 개발은 주소를 나누지 않아 이런 버그가 테스트에서 안 보이므로 여기서 나눠 본다.
"""
import json
import re
from pathlib import Path

import pytest

from app import main
from app.config import settings
from app.services import site_render

SAMPLES = Path(__file__).resolve().parents[2] / "templates" / "samples"
ATTR = re.compile(r'(?:href|action|src|poster)="(/[^"]*)"')
SCRIPT_URL = re.compile(r"""(?:fetch\(|location(?:\.href)?\s*=\s*|\.open\()\s*['"](/[^'"]+)""")
CONTACTS = ("call-first", "booking-first", "chat-first", "form", "kakao-channel")


@pytest.fixture
def split(monkeypatch):
    from app.services import guest_chat
    monkeypatch.setattr(settings, "preview_host", "pv.test")
    monkeypatch.setattr(settings, "public_base_url", "https://app.test")
    monkeypatch.setattr(guest_chat, "enabled", lambda key: True)  # 손님 채팅 링크가 꼭 나오게


def _app_only(html: str) -> list:
    """미리보기 주소에서 404가 날 상대 주소들."""
    found = ATTR.findall(html) + SCRIPT_URL.findall(html)
    return sorted({u for u in found if not u.startswith(main._PREVIEW_PATHS)})


@pytest.mark.parametrize("name", sorted(p.stem for p in SAMPLES.glob("*.json")))
def test_samples_have_no_app_only_relative_links(split, name):
    spec = json.loads((SAMPLES / f"{name}.json").read_text(encoding="utf-8"))
    html = site_render.render_site(spec, site_key="k1", public=True, title="가게")
    assert _app_only(html) == []


@pytest.mark.parametrize("variant", CONTACTS)
def test_contact_chat_button_goes_to_app_host(split, variant):
    content = {"phone": "02-1234-5678", "booking_url": "https://booking.example.com/a",
               "channel_url": "https://pf.kakao.com/_x", "kakao_channel_url": "https://pf.kakao.com/_x"}
    spec = json.loads((SAMPLES / "cafe.json").read_text(encoding="utf-8"))
    spec["sections"] = [{"id": "contact", "type": "contact", "variant": variant, "content": content}]
    html = site_render.render_site(spec, site_key="k1", public=True, title="가게")
    assert 'href="https://app.test/chat/k1"' in html
    assert _app_only(html) == []
