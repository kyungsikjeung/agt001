"""P3-5 모델 비교 하네스 (D39).

같은 설명문 6종(docs/product/evals/design-compare/briefs.md 고정, 읽기만 함) ×
후보(규칙 기준선 + 규칙 변형, AI 후보는 미측정) × 품질(D37 6요소 점수 재사용) ·
속도(초) · 가격(호출원가 또는 0원)을 재서 비교표 md로 출력한다.

외부 API를 부르지 않는다 (AI 호출 없음, 비용 0원). AI 후보 3종
(Muse Spark 1.3 유료 · Gemini 계열 · Claude Sonnet 5)은 --ai 로만 시도하며,
기본 실행에서는 호출하지 않고 미해결로 기록한다.

사용법: .venv/bin/python -m evals.run_design_compare [--report PATH]
"""
import argparse
import copy
import datetime
import re
import tempfile
import time
from pathlib import Path

from app.config import settings
from app.services import design
from app.services import design_concept as DC
from evals.run_site_quality import (
    INDUSTRIES,
    VIEW_H,
    VIEW_W,
    _six,
    card_action_facts,
    evaluate_actions,
    make_card,
    measure,
)

ROOT = Path(__file__).resolve().parent
BRIEFS = ROOT.parent / "docs" / "product" / "evals" / "design-compare" / "briefs.md"
DEFAULT_REPORT = ROOT.parent / "docs" / "product" / "evals" / "design-compare" / "비교결과.md"

# 후보: (id, 라벨, 시안 변형, 설명). 규칙 경로만이라 외부 호출·비용 없음.
CANDIDATES = (
    ("rule", "규칙 기준선", "v1", "업종 규칙 컨셉(_RULE) + v1 기본형"),
    ("rule-alt", "규칙 변형", "v2", "업종 규칙 컨셉(_RULE) + v2 사진 강조형"),
)

# D39 운영 상한 (비교표에 함께 기록).
MONTHLY_CAP_USD = 30


def brief_industries() -> list[str]:
    """briefs.md 읽기 전용 확인: ##見出し 6종이 run_site_quality 6업종과 일치하는지."""
    heads = re.findall(r"^## (\w+)", BRIEFS.read_text(encoding="utf-8"), re.M)
    ordered = [h for h in heads if h in INDUSTRIES]
    if sorted(ordered) != sorted(INDUSTRIES):
        raise SystemExit(f"briefs.md 6종 불일치(원문 수정 금지, 확인만): {heads}")
    return ordered  # briefs.md 순서 그대로 (restaurant 먼저)


def build(out_dir: Path) -> tuple[list[dict], float]:
    """설명문 6종 × 후보 2종 = 12쪽을 운영 코드로 만든다. (초, 쪽 목록)을 돌려준다."""
    pages = []
    gen = Path(tempfile.mkdtemp(prefix="dcmp-"))
    old = settings.generated_dir
    settings.generated_dir = gen
    t0 = time.perf_counter()
    try:
        for ind in brief_industries():
            card, _ = make_card(ind, "full")
            card["concept"] = DC.rule_concept(card)  # 규칙 기준선: AI 호출 없음
            for cid, _label, vid, _desc in CANDIDATES:
                rid = f"dc-{ind}-{cid}"
                design.publish_choice(rid, copy.deepcopy(card), vid)
                html = (gen / rid / "published" / "index.html").read_text(encoding="utf-8")
                path = out_dir / f"{ind}-{cid}.html"
                path.write_text(html, encoding="utf-8")
                pages.append({"industry": ind, "candidate": cid, "variant": vid,
                              "html": path, "expect": {"name": "x"},
                              "action_facts": card_action_facts(card)})
    finally:
        settings.generated_dir = old
    return pages, time.perf_counter() - t0


def six_marks(m: dict) -> tuple[str, int]:
    """6요소 O/X 문자열과 통과 수(hero_visual 제외 5개 중). m이 없으면 ('미측정', -1)."""
    if not m:
        return "미측정", -1
    s = _six(m)
    marks = (f"제목{'O' if s['title'] else 'X'}·여백{'O' if s['spacing'] else 'X'}·"
             f"색{'O' if s['color'] else 'X'}·버튼{'O' if s['cta'] else 'X'}·"
             f"행동{'O' if s['actions'] else 'X'}")
    return marks, sum(s.values())


def report(pages: list[dict], build_sec: float, measure_sec: float, measured: bool) -> str:
    n = len(pages)
    avg_sec = (build_sec + measure_sec) / n if n else 0
    today = datetime.date.today().isoformat()
    main_rows, six_rows = [], []
    for pg in pages:
        m = pg.get("m") or {}
        label = next(lb for cid, lb, _v, _d in CANDIDATES if cid == pg["candidate"])
        six_rows.append(
            f"| {pg['industry']} | {label} | "
            f"{(m.get('title_ratio', 0)) if m else '-'} "
            f"{'O' if m and _six(m)['title'] else ('-' if not m else 'X')} | "
            f"{m.get('spacing_steps', '-') if m else '-'} "
            f"{'O' if m and _six(m)['spacing'] else ('-' if not m else 'X')} | "
            f"{m.get('hero_visual', '-') if m else '-'} | "
            f"{m.get('color_count', '-') if m else '-'} "
            f"{'O' if m and _six(m)['color'] else ('-' if not m else 'X')} | "
            f"{'O' if m and _six(m)['cta'] else ('-' if not m else 'X')} | "
            f"{m.get('first_screen_actions', '-') if m else '-'} "
            f"{'O' if m and _six(m)['actions'] else ('-' if not m else 'X')} |")
    # 위 분기에서 행 문자열이 어긋나지 않게 main_rows를 다시 만든다.
    main_rows = []
    for pg in pages:
        m = pg.get("m") or {}
        marks, passed = six_marks(m)
        act = pg.get("actions") or {}
        qual = f"{marks} ({passed}/5)" if passed >= 0 else "미측정"
        label = next(lb for cid, lb, _v, _d in CANDIDATES if cid == pg["candidate"])
        main_rows.append(f"| {pg['industry']} | {label} | {qual} | "
                         f"{avg_sec:.1f} | 0원 | {'O' if act.get('ok') else 'X'} |")
    text = (
        f"# 디자인 비교 1차 — 규칙 기준선 vs 규칙 변형 ({today})\n\n"
        f"목적: D39 모델 비교 하네스. 같은 설명문 6종(briefs.md 원문 고정, 읽기만 함)을 "
        f"후보 2종에 돌려 품질·속도·가격 표로 기록한다. "
        f"실행: `.venv/bin/python -m evals.run_design_compare`\n\n"
        f"## 조건\n\n"
        f"- 설명문: [briefs.md](briefs.md) 6종(restaurant·cafe·pension·salon·academy·workshop), "
        f"품질 점검 full 입력과 같은 가게 사실\n"
        f"- 후보: 규칙 기준선(업종 규칙 컨셉 `_RULE` + v1 기본형), "
        f"규칙 변형(같은 컨셉 + v2 사진 강조형)\n"
        f"- 외부 API 호출 없음(AI 호출 없음), 비용 0원. "
        f"D39 운영 상한 월 ${MONTHLY_CAP_USD}, 닿으면 규칙 컨셉(`_RULE`)으로 자동 전환\n"
        + ("" if measured else
           "> 브라우저 측정 건너뜀(브라우저 도구 없음). 6요소는 미측정, 누를 것 점검만 기록.\n\n")
        + "## 품질·속도·가격 표\n\n"
        "| 설명문(업종) | 후보 | 품질(6요소) | 속도(초/쪽, 평균) | 가격 | 누를 것 |\n"
        "|---|---|---|---|---|---|\n"
        + "\n".join(main_rows) + "\n\n"
        "## 6요소 점수 (D37 매일 회귀, run_site_quality 재사용)\n\n"
        "### 요약 (항목별 통과 쪽 수)\n\n| 항목 | 기준 | 통과 |\n|---|---|---|\n"
    )
    if measured:
        for key, lb, rule in (("title", "제목 대비(title_ratio)", "h1/본문 2.0 이상"),
                              ("spacing", "여백 리듬(spacing_steps)", "section 상·하 padding 종류 3개 이하"),
                              ("color", "색(color_count)", "유채색 3개 이하"),
                              ("cta", "카드·버튼(cta_shape)", "첫 화면 첫 버튼 높이 48px 이상·둥근 모서리"),
                              ("actions", "첫 화면 한 가지 행동(first_screen_actions)", "행동 버튼 1~2개")):
            hit = sum(1 for pg in pages if pg.get("m") and _six(pg["m"])[key])
            text += f"| {lb} | {rule} | {hit}/{n} |\n"
        text += ("| 사진(hero_visual) | 첫 화면 그림 넓이 비율(참고값, 판정 없음) | - |\n"
                 "\n### 쪽별\n\n"
                 "| 쪽(업종) | 후보 | 제목비율 | 여백종류 | 첫화면그림 | 색수 | 버튼모양 | 첫화면행동 |\n"
                 "|---|---|---|---|---|---|---|---|\n"
                 + "\n".join(six_rows) + "\n")
    else:
        text += "> 브라우저 측정 건너뜀으로 6요소 미측정.\n"
    text += (
        "\n## AI 후보 3종 (D39, 미해결)\n\n"
        "| 후보 | 상태 | 비고 |\n|---|---|---|\n"
        "| Muse Spark 1.3 유료 | 미측정 | Zen 키 경유 비교 예정, 이번 실행은 외부 호출 없이 기준선만 기록 |\n"
        "| Gemini 계열 | 미측정 |同上 |\n"
        "| Claude Sonnet 5 | 미측정 |同上 |\n"
        "\n미해결: D39 유료 후보 3종 비교는 별도 승인·예산 확인 뒤 `--ai` 실행으로 진행한다.\n"
    )
    return text


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None, help="HTML 저장 폴더 (기본: 임시 폴더)")
    ap.add_argument("--report", default=str(DEFAULT_REPORT), help="비교표 저장 경로")
    ap.add_argument("--ai", action="store_true",
                    help="(준비 안 됨) AI 후보 비교. 지금은 거부하고 기준선만 기록한다")
    a = ap.parse_args()
    if a.ai:
        raise SystemExit("AI 후보 비교(--ai)는 미구현: D39 3종 비교 승인·예산 확인 뒤에 진행 (미해결 유지)")
    out_dir = Path(a.out or tempfile.mkdtemp(prefix="dcmp-out-"))
    out_dir.mkdir(parents=True, exist_ok=True)
    pages, build_sec = build(out_dir)
    evaluate_actions(pages)  # 브라우저 없이 HTML 직접 읽기라 항상 됨
    try:
        t0 = time.perf_counter()
        measure(pages, out_dir)
        measure_sec = time.perf_counter() - t0
        measured = True
    except Exception as e:  # 브라우저 도구가 없으면 누를 것 점검만 보고한다
        print(f"브라우저 측정 건너뜀(도구 없음): {e}")
        measure_sec = 0.0
        measured = False
    text = report(pages, build_sec, measure_sec, measured)
    Path(a.report).write_text(text, encoding="utf-8")
    print(text)
    print(f"비교표: {a.report} ({len(pages)}행: 6종 × 2후보)")
    print(f"휴대폰 {VIEW_W}×{VIEW_H}, 그림·HTML: {out_dir}")


if __name__ == "__main__":
    main()
