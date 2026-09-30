// 랜딩 템플릿 → 빌더 시작 테스트 (BUILDER_CONTRACT §6 9번, fetch 가짜).
import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import Landing from '../Landing';

const startRoom = vi.fn();

vi.mock('../api', () => ({
  visitorId: () => 'v-test',
  track: vi.fn(),
  startRoom: (...args: unknown[]) => startRoom(...args),
}));
vi.mock('../auth', () => ({
  me: () => Promise.resolve(null),
  startLogin: vi.fn(),
  logout: vi.fn(),
}));
vi.mock('../voice', async (orig) => {
  const actual = (await orig()) as object;
  return {
    ...actual,
    voiceSupported: false,
    useVoiceInput: () => ({ state: 'idle', seconds: 0, status: null, numCheck: false, toggle: () => {} }),
  };
});

let navTo = '';

beforeEach(() => {
  localStorage.clear();
  navTo = '';
  startRoom.mockReset();
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => ({ ok: true, status: 200, json: async () => ({}) }) as Response),
  );
  // location.href 쓰기를 잡아 이동 주소를 확인한다.
  Object.defineProperty(window, 'location', {
    configurable: true,
    value: {
      get href() {
        return navTo || 'http://localhost/';
      },
      set href(v: string) {
        navTo = v;
      },
      get search() {
        return '';
      },
      get pathname() {
        return '/';
      },
    },
  });
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  Reflect.deleteProperty(window, 'location');
});

function stubStart(data: unknown, ok = true) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) => {
      if (String(url) === '/api/start') {
        return { ok, status: ok ? 200 : 500, json: async () => data } as Response;
      }
      return { ok: true, status: 200, json: async () => ({}) } as Response;
    }),
  );
}

describe('랜딩 템플릿 → 빌더', () => {
  it('템플릿 누름 → /api/start → member 저장 뒤 builder_url 이동', async () => {
    stubStart({ room_id: 'r1', member_id: 'm9', builder_url: '/start?room=r1' });
    render(<Landing />);
    const card = screen.getByText('한결 밥상').closest('button');
    expect(card).not.toBeNull();
    fireEvent.click(card!);
    await waitFor(() => expect(navTo).toBe('/start?room=r1'));
    expect(localStorage.getItem('agt001_member_id')).toBe('m9');
    const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
    expect(fetchMock.mock.calls.some((c) => String(c[0]) === '/api/start')).toBe(true);
    // 채팅방(자유 입력)으로는 가지 않는다.
    expect(startRoom).not.toHaveBeenCalled();
  });

  it('실패하면 예시 문장을 채운다', async () => {
    stubStart({}, false);
    render(<Landing />);
    const card = screen.getByText('한결 밥상').closest('button');
    fireEvent.click(card!);
    const input = (await screen.findByLabelText('만들고 싶은 사이트 설명')) as HTMLTextAreaElement;
    await waitFor(() => expect(input.value).toContain('한식 식당을 운영해요'));
    expect(navTo).toBe('');
  });

  it('자유 입력은 그대로 채팅으로 시작한다', async () => {
    startRoom.mockResolvedValue(undefined);
    stubStart({ room_id: 'r1', member_id: 'm9', builder_url: '/start?room=r1' });
    render(<Landing />);
    const input = (await screen.findByLabelText('만들고 싶은 사이트 설명')) as HTMLTextAreaElement;
    fireEvent.change(input, { target: { value: '우리 가게 사이트 필요해요' } });
    fireEvent.click(screen.getByRole('button', { name: '시작하기' }));
    await waitFor(() => expect(startRoom).toHaveBeenCalled());
  });
});
