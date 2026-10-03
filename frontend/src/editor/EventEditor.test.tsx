// 청첩장 양가 연락처·계좌 고치기 (EVENT_INVITE_PLAN, fetch 가짜).
import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import EventEditor from './EventEditor';
import type { RoomCard } from './cardApi';

const CARD: RoomCard = {
  title: '김민준 · 이서연',
  industry: '초대·기념',
  fields: [],
  photos: [],
  choice: 'v1',
  published: null,
  site_url: null,
  can_edit: true,
  event: {
    family: [
      { side: '신랑측', people: [{ role: '신랑', name: '김민준' }] },
      { side: '신부측', people: [{ role: '신부', name: '이서연' }] },
    ],
    gift: [{ side: '신랑측', accounts: [{ role: '신랑', holder: '김민준', bank: '예시은행', number: '000-0000-0000' }] }],
    saved: { family: false, gift: false },
  },
};

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function stubPut(status: number, body: unknown) {
  const calls: { url: string; body: Record<string, unknown> }[] = [];
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      calls.push({ url, body: JSON.parse(String(init?.body ?? '{}')) });
      return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
    }),
  );
  return calls;
}

describe('EventEditor', () => {
  it('번호를 넣고 저장하면 양가 연락처를 보낸다', async () => {
    const calls = stubPut(200, CARD);
    const saved = vi.fn();
    render(<EventEditor roomId="r1" card={CARD} kind="family" onSaved={saved} />);
    const phones = screen.getAllByPlaceholderText('010-0000-0000');
    fireEvent.change(phones[0], { target: { value: '010-1234-5678' } });
    fireEvent.click(screen.getAllByRole('button', { name: '+ 사람 더하기' })[0]);
    fireEvent.click(screen.getByRole('button', { name: '저장' }));
    expect(await screen.findByText('저장했어요.')).toBeInTheDocument();
    const family = (calls[0].body.event as { family: { side: string; people: Record<string, string>[] }[] }).family;
    expect(family[0]).toMatchObject({ side: '신랑측', people: [{ role: '신랑', name: '김민준', phone: '010-1234-5678' }, { name: '' }] });
    expect(saved).toHaveBeenCalled();
  });

  it('서버가 틀린 곳을 알려 주면 그 말을 보인다', async () => {
    stubPut(400, { detail: '김민준 전화번호: 전화번호 자리수가 맞지 않아요' });
    render(<EventEditor roomId="r1" card={CARD} kind="family" onSaved={() => {}} />);
    fireEvent.click(screen.getByRole('button', { name: '저장' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('김민준 전화번호');
  });

  it('아직 넣지 않은 계좌는 예시 은행·번호를 비워 보인다', () => {
    render(<EventEditor roomId="r1" card={CARD} kind="gift" onSaved={() => {}} />);
    expect(screen.getByDisplayValue('김민준')).toBeInTheDocument();
    expect(screen.queryByDisplayValue('예시은행')).toBeNull();
    expect(screen.getByPlaceholderText('123456-01-234567')).toHaveValue('');
  });
});
