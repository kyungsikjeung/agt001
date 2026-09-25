# T2 추출 평가 (WP P-1d)

`cases.jsonl`은 요구사항 추출(T2) 테스트용 발화 60개와 기대 칸이다.
업종 6개(펜션·카페·식당·미용실·공방·학원) × 10개.
e001~e003은 `docs/product/research/REQUIREMENTS_ENGINE_RESEARCH.md` §5의 실측 오분류 3건이다.

## 형식 (cases.jsonl, 한 줄에 하나)

| 필드 | 내용 |
|---|---|
| `id` | `e001`~`e060` (중복 없음) |
| `industry` | 업종 키 (`pension`, `cafe`, `restaurant`, `salon`, `workshop`, `academy`) |
| `last_question` | 직전 질문 문장. 짧은 답 유형에만 있고, 없으면 `null` |
| `text` | 사장님 발화 (그대로 추출 입력에 씀) |
| `expect` | `{칸키: 기대 값 또는 [여러 값]}`. "알아서 해주세요"형은 `{}`(빈 기대) |
| `must_not` | `[지어내면 안 되는 칸 키]`. 전화·주소를 말하지 않은 경우 `phone`·`location` 포함 |
| `note` | 무엇을 시험하는지 |

칸 키는 `app/services/prd_schema.py`의 `SLOTS`에 있는 것만 쓴다.
전화번호는 `010-0000-XXXX` 가짜 번호만 쓴다.

## 채점 규칙

- 칸별 일치: 기대 값이 추출 값에 포함되면 일치 (부분 문자열 포함).
  기대 값이 리스트면 항목마다 각각 판정한다.
- 실패: `must_not`에 있는 칸이 하나라도 추출되면 그 케이스는 실패.
- 빈 기대(`expect: {}`): 추출이 빈 목록이어야 통과. 하나라도 추출하면 실패.
- 사실 칸(`phone`, `hours`, `location`, `price`)은 `prd_engine.grounded` 규칙도 함께 본다.
  근거 없는 값은 추출이 냈더라도 버려진 것으로 친다.

## 실행 방법

- CI에서는 녹화본으로 돌리고, 주 1회 실제 AI 호출로 다시 녹화한다
  (REQUIREMENTS_ENGINE_PLAN.md §4 T2).
- 러너(실행기·채점기)는 Claude가 만든다. 이 폴더에는 케이스 데이터만 둔다.
