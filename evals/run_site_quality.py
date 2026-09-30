"""공개 사이트 품질 평가: 6업종 × 정보 2단계(다 줌·거의 안 줌) × 3안 = 36쪽.

AI를 부르지 않는다. 평가 시나리오(evals/scenarios/*-terse.json)의 가게 사실로 카드를 직접 만들고,
운영과 같은 코드(design.publish_choice)로 공개본을 만든 뒤 휴대폰 크기(390×844) 브라우저에서 잰다.
사진·AI 문구 초안은 넣지 않는다(사진 칸은 업종 예시 그림으로 나온다).
누를 것 점검(버튼 동작)은 공개본 HTML을 직접 읽어 확인한다(브라우저 없이도 됨):
쪽마다 a[href]·button·form을 모아 tel:/sms: 번호=카드 전화번호, 외부 링크=카드 예약·채널·영상 주소,
# 링크의 id 존재, 죽은 버튼(href="#"·빈 href·javascript:), 폼 action·required 칸을 본다.

사용법: .venv/bin/python -m evals.run_site_quality [--out DIR] [--report PATH]
"""
import argparse
import copy
import datetime
import json
import re
import tempfile
import time
from html.parser import HTMLParser
from pathlib import Path

from app.config import settings
from app.services import design
from app.services import design_variants as DV
from app.services import prd_engine as E
from app.services import prd_schema as S

ROOT = Path(__file__).resolve().parent
INDUSTRIES = ("cafe", "restaurant", "pension", "salon", "academy", "workshop")
VIEW_W, VIEW_H = 390, 844

# 누를 것 점검에서 믿는 폼 주소 앞부분 (문의·예약·주문 공용 API).
_ACTION_FORM_PREFIXES = ("/api/inquiries/", "/api/bookings/", "/api/orders/")


def _digits_only(value) -> str:
    """전화번호 비교용: 숫자만 남긴다."""
    return re.sub(r"\D", "", value or "")


def _norm_link_url(value) -> str:
    """외부 링크 비교용: 앞뒤 공백을 떼고 끝의 '/'를 뗀다."""
    return (value or "").strip().rstrip("/")


def card_action_facts(card: dict) -> dict:
    """카드에서 누를 것 점검에 쓸 사실만 뽑는다 (전화·예약 주소·채널 주소·영상 주소)."""
    slots = card.get("slots") or {}
    phone = ""
    slot = slots.get("phone") or {}
    if slot.get("status") == S.FILLED:
        phone = str(slot.get("value") or "")
    if not phone and isinstance(card.get("phone"), str):
        phone = card["phone"]
    booking = ""
    slot = slots.get("booking_url") or {}
    if slot.get("status") == S.FILLED:
        booking = str(slot.get("value") or "")
    channel = str(card.get("kakao_channel_url") or card.get("channel_url") or "")
    videos = [str(u) for u in (card.get("videos") or []) if isinstance(u, str) and u.strip()]
    return {"phone": phone, "booking_url": booking, "channel_url": channel, "video_urls": videos}


class _ActionCollector(HTMLParser):
    """공개본 HTML에서 링크·버튼·폼·id를 모은다 (표준 라이브러리만, 브라우저 없음)."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list = []
        self.buttons: list = []
        self.forms: list = []
        self.ids: list = []
        self._form_stack: list = []
        self._text_for: list = []  # (종류, 보관 dict) 글자 모으기

    def handle_starttag(self, tag: str, attrs: list) -> None:
        at = dict(attrs)
        if at.get("id"):
            self.ids.append(str(at["id"]))
        if tag == "a" and "href" in at:
            one = {"href": str(at["href"]), "text": ""}
            self.links.append(one)
            self._text_for.append(("a", one))
        elif tag == "button":
            one = {"text": "", "type": str(at.get("type") or ""),
                   "form_action": self._form_stack[-1] if self._form_stack else None}
            self.buttons.append(one)
            self._text_for.append(("button", one))
        elif tag == "form":
            one = {"action": str(at.get("action") or ""), "fields": []}
            self.forms.append(one)
            self._form_stack.append(one["action"])
        elif tag in ("input", "textarea", "select") and self._form_stack is not None and self.forms:
            # 숨김 스팸 칸도 fields에 담기만 한다 (required가 없어 판정에 영향 없음)
            self.forms[-1]["fields"].append({"name": str(at.get("name") or ""),
                                             "required": "required" in at})

    def handle_data(self, data: str) -> None:
        if self._text_for:
            self._text_for[-1][1]["text"] += data

    def handle_endtag(self, tag: str) -> None:
        if tag in ("a", "button") and self._text_for:
            kind, one = self._text_for.pop()
            one["text"] = one["text"].strip()
        elif tag == "form" and self._form_stack:
            self._form_stack.pop()


def collect_actions(html_text: str) -> dict:
    """HTML 한 장에서 링크·버튼·폼·id 목록을 뽑는다."""
    box = _ActionCollector()
    box.feed(html_text or "")
    return {"links": box.links, "buttons": box.buttons, "forms": box.forms, "ids": box.ids}


def check_actions(links: list, buttons: list, forms: list, page_ids, facts: dict) -> list:
    """순수 판정 함수 (브라우저 없이 시험 가능).

    입력: links=[{"href": ...}], buttons=[{"type": ..., "form_action": ...}],
    forms=[{"action": ..., "fields": [{"name": ..., "required": bool}]}],
    page_ids=[id ...], facts={"phone": ..., "booking_url": ...,
    "channel_url": ..., "video_urls": [...]}.
    출력: [{"kind": ..., "detail": ...}]. kind는 dead(죽은 버튼·빠진 내부 주소·잘못된 폼 합침) ·
    wrong_phone(틀린 번호) · unknown_link(모르는 링크) · missing_anchor(빠진 # id) ·
    bad_form(잘못된 폼). dead·wrong_phone이 하나라도 있으면 그 쪽은 X.
    """
    problems = []
    facts = facts or {}
    phone_digits = _digits_only(facts.get("phone"))
    known = {_norm_link_url(facts.get("booking_url")), _norm_link_url(facts.get("channel_url")),
             *(_norm_link_url(u) for u in (facts.get("video_urls") or []))}
    known.discard("")
    ids = set(page_ids or [])
    for link in links or []:
        raw = link.get("href") if isinstance(link, dict) else link
        href = (raw or "").strip()
        lowered = href.lower()
        if href == "":
            problems.append({"kind": "dead", "detail": "빈 href"})
        elif lowered.startswith("javascript:"):
            problems.append({"kind": "dead", "detail": f"javascript: 링크 {href[:40]}"})
        elif href == "#":
            problems.append({"kind": "dead", "detail": 'href="#"'})
        elif lowered.startswith("tel:") or lowered.startswith("sms:"):
            digits = _digits_only(href.split(":", 1)[1])
            if not digits:
                problems.append({"kind": "dead", "detail": f"번호 없는 {href[:20]}"})
            elif digits != phone_digits:
                problems.append({"kind": "wrong_phone",
                                 "detail": f"{href[:30]} (카드 {phone_digits or '번호 없음'})"})
        elif href.startswith("#"):
            target = href[1:].split("?")[0].strip()
            if target and target not in ids:
                problems.append({"kind": "missing_anchor", "detail": f"없는 id #{target}"})
        elif lowered.startswith("https://") or lowered.startswith("http://"):
            if _norm_link_url(href) not in known:
                problems.append({"kind": "unknown_link", "detail": f"모르는 링크 {href[:60]}"})
        # 그 밖 상대경로(/uploads/ 등 그림·내부 주소)는 점검 대상 아님
    for btn in buttons or []:
        btype = str((btn.get("type") if isinstance(btn, dict) else "") or "").lower()
        in_form = isinstance(btn, dict) and btn.get("form_action") is not None
        if in_form and btype in ("", "submit", "reset", "image"):
            continue  # 폼 전송·리셋은 폼 점검에서 따로 본다
        label = str(btn.get("text") or "").strip()[:20] if isinstance(btn, dict) else ""
        problems.append({"kind": "dead", "detail": f"동작 없는 버튼 {label}"})
    for form in forms or []:
        action = str(form.get("action") or "").strip() if isinstance(form, dict) else ""
        fields = form.get("fields") or [] if isinstance(form, dict) else []
        if not any(action.startswith(p) for p in _ACTION_FORM_PREFIXES):
            problems.append({"kind": "bad_form", "detail": f"잘못된 폼 주소 {action or '(없음)'}"})
        elif not any(f.get("required") for f in fields if isinstance(f, dict)):
            problems.append({"kind": "bad_form", "detail": f"required 칸 없는 폼 {action}"})
    return problems


def summarize_action_problems(problems: list) -> dict:
    """문제 목록 → 쪽별 표에 쓸 개수 (죽은 버튼·틀린 번호·모르는 링크).

    죽은 버튼에는 빠진 # id(missing_anchor)와 잘못된 폼(bad_form)도 합친다
    (둘 다 눌러도 동작하지 않으므로)."""
    out = {"dead": 0, "wrong": 0, "unknown": 0}
    for p in problems or []:
        kind = p.get("kind") if isinstance(p, dict) else ""
        if kind in ("dead", "missing_anchor", "bad_form"):
            out["dead"] += 1
        elif kind == "wrong_phone":
            out["wrong"] += 1
        elif kind == "unknown_link":
            out["unknown"] += 1
    return out

# 쪽마다 브라우저 안에서 잰다. 결과는 JSON 한 덩어리.
_PROBE = r"""
(facts) => {
  const vis = (el) => { const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none' && +s.opacity !== 0; };
  const rgb = (c) => { const m = c.match(/rgba?\(([^)]+)\)/); if (!m) return null;
    const p = m[1].split(/[ ,\/]+/).filter(Boolean).map(Number); return {r:p[0], g:p[1], b:p[2], a: p.length > 3 ? p[3] : 1}; };
  // 대비 판정용: rgb + oklch. 짙은 띠(section[data-tone=inverse]) 배경은
  // getComputedStyle이 oklch()로 돌려준다 (QA-1). 못 읽으면 흰 바탕으로 떨어져
  // 흰 글자가 1.00으로 찍혔던 문제. 색 개수(color_count)는 기존 rgb만 쓴다.
  const color = (c) => { const v = rgb(c); if (v) return v;
    const m = c.match(/oklch\(\s*([0-9.]+%?)\s+([0-9.]+)\s+([0-9.]+|none)\s*(?:\/\s*([0-9.]+%?))?\)/);
    if (!m) return null;
    let l = parseFloat(m[1]); if (m[1].endsWith('%')) l /= 100;
    let a = m[4] === undefined ? 1 : parseFloat(m[4]); if (m[4] && m[4].endsWith('%')) a /= 100;
    const v2 = oklchToRgb(l, parseFloat(m[2]), m[3] === 'none' ? 0 : parseFloat(m[3]));
    return {r:v2[0], g:v2[1], b:v2[2], a}; };
  // oklch(L C h) → sRGB 0~255 (gamut 밖은 자른다).
  const oklchToRgb = (l, cc, h) => { const a = cc * Math.cos(h * Math.PI / 180), b = cc * Math.sin(h * Math.PI / 180);
    let L = l + 0.3963377774 * a + 0.2158037573 * b, M = l - 0.1055613458 * a - 0.0638541728 * b,
      S = l - 0.0894841775 * a - 1.2914855480 * b;
    L *= L * L; M *= M * M; S *= S * S;
    return [4.0767416621 * L - 3.3077115913 * M + 0.2309699292 * S,
      -1.2684380046 * L + 2.6097574011 * M - 0.3413193965 * S,
      -0.0041960863 * L - 0.7034186147 * M + 1.7076147010 * S].map(v =>
      Math.min(255, Math.max(0, (v <= 0.0031308 ? 12.92 * v : 1.055 * Math.pow(v, 1 / 2.4) - 0.055)) * 255)); };
  const lum = (c) => { const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
    return 0.2126 * f(c.r) + 0.7152 * f(c.g) + 0.0722 * f(c.b); };
  const blend = (fg, bg) => ({r: fg.r * fg.a + bg.r * (1 - fg.a), g: fg.g * fg.a + bg.g * (1 - fg.a), b: fg.b * fg.a + bg.b * (1 - fg.a), a: 1});
  // 글자 뒤 배경: 불투명한 배경색이 나올 때까지 위로. 배경 그림·그라데이션을 만나면 판정 보류.
  // 바탕(BODY)까지 닿았으면 pageBg=true (사진 위 글자일 수 있음).
  const bgOf = (el) => { let layers = []; let pageBg = false;
    for (let e = el; e; e = e.parentElement) { const s = getComputedStyle(e);
      if (s.backgroundImage && s.backgroundImage !== 'none') return {bg: null, pageBg: false};
      const c = color(s.backgroundColor);
      if (c && c.a > 0) { layers.push(c);
        if (c.a >= 1) { pageBg = (e.tagName === 'BODY' || e.tagName === 'HTML'); break; } } }
    let base = {r:255, g:255, b:255, a:1}; for (const c of layers.reverse()) base = blend(c, base);
    return {bg: base, pageBg}; };
  const out = {overflow: document.documentElement.scrollWidth > window.innerWidth + 1,
    scrollWidth: document.documentElement.scrollWidth, height: document.documentElement.scrollHeight,
    smallText: [], lowContrast: [], contrastUnknown: 0, photoBacked: 0, textChecked: 0, smallTargets: [], brokenImages: 0,
    missingAlt: 0, h1: document.querySelectorAll('h1').length, sections: document.querySelectorAll('section').length};
  const seen = new Set();
  for (const el of document.body.querySelectorAll('*')) {
    const own = [...el.childNodes].filter(n => n.nodeType === 3).map(n => n.textContent.trim()).join(' ').trim();
    if (!own || !vis(el) || el.closest('svg')) continue;
    const s = getComputedStyle(el); const size = parseFloat(s.fontSize); out.textChecked++;
    if (size < 14 && !seen.has('s' + own)) { seen.add('s' + own); out.smallText.push(`${size}px "${own.slice(0, 30)}"`); }
    const fg = color(s.color); const {bg, pageBg} = bgOf(el);
    if (!fg || !bg) { out.contrastUnknown++; continue; }
    // 첫 화면 사진 위 흰 글자: 덮개(.s-media::after)·사진 픽셀은 CSS로 못 읽어
    // 바탕색과 견주면 1.0대로 오판한다. 실측 증거(QA-1 generated/qa1/contrast-pixels.md:
    // 획 뒤 최악이 큰 글자 3.1·보통 글자 4.5 이상)로 덮개 설계가 받치므로 판정 보류(photoBacked)로 둔다.
    // 기준을 낮추지 않는다. 버튼처럼 자체 불투명 바탕이 있으면(pageBg 아님) 그대로 판정한다.
    if (pageBg && el.closest('.s-hero--photo-overlay .s-hero__body')) {
      out.contrastUnknown++; out.photoBacked++; continue; }
    const f = blend(fg, bg); const L1 = lum(f), L2 = lum(bg);
    const ratio = (Math.max(L1, L2) + 0.05) / (Math.min(L1, L2) + 0.05);
    const large = size >= 24 || (size >= 18.66 && +s.fontWeight >= 700);
    if (ratio < (large ? 3 : 4.5) && !seen.has('c' + own)) { seen.add('c' + own);
      out.lowContrast.push(`${ratio.toFixed(2)} "${own.slice(0, 30)}"`); }
  }
  for (const el of document.querySelectorAll('a[href], button, input:not([type=hidden]), textarea, select')) {
    if (!vis(el)) continue; const r = el.getBoundingClientRect();
    if (r.right <= 0 || r.bottom <= 0 || r.left >= document.documentElement.scrollWidth) continue;  // 화면 밖(스팸 숨김 칸)
    // 문장 안 링크는 제외(WCAG 2.5.8 예외). 한 줄짜리 독립 링크·버튼·입력칸만 본다.
    const inline = el.tagName === 'A' && getComputedStyle(el).display === 'inline' && el.parentElement &&
      el.parentElement.textContent.trim().length > el.textContent.trim().length + 5;
    if (!inline && (r.height < 44 || r.width < 44))
      out.smallTargets.push(`${Math.round(r.width)}×${Math.round(r.height)} ${el.tagName.toLowerCase()} "${(el.textContent || el.getAttribute('aria-label') || el.name || '').trim().slice(0, 20)}"`);
  }
  for (const img of document.images) { if (img.complete && img.naturalWidth === 0) out.brokenImages++; if (!img.hasAttribute('alt')) out.missingAlt++; }
  const text = document.body.innerText;
  // 눈에 보이는 글자만(글자 크기 0으로 감춘 빈칸은 제외): 화면에 실제로 보이는 빈칸·'예시' 표시
  const shown = []; const walk = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  for (let n; (n = walk.nextNode());) { const e = n.parentElement;
    if (e && vis(e) && parseFloat(getComputedStyle(e).fontSize) > 0) shown.push(n.textContent); }
  const shownText = shown.join(' ');
  out.placeholders = [...new Set(shownText.match(/\[[^\]\n]{0,20}입력\]/g) || [])];
  // D36: "예시 이미지" 배지는 방문자에게 보이는 게 맞다. 사장님용 안내 문구만 문제로 센다.
  out.exampleLabel = /사진으로 바뀌어요/.test(shownText);
  const firstScreen = [...document.querySelectorAll('h1, h2, a, button, p')].filter(e => vis(e) && e.getBoundingClientRect().top < window.innerHeight);
  const firstText = firstScreen.map(e => e.innerText).join(' ');
  out.nameAboveFold = !!facts.name && firstText.includes(facts.name);
  out.ctaAboveFold = firstScreen.some(e => (e.tagName === 'A' || e.tagName === 'BUTTON') && /문의|전화|예약|신청/.test(e.innerText));
  out.facts = {};
  for (const [k, v] of Object.entries(facts)) {
    if (!v) continue;
    out.facts[k] = k === 'phone' ? !!document.querySelector(`a[href="tel:${v}"]`) || text.includes(v)
      : Array.isArray(v) ? v.every(x => text.includes(x)) : text.includes(v);
  }
  // D37 6요소 (제목 대비·여백 리듬·사진·색·버튼·첫 화면 행동)
  // 1. title_ratio: h1 글자 크기 / 본문(p) 대표 글자 크기(중앙값)
  const h1El = [...document.querySelectorAll('h1')].find(e => vis(e));
  const h1Size = h1El ? parseFloat(getComputedStyle(h1El).fontSize) : 0;
  const pSizes = [...document.querySelectorAll('p')].filter(e => vis(e))
    .map(e => parseFloat(getComputedStyle(e).fontSize)).filter(v => v > 0).sort((a, b) => a - b);
  const pRep = pSizes.length ? pSizes[Math.floor(pSizes.length / 2)] : 0;
  out.title_ratio = (h1Size && pRep) ? +((h1Size / pRep).toFixed(2)) : 0;
  // 2. spacing_steps: section 위·아래 padding 값 종류 수(정수 px 기준)
  const pads = new Set();
  for (const sec of document.querySelectorAll('section')) {
    const s = getComputedStyle(sec);
    const pt = Math.round(parseFloat(s.paddingTop)), pb = Math.round(parseFloat(s.paddingBottom));
    if (!Number.isNaN(pt)) pads.add(pt); if (!Number.isNaN(pb)) pads.add(pb);
  }
  out.spacing_steps = pads.size;
  // 3. hero_visual: 첫 화면(창 높이 안) img·svg·배경그림 차지 넓이 비율(0~1, 참고값)
  const vw = window.innerWidth, vh = window.innerHeight, vArea = vw * vh;
  const clip = (r) => { const w = Math.max(0, Math.min(r.right, vw) - Math.max(r.left, 0));
    const h = Math.max(0, Math.min(r.bottom, vh) - Math.max(r.top, 0)); return w * h; };
  let heroArea = 0;
  for (const el of document.querySelectorAll('img, svg')) {
    if (!vis(el)) continue; const r = el.getBoundingClientRect();
    if (r.bottom <= 0 || r.top >= vh) continue; heroArea += clip(r);
  }
  for (const el of document.querySelectorAll('*')) {
    if (el.tagName === 'IMG' || el.closest('svg')) continue;
    let s; try { s = getComputedStyle(el); } catch (e) { continue; }
    if (!s.backgroundImage || s.backgroundImage === 'none') continue;
    if (!vis(el)) continue; const r = el.getBoundingClientRect();
    if (r.bottom <= 0 || r.top >= vh) continue; heroArea += clip(r);
  }
  out.hero_visual = vArea ? +Math.min(1, heroArea / vArea).toFixed(2) : 0;
  // 4. color_count: 보이는 요소 글자색·배경색 중 무채색 제외 서로 다른 색 수(RGB 16단위 반올림)
  const cols = new Set();
  for (const el of document.querySelectorAll('body, body *')) {
    if (!vis(el) || el.closest('svg')) continue;
    const s = getComputedStyle(el);
    for (const c of [rgb(s.color), rgb(s.backgroundColor)]) {
      if (!c || c.a === 0) continue;
      if (Math.max(c.r, c.g, c.b) - Math.min(c.r, c.g, c.b) < 24) continue;
      cols.add([c.r, c.g, c.b].map(v => Math.min(255, Math.round(v / 16) * 16)).join(','));
    }
  }
  out.color_count = cols.size;
  // 5·6. 첫 화면 행동 버튼
  const inFold = (el) => { const r = el.getBoundingClientRect();
    return r.bottom > 0 && r.top < window.innerHeight && r.width > 0 && r.height > 0; };
  const isAction = (el) => { const t = (el.innerText || '') + ' ' + (el.getAttribute('aria-label') || '');
    if (/문의|전화|예약|신청/.test(t)) return true;
    const h = el.getAttribute('href') || ''; return h.startsWith('tel:'); };
  const foldActions = [...document.querySelectorAll('a, button')].filter(e => vis(e) && inFold(e) && isAction(e));
  out.first_screen_actions = foldActions.length;
  const foldBtns = [...document.querySelectorAll('a, button')].filter(e => vis(e) && inFold(e));
  const cta = foldActions[0]
    || foldBtns.find(e => (e.tagName === 'BUTTON') || (e.tagName === 'A' && e.classList.contains('btn')))
    || null;
  if (cta) {
    const r = cta.getBoundingClientRect(); const s = getComputedStyle(cta);
    const rads = [s.borderTopLeftRadius, s.borderTopRightRadius, s.borderBottomLeftRadius, s.borderBottomRightRadius]
      .map(v => parseFloat(v) || 0);
    out.cta_shape = (r.height >= 48 && rads.some(v => v > 0));
    out.cta_h = Math.round(r.height); out.cta_radius = s.borderTopLeftRadius;
  } else { out.cta_shape = false; out.cta_h = 0; out.cta_radius = '0px'; }
  return out;
}
"""


def _scenario(ind: str) -> dict:
    return json.loads((ROOT / "scenarios" / f"{ind}-terse.json").read_text(encoding="utf-8"))


def make_card(ind: str, level: str) -> tuple[dict, dict]:
    """(카드, 화면에 있어야 할 사실). level: full(다 줌) | min(업종·가게 이름만)."""
    sc = _scenario(ind)
    f = sc["facts"]
    card = E.new_card()
    card["industry"] = ind
    E._put(card, "business_type", f["business_type"], S.FILLED, 1)
    E._put(card, "shop_name", f["shop_name"], S.FILLED, 1)
    expect = {"name": f["shop_name"]}
    if level == "full":
        phone = f.get("phone") or "010-0000-" + str(1000 + INDUSTRIES.index(ind))
        offerings = [o.strip() for o in f["offerings"].split(",")]
        E._put(card, "phone", phone, S.FILLED, 1)
        E._put(card, "hours", f["hours"], S.FILLED, 1)
        E._put(card, "location", f["location"], S.FILLED, 1)
        E._put(card, "offerings", offerings, S.FILLED, 1)
        if f.get("detail"):
            E._put(card, "detail", f["detail"], S.FILLED, 1)
        hidden_keys = [k for k, _ in S.INDUSTRIES[ind].hidden]
        card["hidden"] = {"asked": True, "selected": [k for k, v in sc["hidden_facts"].items() if v and k in hidden_keys]}
        expect.update(phone=phone, hours=f["hours"], location=f["location"], offerings=offerings)
    return card, expect


def build_pages(out_dir: Path) -> list[dict]:
    """공개본 HTML 36쪽을 운영 코드로 만든다."""
    pages = []
    gen = Path(tempfile.mkdtemp(prefix="siteq-"))
    old = settings.generated_dir
    settings.generated_dir = gen
    try:
        for ind in INDUSTRIES:
            for level in ("full", "min"):
                card, expect = make_card(ind, level)
                for v in DV.variants(card):
                    rid = f"{ind}-{level}"
                    design.publish_choice(rid, copy.deepcopy(card), v["id"])
                    html = (gen / rid / "published" / "index.html").read_text(encoding="utf-8")
                    path = out_dir / f"{rid}-{v['id']}.html"
                    path.write_text(html, encoding="utf-8")
                    pages.append({"industry": ind, "level": level, "variant": v["id"], "name": v["name"],
                                  "html": path, "expect": expect, "action_facts": card_action_facts(card)})
    finally:
        settings.generated_dir = old
    return pages


def evaluate_actions(pages: list[dict]) -> None:
    """공개본 HTML을 직접 읽어 누를 것 점검을 한다 (브라우저 없이 됨). 결과를 쪽마다 넣는다."""
    for pg in pages:
        html_text = Path(pg["html"]).read_text(encoding="utf-8")
        got = collect_actions(html_text)
        problems = check_actions(got["links"], got["buttons"], got["forms"], got["ids"],
                                 pg.get("action_facts") or {})
        counts = summarize_action_problems(problems)
        pg["actions"] = {"problems": problems, **counts,
                         "ok": counts["dead"] == 0 and counts["wrong"] == 0}


def _serve(out_dir: Path):
    """out_dir와 /art(공용 예시 그림)를 운영처럼 같은 출처로 서빙. file://로 열면 /art/… 사진이 모두 깨진다."""
    import functools
    import http.server
    import threading

    art = settings.templates_dir / "art"

    class H(http.server.SimpleHTTPRequestHandler):
        extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map, ".webp": "image/webp"}

        def translate_path(self, path):
            if path.startswith("/art/"):
                return str(art / path[len("/art/"):].split("?")[0])
            return super().translate_path(path)

        def log_message(self, *a):
            pass

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(H, directory=str(out_dir)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def measure(pages: list[dict], out_dir: Path) -> None:
    from playwright.sync_api import sync_playwright

    srv = _serve(out_dir)
    base = f"http://127.0.0.1:{srv.server_address[1]}/"
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            # 나타내기 애니메이션이 끝난 모습으로 찍는다(전체 캡처는 스크롤하지 않아 아래 부품이 투명하게 찍힌다)
            page = browser.new_page(viewport={"width": VIEW_W, "height": VIEW_H}, device_scale_factor=1,
                                    reduced_motion="reduce")
            for pg in pages:
                page.goto(base + pg["html"].relative_to(out_dir).as_posix())
                page.wait_for_load_state("networkidle")
                pg["m"] = page.evaluate(_PROBE, pg["expect"])
                shot = out_dir / (pg["html"].stem + ".png")
                # 전체 캡처에서는 화면 아래 고정 버튼이 부품 맨 위로 끌려 올라가 겹쳐 보인다(실제 휴대폰에서는 정상)
                page.add_style_tag(content=".s-contact__sticky{position:static}")
                page.screenshot(path=str(shot), full_page=True)
                page.screenshot(path=str(out_dir / (pg["html"].stem + "-fold.png")))
                pg["shot"] = shot
        finally:
            browser.close()
            srv.shutdown()


def distinctness(pages: list[dict], out_dir: Path) -> dict:
    """같은 조건의 3안 첫 화면이 얼마나 다른지 (0 = 똑같음, 100 = 완전히 다름). 픽셀 평균 차이."""
    from PIL import Image, ImageChops, ImageStat

    res = {}
    for ind in INDUSTRIES:
        for level in ("full", "min"):
            ims = [Image.open(out_dir / f"{ind}-{level}-{v}-fold.png").convert("L").resize((130, 281))
                   for v in ("v1", "v2", "v3")]
            diffs = [ImageStat.Stat(ImageChops.difference(ims[a], ims[b])).mean[0] / 2.55
                     for a, b in ((0, 1), (0, 2), (1, 2))]
            res[f"{ind}-{level}"] = round(min(diffs), 1)
    return res


def contact_sheets(pages: list[dict], out_dir: Path) -> None:
    """업종·조건마다 3안 전체 화면을 나란히 붙인 그림 (사람 눈 검토용)."""
    from PIL import Image

    for ind in INDUSTRIES:
        for level in ("full", "min"):
            ims = [Image.open(out_dir / f"{ind}-{level}-{v}.png") for v in ("v1", "v2", "v3")]
            h = max(i.height for i in ims)
            sheet = Image.new("RGB", (VIEW_W * 3 + 40, h), "white")
            for n, im in enumerate(ims):
                sheet.paste(im, (n * (VIEW_W + 20), 0))
            scale = min(1.0, 2400 / h)
            sheet = sheet.resize((int(sheet.width * scale), int(h * scale)))
            sheet.save(out_dir / f"sheet-{ind}-{level}.png")


# ── 채팅방 UX 점검 (P2 UX 3행, 브라우저 없이 static/room.html 직접 읽기) ──
# 공개본 36쪽과 별개로, 요구사항 채팅방의 대기·비교·신뢰 장치가 코드에 살아 있는지 본다.
# 비용 0원·브라우저 불필요라 매일 회귀에 항상 포함한다.

UX_CHECKS = (
    # (행, 라벨, 있어야 할 문자열들)
    ("wait", "대기 체감", ("progressWrap", "progressFill", "시안 먼저",
                          "progressbar", "aria-busy", "나갔다 와도 돼요",
                          "design-thumb.loading", "aspect-ratio",
                          "prefers-reduced-motion")),
    ("compare", "비교 용이", ("designSheetWrap", "DESIGN_DIFFS", "designSheetOpen",
                             "designSheetPick", "크게 보기")),
    ("trust", "신뢰 라벨", ("src-note", "AI 정리", "quote-note", "참고용",
                           "inquiry-note", "30일")),
)


def evaluate_chat_ux(room_path=None) -> list[dict]:
    """room.html에 UX 장치가 있는지. 반환: [{row, label, ok, missing}]."""
    path = Path(room_path) if room_path else ROOT.parent / "static" / "room.html"
    try:
        html = path.read_text(encoding="utf-8")
    except OSError:
        return [{"row": r, "label": lb, "ok": False, "missing": ["room.html 없음"]}
                for r, lb, _ in UX_CHECKS]
    out = []
    for row, label, needles in UX_CHECKS:
        missing = [nd for nd in needles if nd not in html]
        out.append({"row": row, "label": label, "ok": not missing, "missing": missing})
    return out


# ── Qwen vision 첫 화면 채점 (①, --vision 때만, 유료 몇 센트) ──

ZEN_CHAT_URL = "https://opencode.ai/zen/v1/chat/completions"
VISION_MODEL_DEFAULT = "qwen3.8-flash"
VISION_ASPECTS = ("name", "action", "clarity", "trust")
VISION_PROMPT = (
    "너는 모바일 웹사이트 첫 화면 심사위원이다. 390×844 휴대폰 스크린샷을 본다. "
    "JSON만 출력한다: {\"name\": 0~2 (가게 이름이 첫눈에 보이는지), "
    "\"action\": 0~2 (문의·전화·예약 버튼이 분명한지), "
    "\"clarity\": 0~2 (무엇을 하는 곳인지 한눈에 이해되는지), "
    "\"trust\": 0~2 (주소·영업시간·연락처 등 믿을 근거가 보이는지), "
    "\"note\": \"한 줄 근거 20자 안팎\"}"
)


def _vision_call(image_bytes: bytes, model: str, key: str, timeout: float = 90.0) -> tuple:
    """(점수 dict 또는 None, 사용량 dict). 실패하면 (None, {}) — 호출한 쪽이 건너뛴다."""
    import base64
    import httpx

    try:
        from PIL import Image
    except ImportError:
        Image = None
    data = image_bytes
    if Image is not None:
        try:
            import io as _io
            im = Image.open(_io.BytesIO(image_bytes)).convert("RGB")
            im.thumbnail((390, 844))
            buf = _io.BytesIO()
            im.save(buf, format="JPEG", quality=70)
            data = buf.getvalue()
        except Exception:
            data = image_bytes
    b64 = base64.b64encode(data).decode()
    body = {"model": model, "max_tokens": 400,
            "messages": [{"role": "user", "content": [
                {"type": "text", "text": VISION_PROMPT},
                {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + b64}}]}]}
    for attempt in range(3):
        try:
            r = httpx.post(ZEN_CHAT_URL, timeout=timeout,
                           headers={"Authorization": f"Bearer {key}"},
                           json=body)
            if r.status_code != 200:
                time.sleep(2 * (attempt + 1))
                continue
            d = r.json()
            text = (d.get("choices") or [{}])[0].get("message", {}).get("content", "")
            m = re.search(r"\{.*\}", text or "", re.S)
            if not m:
                return None, {}
            got = json.loads(m.group(0))
            scores = {k: got.get(k) for k in VISION_ASPECTS}
            if any(not isinstance(v, int) or not 0 <= v <= 2 for v in scores.values()):
                return None, {}
            if not isinstance(got.get("note"), str):
                return None, {}
            usage = d.get("usage") or {}
            return {**scores, "note": got["note"][:60]}, {
                "prompt": usage.get("prompt_tokens", 0),
                "completion": usage.get("completion_tokens", 0)}
        except Exception:
            time.sleep(2 * (attempt + 1))
    return None, {}


def score_vision(pages: list[dict], out_dir: Path, model: str = VISION_MODEL_DEFAULT) -> dict:
    """fold 스크린샷 36쪽을 vision으로 채점. 키가 없으면 건너뜀 표시만 돌려준다."""
    key = (settings.zen_api_key or "").strip()
    if not key:
        return {"skipped": "ZEN_API_KEY 없음", "model": model, "rows": [], "missing": [],
                "prompt_tokens": 0, "completion_tokens": 0}
    rows, missing = [], []
    prompt_tokens = completion_tokens = 0
    for pg in pages:
        name = f"{pg['industry']}-{pg['level']}-{pg['variant']}"
        shot = out_dir / (pg["html"].stem + "-fold.png")
        if not shot.exists():
            missing.append(name)
            continue
        scores, usage = _vision_call(shot.read_bytes(), model, key)
        prompt_tokens += usage.get("prompt", 0)
        completion_tokens += usage.get("completion", 0)
        if scores is None:
            missing.append(name)
        else:
            rows.append({"page": name, **scores})
        time.sleep(1.5)
    return {"skipped": "", "model": model, "rows": rows, "missing": missing,
            "prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens}


def _six(m: dict) -> dict:
    """D37 6요소 통과 여부. hero_visual은 참고값이라 판정 없음."""
    return {
        "title": (m.get("title_ratio") or 0) >= 2.0,
        "spacing": (m.get("spacing_steps") if m.get("spacing_steps") is not None else 99) <= 3,
        "color": (m.get("color_count") if m.get("color_count") is not None else 99) <= 3,
        "cta": bool(m.get("cta_shape")),
        "actions": 1 <= (m.get("first_screen_actions") or 0) <= 2,
    }


def report(pages: list[dict], dist: dict, ux: list | None = None,
           vision: dict | None = None) -> str:
    rows, issues = [], {"overflow": 0, "small": 0, "contrast": 0, "targets": 0, "broken": 0, "ph": 0, "facts": 0,
                        "fold_name": 0, "fold_cta": 0, "h1": 0, "photo": 0}
    six_rows, six_pass = [], {"title": 0, "spacing": 0, "color": 0, "cta": 0, "actions": 0}
    act_pages = {"dead": 0, "wrong": 0, "unknown": 0, "fail": 0}
    act_total = {"dead": 0, "wrong": 0, "unknown": 0}
    measured = sum(1 for pg in pages if pg.get("m"))
    for pg in pages:
        m = pg.get("m") or {}
        name = f"{pg['industry']}-{pg['level']}-{pg['variant']}"
        counts = summarize_action_problems((pg.get("actions") or {}).get("problems", []))
        ok = counts["dead"] == 0 and counts["wrong"] == 0
        for k in act_total:
            act_total[k] += counts[k]
        for k in ("dead", "wrong", "unknown"):
            act_pages[k] += counts[k] > 0
        act_pages["fail"] += not ok
        if m:
            missing = [k for k, v in (m.get("facts") or {}).items() if not v]
            flags = {"overflow": m.get("overflow"), "small": bool(m.get("smallText")),
                     "contrast": bool(m.get("lowContrast")), "targets": bool(m.get("smallTargets")),
                     "broken": (m.get("brokenImages") or 0) > 0,
                     "ph": bool(m.get("placeholders")) or m.get("exampleLabel"), "facts": bool(missing),
                     "fold_name": not m.get("nameAboveFold"), "fold_cta": not m.get("ctaAboveFold"),
                     "h1": m.get("h1") != 1}
            # 사진 위 글자는 판정 보류(X 아님) — 사장님 사진이 밝으면 안 보일 수 있어 개수는 늘 드러낸다
            issues["photo"] += (m.get("photoBacked") or 0) > 0
            for k, v in flags.items():
                issues[k] += bool(v)
            rows.append(f"| {name} | {'X' if m.get('overflow') else '-'} | "
                        f"{len(m.get('smallText') or [])} | {len(m.get('lowContrast') or [])} | "
                        f"{len(m.get('smallTargets') or [])} | {m.get('brokenImages', '-')} | "
                        f"{', '.join(m.get('placeholders') or []) or ('예시' if m.get('exampleLabel') else '-')} | "
                        f"{', '.join(missing) or '-'} | "
                        f"{'O' if m.get('nameAboveFold') else 'X'} | {'O' if m.get('ctaAboveFold') else 'X'} | "
                        f"{m.get('h1', '-')} | {m.get('height', '-')} | "
                        f"{counts['dead']} | {counts['wrong']} | {counts['unknown']} | {'O' if ok else 'X'} |")
            s = _six(m)
            for k, v in s.items():
                six_pass[k] += bool(v)
            six_rows.append(
                f"| {name} | {m.get('title_ratio', 0):.2f} {'O' if s['title'] else 'X'} | "
                f"{m.get('spacing_steps', '-')} {'O' if s['spacing'] else 'X'} | "
                f"{m.get('hero_visual', 0):.2f} | "
                f"{m.get('color_count', '-')} {'O' if s['color'] else 'X'} | "
                f"{'O' if s['cta'] else 'X'}({m.get('cta_h', 0)}px,{m.get('cta_radius', '-')}) | "
                f"{m.get('first_screen_actions', '-')} {'O' if s['actions'] else 'X'} |")
        else:
            rows.append(f"| {name} | - | - | - | - | - | - | - | - | - | - | - | "
                        f"{counts['dead']} | {counts['wrong']} | {counts['unknown']} | {'O' if ok else 'X'} |")
    n = len(pages)
    detail = []
    for pg in pages:
        m = pg.get("m") or {}
        items = [("작은 글자", m.get("smallText") or []), ("대비 부족", m.get("lowContrast") or []),
                 ("작은 누름 칸", m.get("smallTargets") or [])]
        lines = [f"  - {k}: " + "; ".join(v[:6]) + (" …" if len(v) > 6 else "") for k, v in items if v]
        probs = (pg.get("actions") or {}).get("problems", [])
        if probs:
            lines.append("  - 누를 것: " + "; ".join(p.get("detail", p.get("kind", "")) for p in probs[:6])
                         + (" …" if len(probs) > 6 else ""))
        if lines:
            detail.append(f"- **{pg['industry']}-{pg['level']}-{pg['variant']}**\n" + "\n".join(lines))
    today = datetime.date.today().isoformat()
    head = (f"# 공개 사이트 품질 자동 점검 ({today})\n\n"
            f"대상 {n}쪽(6업종 × 정보 다 줌/거의 안 줌 × 3안), 휴대폰 {VIEW_W}×{VIEW_H}, 공개본(`publish_choice`). "
            "사진·AI 문구 초안 없음. 실행: `.venv/bin/python -m evals.run_site_quality`\n\n"
            + ("" if measured == n else
               f"> 브라우저 측정 {measured}/{n}쪽 건너뜀(브라우저 도구 없음). 누를 것 점검은 HTML 직접 읽기로 모두 함.\n\n")
            + "## 문제가 있는 쪽 수\n\n| 항목 | 기준 | 쪽 수 |\n|---|---|---|\n"
            f"| 가로 넘침 | 화면보다 넓으면 X | {issues['overflow']}/{n} |\n"
            f"| 작은 글자 | 14px 미만 글자가 있음 | {issues['small']}/{n} |\n"
            f"| 글자 대비 | WCAG AA(4.5:1, 큰 글자 3:1) 미달 | {issues['contrast']}/{n} |\n"
            f"| 사진 위 글자 | 첫 화면 사진 덮개 위 글자, CSS로 못 재서 판정 보류(참고, X 아님 — 밝은 사진이면 실측) | {issues['photo']}/{n} |\n"
            f"| 누름 칸 크기 | 44×44px 미만 버튼·링크·입력칸 | {issues['targets']}/{n} |\n"
            f"| 깨진 그림 | 불러오지 못한 이미지 | {issues['broken']}/{n} |\n"
            f"| 빈칸 노출 | 공개본에 `[… 입력]`·'예시' | {issues['ph']}/{n} |\n"
            f"| 사실 누락 | 카드의 이름·전화·시간·주소·상품이 화면에 없음 | {issues['facts']}/{n} |\n"
            f"| 첫 화면 이름 | 첫 화면에 가게 이름 없음 | {issues['fold_name']}/{n} |\n"
            f"| 첫 화면 행동 | 첫 화면에 문의·전화·예약 버튼 없음 | {issues['fold_cta']}/{n} |\n"
            f"| 제목 구조 | h1이 정확히 1개가 아님 | {issues['h1']}/{n} |\n"
            f"| 죽은 버튼 | href=\"#\"·빈 href·javascript:·빠진 # id·잘못된 폼, 1개라도 있으면 X | "
            f"{act_pages['dead']}/{n} (합계 {act_total['dead']}개) |\n"
            f"| 틀린 번호 | tel:/sms: 숫자가 카드 전화번호와 다름, 1개라도 있으면 X | "
            f"{act_pages['wrong']}/{n} (합계 {act_total['wrong']}개) |\n"
            f"| 모르는 링크 | 외부 링크가 카드 예약·채널·영상 주소가 아님(참고, X 아님) | "
            f"{act_pages['unknown']}/{n} (합계 {act_total['unknown']}개) |\n"
            f"| 누를 것 판정 | 죽은 버튼·틀린 번호가 1개라도 있으면 X | {act_pages['fail']}/{n} |\n\n"
            "## 3안 첫 화면 차이 (가장 비슷한 두 안의 픽셀 차이, 0=같음, 8 이상 통과·미만 X)\n\n"
            "| 업종-조건 | 최소 차이 | 판정 |\n|---|---|---|\n"
            + "\n".join(f"| {k} | {v} | {'O' if v >= 8 else 'X'} |" for k, v in dist.items()) +
            "\n\n## 6요소 점수 (D37 매일 회귀)\n\n"
            "### 요약 (항목별 통과 쪽 수)\n\n| 항목 | 기준 | 통과 |\n|---|---|---|\n"
            f"| 제목 대비(title_ratio) | h1/본문 2.0 이상 | {six_pass['title']}/{n} |\n"
            f"| 여백 리듬(spacing_steps) | section 상·하 padding 종류 3개 이하 | {six_pass['spacing']}/{n} |\n"
            f"| 사진(hero_visual) | 첫 화면 그림 넓이 비율(참고값, 판정 없음) | - |\n"
            f"| 색(color_count) | 유채색 3개 이하 | {six_pass['color']}/{n} |\n"
            f"| 카드·버튼(cta_shape) | 첫 화면 첫 버튼 높이 48px 이상·둥근 모서리 | {six_pass['cta']}/{n} |\n"
            f"| 첫 화면 한 가지 행동(first_screen_actions) | 행동 버튼 1~2개 | {six_pass['actions']}/{n} |\n\n"
            "### 쪽별\n\n| 쪽 | 제목비율 | 여백종류 | 첫화면그림 | 색수 | 버튼모양 | 첫화면행동 |\n"
            "|---|---|---|---|---|---|---|\n"
            + "\n".join(six_rows) +
            "\n\n## 쪽별\n\n| 쪽 | 넘침 | 작은 글자 | 대비 | 작은 칸 | 깨진 그림 | 빈칸 | 없는 사실 | 첫화면 이름 | 첫화면 버튼 | h1 | 높이 | 죽은 버튼 | 틀린 번호 | 모르는 링크 | 누를 것 |\n"
            "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|\n")
    text = head + "\n".join(rows) + "\n\n## 세부\n\n" + "\n".join(detail) + "\n"
    if ux is not None:
        text += ("\n## 채팅방 UX 3행 (P2, room.html 직접 읽기, 비용 0원)\n\n"
                 "| 행 | 장치 | 판정 |\n|---|---|---|\n"
                 + "\n".join(f"| {u['label']} | "
                             f"{'있음' if u['ok'] else '없음: ' + ', '.join(u['missing'])} | "
                             f"{'O' if u['ok'] else 'X'} |" for u in ux) + "\n")
    if vision is not None:
        text += "\n## Qwen vision 첫 화면 채점 (①, 0~2점)\n\n"
        if vision.get("skipped"):
            text += f"> 건너뜀: {vision['skipped']}\n"
        else:
            rows_v = vision.get("rows") or []
            n_v = len(rows_v)
            text += (f"모델: {vision.get('model')}, 채점 {n_v}/36쪽"
                     + (f" (미측정 {len(vision.get('missing') or [])}쪽: "
                        + ", ".join(vision.get("missing") or []) + ")" if vision.get("missing") else "")
                     + f", 토큰 입력 {vision.get('prompt_tokens', 0)}/출력 "
                     f"{vision.get('completion_tokens', 0)}\n\n"
                     "| 항목 | 평균 |\n|---|---|\n")
            for k, lb in (("name", "이름 명확"), ("action", "행동 명확"),
                          ("clarity", "한눈 이해"), ("trust", "신뢰 근거")):
                avg = round(sum(r[k] for r in rows_v) / n_v, 2) if n_v else 0
                text += f"| {lb} | {avg} |\n"
            if n_v:
                total = round(sum(sum(r[k] for k in VISION_ASPECTS) for r in rows_v) / n_v, 2)
                text += f"| 합계(/8) | {total} |\n"
            text += ("\n### 쪽별\n\n| 쪽 | 이름 | 행동 | 이해 | 신뢰 | 근거 |\n"
                     "|---|---|---|---|---|---|\n"
                     + "\n".join(f"| {r['page']} | {r['name']} | {r['action']} | "
                                 f"{r['clarity']} | {r['trust']} | {r['note']} |" for r in rows_v) + "\n")
    return text


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None, help="HTML·스크린샷 저장 폴더 (기본: 임시 폴더)")
    ap.add_argument("--report", default=None, help="성적표 저장 경로 (기본: 화면에만)")
    ap.add_argument("--vision", action="store_true",
                    help="Qwen vision으로 36쪽 첫 화면 채점 (유료 몇 센트, ZEN_API_KEY 필요)")
    ap.add_argument("--vision-model", default=VISION_MODEL_DEFAULT,
                    help=f"vision 채점 모델 (기본: {VISION_MODEL_DEFAULT})")
    a = ap.parse_args()
    out_dir = Path(a.out or tempfile.mkdtemp(prefix="siteq-out-"))
    out_dir.mkdir(parents=True, exist_ok=True)
    pages = build_pages(out_dir)
    evaluate_actions(pages)  # 브라우저 없이 HTML 직접 읽기라 항상 됨
    ux = evaluate_chat_ux()  # 비용 0원이라 항상 포함
    try:
        measure(pages, out_dir)
        dist = distinctness(pages, out_dir)
        contact_sheets(pages, out_dir)
    except Exception as e:  # 브라우저 도구가 없으면 누를 것 점검만 보고한다
        print(f"브라우저 측정 건너뜀(도구 없음): {e}")
        dist = {}
    vision = score_vision(pages, out_dir, a.vision_model) if a.vision else None
    text = report(pages, dist, ux=ux, vision=vision)
    (out_dir / "measure.json").write_text(json.dumps([{**{k: v for k, v in p.items() if k not in ('html', 'shot')}}
                                                       for p in pages], ensure_ascii=False, indent=1), encoding="utf-8")
    if a.report:
        Path(a.report).write_text(text, encoding="utf-8")
    print(text)
    print(f"그림·HTML: {out_dir}")


if __name__ == "__main__":
    main()
