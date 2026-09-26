# templates 사용법 (agt001-S 소유)

근거: `docs/product/SECTION_LIBRARY_SPEC.md` (§1 토큰, §2 부품 8종 20변형, §4 업종 6종).
`templates/sections/*.mustache` 20종과 `templates/site.css`는 앞선 작업에서 확정됨.
이 폴더에서 S가 소유하는 것은 `tokens/*.json`, `samples/*.json`, 이 README뿐이다.

## 1. 파일 규칙

- `tokens/palettes.json`: 팔레트 ID → `{primary, accent, ground, ink}`. SPEC §1.6 값 그대로.
  색은 16진 6자리 소문자(`#rrggbb`)만. 파생값(`--on-primary`, `--ground-soft`,
  `--line`, `--focus`, `--muted`)은 명세에 저장하지 않고 렌더러가 계산한다(§1.1).
- `tokens/font_pairs.json`: 폰트페어 ID → `{display, body, css2_url}`.
  SPEC §1.2 6종. `css2_url`은 Google Fonts 한 벌 URL, 해당 없으면(전부 Pretendard) `null`.
  한글 서브셋 + `font-display: swap` 전제.
- `tokens/density.json`: 단계 → `{pad_y, pad_y_mobile, gap, card_pad, card_gap, content_max}` (px).
  SPEC §1.3 값 그대로. `content_max`는 전 단계 720.
- `tokens/radius.json`: 단계 → `{card, btn}` (px, 알약형은 999). SPEC §1.4 값 그대로.
- `tokens/image_style.json`은 두지 않는다. `image_style`(`full-bleed`/`card`/`circle-mini`)은
  SPEC §1.5의 처리 약속이라 별도 수치 파일 없이 샘플의 `tokens.image_style` 문자열로만 참조한다.
- `samples/<pension|cafe|restaurant|salon|workshop|academy>.json`:
  `{version: 3, tokens: {palette, font_pair, density, radius, image_style}, sections: [{id, type, variant, content}], locked: []}`.
  SPEC §4 업종 기본 조합 그대로. `tokens.*`는 전부 ID 문자열(객체 아님).
  가게 사실(이름·전화·주소·가격)은 비워 둔다(D26): `title`/`phone`/`address`/`price` 계열은
  `""` 또는 `[]`로 두고, 렌더 시 템플릿의 `[… 입력]` 자리 표시가 노출된다.
  `locked`는 빈 배열로 시작한다.
- `sections[].type` / `variant`는 `templates/sections/<type>--<variant>.mustache` 파일이
  존재하는 조합만 허용한다(23종: SPEC §2 20종 + 문의 공용 2종 + 영상 1종). 새 조합을 쓰려면 먼저 mustache 파일을 만든다.
- 금지(소유 파일 공통): 삼중 중괄호, 스크립트 태그, 아이프레임 태그,
  `http:` 평문 URL 없음. 외부 링크는 `https://`만.
  폼 태그는 `contact--form` 1종에만 허용(§5 서버 계약의 일반 HTML form 전송용).
  Mustache는 `{{ }}` 이중 중괄호만 쓴다(HTML 이스케이프 유지).

## 2. 토큰 → CSS 변수 (렌더러 주입, site.css가 소비)

| 토큰 | CSS 변수 |
|---|---|
| `palette.primary/accent/ground/ink` | `--c-primary/--c-accent/--c-ground/--c-ink` |
| `font_pair` | `--font-display` (display), `--font-body` (body) |
| `density` | `--space-section` (pad_y, 모바일은 pad_y_mobile), `--space-gap` (gap), `--space-card` (card_pad) |
| `radius` | `--radius-card` (card), `--radius-btn` (btn) |

## 3. 부품별 Mustache 변수 목록 (템플릿 파일 기준, 정확히)

`id`는 전 부품 공통(섹션 id → `data-section-id`, `aria-labelledby` 접미사).
`{{#x}}…{{/x}}` / `{{^x}}…{{/x}}`는 값이 비면 자리 표시 분기로 렌더한다.
아래에 없는 키를 템플릿에 넘겨도 무시된다. 순서는 템플릿 등장 순서가 아니다.

- `hero--photo-overlay`: `id`, `image_src`, `image_alt`, `title`, `subtitle`, `cta_label`, `cta_href`
- `hero--photo-side`: `id`, `image_src`, `image_alt`, `title`, `subtitle`, `cta_label`, `cta_href`
- `hero--text-only`: `id`, `title`, `subtitle`, `cta_label`, `cta_href` (이미지 변수 없음)
- `intro--short`: `id`, `body`
- `intro--owner`: `id`, `body`, `owner_name`
- `intro--stats`: `id`, `body`, `has_stats`, `stats[].label`, `stats[].value`
- `offerings--list-price`: `id`, `label`, `has_items`, `items[].name`, `items[].desc`, `items[].price`
- `offerings--photo-grid`: `id`, `label`, `has_items`, `items[].image_src`, `items[].image_alt`, `items[].name`, `items[].desc`, `items[].price`
- `offerings--tabs`: `id`, `label`, `has_items`, `items[].name`, `items[].desc`, `items[].price`, `items[].index` (앵커 `#tab-{{id}}-{{index}}`용. `{{id}}`는 루트 섹션 id를 그대로 쓴다)
- `gallery--grid`: `id`, `items[].src`, `items[].alt`, `items[].caption`
- `gallery--swipe`: `id`, `items[].src`, `items[].alt`, `items[].caption`
- `around--map-list`: `id`, `address`, `map_url`, `has_items`, `items[].name`, `items[].note`
- `around--transit`: `id`, `address`, `map_url`, `has_items`, `items[].name`, `items[].note`
- `contact--call-first`: `id`, `phone`, `phone_digits`, `hours`, `address`
- `contact--booking-first`: `id`, `booking_url`, `phone`, `phone_digits`, `hours`, `address`
- `contact--chat-first`: `id`, `channel_url`, `phone`, `phone_digits`, `hours`, `address`
- `contact--form`: `id`, `site_key`, `retention_days` (§5 서버 계약용. SPEC §2 외 플랫폼 공용 ①)
- `contact--kakao-channel`: `id`, `kakao_channel_url` (SPEC §2 외 플랫폼 공용 ①)
- `cta--call-sms`: `id`, `phone`, `phone_digits`
- `cta--external`: `id`, `booking_url`, `phone`, `phone_digits`
- `reviews--list`: `id`, `has_items`, `items[].quote`, `items[].author`, `items[].source`
- `reviews--slot-only`: `id` (그 외 변수 없음. 고정 문구 "후기가 모이면 여기에 표시됩니다"만 렌더)
- `video--card`: `id`, `items[].url`, `items[].title`, `items[].platform`, `items[].platform_label`, `items[].thumb`

## 4. 렌더러가 넘겨야 할 파생 값

명세 content 스키마(SPEC §2) 키를 템플릿 변수로 옮기며 렌더러가 계산하는 값이다.
AI·제작물은 파생값을 직접 지정할 수 없다.

- `phone_digits`: `phone`에서 숫자만 남긴 값. `tel:`/`sms:` href 전용.
  표시 텍스트는 `phone` 원문 그대로. `phone`이 비면 `tel:`/`sms:` 링크를 걸지 않고
  `[전화번호 입력]` 자리 표시를 렌더한다(SPEC G6).
- `image_src` / `image_alt` (hero, offerings photo-grid):
  명세 content의 `image`(`asset:<id>` | 상대경로)에서 `image_src`를 해결한다.
  `image`가 비면 `image_src`를 비워 둔다 → 템플릿이 `[사진 입력]` 자리 표시를 렌더하고,
  hero는 `text-only` 폴백과 동등한 빈 상태가 된다. `image_alt` 기본값은 "가게 전경 사진"
  (gallery는 업종+내용 초안, 예: "펜션 객실 사진 1"). 장식 이미지는 `alt=""`.
- `cta_label` / `cta_href` (hero): 명세 `cta: {label, href}`에서 옮긴다.
  `href`는 `^(tel:|https://|#)`만 허용. `tel:`는 `phone_digits`로 정규화.
  `cta`가 비면 두 값을 모두 비워 CTA를 숨긴다.
- `has_items` (offerings, gallery-swipe/grid 제외, around, reviews-list):
  `items` 배열 비어 있지 여부. `false`면 `[메뉴 입력]`/`[교통 안내 입력]` 자리 카드,
  reviews는 "후기가 모이면 여기에 표시됩니다" 1줄을 렌더한다.
  gallery(grid/swipe)는 `has_items` 분기 없이 `items`를 그대로 순회한다.
  사진 0장이면 섹션을 숨긴다(SPEC §2.4).
- `has_stats` (intro-stats): `stats` 배열 비어 있지 여부.
  `false`면 `[숫자 정보 입력]` 자리 표시를 렌더한다.
- `video--card`: 유효한 영상 주소가 없으면 부품을 숨긴다(공개·시안 모두).
  유튜브(`watch`·`youtu.be`·`shorts`)는 `thumb`에 `https://i.ytimg.com/vi/<id>/hqdefault.jpg`,
  인스타그램(`reel`·`p`)·네이버TV는 `thumb` 없이 업종 색 카드 + 플랫폼 이름.
- `items[].index` (offerings-tabs 전용): 1부터 시작하는 일련번호.
  탭 앵커 `href="#tab-{{id}}-{{index}}"`와 패널 `id="tab-{{id}}-{{index}}"`에 쓴다.
- `label` 기본값 (offerings 3종): 비면 `photo-grid`/`list-price`/`tabs` 모두 "메뉴".
  샘플은 업종 표시 이름(객실/메뉴/시술/수업/반)을 명시한다.
- 토큰 파생 CSS값(SPEC §1.1, 렌더러가 `:root`에 주입):
  `--on-primary` (primary-흰색 대비 4.5:1 이상이면 `#FFFFFF`, 아니면 `#1A1A1A`),
  `--ground-soft` (`color-mix(in srgb, var(--ground) 50%, #FFFFFF)` + 구형 대체값),
  `--card` (항상 `#FFFFFF`), `--line` (`ink` 14% + `rgba()` 대체값),
  `--focus` (`accent` 3px 실선 + 2px 오프셋), `--muted` (`ink` 60%, 장식 전용).

## 5. 플랫폼 공용 ① "문의 받기" 서버 계약 요약 (구현 소유: Claude — 바꾸지 마라)

- 전송: `POST /api/inquiries/{site_key}` (`application/x-www-form-urlencoded`,
  일반 HTML form 전송 — 스크립트 불필요).
- 필드: `name`(선택, 40자), `contact`(필수, 전화 또는 이메일, 100자),
  `message`(필수, 1000자), `agree`(필수 체크 `"yes"` — 개인정보 수집 동의),
  `website`(비워 둬야 하는 스팸 방지용 숨김 칸).
- 성공: `303` → `/api/inquiries/{site_key}/done`
  (서버가 만든 "문의가 전달됐어요" 페이지, 사이트로 돌아가기 링크).
- 실패: `400` 페이지(무엇이 틀렸는지), 너무 잦으면 `429`.
- 생성 사이트는 CSP sandbox로 열리므로(`app/api/public.py` `_SITE_HEADERS`)
  두 부품은 스크립트 없이 동작해야 한다.
