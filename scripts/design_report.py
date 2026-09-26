"""디자인 학습 기록 요약 (DECISIONS.md D44·D45).

사용법: .venv/bin/python scripts/design_report.py [--days 90]
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services import design_log  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--days", type=int, default=90)
    print(json.dumps(design_log.report(ap.parse_args().days), ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
