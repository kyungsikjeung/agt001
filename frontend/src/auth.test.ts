// auth.ts 테스트 (fetch 가짜).
import { afterEach, describe, expect, it, vi } from 'vitest';
import { claim, logout, me, startLogin } from './auth';

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

function mockFetch(status: number, body: unknown = {}) {
  return vi.fn(async () => ({ ok: status >= 200 && status < 300, status, json: async () => body }) as Response);
}

describe('auth', () => {
  it('401이면 로그인 안 함(null)으로 처리한다', async () => {
    vi.stubGlobal('fetch', mockFetch(401));
    expect(await me()).toBeNull();
  });

  it('404(서버 미배포)이면 로그인 안 함(null)으로 처리한다', async () => {
    vi.stubGlobal('fetch', mockFetch(404));
    expect(await me()).toBeNull();
  });

  it('200이면 사용자를 돌려준다', async () => {
    const user = { id: 'u1', nickname: '사장님', provider: 'kakao' };
    vi.stubGlobal('fetch', mockFetch(200, { user }));
    expect(await me()).toEqual(user);
  });

  it('startLogin은 제공자 로그인 주소로 이동한다 (fetch 아님)', () => {
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
    const loc = { href: 'http://localhost/' };
    vi.stubGlobal('location', loc);
    startLogin('kakao', '/projects');
    expect(loc.href).toBe('/auth/kakao/start?next=%2Fprojects');
    startLogin('google', '/');
    expect(loc.href).toBe('/auth/google/start?next=%2F');
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('claim은 401이면 0, 성공이면 claimed 수를 돌려준다', async () => {
    vi.stubGlobal('fetch', mockFetch(401));
    expect(await claim(['r1'])).toBe(0);
    vi.stubGlobal('fetch', mockFetch(200, { claimed: 2 }));
    expect(await claim(['r1', 'r2'])).toBe(2);
    expect(await claim([])).toBe(0);
  });

  it('logout은 POST /api/logout을 같은 출처로 보낸다', async () => {
    const fetchMock = mockFetch(204);
    vi.stubGlobal('fetch', fetchMock);
    await logout();
    expect(fetchMock).toHaveBeenCalledWith('/api/logout', { method: 'POST', credentials: 'same-origin' });
  });
});
