// 청첩장 참석 여부 집계 화면 (fetch 가짜).
import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import RsvpSummary from './RsvpSummary';

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const DATA = {
  total: { replies: 2, people: 2, declined: 1, meal: 2 },
  sides: { 신부측: 2 },
  entries: [
    { id: 2, name: '이선배', side: '신랑측', attend: false, count: 0, meal: false, note: '', contact: '', ts: '' },
    { id: 1, name: '박하객', side: '신부측', attend: true, count: 2, meal: true, note: '축하해요', contact: '', ts: '' },
  ],
};

describe('RsvpSummary', () => {
  it('합계·측별 인원·명단을 보이고 참석만 걸러 본다', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify(DATA), { status: 200 })));
    render(<RsvpSummary roomId="r1" />);
    expect(await screen.findByText('참석 2명 · 식사')).toBeInTheDocument();
    expect(screen.getByText('신부측 2명')).toBeInTheDocument();
    expect(screen.getByText('이선배')).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText('참석만 보기'));
    expect(screen.queryByText('이선배')).toBeNull();
  });

  it('응답이 없으면 안내한다', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ entries: [], total: {}, sides: {} }), { status: 200 })));
    render(<RsvpSummary roomId="r1" />);
    expect(await screen.findByText('공개하면 하객이 보낸 참석 여부가 여기에 모여요.')).toBeInTheDocument();
  });
});
