# OCI 다인원 공유채팅(room) E2E 검증 기록

- 검증일시(UTC): 2026-09-23 09:19~09:21 (curl 외부 검증, 코드 수정 없음)
- 대상: http://144.24.91.250:8643 (OCI 실배포본)
- 검증용 방: `dceaf8c3` / requirement: `0b7c29a7` / 멤버: `m1`(검증봇)
- 방법: curl 실측만. SSH 미사용(필요 없었음). 테스트 데이터 정리 안 함(지시대로 유지).

## 결론: 전체 통과 (9단계 모두 정상)

입장→요청→승인(과반투표 1/1)→견적(QUOTED)→진행(GENERATING, design_url 발급)→시안 200→GET 폴링만으로 GENERATING→DONE 전이→배포 URL 200 + Hermes HTML 실콘텐츠 확인까지 끊김 없이 동작했다.
특히 최근 수정 버그( GET /messages 폴링만으로는 DONE으로 안 넘어가던 문제)는 OCI에서도 고쳐진 것이 실측으로 확인됐다 — 추가 채팅 전송 없이 폴링 4회차(약 15초 후)에 DONE 전이.
관찰사항 2건(장애 아님)은 하단 "관찰 및 참고"에 기록.

---

## 1. health 체크 — 서버 생존 확인

실행한 명령:
```
curl -s -w '\nHTTP_CODE:%{http_code}\n' --max-time 15 http://144.24.91.250:8643/health
```

실제 응답:
```
{"status":"ok"}
HTTP_CODE:200
```

판정: 정상. 서버 생존.

## 2. 방 생성 — POST /room

실행한 명령:
```
curl -s -w '\nHTTP_CODE:%{http_code}\n' --max-time 15 -X POST http://144.24.91.250:8643/room
```

실제 응답:
```
{"room_id":"dceaf8c3"}
HTTP_CODE:200
```

판정: 정상. room_id 발급됨. 이후 단계는 전부 `dceaf8c3` 사용.

## 3. 첫 대화 — RAG/요청 접수 확인

실행한 명령:
```
curl -s --max-time 60 -X POST http://144.24.91.250:8643/room/dceaf8c3/chat \
  -H 'Content-Type: application/json' \
  -d '{"member_id":"m1","nickname":"검증봇","message":"카페 예약 웹사이트 만들고 싶어요"}'
```

실제 응답 (POST 본문):
```
{"ai_status":"IDLE"}
```

이어서 상태 조회:
```
curl -s 'http://144.24.91.250:8643/room/dceaf8c3/messages?since=0'
```
응답 요약: `state=AWAIT_APPROVAL`, 메시지 3건(seq0 입장 system, seq1 채팅, seq2 ai_reply "신규 프로젝트 … 요청하신 내용을 검토했습니다. 이 요구사항으로 견적을 진행할까요? (승인/거절로 답해주세요)").

판정: 정상. POST 본문은 상태만 돌려주고 실제 AI 텍스트는 GET /messages로 확인되는 구조(로컬 거동과 동일 패턴). 상태가 IDLE→AWAIT_APPROVAL로 전이됨.
관찰: ai_reply가 과거사례 RAG 매칭형이 아닌 범용 "신규 프로젝트" 템플릿이었음 (장애 아님, 관찰사항에 기록).

## 4. "승인" — AWAIT_APPROVAL → QUOTED 전이 + 과반투표(1명) 확인

실행한 명령:
```
curl -s --max-time 60 -X POST http://144.24.91.250:8643/room/dceaf8c3/chat \
  -H 'Content-Type: application/json' \
  -d '{"member_id":"m1","nickname":"검증봇","message":"승인"}'
→ POST 본문: {"ai_status":"IDLE"}
curl -s 'http://144.24.91.250:8643/room/dceaf8c3/messages?since=0' (파싱 확인)
```

실제 응답 (GET 파싱):
```
STATE: QUOTED
N_MSGS: 6
seq=3 chat "승인"
seq=4 vote "검증봇님이 승인했습니다 (찬성 1/1, 반대 0/1)"
seq=5 ai_reply "승인 감사합니다. 견적안입니다: A: 2주, 1,500,000원 … B: 4주, 2,500,000원 … C: 6주, 4,000,000원 … 추천: B … 이 견적으로 진행할까요? (진행/취소)"
```

판정: 정상. 1명 방에서도 찬성 1/1로 과반 충족, AWAIT_APPROVAL→QUOTED 전이 및 견적안(A/B/C+추천B) 출력.

## 5. "진행" — QUOTED → GENERATING 전이 + design_url 발급 확인

실행한 명령:
```
curl -s --max-time 60 -X POST http://144.24.91.250:8643/room/dceaf8c3/chat \
  -H 'Content-Type: application/json' \
  -d '{"member_id":"m1","nickname":"검증봇","message":"진행"}'
→ POST 본문: {"ai_status":"GENERATING"}
curl -s 'http://144.24.91.250:8643/room/dceaf8c3/messages?since=0' (파싱 확인)
```

실제 응답 (GET 파싱):
```
STATE: GENERATING | AI_STATUS: GENERATING | DEPLOY: None | N: 8
DESIGN_URL: /design/0b7c29a7
DESIGN_PREVIEW: /design/0b7c29a7/preview.png
seq=6 chat "진행"
seq=7 ai_reply "진행합니다! UI 시안이 준비됐어요: /design/0b7c29a7 … 팀C 코드생성 에이전트(Hermes)를 백그라운드로 시작했습니다. 완료까지 최대 90초 …"
```

판정: 정상. QUOTED→GENERATING 전이, design_url(`/design/0b7c29a7`) 응답에 포함.

## 6. 시안 페이지 서빙 — GET /design/<id>

실행한 명령:
```
curl -s -o /tmp/design_check.html -w 'HTTP_CODE:%{http_code} SIZE:%{size_download} TIME:%{time_total}s\n' \
  --max-time 15 http://144.24.91.250:8643/design/0b7c29a7
```

실제 응답:
```
HTTP_CODE:200 SIZE:2398 TIME:0.024531s
LEN: 2235, <!DOCTYPE html> <html lang="ko"> … <title>web 프로젝트 시안 — UI 시안</title> … requirement_id '0b7c29a7' 본문 포함
```

판정: 정상. HTTP 200 + 실제 HTML 시안 서빙.

## 7. GENERATING → DONE 전이 — GET 폴링만으로 전이되는지 (핵심 회귀 포인트)

실행한 명령 (5초 간격 × 10회):
```
for i in $(seq 1 10); do echo "=== POLL #$i $(date -u +%H:%M:%S) ===";
curl -s --max-time 15 'http://144.24.91.250:8643/room/dceaf8c3/messages?since=0' | (파싱);
sleep 5; done
```

실제 응답 (요약):
```
POLL #1 09:20:13 STATE: GENERATING | AI: GENERATING | DEPLOY: None | N: 8
POLL #2 09:20:18 STATE: GENERATING | AI: GENERATING | DEPLOY: None | N: 8
POLL #3 09:20:23 STATE: GENERATING | AI: GENERATING | DEPLOY: None | N: 8
POLL #4 09:20:28 STATE: DONE | AI: DONE | DEPLOY: http://144.24.91.250:8643/site/0b7c29a7/ | N: 9
  seq=8 ai_reply "코드 생성이 완료됐습니다! - 생성된 파일: index.html - 배포 링크: http://144.24.91.250:8643/site/0b7c29a7/ … 파이프라인 뼈대 관통 완료 (팀C 실구현)."
POLL #5~#10 09:20:33~09:20:59 STATE: DONE 유지 (동일 seq=8, deploy_url 동일)
```

판정: 정상. 폴링 도중 추가 채팅을 보내지 않았는데도 #4(약 "진행" 후 24초, 폴링 시작 후 약 15초)에 DONE 전이. 최근 수정(GET 폴링만으로 상태 전이)이 OCI 배포본에 반영된 것 확인. 전이 후 상태 안정적(6회 연속 DONE 유지).

## 8. 배포 URL 실측 — HTTP 200 + Hermes HTML 콘텐츠 확인

실행한 명령:
```
curl -s -o /tmp/site_check.html -w 'HTTP_CODE:%{http_code} SIZE:%{size_download} TIME:%{time_total}s\n' \
  --max-time 15 'http://144.24.91.250:8643/site/0b7c29a7/'
```

실제 응답:
```
HTTP_CODE:200 SIZE:834 TIME:0.024077s
LEN: 742
HEAD: <!DOCTYPE html> | <html lang="ko"> | … <title>카페 예약</title> | … <h1>카페 예약</h1> |
      <p>환영합니다! 여기서 원하는 날짜와 시간에 좌석을 예약할 수 있습니다.</p>
HAS_HTML: True / HAS_CAFE(카페·예약 키워드): True
```

판정: 정상. HTTP 200 + 요청 주제(카페 예약)에 맞는 Hermes 생성 HTML 실콘텐츠.

## 9. 테스트 데이터 정리 — 생략 (지시대로 유지)

방 `dceaf8c3` / requirement `0b7c29a7` / 배포물 `/site/0b7c29a7/` 그대로 둠. 코드 수정 없음, SSH 접속 없음, `.env` 미열람, git add/commit/push 없음.

---

## 관찰 및 참고 (장애 아님)

1. POST /room/<id>/chat 응답 본문은 AI 텍스트를 포함하지 않고 `{"ai_status": "..."}`만 반환. 실제 AI 텍스트는 GET /room/<id>/messages로 확인해야 함. 로컬 검증 시와 같은 구조로 보이며 E2E 흐름에는 지장 없음. room.html 클라이언트가 이 구조에 맞춰 폴링하므로 정상 범위로 판단.
2. 첫 요청에 대한 ai_reply가 과거사례 RAG 매칭형이 아닌 범용 "신규 프로젝트" 템플릿이었음. 상태 전이(AWAIT_APPROVAL→이후 전 단계)는 모두 정상이므로 기능 장애는 아니나, OCI의 RAG 인덱스/사례 DB가 비어 있거나 유사도 임계값 미달일 가능성을 기록해 둠. 필요시 별도 작업으로 RAG 매칭률 확인 권장 (본 작업 범위 밖).
3. 정적 파일 경로: `GET /static/room.html` → 404, `GET /room.html` → 200(11981B), `GET /` → 200(5179B). static 디렉터리명이 URL prefix가 아니라 루트에서 서빙되는 구성으로 보임. room.html E2E 검증(브라우저)은 `/room.html`로 하면 됨. 이 역시 장애 아님.
