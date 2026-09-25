// 목업 명세 2개 (서버 연결 없음). 전부 가짜 값 + "예시" 표시.
// D23: 전화는 자리 표시로 비워 둠. D26: 예시 가게의 가짜 사실은 넣지 않음.
import type { DesignSpec } from './types';

export const MOCK_PENSION: DesignSpec = {
  version: 4,
  based_on_prd_version: 2,
  shopName: '예시 솔숲 펜션',
  tokens: {
    palette: 'forest',
    font_pair: 'serif-warm',
    density: 'comfortable',
    radius: 'soft',
    image_style: 'full-bleed',
  },
  sections: [
    {
      id: 'hero',
      type: 'hero',
      variant: 'photo-overlay',
      content: {
        title: '예시 솔숲 펜션',
        subtitle: '숲속에서 쉬어가는 예시 숙소입니다',
        image: '',
      },
    },
    {
      id: 'intro',
      type: 'intro',
      variant: 'short',
      content: {
        body: '예시 문구입니다. 실제 소개 글로 바꿔주세요. 조용한 숲속에 있는 작은 펜션입니다.',
      },
    },
    {
      id: 'rooms',
      type: 'offerings',
      variant: 'photo-grid',
      content: {
        label: '객실',
        items: [
          { name: '예시 숲방', desc: '2인 기준 예시 객실', price: '' },
          { name: '예시 가족방', desc: '4인 기준 예시 객실', price: '예시 010-0000-0001로 문의' },
        ],
      },
    },
    {
      id: 'around',
      type: 'around',
      variant: 'transit',
      content: {
        address: '',
        items: [{ name: '예시 계곡', note: '차로 5분 (예시)' }],
      },
    },
    {
      id: 'contact',
      type: 'contact',
      variant: 'call-first',
      content: {
        phone: '',
        hours: '입실 오후 3시 · 퇴실 오전 11시 (예시)',
        address: '',
      },
    },
    {
      id: 'booking',
      type: 'cta',
      variant: 'call-sms',
      content: { phone: '' },
    },
    {
      id: 'reviews',
      type: 'reviews',
      variant: 'slot-only',
      content: {},
    },
  ],
  // 사장님이 직접 정한 값 (잠금 예시).
  locked: ['hero.title', 'contact.hours'],
};

export const MOCK_CAFE: DesignSpec = {
  version: 2,
  based_on_prd_version: 2,
  shopName: '예시 골목 카페',
  tokens: {
    palette: 'coffee',
    font_pair: 'sans-clean',
    density: 'comfortable',
    radius: 'soft',
    image_style: 'card',
  },
  sections: [
    {
      id: 'hero',
      type: 'hero',
      variant: 'photo-side',
      content: {
        title: '예시 골목 카페',
        subtitle: '동네 사랑방 같은 예시 카페입니다',
        image: '',
      },
    },
    {
      id: 'intro',
      type: 'intro',
      variant: 'owner',
      content: {
        body: '예시 인사말입니다. 편하게 쉬다 가세요.',
        owner_name: '예시 사장님',
      },
    },
    {
      id: 'menu',
      type: 'offerings',
      variant: 'list-price',
      content: {
        label: '메뉴',
        items: [
          { name: '예시 아메리카노', desc: '고소한 예시 원두', price: '예시 4,500원' },
          { name: '예시 라떼', desc: '부드러운 예시 라떼', price: '' },
        ],
      },
    },
    {
      id: 'contact',
      type: 'contact',
      variant: 'chat-first',
      content: {
        phone: '',
        hours: '',
        channel_url: 'https://example.com/channel',
      },
    },
    {
      id: 'booking',
      type: 'cta',
      variant: 'call-sms',
      content: { phone: '' },
    },
    {
      id: 'reviews',
      type: 'reviews',
      variant: 'slot-only',
      content: {},
    },
  ],
  locked: ['hero.title'],
};

export const MOCK_SPECS: Array<{ id: string; label: string; spec: DesignSpec }> = [
  { id: 'pension', label: '펜션 예시', spec: MOCK_PENSION },
  { id: 'cafe', label: '카페 예시', spec: MOCK_CAFE },
];
