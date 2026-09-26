# 웹사이트 카테고리 50종: 항목·UIUX·토큰·기능·공통모듈 조사

> 작성: 2026-09-27 / 전편: `UI_REFERENCE_2026.md`(30종: A~G).
> 본편: 신규 20종(H~L: 이커머스·종교·부동산·의료·생활서비스) 상세 + 50종 공통모듈 판정 + 배너·UI요소 스타일 + 완성형 추가 검토.
> 정직 고지: URL은 실제 방문·검색 확인분만 수록. 카테고리당 20개 확충은 수집 프로토콜(전편 §4)로 반복한다.

## 1. 50종 목록 (30 기존 + 20 신규)

- 기존 30: A1~A5 펜션·숙박, B1~B4 카페·디저트, C1~C5 식당, D1~D4 미용·뷰티, E1~E3 공방, F1~F4 학원, G1~G5 개인·단체·웹서비스 (상세: 전편 §2)
- 신규 20: H1~H6 이커머스, I1~I3 종교·비영리, J1~J3 부동산·분양, K1~K4 의료, L1~L4 생활서비스 (상세: 아래 §2)

## 2. 신규 20종 항목표 (부품 순서·필수 데이터·구성 메모)

### H. 이커머스 (공통: 상품-장바구니-결제-후기-배송)

| # | 카테고리 | 대표 부품 순서 | 필수 데이터 | 구성 메모 |
|---|---|---|---|---|
| H1 | 종합·식품 쇼핑몰 | hero(기획전 배너·캐러셀) → 베스트 → 카테고리 → 상품카드(가격·평점) → 후기 → 장바구니·결제 | 상품명·가격·옵션·배송비, 후기, 결제 수단 | 상품카드=이미지+가격+평점+장바구니 버튼이 표준. 게스트 결제 필수 (출처: Shopify·Baymard 2026: 이탈 70%, 게스트 결제가 핵심) |
| H2 | 패션몰 | hero(룩북) → 신상 → 코디·상세(사이즈표) → 후기(착용샷) → 결제 | 사이즈·색상 옵션, 상세 이미지, 후기 | 옵션 스와치·사이즈표가 전환 핵심 |
| H3 | 화장품·뷰티몰 | hero → 베스트·성분 → 상품 → 후기(사용샷) → 결제 | 성분·용량·가격, 후기 | 성분=detail, 사용샷 후기=reviews |
| H4 | 가구·인테리어몰 | hero(공간 사진) → 카테고리 → 상품(치수) → 시공 사례 → 문의·결제 | 치수·소재·가격, 시공 사진 | 치수표가 필수 데이터. AR·3D는 베타 밖 |
| H5 | 펫용품몰 | hero → 사료·간식·용품 → 후기 → 정기배송 안내 → 결제 | 중량·성분·가격, 정기배송 여부 | 정기배송=구독 안내 섹션 |
| H6 | 건강식품몰 | hero → 효능·성분 → 상품 → 후기 → 결제 | 성분·섭취법·가격 | 효능 문구는 법규 주의 (문구 그대로만) |

### I. 종교·비영리

| # | 카테고리 | 대표 부품 순서 | 필수 데이터 | 구성 메모 |
|---|---|---|---|---|
| I1 | 교회 | hero(예배 시간) → 예배 안내 → 설교 영상 → 행사·모임 → 새신자 안내 → 헌금·문의 | 예배 시간·장소, 설교 링크, 행사 일정 | 예배시간+설교+행사+새신자가 4기둥 (실사례: Harvest·Silverdale·Fellowship 전부 이 구조) |
| I2 | 성당·사찰·종교시설 | hero → 미사·법회 시간 → 공지 → 행사 → 오시는 길 | 시간·공지·주소 | I1에서 헌금·설교만 바뀜. 공통 모듈로 묶음 |
| I3 | 비영리·봉사단체 | hero(미션) → 활동 소개 → 후원 → 모집 → 소식(공지) | 미션·후원 수단·모집 | 후원=결제 대체(계좌 안내). 소식=공지 게시판 |

### J. 부동산·분양

| # | 카테고리 | 대표 부품 순서 | 필수 데이터 | 구성 메모 |
|---|---|---|---|---|
| J1 | 아파트 분양·모델하우스 | hero(조감도) → 사업개요 → 입지 → 평면·평형 → 분양일정·분양가 → 관심고객등록·대표번호 | 사업개요·입지·평면·일정·분양가·대표번호 | 메뉴가 정형화됨 (사업/단지/세대/분양/홍보). 관심고객등록=문의폼, 방문예약=예약. 면책 문구 필수 (실사례: housemap·북오산·e편한세상) |
| J2 | 공인중개·매물 | hero(지역) → 매물 목록(가격·평형) → 상세 → 상담 문의 | 매물·가격·평형·주소·전화 | 매물=offerings 반복형. H1 상품카드와 같은 모듈 |
| J3 | 인테리어·리모델링 | hero(시공 사진) → 시공 사례 → 견적 문의 → 후기 | 시공 사진·평형대·견적 수단 | 비포어/애프터 갤러리가 핵심 |

### K. 의료

| # | 카테고리 | 대표 부품 순서 | 필수 데이터 | 구성 메모 |
|---|---|---|---|---|
| K1 | 치과 | hero → 진료 과목 → 의료진 → 예약 → 오시는 길 | 진료 항목·의료진·예약 수단 | 의료진=디자이너 구조와 동일 (사진·약력·담당) |
| K2 | 한의원·한방 | hero → 진료·프로그램 → 의료진 → 예약 | 진료·의료진·예약 수단 | K1과 공통 모듈 |
| K3 | 피부과·성형외과 | hero(시술 전후) → 시술·가격 → 의료진 → 예약·상담 → 후기 | 시술·가격·의료진 | 시술 전후 사진이 핵심. 가격은 "상담 후 결정" 자리 표시 허용 |
| K4 | 동물병원 | hero → 진료 과목 → 의료진 → 예약·응급 → 오시는 길 | 진료·응급 전화·예약 | 응급 전화 CTA를 최상단 sticky |

### L. 생활서비스

| # | 카테고리 | 대표 부품 순서 | 필수 데이터 | 구성 메모 |
|---|---|---|---|---|
| L1 | 세차·디테일링 | hero → 코스·가격 → 예약 → 오시는 길 | 코스·가격·소요시간·예약 | 코스=매트릭스(차종×코스). 미용실 가격표와 같은 모듈 |
| L2 | 청소·에어컨 | hero → 서비스·가격(평형별) → 예약 → 후기 | 평형·가격·예약 수단 | 평형별 가격표가 핵심 |
| L3 | 이사·용달 | hero → 서비스 종류 → 견적 문의 → 후기 | 출발·도착·날짜·전화 | 견적 문의폼(이사 날짜·구간 필드) |
| L4 | 수리·설비 | hero → 수리 항목·출장비 → 예약 → 후기 | 항목·출장비·전화 | 출장비 명시가 신뢰 핵심 |

## 3. UI/UX 패턴 조사 (50종 횡단)

| 패턴 | 쓰는 곳 | 우리 부품 | 메모 |
|---|---|---|---|
| 히어로 캐러셀 (기획전·조감도·룩북) | H·J1·F | hero 확장 | 1장이 기본, 3장까지. 자동 넘김 + 점 표시. 텍스트는 1줄 CTA |
| 상품·매물 카드 그리드 | H·J2·B2 | offerings 확장 | 이미지+이름+가격+평점+버튼. 2열(모바일) 고정 |
| 가격 매트릭스표 | D1·F1·L1·L2·K3 | price_list(신규) | 등급×항목. 가로 스크롤 허용 |
| 일정·시간표 | F·I·J1(분양일정) | sections 표 | 날짜·시간·장소 3열 |
| 의료진·디자이너·선생님 카드 | D1·K·F | gallery+intro | 사진·이름·담당·경력. 예약 버튼 연결 |
| 설교·영상 목록 | I·G2 | video card | 썸네일+제목+날짜 |
| 분양 탭 (사업/단지/세대/분양/홍보) | J1 | sections 탭형 | 탭은 5개 이하, 각 탭 1화면 |
| 관심고객등록·견적 폼 | J1·J3·L3 | form 확장 | 이름·전화+1개(관심 평형/날짜). 개인정보 동의 필수 |
| sticky 하단바 (전화·예약·문의) | 전부(특히 K4·C5) | cta sticky | 모바일에서만 표시, 2버튼 이하 |
| 후기 (실문구·평점·사진) | H·D·F·L | reviews | 지어내지 않음. 없으면 숨김 (현행) |
| FAQ·공지 | J1·H·I | sections | 5개 이하 아코디언 |
| 오시는 길+지도 링크 | 전부 | around/map | 지도 임베드는 API 키 방식이라 링크가 기본 |

## 4. 디자인 토큰 예시 (카테고리별 분류)

> 우리 컨셉 토큰(palette·font_pair·density·radius·lead)에 얹는다.

| 계열 | 해당 카테고리 | palette 예 | font_pair 예 | density/radius | lead |
|---|---|---|---|---|---|
| 따뜻·식욕 | B·C·H2(식품) | 크림·브라운·토마토 | 고딕+명조 제목 | 보통/둥글게 | offerings |
| 신뢰·의료 | K·J | 화이트·네이비·민트 | 고딕 | 여백 넓게/살짝 둥글게 | intro |
| 고급·뷰티 | D·H3 | 블랙·베이지·골드 | 명조 제목 | 넓게/둥글게 | gallery |
| 활기·교육 | F·L | 화이트·오렌지·그린 | 고딕 굵게 | 보통/둥글게 | offerings |
| 정보·분양 | J1·G5 | 화이트·그레이·블루 | 고딕 | 빽빽/각지게 | sections(일정) |
| 공동체·종교 | I·G4 | 화이트·베이지·브라운 | 명조+고딕 | 넓게/둥글게 | intro |
| 쇼핑·전환 | H | 화이트+강조 1색 | 고딕 굵게 | 보통/살짝 둥글게 | gallery(베스트) |

## 5. 기능 조사 + 공통 DB·공통 모듈 판정

| 기능 | 쓰는 곳 | 공통 DB | 공통 모듈 | 비고 |
|---|---|---|---|---|
| 로그인·회원 | H·J1(홍보자료)·I(교인) | users(있음) | auth 확장 | 베타: 분양 홍보자료·교인 전용만 |
| 게시판(공지·FAQ·홍보자료·주보) | J1·I·H | posts(신규) | board 1종(목록·상세·쓰기) | 분양 홍보자료가 번호·제목·날짜·조회수 표준형 |
| 후기(작성+표시) | H·D·F·L | reviews(신규) | review 1종 | 표시는 실문구만. 작성은 베타 뒤 |
| 예약·방문예약·관심등록 | A·D·K·L·J1 | bookings(신규) | form 3종(예약형·등록형·견적형) | 외부 링크형은 URL만 |
| 장바구니·주문·결제 | H | orders(신규) | **베타 밖** | 온라인 판매는 out_of_beta. 상품 진열까지만 |
| 문의 양식→저장→알림 | 전부 | inquiries(있음) | 공용 (현행) | 30일 보관·카톡 알림 현행 유지 |
| 사진첩·갤러리 | D·F·G1·J3 | photos(있음) | 공용 (현행) | 위치정보 제거 현행 유지 |
| 영상(유튜브·인스타) | I·G | videos(있음) | 공용 (현행) | 설교·시술 영상 동일 부품 |
| 지도·오시는 길 | 전부 | — (외부 링크) | map 링크형 | 임베드는 API 키 방식이라 제외 |
| 문자·이메일 발송 | H·J1 | — | **베타 밖** (알림톡 out_of_beta) | 카톡 "나에게 보내기"만 현행 |
| 통계·조회수 | J1·H | stats(신규) | 카운터 1종 | 조회수는 표시용이라 가볍게 |

## 6. 완성형 홈페이지 추가 검토 (빠진 것 찾기)

| # | 검토 항목 | 판정 |
|---|---|---|
| 1 | 약관·개인정보·사업자 정보 푸터 | 전 카테고리 필수. 템플릿 고정 |
| 2 | 면책 문구 (분양 CG·의료 효능·식품 효능) | J1·K·H6 필수. 카드 `notice` 키로 |
| 3 | 개인정보 동의 체크 (폼마다) | form 3종에 포함. 44px 누름칸 |
| 4 | 빈 상태 처리 (가격 미정·사진 없음·후기 없음) | 자리 표시·숨김·"가격 문의" (현행 유지) |
| 5 | 다국어 | out_of_beta. 안내만 |
| 6 | 검색 (사이트 내) | alternative. 베타는 제외 |
| 7 | 404·로딩·에러 화면 | 렌더러 기본 1종 |
| 8 | SEO 기본 (제목·설명·OG) | 전 페이지 자동. D37 6요소에 포함 |

## 7. 레퍼런스 (확인분)

- 이커머스 구조: https://www.shopify.com/blog/ecommerce-checkout, https://elogic.co/blog/what-are-the-must-have-features-of-ecommerce-website-design, https://litextension.com/blog/ecommerce-website-features, https://www.cminds.com/blog/wordpress/9-essential-ecommerce-website-features-store-must, https://www.zinc.digital/2026/essential-ecommerce-website-features, https://aiadvantageagency.com/ecommerce-website-must-haves, https://www.unfoldmart.com/blogs/the-top-ecommerce-website-features-you-need-for-2026, https://whidegroup.com/blog/most-effective-e-commerce-website-features-to-boost-sales, https://redgobble.com/blog/essential-features-every-ecommerce-website-needs, https://www.shopify.com/blog/ecommerce-checkout-optimization
- 교회 구조: https://harvestraleigh.churchcenter.com/, https://silverdalebc.churchcenter.com/, https://tfcpeople.churchcenter.com/, https://www.rccgfaithchapel.org/, https://albionchristianchurch.com/, https://christchurchcranbrook.org/, http://myfellowship.church/sermonspodcast, http://myfellowship.church/details, https://www.blackhawkcommunitychurch.com/events-sermons, https://myrtlegrove.org/events-home
- 분양 구조: https://housemap.co.kr/, https://apt-modelhouse.co.kr/schedule, https://themodelhouse.co.kr/cs, https://apt-modelhouse.co.kr/brand, https://gc-thehue.com/sale-info/schedule.php, http://www.sasm.or.kr/ad, https://bongdam-xi-raffiner.com/modelhouse, https://osungsm.co.kr/schedule, http://modelhouse-home14.co.kr/free, http://modelhouse00.the-h.kr/p3
- 병원 구조: https://jivakahospital.com/appointment, https://www.royalbahrainhospital.com/doctors, https://laksamgeneralhospital.org/, https://ourclinic.cm/departments, https://www.samsunghospital.com/en/health-promotion-center/appointments.do, https://clinic-website-ui.netlify.app/, https://responsive-hospital-website.vercel.app/, https://www.mchcares.com/departments
- 전편 27건 + §1 트렌드 16건과 합쳐 70건. 카테고리당 20개는 전편 §4 프로토콜로 반복 확충.
