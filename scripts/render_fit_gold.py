"""정답 시안(evals/fit_gold/*.json)을 실제 렌더러로 그려 static/compare/fit/에 저장 (DESIGN_FIT_PLAN 0-2).

사용법: .venv/bin/python scripts/render_fit_gold.py
시안(public=False)과 공개본(public=True)을 둘 다 만든다. 로컬 파일로 열리게 /art/ 주소만 상대 경로로 바꾼다.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.services import site_render as SR  # noqa: E402

GOLD = ROOT / "evals" / "fit_gold"
OUT = ROOT / "static" / "compare" / "fit"
KIND = {"cafe": "cafe", "salon": "salon", "academy": "academy", "pension": "pension"}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    names = []
    for path in sorted(GOLD.glob("*.json")):
        spec = json.loads(path.read_text(encoding="utf-8"))
        kind = KIND.get(path.stem.split("-")[0], "other")
        for public in (False, True):
            doc = SR.render_site(spec, site_key="gold", title=spec["navbar"]["title"], kind=kind, public=public)
            doc = doc.replace('"/art/', '"../../../templates/art/')
            (OUT / f"{path.stem}{'-public' if public else ''}.html").write_text(doc, encoding="utf-8")
        names.append(path.stem)
    frames = "".join(
        f'<figure><figcaption>{n} · <a href="{n}.html">시안</a> · <a href="{n}-public.html">공개본</a></figcaption>'
        f'<iframe src="{n}.html" title="{n}"></iframe></figure>' for n in names)
    (OUT / "index.html").write_text(
        '<!doctype html><meta charset="utf-8"><title>정답 시안</title><style>'
        "body{margin:0;padding:24px;font-family:system-ui;background:#eceae6}"
        "main{display:flex;gap:24px;overflow-x:auto}figure{margin:0}figcaption{font-size:14px;margin-bottom:8px}"
        "iframe{width:390px;height:844px;border:0;border-radius:28px;background:#fff;box-shadow:0 10px 40px #0002}"
        f"</style><main>{frames}</main>", encoding="utf-8")
    print("\n".join(str(OUT / f"{n}.html") for n in names))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
