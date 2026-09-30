# 계약서: 메뉴 태그 사진 창고 + 공간 예시 4장 (ART_LIB_CONTRACT)

> 2026-10-01 (KST) / Claude 작성, OpenCode 구현, Claude 검토·생성 실행. 계획 [OWNER_FEEDBACK_1001_PLAN](OWNER_FEEDBACK_1001_PLAN.md) §5, 결정 D58 ③(베타 전 생성 상한 없음, 만든 사진은 태그로 저장해 재사용).
> 재사용: `ai_images._generate_bytes`·`prompt_for`(Gemini, 사람·글자·간판·로고 금지 규칙), `photos._clean_ai_image`, `site_data._item_image`(사진 고르는 순서), `card_api.post_change_followup`, `photos._refresh_designs_async`, `app.llm.chat_json`, 예시 표시(D51).

## 0. 결론

- 메뉴·항목 이름마다 **태그**를 정한다. 예: "아메리카노" → `coffee-americano`, "알리오올리오" → `pasta-oil`.
- 태그 사진이 창고에 있으면 그 사진을 쓰고, 없으면 **태그 낱말만으로** 한 장 만들어 창고에 넣는다. 다음 가게는 다시 만들지 않고 재사용한다.
- 사진 고르는 순서: 사장님 사진 → 그 방의 AI 그림 → **창고 태그 사진** → 업종 예시 팩.
- 창고 사진은 가게 것이 아니라서 공개본에 **"예시 이미지"** 표시를 단다(D51).
- 공간 예시는 업종마다 1장에서 **4장**(입구·내부·자리·분위기)으로 늘린다. Claude가 한 번 만들어 `templates/art/ex/`에 넣는다.

## 1. 데이터

- 창고 폴더: `settings.generated_dir / "art-lib"`.
  - 파일은 `<tag>.webp`이고, 목록은 `index.json`이다: `{tag: {"words": [str], "industry": str, "prompt": str, "made": "YYYY-MM-DD"(KST), "src": "gemini"}}`.
- 태그 낱말표: `app/data/art_tags.json`: `{tag: {"words": ["아메리카노", "americano"], "industry": ["cafe"], "prompt": "a cup of americano coffee on a wooden table"}}`.
  - 업종마다 자주 나오는 항목을 **업종당 15~20개, 모두 100개 안팎**으로 담는다(카페·식당·미용실·공방·학원·펜션).
- 태그 모양: `^[a-z0-9]+(-[a-z0-9]+){0,3}$`, 40자 이하.
- 주소: `GET /art-lib/{tag}.webp`(태그 모양이 아니면 404). `Cache-Control: public, max-age=86400`이고, `/uploads`와 같은 방식이다.
- 사장님 정보(가게 이름·전화·주소·사진)는 창고에도 AI 요청에도 넣지 않는다. 항목 이름과 업종만 넣는다.

## 2. 서버 (`app/services/art_lib.py` 신규)

| 번호 | 함수 | 규칙 |
|---|---|---|
| 1 | `tag_for(name, industry) -> str \| None` | ① 낱말표에서 찾는다: 이름을 정규화(공백·괄호·숫자·단위 빼기)한 뒤 `words` 중 하나와 같거나 포함하면 그 태그. ② 없으면 LLM(`chat_json`)에 "이 목록 중 하나 또는 새 태그"를 묻는다. 목록은 낱말표 태그 + 창고 태그다. 응답 `{"tag", "prompt"}`에서 태그 모양이 틀리면 None. ③ 결과를 창고 `index.json`의 `aliases`(`{정규화 이름: tag}`)에 저장해 같은 이름은 LLM을 다시 부르지 않는다 |
| 2 | `url(tag) -> str \| None` | 파일이 있으면 `/art-lib/<tag>.webp` |
| 3 | `ensure(tag, prompt, industry) -> bool` | 파일이 없으면 만든다. 같은 태그는 동시에 한 번만 만든다(프로세스 잠금 + 진행 중 표시 파일). 프롬프트는 `ai_images`의 항목 프롬프트 규칙(사람·글자·간판·로고 금지, 35mm 스타일)에 `prompt`를 끼운다. 결과는 `_clean_ai_image` → webp로 저장한다. 하루 상한은 `settings.art_lib_daily_cap`(기본 0 = 제한 없음, D58 ③)이다. 실패하면 False이고 예외를 내지 않는다 |
| 4 | `prefetch(card) -> None` | 사장님 사진·방 AI 그림이 없는 항목마다 `tag_for` → 창고에 없으면 `ensure`를 **뒤에서** 부른다(스레드, 한 번에 최대 3개씩). 하나라도 새로 만들어지면 `photos._refresh_designs_async`로 시안·공개본을 다시 그린다 |
| 5 | `pick(card, name) -> dict` | 창고에 있으면 `{"image": url, "image_alt": f"{name} 사진 (예시)", "image_example": True}`, 없으면 `{}`. **그리기 중에는 LLM·생성을 부르지 않는다**(`aliases`와 낱말표만 본다) |

- 부르는 곳:
  - `site_data._item_image`: AI 그림 다음, 예시 팩 앞에 `art_lib.pick`.
  - `card_api.post_change_followup`: 바뀐 칸에 항목이 있으면 `art_lib.prefetch`.
  - `chat_flow`의 시안 만들기 시작과 빌더 시작(`start.post_start`)에서 한 번씩 `prefetch`.

## 3. 공간 예시 4장 (Claude 실행, 비용 있음)

- 업종 6개 × `space1`~`space4` = 24장을 `ai_images._generate_bytes`로 만든다. 프롬프트는 업종 공간 + 입구·내부·자리·분위기다. 파일은 `templates/art/ex/<industry>-space<n>.webp`이다.
- 예시 팩(`design_variants`의 pack photos)에 `space:1`~`space:4`를 넣는다. 공간 사진첩 구역이 이 4장을 돌려 쓴다(객실 `room:k`와 같은 방식).
- 눈 검수는 P3와 같게 한다: 사람·글자·간판·로고 없음, 업종에 맞음.

## 4. 작업 묶음

| 묶음 | 누가 | 파일(소유) | 선행 |
|---|---|---|---|
| A1 창고 | OpenCode | `app/services/art_lib.py`, `app/data/art_tags.json`, `app/api/public.py`(경로 1개), `app/config.py`(`art_lib_daily_cap` 한 줄), `tests/unit/test_art_lib.py` | 없음 |
| A2 연결 | OpenCode | `app/services/site_data.py`(`_item_image` 한 줄), `app/api/card.py`(followup 한 줄), `app/services/chat_flow.py`·`app/api/start.py`(한 줄씩), `tests/unit/test_art_lib.py` 추가 | A1, NOTICE N1(같은 파일) |
| A3 공간 4장 | Claude | `templates/art/ex/*-space[1-4].webp`, 예시 팩 표 | 없음 |
| A4 창고 채우기 | Claude | 낱말표 100개 태그를 미리 한 번 만든다(비용 기록) | A1 |

**하지 말 것**: 그리기 중 생성·LLM 호출, 가게 정보를 AI에 보내기, 사장님 사진을 창고에 넣기, 창고 사진에 예시 표시 빼기, 새 의존성.

## 5. 합격 테스트

| 번호 | 테스트 |
|---|---|
| 1 | `tag_for`: 낱말표 적중("아이스 아메리카노 L" → `coffee-americano`), 모르는 이름 → 가짜 LLM 태그, 틀린 태그 모양 → None, 같은 이름 두 번째는 LLM 호출 없음 |
| 2 | `ensure`: 가짜 생성기로 파일·index 저장, 같은 태그 동시 두 번 → 한 번만 생성, 상한 1이면 두 번째 태그는 False, 요청 본문에 가게 이름·전화 없음 |
| 3 | `pick`·`_item_image` 순서: 사장님 사진 > AI > 창고 > 팩, 창고 사진은 `image_example` |
| 4 | `GET /art-lib/<tag>.webp` 200, 이상한 태그(`../x`) 404 |
| 5 | `prefetch`가 뒤에서 돌고, 그리기 함수는 생성·LLM을 부르지 않음(가짜가 호출되면 실패) |

## 변경 이력

| 날짜 | 내용 |
|---|---|
| 2026-10-01 | 처음 작성 (D58 ③) |
