# 모션 라이브러리 조사·사용 계획 (MOTION_PLAN)

> 2026-09-28 (KST). 대표 요청: "모션 애니메이션 라이브러리를 조사해서 어떻게 쓸지 계획".
> 전제: 시안은 스크립트가 막혀 있다(CSP `sandbox`, 시안 주소는 `form-action 'none'`). 공개본은 스크립트를 허용하지만 렌더러는 스크립트를 내보내지 않는다(D31). 라이선스는 MIT·Apache-2.0·OFL만 쓴다.
> 관련: [DESIGN_FIT_PLAN](DESIGN_FIT_PLAN.md) §10, `templates/site.css` 끝의 "모션 토큰" 블록.

## 0. 결론

**생성 사이트는 CSS 네이티브 모션을 쓰고, JS 라이브러리는 쓰지 않는다.** 이유는 세 가지다.

1. 시안은 스크립트가 돌지 않는다. JS 모션은 사장님이 고르는 화면에서 보이지 않는다.
2. 2026년 기준으로 필요한 효과(스크롤 나타내기, 안내창 등장, 눌림, 자동 흐름)를 CSS가 대부분 한다.
3. 스크립트가 없어야 보안(D31)·속도·접근성을 한 곳에서 지킬 수 있다.

**JS 모션은 우리 앱(React 채팅·시안 고르기 화면)에만 쓴다. 후보는 Motion(MIT)이다.**

## 1. 조사 결과

| 후보 | 라이선스 | 크기·성격 | 판정 | 근거 |
|---|---|---|---|---|
| **CSS 스크롤 연동 애니메이션** (`animation-timeline: view()/scroll()`) | 표준 | 0KB. 스크롤 위치에 맞춰 나타남·진행 | **채택** (지원하지 않는 브라우저에서는 가만히 보임) | Chrome·Edge 115+, Safari 26(2025-09)부터 지원. Firefox는 2026-06 기준 정식판에서 아직 설정(flag) 뒤에 있음 |
| **@starting-style / :target / 키프레임** | 표준 | 0KB. 등장 효과, 스크립트 없는 안내창 | **채택** | @starting-style: Chrome 117·Firefox 129·Safari 17.5 |
| **View Transitions (문서 간)** | 표준 | 0KB. 쪽 이동 전환 | 보류 (한 쪽짜리 사이트라 이득 작음) | Chrome 126+·Safari 18.2+, Firefox 정식판 미지원 |
| **Motion** (motion.dev, 옛 Framer Motion) | **MIT** | `inView` 약 0.5KB, `animate` 미니 2.3KB. React용 있음 | **앱(React)에만 채택**. 생성 사이트는 필요할 때 공개본 전용 보강 후보로만 둔다 | MIT·되돌릴 수 없는 라이선스라고 명시 |
| **GSAP** | Webflow "Standard License" (오픈소스 아님) | 강력하고 무료 | **제외** | "코드 없이 시각 애니메이션을 만드는 도구에서 Webflow와 경쟁하는 용도"를 금지. 우리 제품(코드 없는 사이트 제작)과 충돌할 위험. 우리 라이선스 규칙(MIT·Apache·OFL)에도 어긋남 |
| **Anime.js v4** | MIT | 범용 JS 엔진 | 제외 (Motion과 겹침) | — |
| **Embla Carousel** (+autoplay) | MIT | 캐러셀 | 보류 (CSS scroll-snap과 마퀴로 충분) | 공개본에 스와이프 자동 넘김이 꼭 필요해지면 다시 본다 |
| **dotLottie web** | MIT | Rust·WASM 플레이어, 엔진 약 500KB를 CDN에서 받음 | 제외 (무겁고 외부 요청) | — |
| Lenis(부드러운 스크롤)·AOS | MIT | 스크롤을 가로챔 / CSS와 겹침 | 제외 (휴대폰 기본 스크롤감과 접근성을 해침) | — |

## 2. 모션 토큰 (site.css에 적용함)

| 토큰 | 값 | 쓰는 곳 |
|---|---|---|
| `--motion-fast` | 140ms | 눌림, 화살표 이동 |
| `--motion-base` | 240ms | 칩·색 전환, 배경 흐림 |
| `--motion-slow` | 420ms | 안내창, 사진 확대 |
| `--motion-ease-out` | `cubic-bezier(.2,.8,.2,1)` | 대부분 |
| `--motion-ease-spring` | `linear()` 스프링(지원하지 않는 곳은 `cubic-bezier(.34,1.4,.64,1)`) | 안내창 등장, 시간 칩 선택 |

나중에는 안마다 **모션 성격**(`calm`·`lively`·`none`)을 명세 토큰으로 두고, D38 명세 쓰기에서 고르게 한다(3단계).

## 3. 모션 원형 (이것만 쓴다)

| # | 원형 | 방식 | 적용 부품 |
|---|---|---|---|
| M1 | 스크롤 나타내기 | `animation-timeline: view()` + `@supports` | 모든 섹션 (기존) |
| M2 | 첫 화면 느린 확대(켄번즈) | 키프레임 18초 | 첫 화면 사진 (기존) |
| M3 | 자동 흐름(마퀴) | 키프레임, 올려놓으면 멈춤 | 사진첩 마퀴 (기존) |
| M4 | 눌림·들림 | `:active` scale, `(hover:hover)`에서만 들림 | 버튼, 담기, 담당자 카드 |
| M5 | 아래에서 올라오는 안내창 | `:target` + 키프레임 스프링 | 주문 준비 중 안내 (D53⑤) |
| M6 | 하단 바 등장 | `animation-timeline: scroll(root)` 0~45vh | 하단 행동 바 |
| M7 | 선택 칩 | `:checked + label` 색·크기 전환 | 디자이너·시간 선택 |
| M8 | 위치 표시 맥박 | 무한 키프레임(2.4초) | 예시 지도 핀 |

**규칙**

- `transform`·`opacity`만 움직인다(레이아웃 흔들림 0).
- 움직임이 끝난 상태가 기본값이다. 모션을 지원하지 않거나 끈 환경에서도 내용이 다 보인다.
- `prefers-reduced-motion: reduce`이면 전부 끈다. 무한 모션(M3·M8)은 이 경우 멈춘다.
- 한 화면에서 무한 모션은 2개까지다.

## 4. 사용 계획

| 단계 | 할 일 | 상태 |
|---|---|---|
| 1 | 모션 토큰 + 원형 M4~M8을 적합성 부품에 적용 | **완료 (2026-09-28)** |
| 2 | 적합성 채점(`draft_fit`)에 모션 검사 추가: 원형 밖 `@keyframes` 금지, `prefers-reduced-motion` 대응, `transform`·`opacity` 외 속성 애니메이션 금지 | 2단계 |
| 3 | 명세 토큰 `motion: calm/lively/none`: 3안의 성격에 맞춰 원형 조합을 바꾼다(D43 ③대비 = lively) | 3단계 |
| 4 | 앱(React): `motion` 패키지로 시안 3안 카드 → 전체 화면 전환, 채팅 말풍선 등장. 번들 목표 +5KB 이하(`LazyMotion`) | 3~4단계, OpenCode |
| 5 | Firefox에서 스크롤 나타내기를 꼭 보여야 하면 공개본에만 Motion `inView`(0.5KB)를 플랫폼 파일로 붙인다(시안 제외) | 필요할 때만 |

## 출처

- [GSAP Standard License](https://gsap.com/community/standard-license/) · [Webflow: GSAP 무료화](https://webflow.com/blog/gsap-becomes-free)
- [Motion: GSAP vs Motion](https://motion.dev/docs/gsap-vs-motion) · [Motion inView](https://motion.dev/docs/inview) · [Motion FAQ(라이선스)](https://motion.dev/docs/faqs)
- [Can I use: animation-timeline scroll()](https://caniuse.com/mdn-css_properties_animation-timeline_scroll) · [Scroll-driven animations 2026 가이드](https://cssawwwards.com/blog/css-scroll-driven-animations-guide-2026)
- [Chrome: cross-document view transitions](https://developer.chrome.com/docs/web-platform/view-transitions/cross-document) · [What's New in CSS 2026](https://modern-css.com/whats-new-in-css-2026/)
- [Anime.js (GitHub, MIT)](https://github.com/juliangarnier/anime) · [Embla autoplay](https://www.embla-carousel.com/docs/plugins/autoplay) · [dotlottie-web](https://github.com/lottiefiles/dotlottie-web)
