// 오시는 길 위치 검색 테스트 (BUILDER_FIX_1003_CONTRACT J3).
import '@testing-library/jest-dom/vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import SectionPanel from './SectionPanel';
import type { RoomCard } from './cardApi';

const CARD: RoomCard = {
  title: '우리 가게',
  industry: '카페',
  fields: [
    { key: 'shop_name', label: '가게 이름', value: '우리 가게', status: 'filled', fact: false, placeholder: false },
    { key: 'location', label: '위치', value: '앞골목', status: 'filled', fact: true, placeholder: false },
    { key: 'hours', label: '영업시간', value: '매일 09:00~18:00', status: 'filled', fact: true, placeholder: false },
    { key: 'phone', label: '전화번호', value: '010-1234-5678', status: 'filled', fact: true, placeholder: false },
  ],
  photos: [],
  choice: 'v3',
  published: null,
  site_url: null,
  can_edit: true,
};

const SECTIONS = [
  { id: 'hero', label: '첫 화면', bind: 'hero', locked: true, hidden: false },
  { id: 'visit', label: '오시는 길', bind: 'location', locked: false, hidden: false },
  { id: 'wedding', label: '날짜와 장소', bind: 'event', locked: false, hidden: false },
];

function renderPanel(selectedId: string) {
  return render(
    <SectionPanel
      roomId="r1"
      card={CARD}
      sections={SECTIONS}
      addable={[]}
      added={[]}
      baseItems={[]}
      variant="v3"
      selectedId={selectedId}
      clickedText=""
      onSelect={() => {}}
      onSaved={() => {}}
    />,
  );
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe('SectionPanel 오시는 길 위치 검색 (J3)', () => {
  it('오시는 길 구역을 고르면 주소 검색 버튼이 보인다', () => {
    renderPanel('visit');
    expect(screen.getByRole('button', { name: '주소 검색' })).toBeInTheDocument();
  });

  it('날짜와 장소 구역(초대 event)을 고르면 주소 검색 버튼이 보인다', () => {
    renderPanel('wedding');
    expect(screen.getByRole('button', { name: '주소 검색' })).toBeInTheDocument();
  });

  it('첫 화면 구역에는 주소 검색 버튼이 없다', () => {
    renderPanel('hero');
    expect(screen.queryByRole('button', { name: '주소 검색' })).toBeNull();
  });

  it('위치 글자 칸은 그대로 둔다 (직접 고치기)', () => {
    renderPanel('visit');
    expect(screen.getByDisplayValue('앞골목')).toBeInTheDocument();
  });
});

describe('SectionPanel 칸 부품 (10/4)', () => {
  it('오시는 길의 전화번호는 하이픈 자동 칸', () => {
    renderPanel('visit');
    const phone = screen.getByLabelText('전화번호');
    expect(phone).toHaveAttribute('type', 'tel');
  });

  it('펜션(체크인·아웃 시간)이면 시간 칩, 다른 업종 영업시간은 글 칸', () => {
    renderPanel('visit');
    expect(screen.getByDisplayValue('매일 09:00~18:00')).toBeInTheDocument();
    cleanup();
    const pension = { ...CARD, fields: CARD.fields.map((f) => (f.key === 'hours' ? { ...f, label: '체크인·아웃 시간', value: '15시 / 11시' } : f)) };
    render(
      <SectionPanel roomId="r1" card={pension} sections={SECTIONS} addable={[]} added={[]} baseItems={[]} variant="v3"
        selectedId="visit" clickedText="" onSelect={() => {}} onSaved={() => {}} />,
    );
    expect(screen.getByRole('group', { name: '체크인' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '15:00' })).toHaveAttribute('aria-pressed', 'true');
  });
});
