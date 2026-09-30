"""주문·스탬프를 켠 가게의 공개본을 다시 공개한다 (WAVE5_CONTRACT §2.3).

비상 스위치를 바꾼 뒤 한 번 실행한다. DB 행은 바꾸지 않고 공개 파일만 다시 쓴다.
가게 이름·전화는 절대 출력하지 않는다 (site_key만).
"""
import sys


def _targets() -> list[str]:
    """공개본이 있는 세션 중 주문 켜짐 또는 스탬프 규칙 켜짐인 site_key 목록."""
    from sqlalchemy import select

    from app.config import settings
    from app.db.models import SessionRow
    from app.db.session import get_sessionmaker
    from app.services import shop_settings, stamps

    with get_sessionmaker()() as db:
        rows = db.scalars(select(SessionRow)).all()
        cards = [(r.requirement_id, r.prd) for r in rows]
    out = []
    for site_key, card in cards:
        if not isinstance(card, dict) or not card.get("published"):
            continue
        try:
            order_on = bool(shop_settings.get(site_key).get("order_on"))
        except Exception:
            order_on = False
        try:
            stamp_on = stamps.rule(site_key) is not None
        except Exception:
            stamp_on = False
        if not (order_on or stamp_on):
            continue
        if not (settings.generated_dir / site_key / "published" / "index.html").is_file():
            continue
        out.append(site_key)
    return out


def _card_for(site_key: str) -> dict | None:
    from sqlalchemy import select

    from app.db.models import SessionRow
    from app.db.session import get_sessionmaker

    with get_sessionmaker()() as db:
        card = db.scalar(select(SessionRow.prd).where(SessionRow.requirement_id == site_key))
    return card if isinstance(card, dict) else None


def main(argv: list[str]) -> int:
    """--dry-run이면 대상 site_key만 출력. 아니면 다시 공개하고 마지막 줄에 합계."""
    from app.services import design

    targets = _targets()
    if "--dry-run" in argv:
        for key in targets:
            print(key)
        return 0
    ok, fail = 0, 0
    for key in targets:
        try:
            card = _card_for(key)
            if card is None or not card.get("published"):
                raise ValueError("공개본 정보가 없어요.")
            design.publish_choice(key, card, card["published"])
            ok += 1
        except Exception as e:
            fail += 1
            print(f"{key}: {e}")
    print(f"다시 공개 {ok}곳, 실패 {fail}곳")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
