// 청첩장 방명록 관리: 최신순 목록, 지우기 (fetch 가짜).
import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import GuestbookAdmin from './GuestbookAdmin';

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe('GuestbookAdmin', () => {
  it('글을 보이고 지우면 목록에서 뺀다', async () => {
    const calls: string[] = [];
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string, init?: RequestInit) => {
        calls.push(`${init?.method ?? 'GET'} ${url}`);
        if (init?.method === 'DELETE') return new Response(null, { status: 204 });
        return new Response(
          JSON.stringify({ entries: [{ id: 7, name: '박하객', message: '축하해요', ts: '2026-10-02T03:00:00Z' }] }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        );
      }),
    );
    render(<GuestbookAdmin roomId="r1" />);
    expect(await screen.findByText('축하해요')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '박하객님 글 지우기' }));
    await waitFor(() => expect(screen.queryByText('축하해요')).toBeNull());
    expect(calls).toContain('DELETE /api/rooms/r1/guestbook/7');
  });

  it('글이 없으면 안내한다', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ entries: [] }), { status: 200 })));
    render(<GuestbookAdmin roomId="r1" />);
    expect(await screen.findByText('아직 남긴 글이 없어요.')).toBeInTheDocument();
  });
});
