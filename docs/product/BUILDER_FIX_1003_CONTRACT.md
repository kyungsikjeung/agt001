# 빌더 고치기 10/3 계약 (BUILDER_FIX_1003_CONTRACT)

> 2026-10-03 (KST) 대표 피드백 6건. 계약 Claude, 구현 OpenCode(muse-spark-1.3), 검토·테스트·커밋 Claude.

| # | 대표 피드백 | 작업 |
|---|---|---|
| 1 | 사진 고치기를 열면 닫고 돌아갈 수 없다(X 버튼) | J1 |
| 2 | 공방·학원 선생님 구역 디자인이 없다(참고: 인강 사이트 선생님 카드 격자) | S1(서버) · S3(모양) · S2(고치기 칸) |
| 3 | 오시는 길 고치기 칸에 위치 검색이 없다 | J3 |
| 4 | 왼쪽 구역 목록을 끌어서 순서를 바꾸면 시안 순서도 바뀌어야 | J4 |
| 5 | 채팅 메뉴를 눌러도 아무것도 안 떠서 있는지도 모르겠다 | J5 |
| 6 | 랜딩에서 템플릿(펜션·숙박)을 누른 뒤 브라우저 뒤로 가기 → 아무것도 안 눌림 | J6 |

## J1 사진 고치기 닫기 (`frontend/src/builder/PhotoSheet.tsx`, `photoSheet.css`, `PhotoSheet.test.tsx`)
- 원인: 시트가 길어 스크롤하면 맨 위 '닫기' 줄이 사라진다.
- `.ph-top`을 시트 안에서 `position: sticky; top: 0` (배경색 있게, 위에 겹쳐도 글이 비치지 않게).
- 닫기 버튼: 글자 '닫기' 대신 ✕ 아이콘(인라인 SVG) + `aria-label="닫기"`, 누르는 면 44×44px 이상.
- 시트 밖 어두운 곳(`.ph-scrim`)을 누르면 닫기(`e.target === e.currentTarget`일 때만). 열려 있는 동안 Esc 키로 닫기.
- 테스트: ✕·Esc·바깥 누르기 → `onClose` 1번, 시트 안 누르기 → 안 닫힘.

## J3 오시는 길 위치 검색 (`frontend/src/editor/SectionPanel.tsx`, 새 `frontend/src/editor/SectionPanel.location.test.tsx`)
- `kind === 'location'` 또는 `'when'`이면 칸들 위에 `<AddressSearch roomId={roomId} onSaved={(c) => onSaved(c, selected.id)} />`
  (`frontend/src/builder/AddressSearch.tsx` 그대로 재사용. 저장하면 좌표가 들어가 공개본에 카카오 지도가 나온다 — MAP_CONTRACT).
- 위치 글자 칸은 그대로 둔다(직접 고치기).
- 테스트: 오시는 길 구역을 고르면 '주소 검색' 버튼이 보인다. 다른 구역(예: 첫 화면)에는 없다.

## J4 왼쪽 구역 끌어서 순서 바꾸기 (`frontend/src/editor/SiteEditor.tsx`, `frontend/src/editor/editor.css`, `frontend/src/editor/SiteEditor.test.tsx`)
- 대상: 빌더 넓은 화면 왼쪽 `nav.ed-outline`(구역 바로가기) 목록.
- 네이티브 HTML5 끌기(`draggable`, `onDragStart`/`onDragOver`/`onDrop`/`onDragEnd`). 새 라이브러리 금지.
- `locked`인 구역은 끌 수 없고 제자리에 둔다: 새 순서를 만들 때 locked 구역은 원래 자리(index)에 다시 끼운다.
- 놓으면 `saveCard(roomId, readMemberId(), {}, undefined, { layout: { variant, order, hidden, added } })`
  — `hidden` = 지금 숨김 구역 id들, `added` = `preview.layout?.added ?? []`. 성공하면 기존 `handleSaved(updated, 옮긴 id)`(미리보기 다시 그림).
  실패하면 `role="alert"` 문구 '순서를 바꾸지 못했어요. 잠시 뒤 다시 해 주세요.'
- 끄는 동안 놓을 자리 위에 선 표시(css 클래스 `ed-outline-drop`), 줄 앞에 끌기 손잡이 아이콘(⋮⋮, `aria-hidden`).
- 같은 자리에 놓으면 저장하지 않는다. 오른쪽 칸의 '구역 위로·아래로' 버튼은 그대로(키보드 대체).
- 테스트: dragStart(2번째) → dragOver/drop(4번째) → saveCard가 바뀐 order로 1번 불림. locked 구역은 `draggable=false`.

## J5 공개 뒤 기능 칩 안내 창 (`frontend/src/builder/BuilderPage.tsx`, `frontend/src/builder/builder.css`, `frontend/src/builder/BuilderPage.test.tsx`)
- 원인: 채팅·스탬프·온라인 주문 칩은 `after_publish`라 누르면 화면 맨 아래 한 줄(`chipMsg`)만 바뀐다 → 아무 반응 없는 것처럼 보인다.
- `after_publish` 칩을 누르면 공지 창(`bd-notice-sheet`)과 같은 자리·모양의 안내 창(`role="dialog"`, `aria-label`=칩 이름)을 연다. PUT은 하지 않는다.
- 창 내용(키별 글, 코드 안 상수):
  - `chat` 제목 '손님 채팅' / "공개 사이트에 '채팅하기' 버튼이 생겨 손님이 바로 물어볼 수 있어요. 답은 사장님 화면 > 채팅에서 해요."
  - `stamps` 제목 '스탬프 적립' / "손님이 결제하면 스탬프가 자동으로 쌓여요. 몇 개에 무엇을 줄지는 사장님 화면 > 스탬프에서 정해요."
  - `order` 제목 '온라인 주문' / "손님이 사이트에서 포장 주문을 넣을 수 있어요. 사장님 화면 > 주문에서 켜고 받아요."
  - 모르는 키: 제목 = 칩 이름, 글 "공개한 뒤 사장님 화면에서 켜고 끌 수 있어요."
  - 상태 한 줄: `지금: 켜짐` 또는 `지금: 꺼짐`.
  - 공개했으면(`card.published` 참) `<a href="/owner">사장님 화면 열기</a>`, 아니면 "사이트를 공개하면 바로 쓸 수 있어요."
  - 위 오른쪽 ✕ 닫기(`aria-label="닫기"`), Esc로도 닫기. 다른 칩 창(공지)이 열려 있으면 그건 닫고 연다.
- 기존 `chipMsg` '공개한 뒤 사장님 화면에서 켤 수 있어요' 줄은 없앤다.
- 테스트: 채팅 칩 → 창에 '손님 채팅'·'지금: 켜짐', ✕ → 닫힘, PUT 안 불림.

## J6 뒤로 가기 뒤 잠김 (`frontend/src/Landing.tsx`, `frontend/src/landing-smoke.test.tsx`)
- 원인: 템플릿·시작하기를 누르면 `busy=true` 후 `location.href`로 떠난다. 뒤로 가기는 브라우저가 그 상태 그대로 되살린다(bfcache) → 모든 버튼이 `busy`로 막힘.
- `useEffect`로 `window.addEventListener('pageshow', () => setBusy(false))` (정리 함수에서 제거).
- 테스트: 템플릿을 눌러 busy로 만든 뒤 `window.dispatchEvent(new Event('pageshow'))` → 다시 누를 수 있다.

## S1 선생님 데이터·서버 (`app/api/card.py`, `app/services/site_data.py`, `app/services/photo_needs.py`, `app/services/site_render.py`, 새 `tests/unit/test_staff_edit.py`)
- 저장 모양 `card["staff_edit"]`: 최대 12명, 한 명 = `{"name": 1~20자, "role": ≤12자(예: 선생님·원장·강사), "subject": ≤12자(과목·분야, 예: 영어·도예),
  "tagline": ≤40자(한 줄 소개), "bio": ≤200자, "specialties": 최대 4개 × ≤12자}`. 앞뒤 공백 제거, 이름 빈 줄은 버림.
  같은 이름 두 번이면 400 `같은 이름이 두 번 있어요: <이름>`. 검사 함수 `site_data.clean_staff(raw) -> (list, errors)`.
- `PUT /card` `CardIn.staff: Optional[list[StaffIn]] = Field(default=None, max_length=12)`. None = 그대로, `[]` = 지우기(대화에서 받은 값·예시로 돌아감).
  바뀌면 `changed`에 `"staff"`. `_changed_label`이 `staff`에 '선생님·담당자'를 돌려주게.
- `_view`에 `"staff": site_data.staff_list(card)` — `staff_edit`가 있으면 그것, 없으면 `card_data` 구조 데이터 staff(이름·역할·전문)를 같은 모양(빈 칸은 "")으로. 예시는 넣지 않는다.
- `site_data`: 선생님 원본 = `staff_edit`(있고 비어 있지 않으면) 아니면 `data["staff"]`. optional staff 구역 빼기(지금 `data["staff"]`만 봄)와 `_fill_staff` 둘 다 이 원본을 쓴다(`_fill_staff`에 `card` 인자 추가).
  member에 `subject`·`tagline`·`bio` 넣기. 사장님 사진: `PH.site_photos(card)` 중 `tag == "staff:" + 이름`이고 `/uploads/`로 시작하는 첫 장 → `image`(예시 표시 없음). 없으면 지금처럼 예시 팩 `staff:{pos}`.
  변형: 구역 id가 `teachers`·`teacher`(학원 D·공방 E 청사진)면 사람 수와 상관없이 `"cards"`, 아니면 지금처럼 solo/team.
- `photo_needs.valid_tag`: `"staff:" + 이름`이 `staff_edit` 이름 중 하나면 True.
- `site_render`: `section_type == "staff"`에 `"cards"` 허용. `_staff_members`에 `subject`·`tagline`·`pos`(1부터)·`popover_id = f"staff-{섹션 id}-{pos}"` 추가(섹션 id는 인자로). cards 문맥은 team과 같다(`label`, `booking_href`, `members`).
  다른 곳에 staff 변형 허용 목록이 있으면(`git grep -n '"team"'`) 거기도 `cards`.
- 테스트(`--noconftest`로 DB 없이): clean_staff 검사(길이·중복·빈 이름·12명), `_fill_staff`가 staff_edit·사장님 사진·cards 변형을 쓰는지, valid_tag.

## S3 선생님 카드 모양 (새 `templates/sections/staff--cards.mustache`, 새 `templates/css/55-staff-cards.css`)
- 문맥은 S1 그대로: `id`, `label`, `booking_href`, `members[]` = `{name, role, subject, tagline, bio, initial, specialties[{text}], has_specialties, image_src, image_alt, image_example, example, pos, popover_id}`.
- 참고 모양(인강 사이트 선생님 격자, 하트 버튼은 넣지 않음): 세로 카드(가로:세로 = 4:5), 옅은 바탕(사이트 토큰의 면 색), 둥근 모서리.
  왼쪽 위 `tagline` 굵게 2~3줄, 그 아래 왼쪽 `subject` 작은 글씨 강조색, 그 아래 `name` 크게 굵게 + 다음 줄 `role`(없으면 '선생님').
  사진은 카드 오른쪽 아래에 붙여 카드 너비 약 60%·`object-fit: cover`·`object-position: top`. 사진이 없으면 오른쪽 아래에 큰 이니셜 원.
  격자: 휴대폰 2열, 넓은 화면(≥768px) 4열, 간격 12~16px. 글자는 사진과 겹치지 않게(글 칸 너비 약 55%).
- 카드 전체가 `<button type="button" popovertarget="{{popover_id}}">` → 네이티브 `popover` 상세 창(스크립트 없음):
  큰 사진, 과목, 이름·역할, 한 줄 소개, 전문 태그(`s-tags`), 소개(`bio`), `booking_href`가 있으면 '상담 신청' 버튼, 닫기 버튼(`popovertarget` + `popovertargetaction="hide"`, `aria-label="닫기"`).
- 예시 표시 그대로: `example`이면 '예시', 아니고 `image_example`이면 '예시 사진'(`s-example` 클래스 재사용).
- 색·글꼴·둥글기는 `templates/site.css`의 변수만 쓴다(`.s-staff` 규칙 참고). 새 색 값 금지. 다크 테마는 변수로 자동.

## J7 까치를 누르면 처음 화면으로 (대표 10/3: 빌더·채팅방에서 메인으로 돌아갈 수 없다)
- 랜딩과 같은 모양: `<a href="/" aria-label="처음 화면으로">` 안에 `<img src="/icons/kkachi.svg" alt="" width=28 height=28>`. 누르는 면 44×44px 이상(패딩), 포커스 테두리 보이게.
- J7a `static/room.html`: `header h1::before` 그림을 없애고 h1 앞에 위 링크를 둔다(제목 글자는 그대로).
- J7b `frontend/src/builder/BuilderPage.tsx`·`builder.css`·`BuilderPage.test.tsx`: `.bd-top-row`의 가게 이름(h1) 앞에 위 링크. 불러오는 중·못 연 화면에는 넣지 않아도 된다.
- 테스트(J7b): '처음 화면으로' 링크의 href가 `/`.

## S2 선생님 고치기 칸 (새 `frontend/src/editor/StaffEditor.tsx`·`StaffEditor.test.tsx`, `frontend/src/editor/SectionPanel.tsx`, `frontend/src/editor/cardApi.ts`)
- 서버(S1 완료): `GET/PUT /card` 응답에 `staff: [{name, role, subject, tagline, bio, specialties: string[]}]`.
  저장 = `saveCard(roomId, memberId, {}, undefined, { staff: [...] })`(최대 12명, `[]`이면 대화에서 받은 값·예시로 돌아감). 틀리면 400 `detail` 글(예: '같은 이름이 두 번 있어요: 김민지').
- `cardApi.ts`: `RoomCard.staff?: StaffMember[]` 타입, `saveCard` 추가 인자에 `staff` 허용.
- `SectionPanel.tsx`: `bind === 'staff'` → 새 종류 `'staff'` → `<StaffEditor roomId card onSaved={(c) => onSaved(c, selected.id)} />`. ('채팅으로 말해 주세요' 대신)
- `StaffEditor`: 한 사람 = 접힌 줄(이름 · 과목) → 누르면 펼침. 칸: 이름(20자), 역할(12자, 자리 글 '선생님'), 과목·분야(12자, 예: 영어), 한 줄 소개(40자, 예: 수능 영어, 해석은 제대로), 소개(여러 줄 200자), 전문 분야(쉼표로 최대 4개).
  '+ 선생님 더하기'(12명까지), 줄마다 '빼기'. 아래 '저장' 한 번에 전체를 보낸다. 성공 '저장했어요.', 실패는 서버 `detail` 또는 '저장하지 못했어요. 잠시 뒤 다시 눌러 주세요.'(`role="alert"`).
  사진: 줄마다 '사진 올리기'(`uploadPhoto(roomId, memberId, file, 'staff:' + 이름)` 뒤 `fetchCard`로 새 카드 → onSaved). 저장 안 된 이름(서버 `card.staff`에 없는 이름)이면 버튼을 막고 '이름을 저장한 뒤 사진을 올릴 수 있어요'.
  `card.staff`가 비어 있으면 빈 줄 하나로 시작.
- 테스트: 줄 더하기·고쳐 저장 → saveCard가 staff 배열로 불림, 400 글 표시, 저장 안 된 이름은 사진 버튼 막힘.
