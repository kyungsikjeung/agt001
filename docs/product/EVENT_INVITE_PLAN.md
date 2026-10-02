# 초대·기념 사이트 (청첩장) 계획 (EVENT_INVITE_PLAN)

> 2026-10-02 (KST). 대표 지시: "결혼 청첩장"이라고 했더니 '가게·개인·단체·웹서비스' 넷 중 고르라는 질문이 나왔다.
> 표에 맞추지 말고, 그 사이트에 무엇이 필요한지 생각해서 **있는 부품은 쓰고 없는 부품은 부품 빌더에 요청**해야 한다.

## 원인
`industry_of()`가 6업종·프로필(individual·group·webservice) 별칭 어디에도 '청첩장'이 없어 `other` → `next_question()` 1-1이
`site_kind`(4지선다)를 한 번 묻는다(`app/services/prd_engine.py`, 데이터 `app/data/intake_profiles.json` `ambiguous`).

## 하객이 보는 것 ↔ 부품
| # | 내용 | 부품 | 상태 |
|---|---|---|---|
| 1 | 위 메뉴 | `navbar--main` | 있음 |
| 2 | 첫 화면(두 사람 이름·날짜·사진) | `hero--arch` / `hero--cinematic` | 있음 |
| 3 | 인사말 | `intro--short` | 있음 |
| 4 | 사진(격자·넘기기·가로 자동 흐름) | `gallery--grid` / `gallery--swipe` / `gallery--marquee` | 있음 |
| 5 | 오시는 길(지도·교통·주차) | `around--map` / `around--transit` | 있음 |
| 6 | 참석 여부 | `contact--form` 문구 바꿔 재사용 | 있음 |
| 7 | 날짜·달력·D-day | `event--date` | **1단계 완료** |
| 8 | 양가 연락처 | `family--contacts` | **1단계 완료** |
| 9 | 마음 전하실 곳(계좌·복사) | `gift--accounts` | **1단계 완료** |
| 10 | 방명록(최신순) | `guestbook--list` + 하객 글 저장·삭제·거르기 | 3단계 |

## 단계
1. ✅ 새 부품 3개 (`templates/sections/{event--date,family--contacts,gift--accounts}.mustache`, `templates/css/50-event-parts.css`, `site_render` 문맥·공개본 규칙·공용 스크립트, `tests/unit/test_event_parts.py`)
2. 초대·기념 원형(설계도) + 질문 흐름: 두 분 성함 → 날짜·시간 → 예식장 → 사진 → 계좌 → 연락처. 돌잔치·칠순·개업 초대도 같은 원형
3. 방명록: 하객 글 저장(플랫폼 공용 DB, D31), 신랑·신부 삭제, 욕설 거르기, 최신순
4. 엔진 일반화: 모르는 업종이면 4지선다 대신 "필요한 내용" 추론 → 부품 대응 → 없는 부품은 요청 목록(D44, 관리자 화면). **PR #17·#18(질문 흐름) 합친 뒤**

## 변경 이력
| 날짜 | 내용 |
|---|---|
| 2026-10-02 | 처음 작성, 1단계 완료 |
