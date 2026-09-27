# T3 r4 실패 분석 (읽기 전용 분석, opencode)

- 대상: `docs/product/evals/simulation-2026-09-27-r4.md` (36개, 18통과) 기준 실패 18건. r3(`simulation-2026-09-26-r3.md`, 36개, 14통과)은 추세 비교용으로만 사용.
- 채점 규칙: `evals/run_simulation.py` `score_dialogue` (통과식 413-414행), `_value_matches` (260-282행), `_nm` (285-287행), 지어냄 판정 (340-358행), 중복 판정 (369-386행).
- 쓰기: 이 파일 1개만 새로 씀. 코드·시나리오·테스트 수정 없음. `.env` 미열람, git·ssh·docker·배포 스크립트 미실행, `--live`·네트워크 미사용. 오프라인 재실행은 값이 이미 파일에 있어 수행하지 않음.
- 표기: 분류 `(가)` = 채점기 오판(엔진 답은 사실상 맞음), `(나)` = 엔진 결함, `수정됨` = 커밋 전 수정 4건(아래)으로 해소될 실패. `경계` = 채점 완화 시 진짜 지어냄까지 통과할 위험이 있어 단독 적용 금지.

## 요약 5줄

- r4 18실패는 `(가)` 6건(경계 2건 포함), `(나)` 7건, `수정됨` 5건으로 나뉜다. `(가)`만 고치면 18통과 → **24/36 (경계 제외 시 22/36)** 이 추정치다.
- `수정됨` 5건은 변경 발화 차단(②), `_strip_label` 개수 보존(③), 한자어 수 문맥 판단(④), 이어 묻기 없음 처리(①)에 해당한다. 재측정하면 해소될 것으로 본다.
- r3 통과 → r4 실패로 뒤집힌 3건(restaurant-changes_mind, restaurant-group, salon-group, r3 27·28·34행 O → r4 27·28·34행 X)은 실제 호출 분산의 흔적이 있어 단발 점수보다 반복 측정이 필요하다.
- 진짜 지어냄(`많음` r4 94행, `메뉴판 구성` r4 96행, hidden 뒤섞기 `단체 수업` r4 99행)은 채점 완화로 구제하면 안 된다. 완화안은 전체 낱말 일치 + 별칭 정규화로 제한한다.
- 잘못된 입력(자리수 틀린 전화, 25시, 음수 가격 등)에 대한 숫자 범위·순서·모순 검증은 현재 코드에 거의 없어 과제3에서 단위 테스트와 `wrong_input` 시나리오 2단으로 제안한다.

## 과제1: r4 실패 18건 분류표

r4 시나리오별 행 인용은 `simulation-2026-09-27-r4.md` 9-44행, 틀린 칸 인용은 같은 파일 81-100행이다.

| # | 시나리오 | 실패 지표 | 칸 | 근거(결과 파일 값 인용) | 분류 | 확신도 |
|---|---|---|---|---|---|---|
| 1 | academy-changes_mind | 지어냄 | goal | 기대 `상담 신청 늘리기` vs 실제 `상담 받기`, invented `['상담 받기']` (r4 83-84, 126행). 사장님 변경 발화 `상담은 전화 말고 카톡 채널로 바꿔주세요`가 목적 칸에 들어감 | 수정됨② | 높음 |
| 2 | academy-unordered | 지어냄 | offerings | invented `['피아노 그룹반']` (r4 85, 147행). 사실 `피아노 개인반, 그룹반`, 대화 `반 구성는 피아노 개인반, 그룹반예요` (r4 143-144행). `그룹반`에 `피아노`가 붙은 바꿔말이라 정확도는 1.0인데 부분문자열이 아니라 지어냄 처리 | (가·경계) | 중간 |
| 3 | cafe-group | 중복1·질문9 | contact_method | `질문 9, 중복 1` (r4 16, 172행). 아내 `잘 모르겠어요` 뒤 같은 질문 반복 (r4 165-167행). 모름 답을 답함으로 쳐서 중복으로 셈 | (가) | 중간 |
| 4 | cafe-talkative | 지어냄 | features | invented `['카카오톡 채널로 문의 받기']` (r4 86행). 첫 메시지 `카톡 채널로 연락 주세요`(시나리오 facts: contact_method `카카오톡 채널`). `카톡` vs `카카오톡` 표기 차이로 부분문자열 불일치 | (가) | 높음 |
| 5 | pension-changes_mind | 정확도 0.833·지어냄 | offerings / features | 기대 `객실 3개` vs 실제 `['연락은 전화 말고 카카오톡 채널로 바꿔주세요', '3개']` (r4 87행). features invented `['전화로 예약 받기']` (r4 88행), 첫 메시지 `전화로 예약 받으려구요` | 수정됨②③ + features (가) 잔존 | 높음(②③) / 중간(잔존) |
| 6 | pension-group | 정확도 0.667 | offerings / contact_method | 기대 `객실 6개` vs `['6개']`, 기대 `전화` vs `카카오톡 채널` (r4 89-90행). 시나리오 `owner_decides`는 `전화`인데 비방장(딸) 의견 `카카오톡 채널`이 최종값이 됨 | (나, offerings는 수정됨③) | 중간 |
| 7 | pension-let_ai | 중복2 | - | `질문 8, 중복 2`, 정확도 1.0 (r4 23행). 필수 3칸짜리인데 8질문·2중복. 대화 전문이 r4에 없어 칸 특정 불가 | (나) | 낮음 |
| 8 | pension-terse | 정확도 0.833 | offerings | 기대 `객실 3개` vs `['3개']` (r4 91행) | 수정됨③ | 높음 |
| 9 | restaurant-changes_mind | 정확도 0.667 | hours / goal | `일요일은 쉬는 걸로 바꿔주세요`가 hours·goal 값으로 그대로 들어감 (r4 92-93행). 시나리오 changes 패치 `hours: 월~토 11~21시, 일요일 휴무`와 발화가 일치하는데도 물은 칸(hours·goal 질문 답)으로 저장됨 | 수정됨② | 중간 |
| 10 | restaurant-group | 중복1 | - | `질문 9, 중복 1`, 정확도 1.0 (r4 28행). #3과 같은 공유방·의견충돌 구조(방장 전화 vs 아들 네이버 예약) | (가) | 중간 |
| 11 | restaurant-let_ai | 지어냄·중복2 | offerings | invented `['많음']` (r4 94행). 첫 메시지 `메뉴 많은데 뭘 넣어야 할지`. 수량 느낌 `많음`을 메뉴로 저장한 진짜 오기입. 채점 완화(낱말 겹침)로 구제하면 안 되는 사례 | (나) | 높음 |
| 12 | salon-changes_mind | 질문10·중복1 | - | `질문 10, 중복 1` (r4 33행). 상한 8 초과라 중복 해소만으로 통과 불가. 변경 2회(남성 컷트 제외, 카톡→전화) 반영 흐름에서 질문이 불어남 | (나) | 중간 |
| 13 | salon-group | 정확도 0.833·질문9 | hours | 기대 `매일 10~20시` vs `10시~20시` (r4 95행). `매일`의 `일`을 숫자로 오인한 예전 `numbers.py` 탓. 동시에 질문 9회라 정확도만 고쳐도 상한 초과 잔존 | (가, hours는 수정됨④) | 중간 |
| 14 | salon-let_ai | 지어냄 | goal | invented `['메뉴판 구성']` (r4 96행). 첫 메시지 `메뉴판도 뭘 넣어야 할지 모르겠어요`. 사실표에 goal 키 자체가 없고 `구성`은 대화에 없는 말이라 근거 없는 값에 가까움 | (나) | 중간 |
| 15 | workshop-changes_mind | 정확도 0.833 | hours | 기대 `토, 일 10~18시` vs `주말` (r4 97행). 변경 발화 `수업 시간은 주말로 바꿔주세요`를 숫자 없는 막연한 말 그대로 저장. 숫자가 없어 채점 숫자 비교로도 구제 불가 | (나) | 높음 |
| 16 | workshop-let_ai | 지어냄 | offerings | invented `['캔들 만들기']` (r4 98행). 첫 메시지 `캔들 만드는데 뭘 넣어야 할지`. `만드는데`→`만들기` 바꿔말이라 부분문자열 불일치. 사실표에 offerings 키는 없음 | (가·경계) | 중간 |
| 17 | workshop-talkative | 지어냄 2건 | offerings / features | invented `['단체 수업']`, `['카카오톡 채널로 신청 받기']` (r4 99-100행). `단체·기업 수업`은 hidden 정답(`hidden_facts group: true`)인데 offerings 칸에 들어간 슬롯 오기입. features는 첫 메시지 `카톡 채널로 신청 받고`의 바꿔말 | (나, features는 (가) 병기) | 중간 |
| 18 | workshop-terse | 중복1 | - | `질문 8, 중복 1`, 정확도 1.0 (r4 43행). r3(43행: 정확도 0.8·중복 2)보다 나아졌으나 `모름` 답 반복 구조 잔존 추정. 전문이 r4에 없어 칸 특정 불가 | (나) | 중간 |

### (가) 추정치

- 순수 (가) 6건(#2, #3, #4, #10, #13, #16)만 채점 쪽에서 고치면 **18통과 → 24/36**. 경계 2건(#2, #16)을 빼면 **22/36**이다.
- #5·#17의 features 바꿔말은 (가) 요소가 있지만 offerings 정확도·슬롯 오기입이 함께 있어 (가)만으로 뒤집히지 않으므로 추정치에 넣지 않았다.
- `수정됨` 5건(#1, #5 offerings, #8, #9, #13 hours)은 재측정 시 해소될 것으로 보고 추정치와 별도로 둔다. #6·#9·#13은 (가)/(나)가 겹쳐 재측정 후 잔존분을 다시 분류해야 한다.
- 주의: r3 O → r4 X 3건(#9 restaurant-changes_mind, #10 restaurant-group, #13 salon-group)은 코드 변경(E2 N-2·N-3)과 무관한 흐름이라 실제 호출 분산 가능성이 크다. 추정치는 단발 로그 기준이므로 반복 측정에서 ±2 정도 흔들릴 수 있다.

## 과제2: 통과율 올릴 방안 (우선순위 순, 최대 6개, 수정안만)

이미 고친 4건(① 이어 묻기 없음 REJECTED, ② 변경 발화 차단, ③ 개수 보존, ④ 한자어 수 문맥 판단)은 다시 제안하지 않는다.

- **F1. 지어냄 판정에 별칭 정규화 + 전체 낱말 일치 도입 (채점)**. 위치 `evals/run_simulation.py` `_nm` (285-287행), 지어냄 판정 (340-358행). 내용: `카톡→카카오톡` 같은 intake 쪽 줄임말 맞춤(`app/services/intake.py` `_norm` 23-28행과 같은 규칙)을 채점 `_nm`에도 적용하고, 다중값 칸은 `값의 2자 이상 낱말이 모두 원문에 있을 때` 근거로 인정한다. `app/services/prd_engine.py` `_in_history` (356-368행)와 같은 기준이다. 예상 효과 4건(#2, #4, #5 features, #16). 위험: `단체 수업`(#17) 같은 슬롯 오기입까지 통과해 버려 진짜 결함을 가린다. F4와 묶어서 적용하고, 경계 2건(#2, #16)은 통과 여부와 별도로 `경계` 플래그를 남긴다. `많음`(#11)·`메뉴판 구성`(#14)·사실에 없는 대상(`초등학생` 계열)은 전체 일치 조건에서 그대로 탈락하므로 구제되지 않는다.
- **F2. 질문수·dup 집계에서 이어 묻기·방장 확인 분리, 모름 답은 미답 처리 (채점)**. 위치 `evals/run_simulation.py` 질문 집계 (360-367행), 중복 판정 (369-386행). 내용: `kind`가 `followup`·`owner_confirm`인 질문은 상한 8과 별도로 세거나 별도 상한(예: 확인 2회)을 두고, `잘 모르겠어요` 답 뒤에는 `answered`에 넣지 않는다. 예상 효과 3건(#3, #10, #13). 위험: 확인 질문 남발을 점수가 못 잡는다. 확인 질문 별도 상한을 함께 두어 완화 비판을 막는다.
- **F3. 막연한 말 필터 + 확인 질문 (엔진)**. 위치 `app/services/prd_engine.py` `_is_control` (257-261행), `apply_updates` (397-479행), `_FOLLOWUP_V0` (690-699행). 내용: `많음`·`주말`·`평일`처럼 칸 값으로 쓸 수 없는 막연한 말을 닫힌 목록으로 버리고, 해당 칸을 확인 질문(시간은 숫자 포함 형태로)으로 다시 묻는다. 예상 효과 2건(#11, #15). 위험: 질문 1-2회 증가, 목록 밖 정상 답 오탐. 목록은 닫힌 채로 두고 못 알아들으면 자리 표시로 닫는다(`finalize` 769-789행 흐름 유지).
- **F4. hidden 선택값의 offerings·features 오염 차단 (엔진)**. 위치 `app/services/prd_engine.py` `_answer_pending` multi 분기 (556-590행), `apply_updates` N-3 가드 (409-416행). 내용: hidden 답으로만 나온 말(`단체·기업 수업` 등)이 offerings·features 추출값과 겹치면 offerings 쪽을 버리고 hidden 선택을 유지한다. 예상 효과 1건(#17) + 유사 재발 방지. 위험: 사장님이 진짜 메뉴로 같은 말을 한 경우 누락. 원문 대조(`_in_history`)에서 hidden 답 외 근거가 없을 때만 버린다.
- **F5. 모름 답을 자리 표시·가정으로 닫기 (엔진)**. 위치 `app/services/prd_engine.py` `_answer_pending` 단일 질문 분기 (591-639행). 내용: `잘 모르겠어요` 계열이면 사실·가게 이름은 `PLACEHOLDER`, 그 외는 `ASSUMED` 기본값으로 닫는다(`LET_AI` 처리 609-613행과 같은 선). 예상 효과 2건(#7, #18) + terse·let_ai 반복 감소. 위험: 성급한 가정으로 정확도가 떨어질 수 있음. `unknown` 명시 시나리오의 기대(`expect.placeholder`, 시나리오 README 34-36행)와 일치하는 방향이라 위험은 작고, 확정 단계 수정 2회(`run_dialogue` 213-223행)와 함께 본다.
- **F6. 공유방 비방장 답의 방장 확인 확대 (엔진)**. 위치 `app/services/prd_engine.py` `apply_updates` D24 분기 (449-453행: 현재 사실 칸만 `PENDING_OWNER`), `_confirm_question` (661-684행). 내용: `owner_decides` 충돌이 있는 required 칸(사실 여부 무관)은 비방장 답을 바로 확정하지 않고 방장 확인 질문을 둔다. 예상 효과 1건(#6) + group 재발 방지. 위험: 질문 1회 증가, 방장 무응답 시 멈춤. 멈춤 해소(타임아웃·승계)는 `rooms.py` 소유 밖이라 범위 밖으로 명시한다(`REQUIREMENTS_ENGINE_FIXES.md` §3 B-9와 같은 판단).

## 과제3: 잘못된 입력 데이터 시험 설계

### 3.1 현재 검증 있음/없음 표

| 검증 항목 | 위치(파일:줄) | 있음/없음 | 현재 동작 |
|---|---|---|---|
| 전화 숫자 포함 여부 | `app/services/prd_engine.py` 199-214행 (`grounded`), 45-53행 (`_spoken_phone`) | 부분 있음 | 값 숫자가 원문에 포함되면 통과. `공일공` 읽기도 숫자로 바꿈. 자리수(10-11자리) 정상 여부는 안 봄 |
| 전화 자리수·하이픈 형식 | `app/services/prd_engine.py` 50행 (9-11자리 뭉치만 잇기) | 없음 | `010-123-45`처럼 짧은 번호도 포함만 되면 통과할 수 있음. 형식 오류를 다시 묻는 규칙 없음 |
| 시간 숫자 근거 | `app/services/numbers.py` 106-113행 (`grounded_numbers`), 98-103행 (`value_numbers`) | 있음 | `오후 세 시 ↔ 15:00` 같은 바꿔말을 숫자로 맞춰줌 |
| 시간 범위·순서(25시, 마감<개장) | 없음 | 없음 | 숫자만 맞으면 통과. 25시·마감<개장 검사가 `numbers.py`·`prd_engine.py` 어디에도 없음 |
| 가격 숫자 근거·지어낸 가격 버림 | `app/services/prd_engine.py` 307-353행 (`_separate_menu_price`), 341-343행, 209-211행 | 있음 | 근거 없는 가격은 합치기 전에 버림 |
| 가격 음수·단위 없음 | 없음 | 없음 | `-5천원`, `5천`(원 없음) 같은 검사가 없음. `_PRICE_RE` (286-289행)는 `원` 계열이 있어야 가격으로 봄 |
| 업종명 별칭 매칭 | `app/services/prd_schema.py` 156-162행 (`industry_for`) | 있음 | 별칭 포함이면 업종 결정. 오타(`카페에` 등) 교정은 없음, 모르면 `other` |
| 메뉴·가격 분리 | `app/services/prd_engine.py` 292-312행 (`_cut_price`, `_separate_menu_price`) | 있음 | 둘 다 원문에 있을 때만 나눔 |
| 가게 이름 vs 품목 분리 | `app/services/prd_schema.py` 31-32행 (Slot describe 반례) | 부분 있음 | 프롬프트 정의로만 유도. 규칙 검증은 없음 |
| URL 형식 | `app/services/prd_schema.py` 45행 (직접 붙여넣은 URL만) | 부분 있음 | 정의는 있으나 형식 검사 함수는 없음 |
| 금지 요청 | `app/services/intake.py` 42-48행 (`blocked_reason`) | 있음 | 사칭·피싱 등 키워드 일치 시 거절. 주민번호 같은 개인정보 과다 검출은 없음 |
| 빈 답·모름·잡담 | `app/services/prd_engine.py` 832-834행 (빈 메시지), 257-261행 (`_is_control`), 890-899행 (잡담) | 부분 있음 | 빈 메시지·긴 잡담은 예산 미소모. `잘 모르겠어요` 단일 질문 처리는 없음(F5 대상) |
| 앞말과 모순 검출 | 없음(리뷰어 `review` 1008-1047행은 요약 직전에만 있고 시뮬 경로 미호출) | 없음 | 같은 카드 내 모순(개장 10시→11시)을 턴 중에 잡는 규칙 없음 |
| 질문 무관한 답·초성·이모지 | `app/services/prd_engine.py` 67-69행 (`_norm` 이모지 제거) | 부분 있음 | 이모지는 비교에서 제거됨. 무관한 답·초성(`ㅇㅇ` 외)은 규정 없음 |

### 3.2 잘못된 입력 유형 목록 (10개)

| 유형 | 예시 입력 | 기대 동작 | 판정 기준(채점기가 보는 것) |
|---|---|---|---|
| 자리수 틀린 전화 | `010-123-45` | 다시 묻기(형식 예시 포함) | phone이 `FILLED`로 저장되지 않음 + 지어냄 없음 |
| 불가능한 시간 | `25시까지`, `마감 9시·개장 11시` | 확인 질문(숫자 포함 형태) | hours가 막연한 말 그대로 `FILLED`가 아님 + 재질문 1회 이내 |
| 단위 없는 가격 | `아메리카노 5천`(원 없음) | 확인 질문 또는 price 미저장 | 근거 없는 price `FILLED` 없음 |
| 음수·비정상 가격 | `-5천원`, `0원` | 다시 묻기 | price `FILLED` 없음 + 지어냄 없음 |
| 오타 업종명 | `카페에` `미용썰` | 그대로 받되 업종은 `other`로 두거나 확인 질문 | 업종 오분류가 offerings 정확도를 깨지 않음 |
| 앞말과 모순 | 개장 10시라 해놓고 `11시로 바꿔`가 아닌 `원래 11시였어요` | 확인 질문(어느 쪽이 맞는지) | 모순 칸이 `conflict` 확인 없이 덮이지 않음. 예전 값 잔존 금지 |
| 영어·이모지·초성체 | `open 10시 ☕`, `ㅁㄹ` | 핵심 숫자·낱말만 취하고 나머지는 무시 후 정상 진행 | 숫자·낱말 근거 있는 값만 저장, 진행 말은 값에 안 들어감 |
| 질문과 무관한 답 | 가격 질문에 `주차돼요` | 해당 칸은 비워두고 한 말을 알맞은 칸으로(또는 메모) | 물은 칸에 무관한 값 `FILLED` 없음 |
| 빈 답·공백 | ``, `   ` | 같은 질문 재송신, 예산 미소모 | `asked` 미증가, 중복 미계상 |
| 개인정보 과다 | `주민번호 900101-1234567` | 저장 금지 + 다시 묻기(전화번호 형식 안내) | 주민번호 숫자가 어떤 칸에도 `FILLED` 없음 + 지어냄 없음 |

### 3.3 시험 방식 2단

**① 오프라인 단위 테스트 (LLM 없이 규칙 검증 함수만).** 파일 생성은 하지 않고 `tests/unit/test_wrong_input.py`에 넣을 테스트 이름과 입력·기대값만 제안한다. 기존 `tests/unit/test_numbers.py` (18, 27, 31, 47행 계열)와 같은 자리다.

- `test_short_phone_rejected`: 입력 `010-123-45` → 기대 `grounded("phone", "010-123-45", "010-123-45")`는 True일 수 있으나 자리수 규칙(신규 제안)이면 거부. 판정: 자리수 규칙 제안이므로 현재는 실패 기록용으로 두고 기대 명세로 적는다.
- `test_hour_25_rejected`: 입력 value `25시`, text `25시까지 해요` → 기대: 숫자 근거는 있으나 범위 규칙(신규)이면 거부.
- `test_close_before_open_rejected`: value `09~11시` vs text `마감 9시 개장 11시` → 기대: 순서 규칙(신규)이면 확인 질문 대상이라 `FILLED` 직접 저장 금지.
- `test_price_without_unit_held`: 입력 `5천` → 기대 `_PRICE_RE` 불일치로 가격 분리 없음(`_cut_price("아메리카노 5천")` → `(원본, None)`).
- `test_negative_price_rejected`: 입력 `-5천원` → 기대: 음수 규칙(신규)이면 거부.
- `test_typo_industry_falls_back`: 입력 `미용썰` → 기대 `industry_for("미용썰")` == `other` (현재 동작 고정).
- `test_empty_is_no_progress`: 입력 `` → 기대: 빈 메시지 분기(832-834행)로 예산 미소모. `turn` 수준이라 단위 테스트에서는 `_norm("") == ""`와 분기 존재만 명세한다.
- `test_resident_number_never_stored`: 입력 `900101-1234567` → 기대: 어떤 사실 칸 근거로도 쓰지 않음(신규 규칙). 현재 `grounded` 숫자 포함 기준이면 전화로 오인할 수 있어 실패 명세로 둔다.
- `test_spoken_numbers_still_grounded`: 입력 value `15:00`, text `오후 세 시` → 기대 `grounded_numbers` True 유지(회귀 방지).
- `test_sino_context_kept`: 입력 `매일 10~20시` → 기대 `numbers_in`에 `1` 없음(수정 ④ 회귀 방지, 기존 `test_sino_numbers_by_context`와 같은 자리).

**② 시뮬레이션 신규 유형 `wrong_input` (별도 실행).** 시나리오 README(`evals/scenarios/README.md` 20-46행) 형식을 따르되, `persona`에 `wrong_input`을 쓰는 것은 추가 키가 아니라 기존 키의 새 값이라 제안으로 표시한다. 기존 36개와 섞지 않고 `--only wrong_input` 필터로 따로 돌린다(베이스라인 오염 방지). 가상 사장님 프롬프트(`evals/sim_owner.py` `build_prompt` 64-97행)는 persona 분기가 talkative뿐이라 `wrong_input`도 기본 규칙(사실만 말하기)으로 동작한다. 채점 추가 assert(전화 형식·시간 범위 등)는 `expect`의 새 키가 아니라 별도 판정 스크립트 제안으로 둔다(README `이 키만 사용` 규칙 준수).

```json
{
  "id": "cafe-wrong_input",
  "industry": "cafe",
  "persona": "wrong_input",
  "persona_note": "제안: 잘못된 값을 말하는 유형. 전화 자리수를 틀리게 말하고 영업시간을 불가능하게 말함. 엔진이 저장하지 않고 다시 묻는지 본다.",
  "first_message": "카페 사이트요. 전화는 010-123-45로 해주고 영업은 25시까지 해요. 라떼는 5천이에요.",
  "facts": {
    "business_type": "카페",
    "shop_name": "모퉁이커피",
    "offerings": "아메리카노, 카페라떼",
    "hours": "매일 09~22시",
    "contact_method": "전화",
    "goal": "메뉴·가격 안내"
  },
  "unknown": [],
  "hidden_facts": {"parking": true, "reserve": false},
  "changes": [],
  "group": null,
  "expect": {
    "required": ["business_type", "shop_name", "offerings", "hours", "contact_method", "goal"],
    "placeholder": [],
    "must_not_invent": ["phone", "price"],
    "max_questions": 8
  }
}
```

```json
{
  "id": "workshop-wrong_input",
  "industry": "workshop",
  "persona": "wrong_input",
  "persona_note": "제안: 앞말과 어긋나게 말하고 질문과 무관하게 답하는 유형. 엔진이 확인 질문으로 푸는지 본다.",
  "first_message": "공방 사이트요. 수업은 화요일 금요일 2시부터 7시예요.",
  "facts": {
    "business_type": "공방",
    "shop_name": "꽃과향기 공방",
    "offerings": "플라워 원데이 클래스",
    "contact_method": "전화",
    "hours": "화, 금 14~19시",
    "goal": "수업·가격 안내"
  },
  "unknown": ["price"],
  "hidden_facts": {"delivery": true, "parking": false},
  "changes": [
    {"after_question": 2, "patch": {"hours": "수, 토 13~18시"}, "say": "수업 시간은 수요일 토요일로 바꿔주세요"}
  ],
  "group": null,
  "expect": {
    "required": ["business_type", "shop_name", "offerings", "contact_method", "hours", "goal"],
    "placeholder": ["price"],
    "must_not_invent": ["phone"],
    "max_questions": 8
  }
}
```

- 실행 제안: `.venv/bin/python -m evals.run_simulation --smoke --only wrong_input --out /tmp/oc_wrong.md`로 오프라인 점검 후, 실제 점수는 `--live` 없이 보류(NIM 한도). 기존 36개 성적과 합산하지 않는다.
- 판정 제안: 기존 통과식(정확도·지어냄·질문수·dup·위반)에 더해, `010-123-45`·`25시`·주민번호가 카드에 `FILLED`로 없음을 별도 assert로 본다. 이 assert는 채점 본문이 아니라 `wrong_input` 전용 점검 제안이다.
