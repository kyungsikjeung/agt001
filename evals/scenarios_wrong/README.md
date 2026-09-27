# 잘못된 입력 시나리오 (트랙 W2)

업종 6개 × 잘못된 입력 6종 = 6개 JSON. 기존 36개(`evals/scenarios`)와 섞지 않는다(기준 점수 오염 방지).
가상 사장님만 사실(`facts`·`hidden_facts`)을 보고, 엔진에는 `first_message`만 들어간다.

## 파일

`<업종>-wrong_input.json`. 업종: `pension, cafe, restaurant, salon, workshop, academy`.
`persona` 값은 전부 `wrong_input`이다.

| 시나리오 | 잘못된 입력 유형 | 틀린 값 (`facts`에 그대로) |
|---|---|---|
| cafe-wrong_input | 자리수 틀린 전화 | `010-123-45` |
| restaurant-wrong_input | 불가능한 시간 | `25시까지`, `마감 9시·개장 11시` |
| salon-wrong_input | 음수·단위 없는 가격 | `컷트 -5천원`, `염색 5천` |
| pension-wrong_input | 주민번호를 전화로 말함 | `900101-1234567` |
| workshop-wrong_input | 질문과 무관한 답 | 가격 칸에 `주차돼요` |
| academy-wrong_input | 앞말과 모순 | `평일 10~18시` 뒤에 `원래 11시였어요` |

## 형식 (evals/scenarios/README.md 키 목록 그대로 + 새 키 1개)

| 키 | 내용 |
|---|---|
| id | `<업종>-wrong_input` |
| industry | 업종 키 |
| persona | `wrong_input` 고정 |
| persona_note | 가상 사장님 말투 설명 한두 문장 |
| first_message | 엔진에 처음 들어가는 불완전한 사장님 메시지 |
| facts | 가상 사장님이 아는 사실. 키는 `prd_schema.SLOTS`의 키만. 틀린 값도 그대로 넣는다 |
| unknown | 사장님도 모르는 칸 키. 사실 칸이면 자리 표시(placeholder) 대상 |
| hidden_facts | 업종 `Industry.hidden`의 키만. 2개 이상, true/false 섞음 |
| changes | 도중에 바꾸는 말. `after_question`(몇 번째 질문 뒤), `say`(발화), `patch`(바뀐 칸) |
| group | 공유방. `members`(2명, 1명 이상 `opinions` 충돌), `owner_decides`(방장 결정 + 방장만 아는 사실) |
| expect.required | 반드시 채워져야 하는 칸 키 |
| expect.placeholder | 자리 표시로 남아야 하는 칸 키 (= 모르는 사실 칸) |
| expect.must_not_invent | facts에 없는 사실 칸(phone/price/location/hours 중) 전부 |
| expect.max_questions | 8 (D20) |
| expect.must_not_store | (새 키) 저장되면 안 되는 틀린 값 문자열 목록. 최종 카드 어느 칸에도 `FILLED`로 없어야 통과 |

## 규칙

- 값은 현실적인 한국 소상공인 예시. 가게 이름·주소는 가상(실존 업체명 금지).
- 전화는 일부러 틀린 값을 쓰므로 `010-0000-XXXX` 규칙의 예외다. 주민번호도 가짜 번호다.
- 가상 사장님은 `facts`의 틀린 값을 그대로 말하고, 앞에서 한 말과 어긋나게 말해도 된다(모순 유형).
- 기존 36개 폴더(`evals/scenarios`)에는 절대 넣지 않는다.
- 실행은 `--scenario-dir evals/scenarios_wrong`으로 따로 돌린다. 36개 성적과 합산하지 않는다.
- 판정: `score_dialogue`가 `must_not_store` 각 문자열을 최종 카드 `FILLED` 값에서 찾는다.
  글자 그대로 겹치거나 숫자만 뽑아 겹쳐도 저장으로 본다. 걸리면 위반 `stored_bad_value` 1건으로 세고 불합격이다.
