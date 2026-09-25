// 랜딩의 업종별 템플릿 (DECISIONS.md D15). 카탈로그는 정적 데이터로 둔다.
// 미리보기 색은 DESIGN_PIPELINE_PLAN.md의 디자인 명세 tokens.palette와 같은 형식이다.
// 가상 가게이므로 화면에는 항상 "예시"로 표시한다.

export type Template = {
  id: string;
  name: string;
  shop: string;
  tagline: string;
  starter: string;
  palette: { primary: string; accent: string; ground: string; ink: string };
  sections: string[];
};

export const TEMPLATES: Template[] = [
  {
    id: 'pension',
    name: '펜션·숙박',
    shop: '바다정원 펜션',
    tagline: '객실, 바비큐장, 주변 맛집과 여행지',
    starter:
      '바닷가 근처 작은 펜션이에요. 객실 3개와 바비큐장을 소개하고, 주변 맛집과 여행지도 안내하고 싶어요. 예약 문의는 전화로 받아요.',
    palette: { primary: '#2f5d62', accent: '#e8b86d', ground: '#f6f2ea', ink: '#1f2a2c' },
    sections: ['객실', '바비큐', '주변 안내'],
  },
  {
    id: 'cafe',
    name: '카페',
    shop: '모퉁이 커피',
    tagline: '대표 메뉴, 영업시간, 오시는 길',
    starter: '동네 작은 카페예요. 대표 메뉴와 영업시간, 오시는 길을 보여 주는 사이트가 필요해요.',
    palette: { primary: '#6b4f3a', accent: '#d9a441', ground: '#fbf7f1', ink: '#2b211a' },
    sections: ['메뉴', '영업시간', '오시는 길'],
  },
  {
    id: 'restaurant',
    name: '식당',
    shop: '한결 밥상',
    tagline: '메뉴와 가격, 단체 예약, 주차 안내',
    starter: '한식 식당을 운영해요. 메뉴와 가격, 단체 예약 안내, 주차 정보를 넣고 싶어요.',
    palette: { primary: '#9a3b2f', accent: '#f0c05a', ground: '#fdf8f3', ink: '#2a1a16' },
    sections: ['메뉴', '단체 예약', '주차'],
  },
  {
    id: 'salon',
    name: '미용실',
    shop: '결 헤어',
    tagline: '시술 메뉴, 디자이너 소개, 예약 방법',
    starter: '미용실이에요. 시술 메뉴와 가격, 디자이너 소개, 예약 방법을 보여 주고 싶어요.',
    palette: { primary: '#3d3a4b', accent: '#c9a7b4', ground: '#f7f5f6', ink: '#1e1c24' },
    sections: ['시술', '디자이너', '예약'],
  },
  {
    id: 'workshop',
    name: '공방',
    shop: '흙과 손 도예공방',
    tagline: '원데이 클래스, 작품 사진, 수업 신청',
    starter: '도자기 공방이에요. 원데이 클래스 일정과 작품 사진을 보여 주고, 수업 신청 문의를 받고 싶어요.',
    palette: { primary: '#7a5c3e', accent: '#8fae8b', ground: '#f5f1ea', ink: '#2a241d' },
    sections: ['클래스', '작품', '신청'],
  },
  {
    id: 'academy',
    name: '학원',
    shop: '새싹 영어교실',
    tagline: '반 구성, 시간표, 상담 신청',
    starter: '초등 영어 학원이에요. 반 구성과 수업 시간표, 상담 신청 방법을 안내하고 싶어요.',
    palette: { primary: '#1f5fa8', accent: '#f2b632', ground: '#f4f7fb', ink: '#14233a' },
    sections: ['반 구성', '시간표', '상담'],
  },
];

// 입력창 안내 문구. 몇 초마다 바뀌며 무엇을 적으면 되는지 보여준다.
export const PLACEHOLDERS = TEMPLATES.map((t) => t.starter);
