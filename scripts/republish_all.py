"""공개된 가게를 한꺼번에 다시 공개한다 (10/1 배포 뒤 한 번, 대표 피드백 D58).

- 새 공개 모양(카카오 지도·'채팅하기'·공지 사진·앱형 카드 가운데 정렬)을 기존 공개본에 반영한다.
- 공개 때 가게 행(shops)이 안 생기던 버그(10/1 고침)로 빠진 행을 채운다. 행이 없으면 손님 채팅·예약이 열리지 않는다.
- --geo: 주소 칸은 있는데 지도 좌표가 없으면 카카오로 확인해 좌표를 채운다(카드 저장, 실패하면 그대로 둠).

기본은 미리 보기(아무것도 바꾸지 않음). 가게 이름·전화·주소는 출력하지 않는다(site_key만).
사용법: python scripts/republish_all.py [--apply] [--geo] [--only <site_key>]
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _published() -> list[tuple[str, dict]]:
    """(site_key, 카드) — 공개 기록과 공개 파일이 둘 다 있는 가게만."""
    from sqlalchemy import select

    from app.config import settings
    from app.db.models import SessionRow
    from app.db.session import get_sessionmaker

    with get_sessionmaker()() as db:
        rows = db.execute(select(SessionRow.requirement_id, SessionRow.prd)).all()
    out = []
    for key, card in rows:
        if not key or not isinstance(card, dict) or not card.get("published"):
            continue
        if not (settings.generated_dir / key / "published" / "index.html").is_file():
            continue
        out.append((key, card))
    return sorted(out, key=lambda r: r[0])


def _has_shop(key: str) -> bool:
    from app.db.models import ShopRow
    from app.db.session import get_sessionmaker
    with get_sessionmaker()() as db:
        return db.get(ShopRow, key) is not None


def _needs_geo(card: dict) -> bool:
    from app.services import geo
    loc = geo._loc_text(card)
    return bool(loc) and loc != geo._resolved_for(card)


def main(argv: list[str]) -> int:
    from app import store
    from app.services import booking_engine, design, geo, shops
    from app.services.publish_check import PublishBlockedError

    apply, with_geo = "--apply" in argv, "--geo" in argv
    only = argv[argv.index("--only") + 1] if "--only" in argv and argv.index("--only") + 1 < len(argv) else None
    targets = [(k, c) for k, c in _published() if only is None or k == only]
    if not apply:
        no_shop = no_geo = 0
        for key, card in targets:
            flags = []
            if not _has_shop(key):
                flags.append("가게 행 없음")
                no_shop += 1
            if _needs_geo(card):
                flags.append("좌표 없음")
                no_geo += 1
            print(key + (f"  ({', '.join(flags)})" if flags else ""))
        print(f"미리 보기: 공개 가게 {len(targets)}곳, 가게 행 없음 {no_shop}곳, 좌표 없음 {no_geo}곳. "
              "바꾸려면 --apply (좌표까지 채우려면 --apply --geo)")
        return 0
    ok = fail = shop_added = geo_set = 0
    for key, card in targets:
        try:
            room_id = booking_engine._room_for(key)
            if with_geo and room_id and _needs_geo(card):
                with store.room_tx(room_id) as (_room, session):
                    live = session.get("prd") or {}
                    if geo.fill_if_sure(live):  # 결과가 딱 하나일 때만. 주소 칸은 절대 바꾸지 않는다
                        geo_set += 1
                    card = live
            if not _has_shop(key):
                shops.ensure(key, shops._shop_name({"prd": card}) or None, room_id)
                shop_added += 1
            design.publish_choice(key, card, card["published"])  # 가게 행 뒤에 그려야 채팅 단추가 붙는다
            ok += 1
            print(f"{key}: 다시 공개")
        except PublishBlockedError as e:
            fail += 1
            print(f"{key}: 공개 검사에 걸림 ({'; '.join(e.reasons)})")
        except Exception as e:  # 한 곳이 실패해도 나머지는 계속한다
            fail += 1
            print(f"{key}: 실패 ({type(e).__name__})")
    print(f"다시 공개 {ok}곳, 실패 {fail}곳, 가게 행 채움 {shop_added}곳, 좌표 채움 {geo_set}곳")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
