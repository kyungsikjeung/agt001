"""디자인 학습 기록 (DECISIONS.md D44·D45).

사장님이 어떤 시안을 보고·고르고·말로 고쳤는지, 공개 뒤 문의가 왔는지, 부품으로 못 담은 요구가 무엇인지를
유입 기록(funnel_events)에 남긴다. 명세 값(목록 키)과 사이트 키만 쓰고 가게 사실·대화 원문은 넣지 않는다(90일 보관).
기록이 실패해도 사장님 흐름은 막지 않는다.
"""
import logging
from typing import Optional

from app.services import funnel

log = logging.getLogger(__name__)

# 사장님이 "담을 내용"으로 말한 섹션 이름 → 부품 종류. 어느 것에도 안 맞거나 시안에 그 부품이 없으면 못 담은 요구다.
_SECTION_WORDS = (
    (("메뉴", "상품", "객실", "시술", "수업", "클래스", "강좌", "반 구성", "과정", "가격", "요금", "코스", "프로그램"), "offerings"),
    (("소개", "이야기", "약력", "인사", "철학", "특징"), "intro"),
    (("사진", "갤러리", "포트폴리오", "작품"), "gallery"),
    (("오시는", "위치", "지도", "주변", "찾아오", "교통", "주차"), "around"),
    (("문의", "예약", "상담", "연락", "신청", "영업시간", "시간", "운영"), "contact"),
    (("후기", "리뷰"), "reviews"),
    (("영상", "동영상"), "video"),
    (("편의", "이용 안내", "시설"), "features"),
)
# 문의·예약·신청은 연락 부품(contact)이나 버튼 띠(cta) 어느 쪽이든 담긴다.
_SAME = {"contact": {"contact", "cta"}, "around": {"around", "contact"}}
# 기능 판정(intake) 중 지금 부품·공용 기능으로 바로 못 하는 것
_UNMET_VERDICTS = ("out_of_beta", "alternative", "unknown")


def _safe(event: str, props: dict) -> None:
    try:
        funnel.record(event, props=props)
    except Exception:
        log.exception("디자인 기록 실패(%s) — 흐름은 계속", event)


def _industry(card: dict) -> str:
    from app.services import prd_engine as E
    return E.industry_of(card).key


def _variant_summary(spec: dict) -> str:
    """팔레트:글꼴:첫 화면 변형:첫 화면 다음 부품 — 목록 키만."""
    t, secs = spec.get("tokens") or {}, spec.get("sections") or []
    hero = secs[0].get("variant", "") if secs else ""
    after = secs[1].get("type", "") if len(secs) > 1 else ""
    return ":".join(str(x) for x in (t.get("palette", ""), t.get("font_pair", ""), hero, after))


def shown(site: str, card: dict, items: list[dict]) -> None:
    concept = card.get("concept") or {}
    props = {"site": site, "industry": _industry(card), "source": concept.get("source") or "rule"}
    props.update({v["id"]: _variant_summary(v["spec"]) for v in items if v["id"] in ("v1", "v2", "v3")})
    _safe("design_shown", props)


def polished(site: str, card: dict, variants: list) -> None:
    """UI 에이전트가 3안을 다듬어 바꿈(J11). 바뀐 안 번호만 남긴다."""
    _safe("design_polished", {"site": site, "industry": _industry(card), "variants": ",".join(variants)})


def chosen(site: str, card: dict, variant: str) -> None:
    _safe("design_chosen", {"site": site, "industry": _industry(card), "variant": variant})


def restyled(site: str, card: dict, before: dict, after: dict) -> None:
    """말로 고치기: 바뀐 명세 칸과 새 값만(요청 원문은 남기지 않음)."""
    keys = ("palette", "font_pair", "density", "radius", "lead")
    changed = {k: after.get(k) for k in keys if after.get(k) != before.get(k)}
    if changed:
        _safe("design_restyled", {"site": site, "industry": _industry(card), **changed})


def published(site: str, card: dict, variant: str) -> None:
    _safe("site_published", {"site": site, "industry": _industry(card), "variant": variant})


def inquiry(site: str) -> None:
    _safe("inquiry_received", {"site": site})


def _section_type(label: str) -> Optional[str]:
    for words, kind in _SECTION_WORDS:
        if any(w in label for w in words):
            return kind
    return None


def unmet_items(card: dict) -> list[dict]:
    """부품·공용 기능으로 못 담은 요구 [{kind, ref?, verdict?, label?}]."""
    from app.services import design_variants as DV

    types = {s["type"] for s in DV.base_spec(card)["sections"]}
    out = []
    for label in DV._values(card, "sections"):
        kind = _section_type(label)
        if kind is None or not (_SAME.get(kind, {kind}) & types):
            out.append({"kind": "section", "label": label, "ref": kind or "none"})
    for v in card.get("features_judged") or []:
        if v.get("verdict") in _UNMET_VERDICTS:
            item = {"kind": "feature", "verdict": v["verdict"], "ref": v.get("id") or "none"}
            if not v.get("id"):
                item["label"] = v.get("text") or ""
            out.append(item)
    return out


def unmet(site: str, card: dict) -> None:
    try:
        items = unmet_items(card)
    except Exception:
        log.exception("못 담은 요구 계산 실패 — 흐름은 계속")
        return
    industry = _industry(card)
    for item in items:
        _safe("unmet_need", {"site": site, "industry": industry, **item})


def report(days: int = 90, now=None) -> dict:
    """D44·D45 숫자: 시안 → 고르기 → 공개 → 문의, 말로 고친 칸, 못 담은 요구 비율(느린 경로를 켤 조건 10%)."""
    import datetime
    from collections import Counter

    from sqlalchemy import select

    from app.db.models import FunnelEventRow
    from app.db.session import get_sessionmaker

    now = now or datetime.datetime.now(datetime.timezone.utc)
    since = now - datetime.timedelta(days=days)
    names = ("design_shown", "design_chosen", "design_restyled", "site_published", "inquiry_received", "unmet_need",
             "voice_stt_ok", "voice_stt_empty", "voice_stt_fail")
    with get_sessionmaker()() as db:
        rows = db.execute(select(FunnelEventRow.event, FunnelEventRow.ts, FunnelEventRow.props)
                          .where(FunnelEventRow.event.in_(names), FunnelEventRow.ts >= since)
                          .order_by(FunnelEventRow.id)).all()
    by = {n: [(ts, p or {}) for e, ts, p in rows if e == n] for n in names}
    sites = lambda n: {p.get("site") for _, p in by[n] if p.get("site")}  # noqa: E731
    shown_s, chosen_s, pub_s, unmet_s = sites("design_shown"), sites("design_chosen"), sites("site_published"), sites("unmet_need")

    # 마지막으로 고른 안(사이트마다)
    last_choice = {}
    for _, p in by["design_chosen"]:
        last_choice[p.get("site")] = p.get("variant")
    # 공개 뒤 30일 안 문의 수(사이트마다 첫 공개 기준)
    first_pub = {}
    for ts, p in by["site_published"]:
        first_pub.setdefault(p.get("site"), ts)
    inq = Counter()
    for ts, p in by["inquiry_received"]:
        start = first_pub.get(p.get("site"))
        if start and start <= ts <= start + datetime.timedelta(days=30):
            inq[p.get("site")] += 1
    restyle = Counter(f"{k}={v}" for _, p in by["design_restyled"] for k, v in p.items() if k not in ("site", "industry"))
    unmet = Counter(f"{p.get('kind')}:{p.get('label') or p.get('ref')}" for _, p in by["unmet_need"])
    rate = lambda a, b: round(len(a) / len(b), 3) if b else None  # noqa: E731
    vok = sum(1 for e, _, _ in rows if e == "voice_stt_ok")
    vfail = sum(1 for e, _, _ in rows if e == "voice_stt_fail")
    return {
        "days": days,
        "sites_shown": len(shown_s),
        "choice_rate": rate(chosen_s & shown_s, shown_s),
        "chosen_variant": dict(Counter(last_choice.values())),
        "publish_rate": rate(pub_s & shown_s, shown_s),
        "sites_published": len(pub_s),
        "inquiries_30d_total": sum(inq.values()),
        "published_with_inquiry_rate": rate(set(inq) & pub_s, pub_s),
        "restyle_changes": dict(restyle.most_common(20)),
        "unmet_site_rate": rate(unmet_s & shown_s, shown_s),
        "unmet_top": dict(unmet.most_common(20)),
        "voice_fail_rate": round(vfail / (vok + vfail), 3) if (vok + vfail) else None,  # 성공 대비 실패율(사이트 키 없음)
    }
