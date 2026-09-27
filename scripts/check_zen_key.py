"""Zen 키 확인 (BACKLOG P3-1, DECISIONS.md D39).

.env의 ZEN_API_KEY로 ① 연결 테스트(관리자 화면 키 교체와 같은 검사) ② 비교 후보 3개가 Zen 모델 목록에
있는지 본다. 키 값은 출력하지 않는다(뒤 4자리만).

사용법: .venv/bin/python scripts/check_zen_key.py
"""
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings  # noqa: E402
from app.services import keystore  # noqa: E402

# D39 비교 후보. Muse Spark는 학습에 쓰는 Contributor 판을 빼고 유료판만.
CANDIDATES = {
    "Claude Sonnet 5": lambda m: "sonnet-5" in m,
    "Gemini 3.1 Pro": lambda m: "gemini-3.1-pro" in m,
    "Muse Spark 1.3 (유료)": lambda m: "muse-spark" in m and "contributor" not in m and "free" not in m,
}


def main() -> int:
    key = (settings.zen_api_key or "").strip()
    if not key:
        print("ZEN_API_KEY가 .env에 없어요.")
        return 1
    print(f"키: ****{key[-4:]}")

    ok, msg = keystore.test("zen_api_key", key)
    print(f"① 연결 테스트: {'통과' if ok else '실패'} ({msg})")

    try:
        r = httpx.get("https://opencode.ai/zen/v1/models", timeout=20, headers={"Authorization": f"Bearer {key}"})
        r.raise_for_status()
        ids = [m.get("id", "") for m in r.json().get("data", [])]
    except (httpx.HTTPError, ValueError) as e:
        print(f"② 모델 목록: 실패 ({type(e).__name__})")
        return 1
    print(f"② 모델 목록: {len(ids)}개")
    missing = 0
    for name, match in CANDIDATES.items():
        hits = [m for m in ids if match(m.lower())]
        missing += not hits
        print(f"   {'있음' if hits else '없음'}  {name}: {', '.join(hits) or '-'}")
    return 0 if ok and not missing else 1


if __name__ == "__main__":
    sys.exit(main())
