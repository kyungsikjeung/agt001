# 양방향 추적표 (요구→설계→코드→시험)

> 위치: L1 외부 / 상태: 정본 / 버전: 1.0 (2026-09-27)
> 용어: `GLOSSARY.md`의 쉬운말을 쓴다 (괄호 안 내부명 1회 병기).
> ASPICE 대응: SYS.2·SWE.1 양방향 추적성 + 일관성. 모든 요구는 아래 표에서
> 외부기능(F) ↔ 시스템요구(SYS) ↔ 소프트웨어요구(SW) ↔ 코드 ↔ 시험으로 양쪽을 오갈 수 있어야 한다.
> 추적 끊김(GAP)은 숨기지 않고 §4에 적는다.

## 추적 규칙

1. ID 체계: `F`(외부 기능) · `SYS`(시스템) · `SW`(소프트웨어) · `REQ`(개발 정본) · `G`(reqpipe 정본).
2. 새 요구 추가 시 이 표에 행을 먼저 넣고 코드를 나중에 짠다. 표에 없는 요구의 코드는 받지 않는다.
3. 상태값: `운영` (동작 확인) · `진행` (구현 중) · `미착수` (설계만) · `보류` (베타 뒤).
4. 변경 시 `docs/product/DECISIONS.md`에 D번호를 남기고 이 표의 해당 행을 고친다.

## 1. 정방향 추적 (외부 기능 → 시험)

| 외부 기능 | SYS | SW | 코드 | 시험 | REQ 정본 | 상태 |
|---|---|---|---|---|---|---|
| F-1 채팅 요구 정리 | SYS-1,2,4,5,6 | SW-2,4,5 | `prd_engine.py`, `rag.py` | engine 208·T2·T3 | REQ-CHAT·INTAKE·ASK | 운영 |
| F-1 틀린 값 막기 | SYS-2,3 | SW-3 | `prd_engine._w1_block_reason`, `validate.py` | `test_validate` 50·wrong 6/6 | REQ-VALIDATE | 운영 |
| F-1 금지 거절 | SYS-7 | SW-1 | `intake.py` | `test_intake_gate` | REQ-INTAKE | 운영 |
| F-2 음성 | SYS-22 | SW-16 | `stt.py`, `tts.py`, `voice.js` | 운영 실측 (STT 2.5초·TTS 2.25초) | — | 운영 |
| F-3 사진·영상 | SYS-20,21 | SW-14,15 | `photos.py`, `video_links.py` | `test_photos` (1건 타 트랙 잔여 실패) | — | 운영 |
| F-4 시안 3안 | SYS-11 | SW-8 | `design_variants.py`, `site_render.py` | site-quality 36쪽 | REQ-DESIGN | 운영 |
| F-5 공개 | SYS-12,13,14 | SW-9,10 | `public.py`, `publish_check.py` | `test_publish_check` 11·mobile 11단계 | REQ-DELIVER·REVIEW | 운영 |
| F-6 문의 알림 | SYS-16,17 | SW-12 | `inquiries.py`, `kakao_talk.py` | 단위 (카톡 실측 대기) | REQ-DELIVER | 운영 |
| F-7 직접 편집 | SYS-15 | SW-11 | `api/card.py`, `frontend/src/editor/` | `CardEditor.test` | D27 | 운영 |
| F-8 공유방 | SYS-8,9,18,19 | SW-6,13 | `rooms.py`, `chat_flow.py` | `test_room_timers`·E2E 5 | REQ-GATE | 운영 |
| F-9 참고 견적 | SYS-10 | SW-7 | `quote.rule_quote` | 단위 | REQ-QUOTE·D25 | 운영 |
| F-10 로그인 | SYS-23 | SW-17 | `api/auth.py` | 운영 확인 (카카오 실계정) | D9·D10 | 운영 |
| F-11 예약 | SYS-27 | SW-18 | `bookings.py` | BOOKING_PLAN 기준 | D32-② | 진행 |
| F-12 앱 설치 | SYS-28 | — (순수 정적 파일, 로직 없음) | `manifest.json`, `sw.js` | 브라우저 확인 | 요구 5 | 운영 |
| F-5 AI 문구 | SYS-13 | SW-20 | `copywriter.py`, `design_concept.py`, `design_log.py` | 단위 | — | 운영 |
| F-6 알림·유입 | SYS-16,24 | SW-21 | `notify.py`, `funnel.py` | 단위 | — | 운영 |

## 2. 역방향 추적 (코드 → 요구)

| 코드 | SW | SYS | 외부 기능 |
|---|---|---|---|
| `intake.py`·`prd_schema.py` | SW-1 | SYS-4,7 | F-1 |
| `prd_engine.py`·`validate.py` | SW-2,3,4 | SYS-1,2,3,5,6 | F-1 |
| `rag.py`·`llm.py` | SW-5 | SYS-1 | F-1 |
| `rooms.py`·`chat_flow.py` | SW-6,13 | SYS-8,9,18,19 | F-8 |
| `quote.py` | SW-7 | SYS-10 | F-9 |
| `design*.py`·`site_render.py` | SW-8 | SYS-11 | F-4 |
| `public.py`·`publish_check.py` | SW-9,10 | SYS-12,13,14 | F-5 |
| `card.py`·`editor/` | SW-11 | SYS-15 | F-7 |
| `inquiries.py`·`kakao_talk.py` | SW-12 | SYS-16,17 | F-6 |
| `photos.py`·`video_links.py` | SW-14,15 | SYS-20,21 | F-3 |
| `stt.py`·`tts.py` | SW-16 | SYS-22 | F-2 |
| `auth.py` | SW-17 | SYS-23 | F-10 |
| `bookings.py` | SW-18 | SYS-27 | F-11 |
| `copywriter.py`·`design_concept.py`·`design_log.py` | SW-20 | SYS-13 | F-5 |
| `notify.py`·`funnel.py` | SW-21 | SYS-16,24 | F-6 |
| `codegen.py` (Hermes, 선택) | SW-19 | — | — |

## 3. 비기능 추적

| SW 비기능 | 시험·증거 | 상태 |
|---|---|---|
| SW-N1 응답 p95 5초 | 추출 3.4초·리뷰 3초·TTS 2.25초·STT 2.5초 (운영 실측) | 만족 |
| SW-N2 sandbox 격리 | 별도 호스트+`test_publish_check` 11 | 만족 |
| SW-N3 ID 정제·키 관리 | `security.py`·단위 | 만족 |
| SW-N4 스냅샷·백업 | `deploy.sh`·`backup_db.sh`+서버밖 복사 | 만족 |
| SW-N5 T2 ≥90%·지어냄 0 / T3 회귀 / wrong 6/6 | T2 90.2%·r5 21/36·wrong 6/6 | 일부 (T3 진행) |

## 4. 추적 끊김 (GAP — 숨기지 않는다)

| ID | 끊김 | 조치 |
|---|---|---|
| GAP-1 | F-11 예약·F-12 앱설치에 SYS 없음 | 해소 (v1.1): SYS-27·SYS-28 부여 |
| GAP-2 | SYS-25 검토 게이트·SYS-26 기기 이어쓰기 → SW 없음 | 미착수·베타 뒤. SYS에 표기 완료 |
| GAP-3 | SW-19 Hermes → SYS·F 없음 (선택 기능) | SYS 부여 없이 유지. 공개본 기본 경로는 시안 우선(D31) |
| GAP-4 | orphan 5개 → SW 매핑 없음 | 해소 (v1.1): SW-20(문구·명세)·SW-21(알림·유입) 부여 |

## 5. 일관성 점검 (요구 간 모순)

`BACKLOG.md` §5 모순표 X-1~X-8이 일관성 점검 대장이다. 해소 원칙: 최신 D결정이 우선, 패자는 표에 "변경"으로 남기고 지우지 않는다.

| 모순 | 판정 (최신) | 반영 |
|---|---|---|
| X-1 문의폼 제외 vs 포함 | D32 포함이 최신 | SYS-16·SW-12 반영 완료 |
| X-2 TTS 보류 vs 듣기 버튼 | 부록 변경이 최신 | SYS-22·SW-16 반영 완료 |
| X-4 RAG 가짜 3개 vs 운영 문구 | M-2 교체 | SW-5 반영 완료 |
| X-6 8질문 vs 종류별 예산 | 종류별 예산이 최신 | SW-1 반영 완료 |
| X-8 확정 1회 vs 2회 게이트 잔재 | D22 합침이 최신 | SYS-8 반영 완료 |

## 6. 커버리지 요약

- F 12개 중 운영 11·진행 1. SYS 28개 중 SW 연결 26·미연결 2(GAP-2).
- SW 21개 중 코드·시험 연결 21 (100%). 단 SW-18은 진행, SW-19는 선택. F-12는 로직이 없어 SW 미부여(정적 파일).
- orphan 코드 0개 (GAP-4 해소).

## 변경 이력

| 버전 | 날짜 | 내용 |
|---|---|---|
| 1.1 | 2026-09-27 | SYS-27·28, SW-20·21 부여. GAP-1·GAP-4 해소 |
| 1.0 | 2026-09-27 | 초판 (F12·SYS26·SW19 추적, GAP 4건) |
