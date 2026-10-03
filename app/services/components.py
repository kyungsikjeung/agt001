"""컴포넌트 등록표 (COMPONENT_ENGINE_PLAN §3).

templates/components.json 하나가 부품 정보를 모은다:
- components: 템플릿(type--variant)마다 이름·한 줄 설명·공용 제목 조각 기본값(label_default)
- groups: 같은 데이터(같은 bind)로 바꿔 쓸 수 있는 변형 묶음 → 빌더 '구역 모양 바꾸기'
- styles: 사이트 전체 스타일 축(surface·heading). 기본값은 지금 모양 그대로다.

렌더러(site_render)·구역 편집(layout_edits)·카드 API·컴포넌트 갤러리가 이 모듈만 읽는다.
파일·DB 쓰기 없음. 템플릿 폴더 기준으로 한 번 읽어 캐시한다.
"""
import json
from pathlib import Path

from app.config import settings

_CACHE: dict = {}


def _base() -> Path:
    return Path(settings.templates_dir)


def registry() -> dict:
    """등록표 전체 (캐시). 파일이 없으면 빈 등록표."""
    key = str(_base())
    hit = _CACHE.get(key)
    if hit is not None:
        return hit
    path = _base() / "components.json"
    data = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    built = {
        "components": data.get("components") or {},
        "groups": data.get("groups") or {},
        "styles": data.get("styles") or {},
    }
    _CACHE[key] = built
    return built


def partials() -> dict:
    """공용 조각 templates/partials/*.mustache → {이름: 글}. 끝 줄바꿈은 떼어 둔다(줄 안에 끼워 쓰므로)."""
    key = "partials:" + str(_base())
    hit = _CACHE.get(key)
    if hit is not None:
        return hit
    folder = _base() / "partials"
    out = {}
    if folder.is_dir():
        for path in sorted(folder.glob("*.mustache")):
            out[path.stem] = path.read_text(encoding="utf-8").rstrip("\n")
    _CACHE[key] = out
    return out


def info(key: str) -> dict:
    """type--variant 하나의 정보. 모르면 빈 dict."""
    entry = registry()["components"].get(key)
    return entry if isinstance(entry, dict) else {}


def label_default(key: str) -> str:
    """공용 제목 조각 {{> label}}의 기본 제목(제목이 비었을 때)."""
    value = info(key).get("label_default")
    return value if isinstance(value, str) else ""


def group_for(section_type: str, bind: str) -> dict | None:
    """이 종류·bind 구역이 바꿔 쓸 수 있는 변형 묶음. 없으면 None."""
    for name, group in registry()["groups"].items():
        if not isinstance(group, dict):
            continue
        if group.get("type") == section_type and bind in (group.get("binds") or []):
            return {"name": name, **group}
    return None


def shapes(section_type: str, bind: str) -> list[dict]:
    """빌더 '모양 바꾸기' 목록 [{variant, name, desc, new}]. 바꿀 수 없는 구역이면 빈 목록."""
    group = group_for(section_type, bind)
    if group is None:
        return []
    out = []
    for variant in group.get("variants") or []:
        key = f"{section_type}--{variant}"
        entry = info(key)
        if not entry:
            continue
        out.append({"variant": variant, "name": entry.get("name") or variant,
                    "desc": entry.get("desc") or "", "new": entry.get("new") is True})
    return out


def can_switch(section_type: str, bind: str, variant: str) -> bool:
    """이 구역을 variant 모양으로 바꿀 수 있나 (같은 묶음 안, 템플릿이 있는 것만)."""
    return any(s["variant"] == variant for s in shapes(section_type, bind))


def style_axes() -> dict:
    """스타일 축 {이름: {default, values{값: 이름}}}."""
    return registry()["styles"]


def clean_style(raw) -> dict:
    """사장님이 고른 스타일 → 아는 축·값만, 기본값은 뺀다(기본 = 지금 모양이라 적을 필요 없음)."""
    if not isinstance(raw, dict):
        return {}
    out = {}
    for axis, spec in style_axes().items():
        value = raw.get(axis)
        values = (spec or {}).get("values") or {}
        if isinstance(value, str) and value in values and value != spec.get("default"):
            out[axis] = value
    return out


def body_attrs(tokens: dict) -> dict:
    """명세 tokens의 스타일 축 → <body> data-* 속성. 기본값·모르는 값은 넣지 않는다(지금 출력과 같게)."""
    if not isinstance(tokens, dict):
        return {}
    picked = clean_style({axis: tokens.get(axis) for axis in style_axes()})
    return {f"data-{axis}": value for axis, value in picked.items()}


def problems() -> list[str]:
    """등록표·템플릿이 서로 맞는지 (테스트·갤러리용). 문제가 없으면 빈 목록."""
    base = _base() / "sections"
    files = {p.stem for p in base.glob("*.mustache")} if base.is_dir() else set()
    comps = registry()["components"]
    out = [f"등록표에 없는 템플릿: {k}" for k in sorted(files - set(comps))]
    out += [f"템플릿이 없는 등록표 항목: {k}" for k in sorted(set(comps) - files)]
    for name, group in registry()["groups"].items():
        for variant in (group or {}).get("variants") or []:
            if f"{group.get('type')}--{variant}" not in files:
                out.append(f"묶음 {name}의 변형에 템플릿 없음: {variant}")
    for key in sorted(files):
        text = (base / f"{key}.mustache").read_text(encoding="utf-8")
        if "{{> label}}" in text and not label_default(key):
            out.append(f"{key}: {{{{> label}}}}를 쓰는데 label_default가 없음")
    return out
