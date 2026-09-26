# 디자인 품질 높이기 조사 (2026-09-26 확인)

## 5줄 요약

1. Stitch·Paper·Figma Make·v0·Framer AI·Lovable는 모두 큰 언어 모델로 화면을 만들고, 토큰(색·글꼴·여백 규칙)으로 전체를 통일한다.
2. 이 중 우리처럼 "가게마다 자동으로" 쓸 수 있는 길은 Stitch SDK·MCP와 Figma MCP뿐인데, Stitch는 실험실 제품이라 상업용 자동화에 약관 위험이 있고 확인 못 한 부분이 있다.
3. 마감(2026-09-28) 안에 되는 방법은 우리 부품·CSS를 직접 고치는 것(A)과 검증된 오픈소스 가져오기(D)뿐이다.
4. "Stitch 수준"의 핵심은 큰 제목 대비·넉넉한 여백 리듬·진짜 사진·색 2~3개·둥근 카드와 큰 버튼·첫 화면 한 가지 행동이다.
5. 추천안은 A+D를 합친 것으로, 마감 전에는 글자·여백·카드·첫 화면만 고치고 마감 뒤에 사진·토큰 체계를 손본다.

> 날짜 표기: 아래 모든 출처는 2026-09-26에 확인했다. 확인하지 못한 내용은 "확인 못 함"이라고 적었다.

---

## 0. 우리 지금 상태 (먼저 읽은 것)

- 품질 점검 1차(`docs/product/evals/site-quality-2026-09-26.md`): 36쪽 중 빈칸 노출 24쪽, 펜션 객실 카드 사라짐, 예시 표시 노출 등. 사람이 눈으로 본 문제 10건(Q-1~Q-10).
- 품질 점검 2차(`docs/product/evals/site-quality-2026-09-26-r2.md`): Q-1~Q-5를 고쳐 빈칸 0쪽·사실 누락 0쪽이 됨. 남은 것은 미용실 1·3안 비슷함(Q-6), 겹침형 첫 화면 읽기 어려움(Q-7), 체크박스 20px(Q-8), 낱말 중간 줄바꿈(Q-9), 전화 버튼 중복(Q-10), 작은 글자·작은 누름칸(문의 양식 13px, 체크박스).
- 지금 구조: 부품 25종(`templates/sections/*.mustache`), 공용 CSS(`templates/site.css`), 토큰 4종(`templates/tokens/*.json`: 색·글꼴·여백·모서리). 스크립트 없는 정적 HTML, 휴대폰 390px 우선. 제목 32px·본문 16px·행간 1.625·본문 최대 너비 720px.

---

## 1. 바깥 도구들은 어떻게 좋은 화면을 만드는가

### 1.1 Google Stitch

- 쓰는 모델: Gemini 계열. 처음에는 Gemini 2.5 Pro(실험 모드, 그림 입력 가능)와 2.5 Flash(빠른 모드)였고, 2025년 12월 업데이트 뒤 Gemini 3이 들어갔다. 고를 수 있게 되어 있다.
  - 출처: https://blog.google/innovation-and-ai/models-and-research/google-labs/stitch-updates/ (2026-09-26 확인)
  - 출처: https://www.nxcode.io/resources/news/google-stitch-complete-guide-vibe-design-2026 (2026-09-26 확인)
- 디자인 시스템·토큰 방식: 프로젝트 단위 디자인 시스템을 따로 두고, 화면 만들기 지시에는 색·글꼴을 넣지 말고 배치·내용만 쓰라고 한다(색·글꼴은 시스템에서 자동 적용). URL에서 디자인 시스템을 뽑아오거나 DESIGN.md 파일로 규칙을 주고받을 수 있다.
  - 출처: https://github.com/google-labs-code/stitch-skills/blob/HEAD/plugins/stitch-design/skills/generate-design/SKILL.md (2026-09-26 확인)
  - 출처: https://blog.google/innovation-and-ai/models-and-research/google-labs/stitch-ai-ui-design/ (2026-09-26 확인)
- 이미지 처리: 그림·스케치·스크린샷을 올리면 그에 맞는 화면을 만든다(실험 모드). 말로 시키면 3~5번 다듬는 것이 보통이다.
  - 출처: https://www.digitalcitizen.life/what-is-google-stitch-and-how-it-turns-text-into-app-designs/ (2026-09-26 확인)
- 출력 형식: HTML·CSS 코드와 Figma 붙여넣기(자동 배치·고칠 수 있는 층 구조). React·JS 동작 코드는 직접 안 나오고, AI Studio·Antigravity로 넘겨서 붙인다. 반응형·JS 동작은 확인 못 함.
  - 출처: https://developers.googleblog.com/en/stitch-a-new-way-to-design-uis/ (2026-09-26 확인)
- API·내보내기·자동화: Stitch MCP 서버와 SDK(`@google/stitch-sdk`, npm꾸러미)가 있다. 화면 만들기·고치기·변형 만들기를 코드로 부르고 HTML과 스크린샷 주소를 받아온다. 생성 횟수 제한은 화면版과 같다고 적혀 있다. SDK가 공식 Google 저장소인지는 확인 못 함(둘러보기 사이트·미러 문서에서만 확인).
  - 출처: https://stitch.withgoogle.com/docs/mcp/setup (2026-09-26 확인, 내용은 자바스크립트로 그려져 본문 확인 못 함)
  - 출처: https://googlestitch.me/integration/sdk (2026-09-26 확인, 비공식 안내 사이트)
  - 출처: https://deepwiki.com/google-labs-code/stitch-sdk (2026-09-26 확인, 미러 문서)
- 요금: 무료. 일반 모드 월 350번, 실험 모드 월 50번까지 만들 수 있다고 한다.
  - 출처: https://www.digitalcitizen.life/what-is-google-stitch-and-how-it-turns-text-into-app-designs/ (2026-09-26 확인)
- 이용 조건(상업적 사용·자동화): Stitch 약관 페이지(https://stitch.withgoogle.com/terms)는 자바스크립트로 그려져 내용을 확인 못 함. Google 실험실 제품이라 상업용·대량 자동화에 쓸 수 있는지는 확인 못 함. Google Cloud의 미리보기 AI 제품 약관에는 "평가·시험용으로만 쓰고 상업용·실사용에 쓰지 말라"는 문구가 있으나 Stitch에 그대로 적용되는지는 확인 못 함.
  - 출처: https://cloud.google.com/archive/terms/genai-preview-products-20260320 (2026-09-26 확인, Stitch 적용 여부는 확인 못 함)

### 1.2 Paper (paper.design)

- 쓰는 모델: 어떤 모델을 쓰는지는 공개 문서에서 확인 못 함. 대신 "HTML·CSS 자체가 그림판"이라서 AI가 DOM(웹 문서 구조)을 직접 읽고 쓰는 방식이다. Figma처럼 따로 바꾼 형식이 없어서 코드가 틀어지지 않는다고 설명한다.
  - 출처: https://paper.design/ (2026-09-26 확인)
  - 출처: https://www.working-ref.com/en/reference/paper-desktop-design-code (2026-09-26 확인)
- 디자인 시스템·토큰 방식: 파일 안에 토큰을 만들고, 코드의 CSS 변수·Figma 토큰과 주고받을 수 있다(MCP로 가져오기, 파일끼리 복사·붙여넣기).
  - 출처: https://paper.design/build-log (2026-09-26 확인)
  - 출처: https://paper.design/docs (2026-09-26 확인)
- 이미지 처리: AI 그림 만들기(양 제한), 셰이더(그러데이션·유리 질감 등 GPU 효과), 영상 내보내기가 있다.
  - 출처: https://paper.design/build-log (2026-09-26 확인)
- 출력 형식: HTML·CSS가 그대로 코드다. React·Tailwind로 복사하기, 그림·영상·PDF 내보내기가 있다. Figma로는 못 내보내고, Figma에서 Paper로는 가져올 수 있다.
  - 출처: https://sfailabs.com/guides/figma-mcp-vs-paper (2026-09-26 확인)
- API·내보내기·자동화: Paper 데스크톱 앱을 열면 MCP 서버가 켜지고, 읽기 11종·쓰기 8종 등 24개 도구를 AI 비서(Cursor·Claude Code 등)에 연결한다. 그림판에서 바로 코드를 만들고 Git에 올리는 흐름을 노린다.
  - 출처: https://paper.design/docs/mcp (2026-09-26 확인)
- 요금: 무료版은 MCP 주 100번·그림 조금. Pro는 월 20달러(1년 내면 월 16달러), MCP 주 100만 번.
  - 출처: https://paper.design/pricing (2026-09-26 확인)
- 이용 조건: 만든 코드·프로젝트는 사용자가 가진다(문서 설명 기준). 자동 대량 생성 허용 약관은 확인 못 함.

### 1.3 Figma (Figma Make·Figma Sites 포함)

- 쓰는 모델: Figma Make에서 GPT-5.6 같은 바깥 모델을 고를 수 있다고 한다. 기본 모델이 무엇인지는 확인 못 함.
  - 출처: https://www.figma.com/solutions/ai-code-generator/ (2026-09-26 확인)
- 디자인 시스템·토큰 방식: Figma 디자인 파일의 부품·스타일·변수를 Make에 "스타일 맥락"으로 붙여서 쓴다(유료版). 디자인과 코드를 한 화면에서 오가며 고친다.
  - 출처: https://help.figma.com/hc/en-us/articles/31304412302231-Explore-Figma-Make (2026-09-26 확인)
- 이미지 처리: 그림·Figma 디자인을 지시에 붙여서 쓴다. 사진 자동 생성量·조건은 확인 못 함.
- 출력 형식: HTML·CSS·자바스크립트. 코드 편집기에서 직접 고치고, 미리보기·게시( собственным 주소·내 도메인)까지 된다.
  - 출처: https://www.figma.com/solutions/design-to-code/ (2026-09-26 확인)
- API·내보내기·자동화: Figma MCP 서버(`https://mcp.figma.com/mcp`)로 디자인을 읽고 쓰는 도구를 준다. Dev Mode MCP 안내 저장소가 있다. 단, 무료·보기 권한은 월 6번까지만 쓸 수 있고 제대로 쓰려면 유료 Full 자리가 필요하다.
  - 출처: https://github.com/figma/dev-mode-mcp-server-guide (2026-09-26 확인)
  - 출처: https://developers.figma.com/docs/figma-mcp-server/tools-and-prompts/ (2026-09-26 확인)
- 요금: Starter 무료版은 AI 점수 월 500점. Professional Full 자리는 월 16달러 + AI 점수 월 3,000점. Make 파일 만들기는 유료 Full 자리가 필요(임시 파일은 다른 자리도 시도 가능).
  - 출처: https://www.figma.com/pricing/ (2026-09-26 확인)
  - 출처: https://help.figma.com/hc/en-us/articles/31722591905559-Figma-Make-FAQs (2026-09-26 확인)
- 이용 조건: 만든 코드 내보내기·게시는 자리·요금제에 따라 된다. 가게마다 자동 대량 생성 허용 여부는 약관에서 확인 못 함. Make에 비밀키·개인정보를 넣지 말라는 안내는 있다.
  - 출처: https://help.figma.com/hc/en-us/articles/31304485164695-Create-a-Figma-Make-file (2026-09-26 확인)

### 1.4 v0 (Vercel)

- 쓰는 모델: 고를 수 있는 여러 모델을 쓰며 토큰당 점수를 달리 매긴다. 정확한 모델 이름 목록은 확인 못 함.
  - 출처: https://v0.app/pricing (2026-09-26 확인)
- 디자인 시스템·토큰 방식: Next.js·React·TypeScript·Tailwind CSS·shadcn/ui 조합으로 코드를 만든다. 말로 시켜서 만드는 방식이다.
  - 출처: https://v0.app/docs/faqs (2026-09-26 확인)
- 이미지 처리: 그림 입력·처리의 자세한 조건은 확인 못 함.
- 출력 형식: React 코드. GitHub 양방향 연결로 가져오고, Vercel에 바로 올릴 수 있다. 순수 정적 HTML만 뽑는 흐름은 주 흐름이 아니다.
  - 출처: https://v0.app/docs/faqs (2026-09-26 확인)
- API·자동화: API·내보내기 자동화 약관은 확인 못 함.
- 요금: 무료版 월 5달러어 점수·하루 7번. Plus 팀版 월 30달러(한 사람당), Business 월 100달러(한 사람당).
  - 출처: https://v0.app/docs/pricing (2026-09-26 확인)
- 이용 조건: 만든 코드는 Vercel 것이 아니고 사용자가 상업용으로 쓸 수 있다. 단 결과물이 남과 비슷하거나 틀릴 수 있어 사람이 검토해야 한다.
  - 출처: https://v0.app/docs/faqs (2026-09-26 확인)

### 1.5 Framer AI

- 쓰는 모델: GPT 5.5 기본, Sonnet 4.6·Opus 4.8 중 고를 수 있다(점수 배율 다름).
  - 출처: https://www.framer.com/blog/ai-credits-simpler-plans-and-lower-prices/ (2026-09-26 확인)
- 디자인 시스템·토큰 방식: Figma 같은 그림판 + CMS(글·상품 모음) + AI 비서. MCP로 Claude·Cursor 같은 바깥 AI를 연결할 수 있다.
  - 출처: https://www.framer.com/blog/ai-credits-simpler-plans-and-lower-prices/ (2026-09-26 확인)
- 이미지 처리: 자세한 조건은 확인 못 함.
- 출력 형식: 코드 내보내기가 없다. Framer 안에서 게시·내 도메인 연결만 된다. 옮기려면 처음부터 다시 만들어야 한다는 평가가 있다.
  - 출처: https://www.rapidevelopers.com/review/framer (2026-09-26 확인, 외부 평가)
- 요금: 무료版(상업용 아님), Basic 월 10달러, Pro 월 30달러. AI 점수는 Free 하루 500점, Basic 월 1,000점, Pro 월 3,000점. 랜딩 1개에 약 300점 든다고 한다.
  - 출처: https://www.framer.com/pricing (2026-09-26 확인)
  - 출처: https://www.framer.com/blog/ai-credits-simpler-plans-and-lower-prices/ (2026-09-26 확인)
- 이용 조건: 무료版은 비상업용. 코드 반출이 안 되어 우리 구조(정적 HTML 파일 entrega)와 맞지 않는다.

### 1.6 Lovable

- 쓰는 모델: 어떤 모델인지는 요금·약관 페이지에서 확인 못 함.
- 디자인 시스템·토큰 방식: 말·그림·Figma·문서로 전체 사이트를 만들고, 채팅·눈으로 직접 고치기로 다듬는다.
  - 출처: https://lovable.dev/en/use-cases/websites (2026-09-26 확인)
- 이미지 처리: 자세한 조건은 확인 못 함.
- 출력 형식: TanStack Start(TypeScript 풀스택) 코드. GitHub 연결로 언제든 코드를 가져올 수 있고, 게시·내 도메인도 된다.
  - 출처: https://lovable.dev/en/use-cases/websites (2026-09-26 확인)
- 요금: 무료版은 하루 만들기 5점(월 최대 30점). 유료는 점수 뭉치制. 정확한 월액은 요금 페이지 구조가 복잡해 확인 못 함.
  - 출처: https://lovable.dev/pricing (2026-09-26 확인)
- 이용 조건: 만든 앱·사이트·코드는 사용자가 가진다(AI 모델 쪽 권리는 제외). AI 결과물은 틀릴 수 있어 직접 검토해야 하며, 점수는 결과가 틀려도 돌아오지 않는다.
  - 출처: https://lovable.dev/terms (2026-09-26 확인)

---

## 2. 우리 서비스에 맞는 방법 비교 (A~E)

전제: 가게마다 자동으로 만들어야 하고, 결과물은 스크립트 없는 정적 HTML이어야 하며, 사장님이 말한 사실만 넣어야 한다. 마감은 2026-09-28이다.

| 방법 | 품질 | 비용 | 속도 | 자동화 가능성 | 우리 구조와의 맞음 | 마감 전 가능 여부 |
|---|---|---|---|---|---|---|
| (A) 우리 부품·CSS를 전문 수준으로 다시 짜기 | 높음(우리가 정한 만큼 오른다). 글자·여백·카드만 고쳐도 체감 큼 | 사람 시간만 듦(돈 안 듦) | 1~2일이면 눈엿볼 변화 가능 | 높음(이미 자동 파이프에 탐) | 가장 잘 맞음(정적·스크립트 없음·사실만 넣기 그대로) | 가능. 마감 전 할 일 1순위 |
| (B) Stitch·Paper·Figma를 API·MCP·내보내기로 연결 | 높음(시안 자체는 좋음) | Stitch 무료이나 횟수 제한(350/50). Paper·Figma는 월 16~20달러+AI 점수 | 가게마다 바깥 호출이라 느리고, 손질 시간 듦 | 낮음~중간. Stitch는 실험실 제품·약관 불확실. Figma MCP는 무료 월 6번. Paper는 데스크톱 앱을 켜야 함 | 나쁨. React·JS 코드가 섞이고, 지어낸 문구·없는 사실이 들어갈 수 있음. 정적·스크립트 금지와 충돌 | 마감 전 불가. 마감 뒤 실험만 가능 |
| (C) 좋은 디자인을 참고 그림으로 먼저 만들고 코드로 옮기기 | 높음(방향 잡기에 좋음) | 그림 생성 점수·사람 시간 | 가게마다 그림→코드 2단계라 느림 | 낮음(사람 손이 매번 필요) | 중간. 참고용으로는 좋으나 가게마다 자동화 안 됨 | 마감 전 불가. 3안 중 1안의 방향 잡기용으로만 가능 |
| (D) 검증된 오픈소스 부품·디자인 시스템 가져오기(라이선스 확인) | 중간~높음(검증된 것만 고르면) | 무료(MIT 등). 대신 라이선스 확인 시간 | 빠름(가져와서 토큰에 맞게 손질) | 높음(한 번 손보면 자동 파이프 그대로) | 잘 맞음. 단 JS 없는 것만 고르고, 글꼴·그림 라이선스 따로 확인 | 가능. (A)와 함께 마감 전 가능. 예: MIT 식당 템플릿(아래 3장) |
| (E) LLM이 매번 HTML·CSS를 새로 짜게 하기 | 들쭉날쭉(좋을 때도 있고 깨질 때도 있음) | 매번 API 돈·시간. 36쪽 기준 부담 | 느림(만들고 검사·고치기 반복) | 중간( Header 검증기를 붙여야 함) | 나쁨. 일관성 깨짐·사실 지어내기·보안 위험(원치 않는 코드·외부 불러오기). 지금 "사장님 사실만" 규칙과 충돌 | 마감 전 불가 |

보충 설명:

- (B)의 Stitch 자동화는 기술적으로는 있다(MCP·SDK). 그러나 상업용·대량 자동화 허용 여부는 약관을 확인 못 했고(1.1 참고), 실험실 제품이라 갑자기 바뀌거나 끊길 수 있다. 가게 사이트를 맡기기에 위험하다.
- (B)의 Figma MCP는 읽기 중심이고 쓰기 자동화는 제한적이며, 무료는 월 6번이라 가게마다 쓰기에는 양이 모자라다.
- (D) 후보 예시(식당·카페, MIT 라이선스로 상업용 가능, 2026-09-26 확인):
  - Bistro Astro版 랜딩(메뉴·예약·후기 구성): https://github.com/shadcnstudio/shadcn-astro-bistro-landing-page-free
  - Bistro Next.js版 랜딩: https://github.com/shadcnstudio/shadcn-nextjs-bistro-landing-page-free
  - TableFork 식당 템플릿(HTML 메뉴·예약·가게 정보 구조화): https://github.com/haider484991/tablefork-nextjs-restaurant-template
  - 주의: 코드는 MIT라도 사진·글꼴·아이콘은 따로 라이선스를 확인해야 한다(확인 못 함이 아니라 반드시 확인할 것).
- (E)의 보안 위험(외부 스크립트·추적 코드·지어낸 전화번호 등)이 실제로起きた 사례를 찾지는 못했고, 일반 주의 사항으로만 적는다. 우리 구조에서는 LLM이 부품 배합·문구만 정하고 HTML 뼈대는 템플릿이 만드는 지금 방식이 더 안전하다.

---

## 3. "Stitch·Paper 수준"을 만드는 디자인 요소

아래 기준 숫자는 웹 글자·여백 안내 글에서 가져왔다. 우리 CSS 값과 나란히 적었다.

### 3.1 글자 크기·굵기 대비

- 바깥 기준: 본문 최소 16px(마케팅 페이지는 18px 권장). 컴퓨터 제목 35~50px, 휴대폰 제목 28~40px. 버튼 글자 18~22px·굵기 600~700. 제목은 굵게(700~900), 본문은 보통(400~500). 제목 행간 1.1~1.25, 본문 행간 1.5 안팎. 한 줄 글자 수는 컴퓨터 45~75자, 휴대폰 35~45자.
  - 출처: https://www.reform.app/blog/font-size-impacts-landing-page-conversions (2026-09-26 확인)
  - 출처: https://madegooddesigns.com/web-typography-guide/ (2026-09-26 확인)
  - 출처: https://uxscan.ai/learn/legibility-rules (2026-09-26 확인)
- 우리 지금: 제목 32px(넓은 화면 40px)·부제 h2 24px(넓은 화면 28px)·본문 16px·버튼 16px(첫 화면 17px). 휴대폰 제목 32px는 기준(28~40px) 안에는 들지만, 본문 16px와의 차이(2배)가 작아 "강한 첫인상"이 약하다. 버튼 글자 16px도 기준(18px 이상)보다 작다.
- 부족한 것: 첫 화면 제목을 36~40px·굵기 800 정도로 키우고, 버튼 글자를 18px로 키울 것. h2와 본문 차이도 지금(24 vs 16)보다 벌릴 것(예: 26~28 vs 16).

### 3.2 여백 리듬

- 바깥 기준: 4px 바탕에 4·8·16·24·32px로 여백을 통일하고, 부품마다 같은 리듬을 쓴다. 첫 화면·가격·후기·문의 칸처럼 행동이 있는 곳에 여백을 넉넉히 둔다. 요즘 좋은 평가는 "여백이 많되, 바탕 격자에 맞춰 뜻이 있게" 두는 것이다.
  - 출처: https://garanord.md/responsive-whitespace-adapting-negative-space-across-devices/ (2026-09-26 확인)
  - 출처: https://latte.dev/guide/modern-website-design-examples (2026-09-26 확인)
- 우리 지금: 토큰(`density.json`)으로 섹션 상하·요소 간격을 통일한 것은 잘한 방향이다. 다만 섹션 좌우가 16px로 좁고, 카드 안 여백이 토큰 dépend라 업종마다 체감이 다르다.
- 부족한 것: 섹션 좌우 20px로 넓히고, 첫 화면 아래·버튼 주위 여백을 한 단계 키울 것. 짝수 섹션 띠(지금 `--ground-soft` 번갈아)는 유지하되 색 차이를 줄여 "줄무늬" 느낌을 없앨 것.

### 3.3 사진 사용 방식

- 바깥 기준: 요즘 좋은 평가는 진짜 사진 1장을 크게, 또는 사진 없이 맞춤 글자로 깨끗하게. "사진 위에 흰 글자 얹기"는 남용되어 진부하다는 평가가 있다. 자동 재생 영상·무거운 효과는 휴대폰 속도를 떨어뜨려 피한다.
  - 출처: https://latte.dev/guide/modern-website-design-examples (2026-09-26 확인)
- 우리 지금: 사진이 없을 때 인라인 SVG 예시 그림을 쓰고, 겹침형 첫 화면(photo-overlay)에 예시 그림이 들어가 Q-7(글자 읽기 어려움·어두운 띠 끊김)이起きた. 2차 점검에서 공개본 예시 표시는 숨겼으나, 겹침형 선택 규칙은 그대로다.
- 부족한 것: 사진이 없으면 겹침형 대신 옆 배치·글자만 쓰기(Q-7 수정). 예시 그림 자체를 "사진 자리"가 아니라 업종 분위기(따뜻한 색·큰 모양)로 바꿀 것. 사장님 사진이 오면 첫 화면·메뉴 사진 자리에 그대로 들어가게 사진 규격(가로·세로 비율) 안내를 정할 것.

### 3.4 색 사용

- 바깥 기준: 요즘은 색 2~3개로 절제하고, 본문 대비는 최소 4.5:1(큰 글자 3:1), 여유 있게는 7:1을 노린다.
  - 출처: https://latte.dev/guide/modern-website-design-examples (2026-09-26 확인)
  - 출처: https://uxscan.ai/learn/legibility-rules (2026-09-26 확인)
- 우리 지금: 대비 AA 미달 0건으로 잘하고 있다(점검 1·2차). 주색·강조색·바탕·글자 토큰(`palettes.json`) 구조도 바깥 토큰 방식과 방향이 같다.
- 부족한 것: 대비는 좋으나 "개성"이 약하다. 업종별 2~3개 팔레트(카페 따뜻함·펜션 시원함 등)를 마감 전 3~6종으로 늘리고, 강조색을 제목 밑줄·버튼·가격에만 써서 아낄 것.

### 3.5 카드·버튼 모양

- 바깥 기준: 버튼은 휴대폰에서 44~48px 이상, 글자 18px 안팎·굵게. 카드는 둥근 모서리·옅은 그림자·명확한 제목/설명/가격 순서.
  - 출처: https://www.reform.app/blog/font-size-impacts-landing-page-conversions (2026-09-26 확인)
  - 출처: https://garanord.md/responsive-whitespace-adapting-negative-space-across-devices/ (2026-09-26 확인)
- 우리 지금: 버튼 44~52px로 기준을 맞추고 있다. 카드는 위 4px 강조선 + 둥근 모서리 + 그림자로 구조는 좋다. 체크박스 20px(Q-8), 작은 안내 글자 13px는 기준 미달이다.
- 부족한 것: 카드 위 4px 선을 없애고(요즘은 적은 장식이 좋다는 평가) 사진·제목·가격 간격을 키울 것. 체크박스를 24px 이상·줄 전체 누르기로 고칠 것(Q-8). 13px 안내문은 14px 이상으로 키울 것.

### 3.6 첫 화면 구성

- 바깥 기준: 업종·대상·다름을 한 문장으로(예: "○○동 20년 단골 식당"처럼). 행동 버튼은 1개만 크게. "어서오세요·믿음직한 동반자" 같은 빈말은 죽은 문구로 본다.
  - 출처: https://latte.dev/guide/modern-website-design-examples (2026-09-26 확인)
- 우리 지금: 가게 이름+문의·전화 버튼 36/36쪽으로 구조는 좋다(점검 2차). 다만 3안이 서로 비슷한 문제(Q-6: 미용실 1·3안 차이 2.0~3.2)가 있다.
- 부족한 것: 첫 화면 문구를 "가게 이름 + 한 줄 다름 + 버튼 1개"로 고정하고, 3안은 사진 배치(겹침·옆·글자만)로만 다르게 할 것. 사진 없는 겹침형을 금지(Q-7)하면 차이도 자연히 벌어진다.

### 3.7 실제 예시 화면 URL (식당·카페)

| 예시 | 주소 | 볼 것 |
|---|---|---|
| Bistro 식당 랜딩 데모(오픈소스·MIT) | https://shadcn-nextjs-bistro-landing-page.vercel.app (2026-09-26 확인, 저장소: https://github.com/shadcnstudio/shadcn-nextjs-bistro-landing-page-free) | 큰 예약 버튼 1개, 메뉴 사진·가격 나열, 후기·오시는 길 순서 |
| Bistro Astro版 데모(오픈소스·MIT) | https://shadcn-astro-bistro-landing-page.vercel.app (2026-09-26 확인, 저장소: https://github.com/shadcnstudio/shadcn-astro-bistro-landing-page-free) | 같은 구성의 정적 版. 우리 정적 구조와 가까움 |
| Stitch 소개·예시 | https://blog.google/innovation-and-ai/models-and-research/google-labs/stitch-ai-ui-design/ (2026-09-26 확인) | 지시→고급 화면→Figma·코드 흐름. 개별 식당 예시 고유 주소는 확인 못 함 |
| Paper 예시·문서 | https://paper.design/docs (2026-09-26 확인) | HTML=그림판이라 코드 틀어짐이 없다는 것. 개별 식당 예시 고유 주소는 확인 못 함 |
| Figma Make 소개 | https://www.figma.com/solutions/ai-website-builder/ (2026-09-26 확인) | 지시→반응형 사이트→게시 흐름 |

> 참고: Stitch·Paper·Figma Make는 로그인 뒤 쓰는 도구라, 식당·카페 예시 화면의 고유 공개 URL은 확인 못 함이라고 적는다. 위 표의 Bistro 데모 2개가 이번 조사에서 확인한 유일한 "열어볼 수 있는 식당 예시"이다.

---

## 4. 추천안 1개와 단계별 실행 계획

### 추천안: (A) 우리 부품·CSS 손보기 + (D) MIT 템플릿에서 배치만 참고하기

- 왜 이것인가: 마감(2026-09-28) 안에 되고, 돈을 안 쓰고, 자동 파이프·정적 HTML·사실만 넣기를 그대로 지킨다. (B)(C)(E)는 마감 뒤 실험으로 미룬다.
- 하지 않는 것: Stitch·Paper·Figma 자동 연결을 마감 전에 하지 않는다(약관·품질·속도 위험). LLM이 HTML을 새로 짜게 하지 않는다.

### 마감 전 할 것 (2026-09-28까지)

1. 글자 키우기: 첫 화면 제목 36~40px·굵기 800, h2 26~28px, 버튼 글자 18px, 13px 안내문 14px 이상. (`templates/site.css` 손질 범위)
2. 여백 넓히기: 섹션 좌우 16→20px, 첫 화면·버튼 주위 한 단계 확대. 짝수 띠 색 차이 줄이기.
3. 카드 단순화: 위 4px 선 빼기, 사진·제목·가격 간격 키우기. (`templates/site.css` 손질 범위)
4. 첫 화면 규칙: 사진 없으면 겹침형 금지→옆·글자만(Q-7). 기본안이 글자만이면 3안은 사진 배치로(Q-6). 문구는 "이름+한 줄 다름+버튼 1개".
5. 남은 점검 수정: 체크박스 24px·줄 전체 누르기(Q-8), 이용 안내 `keep-all`(Q-9). 전화 중복(Q-10)은 펜션만 예외로 두고 나머지는 1개로.
6. MIT 템플릿에서 배치만 참고: Bistro·TableFork의 첫 화면→메뉴→후기→오시는 길 순서를 우리 부품 순서에 반영. 코드는 복사하지 말고 배치·간격 숫자만 참고(사진·글꼴 라이선스 별도 확인).
7. 36쪽 다시 찍어 2차 점검표와 비교(작은 글자·작은 칸이 줄었는지 확인).

### 마감 뒤 할 것

1. 사진 규격 정하기: 사장님 사진이 오면 들어갈 자리 비율(첫 화면·메뉴·사진첩)과 없을 때 분위기 그림 교체.
2. 팔레트 3~6종 추가: 업종별 2~3색 조합을 토큰(`palettes.json`)에 넣고 3안에 다르게 배정.
3. (B) 실험: Stitch SDK로 시안 1~2개를 받아보기. 단 실서비스 연결이 아니라 참고용으로만, 약관 확인 뒤에. 상업용·자동화 허용이 확인될 때까지 가게 사이트에 직접 쓰지 않는다.
4. (C) 실험: 3안 중 1안만 참고 그림→코드 흐름으로 방향을 잡아보는지 시험.
5. (E)는 계속 보류: LLM은 부품 배합·문구 초안까지만 맡기고 HTML 뼈대는 템플릿이 만든다.

---

## 출처 목록 (모두 2026-09-26 확인)

- https://blog.google/innovation-and-ai/models-and-research/google-labs/stitch-ai-ui-design/
- https://blog.google/innovation-and-ai/models-and-research/google-labs/stitch-updates/
- https://developers.googleblog.com/en/stitch-a-new-way-to-design-uis/
- https://www.nxcode.io/resources/news/google-stitch-complete-guide-vibe-design-2026
- https://www.digitalcitizen.life/what-is-google-stitch-and-how-it-turns-text-into-app-designs/
- https://github.com/google-labs-code/stitch-skills/blob/HEAD/plugins/stitch-design/skills/generate-design/SKILL.md
- https://stitch.withgoogle.com/docs/mcp/setup (본문은 자바스크립트 렌더라 확인 못 함)
- https://googlestitch.me/integration/sdk (비공식 안내)
- https://deepwiki.com/google-labs-code/stitch-sdk (미러 문서)
- https://cloud.google.com/archive/terms/genai-preview-products-20260320 (Stitch 적용 여부는 확인 못 함)
- https://paper.design/
- https://paper.design/pricing
- https://paper.design/docs
- https://paper.design/docs/mcp
- https://paper.design/build-log
- https://www.working-ref.com/en/reference/paper-desktop-design-code
- https://sfailabs.com/guides/figma-mcp-vs-paper
- https://help.figma.com/hc/en-us/articles/31304412302231-Explore-Figma-Make
- https://help.figma.com/hc/en-us/articles/31304485164695-Create-a-Figma-Make-file
- https://help.figma.com/hc/en-us/articles/31722591905559-Figma-Make-FAQs
- https://www.figma.com/pricing/
- https://www.figma.com/solutions/ai-code-generator/
- https://www.figma.com/solutions/design-to-code/
- https://www.figma.com/solutions/ai-website-builder/
- https://github.com/figma/dev-mode-mcp-server-guide
- https://developers.figma.com/docs/figma-mcp-server/tools-and-prompts/
- https://v0.app/docs/faqs
- https://v0.app/docs/pricing
- https://v0.app/pricing
- https://www.framer.com/pricing
- https://www.framer.com/blog/ai-credits-simpler-plans-and-lower-prices/
- https://www.rapidevelopers.com/review/framer (외부 평가)
- https://lovable.dev/pricing
- https://lovable.dev/terms
- https://lovable.dev/en/use-cases/websites
- https://github.com/shadcnstudio/shadcn-astro-bistro-landing-page-free
- https://github.com/shadcnstudio/shadcn-nextjs-bistro-landing-page-free
- https://github.com/haider484991/tablefork-nextjs-restaurant-template
- https://shadcn-nextjs-bistro-landing-page.vercel.app
- https://shadcn-astro-bistro-landing-page.vercel.app
- https://madegooddesigns.com/web-typography-guide/
- https://www.reform.app/blog/font-size-impacts-landing-page-conversions
- https://uxscan.ai/learn/legibility-rules
- https://garanord.md/responsive-whitespace-adapting-negative-space-across-devices/
- https://latte.dev/guide/modern-website-design-examples
