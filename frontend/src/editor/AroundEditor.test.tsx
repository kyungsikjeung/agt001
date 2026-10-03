import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import AroundEditor, { aroundNote } from './AroundEditor';
import type { RoomCard } from './cardApi';

function card(around?: RoomCard['around']): RoomCard {
  return { title: 't', industry: 'pension', fields: [], photos: [], choice: 'v1', can_edit: true, around } as unknown as RoomCard;
}

beforeEach(() => {
  localStorage.setItem('agt001_member_id', 'm1');
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe('aroundNote (서버 around_note와 같은 규칙)', () => {
  it('단위를 붙인다', () => {
    expect(aroundNote('walk', '3')).toBe('도보 3분');
    expect(aroundNote('car', '10')).toBe('차로 10분');
    expect(aroundNote('distance', '1.2')).toBe('1.2km');
    expect(aroundNote('distance', '800m')).toBe('800m');
    expect(aroundNote('text', '버스 7번 종점')).toBe('버스 7번 종점');
    expect(aroundNote('walk', ' ')).toBe('');
  });
});

describe('AroundEditor', () => {
  it('줄을 채우고 크게 보일 것을 골라 저장한다', async () => {
    const put = vi.fn(async (_url: string, init: RequestInit) => {
      const body = JSON.parse(String(init.body));
      return new Response(JSON.stringify(card(body.around)), { status: 200 });
    });
    vi.stubGlobal('fetch', put);
    const onSaved = vi.fn();
    render(<AroundEditor roomId="r1" card={card()} onSaved={onSaved} />);
    fireEvent.change(screen.getByPlaceholderText('예: 홍대입구역 3번 출구'), { target: { value: '강릉역' } });
    fireEvent.click(screen.getByRole('button', { name: '차로' }));
    fireEvent.change(screen.getByPlaceholderText('10'), { target: { value: '15' } });
    expect(screen.getByText('강릉역 · 차로 15분')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: '거리·시간' }));
    fireEvent.click(screen.getByRole('button', { name: '+ 해수욕장' }));
    fireEvent.click(screen.getByRole('button', { name: '주변 안내 저장' }));
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    const body = JSON.parse(String(put.mock.calls[0][1].body));
    expect(body.around).toEqual({
      title: 'distance',
      items: [
        { name: '강릉역', how: 'car', value: '15' },
        { name: '해수욕장', how: 'walk', value: '' },
      ],
    });
    expect(screen.getByRole('status').textContent).toBe('저장했어요.');
  });

  it('자주 넣는 장소를 누르면 빈 첫 줄에 채운다', () => {
    render(<AroundEditor roomId="r1" card={card()} onSaved={() => {}} />);
    fireEvent.click(screen.getByRole('button', { name: '+ 주차장' }));
    expect((screen.getByPlaceholderText('예: 홍대입구역 3번 출구') as HTMLInputElement).value).toBe('주차장');
    expect(screen.getAllByRole('group', { name: /번째 줄/ })).toHaveLength(1);
  });

  it('저장된 값을 읽어 보인다', () => {
    render(<AroundEditor roomId="r1" card={card({ title: 'place', items: [{ name: '해변', how: 'distance', value: '1.2' }] })} onSaved={() => {}} />);
    expect(screen.getByText('해변 · 1.2km')).toBeTruthy();
    expect(screen.getByRole('button', { name: '장소 이름' }).getAttribute('aria-pressed')).toBe('true');
  });

  it('서버가 400으로 알려 준 틀린 곳을 보여 준다', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ detail: '장소 이름은 20자까지예요: x' }), { status: 400 })));
    render(<AroundEditor roomId="r1" card={card()} onSaved={() => {}} />);
    fireEvent.change(screen.getByPlaceholderText('예: 홍대입구역 3번 출구'), { target: { value: 'x' } });
    fireEvent.click(screen.getByRole('button', { name: '주변 안내 저장' }));
    await waitFor(() => expect(screen.getByRole('alert').textContent).toBe('장소 이름은 20자까지예요: x'));
  });
});
