# 계약서: 주소 검색·확인 + 공개 사이트 카카오 지도 (MAP_CONTRACT)

> 2026-10-01 (KST) / Claude 작성, OpenCode 구현, Claude 검토. 계획 [OWNER_FEEDBACK_1001_PLAN](OWNER_FEEDBACK_1001_PLAN.md) §4, 결정 D58 ②(베타 전, D53② 뒤집기).
> 준비 끝(10/1): 카카오 앱 agt001, JavaScript 키(코드에 이미 있음: `static/room.html`의 `KAKAO_JS_KEY`), JS SDK 도메인 `https://144.24.91.250.sslip.io`·`http://localhost:8650` 등록, 카카오맵 사용 ON(무료 쿼터 이 앱).
> 재사용: `keystore.get("kakao_rest_api_key")`(서버 전용), `httpx`, `site_render._map_links`, `templates/sections/around--map.mustache`, 공개 전 빈칸 확인(D23), 빌더 가게 정보 칸(`BuilderPage` `TOP_KEYS`의 location), 말로 고치기 되돌리기.

## 0. 결론

- **M0 결과(10/1, Claude): A 방식.** 공개 사이트와 같은 `Content-Security-Policy: sandbox …` 헤더를 단 페이지에서 카카오 지도 SDK가 정상으로 그려진다(운영 도메인·localhost·미등록 도메인 모두 타일 로드, 도메인 제한이 그리기를 막지 않음). 그래서 **공개 페이지와 편집 미리보기 안에서 바로 지도를 그린다**(지도 전용 페이지 없음).
- 주소는 서버가 카카오 로컬 API로 확인한다(REST 키는 서버 밖으로 안 나감). 후보가 여러 개면 사장님이 고르고, 못 찾으면 **임시 주소 + 안내 + 빈칸 표시**로 둔다.
- 빌더·편집기의 주소 칸 옆에 **"주소 검색"**(카카오 우편번호 서비스, 키 없음)을 둔다. 고르면 도로명과 좌표를 저장한다.
- 지도 구역: 좌표가 있으면 실제 지도, 없으면 지금 예시 지도와 링크 그대로.

## 1. 데이터

- `card["location_geo"] = {"road": str, "jibun": str, "detail": str, "x": float, "y": float, "src": "search"|"postcode"|"placeholder"}`
  - x는 경도, y는 위도.
- `location` 칸 값은 지금처럼 글자다. 표시는 `road + " " + detail`이다.
- `src == "placeholder"`이면 `location` 칸 상태를 placeholder로 둔다. 그래야 공개 전 빈칸 확인(D23)에 걸린다.
- 가게 이름·전화는 카카오에 보내지 않는다. 주소 말만 보낸다.

## 2. 서버

| 번호 | 무엇 | 파일 |
|---|---|---|
| 1 | `geo.search(query) -> list[dict]`: 카카오 로컬 주소 검색 → 결과 0개면 키워드 검색. 최대 5개 `{road, jibun, x, y}`. 시간 제한 3초, 실패하면 빈 목록(예외 없음). 키가 없으면 빈 목록 | `app/services/geo.py`(신규) |
| 2 | `geo.placeholder(query) -> dict`: 말에 시·구 이름이 있으면 그 시·구청 주소, 없으면 서울시청 주소. 시·구청 주소표는 코드 안 상수로 둔다(시 17개 + 서울 구 25개면 충분, 없으면 시청) | 같은 파일 |
| 3 | `GET /api/rooms/{id}/geo/search?q=` → `{"candidates": [...]}`. 방장만, IP·방당 1분 20번 | `app/api/card.py`(경로 1개) |
| 4 | `PUT /api/rooms/{id}/geo` `{road, jibun?, detail?, x, y, src}` → `location` 칸과 `location_geo`를 저장하고 기존 후속 처리(미리보기·공개본 다시 그리기)를 부른다. 방장만. x·y는 대한민국 범위(경도 124~132, 위도 33~39) 밖이면 400 | 같은 파일 |
| 5 | 말로 고친 주소(`set_field location`)와 채팅 추출로 `location`이 바뀌면 `geo.search(새 값)`을 부른다. 1개면 `location_geo` 저장(src=search). 여러 개면 답에 "○○, △△ 중 어디인가요?" 칩을 붙인다(빌더 SayBar 되묻기 칩, 채팅방 `#choiceBar`). 0개면 placeholder와 안내 문구(계획 §4.2의 5번) | `app/services/geo.py`의 `after_location_change(card, text) -> str \| None`(답에 붙일 한 줄). 부르는 곳은 `builder_agent.apply`와 `chat_flow`의 칸 저장 뒤에 **한 줄씩만** 더한다 |

## 3. 화면

| 번호 | 무엇 | 파일 |
|---|---|---|
| 1 | 빌더 가게 정보의 위치 칸 옆 "주소 검색" 단추 → 카카오 우편번호 서비스 창(`//t1.daumcdn.net/mapjsapi/bundle/postcode/prod/postcode.v2.js`, 누를 때만 불러옴) → 고르면 "상세 주소(층·호)" 칸 → 저장은 `PUT /geo` | `frontend/src/builder/AddressSearch.tsx`(신규), `BuilderPage.tsx`(위치 칸 옆 한 줄) |
| 2 | 우편번호 결과에 좌표가 없으므로, 고른 도로명으로 `GET /geo/search?q=도로명`을 한 번 불러 첫 후보의 x·y를 쓴다 | 같은 파일 |
| 3 | 채팅방 요약의 주소 줄 옆 "주소 검색" 단추 | `static/room.html` |

## 4. 공개 사이트·미리보기 지도 (M0 결과 A)

- 키: `settings.kakao_js_key`(기본값 = 코드에 이미 공개된 JavaScript 키 `db5e5247ff48a792df0cc393b4453c6d`, `.env`로 바꿀 수 있음). REST 키와 섞지 않는다.
- `site_data`: location 구역 content에 `geo = {"x","y"}`를 더한다. `card["location_geo"]`가 있고 `src != "placeholder"`일 때만.
- `site_render`(around, variant map): `has_geo`, `geo_x`, `geo_y`, `map_key`를 ctx에 넣는다.
- `around--map.mustache`:
  - `has_geo`면 예시 지도 대신 `<div class="s-map__live" data-x="{{geo_x}}" data-y="{{geo_y}}" role="img" aria-label="지도: {{address}}"></div>`를 둔다. 스크립트 한 덩이는 SDK를 `autoload=false`로 불러 `kakao.maps.load` 뒤 핀 하나를 찍는다(`draggable:false`, `level:3`).
  - SDK를 못 불러오면(3초 안에 `kakao` 없음) 예시 지도로 되돌린다. 예시 SVG는 `hidden`으로 남겨 두고 되돌릴 때 보인다.
  - "카카오맵에서 크게 보기" 링크는 `https://map.kakao.com/link/map/{{address}},{{geo_y}},{{geo_x}}`다.
- `has_geo`가 없으면 지금과 **똑같다**(예시 지도 + 배지 + 링크).
- `publish_check`: 외부 스크립트 금지에 `https://dapi.kakao.com/v2/maps/sdk.js?appkey=<영숫자>&autoload=false` **정확히 이 모양 한 주소만** 예외로 둔다. 다른 외부 스크립트는 그대로 막는다.
- CSS: `.s-map__live`는 `aspect-ratio: 16/10; width: 100%; border-radius: var(--radius-card)`, 앱형·넓은 화면에서도 같다.
- 누름 칸은 44px 이상, 지도 끌기 금지(페이지 스크롤 방해 방지).
- 개인정보: 좌표는 가게 주소라 공개 정보다. 손님 위치는 묻지 않는다.

## 5. 작업 묶음

| 묶음 | 누가 | 파일(소유) | 선행 |
|---|---|---|---|
| M0 | Claude | ✅ 끝(A 방식) | - |
| M1 서버 | OpenCode | `app/services/geo.py`, `app/api/card.py`(경로 2개), `tests/unit/test_geo.py` | 없음 |
| M2 지도 | OpenCode | `templates/sections/around--map.mustache`, `templates/site.css`(지도 칸), `app/services/site_data.py`(geo 한 줄), `app/services/site_render.py`(around 값만), `app/services/publish_check.py`(예외 한 줄), `app/config.py`(`kakao_js_key` 한 줄), `tests/unit/test_map_render.py` | 없음 |
| M3 화면 | OpenCode | `frontend/src/builder/AddressSearch.tsx`, `BuilderPage.tsx`, `frontend/src/editor/cardApi.ts`(함수 2개), `static/room.html`(단추 한 줄 + 창), 테스트 | M1 응답 모양만 |
| M4 말로·채팅 연결 | OpenCode | `app/services/geo.py`의 `after_location_change`, `builder_agent.py`·`chat_flow.py`에 부르는 한 줄씩, `tests/unit/test_geo.py` | M1 |

**하지 말 것**: REST 키를 화면·로그·응답에 내보내기, 가게 이름·전화를 카카오에 보내기, 손님 위치 요청, 새 의존성(httpx는 이미 있음), `publish_check`에 넓은 예외(도메인 전체 허용).

## 6. 합격 테스트

| 번호 | 테스트 |
|---|---|
| 1 | `geo.search`: 가짜 httpx로 주소 결과 → 5개까지, 주소 0개면 키워드로, 시간 초과·키 없음이면 빈 목록. 요청 본문·주소에 가게 이름·전화가 없음 |
| 2 | `geo.placeholder`: "마포구 연남동" → 마포구청, "부산" → 부산시청, 없음 → 서울시청 |
| 3 | `PUT /geo`: 방장만, 범위 밖 좌표 400, 저장 뒤 미리보기 HTML에 새 주소. placeholder면 공개 시 need=confirm |
| 4 | `after_location_change`: 1개 → 저장, 여러 개 → 되묻기 문구, 0개 → placeholder + 안내 |
| 5 | 지도 렌더: 좌표 있으면 공개본·미리보기 모두 실제 지도 칸 + SDK 한 줄 + 되돌림 예시, 좌표 없거나 placeholder면 지금과 같음. `publish_check` 통과, 다른 외부 스크립트(다른 도메인·다른 경로)는 여전히 막힘 |
| 6 | 화면: 주소 검색 → 상세 주소 → 저장 본문, 우편번호 스크립트는 누를 때만 로드 |
| 7 | Claude: 운영 배포 뒤 공개 사이트에서 실제 지도 표시 확인(390px·노트북) |

## 변경 이력

| 날짜 | 내용 |
|---|---|
| 2026-10-01 | 처음 작성 (D58 ②) |
| 2026-10-01 | M0 결과 A: 샌드박스 공개 페이지·미리보기 안에서 바로 지도(전용 페이지 없음) |
