# 소프트웨어 요구사항 (구현용, SRS)

> 대상: 개발자·구현 세션. SYS(외부 관찰 기준)를 코드·DB·API로 어떻게 만족하는지 정의한다.
> 정본 연결: 외부 기준 `../external/SYSTEM_REQUIREMENTS.md`, REQ 정본 `../hackathon/REQUIREMENTS.md`, 실행 흐름 `../product/FLOWDOC.md`, 결정 `../product/DECISIONS.md`.

## 1. 아키텍처 원칙 (설계 출발점)

- SW-A1: 대화와 코드생성 사이에 확정 PRD 카드를 둔다. 생성 입력은 확정 카드만 (`PRODUCT_ROADMAP.md` §2).
- SW-A2: 모든 상태는 PostgreSQL에 둔다. 인메모리·JSON 파일은 쓰지 않는다.
- SW-A3: 모든 NIM 호출은 `app/llm.py` 단일 진입점. 과부하 시 super→ultra→lightning 폴백, 실패 모델 60초 제외.
- SW-A4: AI는 디자인 명세만 쓰고, 그리기는 승인된 부품 엔진이 한다 (D38). 쪽 전체 HTML 자유 생성 금지 (D31).

## 2. 기능 소프트웨어 요구사항

| ID | 요구 (SW는 ~해야 한다) | 모듈 | SYS |
|---|---|---|---|
| SW-1 | 입구 게이트: 종류 분류(가게·개인·단체·웹서비스)+금지 거절+질문 예산(8·7·8·12) | `app/services/intake.py`, `prd_schema.py`, `app/data/intake_profiles.json` | SYS-4,7 |
| SW-2 | 턴 엔진: 발화→칸 추출(NIM `chat_json`)+근거 검사+다음 질문 1개 선택 | `app/services/prd_engine.py` (`turn`, `extract_detail`) | SYS-1,2,4,5 |
| SW-3 | 저장 차단(W1): `apply_updates`에서 민감정보·전화·시간·가격 검증 실패 시 FILLED 저장 금지, pending 유지, 3회 반복 시 STUCK→PLACEHOLDER. 공유방 PENDING_OWNER 경로도 동일 검사 | `app/services/prd_engine.py` (`_w1_block_reason`), `app/services/validate.py` | SYS-2,3 |
| SW-4 | 리뷰어: 요약 직전 원문↔카드 대조, 원문 인용 확인될 때만 채움 (D34) | `prd_engine.review` | SYS-6 |
| SW-5 | 사례 찾기: 기능 사례집 42+프로필 9 임베딩, 코사인 0.76 기준, 실패해도 대화 계속 | `app/services/rag.py`, `app/llm.py` (`embed`) | SYS-1 |
| SW-6 | 승인 게이트: 1:1 확정 또는 공유방 과반 투표 통과 시에만 진행 | `app/services/rooms.py`, `app/services/chat_flow.py` | SYS-8,9 |
| SW-7 | 견적: 규칙 계산 한 줄 + 베타 무료 (D25). AI 금액 생성 금지 | `app/services/quote.py` (`rule_quote`) | SYS-10 |
| SW-8 | 시안 3안: 카드→부품+토큰 렌더, 역할 고정(정석·분위기·대비, 최소차이 8) | `design_variants.py`, `site_render.py`, `design.py` | SYS-11 |
| SW-9 | 공개: 고른 안 그대로 `/site/<id>/`, 빈칸 감추기, AI 문구 초안(숫자 지어냄 제거) | `chat_flow._publish`, `design.publish_choice`, `app/api/public.py` | SYS-12,13 |
| SW-10 | 게시 검사: 외부 스크립트·외부 폼·자동이동·우회 iframe 5종 차단 (S-5), 서빙 CSP+sandbox 자동검사 (S-2) | `app/services/publish_check.py`, `app/api/public.py`, `app/main.py` (`_split_hosts`) | SYS-14 |
| SW-11 | 직접 편집: 실제 카드 로드·바뀐 칸만 저장·공개본 반영, 방장만 | `app/api/card.py`, `frontend/src/editor/` | SYS-15 |
| SW-12 | 문의: 폼→저장(30일)→채팅방 알림+사장님 카톡, 숨은칸 스팸·IP 10분 5건 제한 | `app/services/inquiries.py`, `kakao_talk.py`, `app/api/inquiries.py` | SYS-16,17 |
| SW-13 | 공유방: 방장 승계·초대링크(기간·목록·폐기)·타이머 경고·10명 상한, member_id 비노출(핸들 12자리) | `app/services/rooms.py`, `app/api/rooms.py` | SYS-18,19 |
| SW-14 | 사진: EXIF 제거·1600px JPEG·시안/공개본 갱신. 메타는 `attachments`표, 파일은 저장소 어댑터(로컬→S3호환) | `app/services/photos.py`, `app/db/models.py` (`AttachmentRow`) | SYS-20 |
| SW-15 | 영상: 유튜브·인스타·네이버TV 링크→영상 카드 | `app/services/video_links.py` | SYS-21 |
| SW-16 | 음성: Parakeet STT(→입력창, 자동전송 없음, 녹음 즉시삭제)+Magpie TTS 듣기+무전기 모드 | `app/services/stt.py`, `tts.py`, `app/api/stt.py`, `tts.py`, `static/voice.js` | SYS-22 |
| SW-17 | 계정: 카카오·구글 OAuth(state+PKCE, `__Host-` 쿠키), 게스트방 계정 귀속, 내 프로젝트 | `app/api/auth.py`, `app/services/auth.py` | SYS-23 |
| SW-18 | 예약 1단계: 공용 `bookings`표·폼 계약·채팅방 확정/거절 (BOOKING_PLAN) | `app/services/bookings.py`, `app/api/bookings.py` | SYS-27 |
| SW-19 | 코드생성(Hermes): 선택 기능, 요청별 Docker `--rm`·`/workspace`만 마운트 | `app/services/codegen.py` | — |
| SW-20 | AI 문구·디자인 명세: 소개 문구 초안(숫자 지어냄 제거)+시안 명세·수정 기록 | `app/services/copywriter.py`, `design_concept.py`, `design_log.py` | SYS-13 |
| SW-21 | 알림·유입 기록: 결정 알림 발송+익명 방문 기록 90일 | `app/services/notify.py`, `funnel.py` | SYS-16, SYS-24 |

## 3. 데이터 요구사항

| 표 | 키 내용 | 보관 |
|---|---|---|
| `rooms`·`sessions`·`chat_turns` | 방·세션·대화 (90일) | SYS-24 |
| PRD 카드 (`sessions.prd`) | 칸 값+상태(FILLED/PENDING/PLACEHOLDER)+근거 | — |
| `attachments` | 사진 메타(id·방·역할·칸·순서·저장위치·삭제표시). 원본 없음 | SYS-20 |
| `inquiries` | 문의 30일 보관 | SYS-16,24 |
| `bookings` | 예약·신청 (BOOKING_PLAN) | SYS-27 |
| `funnel_events` | 익명 유입 기록 90일 | — |
| `generated/<id>/` | 산출물 파일 (DB 밖, 경로 제한·정제) | SYS-12 |

## 4. 비기능 요구사항

| ID | 요구 | 근거 |
|---|---|---|
| SW-N1 | 대화 응답 p95 5초 (NIM 실측: 추출 3.4초·리뷰 3초·TTS 2.25초·STT 2.5초) | FLOWDOC 실측 |
| SW-N2 | 생성 사이트·시안은 별도 호스트+CSP sandbox, 앱 쿠키·저장소 접근 차단 | SYS-14 |
| SW-N3 | ID 정제(영숫자·하이픈·밑줄), 생성경로 산출물 내 제한, 키는 환경변수만 | 보안절 |
| SW-N4 | 배포 스냅샷 5개+자동 롤백, DB 백업 일 1회+서버밖 복사 | 운영절 |
| SW-N5 | T2 추출 ≥90%·지어냄 0건, T3 시나리오 회귀, wrong 6/6 저장차단 | 평가절 |

## 5. 테스트 매핑

- 단위·엔진: `tests/unit`·`tests/engine` (CI 334개) — SW-1~SW-17 회귀.
- 평가: `evals/` 시나리오 36·추출 60·wrong 6 — SW-2~SW-4 품질 게이트.
- E2E: `tests/e2e/mobile_flow.py` 11단계 (운영 스모크).
