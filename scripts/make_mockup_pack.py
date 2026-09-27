"""업종별 목업 이미지 팩 생성 (서버에서 실행, 키 필요).

  .venv/bin/python scripts/make_mockup_pack.py [--only cafe] [--force]

동작: 10업종 × 3슬롯 = 30장을 Gemini로 생성해 templates/art/mock-<업종>-<슬롯>.webp로 저장.
저장된 파일은 design_variants가 /art/ 기본 그림보다 먼저 쓴다.
키가 없으면 안내만 하고 종료한다(로컬 목 테스트는 _mock으로).
"""
import argparse
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings  # noqa: E402
from app.services import ai_images as AI  # noqa: E402
from app.services import photos  # noqa: E402
from app.services import site_render as SR  # noqa: E402


def _save_webp(raw_jpeg: bytes, dest: Path) -> None:
    from PIL import Image
    img = Image.open(io.BytesIO(raw_jpeg)).convert("RGB")
    dest.parent.mkdir(parents=True, exist_ok=True)
    img.save(dest, "WEBP", quality=90, method=6)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--mock", action="store_true", help="키 없이 흐름만 검증 (테스트용 회색 판)")
    args = ap.parse_args()
    kinds = [k for k in SR.KIND_KEYS if not args.only or k == args.only]
    if not args.mock:
        from app.services import keystore
        if not (keystore.get("gemini_api_key") or "").strip():
            print("GEMINI_API_KEY가 없어요. 서버에서 실행해 주세요.")
            return 1
    made, skipped = [], []
    for kind in kinds:
        for slot in AI.SLOTS:
            dest = settings.templates_dir / "art" / f"mock-{kind}-{slot}.webp"
            if dest.exists() and not args.force:
                skipped.append(dest.name)
                continue
            prompt = AI.prompt_for(kind, slot)
            if args.mock:
                from PIL import Image
                buf = io.BytesIO()
                Image.new("RGB", (1280, 720) if slot == "hero" else (800, 800), (180, 170, 160)).save(buf, "JPEG")
                raw = buf.getvalue()
            else:
                raw = AI._generate_bytes(prompt, slot=slot)
            clean, _, _ = photos._clean_ai_image(raw)
            _save_webp(clean, dest)
            made.append(dest.name)
    print(f"생성 {len(made)}장, 건너뜀 {len(skipped)}장")
    for n in made:
        print(" +", n)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
