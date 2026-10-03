// 사진 시트 테스트 (PHOTO_EDIT_CONTRACT §5, fetch 가짜).
import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import PhotoSheet from './PhotoSheet';

const PICK = { section: 'hero', src: 'http://x/a.jpg', index: 0 };

const AI_TARGET = {
  target: 'hero',
  kind: 'ai',
  current_url: 'http://x/before.jpg',
  actions: ['brighter', 'warmer', 'sharper', 'square', 'wide'],
  ai_allowed: true,
  left_today: 9,
  cooldown_sec: 0,
};

const OWNER_TARGET = {
  target: 'hero',
  kind: 'owner',
  current_url: 'http://x/owner.jpg',
  actions: ['brighter', 'warmer', 'sharper', 'square', 'wide'],
  ai_allowed: false,
  left_today: 10,
  cooldown_sec: 0,
};

const CANDIDATE = {
  candidate_id: 'c1',
  before_url: 'http://x/before.jpg',
  after_url: 'http://x/after.jpg',
};

function stubFetch(handler: (url: string, init?: RequestInit) => Promise<unknown>) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => handler(url, init)),
  );
}

function okJson(data: unknown) {
  return { ok: true, status: 200, json: async () => data } as Response;
}

function errJson(status: number, detail: string) {
  return { ok: false, status, json: async () => ({ detail }) } as Response;
}

function callsTo(part: string, method?: string) {
  const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
  return fetchMock.mock.calls.filter(
    (c) => String(c[0]).includes(part) && (!method || (c[1] as RequestInit | undefined)?.method === method),
  );
}

beforeEach(() => {
  localStorage.clear();
  localStorage.setItem('agt001_member_id', 'm1');
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('PhotoSheet', () => {
  it('보정 → 전·후 → 쓰기 → onApplied → 되돌리기', async () => {
    const onApplied = vi.fn();
    stubFetch(async (url, init) => {
      if (url.includes('/photo-edit/target')) return okJson(AI_TARGET);
      if (url.includes('/photo-edit/preview')) return okJson(CANDIDATE);
      if (url.includes('/photo-edit/apply')) return okJson({ ok: true, url: 'http://x/after.jpg', undo: true });
      if (url.includes('/photo-edit/undo')) return okJson({ ok: true, url: 'http://x/before.jpg' });
      throw new Error(`몰라요: ${url} ${init?.method}`);
    });
    render(<PhotoSheet roomId="r1" pick={PICK} onClose={() => {}} onApplied={onApplied} />);
    await screen.findByAltText('지금 사진');
    fireEvent.click(screen.getByRole('button', { name: '더 밝게' }));
    expect(await screen.findByText('바꾼 뒤')).toBeInTheDocument();
    expect(screen.getByText('바꾸기 전')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '이걸로 쓰기' }));
    await waitFor(() => expect(onApplied).toHaveBeenCalledWith('hero', 'http://x/after.jpg'));
    expect(await screen.findByRole('button', { name: '되돌리기' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '되돌리기' }));
    await waitFor(() => expect(callsTo('/photo-edit/undo', 'POST')).toHaveLength(1));
  });

  it('내 사진으로 바꾸기 → 칸 태그로 올리고 미리보기 다시 그림·닫기', async () => {
    const onApplied = vi.fn();
    const onClose = vi.fn();
    stubFetch(async (url) => {
      if (url.includes('/photo-edit/target')) return okJson({ ...AI_TARGET, target: 'item:라떼' });
      if (url.includes('/photos')) return okJson({});
      throw new Error(`몰라요: ${url}`);
    });
    render(<PhotoSheet roomId="r1" pick={PICK} onClose={onClose} onApplied={onApplied} />);
    await screen.findByAltText('지금 사진');
    expect(screen.getByRole('button', { name: '내 사진으로 바꾸기' })).toBeInTheDocument();
    const input = screen.getByLabelText('내 사진으로 바꾸기') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [new File(['x'], 'a.jpg', { type: 'image/jpeg' })] } });
    await waitFor(() => expect(onClose).toHaveBeenCalled());
    const form = callsTo('/room/r1/photos', 'POST')[0][1]?.body as FormData;
    expect(form.get('tag')).toBe('item:라떼');
    expect(onApplied).toHaveBeenCalledWith('item:라떼', '');
  });

  it('첫 화면 사진은 hero 태그로 올리고 올리는 중에는 버튼이 잠긴다', async () => {
    const onApplied = vi.fn();
    const onClose = vi.fn();
    let done!: (v: Response) => void;
    stubFetch(async (url) => {
      if (url.includes('/photo-edit/target')) return okJson({ ...AI_TARGET, target: 'hero' });
      if (url.includes('/photos')) {
        return new Promise<Response>((resolve) => {
          done = resolve;
        });
      }
      throw new Error(`몰라요: ${url}`);
    });
    render(<PhotoSheet roomId="r1" pick={PICK} onClose={onClose} onApplied={onApplied} />);
    await screen.findByAltText('지금 사진');
    const input = screen.getByLabelText('내 사진으로 바꾸기') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [new File(['x'], 'a.jpg', { type: 'image/jpeg' })] } });
    expect(await screen.findByRole('button', { name: '올리는 중…' })).toBeDisabled();
    done(okJson({}));
    await waitFor(() => expect(onClose).toHaveBeenCalled());
    const form = callsTo('/room/r1/photos', 'POST')[0][1]?.body as FormData;
    expect(form.get('tag')).toBe('hero');
    expect(onApplied).toHaveBeenCalledWith('hero', '');
  });

  it('올리기 실패는 메시지를 보이고 시트를 닫지 않는다', async () => {
    const onApplied = vi.fn();
    const onClose = vi.fn();
    stubFetch(async (url) => {
      if (url.includes('/photo-edit/target')) return okJson({ ...AI_TARGET, target: 'hero' });
      if (url.includes('/photos')) return errJson(400, '사진을 올리지 못했습니다 (400)');
      throw new Error(`몰라요: ${url}`);
    });
    render(<PhotoSheet roomId="r1" pick={PICK} onClose={onClose} onApplied={onApplied} />);
    await screen.findByAltText('지금 사진');
    const input = screen.getByLabelText('내 사진으로 바꾸기') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [new File(['x'], 'a.jpg', { type: 'image/jpeg' })] } });
    expect(await screen.findByRole('status')).toHaveTextContent('사진을 올리지 못했습니다 (400)');
    expect(onClose).not.toHaveBeenCalled();
    expect(onApplied).not.toHaveBeenCalled();
    expect(screen.getByRole('dialog', { name: '사진 고치기' })).toBeInTheDocument();
  });

  it('사장님 사진은 안내만 보이고 입력은 없다', async () => {
    stubFetch(async (url) => {
      if (url.includes('/photo-edit/target')) return okJson(OWNER_TARGET);
      return okJson(CANDIDATE);
    });
    render(<PhotoSheet roomId="r1" pick={PICK} onClose={() => {}} onApplied={() => {}} />);
    await screen.findByAltText('지금 사진');
    expect(await screen.findByText('실제 사진은 밝기·색감·자르기만 바꿔요.')).toBeInTheDocument();
    expect(screen.queryByPlaceholderText('예: 더 따뜻한 느낌으로')).toBeNull();
    // 보정 버튼은 그대로 있다.
    expect(screen.getByRole('button', { name: '더 밝게' })).toBeInTheDocument();
  });

  it('AI 실패 detail을 그대로 보인다', async () => {
    stubFetch(async (url) => {
      if (url.includes('/photo-edit/target')) return okJson(AI_TARGET);
      if (url.includes('/photo-edit/preview')) return errJson(400, '사람·글자·간판·로고는 넣을 수 없어요');
      return okJson({});
    });
    render(<PhotoSheet roomId="r1" pick={PICK} onClose={() => {}} onApplied={() => {}} />);
    await screen.findByAltText('지금 사진');
    expect(await screen.findByText('오늘 9번 남았어요.')).toBeInTheDocument();
    fireEvent.change(screen.getByPlaceholderText('예: 더 따뜻한 느낌으로'), {
      target: { value: '사람 넣어 줘' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'AI로 고치기' }));
    expect(await screen.findByText('사람·글자·간판·로고는 넣을 수 없어요')).toBeInTheDocument();
  });

  it('취소하면 늦게 온 답을 버린다', async () => {
    let late = () => {};
    stubFetch(async (url) => {
      if (url.includes('/photo-edit/target')) return okJson(AI_TARGET);
      if (url.includes('/photo-edit/preview')) {
        return new Promise((resolve) => {
          late = () => resolve(okJson(CANDIDATE));
        }) as Promise<Response>;
      }
      return okJson({});
    });
    const onApplied = vi.fn();
    render(<PhotoSheet roomId="r1" pick={PICK} onClose={() => {}} onApplied={onApplied} />);
    await screen.findByAltText('지금 사진');
    fireEvent.click(screen.getByRole('button', { name: '더 밝게' }));
    expect(await screen.findByText('사진을 고치는 중이에요(최대 1분).')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '취소하기' }));
    expect(screen.queryByText('사진을 고치는 중이에요(최대 1분).')).toBeNull();
    late();
    await new Promise((r) => setTimeout(r, 30));
    expect(screen.queryByText('바꾼 뒤')).toBeNull();
    expect(onApplied).not.toHaveBeenCalled();
  });
});

describe('PhotoSheet 닫기', () => {
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  function openSheet(onClose: () => void) {
    stubFetch(async (url) => {
      if (url.includes('/photo-edit/target')) return okJson(AI_TARGET);
      return okJson({});
    });
    render(<PhotoSheet roomId="r1" pick={PICK} onClose={onClose} onApplied={() => {}} />);
    return screen.findByAltText('지금 사진');
  }

  it('✕ 버튼을 누르면 onClose가 1번 불린다', async () => {
    const onClose = vi.fn();
    await openSheet(onClose);
    fireEvent.click(screen.getByRole('button', { name: '닫기' }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('Esc 키를 누르면 onClose가 1번 불린다', async () => {
    const onClose = vi.fn();
    await openSheet(onClose);
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('시트 밖 어두운 곳을 누르면 onClose가 1번 불린다', async () => {
    const onClose = vi.fn();
    await openSheet(onClose);
    const dialog = screen.getByRole('dialog', { name: '사진 고치기' });
    const scrim = dialog.parentElement as HTMLElement;
    fireEvent.click(scrim);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('시트 안을 누르면 닫히지 않는다', async () => {
    const onClose = vi.fn();
    await openSheet(onClose);
    fireEvent.click(screen.getByRole('dialog', { name: '사진 고치기' }));
    fireEvent.click(screen.getByText('사진 고치기'));
    expect(onClose).not.toHaveBeenCalled();
  });
});

describe('PhotoSheet 남은 횟수', () => {
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it('AI로 고치면 남은 횟수를 다시 읽는다 (P3 검수)', async () => {
    let left = 9;
    stubFetch(async (url) => {
      if (url.includes('/photo-edit/target')) return okJson({ ...AI_TARGET, left_today: left });
      if (url.includes('/photo-edit/preview')) {
        left = 8;
        return okJson(CANDIDATE);
      }
      return okJson({});
    });
    render(<PhotoSheet roomId="r1" pick={PICK} onClose={() => {}} onApplied={() => {}} />);
    expect(await screen.findByText('오늘 9번 남았어요.')).toBeInTheDocument();
    fireEvent.change(screen.getByPlaceholderText('예: 더 따뜻한 느낌으로'), {
      target: { value: '여름 느낌으로' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'AI로 고치기' }));
    expect(await screen.findByText('오늘 8번 남았어요.')).toBeInTheDocument();
  });
});
