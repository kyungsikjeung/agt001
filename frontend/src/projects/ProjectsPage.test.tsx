// ProjectsPage 화면 테스트 (fetch·localStorage 가짜).
import '@testing-library/jest-dom/vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import ProjectsPage from './ProjectsPage';

const PROJECT = {
  room_id: 'r1',
  title: '우리 가게 사이트',
  industry: '카페',
  state: 'GENERATING',
  state_label: '제작 중',
  created_at: '2026-09-20T00:00:00Z',
  updated_at: new Date(Date.now() - 3 * 3600 * 1000).toISOString(),
  last_message: '시안 확인했어요',
  members: 2,
  deploy_url: 'https://example.com/s1',
  design_url: 'https://example.com/d1',
};

function mockFetch(routes: Record<string, { status: number; body?: unknown }>, calls: string[]) {
  return vi.fn(async (url: string) => {
    calls.push(typeof url === 'string' ? url : String(url));
    const path = (typeof url === 'string' ? url : String(url)).split('?')[0];
    const route = routes[path] ?? { status: 404 };
    return {
      ok: route.status >= 200 && route.status < 300,
      status: route.status,
      json: async () => route.body ?? {},
    } as Response;
  });
}

beforeEach(() => {
  localStorage.clear();
  localStorage.setItem('agt001_rooms', JSON.stringify(['r1']));
  localStorage.setItem('agt001_member_id', 'm1');
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('ProjectsPage', () => {
  it('카드 목록을 보여준다 (제목·배지·마지막 메시지·상대 시간·참여자·버튼)', async () => {
    const calls: string[] = [];
    vi.stubGlobal(
      'fetch',
      mockFetch({ '/api/me': { status: 401 }, '/api/projects/summary': { status: 200, body: { projects: [PROJECT] } } }, calls),
    );
    render(<ProjectsPage />);
    expect(await screen.findByText('우리 가게 사이트')).toBeInTheDocument();
    expect(screen.getByText('제작 중')).toBeInTheDocument();
    expect(screen.getByText('시안 확인했어요')).toBeInTheDocument();
    expect(screen.getByText('3시간 전')).toBeInTheDocument();
    expect(screen.getByText('참여자 2명')).toBeInTheDocument();
    const resume = screen.getByRole('link', { name: '이어서 하기' });
    expect(resume.getAttribute('href')).toBe('/room.html?room=r1');
    const site = screen.getByRole('link', { name: '사이트 보기' });
    expect(site.getAttribute('href')).toBe('https://example.com/s1');
    expect(site.getAttribute('target')).toBe('_blank');
    expect(screen.getByRole('link', { name: '시안 보기' })).toBeInTheDocument();
  });

  it('방이 없으면 빈 상태를 보여준다', async () => {
    localStorage.setItem('agt001_rooms', JSON.stringify([]));
    const calls: string[] = [];
    vi.stubGlobal('fetch', mockFetch({ '/api/me': { status: 401 } }, calls));
    render(<ProjectsPage />);
    expect(await screen.findByText('아직 만든 사이트가 없어요')).toBeInTheDocument();
    const link = screen.getByRole('link', { name: '새로 만들기' });
    expect(link.getAttribute('href')).toBe('/');
    // 방이 없으면 summary를 호출하지 않는다
    await waitFor(() => expect(screen.getByText('아직 만든 사이트가 없어요')).toBeInTheDocument());
    expect(calls.some((c) => c.startsWith('/api/projects/summary'))).toBe(false);
  });

  it('로그인하지 않았으면 기기 안내와 로그인 버튼을 보여준다', async () => {
    const calls: string[] = [];
    vi.stubGlobal(
      'fetch',
      mockFetch({ '/api/me': { status: 401 }, '/api/projects/summary': { status: 200, body: { projects: [] } } }, calls),
    );
    render(<ProjectsPage />);
    expect(await screen.findByText(/이 기기에서 만든 것만 보여요/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '카카오로 계속하기' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Google로 계속하기' })).not.toBeInTheDocument(); // 테스트 모드라 숨김
  });

  it('로그인했으면 안내를 숨기고 claim을 한 번 보낸 뒤 목록을 보여준다', async () => {
    const calls: string[] = [];
    const fetchMock = mockFetch(
      {
        '/api/me': { status: 200, body: { user: { id: 'u1', nickname: '사장님', provider: 'kakao' } } },
        '/api/me/claim': { status: 200, body: { claimed: 1 } },
        '/api/projects/summary': { status: 200, body: { projects: [PROJECT] } },
      },
      calls,
    );
    vi.stubGlobal('fetch', fetchMock);
    render(<ProjectsPage />);
    expect(await screen.findByText('우리 가게 사이트')).toBeInTheDocument();
    expect(screen.queryByText(/이 기기에서 만든 것만 보여요/)).not.toBeInTheDocument();
    expect(screen.getByText('사장님')).toBeInTheDocument();
    const claimCalls = fetchMock.mock.calls.filter(([url]) => String(url) === '/api/me/claim');
    expect(claimCalls).toHaveLength(1);
  });

  it('저장소 접근이 막혀도 화면이 깨지지 않고 빈 상태를 보여준다', async () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('denied');
    });
    const calls: string[] = [];
    vi.stubGlobal('fetch', mockFetch({ '/api/me': { status: 401 } }, calls));
    render(<ProjectsPage />);
    expect(await screen.findByText('아직 만든 사이트가 없어요')).toBeInTheDocument();
  });
});
