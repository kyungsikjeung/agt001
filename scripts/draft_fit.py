"""시안 적합성 채점 (DESIGN_FIT_PLAN §5, LLM·네트워크 불필요).

draft_score가 "보기 좋은가"를 잰다면, 이것은 "사장님이 말한 것이 나오고 손님이 행동까지 가는가"를 잰다.
사용법: .venv/bin/python scripts/draft_fit.py [--json]
기준 미달이 하나라도 있으면 exit 1.
"""
import html as H
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services import design_variants as DV  # noqa: E402
from app.services import card_data as CD  # noqa: E402
from app.services import site_render as SR  # noqa: E402
from scripts import draft_corpus as C  # noqa: E402

METRICS = ("fact_coverage", "price_pair", "category_fit", "staff_mode_fit", "action_consistency",
           "action_reach", "contact_dupe", "map_present", "generic_heading", "strategy_distinct",
           "class_count", "room_count")
_CONTACTISH = ("contact", "cta", "booking")


def _text(fragment: str) -> str:
    return re.sub(r"\s+", " ", H.unescape(re.sub(r"<[^>]+>", " ", fragment)))


def _blocks(doc: str, tag: str, cls: str = "") -> list[str]:
    """<tag class="...cls...">…</tag> 조각들 (중첩 없는 부품 전제)."""
    cls_pat = ('class="[^"]*' + re.escape(cls)) if cls else ""
    return re.findall(rf"<{tag}\b[^>]*{cls_pat}[^>]*>.*?</{tag}>", doc, re.S)


def _facts(case: dict) -> list[str]:
    s, e = case["slots"], case["expect"]
    out = [s[k] for k in ("shop_name", "phone", "hours", "location") if s.get(k)]
    if case["industry"] == "academy":
        # 반 이름은 요일·시간·인원을 뺀 값으로 시안에 나온다
        data = CD.build(C.build_card(case))
        out += [c["name"] for c in data["classes"]]
    elif case["industry"] == "pension":
        # 객실 이름은 인원을 뺀 값으로 시안에 나온다
        data = CD.build(C.build_card(case))
        out += [r["name"] for r in data["rooms"]]
    else:
        out += list(s.get("offerings") or [])
    out += [p for _, p in e["pairs"]] + list(e["staff"])
    return out


def _cta_texts(doc: str) -> dict:
    hero = next(iter(_blocks(doc, "section", "s-hero")), "")
    nav = next(iter(_blocks(doc, "nav", "s-navbar")), "")
    bar = next(iter(_blocks(doc, "nav", "s-actionbar")), "")
    return {"hero": " ".join(_text(b) for b in re.findall(r'<a\b[^>]*s-btn[^>]*>.*?</a>', hero, re.S)),
            "nav": " ".join(_text(b) for b in re.findall(r'<a\b[^>]*s-navbar__cta[^>]*>.*?</a>', nav, re.S)),
            "bar": _text(bar)}


def score_case(case: dict) -> dict:
    card = C.build_card(case)
    data = CD.build(card)
    variants = DV.variants(card)
    e = case["expect"]
    res = {m: [] for m in METRICS}
    for v in variants:
        spec = v["spec"]
        doc = SR.render_site(spec, site_key="fit", title=DV.title_for(card), kind=DV.kind_for(card))
        text = _text(doc)
        facts = _facts(case)
        res["fact_coverage"].append(sum(f in text for f in facts) / max(len(facts), 1))
        rows = _blocks(doc, "li") + _blocks(doc, "tr")
        res["price_pair"].append(all(any(item in _text(r) and price in _text(r) for r in rows)
                                     for item, price in e["pairs"]))
        res["category_fit"].append(all(re.search(rf"<h3\b[^>]*>\s*{re.escape(c)}", doc) for c in e["categories"]))
        if e["staff_mode"]:
            staff_html = " ".join(_blocks(doc, "section", f"s-staff--{e['staff_mode']}"))
            res["staff_mode_fit"].append(bool(staff_html) and all(n in _text(staff_html) for n in e["staff"]))
        else:
            res["staff_mode_fit"].append(True)
        ctas = _cta_texts(doc)
        res["action_consistency"].append(all(any(k in ctas[w] for k in e["action"]) for w in ("hero", "nav", "bar")))
        types = [s["type"] for s in spec["sections"]]
        first = next((i for i, t in enumerate(types) if t in e["action_sections"]), 99)
        res["action_reach"].append(first < 4)
        res["contact_dupe"].append(sum(t in _CONTACTISH for t in types) <= 2)
        if case["slots"].get("location"):
            around = " ".join(_blocks(doc, "section", "s-around"))
            res["map_present"].append("s-map" in around and "예시 지도" in _text(around))
        else:
            res["map_present"].append(True)
        res["generic_heading"].append(not re.search(r"<h2\b[^>]*>\s*사진첩\s*</h2>", doc))
        if case["industry"] in ("academy", "workshop") and data["classes"]:
            # 학원·공방: 반 카드 수 = 반 수
            res["class_count"].append(doc.count('<li class="s-class">') == len(data["classes"]))
        else:
            res["class_count"].append(True)
        if case["industry"] == "pension" and data["rooms"]:
            # 펜션: 객실 카드 수 = 객실 수
            res["room_count"].append(doc.count('<li class="s-room">') == len(data["rooms"]))
        else:
            res["room_count"].append(True)
    seconds = {(v["spec"]["sections"][1]["type"], v["spec"]["sections"][1].get("variant"))
               for v in variants if len(v["spec"]["sections"]) > 1}
    res["strategy_distinct"] = [len(seconds) == len(variants)]
    return {m: (sum(vals) / len(vals)) for m, vals in res.items()}


def main() -> int:
    table = {c["id"]: score_case(c) for c in C.FIT_CASES}
    totals = {m: round(sum(t[m] for t in table.values()) / len(table), 3) for m in METRICS}
    if "--json" in sys.argv:
        print(json.dumps({"cases": table, "totals": totals}, ensure_ascii=False, indent=1))
    else:
        print("case".ljust(18) + " ".join(m[:9].rjust(9) for m in METRICS))
        for cid, t in table.items():
            print(cid.ljust(18) + " ".join(("PASS" if t[m] == 1 else f"{t[m]:.2f}").rjust(9) for m in METRICS))
        print("TOTAL".ljust(18) + " ".join(("PASS" if totals[m] == 1 else f"{totals[m]:.2f}").rjust(9) for m in METRICS))
    return 0 if all(v == 1 for v in totals.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
