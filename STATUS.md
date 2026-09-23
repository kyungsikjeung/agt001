# 진행 상황 (경영진 확인용)

> 이 문서는 커밋할 때마다 최신 상태로 갱신한다. 전체 시스템 그림은 [README.md](README.md), 정식 요구사항은 [docs/hackathon/REQUIREMENTS.md](docs/hackathon/REQUIREMENTS.md) 참고.

**마감**: 2026-09-28
**최종 갱신**: 2026-09-23
**전략**: 9단계 파이프라인 전체를 얇게(thin vertical slice) 먼저 관통시킨 뒤, 병목 순서(팀A → 팀B → 팀C)로 두껍게 채우는 방식으로 진행 중.

## 🔗 지금 바로 확인해보세요 (경영진용 라이브 링크)

- **1:1 챗봇**: http://144.24.91.250.sslip.io:8643/
- **다인원 공유채팅(신규)**: http://144.24.91.250.sslip.io:8643/room.html — 링크를 열면 새 방이 자동 생성됩니다. 닉네임 입력 후 "카페 예약 사이트 만들고 싶어요" 같은 요청을 보내보세요.
  - **여러 명이 함께 검증하는 법**: 방에 입장한 뒤 화면 하단 "카카오톡으로 초대하기" 버튼으로 같은 방 링크(`?room=<id>`가 붙은 URL)를 다른 사람에게 보내면, 같은 화면에서 서로의 메시지·투표·AI 진행상태가 실시간(4초 폴링)으로 함께 보입니다. 승인은 참여자 과반이 "승인"을 눌러야 다음 단계(견적)로 넘어갑니다.
  - OCI 실배포본에서 전 구간(입장→요청→투표→견적→시안→코드생성→배포 URL) end-to-end 검증 완료 — 근거: [OCI_ROOM_E2E_VERIFICATION.md](docs/hackathon/OCI_ROOM_E2E_VERIFICATION.md)

## 한눈에 보기

| 단계 | 담당 | 상태 |
|---|---|---|
| ① 고객 채팅 | 팀A | ✅ 완료 (웹 위젯) |
| ③ RAG (기존요구 확인) | 팀A | ✅ 완료 (실제 NIM 임베딩 코사인 유사도) |
| ⑥ 질의 (3안+추천) | 팀A | ✅ 완료 (NIM 실시간 생성) |
| ⑦ 승인 게이트 | 팀A | ✅ 완료 (실제 승인/거절 인터랙션) |
| ⑧ 견적 | 팀A | ✅ 완료 |
| ⑨ UI 시안 생성 | 팀B | ✅ 완료 (정적 HTML 템플릿 렌더링 + 헤드리스 브라우저 실제 스크린샷. 템플릿은 아직 1종) |
| ⑩ 시안 링크 | 팀B | ✅ 완료 (`/design/<id>` 실제 서빙, 견적 근거까지 노출) |
| ⑪ 카카오톡 공유 | 팀B | ✅ 완료 (배포 링크는 실사용자 테스트 검증됨, 시안 링크 공유는 로컬 검증 완료) |
| ⑫~⑯ 스펙→코드생성 (Hermes) | 팀C | ✅ 완료 (Docker 샌드박스 격리, 로컬 end-to-end 검증 완료) |
| ⑰ 배포 | 팀C | ✅ 완료 (백엔드가 산출물을 `/site/<id>/`로 직접 서빙, 실제 접속 가능한 URL) |
| ⑱ 사람 최종 검토 | — | ⬜ 미착수 |

범례: ✅ 실구현 완료 · 🟡 스텁(동작은 하나 가짜/임시) · ⬜ 미착수

## 인프라 / 배포

| 항목 | 상태 |
|---|---|
| 로컬 개발환경 (Docker Compose, Hermes+NIM) | ✅ 완료 |
| OCI(Oracle Cloud) 무료 티어 배포 | ✅ 완료 — 실제 서비스 URL로 접속 가능 |
| 비용 모니터링 | ✅ 완료 — 현재까지 $0 (Always Free 범위 내) |
| 팀C 코드생성 보안 격리 (Docker 샌드박스) | ✅ 완료 — 로컬 + OCI 양쪽에서 실제 코드 생성 결과물 확인 |

## 최근 완료된 작업

- 팀C Hermes 코드생성을 Docker 컨테이너로 격리 (기존에 호스트 파일시스템에 임의로 쓰는 보안 문제 발견 → 수정)
- `/chat` 전체 플로우(인사→요구사항→승인→견적→코드생성→완료)를 로컬에서 end-to-end로 실제 검증
- 카카오톡 공유 기능 실사용자 테스트 성공
- 견적(⑧)을 자유 텍스트에서 구조화된 JSON(A/B/C 옵션 + 추천)으로 변경
- 팀B UI 시안 생성기(⑨) + 시안 확인 페이지(⑩) 실구현 — 견적 승인 후 코드생성 전에 실제 시안 페이지를 먼저 만들어 고객에게 보여줌
- 팀B 카카오 미리보기 이미지를 헤드리스 브라우저(Playwright) 실제 스크린샷으로 교체
- 팀C 배포(⑰) 실구현 — 코드생성 산출물을 백엔드가 `/site/<id>/`로 직접 서빙 (가짜 URL 제거)
- UI 반응형(모바일/태블릿/데스크톱) 대응 완료 — 챗봇 위젯, 팀B 시안 템플릿, 팀C Hermes 코드생성 프롬프트 3곳 모두 적용 (OpenCode 위임 → 검토 후 커밋)
- 반응형 대응을 OCI 실제 배포본에도 반영하고 end-to-end 검증 — 이 과정에서 배포용 이미지에 `docker.io`만 있고 CLI 바이너리(`docker-cli`)가 빠져 있던 버그를 실측 발견·수정 (지금까지 OCI에서는 팀C 코드생성이 항상 "docker 없음"으로 스텁 폴백되고 있었음)
- [조사] 회원가입/로그인 도입 여부 판단 ([AUTH_DB_COST_DECISION.md](docs/hackathon/AUTH_DB_COST_DECISION.md)) — 결론: **No-Go (마감 전 착수 금지)**. 공수 2~3일 + 보안 부채가 잔여 일정과 정면 경합. 마감 후 백로그 1순위(최소 범위: 결과 저장만 회원 + 카카오 로그인 + SQLite)로 이관
- [조사] PM 다음 전략 ([PM_NEXT_STRATEGY.md](docs/hackathon/PM_NEXT_STRATEGY.md)) — 결론: 데모가 죽는 순서대로. P0는 다인원 공유채팅 OCI e2e 검증 + STATUS.md 갱신, P1은 ⑱ 설계, 마감 전 금지 목록(로그인/WebSocket/React 전환 등) 재확인
- [조사] 무중단 배포·롤백 ([DEPLOYMENT_STRATEGY.md](docs/hackathon/DEPLOYMENT_STRATEGY.md)) — 결론: blue-green은 기술적으로 가능하나 마감 전 도입 비권장. 당장은 `deploy.sh`에 배포 전 스냅샷+`rollback.sh` 최소 구현(작업량 하·$0) + 발표 시간대 배포 금지를 권장. 모든 방향 OCI Always Free 내 $0 가능
- [조사] 카카오톡 연동 검증 계획 ([KAKAO_VERIFICATION_PLAN.md](docs/hackathon/KAKAO_VERIFICATION_PLAN.md)) — 결론: `room.html`의 Error 4019는 `file://`로 직접 열어서 생긴 착시 버그가 유력(확정 아님). `file://` vs 로컬 서버 vs OCI 3-way 대조 검증 절차 + 판정 매트릭스 수록. `*.html`은 반드시 서버 URL로 접속할 것

## 효율화 계획

[docs/hackathon/EFFICIENCY_PLAN.md](docs/hackathon/EFFICIENCY_PLAN.md) 참고. Top 3 — **전부 적용 완료** (로컬+OCI 양쪽 검증):
1. ✅ 세션 파일 백업 — 재배포해도 대화가 안 끊김을 OCI 실제 재시작으로 검증
2. ✅ NIM 호출 타임아웃(25초) + 견적 폴백 통일 — NIM 장애 시에도 그럴듯한 정적 견적으로 폴백, 500 방지
3. ✅ `scripts/deploy.sh` — rsync+조건부 빌드+헬스체크, 실제 OCI 배포 2회로 검증(최초 빌드/이후 재시작만)

추가로 [docs/hackathon/LOVABLE_RESEARCH.md](docs/hackathon/LOVABLE_RESEARCH.md)에 Lovable(lovable.dev)의 UI생성~배포 방식을 조사해 적용 아이디어 3가지(스냅샷 재발행 모델, 팀B 시안 AI 우회 스타일 수정, 팀C 코드 surgical diff) 정리.

회원가입/로그인: [docs/hackathon/AUTH_DB_COST_DECISION.md](docs/hackathon/AUTH_DB_COST_DECISION.md)에서 조사 완료 — 결론 **No-Go (마감 전 착수 금지)**. 게스트 우선 흐름에 인증을 붙이려면 DB(SQLite 최소)+claim API+로그인 UI가 필요해 공수 2~3일이 잔여 일정과 경합. 마감 후 백로그 1순위(안 A: 방은 비회원 그대로·결과 저장만 회원 + 카카오 로그인)로 이관.

## 신규 기능: 다인원 공유채팅 (핵심 구현·검증 완료)

여러 명이 하나의 방에서 함께 요구사항을 도출하는 기능. 조사·설계·PM 통합 플랜 확정 완료
([MULTIUSER_CHAT_DESIGN.md](docs/hackathon/MULTIUSER_CHAT_DESIGN.md),
[UIUX_DESIGN_REFERENCE.md](docs/hackathon/UIUX_DESIGN_REFERENCE.md),
[MULTIUSER_PM_INTEGRATION_PLAN.md](docs/hackathon/MULTIUSER_PM_INTEGRATION_PLAN.md)).

- ✅ 카카오톡 그룹채팅 안에서 봇이 직접 동작하는 것은 공식 API로 불가능함을 조사로 확인 — 대신 "우리 웹에 room + 카카오는 초대링크 공유"로 방향 확정
- ✅ **백엔드 구현 완료(D-4)**: `POST /room`(방 생성), `POST /room/<id>/chat`(참여자 메시지), `GET /room/<id>/messages`(증분 조회), 과반 투표 승인 게이트, `ai_status` 브로드캐스트, 방 파일 백업/재시작 복구. 기존 1:1 `/chat`은 무변경(회귀 없음 로컬 검증 완료)
- ✅ **프론트 UI 구현 완료(D-3)**: `static/room.html`(305줄, 커밋 `4bb017e`) — Slack식 발신자 표시+아바타, AI 진행상태 배너(`ai_status`), 과반 투표바, 카카오 초대 버튼. 로컬 브라우저 실측(입장→투표→견적→코드생성→배포 URL, 중복 메시지 없음) 완료
- ✅ **end-to-end 검증 완료 (로컬 + OCI 양쪽)** — OCI 실배포본에서 curl 실측으로 9단계 전 구간(입장→요청→과반투표 승인→견적→진행→시안 200→GET 폴링만으로 GENERATING→DONE 전이→배포 URL 200 + Hermes 실콘텐츠) 확인. 근거: [OCI_ROOM_E2E_VERIFICATION.md](docs/hackathon/OCI_ROOM_E2E_VERIFICATION.md)

## 다음으로 할 일

([PM_NEXT_STRATEGY.md](docs/hackathon/PM_NEXT_STRATEGY.md) Top 3 — "데모가 죽는 순서대로")

1. ✅ 다인원 공유채팅 OCI end-to-end 검증 — 완료(위 참고)
2. ✅ STATUS.md 갱신 (다인원 프론트+OCI 검증 완료 반영, 경영진용 라이브 링크 추가)
3. ⑱ 사람 최종 검토(REQ-REVIEW-001) 설계 착수 — 설계 문서 완료: [REVIEW_GATE_DESIGN.md](docs/hackathon/REVIEW_GATE_DESIGN.md) (구현은 아직)
