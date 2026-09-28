# 1·2주차 구현 계약·작업판 (BUILD_W1_W2)

> 2026-09-28 (KST). 대표 결정 D54: UI_AGENT_PLAN 권장안(U1~U6) 그대로, 색은 A(에스프레소·테라코타) 방향, **계획·계약·검토는 Claude, 구현은 OpenCode**.
> 이 문서는 OpenCode 작업의 기준이다. 계약(§1)을 바꾸려면 Claude와 먼저 합의한다. 작업(§2·§3)은 "소유 파일"만 고친다.
> 상위 문서: [UI_AGENT_PLAN](UI_AGENT_PLAN.md) · [DESIGN_FIT_PLAN](DESIGN_FIT_PLAN.md) · [SECTION_LIBRARY_SPEC §2.9](SECTION_LIBRARY_SPEC.md) · [MOTION_PLAN](MOTION_PLAN.md)

## 0. 운영 방식

| 항목 | 내용 |
|---|---|
| 역할 | Claude: 계약·작업 지시·검토·전체 테스트·커밋. OpenCode(`opencode/muse-spark-1.3-contributor-free`): 작업 하나씩 구현 + 자기 테스트 |
| 순서 | 물결(wave) 단위. 같은 물결의 작업은 소유 파일이 겹치지 않아 동시에 돈다. 물결이 끝나면 Claude가 검토하고 전체 테스트를 돌린 뒤 다음 물결을 시작한다 |
| 금지 (모든 작업) | `.env`·비밀 값 읽기 / git add·commit·push / SSH·서버·Docker 상태 바꾸기 / 배포·되돌리기 스크립트 실행 / 패키지 설치 / 소유하지 않은 파일 수정·삭제 / 문서에 한국어·영어 외 문자(일본어·중국어 낱말) 쓰기 |
| 자기 검증 | DB가 필요 없는 테스트만 돌린다: `tests/engine`, `pytest --noconftest tests/unit/<자기 파일>`, `scripts/draft_score.py`, `scripts/draft_fit.py`. DB가 필요한 전체 테스트는 Claude가 돌린다 |
| 보고 | 끝나면 마지막 출력에 ① 바꾼 파일 ② 돌린 명령과 결과(통과 수·실패 수) ③ 계약과 다르게 한 점과 이유를 쓴다 |

## 1. 계약

### 1.1 카드 구조 데이터 `card["data"]` (C-1)

`app/services/card_data.py`의 `build(card) -> dict`가 만든다. 카드 칸(`slots`)·상황 답(`card["situation"]`)·가격 짝(`card["price_pairs"]`)에서 **결정론으로** 계산하고, 카드가 바뀔 때마다 다시 계산한다. LLM을 부르지 않는다.

```json
{
  "version": 1,
  "mode": "dinein | pickup | solo | team | ''",
  "primary_action": "visit | order | reserve | consult | apply | inquire",
  "catalog": [
    {"name": "커피", "source": "owner | assumed",
     "items": [{"name": "아메리카노", "price": "4,500원", "desc": "", "source": "owner"}]}
  ],
  "staff": [{"name": "김미용", "role": "원장", "specialties": ["컷"], "source": "owner"}],
  "classes": [], "rooms": [],
  "schedule": null
}
```

| 칸 | 규칙 |
|---|---|
| `catalog` | 품목 = `offerings`(FILLED·ASSUMED). 가격 = `card["price_pairs"][품목]`(없으면 `""`). 분류는 업종별 낱말표로 **가정**(source=assumed): 카페 = 커피(아메리카노·라떼·에스프레소·콜드브루·드립·카푸치노) / 음료(에이드·티·차·주스·스무디, 그리고 딸기·녹차·초코·고구마가 붙은 라떼) / 디저트(케이크·쿠키·휘낭시에·마카롱·빵·스콘·와플·크로플). 미용실 = 컷 / 염색(염색·컬러·탈색) / 펌(펌·매직·볼륨) / 케어(클리닉·두피·트리트먼트). 어느 분류에도 없으면 `"메뉴"`(미용실은 `"시술"`). 품목이 없으면 `[]` |
| `staff` | `staff` 칸 값 "원장 김미용(컷·펌)" → role=원장, name=김미용, specialties=[컷, 펌]. 직함 낱말: 원장·실장·부원장·디자이너·선생님·강사·대표·팀장 |
| `mode` | 원형 A: `situation.order_mode`가 pickup이면 `pickup`, 아니면 `contact_method`에 픽업·주문이 있으면 `pickup`, 그 외 `dinein`. 원형 B: `situation.team_mode` 우선, 없으면 staff 2명 이상 → `team`, 그 외 `solo` |
| `primary_action` | A-dinein → visit, A-pickup → order, B → reserve, C → reserve, D → consult, E → apply, F·G·H → inquire |
| `classes`·`rooms`·`schedule` | 1주차는 빈 값. 2주차 J7·J5b가 채운다 |

**가격 짝 보존 (근본 수정)**: `prd_engine`에서 `_separate_menu_price`를 부르기 **전에**, 같은 조건(메뉴·가격 둘 다 사장님 말에 있음)으로 `(메뉴, 가격)` 짝을 뽑아 `card["price_pairs"]`(dict, 나중 값이 앞 값을 덮음)에 넣는다. `_separate_menu_price`의 시그니처와 동작은 바꾸지 않는다.

### 1.2 원형·모드 `archetype.of(card)` (C-5)

`app/services/archetype.py`: `of(card) -> tuple[str, str]` = (원형 글자, 모드). 업종 키 → 원형: cafe·restaurant → A, salon → B, pension → C, academy → D, workshop → E, individual → F, group → G, webservice → H, other → A(1주차 임시, 2주차 J11이 LLM 판정). 모드는 `card_data.build(card)["mode"]`. `blueprint(card) -> dict | None`은 `templates/blueprints/<원형>-<모드>.json`이 있으면 읽고, 없으면 `<원형>.json`, 그것도 없으면 None(기존 경로).

### 1.3 청사진 `templates/blueprints/*.json` (C-2)

```json
{
  "archetype": "A", "mode": "dinein",
  "primary": {"label": "길찾기", "target": "around"},
  "secondary": {"label": "메뉴 보기", "target": "menu"},
  "actionbar_secondary": "phone | around | none",
  "tokens": {"font_pair": "serif-warm", "density": "comfortable", "radius": "soft", "image_style": "card"},
  "strategies": [
    {"id": "v1", "name": "메뉴판형", "journey": "메뉴 보고 → 길찾기", "tone": "calm",
     "hero": "photo-overlay",
     "sections": [
       {"id": "menu", "type": "offerings", "variant": "categories", "bind": "catalog", "label": "메뉴", "nav": "메뉴"},
       {"id": "space", "type": "gallery", "variant": "swipe", "bind": "space_photos", "label": "공간", "nav": "공간", "tone": "inverse"},
       {"id": "around", "type": "around", "variant": "map", "bind": "location", "nav": "오시는 길"},
       {"id": "contact", "type": "contact", "variant": "call-first", "bind": "contact"},
       {"id": "inquiry", "type": "contact", "variant": "form", "bind": "none"}
     ]}
  ]
}
```

| 규칙 | 내용 |
|---|---|
| 전략 수 | 정확히 3개(v1 정석·v2 분위기·v3 대비, D43). 전략마다 **두 번째 섹션이 서로 달라야 한다**(`draft_fit.strategy_distinct`) |
| 첫 화면 | 모든 전략에 hero가 맨 앞에 자동으로 붙는다. `hero`는 변형 이름 |
| `target` | 섹션 id. 리졸버가 `#<type>-title-<id>`로 바꾼다. 특수 값 `order-soon` → `#order-soon` |
| `tone` | 섹션: `inverse`는 페이지당 최대 1개(짙은 띠). 전략: `calm`(짙은 띠 없음 → inverse 무시) / `rich` |
| `nav` | 있으면 상단 내비 링크(최대 4개, 순서대로) |
| 1주차 파일 | `A-dinein.json`, `A-pickup.json`, `B-solo.json`, `B-team.json` (정답 시안 `evals/fit_gold/*.json`의 구성을 따른다) |

### 1.4 바인딩과 리졸버 `site_data.resolve()` (C-3, C-4)

`app/services/site_data.py`:

```python
def skeleton(blueprint: dict, strategy_index: int) -> dict        # 청사진 → content 비어 있는 명세(hero 포함, bind·tone 유지)
def resolve(spec: dict, card: dict, *, archetype: str, mode: str = "draft") -> dict   # bind → content 채움 + navbar·actionbar
```

| bind | 채우는 content | 시안(draft)에서 빈 값 |
|---|---|---|
| `hero` | title=가게 이름, subtitle=`detail` → `copy.tagline`, facts=영업·위치, image=사장님 사진 → AI 예시 → 예시 팩, cta=primary, cta2=secondary | 예시 팩 사진 + `ai_example` |
| `catalog` | `offerings--categories`: `card["data"]["catalog"]` → categories. 분류 사진 = 예시 팩의 `category:<이름>` | 가격 없음 → 예시 파일의 `prices`에서 이름 낱말이 맞는 값 + `price_example: true`. 맞는 값이 없으면 `""`(자리 표시). 품목이 0개면 예시 파일 `catalog`를 전부 `example: true`로 |
| `staff` | team/solo: `card["data"]["staff"]` → members(`booking_href` = `#booking-title-booking`) | 사진 없음 → 예시 팩 `staff:<순번>` + `image_example`. 사람이 0명이면 예시 파일 `staff`를 `example: true`로 |
| `booking` | `booking--slots`: staff 이름, services = 품목 이름, service_label | `days` = 예시 현황(오늘 KST 다음 날부터 5일, 영업시간을 읽을 수 있으면 그 범위, 아니면 10~18시) + `days_example: true` |
| `location` | `around--map`: address = `location`(FILLED만) | 없음(자리 표시) |
| `contact` | phone·hours(FILLED만) | 없음 |
| `space_photos`·`style_photos` | 사장님 사진(대표 제외) → 예시 팩 `space:*`/`style:*` | 예시 팩 + `ai: true` |
| `order_soon` | `order--soon`: phone, return_href = 메뉴 섹션 | — |
| `none` | 그대로 | — |

- **사실은 지어내지 않는다(D26)**: 이름·전화·주소·영업시간은 FILLED 칸만 쓴다. 예시로 채운 값에는 반드시 `*_example`/`example`/`ai` 표시를 붙인다(D53①).
- navbar = {title, top, links(nav 순서), cta = primary}, actionbar = {primary, secondary(phone이면 FILLED 전화 `tel:`, 없으면 around 섹션)}.
- 공개본의 예시 제거는 기존 `render_site(public=True)`의 `_drop_examples`가 한다. `resolve`는 모드와 상관없이 같은 값을 넣는다(2주차 계산 값만 모드로 갈린다).

**예시 파일 `templates/examples/<원형>.json`** (C-4):

```json
{
  "photos": {"hero": "/art/ex/cafe-hero.webp", "category:커피": "/art/ex/cafe-coffee.webp",
             "category:음료": "/art/ex/cafe-drink.webp", "category:디저트": "/art/ex/cafe-dessert.webp",
             "space:1": "/art/ex/cafe-space.webp", "space:2": "/art/ex/cafe-hero.webp"},
  "prices": {"아메리카노": "4,500원", "라떼": "5,000원", "에이드": "5,500원", "케이크": "6,500원", "휘낭시에": "3,000원"},
  "catalog": [{"name": "커피", "items": [{"name": "아메리카노", "price": "4,500원"}]}],
  "staff": []
}
```

B는 `salon-*` 사진, 가격(컷 2만원·염색 8만원·펌 10만원·클리닉 4만원), `staff:1~3` = `salon-style2/3/1`.

### 1.5 색 시스템 (C-6, D54: A는 '유일한 색'이 아니라 '규칙')

**팔레트 규칙** (OKLCH, 모두 통과해야 목록에 들어간다): 주색 채도 ≥ 0.10 또는 밝기 ≤ 0.30(의도한 짙은 무채색) / 강조색 색상각이 주색과 90° 이상 차이(주색이 짙은 무채색이면 강조색 채도 ≥ 0.12) / 바탕 채도 ≤ 0.012 / 대비: 글자·바탕 ≥ 7, 주색·바탕 ≥ 4.5, 강조색·바탕 ≥ 4.5, 흰색·강조색 ≥ 4.5.

**팔레트 13종** (`templates/tokens/palettes.json`. 기존 8개 이름은 유지하고 값만 교체, 5개 추가. 2026-09-28 Claude가 규칙 통과 확인):

| 이름 | primary | accent | ground | ink |
|---|---|---|---|---|
| espresso (A) | #292524 | #c2410c | #f5f3ef | #1c1917 |
| cobalt (B) | #1d4ed8 | #b45309 | #f7f6f2 | #0f172a |
| evergreen (C) | #047857 | #be185d | #f5f5f0 | #122019 |
| ink-rose | #1c1917 | #be123c | #f8f5f4 | #1c1917 |
| plum | #6b21a8 | #0f766e | #f7f5f8 | #1e1526 |
| coffee | #3a2618 | #0e7490 | #f6f3ee | #1f1712 |
| forest | #166534 | #c2410c | #f4f5f0 | #14201a |
| moss | #3f6212 | #9d174d | #f5f5ef | #1a2010 |
| sage | #1c2b25 | #c2410c | #f3f6f5 | #132421 |
| brick | #9a3412 | #0f766e | #faf6f3 | #241712 |
| tomato | #b91c1c | #15803d | #fdf7f5 | #261414 |
| navy | #1e3a8a | #c2410c | #f5f7fb | #111827 |
| charcoal-gold | #18181b | #a16207 | #fafaf9 | #18181b |

**원형별 팔레트** (`app/services/palette.py`의 `ARCHETYPE_PALETTES`, 첫 값 = ① 기본, 마지막 지정 = ③ 대비 우선):

| 원형 | ① 정석 | ② 분위기 후보 (사장님 말·사진 색으로 고름) | ③ 대비 |
|---|---|---|---|
| A | espresso | coffee, evergreen, brick, tomato | cobalt |
| B | charcoal-gold | ink-rose, sage, espresso | plum |
| C | forest | evergreen, moss, sage | navy |
| D | navy | cobalt, evergreen, plum | tomato |
| E | moss | brick, coffee, sage | plum |
| F | sage | ink-rose, charcoal-gold, espresso | cobalt |
| G | evergreen | navy, moss, brick | tomato |
| H | cobalt | plum, navy, evergreen | tomato |

`palette.py` API: `check(name) -> list[str]`(규칙 위반 목록) · `pick(archetype, role, mood=None, used=()) -> str`(role 1·2·3. ②는 mood가 후보에 있으면 그 값, 아니면 used에 없는 첫 후보) · `library() -> list[str]`.

**색 역할 CSS** (`templates/site.css` 끝에 추가): `--ground-soft` = 주색 9% + 바탕(oklch 섞기), `--line` = 주색 18% + 바탕, `--card` = 바탕 35% + 흰색, `--inverse` = 주색의 밝기 0.25·채도 최대 0.08(상대 색 문법 `oklch(from var(--c-primary) 0.25 min(c, 0.08) h)`, 모르는 브라우저는 `color-mix(in oklch, var(--c-primary) 70%, #000)`). `section[data-tone="inverse"]`는 배경 `--inverse` 전체 너비 띠(기존 띠처럼 `box-shadow 100vmax` + `clip-path`), 글자·제목·캡션 흰색, 안의 버튼은 흰 바탕·짙은 글자. 분류 제목(`.s-menu__cat`)은 주색, 분류 칩 바탕은 `--ground-soft`.

**렌더러 연결** (C1 작업): 섹션에 `"tone": "inverse"`가 있으면 그 섹션 뿌리 요소에 `data-tone="inverse"`를 붙인다.

### 1.6 상황 탐색 (C-7, D53③, 2물결)

`prd_schema`에 칸 3개를 추가한다(사실 칸 아님, 질문 한도 밖): `team_mode`(혼자·2~3명·4명 이상), `order_mode`(매장 방문·주문 앱 링크·픽업 주문), `menu_categories`(분류 이름 목록). `app/services/situation.py`의 `probe(card) -> list[dict]`는 LLM(`app.llm.chat_json`, 12초·300토큰)에게 "이 원형에서 아직 모르는 것 중 시안을 바꾸는 것"을 허용 목록에서 0~3개 고르게 하고, 엔진이 검증(허용 목록·이미 채운 칸 제외·선택지 3개 이하)한다. LLM이 실패하면 원형별 기본표(A: order_mode, menu_categories / B: team_mode / 그 외 없음)를 쓴다. 고른 질문은 기존 `card["followup_queue"]`에 `{"slot", "text", "options", "budget_free": true}`로 넣고, 질문 한도를 세지 않는다.

### 1.7 2주차 새 부품 계약 (C-8)

| type--variant | content | 비고 |
|---|---|---|
| `classes--cards` | `label`, `cta_href`(#), `classes:[{name*, target, days, time, capacity, fee, fee_example, level, desc, example}]`(≤12) | 카드: 대상 칩, "월·수 16:00", 정원 "8명", 수강료(예시 표시), "상담 신청" 링크 |
| `timetable--week` | `label`, `days[]`(예: 월~토), `rows:[{time*, cells:[{day, text}]}]`(≤12행), `example` | `<table>`. 휴대폰은 첫 열 고정 + 가로 넘김. `<caption>` 필수 |
| `rooms--cards` | `label`, `booking_href`, `rooms:[{name*, image, image_example, capacity, size, price, price_example, features[], example}]`(≤8) | 사진 3:2, 인원·평형·요금(예시 표시)·편의 칩, "이 객실 예약" |
| `booking--dates` | `label`, `note`, `rooms[]`, `nights_max`(기본 3), `days:[{date*, label, dow, state open/few/full}]`(≤21), `days_example` | 라디오 `name="date"`(입실일), 객실 `service` 고르기, 박 수 `nights`, 인원 `party`. `days` 없으면 날짜 입력. API: `nights`를 받으면 service 뒤에 " · N박"을 붙인다 |

CSS는 `templates/css/40-w2-parts.css`(새 폴더). `site_render._bundle`이 `site.css` 뒤에 `templates/css/*.css`를 이름순으로 붙인다.

## 2. 1주차 (9/28~10/4)

### 1물결 (9/28 시작, 동시에)

| 작업 | 내용 | 소유 파일 | 완료 확인 |
|---|---|---|---|
| **J1a** 구조 데이터 | §1.1 전부: `card_data.build`, 가격 짝 보존 | `app/services/card_data.py`(새), `app/services/prd_engine.py`(가격 짝 추가 부분만), `tests/engine/test_card_data.py`(새) | `pytest tests/engine` 통과. 카페·미용실 예로 catalog 분류·가격 짝·staff 파싱 테스트 |
| **J2** 색 시스템 | §1.5 전부: palettes.json 교체·추가, `palette.py`, 역할 CSS, `draft_score`에 `palette_rules_fail`(0 기준)·`inverse_contrast`(흰 글자·inverse ≥ 7) | `templates/tokens/palettes.json`, `app/services/palette.py`(새), `templates/site.css`(끝에 추가만), `scripts/draft_score.py`, `tests/unit/test_palette.py`(새) | `draft_score` 23/23 PASS, `pytest --noconftest tests/unit/test_palette.py tests/unit/test_site_render.py tests/unit/test_fit_components.py` 통과 |
| **J3** 리졸버 | §1.4 전부 + 예시 파일 A·B | `app/services/site_data.py`(새), `templates/examples/A.json`·`B.json`(새), `tests/unit/test_site_data.py`(새) | `pytest --noconftest tests/unit/test_site_data.py`. `evals/fit_gold`의 카페·미용실과 같은 구성이 `skeleton+resolve`로 나오고 `render_site` 통과 |
| **J4** 원형·청사진 | §1.2·§1.3: `archetype.py`, 청사진 4개 | `app/services/archetype.py`(새), `templates/blueprints/*.json`(새), `tests/engine/test_archetype.py`(새) | 청사진마다 type--variant가 `site_render.list_variants()`에 있고, bind가 §1.4 목록 안, 전략 3개·두 번째 섹션이 서로 다름 |
| **C1** 2주차 부품 | §1.7 전부 + `data-tone` 연결 + CSS 폴더 불러오기 + API `nights` | `templates/sections/{classes--cards,timetable--week,rooms--cards,booking--dates}.mustache`(새), `templates/css/40-w2-parts.css`(새), `app/services/site_render.py`, `app/api/bookings.py`, `tests/unit/test_fit_components_w2.py`(새), `tests/unit/test_site_render.py`(부품 개수 줄만), `docs/product/SECTION_LIBRARY_SPEC.md`(§2.10 추가) | `pytest --noconftest tests/unit/test_fit_components_w2.py tests/unit/test_fit_components.py tests/unit/test_site_render.py`. 부품마다 4상태(채움·예시·빈칸·공개) 테스트 |

### 2물결 (1물결 검토 뒤, ~10/1)

| 작업 | 내용 | 소유 파일 | 완료 확인 |
|---|---|---|---|
| **J5** 엔진 연결 A·B | `design_variants.variants()`: 청사진이 있으면 `skeleton → resolve`로 3안, 팔레트는 `palette.pick`(①②③), 없으면 기존 경로. 안 이름·요약 = 전략 name·journey. `draft_corpus.build_card`가 `card_data.build`를 부르게. 기존 테스트 기대값 갱신 | `app/services/design_variants.py`, `scripts/draft_corpus.py`, `scripts/draft_fit.py`(필요 시), `tests/unit/test_design_variants.py` | `draft_fit` A·B 4건 전 항목 PASS, `draft_score` 전부 PASS |
| **J1b** 상황 탐색 | §1.6 | `app/services/prd_schema.py`, `app/services/prd_engine.py`, `app/services/situation.py`(새), `tests/engine/test_situation.py`(새) | LLM 흉내(mock)로 선택·검증·폴백 테스트. 질문 한도가 늘지 않음 |
| **G1** 정답 시안 C·D | 학원 2장(반·시간표형, 상담 우선형)·펜션 1장을 C1 부품 + 새 예시 사진(`/art/ex/academy-*`, `pension-*`)으로 | `evals/fit_gold/academy-*.json`·`pension.json`(새) | `render_fit_gold.py`로 렌더, 4너비 넘침 0 → **대표 승인** |

**1주차 완료 기준**: 채팅으로 만든 카페·미용실 시안이 정답 시안 수준(Claude가 캡처로 확인), `draft_fit` A·B PASS, 전체 테스트(DB 포함) 통과.

## 3. 2주차 (10/5~10/11)

### 3물결

| 작업 | 내용 | 소유 파일 | 완료 확인 |
|---|---|---|---|
| **J5b** 엔진 연결 C·D | 청사진 `C.json`·`D.json`, 예시 파일 C·D, `card_data`에 classes·rooms 구조화(말로 한 목록 → 결정론 파싱: "초등 파닉스반 월수 4시 8명 18만원"), 코퍼스 학원·펜션 3건씩 | `templates/blueprints/C*.json`·`D*.json`, `templates/examples/C.json`·`D.json`, `app/services/card_data.py`, `scripts/draft_corpus.py`, `tests/engine/test_card_data.py` | `draft_fit` C·D PASS |
| **J7** 예약 현황 계산 | `schedule` 구조화(영업시간 글 → 요일별, 모르면 ASSUMED 10~18시·60분·1명), `site_data`에 공개 모드 계산(오늘~14일 KST, 확정 예약 뺌, 담당자별), 예약 확정·취소 때와 매일 00:05 KST에 공개본 다시 그리기 | `app/services/card_data.py`(schedule 부분), `app/services/site_data.py`(계산 부분), `app/services/bookings.py`(decide 뒤 호출), 공개본 다시 그리기 함수가 있는 파일, `tests/unit/test_availability.py`(새, DB 사용) | 휴무·마감·담당자별·날짜 넘어감 테스트 |
| **J9** 데이터 연결표 | `feature_catalog.json` 42개에 `components`·`binding`·`resource` 칸 + 불러오기 검증 + `ready_components(archetype)` | `app/data/feature_catalog.json`, `app/services/intake.py`(불러오기 부분), `tests/engine/test_feature_bindings.py`(새) | 모든 components가 실제 부품, out_of_beta는 대안 부품 |

### 4물결

| 작업 | 내용 | 소유 파일 | 완료 확인 |
|---|---|---|---|
| **J11** UI 에이전트 | UI_AGENT_PLAN §4: `ui_agent.improve(card, variants) -> variants`. 도구 T1~T6은 파이썬 함수, LLM은 지금 NIM(U2: D39 뒤 교체). 고칠 수 있는 것 = 청사진이 허용한 순서·선택 섹션·제목(12자)·부제(숫자는 카드에 있는 것만)·톤·팔레트 후보. 반복 2회·20초·실패 시 규칙 안. `other` 업종 원형 판정. chat_flow: 규칙 3안을 먼저 보내고, 개선 안이 오면 "시안을 더 다듬었어요"로 교체(U3). 자유 코드 생성 `codegen.start`는 설정값으로 끈다(U6, 기본 끔) | `app/services/ui_agent.py`(새), `app/services/archetype.py`(LLM 판정 추가), `app/services/chat_flow.py`, `app/config.py`(설정 1개), `tests/engine/test_ui_agent.py`(새) | 코퍼스에서 개선 안의 draft_fit·draft_score가 규칙 안보다 낮지 않음, 숫자 지어내기 0, 시간 초과 시 규칙 안 유지 |
| **J2b** 사진에 맞춘 색 | 대표 사진 주요 색(PIL) → ② 후보 중 색상각이 가까운 팔레트 | `app/services/palette.py`, `tests/unit/test_palette.py` | 사진 3종 예로 선택 테스트 |
| **G2** 코퍼스 확대 | 원형 A~D 각 3건 이상 + 처음 보는 업종 30개 원형 판정 표 | `scripts/draft_corpus.py`, `evals/archetype_cases.json`(새) | 원형 판정 90% |

**2주차 완료 기준**: 학원·펜션 정답 시안 대표 승인 + `draft_fit` C·D PASS, UI 에이전트가 규칙 안보다 채점이 낮지 않음, 공개본 예약 현황이 확정 예약을 반영.

## 4. 일정 요약

| 날짜 (KST) | 물결 | 작업 |
|---|---|---|
| 9/28~9/30 | 1 | J1a · J2 · J3 · J4 · C1 |
| 10/1~10/4 | 2 | J5 · J1b · G1 → 1주차 완료 확인 |
| 10/5~10/8 | 3 | J5b · J7 · J9 |
| 10/8~10/11 | 4 | J11 · J2b · G2 → 2주차 완료 확인 |
| 10/12~10/15 | 3주차 | 보고 고치기, E·F 최소, 동결(D47) |

## 5. 진행 기록

### 1물결 (2026-09-28 완료)

| 작업 | 결과 | Claude 검토 |
|---|---|---|
| J1a | `card_data.build`, 가격 짝 보존. 엔진 테스트 232개 통과 | **기존 버그 발견·수정**: `_split_items`가 천 단위 쉼표를 잘라 "아메리카노 4,500원" → "아메리카노 4" + "500원"이 되던 문제(숫자 사이 쉼표는 나누지 않게) |
| J2 | 팔레트 13종, `palette.py`, 색 역할 CSS, `draft_score` 색 항목 2개 → 23/23 PASS | 강조색 규칙은 "색상각 90° 이상 **또는** (짙은 무채색 주색 + 강조색 채도 0.12 이상)"으로 해석(Claude 검증과 같음). 옛 forest 값을 기대하던 테스트 1줄 갱신 |
| J3 | `site_data.skeleton/resolve`, 예시 파일 A·B, 테스트 7개 | 정답 시안의 손질(지어낸 예시 품목 추가 등)은 품목이 0개일 때만 재현. 수용 |
| J4 | `archetype.py`, 청사진 4개, 테스트 8개 | **버그 수정**: 업종을 `card["industry"]`에서 읽어 대화로 만든 카드(industry 없음)가 모두 A로 판정되던 문제 → `industry_of(card)` 사용 + 회귀 테스트. 업종→원형 표 중복을 `archetype.py` 한 곳으로. 청사진의 연락 섹션 과다·픽업 v3 안내 부품은 J5에서 고침 |
| C1 | 부품 4종(반 카드·주간 시간표·객실 카드·날짜 예약), `data-tone`, CSS 폴더, API `nights`. 4너비 넘침 0 | 수용 |

전체: 674개 통과, `draft_score` 23/23. 캡처: `static/compare/fit/wave1-gold.png`(카페 espresso·짙은 띠, 미용실 charcoal-gold·moss).
**다음에 다듬을 것**: 주색이 짙은 무채색(espresso·charcoal-gold)이면 옅은 면도 회색이 된다. 이때는 강조색을 섞는다(C3 보정).
**참고**: 9/28 01:55 다른 세션이 커밋 2개(686fe0e·48ef345)를 만들고 docs/hackathon 문서 3개 삭제를 스테이징했다. OpenCode 로그에는 git 명령이 없다.

### 2~4물결 (2026-09-28 완료분)

| 작업 | 결과 | Claude 검토 |
|---|---|---|
| J1b 상황 질문 | LLM이 허용 목록에서 0~3개 고름, 질문 한도 밖, 실패 시 기본값. 엔진 251개 통과 | **수정**: 메뉴 분류 선택지가 낱개(커피·음료·디저트)라 하나만 고르면 모든 메뉴가 한 분류로 몰림 → 분류 묶음 단위("커피·음료·디저트" 등)로 |
| G1 정답 시안 학원 2·펜션 1 | C1 부품 + 새 예시 사진 9장. 4너비 넘침 0 | 짙은 띠 버그 발견 → F1 |
| F1 짙은 띠 + 대비 검사기 | 짙은 띠가 짝수 섹션에서 옅은 띠에 지던 문제, 띠 안 흰 카드 글자 안 보임 수정. `scripts/check_contrast.py` 신설 | 검사기가 **실제 접근성 문제 190건**(옅은 띠 위 보조 글자 3.66~4.31) 발견 → 보조 글자 진하게 |
| J7 예약 현황 실계산 | `availability.py`: 영업시간 읽기, 확정 예약으로 여유·마감 임박·마감, 확정·취소 때와 날짜가 바뀐 첫 방문 때 공개본 다시 그리기(스케줄러 없음) | 수용. 한계: 다시 그릴 때 그 시점 엔진으로 그림 → 공개본 스냅숏(`site_releases`, DATA_ARCHITECTURE_REVIEW)은 오픈 전 과제 |
| J9 데이터 연결표 | 기능 42개에 components·binding·resource | 빈틈: FAQ·공지·공지 띠는 '가능'인데 부품 없음(3주차 후보). '맞춤 예약 달력' 판정 상향은 대표 확인 대기 |
| J5 엔진 연결 A·B | 카페·미용실 4건 적합성 전 항목 PASS | **근본 수정**: 한 글자 메뉴(컷·펌) 가격 짝 누락 → 엔진에 허용 목록(J5는 코퍼스에서만 메웠음, 삭제). ② 사장님 분위기 색 존중(D43), 공개본 끊긴 첫 화면 링크 제거 |
| J5b 엔진 연결 C·D + 에이전트 연결부 | 10건 × 12항목 전부 PASS. 카페 3안 '시그니처'를 대표 메뉴 카드로 | 대비 버그 2종 발견(엔진 출력) → F2 |
| J11 UI 에이전트 | `ui_agent.py`(수정 조각 검증·적용·개선 2회), 다른 업종 원형 LLM 판정, 규칙 안 먼저 → 백그라운드 다듬기, 자유 코드 생성 끔(U6) | **수정**: 다시 그릴 때 '보여 줌' 이벤트 이중 기록(D45 지표 부풂) → '다듬음' 별도 기록, 빈 수정이면 알림 없음, 테스트에서 다듬기 스레드 기본 끔, 예전 코드 생성 테스트 3개는 그 기능을 켜고 검사 |
| F2 엔진 결과물 대비 | 짙은 띠 안 안내문(1.1)·펜션 지도 버튼(4.45) 수정, 주색 글자는 `--primary-ink`. 검사 범위: 엔진 시안 60쪽 + 팔레트 13종 | 수용 |

**검증(2026-09-28)**: 전체 750개 통과, `draft_fit` 10건 × 12항목 PASS, `draft_score` 23/23, `check_contrast --palettes` 실패 0.
**운영 메모**: 테스트 DB는 여러 세션이 같이 쓴다. 07:46 교착 뒤 DB 테스트는 잠금 실행기(scratchpad `dbtest.sh`)로만 돌린다. 1주차분은 다른 세션이 07:55에 커밋(6a33c83·a7e0f65).
**남은 것**: J2b(사진에 맞춘 색), G2(코퍼스·처음 보는 업종 30개), 3주차(보고 고치기, FAQ·공지 부품, 10/15 동결).

### 4물결 마무리 (2026-09-28)

| 작업 | 결과 | Claude 검토 |
|---|---|---|
| J2b 사진에 맞춘 색 | `palette.photo_color`(6색 양자화, 무채색·너무 어둡거나 밝은 색 제외) + `pick(photo=)`. ② 우선순위: 사장님이 말한 색(규칙값과 다를 때만) → 대표 사진(사장님 사진 → AI 예시) 색 → 후보 첫 값 | 예시 사진 19장 중 15장에서 색이 잡힘(대부분 나무·베이지 H60~90 → 따뜻한 팔레트). 안개·회색 사진 4장은 후보 첫 값. 채도 기준(0.03)은 실제 사장님 사진이 쌓이면 다시 본다 |
| G2 코퍼스·원형 판정 | FIT 12건(식당·네일 추가, 원형마다 3건 이상), 처음 보는 업종 30개 표 `evals/archetype_cases.json`, 낱말표 판정 `keyword_archetype`, `scripts/archetype_eval.py` | **수정**: 꽃집이 공방 별칭 "꽃"에 걸려 클래스·체험형(E)이 되던 문제(꽃집·꽃가게·화원은 공방 제외, "클래스"가 붙으면 공방 유지). 낱말표로 정해지면 LLM 판정(8초)을 부르지 않음 |

**검증(2026-09-28, 이 세션 전용 테스트 DB `agt001_test_fit`)**: 전체 766개 통과, `draft_fit` 12건 × 12항목 PASS, `draft_score` 23/23, `check_contrast --palettes` 실패 0, 처음 보는 업종 규칙 판정 30/30.
**LLM 원형 판정(13:05)**: 낱말표에 없는 업종 30개 별도 목록 `evals/archetype_cases_llm.json`(원형마다 3~4개)로 `archetype_eval.py --llm evals/archetype_cases_llm.json` 2회 모두 30/30. 24건이 LLM 경로(24/24), 6건은 업종표가 먼저 맞힘. NIM 모델 시간 초과가 실행마다 1~4번 나 다음 모델로 넘어감 → 8초 한도 안에서 모든 모델이 실패하면 A로 떨어지므로 지연은 계속 본다.
**남은 것**: 3주차: 보고 고치기 1회, FAQ·공지 부품, 공방(E)·개인(F) 최소 청사진, 10/15 동결.

## 변경 이력

| 날짜 | 내용 |
|---|---|
| 2026-09-28 | 처음 작성 (계약 C-1~C-8, 1·2주차 작업 13개, 물결 4개) |
| 2026-09-28 | 1물결 완료·검토 기록(§5), 2물결(J5·J1b·G1) 시작 |
| 2026-09-28 | 2~4물결 검토 기록(J1b·G1·F1·J7·J9·J5·J5b·J11·F2) |
| 2026-09-28 | 4물결 마무리(J2b·G2) 기록 |
