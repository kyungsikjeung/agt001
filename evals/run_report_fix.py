"""P3-7 보고 고치기 하네스 (D42-3).

스크린샷 → 지적(사람 입력) → 명세 수정 → 전후 점수 비교 1회분을 돌린다.
명세 패치는 design_concept.adjust()의 규칙 경로(_keyword_adjust)만 직접 쓴다
(AI 호출 없음, 비용 0원). 전후 점수는 run_site_quality 6요소(_six) 그대로.

사용법: .venv/bin/python -m evals.run_report_fix --industry cafe \
           --note "차분한 느낌으로 바꿔줘"
지적은 --note (또는 --note-file)로 사람이 넣는다. 스크린샷은 out 폴더의
<업종>-before/-after-fold.png 두 장이다.
"""
import argparse
import copy
import datetime
import tempfile
import time
from pathlib import Path

from app.config import settings
from app.services import design
from app.services.design_concept import _keyword_adjust, rule_concept
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

SIX_LABELS = (("title", "제목 대비"), ("spacing", "여백 리듬"), ("color", "색"),
              ("cta", "카드·버튼"), ("actions", "첫 화면 행동"))


def six_line(m: dict) -> str:
    if not m:
        return "미측정"
    s = _six(m)
    return "·".join(f"{lb}{'O' if s[k] else 'X'}" for k, lb in SIX_LABELS) + f" ({sum(s.values())}/5)"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--industry", default="cafe", choices=list(INDUSTRIES))
    ap.add_argument("--note", default="차분한 느낌으로 바꿔줘",
                    help="사람 지적 문장 (스크린샷을 보고 사람이 입력)")
    ap.add_argument("--note-file", default=None, help="지적 문장 파일 (--note 대신)")
    ap.add_argument("--out", default=None, help="HTML·스크린샷 저장 폴더 (기본: 임시 폴더)")
    a = ap.parse_args()
    note = Path(a.note_file).read_text(encoding="utf-8").strip() if a.note_file else a.note.strip()
    if not note:
        raise SystemExit("지적 문장이 비어 있음 (--note 또는 --note-file로 사람이 입력)")

    out_dir = Path(a.out or tempfile.mkdtemp(prefix="rfix-out-"))
    out_dir.mkdir(parents=True, exist_ok=True)
    gen = Path(tempfile.mkdtemp(prefix="rfix-"))
    old = settings.generated_dir
    settings.generated_dir = gen
    t0 = time.perf_counter()
    try:
        card, _ = make_card(a.industry, "full")
        before_concept = rule_concept(card)  # 규칙 기준선 (AI 호출 없음)
        after_concept, reply = _keyword_adjust(before_concept, note)  # 규칙 경로만
        if not reply:
            raise SystemExit(f"규칙 대응 없음: '{note}' — 다른 지적 문장으로 다시 입력")
        pages = []
        for tag, concept in (("before", before_concept), ("after", after_concept)):
            card["concept"] = concept
            rid = f"rf-{a.industry}-{tag}"
            design.publish_choice(rid, copy.deepcopy(card), "v1")  # 같은 v1에 명세만 바꿈
            html = (gen / rid / "published" / "index.html").read_text(encoding="utf-8")
            path = out_dir / f"{a.industry}-{tag}.html"
            path.write_text(html, encoding="utf-8")
            pages.append({"industry": a.industry, "level": "full", "variant": "v1",
                          "html": path, "expect": {"name": "x"},
                          "action_facts": card_action_facts(card)})
    finally:
        settings.generated_dir = old
    build_sec = time.perf_counter() - t0

    evaluate_actions(pages)
    try:
        t1 = time.perf_counter()
        measure(pages, out_dir)
        measure_sec = time.perf_counter() - t1
        measured = True
    except Exception as e:
        print(f"브라우저 측정 건너뜀(도구 없음): {e}")
        measure_sec = 0.0
        measured = False

    changed = {k: (before_concept.get(k), after_concept.get(k))
               for k in ("palette", "font_pair", "density", "radius", "lead", "mood")
               if before_concept.get(k) != after_concept.get(k)}
    today = datetime.date.today().isoformat()
    lines = [
        f"# 보고 고치기 시범 ({a.industry}, {today})",
        "",
        f"- 지적(사람 입력): {note}",
        f"- 명세 패치: `_keyword_adjust` 규칙 경로만 (AI 호출 없음). 답: {reply}",
        "- 바뀐 값: " + (", ".join(f"{k} {v[0]}→{v[1]}" for k, v in changed.items()) or "(없음)"),
        f"- 휴대폰 {VIEW_W}×{VIEW_H}, v1 동일 변형에 명세만 교체. "
        f"걸린 시간 {build_sec + measure_sec:.1f}초, 비용 0원.",
        f"- 스크린샷: `{a.industry}-before-fold.png` → `{a.industry}-after-fold.png` ({out_dir})",
        "",
        "## 전후 6요소 점수 (D37, run_site_quality 재사용)",
        "",
        "| 구분 | 6요소 | 누를 것 |",
        "|---|---|---|",
    ]
    for pg, tag in zip(pages, ("수정 전", "수정 후")):
        act = pg.get("actions") or {}
        lines.append(f"| {tag} | {six_line(pg.get('m'))} | {'O' if act.get('ok') else 'X'} |")
    if measured:
        b, f = (p.get("m") or {} for p in pages)
        lines += ["", "## 전후 원값",
                  "",
                  "| 구분 | 제목비율 | 여백종류 | 첫화면그림 | 색수 | 버튼모양 | 첫화면행동 |",
                  "|---|---|---|---|---|---|---|"]
        for pg_m, tag in ((b, "수정 전"), (f, "수정 후")):
            s = _six(pg_m)
            lines.append(
                f"| {tag} | {pg_m.get('title_ratio', 0):.2f} {'O' if s['title'] else 'X'} | "
                f"{pg_m.get('spacing_steps', '-')} {'O' if s['spacing'] else 'X'} | "
                f"{pg_m.get('hero_visual', 0):.2f} | "
                f"{pg_m.get('color_count', '-')} {'O' if s['color'] else 'X'} | "
                f"{'O' if s['cta'] else 'X'} | "
                f"{pg_m.get('first_screen_actions', '-')} {'O' if s['actions'] else 'X'} |")
    else:
        lines.append("\n> 브라우저 측정 건너뜀으로 6요소는 미측정, 누를 것 점검만 기록.")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
