"""주소 검색·임시 주소 (MAP_CONTRACT §2-1·2).

REST 키는 서버에서만 쓰고 화면·로그·응답에 내보내지 않는다.
가게 이름·전화는 카카오에 보내지 않는다. 주소 말(query)만 보낸다.
"""
import logging
from typing import Optional

import httpx

from app.services import keystore

log = logging.getLogger(__name__)

_ADDR_URL = "https://dapi.kakao.com/v2/local/search/address.json"
_KEYWORD_URL = "https://dapi.kakao.com/v2/local/search/keyword.json"
_TIMEOUT = 3.0
_MAX = 5

# 대한민국 범위 (PUT /geo도 같은 값으로 본다)
X_MIN, X_MAX = 124.0, 132.0
Y_MIN, Y_MAX = 33.0, 39.0


def _headers(key: str) -> dict:
    return {"Authorization": f"KakaoAK {key}"}


def _one(road: str, jibun: str, x, y) -> Optional[dict]:
    """좌표가 숫자로 읽히면 후보 한 개, 아니면 버린다."""
    try:
        fx, fy = float(x), float(y)
    except (TypeError, ValueError):
        return None
    road, jibun = (road or "").strip(), (jibun or "").strip()
    road = road or jibun  # 도로명이 없는 주소(지번만)도 후보로 둔다
    if not road:
        return None
    return {"road": road, "jibun": jibun, "x": fx, "y": fy}


def _from_address(docs: list) -> list:
    out = []
    for d in docs:
        if not isinstance(d, dict):
            continue
        road = (d.get("road_address") or {}).get("address_name") if isinstance(d.get("road_address"), dict) else ""
        jibun = (d.get("address") or {}).get("address_name") if isinstance(d.get("address"), dict) else ""
        one = _one(road or "", jibun or "", d.get("x"), d.get("y"))
        if one:
            out.append(one)
        if len(out) >= _MAX:
            break
    return out


def _from_keyword(docs: list) -> list:
    out = []
    for d in docs:
        if not isinstance(d, dict):
            continue
        one = _one(d.get("road_address_name") or "", d.get("address_name") or "", d.get("x"), d.get("y"))
        if one:
            out.append(one)
        if len(out) >= _MAX:
            break
    return out


def search(query: str) -> list:
    """카카오 로컬 주소 검색 → 0개면 키워드 검색. 최대 5개. 실패하면 빈 목록(예외 없음)."""
    q = (query or "").strip()
    if not q:
        return []
    key = (keystore.get("kakao_rest_api_key") or "").strip()
    if not key:
        return []
    headers = _headers(key)
    try:
        r = httpx.get(_ADDR_URL, headers=headers, params={"query": q}, timeout=_TIMEOUT)
        if r.status_code != 200:
            return []
        docs = r.json().get("documents") or []
        found = _from_address(docs)
        if found:
            return found
        r = httpx.get(_KEYWORD_URL, headers=headers, params={"query": q}, timeout=_TIMEOUT)
        if r.status_code != 200:
            return []
        return _from_keyword(r.json().get("documents") or [])
    except Exception:
        log.warning("주소 검색 실패(통신)")
        return []


# 시청 주소표 (시 17개). 좌표는 시청 위치다.
_CITIES = (
    (("서울", "서울시"), "서울특별시 중구 세종대로 110", 126.9784, 37.5668),
    (("부산", "부산시"), "부산광역시 연제구 중앙대로 1001", 129.0756, 35.1796),
    (("대구", "대구시"), "대구광역시 중구 공평로 88", 128.6014, 35.8714),
    (("인천", "인천시"), "인천광역시 남동구 정각로 29", 126.7052, 37.4563),
    (("광주", "광주시"), "광주광역시 서구 내방로 111", 126.8526, 35.1595),
    (("대전", "대전시"), "대전광역시 서구 둔산로 100", 127.3845, 36.3504),
    (("울산", "울산시"), "울산광역시 남구 중앙로 201", 129.3139, 35.5395),
    (("세종", "세종시"), "세종특별자치시 한누리대로 2130", 127.2893, 36.4800),
    (("경기", "경기도"), "경기도 수원시 영통구 도청로 30", 127.0097, 37.2880),
    (("강원", "강원도"), "강원특별자치도 춘천시 중앙로 1", 127.7300, 37.8857),
    (("충북", "충청북도"), "충청북도 청주시 상당구 상당로 82", 127.4917, 36.6357),
    (("충남", "충청남도"), "충청남도 홍성군 홍북읍 충남대로 21", 126.6513, 36.6358),
    (("전북", "전라북도"), "전북특별자치도 전주시 완산구 효자로 225", 127.1088, 35.8205),
    (("전남", "전라남도"), "전라남도 무안군 삼향읍 오룡길 1", 126.4645, 34.8166),
    (("경북", "경상북도"), "경상북도 안동시 풍천면 도청대로 455", 128.7436, 36.4919),
    (("경남", "경상남도"), "경상남도 창원시 의창구 중앙대로 300", 128.6811, 35.2377),
    (("제주", "제주도"), "제주특별자치도 제주시 문연로 6", 126.5003, 33.4894),
)

# 서울 구청 주소표 (25개). 말에 구 이름이 있으면 시청보다 먼저 둔다.
_GUS = (
    (("종로구", "종로"), "서울특별시 종로구 삼봉로 43", 126.9782, 37.5733),
    (("중구",), "서울특별시 중구 창경궁로 17", 126.9975, 37.5641),
    (("용산구", "용산"), "서울특별시 용산구 녹사평대로 150", 126.9909, 37.5326),
    (("성동구", "성동"), "서울특별시 성동구 고산자로 270", 127.0371, 37.5634),
    (("광진구", "광진"), "서울특별시 광진구 자양로 117", 127.0825, 37.5385),
    (("동대문구", "동대문"), "서울특별시 동대문구 천호대로 145", 127.0560, 37.5838),
    (("중랑구", "중랑"), "서울특별시 중랑구 봉화산로 179", 127.0926, 37.6063),
    (("성북구", "성북"), "서울특별시 성북구 보문로 168", 127.0167, 37.6024),
    (("강북구", "강북"), "서울특별시 강북구 도봉로89길 13", 127.0255, 37.6392),
    (("도봉구", "도봉"), "서울특별시 도봉구 마들로 656", 127.0472, 37.6688),
    (("노원구", "노원"), "서울특별시 노원구 노해로 437", 127.0565, 37.6544),
    (("은평구", "은평"), "서울특별시 은평구 은평로 195", 126.9270, 37.6176),
    (("서대문구", "서대문"), "서울특별시 서대문구 연희로 248", 126.9391, 37.5791),
    (("마포구", "마포"), "서울특별시 마포구 월드컵로 212", 126.9083, 37.5638),
    (("양천구", "양천"), "서울특별시 양천구 목동동로 105", 126.8658, 37.5169),
    (("강서구", "강서"), "서울특별시 강서구 화곡로 302", 126.8495, 37.5509),
    (("구로구", "구로"), "서울특별시 구로구 가마산로 245", 126.8874, 37.4955),
    (("금천구", "금천"), "서울특별시 금천구 시흥대로73길 70", 126.9026, 37.4566),
    (("영등포구", "영등포"), "서울특별시 영등포구 당산로 123", 126.9102, 37.5264),
    (("동작구", "동작"), "서울특별시 동작구 장승배기로 161", 126.9396, 37.5124),
    (("관악구", "관악"), "서울특별시 관악구 관악로 145", 126.9517, 37.4782),
    (("서초구", "서초"), "서울특별시 서초구 남부순환로 2584", 127.0325, 37.4836),
    (("강남구", "강남"), "서울특별시 강남구 학동로 426", 127.0366, 37.5172),
    (("송파구", "송파"), "서울특별시 송파구 올림픽로 326", 127.1073, 37.5145),
    (("강동구", "강동"), "서울특별시 강동구 성내로 45", 127.1238, 37.5302),
)


def placeholder(query: str) -> dict:
    """말에 시·구 이름이 있으면 그 시·구청, 없으면 서울시청. 빈칸 표시용이다."""
    q = (query or "").strip()

    def out(road, x, y):
        return {"road": road, "jibun": "", "detail": "", "x": x, "y": y, "src": "placeholder"}

    # 말에서 먼저 나온 시·도를 고른다 ("경기 광주" → 경기도, "부산 강서구" → 부산)
    hits = [(min(q.find(k) for k in keys if k in q), road, x, y)
            for keys, road, x, y in _CITIES if q and any(k in q for k in keys)]
    city = min(hits)[1:] if hits else None
    # 서울 구 이름(중구·강서 등)은 다른 도시에도 있어, 서울이거나 시·도를 말하지 않았을 때만 본다
    if city is None or city[0] == _CITIES[0][1]:
        for keys, road, x, y in _GUS:
            if q and any(k in q for k in keys):
                return out(road, x, y)
    if city is not None:
        return out(*city)
    return out(*_CITIES[0][1:])
