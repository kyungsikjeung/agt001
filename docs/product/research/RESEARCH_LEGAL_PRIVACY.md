# W1 법·개인정보 웹 리서치 (RESEARCH_LEGAL_PRIVACY)

- 작성일: 2026-09-26 (모든 출처 확인일과 같음)
- 읽은 것: `static/privacy.html` (확인 필요 표시), `docs/product/USER_DB_PLAN.md` (법적 체크리스트), `app/services/inquiries.py` (문의 저장·전달, 보관 30일)
- 방법: 읽기만 (API 호출·가입·로그인·폼 제출 없음)
- 규칙: 공식 문서로 확인 못한 것은 `확인 필요`. 법률 자문 아님. 시행 전 법률 검토 필요.

## 1) NVIDIA 호스팅 API

| 대상 | 입력 보관 여부·기간 | 학습 사용 여부 | 처리 국가 | 관련 약관·개인정보 문서 URL (확인일 2026-09-26) |
|---|---|---|---|---|
| NIM 채팅·임베딩 (`build.nvidia.com`, `integrate.api.nvidia.com`) 체험판 | 세션 중 서비스 제공 목적 처리. 세션 종료 후 저장·사용 안 함이 원칙. 단 특정 서비스에 별도 고지된 경우 예외. 보관 일수는 `확인 필요` (공식 문서에 일수 없음) | 원칙은 서비스 제공 목적만. 단 모델별 체험 화면 고지에는 `입력·출력을 기록해 제품·서비스 개선(모델 포함)에 사용`이라는 문구가 있음. 둘의 관계는 `확인 필요` (아래 비고 참조) | `확인 필요` (공식 문서에서 처리 리전 명시 못 찾음. 운영사는 미국 기업) | 체험판 약관 PDF: https://assets.ngc.nvidia.com/products/api-catalog/legal/NVIDIA%20API%20Trial%20Terms%20of%20Service.pdf (2.2·2.3·2.7·3.3절, 확인일 2026-09-26). 안내 스레드: https://forums.developer.nvidia.com/t/clarification-on-trial-api-use/334275 (확인일 2026-09-26). 모델별 고지 예: https://build.nvidia.com/nvidia/nsight-copilot (확인일 2026-09-26) |
| Riva Parakeet 음성 인식 (`grpc.nvcf.nvidia.com`) | `확인 필요` (NVCF 약관의 일반 수집 항목만 확인됨. 음성 원본·전사 텍스트의 보관 일수 공식 명시 없음) | `확인 필요` (NVCF 약관은 `작업량 지표·오류/실행 로그`를 운영·개선 목적 수집으로 명시. 음성 내용물의 모델 학습 사용 여부는 별도 명시 못 찾음) | `확인 필요` (공식 문서에서 리전 명시 못 찾음) | NVCF 서비스별 약관: https://www.nvidia.com/en-us/agreements/cloud-services/service-specific-terms-for-nvcf-service/ (7장 수집 목적, DPA 준용, 확인일 2026-09-26). 호출 방식 예: https://build.nvidia.com/nvidia/parakeet-ctc-1_1b-asr/api (확인일 2026-09-26) |
| Magpie 음성 합성 (`grpc.nvcf.nvidia.com`) | `확인 필요` (Parakeet 행과 같음. 합성용 텍스트의 보관 일수 공식 명시 없음) | `확인 필요` (Parakeet 행과 같음) | `확인 필요` (공식 문서에서 리전 명시 못 찾음) | NVCF 서비스별 약관: https://www.nvidia.com/en-us/agreements/cloud-services/service-specific-terms-for-nvcf-service/ (확인일 2026-09-26). 호출 방식 예: https://build.nvidia.com/nvidia/magpie-tts-multilingual/api (확인일 2026-09-26) |
| NVIDIA 공통 개인정보방침 | 계정·기업 데이터는 교류가 없을 경우 5년까지 보관 후 삭제 취지 기재. API 입력물 보관 기간은 이 문서에서 못 찾음 → `확인 필요` | AV·AI 연구용 공개 데이터의 학습 사용 기재는 있으나, 호스팅 API 입력물의 학습 사용은 모델별 고지를 봐야 함 | 국가 목록은 있으나 API 처리 리전 명시는 못 찾음 → `확인 필요` | https://www.nvidia.com/en-us/about-nvidia/privacy-policy/ (확인일 2026-09-26) |

- 비고 1 (체험판 이중 고지): 약관 2.2·2.3은 `세션 중 서비스 제공 목적 처리, 종료 후 미저장(예외 별도 고지)` 취지이고, 포럼 답변도 이를 안내함. 출처: https://forums.developer.nvidia.com/t/clarification-on-trial-api-use/334275 (확인일 2026-09-26). 반면 모델 체험 화면에는 `입출력 기록·제품 개선 사용, 보안·부정사용 감시 기록, 기밀·개인정보 업로드 금지` 취지 고지가 있음. 출처: https://build.nvidia.com/nvidia/nsight-copilot (확인일 2026-09-26). 어느 쪽이 우리 사용 구간에 적용되는지, 유료 전환 시 조건이 바뀌는지는 `확인 필요`.
- 비고 2 (NVCF 수집 항목): 설정·운영체제 데이터, 작업량 지표(실행 수·GPU 시간 등), 오류·실행 로그를 수집하고, 오류·실행 로그는 고객 선택으로 삭제 가능 취지. 고객 콘텐츠는 DPA에 따라 처리 취지. 출처: https://www.nvidia.com/en-us/agreements/cloud-services/service-specific-terms-for-nvcf-service/ (확인일 2026-09-26). DPA 원문·보관 일수·리전은 `확인 필요`.
- 비고 3 (자체 NIM): 자체 호스팅 NIM은 입력이 NVIDIA로 가지 않는다는 취지의 포럼 답변이 있으나 2차 출처이므로 참고만. 출처: https://forums.developer.nvidia.com/t/privacy-concern-about-nvidia-nim/314580 (확인일 2026-09-26). 공식 문구 확인은 `확인 필요`.

## 2) 한국 개인정보 보호법 (2023.9 개정 이후)

### 2-1 국외 이전 고지 항목

| 항목 | 내용 | 출처 URL (확인일 2026-09-26) |
|---|---|---|
| 이전 가능 조건 5가지 | 별도 동의 / 법령·조약 근거 / 계약 체결·이행에 필요한 처리위탁·보관 / 보호위 고시 인증 + 조치 / 보호수준 동등성 인정국 | https://www.privacy.go.kr/front/contents/cntntsView.do?contsNo=367, https://govbrief.kr/scan/011357/28%EC%9D%988/ |
| 별도 동의 시 사전 고지 5가지 | 이전 항목 / 이전 국가·시기·방법 / 이전받는 자 성명(법인은 명칭+연락처) / 이전받는 자 이용 목적·보유 이용 기간 / 거부 방법·절차·효과 | https://casenote.kr/%EB%B2%95%EB%A0%B9/%EA%B0%9C%EC%9D%B8%EC%A0%95%EB%B3%B4_%EB%B3%B4%ED%98%B8%EB%B2%95/%EC%A0%9C28%EC%9E%90%EC%9D%988/ (법 제28조의8 제2항) |
| 변경 시 | 고지 항목 변경 시 알리고 다시 동의 | 같은 출처 (법 제28조의8 제3항) |
| 계약 이행용 처리위탁·보관 시 | 방침 공개 또는 이메일 등으로 알림. 2023.9 이후 동의 없이 가능하나 공개 의무 유지 취지 | https://www.privacy.go.kr/front/contents/cntntsView.do?contsNo=367, https://itwiki.kr/w/ISMS-P_%EC%9D%B8%EC%A6%9D_%EA%B8%B0%EC%A4%80_3.3.4.%EA%B0%9C%EC%9D%B8%EC%A0%95%EB%B3%B4%EC%9D%98_%EA%B5%AD%EC%99%B8%EC%9D%B4%EC%A0%84 |
| 방침 공개 의무 | 이전 근거 규정 공개. 동의 이전이면 동의 내용 공개 (시행령 제31조 제1항 제2호 취지) | https://govbrief.kr/scan/011468/31/, https://www.privacy.go.kr/front/contents/cntntsView.do?contsNo=367 |
| 금지·보호조치 | 법 위반 내용의 이전 계약 금지. 안전성 확보·고충·분쟁 해결 조치 | 같은 출처 (법 제28조의8 제5항, 시행령 제29조의10 취지) |

### 2-2 처리 위탁 고지 항목

| 항목 | 내용 | 출처 URL (확인일 2026-09-26) |
|---|---|---|
| 위탁 계약 문서 필수 5가지 | 목적 외 처리 금지 / 기술적·관리적 보호조치 / 재위탁 제한·접근 제한·감독·손해배상 등 (법 제26조 제1항 + 시행령 제28조 제1항 취지) | https://www.law.go.kr/LSW/flDownload.do?bylClsCd=200203&flNm=%5B%EB%B3%84%EC%A7%80+13%5D+%ED%91%9C%EC%A4%80+%EA%B0%9C%EC%9D%B8%EC%A0%95%EB%B3%B4%EC%B2%98%EB%A6%AC%EC%9C%84%ED%83%81+%EA%B3%84%EC%95%BD%EC%84%9C%28%EC%95%88%29&flSeq=145147793, https://govbrief.kr/scan/011468/28/ |
| 공개 항목 2가지 | 위탁 업무 내용 + 수탁자. 홈페이지에 계속 공개가 원칙 | https://govbrief.kr/scan/011468/28/ (시행령 제28조 제2항), https://itwiki.kr/w/ISMS-P_%EC%9D%B8%EC%A6%9D_%EA%B8%B0%EC%A4%80_3.3.2.%EA%B0%9C%EC%9D%B8%EC%A0%95%EB%B3%B4_%EC%B2%98%EB%A6%AC_%EC%97%85%EB%AC%B4_%EC%9C%84%ED%83%81 |
| 방침 기재 | 위탁 사항은 방침에 적음 (법 제30조 취지) | https://govbrief.kr/scan/011357/30/ |
| 표준 방침 작성 기준 | 보호위 `개인정보 처리방침 작성지침(2025.4.)` 참조. 원문 파일은 보호위 자료실에서 확인 | https://www.privacy.go.kr/front/bbs/bbsView.do?bbscttNo=20806&bbsNo=BBSMSTR_000000000049 (확인일 2026-09-26). 세부 항목 인용은 `확인 필요` (원문 직접 대조 전) |

## 3) 방문자 문의 저장·전달 시 우리 지위

- 전제 (`app/services/inquiries.py`, 확인일 2026-09-26): 방문자 이름·연락처·내용을 우리 DB(`InquiryRow`)에 저장(보관 30일)하고, 해당 가게 채팅방에 알림으로 전달. 동의 체크(`agree=yes`) 없으면 거부. IP는 저장 안 함.

| 구분 | 판단 기준 | 우리 사안 적용 | 방침·약관에 적을 것 |
|---|---|---|---|
| 우리가 처리자(수집 주체) | 폼·DB·보관 기간·동의를 우리가 정하면 우리가 처리자 | 해당. 폼 문구·저장·30일 파기를 우리가 정함 | 수집 항목·목적·보관 30일·파기·권리 행사를 우리 방침에 명시 |
| 가게(사장님)가 수탁자인 경우 | 사장님이 우리 지시 범위 안에서만 열람·답장하면 수탁자 취급 가능 | 알림 열람·답장만 하면 이쪽에 가까움. 단 사장님이 연락처를 따로 저장·영업 활용 시 성격 변동 | 위탁 내용(문의 전달·열람)·수탁자(해당 가게) 공개, 목적 외 이용 금지 안내 |
| 가게가 별도 처리자인 경우 | 사장님이 받은 연락처를 자기 판단으로 보관·이용하면 별도 처리자(또는 제3자 제공 상대) 취지 | 방 알림 이후 사장님 단말·메모에 남으면 이쪽으로 이동 가능 | 제3자 제공 항목·목적·보관(방 보관 정책 적용)·사장님 문의처 안내. 제공 근거(방문자 동의) 명시 |
| OCI·카카오·구글·NVIDIA | 저장·인증·AI 처리를 맡기면 위탁 또는 국외 이전 상대 | OCI 춘천은 국내 보관이라 국외 이전 아님. 위탁 해당 여부는 `확인 필요`. 카카오·구글·NVIDIA는 국외 이전 검토 대상. 이전 국가·기간은 `확인 필요` | 위탁 표(업무·수탁자)와 국외 이전 표(국가·항목·목적·기간·거부법)를 분리 기재 |

- 방침·약관 기재안 (초안, 법률 검토 전): `문의 전달` 목적, `이름·연락처·내용` 항목, `해당 가게에 전달` 상대, `수집분 30일·방 알림분은 방 보관 정책` 기간, `열람·삭제 요청처`를 각각 적는다. 수탁·제공 구분 확정 전에는 `가게 전달` 사실과 `사장님 재이용 시 사장님 책임` 취지를 함께 적는다.

## 4) 만 14세 미만·보호책임자

| 주제 | 요건 | 출처 URL (확인일 2026-09-26) |
|---|---|---|
| 만 14세 미만 | 동의가 필요하면 법정대리인 동의 + 동의 확인. 대리인 연락용 최소 정보만 아동에게 직접 수집 가능. 아동 고지는 쉬운 말·양식 | https://www.law.go.kr/LSW/lsLinkCommonInfo.do?ancYnChk=&chrClsCd=010202&lsJoLnkSeq=1029334873 (법 제22조의2), https://www.easylaw.go.kr/CSP/CnpClsMainBtr.laf?ccfNo=2&cciNo=1&cnpClsNo=2&csmSeq=659&menuType=cnpcls&popMenu=ov |
| 보호책임자 지정 | 처리 업무 총괄 책임자 지정. 소규모 예외 시 사업주·대표자가 책임자 | https://govbrief.kr/scan/011357/31/ (법 제31조) |
| 보호책임자 공개 범위 | 성명 또는 보호 업무·고충 처리 부서 명칭 + 전화번호 등 연락처를 방침에 공개 | https://govbrief.kr/scan/011357/30/ (법 제30조 관련 항목) |
| 현행 방침 평가 | `static/privacy.html`은 이름+전화만 있음. 부서(또는 역할)·이메일·처리 기한·대체 연락 수단이 없음 | `static/privacy.html` (확인일 2026-09-26) |

## 5) `static/privacy.html` 확인 필요 칸 채울 문안 초안

| 방침 위치 | 초안 문안 (베타·법률 검토 전) |
|---|---|
| 1절 문의 행의 `수탁자 확인 필요` | `당사는 방문자 문의를 자기 DB에 저장하고 해당 가게 채팅방에 전달합니다. 이 범위에서 당사는 문의 수집 주체이며, 가게는 전달받은 문의를 답장 목적 안에서 다룹니다. 가게가 연락처를 따로 저장하거나 영업에 쓰면 그 부분은 해당 가게 책임입니다. (법률 검토 후 수탁·제공 구분 확정)` |
| 3절 서버 로그 `30일 제안·확인 필요` | `서버·접근 로그(IP 포함 가능)는 30일간 보관 후 순환 삭제합니다. (운영 확정 전 잠정치. 확정 시 개정 이력에 기록)` |
| 3절 파기 절차 `실행 방식 확인 필요` | `보관 기간이 끝난 전자 파일은 복구 불가 방식으로 삭제하고, 삭제 실행 기록(시각·대상·건수)을 남깁니다. (실행 방식 운영 문서 확정 후 반영)` |
| 4절 `제3자 제공 없음(확인 필요)` | `수집 목적 안의 가게 전달(문의 알림)·인증·AI 처리 외에는 제3자 제공을 하지 않습니다. 법령 요청이 있으면 그때 알립니다. (가게 전달의 제공·위탁 구분은 법률 검토 후 확정)` |
| 4절 OCI `수탁자 여부 확인 필요` | `서버 보관: Oracle Cloud Infrastructure ap-chuncheon-1(국내). 위탁 업무 내용과 수탁자 표시는 법률 검토 후 확정합니다.` |
| 4절 NVIDIA 3행 `확인 필요` 일체 | `NVIDIA 호스팅 API(미국 기업) 처리분: 이전 국가·보관 기간·학습 사용 여부는 공식 문서로 확정되지 않아 확인 중입니다. 체험판 조건에서는 입력·출력이 기록·개선에 쓰일 수 있다는 고지가 있어, 문의·개인정보·기밀은 보내지 마세요. (유료·무기록 조건 확정 전까지)` |
| 5절 권리 행사 `절차·기한 확인 필요` | `보호책임자 연락처로 요청하세요. 본인 확인 뒤 지체 없이 조치하고 결과를 알립니다. (확인 절차·기한은 법령 기준 반영 후 확정)` |
| 6절 격리 `적용 범위 확인 필요` | `격리 제공이 목표이며, 실제 적용 범위는 점검 후 확정합니다.` |
| 7절 `접속 기록 1년·유출 절차 확인 필요` | `접속 기록 보관 기간과 유출 통지·신고 절차는 별도 문서 확정 후 반영합니다.` |
| 8절 보호책임자 | `이름: 정경식 / 역할: 개인정보 보호책임자 / 전화: 010-9656-7830 / 이메일·부서·처리 기한: 법률 검토 시 추가` |
| 9절 14세 미만 `가입 제한 확인 필요` | `14세 미만은 가입·이용 대상이 아닙니다. 14세 미만 문의가 들어오면 법정대리인 동의 확인 전에는 처리하지 않습니다. (연령 확인 방식 확정 후 반영)` |

## 6) 우리 프로젝트에 대한 추천

| 무엇을 | 왜 | 바꿀 파일/문서 |
|---|---|---|
| NVIDIA 체험판에 개인정보·문의·기밀을 보내지 않는 규칙 유지 | 체험 화면 고지에 기록·개선 사용 문구가 있어 유출·학습 논란 가능 | `docs/product` 운영 규칙 문서 (새 규칙 1줄) |
| NVIDIA 처리 국가·보관 일수·학습 사용을 `확인 필요`로 두고 유료·무기록 조건 문의 | 공식 문서에 일수·리전 명시 없음. 약관과 화면 고지가 다름 | `static/privacy.html` 4절 (이번 초안 반영 후 법률 검토) |
| 문의 방침을 `수집 주체는 우리 + 가게 전달` 구조로 적기 | 현행 코드가 우리 DB 저장 + 방 알림 전달이라 수탁자 단독 표기는 안 맞음 | `static/privacy.html` 1·2·3·4절, 문의 폼 안내문 |
| 보호책임자에 부서·이메일·처리 기한 추가 | 현행 이름+전화만으로 공개 범위 약함 | `static/privacy.html` 8절·5절 |
| 14세 미만 이용 제한·처리 중단 문구 확정 | 대상이 소상공인이라도 방치 금지 취지 | `static/privacy.html` 9절, 가입·문의 흐름 문서 |
| 서버 로그 30일·파기 실행 기록·유출 절차를 운영 문서로 확정 | 방침 잠정치를 확정값으로 바꿔야 함 | `docs/product/USER_DB_PLAN.md` 후속, `static/privacy.html` 3·7절 |
| OCI 위탁 해당 여부 법률 검토 | 국내 보관이라도 위탁 표시 의무가 갈림 | `static/privacy.html` 4절, 위탁 계약 문서 |

- 출처 모음: 법령 https://www.law.go.kr/LSW/lsInfoP.do?ancYnChk=0&lsId=011357 · 보호위 https://www.pipc.go.kr · 개인정보 포털 https://www.privacy.go.kr/front/contents/cntntsView.do?contsNo=367 · NVIDIA 방침 https://www.nvidia.com/en-us/about-nvidia/privacy-policy/ · NVCF 약관 https://www.nvidia.com/en-us/agreements/cloud-services/service-specific-terms-for-nvcf-service/ · 체험판 약관 https://assets.ngc.nvidia.com/products/api-catalog/legal/NVIDIA%20API%20Trial%20Terms%20of%20Service.pdf · 포럼 https://forums.developer.nvidia.com/t/clarification-on-trial-api-use/334275 · 모델 고지 https://build.nvidia.com/nvidia/nsight-copilot · 작성지침 https://www.privacy.go.kr/front/bbs/bbsView.do?bbscttNo=20806&bbsNo=BBSMSTR_000000000049 (이상 확인일 2026-09-26).

W1 exit 0
