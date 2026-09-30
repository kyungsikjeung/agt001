"""B6 P3: 실제 Gemini로 사진 고치기 확인 (PHOTO_EDIT_CONTRACT §6 P3).

6업종 첫 화면 공용 예시 사진을 한 장씩 AI로 고치고(가게 전용 후보), 금지 말 거절·가게 정보 미전송·
공용 파일 불변·사장님 사진 보정을 확인한다. 결과: generated/p3/<업종>-{before,after}.jpg, 대조표 PNG,
docs/product/evals/photo-edit-check-<KST 날짜>.md. 비용: 출력 1장 $0.039(ai.google.dev/gemini-api/docs/pricing,
2026-09-30 확인), 입력은 무시할 수준.

실행: .venv/bin/python evals/run_photo_edit_check.py [--only cafe] [--dry]
  --dry: Gemini를 부르지 않고 준비·대상 찾기·금지 말·보정만 확인
"""
import argparse
import copy
import datetime
import hashlib
import io
import json
import logging
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

PRICE_PER_IMAGE = 0.039
KST = datetime.timezone(datetime.timedelta(hours=9))

# 업종별 고칠 말 (사장님이 할 법한 짧은 말). 가게 정보 없음.
REQUESTS = {
    "cafe": "창가에 햇살이 더 들어오게",
    "restaurant": "조명을 더 따뜻하게",
    "salon": "더 밝고 깨끗한 느낌으로",
    "academy": "창밖을 초록 나무로",
    "workshop": "작업대를 더 밝게",
    "pension": "해 질 녘 노을 느낌으로",
}
# 가게 정보: 카드에 넣고, Gemini 요청 본문에 절대 없어야 한다.
SHOP = {"shop_name": "모퉁이확인상회", "phone": "010-4321-8765", "location": "서울 마포구 확인로 77"}
FORBIDDEN = ["사람 넣어 줘", "간판에 가게 이름 써 줘", "로고 넣어", "얼굴 보이게"]
NUMERIC = "010-1234-5678 적어 주고 밝게"


def _card(ind: str) -> dict:
    from app.services import prd_engine as E
    from app.services import prd_schema as S
    card = E.new_card(ind)
    for k, v in SHOP.items():
        E._put(card, k, v, S.FILLED, 1)
    card["turn"] = 1
    return card


def _hero_src(html: str) -> str:
    import re
    m = re.search(r'data-section-id="hero".*?<img[^>]*src="([^"]+)"', html, re.S)
    return m.group(1) if m else ""


def _art_hashes() -> dict:
    base = ROOT / "templates" / "art"
    return {str(p.relative_to(base)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(base.rglob("*")) if p.is_file()}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only")
    ap.add_argument("--dry", action="store_true")
    args = ap.parse_args(argv)
    logging.disable(logging.WARNING)

    from app.config import settings
    from app.services import ai_images, photo_edit, site_render
    from app.services import design_variants as DV

    out = ROOT / "generated" / "p3"
    out.mkdir(parents=True, exist_ok=True)
    settings.generated_dir = out / "gen"
    before_art = _art_hashes()

    # Gemini 요청 본문을 가로채 가게 정보가 없는지 본다 (실제 호출은 그대로 통과).
    bodies: list[str] = []
    real_post = ai_images.httpx.post

    def spy(url, **kw):
        bodies.append(json.dumps(kw.get("json") or {}, ensure_ascii=False))
        if args.dry:
            raise AssertionError("--dry에서는 Gemini를 부르지 않는다")
        return real_post(url, **kw)
    ai_images.httpx.post = spy

    rows, calls = [], 0
    for ind, request in REQUESTS.items():
        if args.only and ind != args.only:
            continue
        card = _card(ind)
        spec = DV.variants(card)[0]["spec"]
        html = site_render.render_site(spec, site_key=f"p3{ind}", title="x", kind=ind)
        src = _hero_src(html)
        session = {"prd": card, "requirement_id": f"p3{ind}"}
        row = {"업종": ind, "요청": request, "대상": "", "결과": "", "초": "", "메모": ""}
        try:
            target = photo_edit.resolve_target(card, spec, "hero", src, 0)
            row["대상"] = f"{target['target']}·{target['kind']}"
            if args.dry:
                row["결과"] = "건너뜀(--dry)"
            else:
                t0 = time.monotonic()
                cand = photo_edit.make_candidate(f"p3{ind}", session, target, instruction=request)
                calls += 1
                row["초"] = f"{time.monotonic() - t0:.1f}"
                after = Path(settings.generated_dir) / cand["after_url"].lstrip("/")
                before = ROOT / "templates" / src.lstrip("/")
                for name, p in (("before", before), ("after", after)):
                    if p.is_file():
                        (out / f"{ind}-{name}.jpg").write_bytes(p.read_bytes())
                row["결과"] = "후보 생성" if after.is_file() else f"후보 파일 없음({cand['after_url']})"
                row["메모"] = "카드 그대로" if (card.get("ai_images") or {}).get(target["target"], {}).get("url") in (None, target["current_url"]) else "카드가 바뀜(X)"
        except Exception as e:  # 확인 스크립트: 한 업종이 실패해도 표에 남기고 계속
            row["결과"] = f"실패: {type(e).__name__}: {str(e)[:80]}"
        rows.append(row)

    leaked = [v for v in SHOP.values() if any(v in b or v.replace("-", "") in b for b in bodies)]
    forbidden = []
    for text in FORBIDDEN:
        try:
            photo_edit.clean_instruction(text)
            forbidden.append((text, "통과(X)"))
        except ValueError as e:
            forbidden.append((text, f"거절: {e}"))
    numeric = photo_edit.clean_instruction(NUMERIC)
    # 사장님 사진 보정: 가짜 사진 한 장으로 5가지 (API 없음)
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (800, 600), (120, 110, 100)).save(buf, "JPEG")
    adjusted = {a: Image.open(io.BytesIO(photo_edit.adjust(buf.getvalue(), a))).size for a in photo_edit.actions_for("owner")}
    art_same = _art_hashes() == before_art

    _sheet(out, [r["업종"] for r in rows if r["결과"] == "후보 생성"])
    date = datetime.datetime.now(KST).strftime("%Y-%m-%d")
    lines = [f"# 사진 고치기 실제 확인 (B6 P3, {date})", "",
             f"Gemini 호출 {calls}번, 추정 비용 ${calls * PRICE_PER_IMAGE:.3f} (출력 1장 ${PRICE_PER_IMAGE}).", "",
             "| 업종 | 요청 | 대상 | 결과 | 초 | 메모 |", "|---|---|---|---|---|---|"]
    lines += [f"| {r['업종']} | {r['요청']} | {r['대상']} | {r['결과']} | {r['초']} | {r['메모']} |" for r in rows]
    lines += ["", "## 안전 확인", "",
              f"- 가게 정보(이름·전화·주소)가 Gemini 요청 본문에: {'없음' if not leaked else '있음(X) ' + ', '.join(leaked)}",
              f"- 공용 예시 파일(templates/art) 변화: {'없음' if art_same else '있음(X)'}",
              f"- 숫자 모양 제거: '{NUMERIC}' → '{numeric}'"]
    lines += [f"- 금지 말 '{t}': {r}" for t, r in forbidden]
    lines += [f"- 사장님 사진 보정 {a}: {w}×{h}" for a, (w, h) in adjusted.items()]
    lines += ["", "## 눈으로 볼 것 (Claude)", "",
              "- 같은 장소로 보이나(내용이 엉뚱하게 바뀌지 않았나)", "- 사람·얼굴·글자·간판·로고가 새로 생기지 않았나",
              "- 요청한 느낌이 반영됐나", f"- 대조표: generated/p3/sheet.png"]
    report = ROOT / "docs" / "product" / "evals" / f"photo-edit-check-{date}.md"
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    bad = leaked or not art_same or any("통과(X)" in r for _, r in forbidden)
    return 1 if bad else 0


def _sheet(out: Path, inds: list[str]) -> None:
    """전·후 대조표 한 장 (업종마다 한 줄)."""
    from PIL import Image
    if not inds:
        return
    w, h = 480, 300
    sheet = Image.new("RGB", (w * 2 + 30, (h + 20) * len(inds) + 10), (255, 255, 255))
    for i, ind in enumerate(inds):
        for j, name in enumerate(("before", "after")):
            p = out / f"{ind}-{name}.jpg"
            if p.is_file():
                img = Image.open(p).convert("RGB")
                img.thumbnail((w, h))
                sheet.paste(img, (10 + j * (w + 10), 10 + i * (h + 20)))
    sheet.save(out / "sheet.png")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
