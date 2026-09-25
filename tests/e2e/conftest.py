"""E2E 공용 픽스처 (tests/e2e 전용).

실제 서버 + 실제 브라우저가 필요하므로 E2E_BASE_URL이 없으면
테스트 모듈 전체가 skip된다 (test_room_e2e.py의 pytestmark 참조).
"""
import os

import pytest
from playwright.sync_api import sync_playwright

BASE_URL = os.environ.get("E2E_BASE_URL", "").rstrip("/")


@pytest.fixture(scope="session")
def base_url():
    if not BASE_URL:
        pytest.skip("E2E_BASE_URL 미설정 - 실제 서버가 필요하므로 skip")
    return BASE_URL


@pytest.fixture(scope="session")
def browser():
    if not BASE_URL:
        pytest.skip("E2E_BASE_URL 미설정 - 실제 서버가 필요하므로 skip")
    with sync_playwright() as p:
        bw = p.chromium.launch()
        yield bw
        bw.close()
