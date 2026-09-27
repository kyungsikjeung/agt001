# 한국어 숫자 해석과 값 근거 확인 조사

- 확인한 날짜: 2026-09-27 (아래 논문과 저장소는 모두 이날 직접 열어 본 것만 적었다)
- Claude 검수(2026-09-27): arXiv 2309.08626·ACL 2022.emnlp-main.56(Correctable-DST)·NeMo ITN ko 폴더 직접 열어 실재 확인. 2309.08626의 "한국어 실험" 주장만 초록으로 확인 안 돼 표시함.
- 대상 코드: app/services/numbers.py, app/services/prd_engine.py, evals/run_simulation.py

## 요약

- 한국어 수사 해석은 규칙 기반을 유지하는 편이 낫다. 형태소 분석기는 무겁고 동음이의 문제를 풀어 주지 않는다.
- NeMo 한국어 규칙 폴더가 살아 있고 요즘도 손질되고 있다. 통째로 가져오지 말고 숫자 단위와 시각 패턴만 베껴 쓴다.
- 값 근거 확인은 지금처럼 원문 포함 검사를 두되 숫자 값은 집합 포함으로, 말만 다른 경우는 좁게 허용한다.
- 채점기 부분 일치는 숫자 없는 짧은 값에만 쓰고 숫자 있는 값은 숫자 집합 동등을 요구해야 지어낸 값을 놓치지 않는다.
- 사용자 정정은 어느 칸을 고칠지 먼저 가리는 단계가 핵심이라 고칠 칸 탐지 규칙을 먼저 보강한다.

## 조사 1: 논문

| 제목 | 연도·학회 | URL | 핵심 아이디어 | 우리 코드 적용 | 비용 |
|---|---|---|---|---|---|
| NeMo Inverse Text Normalization: From Development To Production | 2021 · Interspeech 2021 | https://arxiv.org/abs/2104.05055 | 말한 형태를 문서 형태로 바꾸는 규칙을 WFST 문법으로 쌓는다. 개발과 운영을 같은 문법으로 돌려서 예측하지 못한 고침이 나가지 않게 한다. | numbers.py의 _COUNTER_RE 단위 목록과 _parse_chunk 분기를 NeMo ko 규칙의 cardinal·money·time 패턴과 대조해서 빠진 단위를 메운다. 통째 설치는 하지 않는다. | 작음 |
| Thutmose Tagger: Single-pass neural model for Inverse Text Normalization | 2022 · arXiv | https://arxiv.org/abs/2208.00064 | 문장 생성이 아니라 낱말마다 갈아 끼울 조각을 붙이는 태깅으로 본다. 입력 낱말과 출력 조각이 일대일로 맞아서 지어내기가 줄고 디버깅이 쉽다. | grounded() (prd_engine.py)와 _separate_menu_price()의 나누기 조건에 쓴다. 메뉴 조각과 가격 조각이 둘 다 원문에 있어야 나누는 지금 규칙이 이 논문 방향과 같다. 조각별 근거 기록을 남기는 쪽으로 다듬는다. | 작음 |
| Improving Robustness of Neural Inverse Text Normalization via Data-Augmentation, Semi-Supervised Learning, and Post-Aligning Method | 2023 · ICASSP 2024 투고 | https://arxiv.org/abs/2309.08626 | 학습 때 못 본 말투에 약한 문제를 실제 음성 인식 결과로 직접 학습해서 푼다. 예측 뒤에 정렬로 바로잡는 단계를 둬서 엉뚱한 고침을 막는다. (한국어 실험 여부는 초록에 없음 — Claude 확인 시 미확인, 저자는 한국 연구진) | numbers.py의 남은 한계("3~4만원" 범위, "만오천" 생략형, "열 시 반", "한 시간 반")를 다룰 때 쓴다. 범위와 반올림 표현을 위한 테스트 쌍을 AI Hub 공개 말뭉치 쪽에서 모으고, value_numbers() 뒤에 정렬 확인을 둔다. | 중간 |
| SelfCheckGPT: Zero-Resource Black-Box Hallucination Detection for Generative Large Language Models | 2023 · EMNLP 2023 | https://aclanthology.org/2023.emnlp-main.557/ | 같은 질문을 여러 번 물어 답이 서로 어긋나면 지어낸 것으로 본다. 외부 자료 없이 일관성만으로 가려낸다. | _value_matches() (run_simulation.py)의 참고용이다. 채점 때 애매한 값은 값 자체만 보지 말고 같은 칸을 여러 턴에서 뽑은 기록과 겹치는지로 본다. 매 턴 여러 번 묻는 방식은 질문 예산을 깨므로 쓰지 않는다. | 참고만 |
| RARR: Researching and Revising What Language Models Say, Using Language Models | 2023 · ACL 2023 | https://aclanthology.org/2023.acl-long.910/ | 만든 글을 근거에 비춰 고친다. 근거 없는 부분만 고치고 원래 문장은 최대한 살린다. 근거 찾기와 고치기를 나눈다. | grounded() (prd_engine.py)가 버리는 대신 고치는 흐름에 쓴다. 숫자는 numbers.grounded_numbers()로, 숫자 없는 값은 낱말 포함으로 근거를 찾고, 근거 없는 사실만 버리는 지금 구조를 유지한다. 고치기 단계는 새로 두지 않는다. | 작음 |
| Extract, Define, Canonicalize: An LLM-based Framework for Knowledge Graph Construction | 2024 · EMNLP 2024 | https://arxiv.org/abs/2404.03868 | 뽑기·정의·표준화를 나눈다. 뽑을 때는 스키마를 다 보여 주지 않고 뽑은 뒤에 같은 뜻을 하나로 모은다. | _value_matches() (run_simulation.py)와 _strip_label() (prd_engine.py)에 쓴다. "객실 6개"와 "6개", "매일 10~20시"와 "10시~20시" 같은 표현 차이는 표준화 단계에서만 허용하고, 뽑기 단계의 스키마는 그대로 둔다. | 작음 |
| Correctable-DST: Mitigating Historical Context Mismatch between Training and Inference for Improved Dialogue State Tracking | 2022 · EMNLP 2022 | https://aclanthology.org/2022.emnlp-main.56/ | 이전에 틀린 상태가 다음 턴으로 번지는 문제를 틀린 칸 찾기·바뀔 칸 찾기로 푼다. 상태 생성 전에 어느 칸을 손볼지 먼저 정한다. | turn()과 apply_updates() (prd_engine.py)의 정정 처리에 쓴다. "A 말고 B" 발화는 CHANGE_NORMS로 걸러내는데, 어느 칸의 값을 갈아 끼울지 정하는 규칙이 빈약하다. 고칠 칸 탐지를 먼저 두고 값 덮어쓰기를 뒤에 둔다. | 중간 |
| Using LLMs for the Extraction and Normalization of Product Attribute Values | 2024 · ADBIS 2024 | https://arxiv.org/abs/2403.02130 | 뽑기와 표준화를 나눠서 재고, 이름 펼치기·단위 바꾸기·문자열 다듬기를 표준화에서 한다. 뽑은 값과 표준화한 값을 따로 둬서 재는 기준을 만든다. | _separate_menu_price()와 _cut_price() (prd_engine.py)에 쓴다. 메뉴 이름 다듬기와 가격 단위 맞추기를 분리하고, 가격 합치기 전에 grounded()로 지어낸 가격을 먼저 버리는 지금 순서를 지킨다. | 작음 |

## 조사 2: 저장소

| 이름 | URL | 별 수 | 마지막 커밋 | 라이선스 | 하는 일 | 푸는 문제 | 설치 무게 | 추천 |
|---|---|---|---|---|---|---|---|---|
| NVIDIA NeMo-text-processing | https://github.com/NVIDIA/NeMo-text-processing | 508 | 2026-09-18 | Apache-2.0 | 말한 형태와 문서 형태를 바꾸는 WFST 규칙 묶음. 한국어 폴더(ko)에 data·taggers·verbalizers가 있다. | 범위 "3~4만원", 시각 "반", 단위 목록 보강 | 무거움. Pynini(OpenFst C 확장) 필요, 리눅스 권장, 신경망 쪽은 PyTorch까지. 통째 설치 불가. | 참고만. 규칙 베끼기 용도. |
| bab2min kiwipiepy | https://github.com/bab2min/kiwipiepy | 405 | 2026-09-25 | Apache-2.0 (2026-09-20에 v0.24.0에서 바뀜) | 한국어 형태소 분석기 파이썬 묶음. 낱말 나누기, 품사, 사용자 사전, 오타 교정까지. | 칸 이름 떼기, "낱말 속 숫자 글자" 판단 | 무거움. C++17 컴파일러와 CMake 필요, 모델 묶음(kiwipiepy_model)이 따로 깔림. | 참고만. 지금은 문맥규칙 유지. |
| konlpy konlpy | https://github.com/konlpy/konlpy | 1.5k | 2022-11-10 | GPL v3 (LICENSE 파일에서 확인) | 한국어 형태소 분석기들을 한 API로 묶은 묶음. | 칸 이름 떼기, 표현 비교 | 무거움. 뒤쪽 분석기들이 자바 실행 환경을 물고, 설치가 깨지기 쉽다. | 불필요. 멈춰 있고 무겁다. |
| lovit soynlp | https://github.com/lovit/soynlp | 993 | 2021-02-01 | LGPL v3 (LICENSE 파일에서 확인) | 말뭉치 통계로 낱말을 찾는 순수 파이썬 묶음. 명사 뽑기, 점수 토크나이저, 정규화 도우미. | 낱말 경계, 붙여 쓴 메뉴 이름 | 가벼움. 순수 파이썬에 numpy·scipy·scikit-learn. 다만 통계 학습에 말뭉치가 필요해서 한 문장씩 오는 채팅에는 바로 못 쓴다. | 참고만. 붙여쓰기 경계 아이디어용. |
| haven-jeon PyKoSpacing | https://github.com/haven-jeon/PyKoSpacing | 436 | 2024-07-04 | GPL-3.0 | 띄어쓰기 자동 교정. 뉴스 말뭉치로 학습한 딥러닝 모델. | 붙여 쓴 입력의 칸 이름 떼기 | 무거움. TensorFlow와 모델 파일 필요. | 불필요. 무겁고 띄어쓰기가 우리 병목이 아니다. |
| Kyubyong g2pK | https://github.com/Kyubyong/g2pK | 271 | 2020-08-03 | Apache-2.0 | 한글을 발음대로 바꾸는 규칙 묶음. 숫자 읽기를 문맥에 따라 가름(12시 열두, 12분 십이). | 고유어·한자어 읽기 가름 | 중간~무거움. jamo·python-mecab-ko·konlpy·nltk를 함께 요구. 멈춰 있다. | 참고만. "12시 12분" 같은 읽기 가름 규칙만 본다. |
| jonghwanhyeon python-mecab-ko | https://github.com/jonghwanhyeon/python-mecab-ko | 111 | 2024-07-14 (v1.3.7) | BSD-3-Clause | mecab-ko 파이썬 바인딩. 형태소·명사·품사 뽑기. | 칸 이름 떼기, 낱말 속 숫자 글자 판단 | 무거움. C 확장 빌드와 mecab-ko 사전 필요. | 불필요. kiwipiepy와 같은 이유로 지금은 제외. |
| daviddrysdale python-phonenumbers | https://github.com/daviddrysdale/python-phonenumbers | 3.8k | 2026-09-24 (v9.0.40 준비) | Apache-2.0 | 구글 전화번호 라이브러리의 파이썬 옮김. 파싱·형식 맞추기·유효성, 글 속 번호 찾기. | 전화번호 "공일공에…" 읽기 | 가벼움. 순수 파이썬, pip 한 방. 핵심 메타 약 2MB, 지역·통신사 메타는 따로. | 참고만. 지금 _spoken_phone() 규칙으로 충분하고 새 의존은 안 늘린다. |
| JDongian python-jamo | https://github.com/JDongian/python-jamo | 121 | 2022-08-16 | Apache-2.0 | 한글 음절과 자모를 나누고 합치는 순수 파이썬 묶음. | 자모 단위 비교 ("빵" 오타 같은 소리 읽기) | 가벼움. 순수 파이썬. | 참고만. 소리나는대로 적은 입력 대응 아이디어용. |
| WieeRd KoreanNumber | https://github.com/WieeRd/KoreanNumber | 7 | 2021-02-10 | 미확인 (페이지에 라이선스 표시 없음) | 한글 숫자와 아라비아 숫자 바꾸기. 파일 두 개짜리 작은 묶음. | "삼만오천원" 같은 기본 변환 | 가벼움. 순수 파이썬 파일 두 개. 다만 고유어·생략형("만오천")·범위는 못 다룸. | 불필요. 우리 numbers.py가 이미 같은 일을 하고 테스트가 붙어 있다. |

## 조사 3: 바로 쓸 아이디어 5개

1. 범위와 "반" 표현을 숫자 해석기에 넣는다.
   - 무엇: "3~4만원"은 {30000, 40000} 둘 다, "열 시 반"·"오후 두시 반"은 30분 더하기, "한 시간 반"은 90분, "만오천"은 15000으로 읽는다. NeMo ko 규칙의 money·time 패턴과 g2pK의 읽기 가름을 참고해서 경우를 늘린다.
   - 어느 파일·함수: app/services/numbers.py의 numbers_in(), _parse_chunk(), value_numbers().
   - 예상 효과: 가격·영업시간 근거 판정 실패(T3에서 값은 맞는데 근거 없음으로 버려지던 유형).
   - 새 의존성: 없음.
   - 위험: 범위를 두 값으로 풀면 "3~4만원"을 "3만원"으로 적은 것도 근거 있음이 될 수 있다. 상한·하한을 따로 기록하고 채점에서는 구간 겹침으로 본다.

2. 채점기 비교를 두 단계로 나눈다.
   - 무엇: 1단계 정규화 동등(_norm 뒤 같은지), 2단계 숫자 집합 포함(fa가 gb 안에 있는지). 부분 문자열 포함(a in b)은 숫자 없는 짧은 값에만 허용한다. EDC 논문의 뽑기·표준화 분리와 같다.
   - 어느 파일·함수: evals/run_simulation.py의 _value_matches(), _nm().
   - 예상 효과: "객실 6개"와 "6개" 같은 표현 차이는 통과시키고 지어낸 값은 계속 잡는다.
   - 새 의존성: 없음.
   - 위험: 숫자 집합이 비면 1단계로만 재야 해서 숫자 없는 factual 값의 기준이 헐거워질 수 있다. 단어 포함 조건을 함께 둔다.

3. 근거 확인에 조각별 근거 기록을 남긴다.
   - 무엇: grounded()가 True·False만 돌려주지 말고 어느 조각(메뉴·가격·숫자)이 원문의 어디에 있었는지 남긴다. Thutmose 논문의 낱말-조각 일대일 맞춤과 RARR의 근거 찾기·고치기 분리를 따른다.
   - 어느 파일·함수: app/services/prd_engine.py의 grounded(), _separate_menu_price(), apply_updates().
   - 예상 효과: 메뉴·가격 뭉침 분리(T3 e013·e025 계열) 실패를 로그로 바로 보인다.
   - 새 의존성: 없음.
   - 위험: 기록 구조가 바뀌면 대화 기록(trace)을 읽는 쪽과 맞아야 한다. trace에 필드 하나만 더한다.

4. 정정은 고칠 칸 탐지를 먼저 둔다.
   - 무엇: "A 말고 B", "바꿔", "대신" 발화는 Correctable-DST처럼 어느 칸을 고칠지 먼저 정하고 값을 덮어쓴다. CHANGE_NORMS 탐지를 넓히고 이전 카드 값과 겹치는 칸을 고칠 칸으로 본다.
   - 어느 파일·함수: app/services/prd_engine.py의 turn(), apply_updates(), CHANGE_NORMS 주변.
   - 예상 효과: 사용자 정정 처리(T3 r4 "일요일은 쉬는 걸로"가 엉뚱한 칸에 들어가던 유형, "객실 3개"가 "3개"만 남던 유형).
   - 새 의존성: 없음.
   - 위험: 고칠 칸을 잘못 고르면 멀쩡한 값을 덮어쓴다. 물은 칸과 겹칠 때만 자동 덮어쓰고 나머지는 확인 질문으로 돌린다.

5. 전화번호는 지금 규칙을 유지하고 라이브러리는 나중으로 미룬다.
   - 무엇: "공일공에…" 읽기는 _spoken_phone() 그대로 두고 python-phonenumbers는 쓰지 않는다. 유효성 검사가 필요해지면 그때 lite 형태로 검토한다.
   - 어느 파일·함수: app/services/prd_engine.py의 _spoken_phone(), grounded()의 phone 분기.
   - 예상 효과: 전화 지어냄 0건 유지, 의존성 0개 유지.
   - 새 의존성: 없음(지금).
   - 위험: 지역번호·050 같은 특이 번호 규칙이 계속 손으로 늘어난다. 케이스 목록을 테스트로 먼저 쌓는다.

### 세 가지 질문에 대한 답

1. 형태소 분석기로 "낱말 속 숫자 글자" 판단을 대신할 가치가 있나.
   - 없다. kiwipiepy는 살아 있고(2026-09-25 커밋) Apache-2.0이라 조건은 좋지만 C 확장과 모델 묶음이 필요해서 매 턴 호출에 무겁다. 더 중요한 건 "오일"(5일·기름), "사인" 같은 동음이의는 품사만으로 안 풀리고 앞뒤 문맥이 필요하다는 점이다. 지금 _sino_is_number() 문맥규칙을 유지하고, NeMo ko 규칙에서 단위 목록만 베껴 오는 편이 싸고 정확하다.

2. NeMo 한국어 ITN 규칙에서 가져올 만한 규칙이 있나.
   - 있다. ko 폴더(data·taggers·verbalizers)가 실제로 있고 2026년에도 한국어 관련 손질(조사 붙이기 후처리, ITN v2)이 있었다. cardinal·money·time·measure 패턴에서 단위 이름과 범위·분수·시각 틀을 참고한다. 다만 Pynini 통째 설치는 무거우니 규칙 베끼기만 하고 문법 파일 자체는 가져오지 않는다.

3. 채점기 표현 비교를 어떻게 하면 지어낸 값은 놓치지 않으면서 표현 차이만 허용하나.
   - 숫자 있는 값은 숫자 집합으로 재고, 말만 다른 경우는 좁게 허용한다. "매일 10~20시"와 "10시부터 밤 9시까지"는 value_numbers() 집합이 같아야 통과, "아메리카노 5천원" 같은 건 메뉴 조각·가격 조각이 둘 다 원문에 있어야 통과(_separate_menu_price() 조건과 같은 잣대). 부분 문자열 포함은 "예약 문의 늘리기" 같은 숫자 없는 값에만 쓰고, 숫자 있는 값에는 쓰지 않는다. 이렇게 하면 표현 차이는 살고 근거 없는 숫자는 걸린다.

## 미확인 목록 (열지 못해서 결론에 쓰지 않음)

- hgtk: 후보로만 보고 페이지를 열지 않았다. 자모 다루기는 python-jamo로 대신 확인했다.
- allo-media text2num: 영어·프랑스어 위라 한국어 수사 문제와 안 맞아서 열지 않았다.
- google libphonenumber 본체: 파이썬 옮김(daviddrysdale/python-phonenumbers)만 열었다. 본체 별 수·커밋·라이선스는 미확인.
- WieeRd KoreanNumber 라이선스: 페이지를 열었으나 라이선스 표시가 없어 미확인.
- Thutmose Tagger 학회: arXiv 페이지를 열었으나 학회 표기가 없어 연도(arXiv 2022)만 적었다.
- konlpy·soynlp를 뺀 나머지 저장소의 세부 동작(모델 크기·실행 속도)은 설치해 보지 않아 적지 않았다. 패키지 설치는 금지라 문서 기준 판단만 썼다.
