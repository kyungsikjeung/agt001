# 요구사항 도출 엔진 최적화 — 조사 결과

> 조사일: 2026-09-25 / 대상 계획: [REQUIREMENTS_ENGINE_PLAN.md](../REQUIREMENTS_ENGINE_PLAN.md)
> 목적: 대화로 요구사항을 뽑는 엔진을 어떻게 만들면 잘 되는지, 연구와 제품 사례로 확인한다.

## 1. 핵심 발견

| # | 발견 | 근거 | 우리 설계에 주는 의미 |
|---|---|---|---|
| 1 | **질문할 칸을 구조(온톨로지)로 고르면 자유 대화보다 크게 낫다.** 숨은 요구사항 발견률 0.52 → 0.69(+33%), 턴 효율 +21%. 구조만 넣어도 0.13 → 0.41 | OntoAgent (arXiv 2605.05828) | "질문 고르기는 규칙" 원칙이 맞다. 그대로 간다 |
| 2 | 구조가 너무 크면 오히려 초반 효율이 떨어진다 | 같은 논문(유도 데이터 15 → 20개: 발견률 +0.02, 효율 -0.03) | 칸 수를 작게 유지한다. 업종마다 필수 6~8칸 + 숨은 항목 5개 안팎 |
| 3 | 효과가 큰 순서: 첫 메시지로 칸 우선순위 매기기 → 매 턴 다시 매기기 → 거절한 영역 가지치기 | 같은 논문 소거 실험(0.41 → 0.58 → 0.64 → 0.69) | 우선순위를 고정표가 아니라 **첫 메시지 기준 점수 + 턴마다 재계산 + "필요 없어요" 영역 제외**로 만든다 |
| 4 | 질문 모양은 두 가지: 언급만 된 것은 확인형("바비큐장도 소개할까요?"), 일부만 말한 것은 구체화형("객실은 몇 개인가요?") | 같은 논문 | 질문 문구표를 칸마다 확인형·구체화형 두 벌로 만든다 |
| 5 | 자유 대화 LLM은 숨은 요구사항의 68%를 놓친다(최고 모델 발견률 0.32) | ReqElicitGym (arXiv 2602.18306) | 업종별 **숨은 항목 목록**(주차, 반려동물, 단체 예약, 영업 외 연락 등)이 필요하다. 사장님은 먼저 말하지 않는다 |
| 6 | LLM은 **디자인 취향 요구를 거의 뽑지 못한다**(발견률 0.01 미만) | ReqElicitGym | "모양은 묻지 않고 시안으로 보여주고 고르게" 원칙을 뒷받침한다 |
| 7 | LLM은 모호함을 알아도 되묻지 않는다. 모호한 질문에 되묻는 비율 5% 미만 | arXiv 2605.25284 | 되물을지 말지를 AI 판단에 맡기지 않는다. 규칙이 정한다 |
| 8 | 흔한 면접 실수 유형을 알려 주고 질문을 만들게 하면 사람이 쓴 질문보다 낫다 | arXiv 2507.02858 | 질문 문구를 AI로 다듬는다면 "금지 실수 목록"(한 번에 여러 개 묻기, 유도 질문, 전문 용어, 이미 들은 것 되묻기)을 함께 준다 |
| 9 | 선택지 버튼은 자유 입력만 있을 때보다 응답률이 2.4배. 선택지는 2~4개, 5개 이상은 고르기 어렵다. 자유 입력은 항상 함께 둔다 | 챗봇 UX 모음(BotHero, Conferbot 등, 업계 자료) | 선택지 2~3개 + "알아서 해주세요" + 자유 입력 유지. 합쳐서 4개를 넘기지 않는다 |
| 10 | NIM은 JSON 스키마로 출력을 강제하는 기능(`guided_json`)을 지원한다. `response_format=json_object`는 빈 JSON도 허용하므로 권장하지 않는다. 게이트웨이는 이제 `extra_body` 최상위의 `guided_json`만 받는다 | NVIDIA NIM 문서, nim-api-adapter PR #117 | 추출 응답을 스키마로 강제한다. 우리 모델(nemotron-3-super)에서 동작하는지 첫 구현 때 확인 필요 |
| 11 | 빠른 사이트 빌더(Durable)는 업종·이름·위치 세 가지만 받고 바로 만든다 | 업계 리뷰 | 최소 필수는 이 셋 + 연락 방법. 나머지는 가정으로 채우고 시안에서 고치게 해도 된다 |

## 2. 가상 사장님(시뮬레이터) 설계 기준

ReqElicitGym의 가상 사용자는 실제 사용자와 정보 공개 행동 일치도가 κ=0.73이다. 세 원칙을 그대로 쓴다.

| 원칙 | 내용 | 우리 적용 |
|---|---|---|
| 근거 한정 | 사실표에 있는 것만 말한다 | 사실표 밖이면 "잘 모르겠어요" |
| 수동 응답 | 묻지 않으면 먼저 말하지 않는다 | 기본 유형은 수동. "말 많은 사장님"만 예외로 첫 메시지에 많이 담는다 |
| 맥락 유지 | 앞에서 한 말과 어긋나지 않는다 | 전체 대화를 매번 넘긴다 |

## 3. 지표 (성적표에 추가)

| 지표 | 정의 | 출처 |
|---|---|---|
| 숨은 요구 발견률 (IRE) | 사실표의 숨은 항목 중 대화로 끌어낸 비율 | ReqElicitGym |
| 턴 할인 핵심 질문률 (TKQR) | 핵심 질문을 얼마나 이른 턴에 했는지(늦을수록 감점) | ReqElicitGym |
| 필수 칸 채움률·정확도·지어낸 값·질문 수·규칙 위반 | 기존 계획 §4.1 | REQUIREMENTS_ENGINE_PLAN.md |

## 4. 계획에 반영할 변경

| # | 변경 | 계획 위치 |
|---|---|---|
| 1 | 칸 우선순위를 "첫 메시지 점수 + 턴마다 재계산 + 거절 영역 제외"로 | §3 ⑦ |
| 2 | 칸마다 질문 문구 두 벌(확인형·구체화형) | P-1a |
| 3 | 업종별 숨은 항목 목록 추가, 시나리오 사실표에도 숨은 항목 포함 | §2, P-1b |
| 4 | 성적표에 IRE·TKQR 추가, 가상 사장님 기본값은 수동 응답 | §4.1 |
| 5 | 추출은 `guided_json`으로 스키마 강제 | P-1c |
| 6 | 선택지 합계 4개 이하(선택지 2~3 + 알아서) | §1 원칙 2 |

## 출처

- [From Chat to Interview: Agentic Requirements Elicitation with an Experience Ontology (arXiv 2605.05828)](https://arxiv.org/html/2605.05828)
- [ReqElicitGym: An Evaluation Environment for Interview Competence in Conversational Requirements Elicitation (arXiv 2602.18306)](https://arxiv.org/html/2602.18306)
- [Requirements Elicitation Follow-Up Question Generation (arXiv 2507.02858)](https://arxiv.org/abs/2507.02858)
- [Knowing but Not Showing: LLMs Recognize Ambiguity but Rarely Ask Clarifying Questions (arXiv 2605.25284)](https://arxiv.org/html/2605.25284v1)
- [LLMREI: Automating Requirements Elicitation Interviews with LLMs (RE 2025)](https://conf.researchr.org/details/RE-2025/RE-2025-Research-Papers/2/LLMREI-Automating-Requirements-Elicitation-Interviews-with-LLMs)
- [ClarQ-LLM benchmark (arXiv 2409.06097)](https://arxiv.org/abs/2409.06097)
- [Structured Uncertainty guided Clarification for LLM Agents (arXiv 2511.08798)](https://arxiv.org/html/2511.08798v1)
- [Reliable LLM-based User Simulator for Task-Oriented Dialogue Systems (arXiv 2402.13374)](https://arxiv.org/abs/2402.13374)
- [NVIDIA NIM Structured Generation](https://docs.nvidia.com/nim/large-language-models/1.12.0/structured-generation.html), [guided_json 형식 변경 (nim-api-adapter PR #117)](https://github.com/dataloop-ai-apps/nim-api-adapter/pull/117)
- [Durable vs Wix ADI](https://reviews.thewindowsclub.com/durable-vs-wix-adi-which-ai-website-builder/), [Wix ADI → Harmony](https://www.wix.com/blog/wix-artificial-design-intelligence)
- [Chatbot UX Best Practices (BotHero)](https://blog.bothero.ai/chatbot-ux-best-practices-the-cognitive-playbook-12-interface-decisions-that-determine-whether-users-trust-your-bot-in-4-seconds-or-close-the-widget-forever), [Chatbot UI Design Best Practices (Conferbot)](https://www.conferbot.com/blog/chatbot-ui-design-best-practices)
