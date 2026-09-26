# 시안 렌더러 구현 판단 기록 (작업 R1)

작성: OpenCode / 일자: 2026-09-26 / 대상: `app/services/site_render.py`

## 1. 구현 판단

- chevron 스코프 그림자 우회: 템플릿의 `{{#title}}{{title}}{{/title}}` 겹침에서
  chevron이 안쪽 `{{title}}`을 `str.title` 메서드로 찾아
  `<built-in method ...>`를 렌더하는 문제가 있었다.
  템플릿은 다른 작업 소유라 고치지 않고, 렌더러에서 문자열을 `_SafeText`
  상자로 감싸 속성 조회를 부모 스코프로 떨어뜨렸다.
  Mustache 명세상 문자열 스코프에 이름 붙은 자식은 없으므로 명세에 맞는 동작이다.
- 파생 색 대체값: `--ground-soft`·`--line`은 구형 브라우저 대체값을 먼저 두고
  `color-mix()` 선언을 뒤에 덮어쓴다. `--muted`도 같은 방식으로
  글자색 60% + 바탕색 혼합의 16진 대체값을 계산해 넣었다.
- `--focus`는 색 값(액센트)으로만 `:root`에 넣었다.
  실제 포커스 모양(3px 실선 + 2px 오프셋)은 `site.css`가 이미 `:focus-visible`에
  직접 들고 있어 렌더러에서 중복 정의하지 않았다.
- 글꼴 스택: 토큰 파일에 패밀리명만 있어
  표시용 `"표시용", "본문용", sans-serif`, 본문용 `"본문용", "Noto Sans KR", sans-serif`로
  조합했다. 둘이 같으면 표시용도 `Noto Sans KR`로 받는다.
- 주소 `map_url`·`channel_url`·`booking_url`·`kakao_channel_url`·`image_src`·`cta_href`·갤러리
  `src`는 `https://`·`tel:`·`sms:`·`mailto:`·`#`로 시작할 때만 살리고 나머지는 빈 값으로
  돌려 템플릿의 자리 표시 분기를 타게 했다.
  `asset:<id>`·상대경로도 일단 빈 값 처리한다 (아래 모호한 점 2번).
- 빈 갤러리(사진 0장)는 섹션째로 숨겼다 (SPEC §2.4).
  그 외 빈 칸은 자리 표시(`[… 입력]`)로 렌더한다.
- `title` 인자가 비면 `<title>`은 `가게 홈페이지`로 둔다.

## 2. 계약에서 모호했던 점

1. 토큰 ID 문자열 vs 객체: SPEC §0 예시는 `tokens.palette`를 객체로 적고,
   작업 지시·샘플은 전부 ID 문자열로 쓴다. 렌더러는 둘 다 받는다
   (문자열이면 표에서 찾고, 객체면 `{primary,accent,ground,ink}`로 바로 쓴다).
   이후 계약은 한쪽으로 고정해 주면 검증 코드를 단순화할 수 있다.
2. `image` 값의 해결: README §4는 `asset:<id>`·상대경로를 `image_src`로
   해결한다고 하지만, 작업 지시의 허용 목록에는 두 형식이 없어 빈 값 처리했다.
   실제 에셋 서빙 규칙(경로 접두사 등)이 정해지면 `_clean_url` 허용부에 추가하면 된다.
3. 갤러리 `alt` 초안: README는 "업종+내용 초안(예: 펜션 객실 사진 1)"이라 하지만
   렌더러는 업종을 모르므로 `가게 사진 N`으로 두었다.
   업종을 넘겨주거나(예: `render_site(..., shop_kind=...)`) 초안 규칙을 고정해 주면 맞춘다.
4. `intro--short` 빈 본문: SPEC §2.2는 "섹션을 렌더하지 않는다"고 하지만
   샘플이 전부 빈 본문으로 시작하고 시안 3안은 단수 안정이 중요해 일단 렌더했다
   (제목만 나오는 상태). 숨기기로 확정되면 `_section_context`에서 `None` 반환으로 바꾸면 된다.
5. `--focus` 형태: 색만 담을지 선언문 전체를 담을지 계약에 없어 색으로 두었다.
   `site.css`가 소비하지 않으므로 실 영향은 없다.

## 3. Claude에게 요청할 것

- 위 1~5번 확정 (특히 에셋 `image` 해결 규칙과 갤러리 `alt` 초안).
- `contact--form`·`contact--kakao-channel`의 서버 계약(§5) 변경 시 렌더러에 통보.
  지금은 `action="/api/inquiries/{{site_key}}"`·`retention_days` 표시·숨김칸 구조를
  `contact--form.mustache` 기준으로 그대로 쓴다.
- 새 `type--variant`를 쓸 때는 mustache 파일을 먼저 추가해 달라.
  없는 조합은 `SiteSpecError`로 막는다 (`list_variants()`로 22종 확인 가능).
- 삼중 중괄호·스크립트·아이프레임이 템플릿에 들어오지 않는지 계속 검사해 달라.
  렌더러는 이중 중괄호 이스케이프를 믿고 동작한다.

## 4. 결정 (Claude, 2026-09-26, BACKLOG M-5)

| # | 모호했던 점 | 결정 |
|---|---|---|
| 1 | 토큰 ID 문자열 vs 객체 | **ID 문자열로 고정.** 시안 3안(`app/services/design_variants.py`)도 ID만 바꾼다. 객체 허용은 하위 호환으로 남기되 새 코드는 쓰지 않는다 |
| 2 | `image`의 `asset:<id>`·상대경로 | **사진 올리기(P-6) 전까지 빈 값(자리 표시) 유지.** 올리기가 생기면 `/assets/<room>/<id>` 같은 우리 경로만 `_clean_url` 허용 목록에 추가한다 |
| 3 | 갤러리 `alt` 초안 | 지금은 `가게 사진 N` 유지. 사진 올리기와 함께 업종·캡션으로 만든다(P-6) |
| 4 | `intro--short` 빈 본문 | **렌더 유지**(제목만). 3안 비교에서 구성이 흔들리지 않게. 공개 전 검사(S-5)에서 빈 소개를 경고로 띄운다 |
| 5 | `--focus` 형태 | 색 값만. 모양은 `site.css`의 `:focus-visible`이 맡는다 |

## 5. 예시 그림 (작업 A1, 2026-09-26)

- 배경: 시안·공개 사이트의 사진 칸이 전부 점선 `[사진 입력]` 상자라 미완성처럼 보였다.
  저작권 문제 없는 자체 제작 SVG(`templates/illustrations/`, 업종 10종 × 대표 1 + 사진첩용 2 = 30장)로
  채우고 작게 `예시 이미지` 표시를 붙인다. 사장님 사진이 오면 그림 대신 사진이 난다.
- 그림은 글자 없음, 파일당 4KB 이내, 색은 CSS 변수(`var(--c-primary)` 등)로만 칠해
  3안마다 팔레트에 맞게 바뀐다. 외부 파일을 부르지 않고 렌더 결과에 인라인으로 넣는다
  (생성물은 sandbox·스크립트 없이 열리므로, `img` 외부 참조·data URI가 아님).
- `render_site(..., kind="<업종 키>")` 인자 추가(기본 `other`, 모르는 값도 `other`).
  `KIND_KEYS` 10종: pension, cafe, restaurant, salon, workshop, academy,
  individual, group, webservice, other.
- 대표(hero, `photo-overlay`·`photo-side`): 사진이 비었을 때 빈 자리 표시를
  인라인 그림 + `예시 이미지` 표시로 갈아끼운다. 사진이 있으면 그림을 쓰지 않는다.
  `text-only`는 사진 칸이 없어 대상이 아니다.
  mustache 파일은 다른 작업 소유라 고치지 않고, 렌더 뒤 문자열로 갈아끼웠다.
- 사진첩(gallery): 사진 0장(주소가 있는 사진이 하나도 없음)이면 숨기지 않고
  예시 그림 2장 + `사장님 사진으로 바뀌어요` 안내를 렌더한다.
  사진이 있으면 예시 그림을 쓰지 않는다. 등급은 템플릿과 같은
  `s-gallery--grid`·`s-gallery--swipe` 구조로 맞췄다.
- `_clean_url`이 우리 사진 주소 `/uploads/`로 시작하는 값도 허용한다
  (contracts/ROOM_FEATURES_API.md §4). 다른 상대경로(`/etc/...`, `../` 등)는 계속 막는다.
- 모호했던 점 §4 표의 2번·3번 후속: 사진 올리기(P-6) 전에는 예시 그림이 자리 표시를 대신하고,
  올리기가 생기면 `/uploads/` 사진이 예시 그림을 밀어낸다. 갤러리 `alt` 초안은 그대로 `가게 사진 N`.

## 6. Claude에게 요청할 것 (작업 A1 후속)

- `app/services/design_variants.py`·`app/services/design.py`에서
  `render_site`에 `kind`를 넘기는 한 줄을 붙여 달라 (소유 밖이라 손대지 않음).
  업종 키는 `design_variants._SAMPLE_FOR` 기준 10종이다.
- 새 `type--variant`를 쓸 때는 mustache 파일을 먼저 추가해 달라 (기존 §3 유지).
