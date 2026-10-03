# 처음 보는 종류 추론 계약 (KIND_INFER_CONTRACT)

> 2026-10-03 (KST). EVENT_INVITE_PLAN 4단계. 계약 Claude, 구현 OpenCode(muse-spark-1.3).

## 문제
업종이 6업종·프로필 별칭 어디에도 안 맞으면(`industry_of` = `other`) `next_question()` 1-1이
"가게·개인·단체·웹서비스" 4지선다(`site_kind`)를 묻는다. 사장님 말을 보고 알 수 있는 걸 되묻는 셈이다.

## 바꾸는 것
1. **새 모듈 `app/services/kind_infer.py`** (situation.py와 같은 모양: LLM이 고르고 엔진이 검증, 실패면 None)
   - `ALLOWED = ("shop", "individual", "group", "webservice", "event")`
   - `infer(business_type: str) -> dict | None` → `{"kind": str, "industry": str, "needs": list[str]}`
     - `llm.chat_json(system, user, timeout_sec=12, max_tokens=300)` 한 번. 예외·JSON 아님·`kind` 허용 밖 → `None`.
     - `industry`: `shop` → `"other"`, 나머지는 kind 그대로(`S.INDUSTRIES` 키).
     - `needs`: 방문자가 사이트에서 봐야 할 내용 이름. 문자열만, 앞뒤 공백 제거, 1~12자, 중복 제거, 최대 6개,
       `llm.foreign_words(need)`가 비어 있지 않으면 버림. 목록이 아니면 `[]`(kind만으로도 성공).
   - system 프롬프트: 각 kind 설명(`event`·`individual`·`group`·`webservice`는 `S.PROFILES[k]["description"]`,
     `shop`은 "가게·매장: 물건·음식·서비스를 파는 곳"), "JSON만 출력", 형식 `{"kind": "event", "needs": ["날짜와 장소", "오시는 길"]}`.
   - user: `f"만들 사이트: {business_type}"` (전화·주소 등 다른 칸은 보내지 않는다).
2. **`app/services/prd_engine.py` `next_question` 1-1**만 수정:
   - 조건(`ind.key == "other"`·`kind_asked` 아님·`business_type` FILLED)은 그대로.
   - `card.get("kind_inferred")`가 없으면 `card["kind_inferred"] = True` 후 `kind_infer.infer(<business_type 값 문자열>)`.
     결과가 있으면 `_apply_inferred_kind(card, res)` 하고 `return next_question(card)` (새 업종으로 다시).
   - 결과가 없거나 이미 추론했으면 지금처럼 `site_kind` 질문을 돌려준다(되돌림 경로).
   - `_apply_inferred_kind(card, res)` (prd_engine 안 새 함수):
     `old = card.get("industry")`; `card["kind_asked"] = True`; `card["industry"] = res["industry"]`;
     `card["inferred_needs"] = res["needs"]`;
     needs가 있고 `sections` 칸 상태가 FILLED가 아니면 `_put(card, "sections", list(needs), S.ASSUMED)`,
     아니면 `_refresh_assumed_sections(card, old)`;
     `design_log.kind_inferred(card, res)` (기록 실패해도 흐름 계속).
   - 다른 곳(4지선다 답 처리 `_answer_pending` 등)은 건드리지 않는다.
3. **기록·관리자 화면 "처음 보는 종류 상위"**
   - `app/services/funnel.py` `SERVER_EVENTS`에 `"kind_inferred"` 추가.
   - `app/services/design_log.py`: `kind_inferred(card, res)` → `_safe("kind_inferred", {"kind": res["kind"], "label": <business_type 앞 30자>})`.
     `report()`의 `names`에 `"kind_inferred"` 추가, 결과에 `"new_kind_top": dict(Counter(f"{kind}:{label}").most_common(20))`.
   - `app/api/admin.py` `admin_metrics`: `unmet_top`처럼 `new_kind_top` 키도 `M.mask_pii`로 가림.
   - `static/admin.html`: `topList("못 담은 요구 상위", g.unmet_top)` 옆에 `topList("처음 보는 종류 상위", g.new_kind_top)`.
4. 부품으로 못 담은 needs는 시안 때 기존 `design_log.unmet()`이 `unmet_need`로 센다(D44 요청 목록) — 새로 만들지 않는다.

## 받아들이는 조건
- `tests/engine/test_kind_infer.py` (가짜 `llm.chat_json`):
  ① 가짜가 `{"kind":"group","needs":["모임 일정","회원 소개"]}` → 첫 질문이 `site_kind`가 아니고 `card["industry"]=="group"`,
     `sections` 값 = 두 needs, 상태 ASSUMED.
  ② `{"kind":"shop"}` → `industry=="other"`, `kind_asked` True, `site_kind` 안 물음.
  ③ 허용 밖 kind·깨진 JSON·예외 → 지금처럼 `site_kind` 질문, 그 뒤 다시 추론하지 않음(호출 1번).
  ④ needs 검증: 13자 이상·영문 낱말·중복·숫자 아닌 값은 버리고 최대 6개.
- 기존 `tests/engine` 전부 통과 (`test_intake_gate.py`의 site_kind 테스트는 가짜가 `{"updates":…}`를 돌려주므로 되돌림 경로로 그대로 통과해야 한다).
