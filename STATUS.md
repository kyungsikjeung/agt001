# 진행 상황 (경영진 확인용)

> 이 문서는 커밋할 때마다 최신 상태로 갱신한다. 전체 시스템 그림은 [README.md](README.md), 정식 요구사항은 [docs/hackathon/REQUIREMENTS.md](docs/hackathon/REQUIREMENTS.md) 참고.

**마감**: 2026-09-28
**최종 갱신**: 2026-09-23
**전략**: 9단계 파이프라인 전체를 얇게(thin vertical slice) 먼저 관통시킨 뒤, 병목 순서(팀A → 팀B → 팀C)로 두껍게 채우는 방식으로 진행 중.

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

## 효율화 계획

[docs/hackathon/EFFICIENCY_PLAN.md](docs/hackathon/EFFICIENCY_PLAN.md) 참고. Top 3 — **전부 적용 완료** (로컬+OCI 양쪽 검증):
1. ✅ 세션 파일 백업 — 재배포해도 대화가 안 끊김을 OCI 실제 재시작으로 검증
2. ✅ NIM 호출 타임아웃(25초) + 견적 폴백 통일 — NIM 장애 시에도 그럴듯한 정적 견적으로 폴백, 500 방지
3. ✅ `scripts/deploy.sh` — rsync+조건부 빌드+헬스체크, 실제 OCI 배포 2회로 검증(최초 빌드/이후 재시작만)

추가로 [docs/hackathon/LOVABLE_RESEARCH.md](docs/hackathon/LOVABLE_RESEARCH.md)에 Lovable(lovable.dev)의 UI생성~배포 방식을 조사해 적용 아이디어 3가지(스냅샷 재발행 모델, 팀B 시안 AI 우회 스타일 수정, 팀C 코드 surgical diff) 정리.

## 신규 기능: 다인원 공유채팅 (진행 중)

여러 명이 하나의 방에서 함께 요구사항을 도출하는 기능. 조사·설계·PM 통합 플랜 확정 완료
([MULTIUSER_CHAT_DESIGN.md](docs/hackathon/MULTIUSER_CHAT_DESIGN.md),
[UIUX_DESIGN_REFERENCE.md](docs/hackathon/UIUX_DESIGN_REFERENCE.md),
[MULTIUSER_PM_INTEGRATION_PLAN.md](docs/hackathon/MULTIUSER_PM_INTEGRATION_PLAN.md)).

- ✅ 카카오톡 그룹채팅 안에서 봇이 직접 동작하는 것은 공식 API로 불가능함을 조사로 확인 — 대신 "우리 웹에 room + 카카오는 초대링크 공유"로 방향 확정
- ✅ **백엔드 구현 완료(D-4)**: `POST /room`(방 생성), `POST /room/<id>/chat`(참여자 메시지), `GET /room/<id>/messages`(증분 조회), 과반 투표 승인 게이트, `ai_status` 브로드캐스트, 방 파일 백업/재시작 복구. 기존 1:1 `/chat`은 무변경(회귀 없음 로컬 검증 완료)
- ⬜ 프론트 UI 구현(D-3): Slack식 발신자 표시+진행카드+투표바, 카카오 초대 링크 연결
- ⬜ end-to-end 검증(로컬+OCI, D-2)

## 다음으로 할 일

- 다인원 공유채팅 프론트 구현 (위 참고)
- 팀B: 시안 템플릿 N종 확장 (지금은 1종 고정)
- ⑱ 사람 최종 검토 단계 설계·구현
- LOVABLE_RESEARCH.md의 적용 가능 아이디어 3가지 실구현 검토
