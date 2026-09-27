# 디자인 품질 개선 로그 (2026-09-28)

> 요구사항 → 중간 시안 품질이 목표(첼로 4안·Paper·Awwwards/Dribbble·할리스급)에 못 미친다는 지적에서 시작.
> 원칙: D31(AI 직접 HTML 금지)·D26(사실 금지) 유지, 무JS·CSP sandbox·휴대폰 우선 유지, MIT/Apache-2.0/OFL만 사용.

## 1. 사용자 문의 로그

| # | 문의 | 답·산출 |
|---|---|---|
| 1 | Stitch 수준 이미지 퀄리티 올리는 방법? | 병목 4개 진단(flash 모델·한줄 프롬프트·q85 압축·SVG 폴백), 0~3단계안 |
| 2 | 오픈소스 참조 시안 보드(Stitch 시스템 보드) | Tailwind값=스크린샷 색과 일치 확인, A안(램프+보드) 제안 |
| 3 | AAOS 대시보드 3종 세트 방안? | 설계시스템+화면+구현가이드 매핑, car-ui-lib·M3 참조안 |
| 4 | 디스플레이 검사앱(Industrial Mono) 레퍼런스 | 사진 없이 토큰+부품만으로 재현 가능 판정, dark·차트·표 제안 |
| 5 | 중간(요구사항→웹사이트) 시안 품질이 핵심임을 명확화 | P0(배경 기본값+스켈레톤+image_style) 제안 |
| 6 | 첼로 4안급 시안 요구 (Paper) | 사진 1벌×CSS 5처리가 D31과 합치, 3건 필요 정의 |
| 7 | 5썸네일 줌인 | 안별 매핑표(01웜/02볼드/03아치/04다크) |
| 8 | 중간단계 품질 리서치 + Paper 온보딩 | 4트랙 병렬 리서치 → P0/P1/P2 종합 |
| 9 | 오픈소스 구성+라이선스+paper.design 확인 | Paper MCP·토큰 docs 확인, MIT/OFL 구성표 |
| 10 | 로컬 HTML 즉시 테스트 환경 | `draft_lab` 방식 제안 |
| 11 | 요구사항→시안 즉시 형식 + 계속 개발 가능? | 서브 방식 + 목표 반복 방식 확답 |
| 12 | 입력·검증·메트릭 완비 후 목표까지 개발 가능? | 12건·메트릭표 확답 |
| 13 | 시작 승인 | 루프 착수 |
| 14 | 반응형 필수 | 390 1열·760 2열 고정 제약, 넘침 메트릭 추가 |
| 15 | Awwwards 참조 고도화 | 평가기준(40/30/20/10) 확인, 모션 범위(=CSS-only) 선언 |
| 16 | OFF+BRAND Lando Norris(offform) | 볼드 타이포+모션+속도, 타이포·속도만 이식 |
| 17 | 수상작 평가 프레임(Nielsen·Jakob·스퀸트 등) | 휴리스틱→자동검사 매핑(single CTA·앵커·순서·select) |
| 18 | Dribbble awards + chrome MCP 언급 | Dribbble 직fetch 차단 확인, 결산기사로 패턴 추출 |
| 19 | chrome MCP로 학원 예시 확인? | 로컬 실물 렌더+캡처로 대체 (`/tmp/draft_lab`) |
| 20 | 시안들 확인 요청 | 12종 갤러리+72 캡처 생성 |
| 21 | 목업 이미지 생성? | `make_mockup_pack.py` + 자동 배선 |
| 22 | 디자인 불만+프롬프팅/코드 에이전트/엔진 문제+논문 조사 | 3트랙 논문 리서치, D31 천장 진단, A/B 처방 |
| 23 | Confetti 카피 프롬프트 읽기 | 디스커버리-우선 3점 추출 → A1 적용 |
| 24 | A부터 순차적 | A1→A4 실행 |
| 25 | 샘플 폴더+index.html | 12종 갤러리 생성 |
| 26 | 바이브코딩 파이프라인+스킬+목적-fit(내비·캐러셀·분위기·전환·모션) | 2트랙 리서치(6도구·12스킬) |
| 27 | 로고·스크롤·자동캐러셀·디테일 | 무JS 3종 구현 착수 |
| 28 | Dribbble hiring 품질 | 스티키 내비·3단 카드·반복 CTA 패턴 추출 |
| 29 | 할리스 캐러셀 동작·주기·반응형 | bxSlider fade+auto(4초) 확인, 매핑표 |
| 30 | Hollys crownOrder 모바일, 목적-fit 매력 | 반응형 통과 선언, 매력·목적 집중 합의 |

## 2. 작업 로그 (코드 변경)

| 영역 | 파일 | 내용 |
|---|---|---|
| P0 사진 | `app/services/design_variants.py` | photo-first(`/art` 기본, text-only 제거), v3 `arch`, 안별 `image_style`, 거리 +1, `_build_navbar`+`_mock_path` |
| P0 후처리 | `app/services/photos.py` | `_clean_ai_image`(1920·q90·샤픈, 업로드 q85와 분리) |
| P0 프롬프트 | `app/services/ai_images.py` | 촬영지시+슬롯 규격, `imageConfig`(hero 16:9·2K), `_model_for` 슬롯 라우팅 |
| P2 모델 | `app/config.py` | `GEMINI_IMAGE_MODEL_HERO` (미지정=기본, ID는 체크 스크립트로 실측) |
| 목업팩 | `scripts/make_mockup_pack.py` | 30장 배치 생성→`templates/art/mock-*`, 자동 우선 사용 |
| A1 문구 | `app/services/copywriter.py` | 디스커버리 브리프(분위기·덧붙임·기능답변)+고민-우선+수식 금지 |
| A2 매핑 | `app/services/design_concept.py` | 크게/작게/어둡게 등 측정값 매핑 확장 |
| A3 락 | `design_concept.py`+`chat_flow.py` | 고른 안 색·글꼴 락, 이후 수정은 유지+안내 |
| A4 검증 | `app/services/design.py` | `_verify_html`+1회 재생성(기본 그림 폴백) |
| 내비·모션 | `navbar--main`·`gallery--marquee` 신규, `site_render.py` 전역 내비+`items_twice`, `site.css` 모션팩(스티키·켄번즈·마퀴·호버·노치), `viewport-fit`+`theme-color` | — |
| 메트릭 | `scripts/draft_corpus.py`(12건), `scripts/draft_score.py`(21개), `scripts/draft_academy_preview.py`(갤러리+캡처) | 베이스 4FAIL → 21/21 PASS |
| 테스트 | 2건 기대값 갱신(photo-first), `test_model_routing_hero_override` 신규 | DB 부재로 로컬은 동등 재현, CI 위임 |

## 3. 검증 상태

* `draft_score`: 21/21 PASS (사진·SVG·3안 차이·문구·CTA·대비·보안·AI·휴리스틱·내비·마퀴·넘침).
* 기존 단위 테스트: 로컬 PG·Docker 부재로 미실행. 수정 테스트 2건+신규 1건은 동일 조건 스크립트 재현 통과, CI에서 전체 확인 필요.
* 실물: `/tmp/draft_lab/index.html` (12종×3안 HTML + 72 캡처).

## 4. 남은 것 (P1·B)

* 상품 `photo-grid` 빈 사진 박스, 안별 kicker/headline, 다크 1종, 목업팩 30장 서버 생성, 공지·이벤트 목록 섹션, B트랙(코드 경로 검증 루프).
* `site_render.py`·`site.css`·`test_site_render.py`의 기존 작업전 변경분은 손대지 않음(본 로그 범위 밖).
