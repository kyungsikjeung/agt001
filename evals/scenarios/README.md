# 요구사항 엔진 대화 시뮬레이션 시나리오 (WP P-1b)

업종 6개 × 사장님 유형 6개 = 36개 JSON. PLAN §4.1(T3) 시뮬레이션의 입력이다.
가상 사장님만 사실(`facts`·`hidden_facts`)을 보고, 엔진에는 `first_message`만 들어간다.

## 파일

`<업종>-<유형>.json`. 업종: `pension, cafe, restaurant, salon, workshop, academy`.
유형: `talkative, terse, unordered, let_ai, changes_mind, group`.

| 유형 | 특징 | 확인하려는 것 |
|---|---|---|
| talkative | 첫 메시지에 facts 대부분(6개 이상) 포함 | 이미 말한 것을 또 묻지 않는가 |
| terse | 첫 메시지는 업종 한두 단어, 답도 짧게 | 선택지로 끌어내는가 |
| unordered | 영업시간·가격 먼저, 가게 이름은 나중에 | 알맞은 칸에 넣는가 |
| let_ai | "알아서 해주세요" 자주 사용, facts는 적게 | 가정으로 채우고 표시하는가, 지어내지 않는가 |
| changes_mind | `changes` 1~2개 | 칸을 고치고 이전 값을 남기지 않는가 |
| group | `group` 채움, 멤버 2명·의견 충돌·방장만 아는 사실 1개 | 두 답을 나란히 보여주고 투표로 넘기는가 |

## 형식 (이 키만 사용)

| 키 | 내용 |
|---|---|
| id | `<업종>-<유형>` |
| industry | 업종 키 |
| persona | 유형 키 |
| persona_note | 가상 사장님 말투 설명 한두 문장 |
| first_message | 엔진에 처음 들어가는 불완전한 사장님 메시지 |
| facts | 가상 사장님이 아는 사실. 키는 `prd_schema.SLOTS`의 키만 |
| unknown | 사장님도 모르는 칸 키. 사실 칸이면 자리 표시(placeholder) 대상 |
| hidden_facts | 업종 `Industry.hidden`의 키만. 2개 이상, true/false 섞음 |
| changes | 도중에 바꾸는 말. `after_question`(몇 번째 질문 뒤), `say`(발화), `patch`(바뀐 칸) |
| group | 공유방. `members`(2명, 1명 이상 `opinions` 충돌), `owner_decides`(방장 결정 + 방장만 아는 사실) |
| expect.required | 반드시 채워져야 하는 칸 키 |
| expect.placeholder | 자리 표시로 남아야 하는 칸 키 (= 모르는 사실 칸) |
| expect.must_not_invent | facts에 없는 사실 칸(phone/price/location/hours 중) 전부 |
| expect.max_questions | 8 (D20) |

## 규칙

- 값은 현실적인 한국 소상공인 예시. 가게 이름·전화·주소는 가상
  (전화는 `010-0000-XXXX` 형식의 가짜 번호, 실존 업체명 금지).
- 가상 사장님 원칙(조사 §2): 사실표에 있는 것만 말하고, 묻지 않으면
  먼저 말하지 않음(talkative 제외), 앞에서 한 말과 어긋나지 않음.
- 14개 시나리오(terse 6 + let_ai 6 + group 2)의 `unknown`에
  사실 칸(phone/price)을 넣어 자리 표시를 시험한다.
