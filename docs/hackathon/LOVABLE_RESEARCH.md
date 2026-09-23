# Lovable 리서치 — agt001 팀B/팀C 개선 참고용

> 작성일: 2026-09-23 / 마감: 2026-09-28 / 코드 변경 없음, 조사 문서만
> 전제: 우리 구조 = 팀A(요구사항/견적) → 팀B(정적 HTML 시안 + Playwright 스크린샷) → 팀C(Hermes 에이전트, Docker 샌드박스, 단일 정적 HTML 생성) → 백엔드가 직접 서빙("배포" 흉내)
> 표기 규칙: "확인됨" = 공식 문서/공식 블로그에서 확인 / "추정" = 비공식 유출·간접 근거 / "확인 불가" = 공개 자료에서 못 찾음. 모르는 것은 지어내지 않음.

## 지금 우리가 당장 참고할 만한 것 Top 3

1. **스냅샷 배포 + 수동 재발행 모델** — Publish 시점의 프로젝트를 고정 스냅샷으로 배포하고, 이후 작업은 라이브에 영향 없이 진행, "Publish changes"를 눌러야만 반영. 우리 BND-5(배포→사람 검토)→BND-9(승인→고객 전송) 게이트와 정확히 같은 철학이라, 지금 구조를 바꾸지 않고 용어·UX만 빌려오면 된다.
2. **단순 스타일 수정은 AI를 우회 (Visual Edits 방식)** — "버튼 색 바꿔줘" 같은 수정은 LLM 호출 없이 클라이언트 측 AST/문자열 치환으로 Tailwind 클래스를 바꾸고 낙관적으로 미리보기 갱신. 팀B 시안 단계(정적 HTML 템플릿이라 오히려 Lovable보다 쉬움)에 D+1~2 내 적용 가능.
3. **전체 재생성 금지, 변경 파일만 surgical edit + iframe 스트리밍 미리보기** — 후속 요청마다 전체를 다시 뽑지 않고 필요한 파일의 필요한 부분만 diff로 적용, 미리보기는 iframe에 HMR식으로 즉시 반영. 팀C 프롬프트 규칙 1줄("변경 없는 부분은 그대로, 변경 파일만 출력")로 오늘부터 적용 가능.

---

## 1. UI 생성 방식: 어떤 코드를 만들고, 미리보기는 어떻게 보여주는가

### 1-a. 생성 코드 종류: React+Vite 프로젝트 (정적 HTML 아님)

- **확인된 내용**: Lovable은 기본적으로 **React + Vite + TypeScript** 프로젝트를 생성한다. 스타일은 **Tailwind CSS + shadcn/ui + Radix UI** 조합이다. Next.js/Angular/Vue 등은 기본 지원이 아니며, 필요하면 코드를 export해서 직접 마이그레이션해야 한다. 출처:
  - https://lovable.dev/faq/capabilities/tech-stack/lovable-nextjs-support ("Lovable generates React + Vite + TypeScript by default, not Next.js...")
  - https://docs.lovable.dev/tips-tricks/deployment-hosting-ownership ("Applications are standard Vite + React projects...")
  - https://www.netlify.com/knowledge-base/deploy-your-lovable-app-to-netlify/ ("a standard Vite, React, and TypeScript project, usually with Tailwind and shadcn/ui, and Supabase behind any backend features")
- **확인된 내용(2026-05-13 이후 변경점)**: 공식 블로그에 따르면 신규 프로젝트는 기존 SPA(React + Vite + React Router, 정적 호스팅) 대신 **TanStack Start(SSR/SSG/CSR per-route) 기반**으로 생성된다고 밝히고 있다. 출처:
  - https://lovable.dev/fr/blog/building-apps-using-tanstack-start ("Starting May 13, new projects are Server-Side Rendered (SSR) and powered by TanStack Start", "Previously we created Single-Page Apps (SPAs) built with React + Vite...")
- **우리 프로젝트 적용 가능성: 무리**
  - **이유**: 팀C 현재 산출물은 "단일 정적 HTML"이며 Docker 샌드박스+Hermes 파이프라인 전체가 그 전제로 설계·계약(BND-3/BND-5)되어 있다. 마감(9/28, 약 5일) 안에 React+Vite+TS 멀티파일 프로젝트 생성 + `npm run build` 파이프라인으로 갈아타면 빌드 실패 지점·의존성·Render 배포 절차를 전부 다시 검증해야 한다. Lovable식 풀 프로젝트 생성은 해커톤 이후 로드맵으로 미룬다.

### 1-b. 스트리밍 실시간 미리보기: iframe + 빌드 즉시 반영 (+ Visual Edits는 HMR)

- **확인된 내용**: 에디터 우측에 **라이브 미리보기(iframe)**가 있고, 코드 변경이 즉시 반영된다. 공식 문서는 "It updates as Lovable builds, so you can watch changes appear"라고 설명하며, 미리보기를 "항상 최신 작업을 실행하는 비공개 스테이징"으로 정의한다(퍼블리시된 공개 스냅샷과 구분). 출처:
  - https://docs.lovable.dev/features/projects/preview
- **확인된 내용(Visual Edits 기술 방식)**: 공식 블로그 "How we built the Visual Edits feature"에서 다음을 공개했다: (1) 브라우저에서 시각↔코드 양방향 매핑(클릭한 요소 ↔ JSX 위치), (2) **클라이언트 측 AST + Tailwind 생성**으로 선언적 코드 변경, (3) 네트워크 왕복 없이 DOM에 낙관적(optimistic) 반영, (4) **수정된 줄만 diff 계산** → 클라우드 환경에 푸시 → **HMR 이벤트**로 세션에 즉시 반영. 출처:
  - https://lovable.dev/blog/visual-edits
- **추정(비공식 유출 기반)**: 유출된 것으로 알려진 시스템 프롬프트(gist/깃허브 미러)에는 "사용자는 우측 iframe에서 라이브 프리뷰를 본다", "모든 수정은 즉시 빌드·렌더되므로 부분 완성 상태로 두지 마라", 파일 업데이트 시 전체가 아닌 변경분만 `lov-write`로 쓰고 나머지는 `// ... keep existing code`로 생략(뒤단 빠른 모델이 전체 파일 복원)한다는 지침이 있다. **Lovable 공식 발표가 아니므로 그대로 믿지 말고 참고용으로만 볼 것.** 출처:
  - https://gist.github.com/oguzdelioglu/c8c25b4293cbf44354950f28cab77e47 (비공식 미러)
  - https://github.com/x1xhlol/system-prompts-and-models-of-ai-tools/blob/main/Lovable/Agent%20Prompt.txt (비공식 모음)
- **확인 불가**: Lovable이 **WebContainer / StackBlitz / Sandpack 같은 브라우저 내 실행 기술**을 쓴다는 공개 언급은 찾지 못했다. 반대로 Lovable 공식 npm 패키지 `@lovable.dev/lovite` 설명에는 "Lovable's sandbox environment runs your Vite dev server behind a proxy"라고 되어 있어, 미리보기는 **서버 측 샌드박스의 Vite dev 서버를 프록시 경유로 보여주는 구조**로 보인다(브라우저 내 Node 실행이 아님). 출처:
  - https://www.npmjs.com/package/@lovable.dev/lovite
- **우리 프로젝트 적용 가능성**
  - iframe 스트리밍 미리보기 뼈대 → **가능**. 팀B 시안 링크 페이지·팀C 미리보기에 이미 iframe 개념이 있으며, "생성 중 변경분을 점진 표시"는 SSE/폴링으로 받은 HTML을 iframe에 순차 반영하는 정도로 축소 구현할 수 있다. 서버 측 샌드박스+프록시 구조는 우리(백엔드가 산출물을 직접 서빙)와 같은 방향이라 철학이 맞는다.
  - 브라우저 내 WebContainer 실행 → **무리**. 근거 자료도 없고(확인 불가), SharedArrayBuffer/COOP·COEP 헤더·대용량 WASM 등 마감 내 검증할 것이 너무 많다. 서버 측 렌더+iframe 방식을 유지한다.

---

## 2. 배포 방식: 생성 코드를 어떻게 실제 URL로 만드는가

- **확인된 내용(자체 호스팅이 기본)**: 에디터 우측 상단 **Publish 버튼(또는 채팅으로 "Publish my app")** → 보안 스캔 → `*.lovable.app` URL(커스텀 가능)로 배포, **HTTPS 자동**, 전 세계 전송. 핵심은 **"퍼블리시할 때마다 현재 프로젝트의 스냅샷(snapshot)을 배포"**하며, **퍼블리시 이후의 작업은 라이브 사이트에 영향을 주지 않고, 다시 Publish해야 반영**된다는 점이다. 출처:
  - https://docs.lovable.dev/features/publish.md (정확히는 https://docs.lovable.dev/features/publish)
  - http://docs.lovable.dev/features/publish
  - https://docs.lovable.dev/features/hosting ("Publishing takes a snapshot of your project and puts it live")
- **확인된 내용(인프라 실체)**: 구 스택은 정적 SPA를 CDN(Cloudflare Pages)에 올리는 방식이었고, 신 스택(TanStack Start 이후)은 **Cloudflare Workers**에서 빌드·서빙되는 것으로 공식 블로그가 밝히고 있다. 출처:
  - https://lovable.dev/fr/blog/building-apps-using-tanstack-start ("Runtime | Static hosting (Cloudflare Pages) | Cloudflare Workers")
- **확인된 내용(외부 연동은 GitHub 경유)**: Lovable 안에 "Netlify/Vercel로 배포" 버튼은 없고, **GitHub 양방향 동기화**를 거쳐 외부 호스팅(Netlify, Cloudflare Pages, Vercel, AWS/GCP/Azure, 자체 Docker/K8s)으로 내보내는 구조다. Lovable 편집 내용이 main에 커밋되고, GitHub에 직접 푸시한 내용도 Lovable로 역류한다. 백엔드(Lovable Cloud/Supabase)는 프론트와 독립적으로 옮길 수 있다. 출처:
  - https://docs.lovable.dev/integrations/github.md (정확히는 https://docs.lovable.dev/integrations/github)
  - https://docs.lovable.dev/tips-tricks/deployment-hosting-ownership
  - https://www.netlify.com/knowledge-base/deploy-your-lovable-app-to-netlify/
- **확인된 내용(백엔드)**: 기본 백엔드는 **Lovable Cloud(내부적으로 Supabase/Postgres 기반)**이며, 별도 Supabase 프로젝트 연결도 지원한다. 프론트 생성과 달리 백엔드는 AI가 Supabase Management API로 프로젝트·테이블·스토리지·RLS·Edge Function을 프로비저닝한다. 출처:
  - https://supabase.com/customers/lovable.md
  - https://supabase.com/blog/lovable-cloud-launch
  - https://docs.lovable.dev/integrations/supabase.md
- **우리 프로젝트 적용 가능성**
  - 스냅샷+재발행 모델 → **가능(강력 추천)**. 지금도 BND-5(deploy)→사람 검토→BND-9(approved만 고객 전송) 구조라 이미 같은 철학이다. 팀B 전송 상태머신("시안전송완료 → 배포전송가능")과 팀C BND-5 `status: ready/failed`에 "스냅샷 고정, 재발행 전까지 라이브 불변" 규칙을 명문화만 하면 된다. 코드 변경 없이 문서 1줄 추가로 끝난다.
  - GitHub 양방향 동기화 → **무리**. 마감 내 OAuth·웹훅·충돌 해결을 검증할 시간이 없고, 요구사항에도 없다. export는 "Download codebase" 수준의 단방향 덤프로 충분하다.
  - Supabase식 백엔드 자동 프로비저닝 → **무리**. 우리 스코프는 정적 산출물 서빙이며, DB/Auth가 요구사항에 없다.

---

## 3. 반복 수정: 후속 요청 시 전체 재생성 vs 부분 diff

- **확인된 내용(모드 분리)**: 채팅에는 **Build 모드(프로젝트에 직접 변경, 기본값)**와 **Plan 모드(코드를 건드리지 않고 논의·계획만)**가 있다. 드래프트(draft) 상태에서는 요청이 드래프트에만 적용되고, accept/update로 반영한다. 실행 취소(undo), 파일·이미지·커넥터 첨부, 스크린샷 첨부도 지원. 출처:
  - https://docs.lovable.dev/features/projects/chat
- **확인된 내용(Visual Edits = AI 우회)**: 색상·폰트 같은 스타일 다듬기는 AI를 호출하지 않고, 브라우저 내 AST 조작으로 소스를 선언적으로 수정 → diff로 푸시 → HMR로 즉시 반영한다(§1-b). "AI는 (상대적으로) 비싸다"는 것이 이 설계를 한 공개적 이유다. 출처:
  - https://lovable.dev/blog/visual-edits ("Problem 2: AI is still (relatively) expensive", "Diffs are computed to update only precisely modified lines")
- **추정(유출 프롬프트 기반)**: 채팅 기반 코드 수정도 **전체 파일 재작성이 아니라 변경분만 생성**하고(`// ... keep existing code`로 불변부 생략), 뒤단에서 전체 파일을 복원하는 2단계 구조로 보인다. "버튼 색 바꿔줘"가 오면 버튼이 있는 파일의 해당 클래스만 고치는 surgical edit 철학이다. 단, **비공식 유출이므로 'Lovable이 이렇게 한다'고 단정하지 말 것.** 출처: §1-b의 gist/미러와 동일.
- **확인 불가**: 변경 범위 결정(플래너가 파일 목록을 먼저 정하는지, 한 패스로 판단하는지), 컨텍스트 윈도우에 전체 프로젝트를 넣는지 요약만 넣는지, 사용 중인 기반 모델명 등 내부 파이프라인 상세는 공개 자료에서 확인 불가.
- **우리 프로젝트 적용 가능성**
  - surgical diff 규칙(팀C 프롬프트에 1줄 추가) → **가능(오늘 가능)**. 예: "후속 수정 요청 시 전체 HTML을 다시 쓰지 말고, 변경된 요소·섹션만 출력하고 나머지는 원본 유지". Hermes 샌드박스 실행 후에는 변경 전후 diff를 FLOWDOC에 첨부하면 요구 9(Flow 검토 산출물)도 동시에 만족한다.
  - Visual-Edits식 AI 우회(팀B 시안) → **가능**. 시안이 정적 HTML 템플릿이라 Lovable(React AST)보다 오히려 쉽다: 색상 프리셋·폰트 크기 같은 파라미터성 수정은 NIM/Hermes를 호출하지 않고 템플릿 변수 치환 + Playwright 재스크린샷으로 처리. "AI 호출이 필요한 수정 vs 변수 치환으로 끝나는 수정"을 구분하는 분기 1개만 추가하면 된다.
  - Plan/Build 모드 + draft 미리보기 → **부분 가능**. 전체 모드 분리는 무리지만, "고객 확정 전에는 산출물 스냅샷을 건드리지 않고 미리보기(draft)만 갱신" 규칙은 지금 승인 게이트(⑦)와 스냅샷 모델로 커버된다. 별도 구현 없이 운영 규칙으로 못박는다.
  - 파일 단위 HMR식 부분 새로고침(React 수준) → **무리**. 단일 정적 HTML 산출물에는 HMR 개념이 그대로 안 맞고, iframe 전체 리로드로 충분하다.

---

## 4. 적용/무리 판정표 (마감 2026-09-28 기준)

| # | Lovable 방식 | 적용 판정 | 이유 |
|---|---|---|---|
| 1 | 스냅샷 배포 + 수동 재발행 | **가능** | BND-5/BND-9 게이트와 동형. 문서 명문화만으로 적용, 코드 변경 불필요 |
| 2 | 단순 스타일 수정 AI 우회 (Visual Edits) | **가능** | 팀B 정적 템플릿 변수 치환으로 축소 구현 가능. 비용·속도 개선이 큼 |
| 3 | 후속 수정은 surgical diff (전체 재생성 금지) | **가능** | 팀C 프롬프트 1줄 + FLOWDOC diff 첨부로 오늘 적용 가능 |
| 4 | iframe 라이브 미리보기 (서버 샌드박스+프록시) | **가능(축소)** | SSE/폴링 점진 표시 수준으로 축소. WebContainer는 제외 |
| 5 | Build/Plan 모드, draft, undo | **부분 가능** | 운영 규칙(게이트·스냅샷)으로 커버. 전용 모드 UI 구현은 제외 |
| 6 | React+Vite+TS 멀티파일 생성 | **무리** | 계약·빌드·배포 전면 재검증 필요. 해커톤 후 로드맵 |
| 7 | TanStack SSR / Cloudflare Workers | **무리** | 인프라 교체 수준. 정적 서빙 유지 |
| 8 | GitHub 양방향 sync | **무리** | OAuth·충돌 해결 검증 시간 없음. 단방향 덤프로 대체 |
| 9 | Supabase 자동 프로비저닝 백엔드 | **무리** | 스코프 밖(DB/Auth 요구 없음) |
| 10 | 브라우저 내 실행 (WebContainer 등) | **무리** | Lovable 사용 근거 자체가 확인 불가 + 마감 내 검증 불가 |

---

## 출처 목록

- https://lovable.dev/faq/capabilities/tech-stack/lovable-nextjs-support
- https://lovable.dev/fr/blog/building-apps-using-tanstack-start
- https://docs.lovable.dev/features/projects/preview
- https://docs.lovable.dev/features/projects/chat
- https://docs.lovable.dev/features/publish (https://docs.lovable.dev/features/publish.md 리다이렉트 포함)
- https://docs.lovable.dev/features/hosting
- https://docs.lovable.dev/tips-tricks/deployment-hosting-ownership
- https://docs.lovable.dev/integrations/github (https://docs.lovable.dev/integrations/github.md 포함)
- https://docs.lovable.dev/integrations/supabase.md
- https://lovable.dev/blog/visual-edits
- https://www.netlify.com/knowledge-base/deploy-your-lovable-app-to-netlify/
- https://supabase.com/customers/lovable.md
- https://supabase.com/blog/lovable-cloud-launch
- https://www.npmjs.com/package/@lovable.dev/lovite
- (비공식·참고용) https://gist.github.com/oguzdelioglu/c8c25b4293cbf44354950f28cab77e47
- (비공식·참고용) https://github.com/x1xhlol/system-prompts-and-models-of-ai-tools/blob/main/Lovable/Agent%20Prompt.txt
