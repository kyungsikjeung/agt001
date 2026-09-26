# OpenDesign 비교 실험 1차 (2026-09-26)

목적: 쪽 전체를 AI가 자유 생성하는 오픈소스(OpenDesign)가 무료 NIM 모델로 우리 부품 방식보다 나은 시안을 내는지 본다(D37 나란히 비교의 한 축). 결정: DECISIONS D38·D39.

## 조건

- OpenDesign `nexu-io/open-design` main `1b47e60`(2026-09-24), Apache-2.0. Docker로 로컬(127.0.0.1:7456)에서만 실행.
- 공식 이미지에는 OpenCode가 없어 BYOK 실행이 막힌다("BYOK API runs require OpenCode"). 공식 이미지 위에 `opencode-ai@1.18.31`만 더한 이미지로 실행.
- 연결 테스트 기본 12초 제한에 GLM이 걸려 `OD_CONNECTION_TEST_PROVIDER_TIMEOUT_MS=90000`으로 늘림.
- 모델: NIM `z-ai/glm-5.3`(BYOK, OpenAI 호환). 설명문: [briefs.md](briefs.md)의 식당(황남밥상), 한 줄로 이어 붙여 입력. 디자인 시스템·템플릿은 기본값.

## 결과

| 항목 | 값 |
|---|---|
| 결과 | **실패, 만들어진 파일 0개** |
| 걸린 시간 | 약 23분(1,422초) |
| 진행 | 규칙 파일 읽기 3회 → 디자인 방향 "Human / approachable" 선택 → HTML 쓰기 단계에서 멈춤 |
| 실패 원인 | "Agent stalled without emitting any new output for 600s" — 모델이 600초 동안 출력 없음 |
| 사용량 | 입력 18,568 토큰, 출력 191 토큰(멈추기 전까지) |

## NIM 모델 속도 실측 (같은 날, 한국어 400자 요청, 스트리밍)

| 모델 | 첫 글자까지 | 초당 조각 | 비고 |
|---|---|---|---|
| `z-ai/glm-5.3` | 30.6초 | 약 8.8 | 글만 받음(그림 넣으면 400 오류). "say ok"도 16초 |
| `z-ai/glm-5.3-flash` | — | — | "say ok"에 81초 |
| `deepseek-ai/deepseek-v4.1-flash` | 0.4초 | 약 9.0 | |
| `moonshotai/kimi-k2.6` | — | — | 404(목록에는 있으나 호출 불가) |
| `moonshotai/kimi-k3` | — | — | 그림 입력에 32초 뒤 빈 답 |
| `google/gemma-4-31b-it` | — | — | 그림 읽고 지적 가능, 178초 |

## 판단

- 무료 NIM으로 쪽 전체 자유 생성은 한 장 15~25분(추정) 또는 실패. 사장님이 기다릴 수 없고, 운영 경로로 쓸 수 없다 → D38(명세 + 부품)을 속도 쪽에서도 뒷받침.
- 품질 비교 자체는 아직 못 했다. 2차는 D39 유료 후보 3개로 같은 설명문 6개를 돌려 비교한다.
- 우리 결과 캡처는 `.venv/bin/python -m evals.run_site_quality --out <폴더>`로 같은 6업종을 다시 만든다(이번 캡처는 임시 폴더에만 있음).
