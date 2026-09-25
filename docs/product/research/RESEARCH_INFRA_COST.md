# 인프라·비용 웹 리서치 (W3)

- 확인 날짜: 2026-09-26 (아래 모든 출처에 적용, 별도 표기 없으면 이 날짜 확인)
- 대상 코드: `app/llm.py`(주/대비 모델), `app/config.py`(STT·TTS), `deploy/Caddyfile`(sslip.io 2개 호스트), `app/services/quote.py`(RULE_* 상수)
- 원칙: 공식 문서로 확인 못한 것은 "확인 필요"라고 표기한다. 지어내지 않는다.

## 1) build.nvidia.com 무료 사용

| 항목 | 내용 | 출처 |
|---|---|---|
| 무료 크레딧 | 가입 시 1,000 크레딧 지급, 상한 5,000 크레딧이라는 사용자 보고 다수. 가입에 신용카드 불필요 | https://forums.developer.nvidia.com/t/api-credits-for-build-nvidia-com/306633, https://build.nvidia.com/llms.txt |
| 요청 제한 | 무료 등급은 대부분 모델 분당 최대 40요청(RPM), 토큰 과금 없음. 개인 한도는 대시보드 우상단 표시 | https://build.nvidia.com/models?q=LLM (FAQ 문구) |
| 과부하 503 양상 | 작업자 큐가 차면 `ResourceExhausted: All workers are busy, please retry later` 503이 내려온 사례 보고 | https://github.com/earendil-works/pi/issues/6364 |
| 503·429 대응 권고 | 지수 백오프+지터로 재시도, Retry-After가 있으면 준수. 400번대(429 제외)는 재시도하지 않기. 우리 `app/llm.py`의 대비 모델 폴백+60초 쿨다운은 이 권고와 같은 방향 | https://github.com/api-evangelist/nvidia/blob/main/rate-limits/nvidia-rate-limits.yml (NVIDIA 공식 문서 아님, 확인 필요: NVIDIA 공식 503 대응 문서는 못 찾음) |
| 무료 사용의 상업 이용 | 불가. Trial 약관 1.2: 평가는 제한된 시험 목적만, 결과물을 상업 환경에서 쓰려면 별도 구독 필요 | http://assets.ngc.nvidia.com/products/api-catalog/legal/NVIDIA%20API%20Trial%20Terms%20of%20Service.pdf |
| 유료 전환 경로 | NVIDIA AI Enterprise: GPU당 연 4,500달러 또는 클라우드 시간당 GPU당 약 1달러. GPU 수 기준 과금. 90일 평가 라이선스 있음 | https://docs.nvidia.com/ai-enterprise/planning-resource/licensing-guide/latest/pricing.html, https://docs.api.nvidia.com/nim/docs/product, https://www.nvidia.com/en-us/data-center/products/ai-enterprise/get-started |
| 가중치 직접 운영 | Nemotron 가중치는 Hugging Face에서 내려받아 상업 환경 포함 무료 운영 가능. NIM 마이크로서비스 형태로 배포하려면 AI Enterprise 필요 | https://nvidia.com/en-us/ai-data-science/foundation-models/nemotron (FAQ 문구) |
| STT·TTS 과금 체계 | `app/config.py`의 NVCF 함수 ID 과금·한도는 이번 조사에서 공식 문서를 못 찾음 | 확인 필요 |

### 대비 모델 3종 페이지 확인

| 모델(`app/config.py` 값) | 페이지에서 확인한 내용 | 출처 |
|---|---|---|
| nvidia/nemotron-3-super-120b-a12b (주) | 120B 전체·활성 12B, 하이브리드 Mamba-Transformer MoE, 1M 컨텍스트, 출시 2026-03-11, Nemotron 개방형 모델 라이선스, 시험 서비스는 Trial 약관 적용 | https://build.nvidia.com/nvidia/nemotron-3-super-120b-a12b |
| nvidia/nemotron-3-ultra-550b-a55b (대비 1) | 550B 전체·활성 55B, 출시 2026-06-04, OpenMDW-1.1 라이선스, 시험 서비스는 Trial 약관 적용 | https://build.nvidia.com/nvidia/nemotron-3-ultra-550b-a55b |
| nvidia/nemotron-3.5-lightning-30b-a3b (대비 2) | 30B 전체·활성 3B, 특화 작업용 고속 모델. Hugging Face 안내에 상업 이용 가능 문구 있음 | https://build.nvidia.com/nvidia/nemotron-3.5-lightning-30b-a3b, https://huggingface.co/nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-BF16 |

## 2) Let's Encrypt 한도와 sslip.io

| 한도 항목 | 내용 | 출처 |
|---|---|---|
| 등록 도메인당 신규 인증서 | 7일당 50개. 계정 무관 전역 한도. 등록 도메인 판정에 Public Suffix List 사용 | https://letsencrypt.org/docs/rate-limits/ |
| 계정당 신규 주문 | 3시간당 300개 (36초당 1개씩 회복) | https://letsencrypt.org/docs/rate-limits/ |
| 동일 식별자 집합 | 7일당 5개 (갱신은 별도 취급되면 면제) | https://letsencrypt.org/docs/rate-limits/ |
| sslip.io의 PSL 등재 | 미등재. 2026-09-26에 `https://publicsuffix.org/list/public_suffix_list.dat`를 내려받아 검색했더니 `sslip` 0건, `nip.io` 0건. 즉 등록 도메인은 `sslip.io` 전체가 되어 전 세계 사용자와 한도를 공유 | 직접 확인(위 URL), 목록 열람: https://publicsuffix.org/list/index.html?commit=Search |
| 실제 발급 실패 사례 | 2026-02-09 sslip.io 주당 한도 소진 신고(`too many certificates ... already issued for "sslip.io"`). 한도를 5만→10만→20만으로 올렸으나 2026-02-15에 10만 한도도 소진 보고 | https://github.com/cunnie/sslip.io/issues/108 |
| 우리 구성의 위험 | `deploy/Caddyfile`의 호스트 2개(`144.24.91.250.sslip.io`, `144-24-91-250.sslip.io`)는 인증서 2장이면 되지만, 발급 시점이 전역 한도 소진 구간과 겹치면 실패한다. 실패는 우리 사용량과 무관하게 발생 가능 | 위 이슈 + LE 한도 문서로 판단 |

### 대안

| 대안 | 내용·비용 | 출처 |
|---|---|---|
| 자체 도메인 | 가비아 행사 기준 신규 등록 `.com` 19,800원, `.kr`·`.co.kr` 16,500원 (부가세 포함, 행사 종료일 있음). 연장료는 신규가보다 비쌀 수 있어 결제 화면 확인 필요. 등록 도메인을 단독 보유하면 7일 50개 한도를 혼자 씀 | https://domain.gabia.com/, https://ridecop.co.kr/gabia-domain-purchase-cost-registration-connection/ |
| Caddy 기본 폴백 | Caddy는 기본적으로 LE 실패 시 ZeroSSL로 자동 폴백한다는 커뮤니티 보고 다수. 우리 Caddyfile에 별도 설정이 없어도 폴백이 동작할 가능성이 있으나 공식 문서 미확인 | 확인 필요: https://caddy.community/t/certificates-being-renewed-with-zerossl-instead-of-lets-encrypt/17801, https://caddy.community/t/debugging-letsencrypt-vs-zerossl/29752 |
| 무료 도메인(DuckDNS 등) | DuckDNS는 `*.duckdns.org` 무료 동적 DNS 제공. 데모용 대체 주소로 쓸 수 있으나 PSL 등재·LE 한도 공유 여부는 미확인 | https://www.duckdns.org/, https://www.duckdns.org/faqs.jsp (PSL 여부는 확인 필요) |

## 3) 한국 소상공인 홈페이지 외주 시세

| 출처 | 원페이지(반응형) | 5페이지 안팎 | 문의폼·부가 기능 | 출처 URL |
|---|---|---|---|---|
| 크몽 랜딩페이지 가격표 | 최저 6만~10만원, 평균 30만~80만원(거래 평균 49만원), 최고 120만원 | 섹션 4~5개 초과 시 추가 비용. 반응형은 평균 20~30% 추가 | 문의폼·카카오 상담·예약 연동 시 퍼블리싱/개발 단가 상승 | https://kmong.com/prices/랜딩페이지-제작 |
| 크몽 카테고리 안내 | 템플릿형 30만~80만원 | 맞춤 개발 80만~300만원 (전체 30만~300만원) | 회원가입·결제·예약은 맞춤 쪽으로 견적 상승 | https://kmong.com/category/601 |
| 크몽 개별 판매자(스프링디자인) | 49만원 (1페이지·5섹션 이내, 반응형) | 89만원 (5페이지 이내) | 카카오톡 채널 연결 등은 기본 포함 표기 | https://kmong.com/gig/720418 |
| 숨고 가격표 | 웹 디자인 평균 50만원 (최저 10만~최고 250만원) | 웹 디자인 외주 평균 78만원 (30만~150만원) | 웹 개발 평균 160만원 (최저 30만~최고 1,000만원) | https://soomgo.com/prices/웹-디자인, https://soomgo.com/prices/웹-개발, https://soomgo.com/hire/웹-디자인 |
| 위시켓 가이드 2025 | 웹빌더 구축 30만원 안팎+월 2만~3만원 | 솔루션형 300만~700만원 (게시판·문의폼 포함) | 자체 개발 600만~1,200만원 (최대 2,000만원). 전체 평균 430만원 (30만~2,000만원) | https://blog.wishket.com/blog/47783 |
| 위아웹 정찰가 | 기본형 55만원~ (문의폼·모바일 반응형 포함) | 표준형 99만원~ (약 12페이지) | 예약·신청 +20만원, 결제 +35만원, 블로그·게시판 +12만원, 회원 +25만원 | https://wiaweb.site/index.html |
| KOE(크몽 판매자) | 10만원 (직접 입력형) | 25만원 (다중 페이지 직접 입력형) | 문의폼 설정 포함 오픈 대행 50만원 | https://koe.kr/pricing |

- 읽는 법: 원페이지는 10만~80만원이 중심대, 5페이지급은 80만~160만원(프리랜서)~300만원(에이전시)이 중심대. 위시켓 평균 430만원은 기업형·중대형까지 포함한 값이라 소상공인 원페이지와 직접 비교하면 안 된다.

## 4) OCI 무료 계층과 우리 compose 위험

| 항목 | 내용 | 출처 |
|---|---|---|
| Ampere A1 무료 한도 | 월 1,500 OCPU시간+9,000GB시간 = 2 OCPU·12GB 상시와 동등. 2026-06-15부터 기존 4 OCPU·24GB에서 절반으로 축소 | https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm, https://www.infoq.com/news/2026/07/oracle-cloud-free-tier-limits/, https://terminalbytes.com/oracle-cloud-free-tier-changes-2026 |
| 그 외 무료분 | AMD 마이크로 2개, 블록 스토리지 합계 200GB, 아웃바운드 월 10TB | https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm, https://www.oracle.com/cloud/compute |
| 부트 볼륨 최소값 | 인스턴스당 최소 47GB. A1 2 OCPU를 1+1로 나누면 부트 볼륨 2개 필요 | https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm |
| 우리 compose 자원 | `db` 메모리 상한 256MB(shared_buffers 32MB, 최대 연결 30), `backend`+`caddy`는 정적 전달 위주라 2 OCPU·12GB 안에 여유가 있다. 디스크도 DB·인증서·이미지 합계가 200GB에 한참 못 미친다 | `docker-compose.yml` + 위 무료 한도 문서로 판단 |
| 유휴 회수 | 7일 동안 CPU 95분위 <20% 이고 네트워크 <20% 이고 메모리 <20%(A1만) 이면 Oracle이 인스턴스 정지 가능. 데모 대기 상태의 저사용 서버가 해당될 수 있음 | https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm |
| 유료 전환(PAYG) 시 회수 면제 | 한도 내 사용은 무료 유지 + 회수 대상 제외라는 보고가 있으나 공식 문서 미확인 | 확인 필요: https://community.oracle.com/customerconnect/discussion/663398/compute-instance-idle |
| A1 용량 부족 시 재시작 실패 | 리전 용량 부족으로 생성·재시작이 밀린다는 보고가 있으나 공식 수치 미확인 | 확인 필요 |

## quote.py RULE_* 상수 추천값

| 상수 | 현재값 | 추천값 | 근거 |
|---|---|---|---|
| RULE_BASE individual·group | 500,000 | 유지 500,000 | 크몽 랜딩 평균 49만원, 숨고 웹 디자인 평균 50만원과 일치 |
| RULE_BASE_DEFAULT (가게·기타) | 600,000 | 유지 600,000 | 위아웹 기본형 55만원~와 같은 대. 가게 홈페이지는 문의폼이 붙는 일이 많아 기본값이 개인보다 약간 높은 것이 타당 |
| RULE_BASE webservice | 1,200,000 | 유지 1,200,000 | 솔루션형 하한 300만원(위시켓)보다 낮게 잡은 보수값. 베타 참고용 과소 추정이 과대 추정보다 안전 |
| RULE_PER_SECTION | 80,000 | 유지 80,000 | 5섹션 추가 시 +40만원 → 원페이지 50만원+40만원=90만원. 크몽 스프링디자인 5페이지 89만원과 일치 |
| RULE_PER_FEATURE ready·owner_setup | 각 100,000 | 유지 | 위아웹 블로그·게시판 +12만원과 같은 대 |
| RULE_PER_FEATURE alternative | 150,000 | 유지 | 결제(+35만원)·회원(+25만원)보다는 낮은 대체 수단 단가로 타당 |
| RULE_INQUIRY_FORM | 200,000 | 유지 200,000 | 위아웹 예약·신청 +20만원과 일치. KOE 오픈 대행 50만원(문의폼 포함)의 부분값으로도 타당 |
| 반올림 단위 100,000 | 유지 | 유지 | 참고 견적은 10만원 단위가 읽기 쉬움 |

## 데모 당일 위험·대비

| 위험 | 영향 | 대비 (이미 된 것 / 할 것) | 관련 파일 |
|---|---|---|---|
| NIM 503·429 또는 크레딧 소진 | AI 견적·채팅 실패 | 된 것: 대비 모델 폴백+쿨다운(`app/llm.py`), 정적 견적 폴백, 규칙 참고 견적(`quote.py`). 할 것: 데모 전 크레딧 잔량 확인, 주 모델을 가벼운 호출부터 예열 | `app/llm.py`, `app/services/quote.py` |
| sslip.io 전역 LE 한도 소진으로 인증서 발급 실패 | HTTPS 접속 불가 | 할 것: 데모 수일 전 미리 발급해 `caddy_data` 볼륨 유지, 재발급 자제. ZeroSSL 폴백 동작은 공식 미확인이라 사전 검증 필요. 여유 있으면 자체 도메인(연 2만원대) 준비 | `deploy/Caddyfile`, `docker-compose.yml` |
| OCI 유휴 회수로 인스턴스 정지 | 서버 전체 중단 | 할 것: 데모 7일 전부터 사실상 매일 접속·배포로 사용 기록 남기기. 정지 시 콘솔에서 재시작하면 부트·블록 볼륨은 유지됨. PAYG 전환은 공식 미확인이라 Harold 판단 필요 | `docker-compose.yml` |
| A1 용량 부족으로 재시작 실패 | 정지 후 복구 불가 | 확인 필요. 대비: 데모 전날 스냅샷·볼륨 상태 기록, 재시작은 데모 당일이 아니라 전날에 시험 | 확인 필요 |
| STT·TTS(NVCF) 한도·과금 | 음성 기능 실패 | 확인 필요. 대비: `stt_enabled`·`tts_enabled`를 끄고도 시연이 이어지도록 순서 준비 | `app/config.py` |
| 무료 등급의 상업 이용 오해 | 베타를 상업 서비스로 안내 시 약관 위반 | 무료 NIM은 시험 목적만 허용되므로 대외 안내는 "베타 시연"으로 한정. 상업 전환 시 AI Enterprise 필요 | Trial 약관 PDF(§1 표) |

## 우리 프로젝트에 대한 추천

| 무엇을 | 왜 | 바꿀 파일/문서 |
|---|---|---|
| RULE_* 값은 그대로 두고 주석의 "확인 필요: 시세 조사로 갱신"을 이번 문서 번호로 교체 | 시세 7개 출처와 정합(특히 50만+40만=90만원)하므로 값 변경보다 근거 고정이 낫다 | `app/services/quote.py` 84~92행 주석 |
| Caddy 인증서를 데모 수일 전 발급·고정하고 `caddy_data` 볼륨을 함부로 지우지 않기 | sslip.io 전역 한도 소진은 우리와 무관하게 터지며 데모 당일 재발급이 막힐 수 있음 | `deploy/Caddyfile`, `docker-compose.yml` (볼륨 부분) + 배포 순서 문서 |
| ZeroSSL 폴백 실제 동작을 스테이징에서 검증 | LE 실패 시 자동 폴백이 안 되면 데모 당일 복구가 없음. 커뮤니티 보고만 있고 공식 미확인 | `deploy/Caddyfile` (검증 후 필요 시 issuer 설정 추가) |
| 자체 도메인 1개(연 2만원대) 확보 검토 | 7일 50개 한도를 단독으로 쓰게 되어 sslip.io 전역 한도 위험 제거. 비용은 연간 커피 몇 잔 수준 | 신규 문서(구매·연결 순서), `deploy/Caddyfile` |
| 유료 전환 전에는 대외 문구를 "베타 시연"으로 통일 | 무료 NIM 키의 상업 이용은 Trial 약관 위반 소지 | 대외 안내 문서, 시안 노출 문구(`BETA_NOTE`는 유지) |
| STT·TTS 한도·과금 별도 확인 | 이번 조사에서 NVCF 함수 과금 공식 문서를 못 찾음 | 후속 리서치 문서 |

W3 exit 0
