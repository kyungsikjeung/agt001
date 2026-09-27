"""Gemini 이미지 키 확인 (포토리얼 예시 이미지).

.env의 GEMINI_API_KEY로 ① 연결 테스트(관리자 화면 키 교체와 같은 검사) ② 이미지 생성 가능 모델이
보이는지 본다. 키 값은 출력하지 않는다(뒤 4자리만).

사용법: .venv/bin/python scripts/check_gemini_image.py
"""
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings  # noqa: E402
from app.services import keystore  # noqa: E402


def main() -> int:
    key = (keystore.get("gemini_api_key") or "").strip()
    if not key:
        print("GEMINI_API_KEY가 없어요(.env 또는 관리자 화면).")
        return 1
    print(f"키: ****{key[-4:]} (출처: {'DB' if key != (settings.gemini_api_key or '').strip() else '.env'})")

    ok, msg = keystore.test("gemini_api_key", key)
    print(f"① 연결 테스트: {'통과' if ok else '실패'} ({msg})")
    if not ok:
        return 1

    base = (settings.gemini_api_base or "https://generativelanguage.googleapis.com").rstrip("/")
    try:
        r = httpx.get(f"{base}/v1beta/models", timeout=20, headers={"x-goog-api-key": key})
        r.raise_for_status()
        models = r.json().get("models", [])
    except (httpx.HTTPError, ValueError) as e:
        print(f"② 모델 목록: 실패 ({type(e).__name__})")
        return 1
    names = sorted(m.get("name", "").split("/")[-1] for m in models)
    print(f"② 모델 목록: {len(names)}개")
    configured = (settings.gemini_image_model or "").strip()
    hero_model = (settings.gemini_image_model_hero or "").strip() or configured
    imageish = [n for n in names if "image" in n.lower()]
    print(f"   이미지 관련: {', '.join(imageish) or '-'}")
    print(f"   설정 모델({configured}): {'있음' if configured in names else '없음(목록에 없음)'}")
    print(f"   히어로 모델({hero_model}): {'있음' if hero_model in names else '없음(목록에 없음)'}")
    return 0 if (configured in names and hero_model in names) else 1


if __name__ == "__main__":
    sys.exit(main())
