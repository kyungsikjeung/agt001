"""메뉴 태그 사진 창고 미리 채우기 (ART_LIB_CONTRACT §4 A4, PREBETA_RUNBOOK §2).

낱말표(app/data/art_tags.json)의 태그 중 창고에 없는 것만 하나씩 만든다(Gemini, 장당 약 $0.039).
기본은 미리 보기(아무것도 만들지 않음). 키 값·가게 정보는 출력하지 않는다.
사용법: python scripts/prefill_art_lib.py [--apply] [--industry cafe] [--limit N]
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

COST = 0.039


def _arg(argv: list[str], name: str):
    return argv[argv.index(name) + 1] if name in argv and argv.index(name) + 1 < len(argv) else None


def main(argv: list[str]) -> int:
    from app.services import art_lib

    industry = _arg(argv, "--industry")
    limit = _arg(argv, "--limit")
    table = art_lib._table()
    tags = [t for t, row in table.items() if industry is None or industry in (row.get("industry") or [])]
    if limit is not None:
        tags = tags[:max(0, int(limit))]
    have = [t for t in tags if art_lib.url(t)]
    missing = [t for t in tags if not art_lib.url(t)]
    if "--apply" not in argv:
        for t in missing:
            print(t)
        print(f"미리 보기: 태그 {len(tags)}개, 이미 있음 {len(have)}개, 없음 {len(missing)}개, "
              f"예상 비용 ${len(missing) * COST:.2f}. 만들려면 --apply")
        return 0
    made = failed = 0
    for t in missing:
        first = ((table.get(t) or {}).get("industry") or [""])[0]
        if art_lib.ensure(t, first):
            made += 1
            print(f"만듦 {t}")
        else:
            failed += 1
            print(f"실패 {t}")
    print(f"만듦 {made}, 실패 {failed}, 추정 비용 ${made * COST:.2f}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
