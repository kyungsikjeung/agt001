"""업종별 공간 예시 4장(입구·내부·자리·분위기)을 Gemini로 만든다 (ART_LIB_CONTRACT §3, D51: 사람·얼굴·글자·간판·로고 없음).

이미 있는 파일은 건너뛴다. 다시 만들려면 해당 .webp를 지우고 돌린다. 키 값은 출력하지 않는다.
사용법: .venv/bin/python scripts/gen_space_examples.py
"""
import io
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.ai_images import ImageError, _generate_bytes  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "templates" / "art" / "ex"
RULES = ("photorealistic photograph, shot on 35mm, f/2.8, natural light, editorial composition, square 1:1. "
         "No people, no faces, no hands, no text, no letters, no signage, no logos, no watermark.")
SHOTS = {
    "cafe": ["the entrance of a small neighborhood cafe with a wooden door and potted plants, blank facade",
             "a wide view of a cozy cafe interior with wooden tables, pendant lights and a counter",
             "a window seat in a cafe with two chairs, a small table and a latte, soft daylight",
             "close-up of a cafe counter with an espresso machine, cups and pastries, warm mood"],
    "restaurant": ["the entrance of a small Korean restaurant with a plain wooden sliding door, stone steps and potted plants, no curtain, no marks",
                   "a wide view of a cozy Korean restaurant dining hall with wooden tables and warm lighting",
                   "a set table for two in a Korean restaurant with spoons, chopsticks, rice bowls and side dishes, no bottles, no labels",
                   "close-up of an open kitchen pass with steaming earthenware pots, warm atmosphere"],
    "salon": ["the glass entrance of a bright minimalist hair salon with plants, blank facade",
              "a wide view of a modern hair salon interior with styling chairs and round mirrors",
              "a single styling station with a chair, mirror, brushes and scissors neatly arranged",
              "close-up of a salon shampoo area with towels and bottles without labels, calm mood"],
    "pension": ["the entrance path of a countryside guesthouse with a wooden gate and garden lights at dusk",
                "a wide view of a guesthouse lounge with a sofa, fireplace and large windows",
                "a wooden deck with outdoor chairs and a barbecue grill overlooking a garden",
                "close-up of a guest room window view of mountains in the morning mist"],
    "academy": ["the entrance of a small study academy with a glass door and a shoe rack, blank walls",
                "a wide view of a bright classroom with small desks, chairs and a whiteboard without writing",
                "a single study desk with open workbooks, pencils and a desk lamp",
                "close-up of a reading corner with low bookshelves of colorful books and cushions"],
    "workshop": ["the entrance of a small craft workshop with a wooden door and potted plants, blank facade",
                 "a wide view of a pottery workshop with a large wooden table and shelves of ceramics",
                 "one work seat at a pottery wheel with tools and a lump of clay",
                 "close-up of glazed ceramic cups drying on a wooden shelf, warm light"],
}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    made = failed = 0
    for industry, shots in SHOTS.items():
        for n, subject in enumerate(shots, start=1):
            path = OUT / f"{industry}-space{n}.webp"
            if path.exists():
                print(f"건너뜀 {path.name}")
                continue
            try:
                raw = _generate_bytes(f"{subject}. {RULES}", slot="gallery-1")
            except ImageError as e:
                failed += 1
                print(f"실패 {path.name}: {e}")
                continue
            img = Image.open(io.BytesIO(raw)).convert("RGB")
            img.thumbnail((1024, 1024))
            img.save(path, "WEBP", quality=80, method=6)
            made += 1
            print(f"만듦 {path.name} {img.width}x{img.height}")
    print(f"끝: 만듦 {made}, 실패 {failed}, 추정 비용 ${made * 0.039:.2f}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
