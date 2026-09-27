"""요구사항 엔진 (REQUIREMENTS_ENGINE_PLAN.md §3, §7; DECISIONS.md D20~D26).

원칙: 추출은 AI(정해진 JSON), 무엇을 물을지는 규칙. 사장님이 말하지 않은 사실은 채우지 않는다.
카드는 dict로 세션에 저장된다(sessions.prd). 이 모듈은 카드만 바꾸고 저장은 호출한 쪽이 한다.
"""
import json
import logging
import re
import time
import unicodedata
from typing import Optional

from app import llm
from app.services import intake, numbers
from app.services import prd_schema as S
from app.services.stt import normalize_digits as _stt_normalize_digits

log = logging.getLogger(__name__)

SKIP_PHRASES = ("시안 먼저", "나머지는 알아서", "나머지 알아서", "그만 물어", "바로 만들어", "이제 보여")
YES_WORDS = ("네", "예", "응", "맞아요", "맞아", "맞습니다", "좋아요", "yes",
             "넵", "네네", "넹", "ㅇㅇ", "응응", "웅", "그래", "그래요", "오케이", "ok")
NO_WORDS = ("아니요", "아니오", "아니", "no", "틀려요", "아니야", "싫어", "별로")
NONE_WORDS = ("없음", "없어요", "해당 없음", "없습니다", "다 없어요")
LATER = "나중에 넣을게요"
LATER_NORMS = frozenset(("나중에넣을게요", "나중에넣을게", "나중에"))
# 건너뛰기 핵심어 (B-6): 정규화 후 부분일치로 본다. "알아서" 단독은 LET_AI이므로 넣지 않는다.
SKIP_KEYWORDS = ("시안먼저", "나머지알아서", "그만물어", "그만", "바로만들어", "바로만들",
                 "이제보여", "건너뛰", "시안보여", "먼저보여", "먼저볼게", "패스", "스킵")
# 거절 표현 (B-7).
# NEEDLESS("필요 없어요" 계열): 칸 자체를 묻지 않겠다는 뜻이라, 칸 언급이 없어도 대기 칸을 REJECTED로 한다.
# REMOVE("빼주세요/제외" 계열): 뺄 항목을 가리키므로 칸 이름이 함께 언급될 때만 REJECTED로 하고,
#   항목(섹션 등) 제거는 추출 exclude 흐름에 맡긴다 ("바비큐는 빼주세요"가 가게 이름 거절이 되면 안 된다).
REJECT_NEEDLESS = ("필요없", "없어도", "안해도", "안할래", "안할게")
REJECT_REMOVE = ("빼주세요", "빼줘", "빼주세", "제외해", "제외", "없애", "제거", "빼고")
REJECT_PATTERNS = REJECT_NEEDLESS + REJECT_REMOVE
# 앞서 한 말을 고치는 발화: 물은 칸의 답이 아니다("일요일은 쉬는 걸로 바꿔주세요"가 목적 칸에 들어가던 T3 r4).
CHANGE_NORMS = ("바꿔", "말고", "대신", "변경", "고쳐", "수정")
# 부정 표현 (B-3): 숨은 항목 라벨 주변(정규화 후 앞뒤 8자)에 있으면 미선택으로 본다.
# 한 글자("안" 등) 부분일치는 오탐("안내")이 나므로 두 글자 이상 패턴만 둔다.
NEG_NORMS = ("안돼", "안되", "안됨", "안해", "안함", "못해", "못가", "못하",
             "없어", "없다", "아니", "별로", "싫", "불가", "빼", "제외")
# 잡담 판정 (B-4): 정규화 후 이 길이를 넘는데 추출·규칙에 안 걸리면 주제 이탈로 보고 예산을 쓰지 않는다.
CHATTER_LEN = 5
def _spoken_phone(text: str) -> str:
    """"공일공에 0000에 6789번" → "010-0000-6789": 세 글자 이상 이어진 한 자리 수 읽기를 숫자로 바꾸고,
    숫자 덩어리만 남았으면 하이픈으로 잇는다(전화 칸에서만 쓴다)."""
    t = re.sub(r"[공영빵일이삼사오육륙칠팔구]{3,}", lambda m: "".join(str(_KO_ONE.get(c, "")) for c in m.group(0)), text or "")
    groups = re.findall(r"\d+", t)
    joined = "".join(groups)
    if 9 <= len(joined) <= 11 and re.fullmatch(r"[\d\s\-에번은이요.,]*", t.replace("번호", "")):
        return "-".join(groups) if len(groups) > 1 else joined
    return t


_KO_ONE = {"공": 0, "영": 0, "빵": 0, "일": 1, "이": 2, "삼": 3, "사": 4, "오": 5, "육": 6, "륙": 6, "칠": 7, "팔": 8, "구": 9}
# 사실 칸 선택지 중 값이 아닌 것 → 이어서 물을 말
_FOLLOWUP = {"hours": {"매일 같은 시간": "몇 시부터 몇 시까지 여나요? 예: 10시~21시",
                       "요일마다 달라요": "요일별로 알려 주세요. 예: 평일 10~21시, 주말 11~18시"}}
# 리뷰어 에이전트(요약 직전 1회)가 보는 원문 범위
SAID_MAX, SAID_CHARS = 40, 300
# 같은 칸을 못 채운 채 이 횟수만큼 물으면 가정·자리 표시로 넘어간다 (INTAKE_GATE_DESIGN §5).
STUCK_LIMIT = 3
_SATISFIED = (S.FILLED, S.ASSUMED, S.PLACEHOLDER, S.REJECTED)


def _norm(s: str) -> str:
    """공백·문장부호·이모지 제거 + 소문자 + NFKC (B-6 비교용). 한글·영숫자만 남긴다."""
    return re.sub(r"[^가-힣a-z0-9]", "", unicodedata.normalize("NFKC", (s or "").lower()))


def _norm_text(s: str) -> str:
    """근거 판정·저장용 정규화 (B-5): NFKC(전각→반각) + 한글 숫자→아라비아 숫자."""
    return _stt_normalize_digits(unicodedata.normalize("NFKC", s or ""))


YES_NORMS = frozenset(_norm(w) for w in YES_WORDS)
# 추출기가 칸 값으로 돌려주면 버릴 진행 말
_CONTROL_NORMS = frozenset([_norm(S.LET_AI), "알아서", "알아서해줘", "알아서해주세요", "나중에", "나중에넣을게요",
                            "나중에넣을게", "모르겠어요", "없음", "없어요"] + [_norm(p) for p in SKIP_PHRASES])
NO_NORMS = frozenset(_norm(w) for w in NO_WORDS)
NONE_NORMS = frozenset(_norm(w) for w in NONE_WORDS)
SKIP_NORMS = frozenset([_norm(p) for p in SKIP_PHRASES] + list(SKIP_KEYWORDS))


# ── 카드 ──────────────────────────────────────────────────────────────

def new_card(template_industry: Optional[str] = None) -> dict:
    card = {"v": 1, "industry": None, "slots": {}, "hidden": {"asked": False, "selected": []},
            "asked": 0, "turn": 0, "pending": None, "done": False}
    if template_industry in S.INDUSTRIES:
        # D26: 업종과 구성만 가정으로 채우고, 가게 사실은 비운다.
        ind = S.INDUSTRIES[template_industry]
        card["industry"] = ind.key
        _put(card, "business_type", ind.name, S.ASSUMED)
        _put(card, "sections", list(ind.default_sections), S.ASSUMED)
    return card


def _put(card, key, value, status, turn=None, by=None):
    card["slots"][key] = {"value": value, "status": status, "evidence": [] if turn is None else [turn], "by": by}


def _slot(card, key) -> dict:
    return card["slots"].get(key) or {"value": None, "status": S.EMPTY, "evidence": [], "by": None}


def _satisfied(card, key) -> bool:
    return _slot(card, key)["status"] in _SATISFIED


def budget(card) -> int:
    """질문 예산 (INTAKE_GATE_DESIGN §6): 종류별 기본값 + 확인이 필요한 기능마다 1 (최대 4)."""
    confirm = sum(1 for v in card.get("features_judged") or [] if v["verdict"] in intake.NEEDS_CONFIRM)
    return S.budget_for(industry_of(card).key) + min(confirm, S.FEATURE_BONUS_MAX)


def industry_of(card) -> S.Industry:
    if card.get("industry") in S.INDUSTRIES:
        return S.INDUSTRIES[card["industry"]]
    return S.industry_for(_slot(card, "business_type").get("value"))


# ── 추출 (AI) ─────────────────────────────────────────────────────────

_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["updates"],
    "properties": {"updates": {"type": "array", "items": {
        "type": "object", "additionalProperties": False, "required": ["slot", "value"],
        "properties": {"slot": {"type": "string", "enum": list(S.SLOTS)}, "value": {"type": "string"}}}}},
}


def _system_prompt() -> str:
    lines = "\n".join(f"- {s.key}: {s.describe}" for s in S.SLOTS.values())
    return (
        "너는 소상공인 웹사이트 요구사항을 정리하는 추출기다. 사장님의 이번 메시지에서 아래 칸에 해당하는 말만 뽑는다.\n"
        "규칙: 사장님이 실제로 말한 것만 뽑는다. 말하지 않은 전화번호·주소·가격·영업시간은 절대 만들지 않는다. "
        "해당하는 말이 없으면 그 칸은 넣지 않는다. 값이 여러 개인 칸은 항목마다 한 줄씩 따로 넣는다. "
        "메뉴와 가격이 붙어 있으면('아메리카노 5천원') 반드시 메뉴와 가격으로 나눠서 넣는다. "
        "직전 질문에 대한 짧은 대답(예: '전화요')은 그 질문의 칸으로 해석한다. JSON만 출력한다.\n"
        f"칸 정의:\n{lines}\n출력 형식(JSON 스키마):\n{json.dumps(_SCHEMA, ensure_ascii=False)}"
    )


def _parse_updates(raw: str) -> Optional[list[dict]]:
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        # 앞뒤에 설명이 붙은 경우를 위해 가장 바깥 {...}만 한 번 더 시도한다.
        m = re.search(r"\{.*\}", raw or "", re.S)
        if not m:
            return None
        try:
            data = json.loads(m.group(0))
        except ValueError:
            return None
    ups = data.get("updates") if isinstance(data, dict) else None
    if not isinstance(ups, list):
        return None
    out = []
    for u in ups:
        if isinstance(u, dict) and u.get("slot") in S.SLOTS and isinstance(u.get("value"), str):
            value = u["value"].strip()[:200]
            # "알아서 해주세요"·"나중에 넣을게요" 같은 진행 말은 칸 값이 아니다(T2 2차: 5건을 값으로 넣음).
            if value and _norm(value) not in _CONTROL_NORMS:
                out.append({"slot": u["slot"], "value": value})
    return out


def extract_detail(text: str, last_question: Optional[str]) -> tuple[list[dict], bool, int, int]:
    """(추출 결과, 형식 통과 여부, 걸린 ms, 시도 횟수). 대화 턴 기록과 성능 평가에 쓴다."""
    user = (f"[직전 질문] {last_question}\n" if last_question else "") + f"[사장님 메시지] {text}"
    started = time.monotonic()
    for attempt in range(2):
        try:
            ups = _parse_updates(llm.chat_json(_system_prompt(), user))
        except Exception:
            log.exception("요구사항 추출 호출 실패")
            return [], False, int((time.monotonic() - started) * 1000), attempt + 1
        if ups is not None:
            return ups, True, int((time.monotonic() - started) * 1000), attempt + 1
        log.warning("요구사항 추출 형식 오류 (시도 %d)", attempt + 1)
    return [], False, int((time.monotonic() - started) * 1000), 2


def extract(text: str, last_question: Optional[str]) -> list[dict]:
    """형식이 틀리면 한 번 다시 시도하고, 그래도 틀리거나 시간이 넘으면 빈 목록(대화는 계속된다)."""
    return extract_detail(text, last_question)[0]


# ── 규칙 ──────────────────────────────────────────────────────────────

def _digits(s: str) -> str:
    # B-5: NFKC(전각→반각) + 한글 숫자 정규화를 먼저 해서 비교한다.
    return re.sub(r"\D", "", _norm_text(s))


# 근거 판단 공용 기준 (T3 r5): 값의 핵심 낱말이 모두 사장님 말에 있어야 근거로 본다.
# 핵심에서 뺄 기능어 (T3 r5 표: 받기·연동·전송 같은 움직임을 나타내는 말은 근거에서 뺀다).
_FUNCTIONAL_WORDS = frozenset(("받기", "하기", "넣기", "안내", "연동", "연결", "전송"))
_FUNCTIONAL_STEMS = frozenset(("받", "하", "넣"))
# 조사·어미 (긴 것부터 뗀다). 한 글자 줄기는 비교하지 않는다 ("많음"↔"많은데" 오탐 방지).
_ENDINGS = ("으려구요", "려구요", "는데", "은데", "에서", "에게", "한테", "으로", "구요",
            "이랑", "하고", "은", "는", "이", "가", "을", "를", "로", "도", "만", "랑",
            "와", "과", "아", "야", "기", "고", "요", "음", "으")


def _alias_text(s: str) -> str:
    """별칭 맞춤 (intake 26행 규칙과 같게: 카카오톡·카카오 → 카톡). 띄어쓰기는 둔다."""
    return _alias_norm(s, keep_space=True)


def _alias_norm(s: str, keep_space: bool = False) -> str:
    t = unicodedata.normalize("NFKC", (s or "").lower())
    t = t.replace("카카오톡", "카톡").replace("카카오", "카톡")
    return re.sub(r"[^가-힣a-z0-9 ]", "", t) if keep_space else _norm(t)


def _stem_word(w: str) -> str:
    """낱말 끝 조사·어미를 뗀다. 두 글자에서 멈춘다."""
    s = w
    while len(s) > 2:
        hit = next((e for e in _ENDINGS if s.endswith(e) and len(s) - len(e) >= 1), None)
        if hit is None:
            break
        s = s[: -len(hit)]
    return s


def _prefix_len(a: str, b: str) -> int:
    n = 0
    for x, y in zip(a, b):
        if x != y:
            break
        n += 1
    return n


def grounded_phrase(value: str, history: str) -> bool:
    """값 구절이 사장님 원문에 근거가 있는지 (엔진 _in_history·채점기 지어냄 공용).
    핵심 낱말(2자 이상, 기능어 제외)이 하나라도 빠지면 False.
    어미 차이(로·가·으로)는 줄기 비교로 받아주고, 한 글자 줄기(받·많)는 비교하지 않는다
    ("받기"는 기능어 제외로, "많음"·"만들기"는 불일치로 처리한다)."""
    words = [w for w in re.split(r"[\s,·/、]+", _alias_text(value)) if len(w) >= 2]
    core = [w for w in words if w not in _FUNCTIONAL_WORDS and _stem_word(w) not in _FUNCTIONAL_STEMS]
    if not core:
        return False
    hist = _alias_text(history)
    nospace = hist.replace(" ", "")
    hist_words = [w for w in hist.split(" ") if w]
    for w in core:
        if w in nospace:
            continue
        sw = _stem_word(w)
        if len(sw) >= 2 and (sw in nospace
                or any(_prefix_len(sw, _stem_word(h)) >= 2 or _prefix_len(w, h) >= 2 for h in hist_words)):
            continue
        return False
    return True


def grounded(slot: str, value: str, text: str) -> bool:
    """사실 칸 값이 사장님 메시지에 근거가 있는지. 없으면 AI가 지어낸 것으로 보고 버린다."""
    if slot not in S.FACT_SLOTS:
        return True
    norm_text = _norm_text(text)
    norm_value = _norm_text(value)
    d = _digits(norm_value)
    if slot == "phone":
        d = _digits(_spoken_phone(norm_value))
        return bool(d) and d in _digits(_spoken_phone(norm_text))
    if d:
        # 시간·가격·주소 번지: 숫자 값으로 비교한다("오후 세 시" ↔ "15:00", "3만5천원" ↔ "35,000원").
        return numbers.grounded_numbers(norm_value, norm_text)
    # 숫자 없는 사실(예: 지역명)은 두 글자 이상 낱말 하나 이상이 메시지에 있어야 한다.
    words = [w for w in re.split(r"[\s,·/]+", norm_value) if len(w) >= 2]
    return bool(words) and any(w in norm_text for w in words)


def _split_items(value) -> list[str]:
    if isinstance(value, list):
        return [v for v in value if v]
    return [p.strip() for p in re.split(r"[,·/]|그리고|랑|와|과", value or "") if p.strip()]


_EXCLUDE_SUFFIX = re.compile(
    r"(은|는|이|가|을|를|도|만|에서|에게|한테)?\s*"
    r"(빼\s*(주세요|줘|주|고)?|제외(\s*해\s*(주세요|줘)?)?|없애\s*(주세요|줘)?|제거(\s*해\s*(주세요|줘)?)?|빼고)"
    r"\s*[.!~요]*$")
_PARTICLE_SUFFIX = re.compile(r"(은|는|이|가|을|를|도|만|랑|이랑|하고|와|과|아|야)$")
_LEADING_FILLER = re.compile(r"^(아|어|음|저|그|자)\s*[, ]\s*")


def _clean_exclude_term(value: str) -> str:
    """B-13: AI가 조사·문장까지 붙여 돌려줘도 핵심어만 남긴다 ("바비큐는 빼주세요"→"바비큐")."""
    s = unicodedata.normalize("NFKC", (value or "").strip())
    s = _LEADING_FILLER.sub("", s)
    s = _EXCLUDE_SUFFIX.sub("", s).strip()
    s = _PARTICLE_SUFFIX.sub("", s).strip()
    return s


def _refresh_assumed_sections(card: dict, old_ind_key: Optional[str]) -> None:
    """B-12: 업종이 바뀌면 사장님이 직접 말한(FILLED) 섹션은 두고, 가정(ASSUMED)만 새 기본값으로 교체."""
    new_ind_key = card.get("industry")
    if not old_ind_key or old_ind_key == new_ind_key:
        return
    cur = _slot(card, "sections")
    if cur["status"] == S.ASSUMED:
        _put(card, "sections", list(S.INDUSTRIES[new_ind_key].default_sections), S.ASSUMED)


def _slot_label_hit(ind, slot_key: str, norm_text: str) -> bool:
    """메시지가 특정 칸을 가리키는지 (라벨 토큰 2자 이상 포함). B-7의 '목적은 필요 없어요'→goal 판정에 쓴다."""
    label = S.label_for(ind, slot_key)
    tokens = [tok for tok in re.findall(r"[가-힣a-z0-9]{2,}", label.lower())]
    return any(tok in norm_text for tok in tokens)


def _is_control(text: str) -> bool:
    """칸 값이 아닌 진행 말("잘 모르겠어요", "알아서 해주세요" 변형)."""
    n = _norm(text)
    return n in _CONTROL_NORMS or any(w in n for w in DONTKNOW_NORMS)


# "모르겠어요" 계열: 되묻지 않고 "알아서"와 똑같이 닫는다 (T3 r5: 같은 질문 되풀이로 중복·질문 수 초과).
DONTKNOW_NORMS = ("모르겠", "몰라", "모름", "글쎄")
# 사이트 목적 칸에 들어오면 안 되는 말: 사이트를 만든다는 것 자체는 목적이 아니다(T3 cafe-let_ai)
_META_GOAL = re.compile(r"(홈페이지|사이트|웹사이트)\s*(제작|만들|개설)")


_COUNT_RE = re.compile(r"(\d+|한|두|세|네|다섯|여섯|일곱|여덟|아홉|열)\s*(개|실|채|동|반|명|곳)")


def _strip_label(ind, key: str, value: str) -> str:
    """"대표 메뉴 아메리카노", "대표 메뉴: 라떼"처럼 칸 이름이 값 앞에 붙어 오면 뗀다(T3 카페 시나리오)."""
    if isinstance(value, list):
        return [_strip_label(ind, key, v) for v in value]
    v = (value or "").strip()
    for label in sorted({S.label_for(ind, key), S.SLOTS[key].label}, key=len, reverse=True):
        for part in [label] + [x for x in re.split(r"[·/]", label) if len(x) >= 2]:
            if v.startswith(part) and len(v) > len(part):
                rest = v[len(part):].lstrip(" :：-은는이가요")
                # "객실 3개"의 "객실"은 칸 이름이 아니라 값의 일부다(T3 r4: 사이트에 "3개"만 남던 문제).
                if rest and not _COUNT_RE.match(rest):
                    return rest
    return v


# 칸 값으로 쓸 수 없는 막연한 말 (T3 r5: offerings "많음"). 닫힌 목록으로만 버린다.
VAGUE_OFFERINGS = frozenset(_norm(w) for w in ("많음", "많아요", "다양", "여러가지", "이것저것", "여러 개", "기타"))
# 숫자 없는 시간을 물을 때 쓰는 말 (_FOLLOWUP "매일 같은 시간"과 같다).
HOURS_FOLLOWUP_TEXT = "몇 시부터 몇 시까지 여나요? 예: 10시~21시"


def _reserve_hours_followup(card: dict) -> None:
    """숫자 없는 시간 답에 실제 시간을 한 번만 이어 묻는다 (1칸 1회)."""
    asked = card.setdefault("followup_asked", [])
    if "hours" in asked:
        return
    asked.append("hours")
    item = {"slot": "hours", "text": HOURS_FOLLOWUP_TEXT}
    if not card.get("followup"):
        card["followup"] = item
    else:
        card.setdefault("followup_queue", []).append(item)


# N-2: 메뉴·가격 뭉침 분리 ("아메리카노 5천원" → 메뉴는 offerings, 가격은 price, T3 e013·e025 계열).
_PRICE_RE = re.compile(
    r"(?<![가-힣a-z0-9])(?:월\s*|달에\s*|한\s*달\s*)?"
    r"[0-9영공일이삼사오육칠팔구십백천만억\s,]*[0-9영공일이삼사오육칠팔구십백천만억]"
    r"[0-9영공일이삼사오육칠팔구십백천만억\s,]*\s*(?:만원|천원|백원|십원|원)")


def _cut_price(item: str) -> tuple[str, Optional[str]]:
    """값 하나를 (메뉴 부분, 가격 부분)으로 나눈다. 나눌 게 없으면 (원본, None)."""
    m = _PRICE_RE.search(item or "")
    if not m:
        return item, None
    price = m.group(0).strip()
    menu = _PARTICLE_SUFFIX.sub("", _PRICE_RE.sub(" ", item))
    menu = re.sub(r"\s+", " ", menu).strip(" ·,/-")
    menu = _LEADING_FILLER.sub("", menu).strip()
    menu = re.sub(r"(부터|까지|정도|약)$", "", menu).strip()
    if not menu or len(menu) < 2 or _is_control(menu):
        return item, None
    return menu, price


def _separate_menu_price(updates: list[dict], text: str) -> list[dict]:
    """추출이 메뉴·가격을 뭉쳐 돌려주면 나누고, 같은 턴의 가격은 하나로 합친다.

    나누는 조건: 메뉴 부분·가격 부분 둘 다 사장님 말에 있어야 한다. 아니면 원본 그대로 둔다.
    """
    if not any(u["slot"] in ("offerings", "price") for u in updates):
        return updates
    norm_t = _norm_text(text)
    out: list[dict] = []
    price_parts: list[str] = []
    menu_parts: list[str] = []
    touched = False
    for u in updates:
        if u["slot"] == "offerings":
            menus = []
            for item in _split_items(u["value"]):
                menu, price = _cut_price(item)
                if price is not None and menu != item and price in norm_t and menu in norm_t:
                    menus.append(menu)
                    if price not in price_parts:
                        price_parts.append(price)
                    touched = True
                else:
                    menus.append(item)
            out.append({"slot": "offerings", "value": ", ".join(menus)})
        elif u["slot"] == "price":
            for item in _split_items(u["value"]):
                menu, price = _cut_price(item)
                if price is not None and menu != item and price in norm_t and menu in norm_t:
                    if price not in price_parts:
                        price_parts.append(price)
                    if menu not in menu_parts:
                        menu_parts.append(menu)
                    touched = True
                elif item not in price_parts and grounded("price", item, text):
                    # 지어낸 가격은 합치기 전에 버린다 (합친 뒤에는 통째로 탈락하므로).
                    price_parts.append(item)
            # price 업데이트는 아래에서 합쳐서 다시 넣는다
        else:
            out.append(u)
    if not touched and not any(u["slot"] == "price" for u in updates):
        return updates
    if menu_parts:
        out.append({"slot": "offerings", "value": ", ".join(menu_parts)})
    if price_parts or any(u["slot"] == "price" for u in updates):
        out.append({"slot": "price", "value": ", ".join(price_parts)})
    return out


def _in_history(value: str, history: str) -> bool:
    """N-3: 값이 지금까지 대화에 근거가 있는지 (채점의 지어냄 판정과 같은 기준)."""
    s = (value or "").strip()
    if not s:
        return False
    if s in history:
        return True
    d = re.sub(r"\D", "", s)
    if d and d in re.sub(r"\D", "", history):
        return True
    # 숫자 없는 값의 낱말 판정은 공용 기준을 쓴다 (전화·주소·가격과 숫자 값은 위에서 끝낸다).
    return grounded_phrase(s, history)


def _judge_features(card: dict) -> None:

    """새로 들어온 기능 요구를 사례집으로 판정한다 (§2 ⑧~⑬). 확인 질문은 줄에 세우고, 알림은 이번 턴 메모로 남긴다."""
    judged = card.setdefault("features_judged", [])
    seen = {v["text"] for v in judged}
    ids = {v["id"] for v in judged if v.get("id")}
    notes = card.setdefault("notes", {"turn": card["turn"], "items": []})
    if notes["turn"] != card["turn"]:
        card["notes"] = notes = {"turn": card["turn"], "items": []}
    for text in _slot(card, "features").get("value") or []:
        if text in seen:
            continue
        v = intake.judge(text)
        if v.get("id") and v["id"] in ids:
            continue  # 같은 기능을 다르게 말한 경우
        judged.append(v)
        seen.add(text)
        if v.get("id"):
            ids.add(v["id"])
        notes["items"].append(intake.note_for(v))
        if v.get("question"):
            card.setdefault("feature_queue", []).append(v["id"])
        if v["verdict"] == intake.OUT_OF_BETA:
            card.setdefault("later", []).append(v.get("name") or text)


def apply_updates(card: dict, updates: list[dict], text: str, by=None, is_owner=True) -> list[str]:
    """추출 결과를 규칙에 맞춰 카드에 넣는다. 반영한 칸 키 목록을 돌려준다."""
    turn = card["turn"]
    applied = []
    updates = _separate_menu_price(updates, text)  # N-2: 메뉴·가격 뭉침 분리
    # N-3: 근거 판단용 대화 기록 (turn()은 said에 현재 메시지를 먼저 넣어 둔다).
    history = "\n".join([*(card.get("said") or []), text])
    for u in updates:
        key, value = u["slot"], u["value"]
        if not grounded(key, value, text):
            log.info("근거 없는 사실 버림: %s", key)
            continue
        if (key in ("target", "features") and key not in industry_of(card).required
                and (card.get("pending") or {}).get("slot") != key):
            # N-3: 묻지도 않은 대상·기능을 근거 없이 채우지 않는다. 근거 있는 항목만 살린다.
            if S.SLOTS[key].multi:
                value = ", ".join(i for i in _split_items(value) if _in_history(i, history))
            elif not _in_history(value, history):
                log.info("근거 없는 %s 버림: %s", key, value)
                continue
        spec = S.SLOTS[key]
        value = _strip_label(industry_of(card), key, value)
        if not value or _is_control(value) or (key == "goal" and _META_GOAL.search(value)):
            continue
        if key == "offerings":
            # 막연한 항목은 버리고 남은 것만 둔다 (T3 r5 restaurant-let_ai "많음").
            kept = [i for i in _split_items(value) if _norm(i) not in VAGUE_OFFERINGS]
            if not kept:
                continue
            value = ", ".join(kept)
        if key == "hours" and not (numbers.value_numbers(str(value)) | numbers.numbers_in(str(value))):
            # 숫자 없는 시간은 저장하지 않는다 (T3 r5 workshop-changes_mind "주말").
            # 숫자 있는 기존 값은 그대로 두고, 실제 시간을 한 번만 이어 묻는다.
            if not _satisfied(card, key):
                _reserve_hours_followup(card)
            continue
        if key == "exclude":
            terms = [_clean_exclude_term(v) for v in _split_items(value)]
            terms = [v for v in terms if v]
            # B-7: 제외어가 칸 이름 자체면(예: "가격은 빼주세요"→"가격") 그 칸을 REJECTED로 한다.
            ind = industry_of(card)
            rejected_any = False
            rest = []
            for term in terms:
                hit = next((k for k in S.SLOTS if k != "exclude"
                            and (S.label_for(ind, k) == term or term == S.SLOTS[k].label
                                 or (len(term) >= 2 and term in S.label_for(ind, k)))), None)
                if hit:
                    _put(card, hit, None, S.REJECTED, turn, by)
                    applied.append(hit)
                    rejected_any = True
                else:
                    rest.append(term)
            excl = set(_split_items(_slot(card, "exclude").get("value")) + rest)
            if rest or not rejected_any:
                _put(card, "exclude", sorted(excl), S.FILLED, turn, by)
            for k in ("sections", "offerings"):
                cur = _slot(card, k)
                if cur.get("value"):
                    # B-16: 부분일치 제거는 의도된 동작이다 ("바비큐" 제외가 "바비큐장" 섹션을 치운다).
                    kept = [v for v in cur["value"] if not any(e in v for e in excl)]
                    card["slots"][k]["value"] = kept
            applied.append(key)
            continue
        if spec.fact and not is_owner:
            # D24: 공유방에서 방장이 아닌 사람이 말한 사실은 방장이 확인해야 카드에 들어간다.
            _put(card, key, _norm_text(value), S.PENDING_OWNER, turn, by)
            applied.append(key)
            continue
        if spec.fact and isinstance(value, str):
            value = _norm_text(value)  # B-5: 사실은 정규화된 값으로 저장한다
            if key == "phone":
                value = _spoken_phone(value)
        if spec.multi:
            cur = _slot(card, key)
            items = list(cur["value"]) if cur["status"] == S.FILLED and cur.get("value") else []
            for item in _split_items(value):
                if item not in items:
                    items.append(item)
            excl = _split_items(_slot(card, "exclude").get("value"))
            items = [i for i in items if not any(e in i for e in excl)]
            _put(card, key, items, S.FILLED, turn, by)
        else:
            _put(card, key, value, S.FILLED, turn, by)
        if key == "business_type":
            old_ind = card.get("industry")
            new_ind = S.industry_for(value).key
            # 종류 질문으로 정한 개인·단체 등을 '기타'가 덮지 않게 한다.
            if not (new_ind == "other" and old_ind not in (None, "other")):
                card["industry"] = new_ind
            _refresh_assumed_sections(card, old_ind)  # B-12
        if key == "features":
            _judge_features(card)
        applied.append(key)
    return applied


def _default_for(card, key):
    ind = industry_of(card)
    if key == "business_type":
        # 업종을 가정으로 정하면 필수 칸이 바뀌므로, 모르는 업종은 지금 업종(대개 '기타')으로 둔다.
        return ind.name
    if key == "sections":
        return list(ind.default_sections)
    q = S.question_for(ind, key)
    real = [o for o in q.options if o not in (LATER, S.LET_AI)]
    return real[0] if real else None


def _is_reject_message(normed: str) -> bool:
    """B-7: '필요 없어요/빼주세요' 계열의 거절 표현이 있는지."""
    return any(p in normed for p in REJECT_PATTERNS)


def _negated_around(normed: str, idx: int, length: int) -> bool:
    """B-3: 라벨 위치 주변 8자에 부정 패턴이 있는지."""
    window = normed[max(0, idx - 8):idx + length + 8]
    return any(p in window for p in NEG_NORMS)


_EXTRA_RE = re.compile(r"(?:^|/)\s*추가\s*[:：]\s*(.*)$", re.S)
# 항목 뒤에 붙는 서술("바비큐 가능해요", "테라스석 있어요")
_PREDICATE_RE = re.compile(r"\s*(도|은|는|이|가)?\s*(가능(해요|합니다|함|하고)?|있어요|있음|있습니다|있고|돼요|됩니다|되고|해요|제공(해요|합니다)?)?[\s.!~]*$")


def _strip_predicate(item: str) -> str:
    return _PREDICATE_RE.sub("", (item or "").strip()).strip(" ,·/—-:")


def _extra_items(text: str) -> list[str]:
    """사장님이 목록 밖에서 더한 항목 이름들. 서술을 떼고 2자 이상만, 최대 5개."""
    out: list[str] = []
    for part in re.split(r"[,、·/]|\s그리고\s", text or ""):
        item = _strip_predicate(part)[:20]
        if len(_norm(item)) >= 2 and item not in out:
            out.append(item)
    return out[:5]


_ORDINAL = {"첫": 1, "두": 2, "세": 3, "네": 4, "다섯": 5}
_SPOKEN_NUM = {"일": 1, "이": 2, "삼": 3, "사": 4, "오": 5, "한": 1, "두": 2, "세": 3, "네": 4, "다섯": 5}
# 정규화(공백·문장부호 제거)한 답 전체가 번호 고르기일 때만. 뒤에 붙는 말: 거·걸로·으로 할게요·요 등.
_TAIL = r"(거|것|꺼|걸|걸로|으로|로)?(요|이요|할게요|해주세요|주세요|해요)?"
_CHOICE_RE = re.compile(r"(?:(?P<ord>첫|두|세|네|다섯)번째|(?P<num>[1-9]|일|이|삼|사|오|한|두|세|네|다섯)번|(?P<digit>[1-9]))" + _TAIL)
_LAST_RE = re.compile(r"(맨)?마지막" + _TAIL)


def _option_index(normed: str, n_options: int) -> Optional[int]:
    """선택지 번호로 한 답이면 0부터 센 자리, 아니면 None. 선택지 개수 밖 번호는 고른 것으로 보지 않는다.
    "하나", "둘"처럼 번·번째가 없는 말은 수량 답일 수 있어 보지 않는다."""
    if not n_options or not normed:
        return None
    if _LAST_RE.fullmatch(normed):
        return n_options - 1
    m = _CHOICE_RE.fullmatch(normed)
    if not m:
        return None
    k = (_ORDINAL.get(m["ord"]) if m["ord"] else
         int(m["num"]) if m["num"] and m["num"].isdigit() else
         _SPOKEN_NUM.get(m["num"]) if m["num"] else int(m["digit"]))
    return k - 1 if k and 1 <= k <= n_options else None


def _answer_pending(card: dict, text: str, by, is_owner: bool) -> Optional[bool]:
    """직전 질문의 선택지·예/아니오 대답을 AI 없이 처리한다. 처리했으면 True, 선택지 대답이 아니면 None."""
    p = card.get("pending")
    if not p:
        return None
    t = text.strip()
    n = _norm(t)
    key = p.get("slot")
    if p["kind"] == "owner_confirm":
        if not is_owner:
            return None
        # B-6: 대소문자 무시·공백/문장부호 제거 후 비교. "네, 맞아요" 같은 공손한 답도 승인으로 본다.
        # 거절을 먼저 본다 ("아니요"가 "네"를 품지 않지만, 혼합 답에서 거절을 우선한다).
        if n in NO_NORMS or (len(t) <= 12 and any(w in n for w in NO_NORMS)):
            card["slots"].pop(key, None)
        elif n in YES_NORMS or (len(t) <= 12 and any(w in n for w in YES_NORMS)):
            card["slots"][key]["status"] = S.FILLED
        else:
            return None
        card["pending"] = None
        return True
    if p["kind"] == "site_kind":
        # 목록 밖 대답이어도 다시 묻지 않는다(자유 대답은 추출로 넘긴다).
        card["kind_asked"] = True
        o = t if t in p["options"] else _fuzzy_option_match(n, t, p["options"])
        if o is None:
            card["pending"] = None
            return None
        card["industry"] = S.KIND_KEYS[S.KIND_OPTIONS.index(o)]
        card["pending"] = None
        return True
    if p["kind"] == "feature":
        fid = p.get("feature")
        card["feature_queue"] = [f for f in card.get("feature_queue") or [] if f != fid]
        o = t if t in p["options"] else _fuzzy_option_match(n, t, p["options"])
        card.setdefault("feature_answers", {})[fid] = o or t[:200]
        card["pending"] = None
        return True if o is not None else None
    if p["kind"] == "conflict":
        # 검토에서 나온 어긋난 값(D34): 사장님이 고른 쪽으로. 목록 밖 대답은 칸 추출로 넘긴다.
        card["conflict_queue"] = [c for c in card.get("conflict_queue") or []
                                  if not (c["slot"] == key and c["said"] == p.get("said"))]
        card["pending"] = None
        o = t if t in p["options"] else _fuzzy_option_match(n, t, p["options"])
        if o is None:
            return None
        if o == p["options"][0]:
            value = _split_items(o) if S.SLOTS[key].multi else o
            status = S.PENDING_OWNER if S.SLOTS[key].fact and not is_owner else S.FILLED
            _put(card, key, value, status, card["turn"], by)
        return True
    if p["kind"] == "multi":
        hidden = industry_of(card).hidden
        # 목록 밖 항목: 화면은 "... / 추가: 바비큐, 테라스석"으로 보낸다. 먼저 떼어 둔다.
        extra = []
        m = _EXTRA_RE.search(t)
        if m:
            extra = _extra_items(m.group(1))
            t = t[:m.start()].strip()
            n = _norm(t)
        # B-2: "없음"은 메시지 전체가 없음 계열일 때만. 고른 항목이 있으면 선택을 먼저 살린다.
        labels = [(k, label) for k, label in hidden]
        selected = []
        for k, label in labels:
            core = label.split("·")[0]
            hit = None
            for cand in (label, core):
                c = _norm(cand)
                idx = n.find(c) if len(c) >= 2 else -1
                if idx >= 0 and not _negated_around(n, idx, len(c)):
                    hit = k
                    break
            if hit and hit not in selected:
                selected.append(hit)
        if selected:
            card["hidden"] = {"asked": True, "selected": selected}
            if extra:
                card["hidden"]["extra"] = extra
            # 고른 항목 말고 덧붙인 말("소형견만 돼요")은 버리지 않는다: 안내 메모로 남기고 칸 추출에도 넘긴다.
            rest = t
            for k, label in labels:
                if k in selected:
                    for cand in sorted((label, label.split("·")[0]), key=len, reverse=True):
                        rest = rest.replace(cand, " ")
            rest = re.sub(r"^[\s,·/\-—:()]+|[\s,·/\-—:()]+$", "", re.sub(r"\s+", " ", rest))
            # "주차 — 바비큐도 돼요"에서 라벨을 떼고 남은 "도 돼요" 같은 찌꺼기는 메모로 남기지 않는다.
            if len(_norm(_strip_predicate(rest))) >= 2:
                card["hidden"]["note"] = rest[:200]
                card["pending_remainder"] = rest[:200]
            card["pending"] = None
            return True
        # 고른 것 없이 "— 덧붙일 말"(화면 형식)이나 추가 항목만 온 경우: 남은 말은 메모이지 항목이 아니다.
        note = t.lstrip("—-– ").strip() if (extra or t.startswith(("—", "-", "–"))) else ""
        if n in NONE_NORMS or extra or note:
            card["hidden"] = {"asked": True, "selected": []}
            if extra:
                card["hidden"]["extra"] = extra
            if note and _norm(note) not in NONE_NORMS and len(_norm(_strip_predicate(note))) >= 2:
                card["hidden"]["note"] = note[:200]
            card["pending"] = None
            return True
        # 목록에 하나도 안 맞는 짧은 답("바비큐 가능해요")은 사장님이 더한 항목이다. 전에는 버려지고 같은 질문을 되풀이했다.
        # 다른 칸 이야기("가게 이름은 …")·숫자·진행 말은 자유 대답 추출로 넘긴다.
        ind = industry_of(card)
        if (len(t) <= 30 and not re.search(r"\d", t) and not _is_control(t)
                and not any(_slot_label_hit(ind, k, n) for k in S.SLOTS)):
            extra = _extra_items(t)
            if extra:
                card["hidden"] = {"asked": True, "selected": [], "extra": extra}
                card["pending"] = None
                return True
        return None  # 목록 밖 대답은 자유 대답으로 추출한다
    # 한 칸 질문
    # 선택지가 "1) 2) 3)"로 보이므로 번호로 답하면 그 선택지다(T3: 목적 칸에 "3"이 들어가던 문제).
    # 말로 고르기(VOICE FR-2): "이 번", "두 번째 거", "마지막 거요"도 같다.
    opts = p.get("options") or []
    idx = _option_index(n, len(opts))
    if idx is not None:
        t = opts[idx]
        n = _norm(t)
    # B-7: 거절 표현이면 그 칸을 REJECTED로 한다 (D23의 "이 항목 빼기"에 해당, 사실 칸 포함).
    # "빼주세요" 계열은 칸 이름이 함께 있어야 거절로 본다 (B-13 제외 흐름과 충돌 방지).
    if any(p in n for p in REJECT_PATTERNS):
        ind = industry_of(card)
        target = next((k for k in S.SLOTS if k != "exclude" and _slot_label_hit(ind, k, n)), None)
        if target is not None or any(p in n for p in REJECT_NEEDLESS):
            reject_slot = target or key
            _put(card, reject_slot, None, S.REJECTED, card["turn"], by)
            card["pending"] = None
            return True
        return None
    # B-6: "알아서 해줘/알아서" 변형, "나중에" 변형, 공백·문장부호·대소문자 무시.
    # "잘 모르겠어요" 계열도 "알아서"와 똑같이 닫는다 (T3 r5 되풀이 방지, 이어 묻기도 같다).
    if n == _norm(S.LET_AI) or "알아서" in n or any(w in n for w in DONTKNOW_NORMS):
        if S.SLOTS[key].fact or key == "shop_name":
            _put(card, key, None, S.PLACEHOLDER, card["turn"], by)
        else:
            _put(card, key, _default_for(card, key), S.ASSUMED, card["turn"], by)
    elif t == LATER or n in LATER_NORMS:
        _put(card, key, None, S.PLACEHOLDER, card["turn"], by)
    elif t in p.get("options", []) or _fuzzy_option_match(n, t, p.get("options", [])) is not None:
        o = t if t in p.get("options", []) else _fuzzy_option_match(n, t, p.get("options", []))
        follow = _FOLLOWUP.get(key, {}).get(o)
        if follow:
            # "매일 같은 시간"은 영업시간 값이 아니다: 실제 시간을 한 번 더 묻는다(T3 카페 시나리오).
            card["followup"] = {"slot": key, "text": follow}
            card["pending"] = None
            return True
        if S.SLOTS[key].fact and not is_owner:
            _put(card, key, _norm_text(o), S.PENDING_OWNER, card["turn"], by)
        else:
            value = [o] if S.SLOTS[key].multi else o
            _put(card, key, value, S.FILLED, card["turn"], by)
            if key == "business_type":
                old_ind = card.get("industry")
                card["industry"] = S.industry_for(o).key
                _refresh_assumed_sections(card, old_ind)  # B-12
    elif n in NONE_NORMS:
        # 이어 묻기가 "없으면 '없음'이라고 해주세요"라고 안내한다. 받지 않으면 같은 질문을 3번 되풀이한다(T3 r4 academy).
        _put(card, key, None, S.REJECTED, card["turn"], by)
    else:
        return None
    card["pending"] = None
    return True


def _fuzzy_option_match(normed: str, raw: str, options: list) -> Optional[str]:
    """B-6: 선택지 변형 인식. 정규화 동등 → 짧은 답(10자 이하)이 선택지를 품거나 그 반대 → 선택지 낱말 포함 순."""
    if not normed:
        return None
    for o in options:
        if _norm(o) == normed:
            return o
    if len(raw.strip()) <= 10:
        for o in options:
            ono = _norm(o)
            if ono and (ono in normed or normed in ono):
                return o
        for o in options:
            words = [w for w in re.findall(r"[가-힣a-z0-9]{2,}", o.lower())]
            if any(w in normed for w in words):
                return o
    return None


def _confirm_question(card: dict, owner_only: bool = False) -> Optional[dict]:
    """닫혀야 승인할 수 있는 확인 질문 하나: 방장 확인 → 기능 확인 → 검토에서 나온 어긋난 값."""
    ind = industry_of(card)
    for key, slot in card["slots"].items():
        if slot["status"] == S.PENDING_OWNER:
            return {"slot": key, "kind": "owner_confirm", "options": ["네", "아니요"],
                    "text": f"{S.label_for(ind, key)}을(를) '{slot['value']}'(으)로 받았어요. 방장님, 맞나요?"}
    if owner_only:
        return None
    for fid in card.get("feature_queue") or []:
        v = next((x for x in card.get("features_judged") or [] if x.get("id") == fid), None)
        if v and v.get("question"):
            return {"slot": None, "kind": "feature", "feature": fid, "options": list(v["question"]["options"]),
                    "text": v["question"]["ask"]}
    for c in card.get("conflict_queue") or []:
        slot = card["slots"].get(c["slot"]) or {}
        cur = slot.get("value")
        cur = ", ".join(cur) if isinstance(cur, list) else str(cur or "")
        if slot.get("status") != S.FILLED or not cur:
            continue
        label = S.label_for(ind, c["slot"])
        return {"slot": c["slot"], "kind": "conflict", "said": c["said"], "options": [c["said"], cur],
                "text": f"다시 읽어 보니 {label}을(를) '{c['said']}'(이)라고 하신 것 같은데, 정리에는 '{cur}'(으)로 되어 있어요. 어느 쪽이 맞나요?"}
    return None


# V2 심화 질문 v0 (REQUIREMENTS_PIPELINE_V2 V2-1): 칸이 채워지면 끝이 아니라
# 칸 종류별 후속 1~2개를 묻는다. 답 없으면 자리 표시로 닫고 넘어간다 (무한 질문 금지).
# 형식: (방금 채워진 칸, 이어 물을 칸, 대상 업종(빈 튜플이면 전부), 방금 값에 있어야 할 말, 질문문)
_FOLLOWUP_V0 = (
    ("offerings", "price", ("cafe", "restaurant", "salon", "workshop", "pension", "academy"), (),
     "각 메뉴·시술 가격은 어떻게 되나요? 예: 컷트 2만원, 염색 8만원. 모르면 '나중에 넣을게요'라고 해주세요."),
    ("offerings", "staff", ("salon", "academy"), (),
     "담당 디자이너·선생님은 누구신가요? 예: 원장 김미용(컷트 담당). 없으면 '없음'이라고 해주세요."),
    ("contact_method", "phone", (), ("전화",),
     "전화로 받으시면 번호를 알려 주세요. 예: 010-0000-0000"),
    ("contact_method", "booking_url", (), ("네이버", "예약", "링크"),
     "예약 페이지 주소를 붙여넣어 주세요. 예: https://booking.naver.com/… 없으면 '나중에 넣을게요'라고 해주세요."),
)


def _maybe_followup(card: dict, applied: list[str]) -> None:
    """V2-1: 방금 채워진 칸이 심화 규칙을 밟으면 물음표를 예약한다 (1칸당 1회).
    한 칸만 채워진 턴은 다음에 바로 묻고(card['followup']), 여러 칸이 한꺼번에
    들어온 턴은 큐에 쌓아 필수·숨은 질문이 끝난 뒤 묻는다(card['followup_queue']).
    기존 흐름(필수 순서·숨은 항목)을 가로채지 않기 위해서다."""
    if not applied:
        return
    asked = card.setdefault("followup_asked", [])
    ind_key = industry_of(card).key
    for trigger, ask_slot, industries, need_words, text in _FOLLOWUP_V0:
        if trigger not in applied or ask_slot in asked or _satisfied(card, ask_slot):
            continue
        if industries and ind_key not in industries:
            continue
        if need_words:
            trigger_text = str((_slot(card, trigger).get("value") or ""))
            if not any(w in trigger_text for w in need_words):
                continue
        asked.append(ask_slot)
        item = {"slot": ask_slot, "text": text}
        if len(applied) == 1 and not card.get("followup"):
            card["followup"] = item
        else:
            card.setdefault("followup_queue", []).append(item)


def next_question(card: dict) -> Optional[dict]:
    """다음에 물을 것 하나. 없으면 None."""
    ind = industry_of(card)
    fu = card.pop("followup", None)
    if fu and not _satisfied(card, fu["slot"]):
        # kind "followup": 같은 칸을 더 자세히 묻는 이어 묻기(답은 한 칸 질문처럼 처리, 평가에서 중복으로 세지 않음)
        return {"slot": fu["slot"], "kind": "followup", "options": [LATER], "text": fu["text"]}
    # 1) 방장 확인이 필요한 사실
    q = _confirm_question(card, owner_only=True)
    if q:
        return q
    # 1-1) 문의 종류가 모호하면 한 번 묻는다 (§2 ⑤): 업종을 들었는데 가게 6업종·프로필 어디에도 안 맞을 때
    if ind.key == "other" and not card.get("kind_asked") and _slot(card, "business_type")["status"] == S.FILLED:
        return {"slot": None, "kind": "site_kind", "options": list(S.KIND_OPTIONS), "text": S.KIND_QUESTION}
    # 1-2) 확인이 필요한 기능 (§2 ⑪⑫)·검토에서 나온 어긋난 값: 사장님이 먼저 말한 요구라 필수 칸보다 앞에 묻는다
    q = _confirm_question(card)
    if q:
        return q
    # 2) 필수 칸 (업종별 순서)
    missing = [k for k in ind.required if not _satisfied(card, k)]
    done_count = len(ind.required) - len(missing)
    # 3) 숨은 항목은 필수 칸이 절반 넘게 찼을 때 한 번 (D21).
    #    업종을 모르면(기타) 묻지 않는다 — 일반 목록("주차·배송")은 엉뚱한 질문이 된다.
    if (ind.key != "other" and not card["hidden"]["asked"] and ind.hidden
            and (done_count >= 3 or not missing)):
        # B-11: 선택지 합계 4개 이하 (조사 #9) — 상위 3개 + 없음. 판정은 전체 목록으로 한다.
        labels = [label for _, label in ind.hidden[:3]]
        q = {"slot": None, "kind": "multi", "options": labels + ["없음"],
             "text": "해당되는 것을 모두 골라 주세요. 목록에 없는 것도 적어 주시면 넣어 드릴게요."}
        if ind.hidden[3:]:
            q["more_options"] = [label for _, label in ind.hidden[3:]]  # 화면 "더 보기" (첫 화면 4개 규칙은 유지)
        return q
    if missing:
        q = S.question_for(ind, missing[0])
        return {"slot": missing[0], "kind": "single", "options": list(q.options) + [S.LET_AI], "text": q.ask}
    # V2-1: 쌓아둔 심화 질문은 필수·숨은 질문이 끝난 뒤에 꺼낸다.
    queue = card.get("followup_queue") or []
    while queue:
        item = queue.pop(0)
        if not _satisfied(card, item["slot"]):
            return {"slot": item["slot"], "kind": "followup", "options": [LATER], "text": item["text"]}
    return None


def finalize(card: dict) -> None:
    """질문을 마칠 때: 남은 필수 칸은 가정(사실 칸은 자리 표시)으로 채운다 (D20, D23)."""
    ind = industry_of(card)
    card["industry"] = ind.key  # 가정값이 업종(과 필수 칸)을 바꾸지 않게 고정한다
    for key in ind.required:
        if not _satisfied(card, key):
            if S.SLOTS[key].fact or key == "shop_name":
                _put(card, key, None, S.PLACEHOLDER)
            else:
                _put(card, key, _default_for(card, key), S.ASSUMED)
    if not _satisfied(card, "sections"):
        _put(card, "sections", list(ind.default_sections), S.ASSUMED)
    contact = str(_slot(card, "contact_method").get("value") or "")
    if not _satisfied(card, "phone") and ("전화" in contact or _slot(card, "contact_method")["status"] != S.FILLED):
        _put(card, "phone", None, S.PLACEHOLDER)
    if not _satisfied(card, "location"):
        _put(card, "location", None, S.PLACEHOLDER)
    # 숨은 항목을 묻기 전에 마쳤으면(건너뛰기·질문 상한) 다시 묻지 않는다.
    card["hidden"]["asked"] = True
    card["pending"] = None
    card["done"] = True


def _stuck_key(pending: Optional[dict]) -> Optional[str]:
    """같은 칸 반복 판정용 키 (B-4). 방장 확인은 엔진에서 해소할 수 없어 제외한다 (B-9)."""
    if not pending:
        return None
    if pending.get("kind") == "multi":
        return "multi:"
    if pending.get("kind") in ("owner_confirm", "site_kind", "feature"):
        return None  # 대답하면 바로 풀리는 질문(목록 밖 대답도 다시 묻지 않음)
    return f"single:{pending.get('slot')}"


def _assume_slot(card: dict, slot_key: str, by=None) -> None:
    """B-4/INTAKE_GATE_DESIGN §5: 같은 칸을 3번 물어도 못 채우면 가정(사실 칸은 자리 표시)으로 두고 넘어간다."""
    if S.SLOTS[slot_key].fact or slot_key == "shop_name":
        _put(card, slot_key, None, S.PLACEHOLDER, card["turn"], by)
    else:
        _put(card, slot_key, _default_for(card, slot_key), S.ASSUMED, card["turn"], by)


def turn(card: dict, text: str, by=None, is_owner=True) -> dict:
    """사장님 메시지 하나를 처리하고 다음에 할 말을 돌려준다."""
    card["turn"] += 1
    t = (text or "").strip()
    n = _norm(t)
    applied: list[str] = []
    # 대화 턴 기록(chat_turns)에 남길 엔진 판단. 원문은 기록하는 쪽이 따로 남긴다.
    trace = {"answered_by_rule": False, "extract_ok": None, "extract_ms": None, "extract_attempts": 0,
             "extracted": [], "skip": False, "asked_slot": (card.get("pending") or {}).get("slot"),
             "asked_kind": (card.get("pending") or {}).get("kind")}
    reason = intake.blocked_reason(t) if t else None
    if reason:
        # §2 ④: 금지 요청은 카드에 넣지 않고 이유를 밝혀 거절한다. 질문 예산도 쓰지 않는다.
        trace.update(blocked=True, done=False, asked=card["asked"])
        return {"done": False, "question": card.get("pending"), "applied": [], "trace": trace, "blocked": reason}
    wants_skip = bool(n) and any(p in n for p in SKIP_NORMS)
    trace["skip"] = wants_skip
    # 리뷰어가 대조할 사장님 원문(최근 SAID_MAX개). 금지 요청은 위에서 이미 돌려보내 여기 남지 않는다.
    said = card.setdefault("said", [])
    said.append(t[:SAID_CHARS])
    del said[:-SAID_MAX]
    if not t:
        # B-4: 빈 메시지는 질문 예산을 쓰지 않고 직전 질문을 그대로 둔다.
        return _repeat_pending(card, applied, trace, from_empty=True)
    if not wants_skip:
        prev_pending = card.get("pending")
        prev_owner_slot = (prev_pending.get("slot") if prev_pending
                           and prev_pending.get("kind") == "owner_confirm" else None)
        answered = _answer_pending(card, t, by, is_owner)
        trace["answered_by_rule"] = bool(answered)
        remainder = card.pop("pending_remainder", None)
        if answered and remainder:
            # 선택과 함께 쓴 말에서도 칸을 뽑는다(예: "주차, 전화는 010-…").
            ups, ok, ms, attempts = extract_detail(remainder, None)
            trace.update(extract_ok=ok, extract_ms=ms, extract_attempts=attempts, extracted=[u["slot"] for u in ups])
            applied = apply_updates(card, ups, remainder, by, is_owner)
        if not answered:
            last_q = (card.get("pending") or {}).get("text")
            ups, ok, ms, attempts = extract_detail(t, last_q)
            trace.update(extract_ok=ok, extract_ms=ms, extract_attempts=attempts,
                         extracted=[u["slot"] for u in ups])
            applied = apply_updates(card, ups, t, by, is_owner)
            # T3 분석 G3: 한 칸 질문에 짧게 답했는데 추출이 다른 칸으로 보냈으면, 그 답은 물은 칸의 값이다
            # ("어떤 것을 소개하고 싶으세요?" → "초등 미술반"을 업종으로 오분류하고 같은 질문을 또 하던 문제).
            ask_slot = (prev_pending or {}).get("slot") if (prev_pending or {}).get("kind") == "single" else None
            # 추출이 아무것도 못 뽑은 잡담은 여기 해당하지 않는다(뭔가 뽑았는데 칸만 엇나간 경우만).
            if (ask_slot and ups and ask_slot not in applied and not S.SLOTS[ask_slot].fact and ask_slot != "business_type"
                    and len(t) <= 30 and not _satisfied(card, ask_slot) and not _is_control(t)
                    and not any(w in n for w in CHANGE_NORMS)):
                value = _split_items(t) if S.SLOTS[ask_slot].multi else t
                _put(card, ask_slot, value, S.FILLED, card["turn"], by)
                applied = list(applied) + [ask_slot]
                trace["direct_answer"] = ask_slot
            # B-8: 방장 확인 대기 중 같은 칸의 자유 대답은 대기값을 갱신하되 확인 질문을 유지한다.
            if (prev_owner_slot and prev_owner_slot in applied
                    and _slot(card, prev_owner_slot)["status"] == S.FILLED and is_owner):
                card["slots"][prev_owner_slot]["status"] = S.PENDING_OWNER
            card["pending"] = None if applied else card.get("pending")
        progress = bool(answered) or bool(applied)
        if progress:
            card["stuck"] = {"slot": None, "count": 0}
            card["chatter"] = 0
            _maybe_followup(card, applied)  # V2-1: 심화 질문이 있으면 다음에 먼저 묻는다
            return _ask_next(card, applied, trace)
        # 진전 없음: 같은 칸 반복이면 stuck을 셈다 (INTAKE_GATE_DESIGN §5).
        key = _stuck_key(card.get("pending"))
        stuck = card.get("stuck") or {"slot": None, "count": 0}
        stuck = {"slot": key, "count": stuck["count"] + 1 if stuck["slot"] == key else 1} if key else {"slot": None, "count": 0}
        card["stuck"] = stuck
        if key and key.startswith("single:") and stuck["count"] >= STUCK_LIMIT:
            _assume_slot(card, key.split(":", 1)[1], by)
            card["stuck"] = {"slot": None, "count": 0}
            card["pending"] = None
            return _ask_next(card, applied, trace)
        if key and key == "multi:" and stuck["count"] >= STUCK_LIMIT:
            card["hidden"] = {"asked": True, "selected": []}
            card["stuck"] = {"slot": None, "count": 0}
            card["pending"] = None
            return _ask_next(card, applied, trace)
        if len(t) > CHATTER_LEN:
            # B-4: 주제 이탈(잡담)은 예산을 쓰지 않고 같은 질문을 다시 보인다.
            # INTAKE_GATE_DESIGN §5: 잡담이 두 번 이어지면 사이트 이야기로 돌아가자고 한 번 말한다.
            card["chatter"] = card.get("chatter", 0) + 1
            result = _repeat_pending(card, applied, trace)
            if card["chatter"] >= 2:
                result["nudge"] = True
                card["chatter"] = 0
            return result
        return _ask_next(card, applied, trace, same_question=True)
    trace["applied"] = applied
    if wants_skip:
        # "나머지는 알아서": 기능 확인·어긋난 값 확인도 닫는다(정리된 값 유지). 방장 확인이 필요한 사실은 남긴다(D24).
        card["feature_queue"] = []
        card["conflict_queue"] = []
    q = None if wants_skip or card["asked"] >= budget(card) else next_question(card)
    if q is None:
        finalize(card)
        trace.update(next_slot=None, next_kind=None, done=True, asked=card["asked"])
        return {"done": True, "question": None, "applied": applied, "trace": trace}
    card["asked"] += 1
    card["pending"] = q
    card["done"] = False
    trace.update(next_slot=q["slot"], next_kind=q["kind"], done=False, asked=card["asked"])
    return {"done": False, "question": q, "applied": applied, "trace": trace}


def _ask_next(card: dict, applied: list[str], trace: dict, same_question: bool = False) -> dict:
    """다음 질문을 등록한다. same_question이면 (짧은 실패 답) 같은 질문을 예산을 써서 다시 보인다."""
    trace["applied"] = applied
    if card["asked"] >= budget(card):
        finalize(card)
        trace.update(next_slot=None, next_kind=None, done=True, asked=card["asked"])
        return {"done": True, "question": None, "applied": applied, "trace": trace}
    if same_question:
        q = card.get("pending") or next_question(card)
    else:
        q = next_question(card)
    if q is None:
        finalize(card)
        trace.update(next_slot=None, next_kind=None, done=True, asked=card["asked"])
        return {"done": True, "question": None, "applied": applied, "trace": trace}
    card["asked"] += 1
    card["pending"] = q
    card["done"] = False
    trace.update(next_slot=q["slot"], next_kind=q["kind"], done=False, asked=card["asked"])
    return {"done": False, "question": q, "applied": applied, "trace": trace}


def _repeat_pending(card: dict, applied: list[str], trace: dict, from_empty: bool = False) -> dict:
    """B-4: 빈 메시지·잡담은 직전 질문을 예산 없이 다시 보인다.

    빈 메시지(폴링·입장)로 처음 띄운 질문은 세지 않고 두었다가, 사장님이 실제로 말한 첫 턴에 센다.
    """
    q = card.get("pending")
    if q is None:
        if not from_empty:
            return _ask_next(card, applied, trace)
        q = next_question(card)
        if q is None:
            finalize(card)
            trace.update(applied=applied, next_slot=None, next_kind=None, done=True, asked=card["asked"])
            return {"done": True, "question": None, "applied": applied, "trace": trace}
        q["counted"] = False
        card["pending"] = q
    elif not from_empty and q.get("counted") is False:
        card["asked"] += 1
        q["counted"] = True
    card["done"] = False
    trace.update(applied=applied, next_slot=q["slot"], next_kind=q["kind"], done=False, asked=card["asked"])
    return {"done": False, "question": q, "applied": applied, "trace": trace}

# ── 리뷰어 에이전트 (요약 직전 1회) ────────────────────────────────
# 규칙 엔진과 추출기가 놓친 요구를 찾는다(첼로 사례: 카카오톡 문의 요구가 버려짐).
# 빠진 것은 원문 인용이 실제 원문에 있을 때만 채우고, 어긋난 것은 고치지 않고 사장님께 묻는다.

_REVIEW_SCHEMA = {
    "type": "object", "required": ["missing", "conflicts"],
    "properties": {
        "missing": {"type": "array", "items": {"type": "object", "required": ["slot", "value", "quote"], "properties": {
            "slot": {"type": "string", "enum": [k for k in S.SLOTS]}, "value": {"type": "string"}, "quote": {"type": "string"}}}},
        "conflicts": {"type": "array", "items": {"type": "object", "required": ["slot", "said", "quote"], "properties": {
            "slot": {"type": "string", "enum": [k for k in S.SLOTS]}, "said": {"type": "string"}, "quote": {"type": "string"}}}},
    },
}


def _review_prompt() -> str:
    lines = "\n".join(f"- {s.key}: {s.describe}" for s in S.SLOTS.values())
    return (
        "너는 웹사이트 요구사항 검토자다. [사장님 원문]과 [정리된 카드]를 비교한다.\n"
        "missing: 원문에서 사장님이 분명히 요구했는데 카드에 없는 것. 특히 기능·연동 요구(예: '문의가 카톡으로 오게')를 놓치지 마라.\n"
        "conflicts: 카드 값이 원문과 다르게 정리된 것(사장님이 말한 값을 said에).\n"
        "규칙: quote에는 원문을 한 글자도 바꾸지 말고 그대로 옮긴다(짧게, 20자 안팎). 원문에 없는 것은 절대 만들지 않는다. "
        "(가정)으로 표시된 값은 사장님이 말하지 않은 기본값이므로 conflicts가 아니다. 없으면 빈 배열. JSON만 출력한다.\n"
        f"칸 정의:\n{lines}\n출력 형식(JSON 스키마):\n{json.dumps(_REVIEW_SCHEMA, ensure_ascii=False)}"
    )


def _parse_review(raw: str, said_text: str) -> tuple[list[dict], list[dict]]:
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        m = re.search(r"\{.*\}", raw or "", re.S)
        data = json.loads(m.group(0)) if m else {}
    norm_said = _norm(said_text)

    def quoted(item) -> bool:
        q = _norm(str(item.get("quote") or ""))
        return len(q) >= 2 and q in norm_said  # 인용이 원문에 없으면 AI가 지어낸 것으로 보고 버린다

    missing = [m for m in data.get("missing") or [] if isinstance(m, dict) and m.get("slot") in S.SLOTS
               and m.get("slot") != "exclude" and str(m.get("value") or "").strip() and quoted(m)]
    conflicts = [c for c in data.get("conflicts") or [] if isinstance(c, dict) and c.get("slot") in S.SLOTS
                 and str(c.get("said") or "").strip() and quoted(c)]
    return missing[:5], conflicts[:3]


def review(card: dict, timeout_sec: float = 15.0) -> dict:
    """요약 직전 검토. 빠진 요구는 카드에 넣고(근거 확인), 어긋난 값은 목록으로 돌려준다. 실패하면 조용히 건너뛴다."""
    said = card.get("said") or []
    result = {"ok": False, "added": [], "conflicts": [], "ms": 0}
    if not said:
        return result
    said_text = "\n".join(f"- {x}" for x in said)
    user = f"[사장님 원문]\n{said_text}\n\n[정리된 카드]\n{summary_text(card)}"
    started = time.monotonic()
    try:
        missing, conflicts = _parse_review(llm.chat_json(_review_prompt(), user, timeout_sec=timeout_sec), said_text)
    except Exception:
        log.exception("요구사항 검토 실패(건너뜀)")
        result["ms"] = int((time.monotonic() - started) * 1000)
        return result
    # 어긋남은 사장님이 채운 칸(FILLED)에서, 말한 값이 카드 값과 실제로 다를 때만 본다.
    # (가정) 기본값을 "다르다"고 짚는 오탐을 막는다(실측: 가정값 3건을 모두 어긋남으로 보고).
    def real_conflict(c) -> bool:
        slot = _slot(card, c["slot"])
        said_n = _norm(c["said"])
        cur = slot.get("value")
        cur_n = _norm(", ".join(cur) if isinstance(cur, list) else str(cur or ""))
        return (slot["status"] == S.FILLED and "가정" not in c["said"] and bool(said_n)
                and said_n not in cur_n and cur_n not in said_n)
    conflicts = [c for c in conflicts if real_conflict(c)]
    turn = card["turn"]
    before = {k: (v.get("status"), json.dumps(v.get("value"), ensure_ascii=False)) for k, v in card["slots"].items()}
    ups = []
    for m in missing:
        slot = _slot(card, m["slot"])
        if slot["status"] in (S.FILLED, S.PENDING_OWNER, S.REJECTED) and not S.SLOTS[m["slot"]].multi:
            continue  # 이미 사장님 말로 채운 한 칸은 덮지 않는다(어긋나면 conflicts로 온다)
        ups.append({"slot": m["slot"], "value": m["value"].strip()[:200]})
    # 사실 칸은 원문 근거(grounded)를 한 번 더 본다: apply_updates가 같은 규칙을 쓴다.
    applied = apply_updates(card, ups, " ".join(said), by="reviewer") if ups else []
    added = [k for k in dict.fromkeys(applied)
             if before.get(k) != (card["slots"][k].get("status"), json.dumps(card["slots"][k].get("value"), ensure_ascii=False))]
    card["review"] = {"turn": turn, "added": added, "conflicts": conflicts}
    result.update(ok=True, added=added, conflicts=conflicts, ms=int((time.monotonic() - started) * 1000))
    return result


def review_text(card: dict) -> str:
    """검토에서 빠진 것을 넣었다고 알리는 말. 어긋난 값은 글로 알리지 않고 게이트가 질문으로 묻는다."""
    r = card.get("review") or {}
    ind = industry_of(card)
    if r.get("added"):
        return "다시 읽어 보니 빠진 게 있어 넣었어요: " + ", ".join(S.label_for(ind, k) for k in r["added"])
    return ""


def close_gate(card: dict) -> dict:
    """승인 전 게이트: 질문을 마친 카드를 요약·승인으로 보내기 전에 열린 것이 없는지 확인한다.

    1) 검토(리뷰어)는 카드마다 한 번만 돈다. 2) 검토가 넣은 기능의 확인 질문·방장 확인·어긋난 값이 남아 있으면
    질문 하나를 돌려준다(질문 예산과 상관없이, 닫혀야 승인할 수 있다). 모두 닫혔으면 question은 None.
    """
    rv = None
    if card.get("review") is None:
        rv = review(card)
        if not rv["ok"]:
            card["review"] = {"turn": card["turn"], "added": [], "conflicts": [], "failed": True}
        card["conflict_queue"] = list(card["review"].get("conflicts") or [])
    q = _confirm_question(card)
    if q is None:
        return {"question": None, "review": rv}
    q["gate"] = True
    card["pending"] = q
    card["done"] = False
    return {"question": q, "review": rv}


# ── 사람이 읽는 형태 ────────────────────────────────────────────────

def format_question(card: dict, q: dict) -> str:
    if q["kind"] == "multi":
        opts = " · ".join(q["options"])
        body = f"{q['text']}\n{opts}"
    else:
        body = q["text"] + "\n" + "  ".join(f"{i + 1}) {o}" for i, o in enumerate(q["options"]))
    if q.get("gate"):
        return f"{body}\n\n(승인 전에 확인할 게 남았어요)"
    return f"{body}\n\n(질문 {card['asked']}/{budget(card)} · '시안 먼저'라고 하시면 나머지는 알아서 채울게요)"


def _display(ind, key, slot) -> str:
    value = slot.get("value")
    if slot["status"] == S.PLACEHOLDER:
        return f"[{S.label_for(ind, key)} 입력 필요]"
    text = ", ".join(value) if isinstance(value, list) else (value or "AI가 정함")
    return f"{text} (가정)" if slot["status"] == S.ASSUMED else text


_SUMMARY_ORDER = ("business_type", "shop_name", "goal", "target", "offerings", "sections", "features", "exclude",
                  "contact_method", "phone", "hours", "location", "price", "detail")


def ack_text(card: dict, applied: list[str]) -> str:
    """이번 메시지에서 알아들은 것을 되짚는다. 사장님이 말한 요구가 버려지지 않았음을 보여준다."""
    if not applied:
        return ""
    ind = industry_of(card)
    parts = []
    for key in dict.fromkeys(applied):
        slot = card["slots"].get(key)
        if not slot or slot.get("value") in (None, "", []):
            continue
        value = ", ".join(slot["value"]) if isinstance(slot["value"], list) else slot["value"]
        parts.append(f"{S.label_for(ind, key)} '{value}'")
    out = ("이렇게 이해했어요: " + " · ".join(parts) + "\n\n") if parts else ""
    notes = card.get("notes") or {}
    if notes.get("turn") == card["turn"] and notes.get("items"):
        out += "\n".join(notes["items"]) + "\n\n"
    return out


def summary_text(card: dict) -> str:
    ind = industry_of(card)
    lines = [f"• {S.label_for(ind, k)}: {_display(ind, k, card['slots'][k])}"
             for k in _SUMMARY_ORDER if k in card["slots"] and card["slots"][k]["status"] != S.REJECTED]
    hidden = [label for key, label in ind.hidden if key in card["hidden"]["selected"]]
    hidden += card["hidden"].get("extra") or []
    if hidden:
        note = card["hidden"].get("note")
        lines.append(f"• 안내할 것: {', '.join(hidden)}" + (f" ({note})" if note else ""))
    for v in card.get("features_judged") or []:
        answer = (card.get("feature_answers") or {}).get(v.get("id"))
        how = {intake.READY: "넣음", intake.OWNER_SETUP: "사장님 준비 필요", intake.ALTERNATIVE: "대체안",
               intake.OUT_OF_BETA: "베타 뒤", "unknown": "확인 필요"}[v["verdict"]]
        lines.append(f"• 기능 '{v.get('name') or v['text']}': {how}" + (f" — {answer}" if answer else ""))
    if card.get("later"):
        lines.append(f"• 나중 할 일: {', '.join(card['later'])}")
    return "\n".join(lines)


def spec_text(card: dict) -> str:
    """코드생성에 넘길 요구사항 요약. 자리 표시 칸은 [..]로 남겨 지어내지 못하게 한다."""
    hows = [f"- {v.get('name') or v['text']}: {v['how']}" for v in card.get("features_judged") or []
            if v["verdict"] in (intake.READY, intake.OWNER_SETUP, intake.ALTERNATIVE) and v.get("how")]
    extra = ("\n기능 구현 방법(사례집):\n" + "\n".join(hows)) if hows else ""
    return ("요구사항 카드:\n" + summary_text(card) + extra
            + "\n(가정)은 기본값, [..] 자리는 비워 두고 자리 표시로 남길 것. '베타 뒤' 기능은 만들지 말 것.")
