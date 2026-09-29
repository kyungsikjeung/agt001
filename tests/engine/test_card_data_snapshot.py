"""card_data.build 스냅샷 (DEPTH_DESIGN_BOOKING_PLAN §8: 프로필 확장 전후 회귀 확인). DB 없이 돌아간다.

의도한 변경이면 UPDATE_SNAPSHOT=1 로 한 번 돌려 파일을 새로 쓰고, 달라진 줄을 검토해 함께 커밋한다.
"""
import json
import os
import sys
from pathlib import Path

from app.services import card_data
from app.services import prd_engine as E
from app.services import prd_schema as S

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from draft_corpus import CASES  # noqa: E402

SNAP = Path(__file__).parent / "snapshots" / "card_data.json"


def _build_all() -> dict:
    out = {}
    for case in CASES:
        card = E.new_card(case["industry"])
        for key, value in case["slots"].items():
            E._put(card, key, value, S.FILLED, 1)
        out[case["id"]] = card_data.build(card)
    return out


def test_card_data_snapshot():
    got = _build_all()
    if os.environ.get("UPDATE_SNAPSHOT") or not SNAP.exists():
        SNAP.write_text(json.dumps(got, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    assert got == json.loads(SNAP.read_text(encoding="utf-8"))
