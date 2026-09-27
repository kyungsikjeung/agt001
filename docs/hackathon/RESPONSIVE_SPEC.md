# 반응형 UI 기술 스펙 (agt001)

## 1. 브레이크포인트 기준

| 구분 | 범위 | 대상 기기 |
|------|------|-----------|
| 모바일 | ~480px | 스마트폰 세로 |
| 태블릿 | 481~768px | 스마트폰 가로 / 태블릿 |
| 데스크톱 | 769px+ | 노트북 / 데스크톱 |

- 기준 근거: 기존 레이아웃의 고정 폭(`max-width: 640px`)이 모바일(~360px)에서 깨지지 않도록 480px을 1차 분기점으로 둔다. 768px은 태블릿 세로의 일반적인 상한이다.

## 2. 접근 방식

- **mobile-first**: 기본 스타일은 좁은 화면 기준으로 작성하고, 넓은 화면용 규칙은 `min-width` 미디어 쿼리로 점진적 확장한다. (단, 기존 데스크톱 스타일을 깨지 않기 위해 좁은 화면 보정용 `max-width` 쿼리도 병용한다.)
- **viewport meta 태그**: 모든 HTML 산출물에 아래 태그를 포함한다.
  ```html
  <meta name="viewport" content="width=device-width, initial-scale=1">
  ```
  없으면 모바일 브라우저가 페이지를 데스크톱 폭(~980px)으로 렌더링해 media query가 동작하지 않는다.
- **fluid width + media query**: 고정 `px` 폭 대신 `width: 100%`, `max-width: 640px`, `%`/`rem` 조합으로 유동 폭을 유지한다. 미디어 쿼리에서는 `padding`, `font-size`, `#log`/`.hero` 높이만 조정한다.
- **고정 px 금지 원칙**: 본문 폭·패딩·폰트에 절대 고정 px를 쓰지 않는다. 예외적으로 `border`, `border-radius` 같은 장식 속성은 px 허용.
- **기능/로직 불변**: 레이아웃·CSS만 변경한다. JS, 플레이스홀더, 함수 시그니처, 라우트, JSON 필드명은 건드리지 않는다.

## 3. 적용 대상

### (a) static/index.html (고객용 챗봇 위젯)
- viewport meta 태그 추가.
- `body { max-width: 640px; width: 100%; box-sizing: border-box; }` 로 좁은 화면에서 가로 스크롤 방지.
- `@media (max-width: 480px)`: body 여백 축소(`margin: 16px auto`), `#log` 높이 축소(예: `height: 60vh`), `#row` 입력창·버튼 터치 영역 유지, `h2` 폰트 축소.
- 카카오 공유 버튼·채팅 입력창 등 기존 JS/기능은 그대로 둔다.

### (b) templates/variant-1.html (병렬작업 2 UI 시안 템플릿)
- viewport meta 태그 추가.
- 플레이스홀더 `{{TITLE}}`, `{{PLATFORM}}`, `{{FEATURES_HTML}}`, `{{QUOTE_AMOUNT}}`, `{{QUOTE_BASIS}}`, `{{REQUIREMENT_ID}}` 의 이름·위치는 절대 변경 금지 (`backend.py`의 `render_design()`이 문자열 치환하므로 바꾸면 깨진다).
- CSS만 반응형으로 개선: `@media (max-width: 480px)` 에서 `.hero` 패딩 축소(`24px 16px`), `h1` 폰트 축소(`20px`), `.section` 패딩 축소(`16px`), `.quote-amount` 폰트 축소(`22px`). `img`/`ul` 넘침 방지를 위해 `max-width: 100%`, `box-sizing: border-box` 적용.

### (c) 병렬작업 3 Hermes 코드생성 산출물
- `backend.py`의 `_run_hermes_codegen_job()` 프롬프트에 반응형 요구사항을 명시한다: "반응형 웹(모바일/데스크톱에서 모두 잘 보이게, viewport meta 태그 포함)으로 만들어라".
- Hermes 산출물은 서버가 검증하지 않는 최종 고객 인도물이므로, 프롬프트 지시 한 줄이 품질을 좌우한다. 산출물 HTML에도 위 §2의 viewport + fluid width + media query 원칙이 그대로 적용되도록 유도한다.
