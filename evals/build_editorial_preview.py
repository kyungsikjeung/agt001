"""편집형(에디토리얼) 4방향 미리보기 생성 (Claude 시범, 2026-09-27).

가짜 가게 정보(실존 상호 금지)로 4방향 페이지를 site_render.render_site(public=True)로
만들어 static/compare/editorial-A.html ~ editorial-D.html로 저장한다.
A=카페, B=코딩 학원, C=펜션(실사 예시라 "예시 이미지" 표시), D=음악 연습실.

실행: .venv/bin/python evals/build_editorial_preview.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.site_render import render_site  # noqa: E402

OUT_DIR = ROOT / "static" / "compare"
FAKE_PHONE = "010-1234-5678"


def _tokens(palette: str, font_pair: str) -> dict:
    return {
        "palette": palette,
        "font_pair": font_pair,
        "density": "comfortable",
        "radius": "soft",
        "image_style": "card",
    }


def spec_a() -> tuple:
    """A 빈티지 일러스트형: 카페."""
    spec = {
        "version": 3,
        "tokens": _tokens("coffee", "serif-warm"),
        "locked": [],
        "sections": [
            {
                "id": "hero", "type": "hero", "variant": "illustrated",
                "content": {
                    "title": "예시카페 오후쉼표",
                    "lines": [
                        "천천히 내리는 커피 한 잔,",
                        "창밖 햇살이 머무는 자리,",
                        "오늘 오후는 잠시 쉬어가세요.",
                    ],
                    "image": "/art/cafe-engraving.webp",
                    "image_alt": "판화풍 카페 그림",
                    "cta": {"label": "메뉴 보기", "href": "#menu"},
                },
            },
            {
                "id": "menu", "type": "offerings", "variant": "cards",
                "content": {
                    "label": "대표 메뉴",
                    "items": [
                        {"name": "수제 크림 라떼", "desc": "고소한 크림을 올린 대표 커피",
                         "price": "6,000원", "image": "/uploads/example-menu-1.jpg",
                         "image_alt": "수제 크림 라떼 사진"},
                        {"name": "밤 식빵 세트", "desc": "든든한 오후 간식",
                         "price": "7,500원", "image": "/uploads/example-menu-2.jpg",
                         "image_alt": "밤 식빵 세트 사진"},
                        {"name": "유자 수제차", "desc": "따뜻하게 즐기는 수제 차",
                         "price": "5,500원", "image": "/uploads/example-menu-3.jpg",
                         "image_alt": "유자 수제차 사진"},
                    ],
                },
            },
            {
                "id": "contact", "type": "contact", "variant": "call-first",
                "content": {"phone": FAKE_PHONE, "hours": "매일 10:00-21:00",
                            "address": "가상시 미리보기로 1"},
            },
        ],
    }
    return spec, "예시카페 오후쉼표"


def spec_b() -> tuple:
    """B 산뜻한 스토리형: 코딩 학원."""
    spec = {
        "version": 3,
        "tokens": _tokens("navy", "sans-clean"),
        "locked": [],
        "sections": [
            {
                "id": "hero", "type": "hero", "variant": "story",
                "content": {
                    "title": "처음 코딩, 두렵지 않게",
                    "highlight": "두렵지 않게",
                    "subtitle": "예시 두드림코딩은 소수 정원으로 차근차근 함께합니다.",
                    "image": "/art/academy-glass.webp",
                    "image_alt": "유리 추상 그림",
                    "cta": {"label": "상담 신청", "href": "#contact"},
                    "facts": [{"label": "정원", "value": "반별 8명"}],
                },
            },
            {
                "id": "worry", "type": "concerns", "variant": "bubbles",
                "content": {
                    "heading": "학부모님, 이런 고민 있으세요?",
                    "items": [
                        {"quote": "컴퓨터를 처음 접하는데 따라갈 수 있을까요?",
                         "who": "초등 4학년 학부모"},
                        {"quote": "학원만 다니면 실력이 늘지 않을까 걱정돼요.",
                         "who": "중등 1학년 학부모"},
                        {"quote": "수업 시간 외에 질문할 곳이 있나요?",
                         "who": "예비 수강생 학부모"},
                    ],
                    "note": "상담 시간에 하나씩 답해 드립니다.",
                },
            },
            {
                "id": "contact", "type": "contact", "variant": "call-first",
                "content": {"phone": FAKE_PHONE, "hours": "평일 13:00-20:00",
                            "address": "가상시 미리보기로 2"},
            },
        ],
    }
    return spec, "예시 두드림코딩"


def spec_c() -> tuple:
    """C 로맨틱 에디토리얼: 펜션 (실사처럼 보이는 예시라 반드시 예시 표시)."""
    spec = {
        "version": 3,
        "tokens": _tokens("forest", "serif-elegant"),
        "locked": [],
        "sections": [
            {
                "id": "hero", "type": "hero", "variant": "arch",
                "content": {
                    "eyebrow": "숲속 작은 쉼터",
                    "title": "예시 바람결펜션",
                    "subtitle": "창밖으로 바람이 쉬어 가는 방 두 칸.",
                    "image": "/art/pension-example.webp",
                    "image_alt": "펜션 외관 예시 사진",
                    "ai_example": True,
                    "label_en": "REST IN THE WIND",
                    "cta": {"label": "객실 보기", "href": "#rooms"},
                },
            },
            {
                "id": "rooms", "type": "offerings", "variant": "cards",
                "content": {
                    "label": "객실 안내",
                    "items": [
                        {"name": "바람방", "desc": "햇살이 드는 2인 객실",
                         "price": "1박 120,000원~"},
                        {"name": "숲방", "desc": "조용한 4인 가족 객실",
                         "price": "1박 170,000원~"},
                    ],
                },
            },
            {
                "id": "contact", "type": "contact", "variant": "call-first",
                "content": {"phone": FAKE_PHONE, "hours": "입실 15:00 · 퇴실 11:00",
                            "address": "가상시 미리보기로 3"},
            },
        ],
    }
    return spec, "예시 바람결펜션"


def spec_d() -> tuple:
    """D 다크 시네마틱: 음악 연습실 (예시 이미지 표시)."""
    spec = {
        "version": 3,
        "tokens": _tokens("charcoal-gold", "serif-elegant"),
        "locked": [],
        "sections": [
            {
                "id": "hero", "type": "hero", "variant": "cinematic",
                "content": {
                    "kicker": "밤에도 불이 꺼지지 않는 곳",
                    "title": "예시 밤낮연습실",
                    "subtitle": "방음실 6개, 새벽 2시까지 운영하는 연습 공간.",
                    "image": "/art/pension-example.webp",
                    "image_alt": "연습실 내부 예시 사진",
                    "ai_example": True,
                    "cta": {"label": "예약하기", "href": "https://booking.example.com/nightday"},
                    "cta2": {"label": "전화 상담", "href": "tel:01012345678"},
                },
            },
            {
                "id": "contact", "type": "contact", "variant": "call-first",
                "content": {"phone": FAKE_PHONE, "hours": "매일 10:00-02:00",
                            "address": "가상시 미리보기로 4"},
            },
            {
                "id": "quick", "type": "quickbar", "variant": "float",
                "content": {
                    "phone": FAKE_PHONE,
                    "channel_url": "https://pf.example.com/nightday",
                    "booking_url": "https://booking.example.com/nightday",
                },
            },
        ],
    }
    return spec, "예시 밤낮연습실"


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    jobs = (("A", spec_a), ("B", spec_b), ("C", spec_c), ("D", spec_d))
    for letter, maker in jobs:
        spec, title = maker()
        html_text = render_site(spec, title=title, public=True)
        out = OUT_DIR / f"editorial-{letter}.html"
        out.write_text(html_text, encoding="utf-8")
        print(f"{letter}: {out} ({len(html_text)}자)")


if __name__ == "__main__":
    main()
