# 계약서: 공지에 사진 (NOTICE_PHOTO_CONTRACT)

> 2026-10-01 (KST) / Claude 작성, OpenCode 구현, Claude 검토. 계획 [OWNER_FEEDBACK_1001_PLAN](OWNER_FEEDBACK_1001_PLAN.md) §3, 결정 D58 ①(베타 전, D55② 예외).
> 재사용: 공지 저장 `card_api.save_notice`, 공지 띠·팝업 `site_render`(D56), 사진 올리기 `POST /room/{id}/photos`(`photos.add`, 태그), 빌더 공지 시트(`BuilderPage`), 편집기 공지 칸(`CardEditor`).
> 선행: MAP_CONTRACT M1·M2·M3 커밋(같은 파일 `card.py`·`site_render.py`·`BuilderPage.tsx`를 고친다).

## 0. 결론

- 공지는 **글, 사진, 또는 둘 다**다. 둘 다 비면 공지를 끈다.
- `card["notice"] = {"text": str, "photos": [url…], "popup": bool}`. 예전 `{text, popup}`은 `photos=[]`로 읽는다.
- 사진은 1~5장이고, 이 방에 **`notice` 태그로 올린 사진만** 받는다. 공지 사진은 첫 화면·공간·메뉴 사진으로 쓰지 않는다.
- 공개 사이트:
  - 공지 띠의 "공지" 글자를 **종 아이콘**으로 바꾼다(`aria-label="공지"`, 누름 칸 44px).
  - 사진이 있으면 띠에 첫 장 작은 그림을 둔다. 띠를 누르면 팝업이 열린다.
  - 팝업은 사진을 **가로로 넘기고**(scroll-snap), 아래 점이 몇 번째인지 보인다.

## 1. 서버

| 번호 | 무엇 | 파일 |
|---|---|---|
| 1 | `photo_needs.valid_tag`: `"notice"`를 허용한다 | `app/services/photo_needs.py` |
| 2 | `photos.site_photos(card) -> list`: `card["photos"]` 중 `tag != "notice"`만 돌려준다. 사이트·시안·사진 고치기·사진 질문이 `card["photos"]`를 **사진 후보로** 읽는 곳은 모두 이것으로 바꾼다. 적어도 `design_variants.py`(191·526행 부근), `card_data.py`(248행 부근), `ai_images.py`(300행 부근), `photo_edit.py`(`_owner_urls`, 345행 부근)이고, 다른 곳도 `grep`으로 찾는다. 사진 개수 상한(`MAX_PER_ROOM`)은 전체 기준 그대로 | `app/services/photos.py` 외 |
| 3 | `save_notice(card, text, popup=False, photos=None) -> bool`: `photos`는 이 카드 `photos` 중 `tag == "notice"`인 주소만 남기고 순서를 지키며 5장까지. 글과 사진이 둘 다 비면 공지를 끈다. 결과가 같으면 False | `app/api/card.py` |
| 4 | `NoticeIn`에 `photos: list[str] = []`(최대 5). `PUT /card`의 notice 저장이 `photos`를 넘긴다 | 같은 파일 |
| 5 | 빌더 `PUT /features` `key == "notice"`: 켤 때 `text`와 `photos` 중 하나는 있어야 한다(없으면 400 "공지 글이나 사진을 넣어 주세요"). `FeatureIn`에 `photos` 추가. 칩의 `on`은 글 또는 사진이 있으면 켜짐 | `app/api/start.py` |
| 6 | `fix-targets`의 notice 칸: 글 또는 사진이 있으면 보이고, `current`는 글, 글이 없으면 "사진 N장" | `app/api/card.py` |
| 7 | `site_data`: `out["notice"] = {"text", "photos", "popup"}`. 사진 주소는 그대로 | `app/services/site_data.py` |

## 2. 공개 사이트·미리보기 (`site_render`, `site.css`)

- 띠: `<div class="s-notice" role="note">` 안에 `<button type="button" class="s-notice__open" aria-label="공지 열기">`.
  - 단추 안: 종 아이콘 SVG(`aria-hidden`), 사진이 있으면 첫 장 32px 둥근 그림, 글(없으면 "사진 공지 N장")을 둔다.
  - 글은 지금처럼 `html.escape`한다.
- 팝업: 글 + 사진 목록(`<ul class="s-notice__photos">`, `scroll-snap-type: x mandatory`, 한 장씩 `scroll-snap-align: center`, 이미지 `loading="lazy"`, `alt="공지 사진 N"`) + 점(`<ol class="s-notice__dots" aria-hidden="true">`) + 닫기.
  - 스크립트는 지금 팝업 스크립트를 넓힌다: 띠 단추를 누르면 열기, 넘길 때 점 갱신(`scroll` 이벤트, 스크립트 한 덩이).
  - `popup`이 켜져 있으면 들어올 때 한 번 연다(지금과 같음). 꺼져 있으면 띠를 누를 때만 연다.
  - 스크립트가 없으면 띠만 보인다.
- 편집 미리보기(`edit=True`)에서는 팝업을 자동으로 열지 않는다(지금과 같음). 띠를 누르면 편집 쪽 구역 선택이 먼저다.
- 사진이 없으면 글만 공지는 **지금 모양과 같다**. 종 아이콘만 바뀐다.
- 누름 칸 44px, 대비 AA, 390px에서 넘침 없음.

## 3. 화면

| 번호 | 무엇 | 파일 |
|---|---|---|
| 1 | `NoticePhotos.tsx`: 공지 사진 고르기. "사진 추가"(파일 → `uploadPhoto(…, 'notice')`, 여러 장 한 번에 가능, 합해서 5장까지), 작은 그림 목록 + 지우기(목록에서 빼기만, 파일은 안 지움) + 순서는 올린 순서 | `frontend/src/editor/NoticePhotos.tsx`(신규) |
| 2 | `uploadPhoto`가 `{id, url}`을 돌려주게 바꾼다(서버는 이미 돌려줌). 부르는 곳은 돌려받은 값을 안 써도 된다 | `frontend/src/editor/cardApi.ts` |
| 3 | 편집기 공지 칸: 글 칸 아래 `NoticePhotos`, 저장 본문 `notice: {text, popup, photos}`. 안내 문구: "글이나 사진 중 하나는 넣어 주세요" | `frontend/src/editor/CardEditor.tsx` |
| 4 | 빌더 공지 시트: 글 칸 아래 `NoticePhotos`, 켜기 본문에 `photos` | `frontend/src/builder/BuilderPage.tsx`, `frontend/src/editor/cardApi.ts`(putFeature 인자) |

## 4. 작업 묶음 (MAP M1~M3 커밋 뒤)

| 묶음 | 파일(소유) |
|---|---|
| N1 서버 | `app/services/photo_needs.py`, `app/services/photos.py`, 사진 후보를 읽는 서비스 파일들(§1-2), `app/api/card.py`, `app/api/start.py`, `app/services/site_data.py`, `tests/unit/test_notice_photos.py`(신규) |
| N2 사이트 | `app/services/site_render.py`(공지 띠·팝업만), `templates/site.css`(공지 규칙만), `tests/unit/test_notice_render.py`(신규) |
| N3 화면 | `frontend/src/editor/NoticePhotos.tsx`, `CardEditor.tsx`, `cardApi.ts`, `frontend/src/builder/BuilderPage.tsx`, 해당 테스트 |

- N2는 N1의 `site_data` 모양(§1-7)만 알면 된다. N1·N2·N3는 파일이 겹치지 않아 병렬로 할 수 있다.

**하지 말 것**: 공지 사진을 AI로 만들거나 고치기, 사진 파일 지우기, 다른 방 사진 주소 받기, 새 의존성, 공개 사이트에 외부 스크립트.

## 5. 합격 테스트

| 번호 | 테스트 |
|---|---|
| 1 | `valid_tag("notice")`, `site_photos`가 공지 사진을 뺌: 공지 사진만 올린 카드는 첫 화면·공간이 예시 사진 그대로 |
| 2 | `save_notice`: 글만·사진만·둘 다·둘 다 빔(끔), 남의 주소·태그 없는 사진 주소 버림, 6장 → 5장, 예전 `{text, popup}` 읽기 |
| 3 | `PUT /features notice`: 글·사진 없이 켜면 400, 사진만으로 켜기 가능, 칩 on |
| 4 | 렌더: 글만 공지 = 종 아이콘 + 글. 사진 공지 = 띠 작은 그림 + 팝업 사진 N장 + 점 N개. 편집 미리보기는 자동 팝업 없음. `publish_check` 통과 |
| 5 | 화면: `NoticePhotos` 올리기 → 목록 → 빼기 → 저장 본문의 `photos`, 5장 넘으면 안내 |
| 6 | Claude: 390px 공개 사이트에서 띠 → 팝업 → 넘기기 캡처 |

## 변경 이력

| 날짜 | 내용 |
|---|---|
| 2026-10-01 | 처음 작성 (D58 ①) |
