// 주변 안내 고치기 + 공용 부품(단위 칸·보기 카드·줄 목록·가격 칸) (10/4 대표 요청).
import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { useState } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import NearbyEditor from './NearbyEditor';
import PriceField from './fields/PriceField';
import { parsePrice } from './fields/UnitValueField';
import type { RoomCard } from './cardApi';

const CARD: RoomCard = {
  title: '달빛 펜션', industry: '펜션', fields: [], photos: [], choice: 'v2', published: null, site_url: null, can_edit: true,
  nearby: { style: 'stack', items: [{ name: '해수욕장', unit: 'walk', value: 3, sub: '도보 3분', photo: '' }] },
};

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function stubSave() {
  const bodies: unknown[] = [];
  vi.stubGlobal('fetch', vi.fn(async (_url: string, init?: RequestInit) => {
    bodies.push(JSON.parse(String(init?.body)));
    return { ok: true, status: 200, json: async () => CARD } as Response;
  }));
  return bodies;
}

describe('NearbyEditor', () => {
  it('저장된 줄을 보이고, 줄을 더해 대제목·소제목(차로 10분)·배치를 저장한다', async () => {
    const bodies = stubSave();
    render(<NearbyEditor roomId="r1" card={CARD} onSaved={() => {}} />);
    expect(screen.getByDisplayValue('해수욕장')).toBeInTheDocument();
    expect(screen.getByText('보이는 글: 도보 3분')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '+ 장소 더하기 (1/8)' }));
    const row = screen.getByRole('listitem', { name: '2. 새 장소' });
    fireEvent.change(within(row).getByPlaceholderText('예: ○○해수욕장'), { target: { value: '전통시장' } });
    fireEvent.click(within(row).getByRole('button', { name: '차로' }));
    fireEvent.change(within(row).getByLabelText('소제목 (거리) (분)'), { target: { value: '10분' } });
    expect(within(row).getByText('보이는 글: 차로 10분')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /사진 위 배지/ }));
    fireEvent.click(screen.getByRole('button', { name: '주변 안내 저장' }));
    await waitFor(() => expect(bodies).toHaveLength(1));
    expect(bodies[0]).toEqual({ fields: {}, nearby: { style: 'badge', items: [
      { name: '해수욕장', unit: 'walk', value: 3 },
      { name: '전통시장', unit: 'car', value: 10 },
    ] } });
  });

  it('줄 옮기기·지우기, 이름을 바꾸면 prev_name을 같이 보낸다(사진이 따라가게)', async () => {
    const bodies = stubSave();
    render(<NearbyEditor roomId="r1" card={CARD} onSaved={() => {}} />);
    fireEvent.change(screen.getByDisplayValue('해수욕장'), { target: { value: '○○해변' } });
    fireEvent.click(screen.getByRole('button', { name: '+ 장소 더하기 (1/8)' }));
    fireEvent.click(screen.getByRole('button', { name: '새 장소 위로' }));
    expect(screen.getAllByRole('listitem')[0]).toHaveAccessibleName('1. 새 장소');
    fireEvent.click(screen.getByRole('button', { name: '새 장소 지우기' }));
    fireEvent.click(screen.getByRole('button', { name: '주변 안내 저장' }));
    await waitFor(() => expect(bodies).toHaveLength(1));
    expect(bodies[0]).toMatchObject({ nearby: { items: [{ name: '○○해변', unit: 'walk', value: 3, prev_name: '해수욕장' }] } });
  });

  it('거리(km)는 소수, 1 미만은 m로 보인다', () => {
    stubSave();
    render(<NearbyEditor roomId="r1" card={CARD} onSaved={() => {}} />);
    fireEvent.click(screen.getByRole('button', { name: '거리' }));
    fireEvent.change(screen.getByLabelText('소제목 (거리) (km)'), { target: { value: '0.35km' } });
    expect(screen.getByDisplayValue('0.35')).toBeInTheDocument();
    expect(screen.getByText('보이는 글: 350m')).toBeInTheDocument();
  });
});

function PriceHost({ start }: { start: string }) {
  const [p, setP] = useState(start);
  return (
    <>
      <PriceField price={p} onChange={setP} />
      <output data-testid="price">{p}</output>
    </>
  );
}

describe('PriceField (메뉴 가격, 같은 단위 칸)', () => {
  it('숫자만 누르면 "4,500원" 글로 저장', () => {
    render(<PriceHost start="" />);
    fireEvent.change(screen.getByLabelText('가격 (원)'), { target: { value: '4500' } });
    expect(screen.getByTestId('price')).toHaveTextContent('4,500원');
  });

  it('예전 글을 읽는다: "5,000원"은 금액, "시가"는 직접 쓰기', () => {
    expect(parsePrice('5,000원')).toEqual({ unit: 'won', value: '5000' });
    expect(parsePrice('시가')).toEqual({ unit: 'text', value: '시가' });
    render(<PriceHost start="시가" />);
    expect(screen.getByRole('button', { name: '직접 쓰기' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByDisplayValue('시가')).toBeInTheDocument();
  });
});
