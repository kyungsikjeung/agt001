"""랜딩 템플릿 카드·첫 화면 데모용 예시 사진을 Gemini로 만든다 (D51: 사람·얼굴·간판 글자·로고 없음, 화면에 '예시 이미지' 표시).

이미 있는 파일은 건너뛴다. 다시 만들려면 해당 .webp를 지우고 돌린다. 키 값은 출력하지 않는다.
사용법: .venv/bin/python scripts/gen_landing_examples.py
"""
import io
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.ai_images import ImageError, _generate_bytes  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "frontend" / "src" / "landing" / "img"
RULES = ("photorealistic photograph, shot on 35mm, f/2.8, natural light, editorial composition. "
         "No people, no faces, no hands, no text, no letters, no signage, no logos, no watermark.")
SHOTS = {
    # 템플릿 카드 (frontend/src/templates.ts)
    "pension": "a small seaside guesthouse with a lawn garden and wooden deck at golden hour, calm sea behind",
    "cafe": "a cozy corner neighborhood cafe counter with a latte with latte art and a small pastry, warm window light",
    "restaurant": "a Korean home-style set meal on a wooden table: rice, stew in an earthenware pot, "
                  "several small side dishes in ceramic bowls, 45-degree angle",
    "salon": "a bright minimalist hair salon interior with a styling chair, round mirror and green plants, soft daylight",
    "workshop": "a pottery studio with a potter's wheel holding a freshly thrown clay bowl, "
                "wooden shelves of glazed ceramics behind, warm light",
    "academy": "a cheerful small English classroom for children with low bookshelves of colorful picture books "
               "and small wooden tables, bright daylight",
    # 첫 화면 데모 (frontend/src/landing/HeroDemo.tsx)
    "demo-bunsik": "Korean street-food snack plates on a stainless table: tteokbokki in red sauce, sliced gimbap, "
                   "fried dumplings, bright and appetizing",
    "demo-pilates": "a calm pilates studio with reformer machines on a light wooden floor, large windows, soft morning light",
}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    failed = 0
    for name, subject in SHOTS.items():
        path = OUT / f"{name}.webp"
        if path.exists():
            print(f"건너뜀 {path.name}")
            continue
        try:
            raw = _generate_bytes(f"{subject}. {RULES}", slot="hero")
        except ImageError as e:
            print(f"실패 {name}: {e}")
            failed += 1
            continue
        img = Image.open(io.BytesIO(raw)).convert("RGB")
        img.thumbnail((960, 960))
        buf = io.BytesIO()
        img.save(buf, "WEBP", quality=78, method=6)
        path.write_bytes(buf.getvalue())
        print(f"저장 {path.name} {img.size[0]}x{img.size[1]} {len(buf.getvalue()) // 1024}KB")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
