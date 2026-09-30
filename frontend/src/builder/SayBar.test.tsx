// 말로 고치기 화면 테스트 (SAY_CONTRACT §7, fetch 가짜).
import '@testing-library/jest-dom/vitest';
import { cleanup, act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import BuilderPage from './BuilderPage';

const CARD = {
  title: '우리 가게',
  industry: '카페',
  fields: [
    { key: 'shop_name', label: '가게 이름', value: '우리 가게', status: 'filled', fact: false, placeholder: false },
    { key: 'phone', label: '전화번호', value: '010-1234-5678', status: 'filled', fact: true, placeholder: false },
    { key: 'location', label: '위치', value: '앞골목', status: 'filled', fact: true, placeholder: false },
  ],
  photos: [],
  choice: 'v1',
  published: null,
  site_url: null,
  can_edit: true,
};

const FEATURES = [
  { key: 'section:menu', label: '메뉴', kind: 'section', on: true, locked: false },
  { key: 'section:space', label: '공간', kind: 'section', on: false, locked: false },
  { key: 'notice', label: '공지', kind: 'shop', on: false, needs_text: true },
];

const PREVIEW = {
  variant: 'v1',
  html: '<!doctype html><html><body><section data-section-id="menu">메뉴</section></body></html>',
  sections: [
    { id: 'hero', label: '첫 화면', bind: 'hero', locked: true, hidden: false },
    { id: 'menu', label: '메뉴', bind: 'catalog', locked: false, hidden: false },
  ],
  addable: [{ id: 'space', label: '공간', bind: 'space_photos' }],
};

let heard: ((text: string) => void) | null = null;

vi.mock('../voice', () => ({
  useVoiceInput: (onText: (text: string) => void) => {
    heard = onText;
    return { state: 'idle', seconds: 0, status: null, numCheck: false, toggle: () => {}, clearNumCheck: () => {} };
  },
}));

function stubFetch(handler: (url: string, init?: RequestInit) => Promise<unknown>) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => handler(url, init)),
  );
}

function okJson(data: unknown) {
  return { ok: true, status: 200, json: async () => data } as Response;
}

function callsTo(part: string, method?: string) {
  const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
  return fetchMock.mock.calls.filter(
    (c) => String(c[0]).includes(part) && (!method || (c[1] as RequestInit | undefined)?.method === method),
  );
}

function baseStub(extra: (url: string, init?: RequestInit) => Promise<unknown>) {
  stubFetch(async (url, init) => {
    const r = await extra(url, init);
    if (r) return r;
    if (url.includes('/card/preview')) return okJson(PREVIEW);
    if (url.includes('/features')) return okJson({ variant: 'v1', features: FEATURES });
    return okJson(CARD);
  });
}

beforeEach(() => {
  localStorage.clear();
  localStorage.setItem('agt001_member_id', 'm1');
  heard = null;
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('말로 고치기', () => {
  it('보내기 → POST /say, 말풍선, 미리보기 다시, agt-scroll+flash(focus), 칩 갱신', async () => {
    const says: unknown[] = [];
    const onFeatures = FEATURES.map((f) => (f.key === 'section:space' ? { ...f, on: true } : f));
    baseStub(async (url, init) => {
      if (url.includes('/say')) {
        says.push(JSON.parse(String(init?.body)));
        return okJson({
          reply: '공간을 켰어요.',
          focus: 'space',
          features: onFeatures,
          undo: true,
          rejected: [],
          source: 'rule',
        });
      }
      return null;
    });
    render(<BuilderPage roomId="r1" />);
    await screen.findByTitle('사이트 미리보기');
    fireEvent.change(screen.getByLabelText('말로 고치기'), { target: { value: '공간 보여 줘' } });
    fireEvent.click(screen.getByRole('button', { name: '보내기' }));
    await waitFor(() => expect(says).toHaveLength(1));
    expect(says[0]).toEqual({ text: '공간 보여 줘' });
    // 답 말풍선과 되돌리기 버튼이 보인다.
    expect(await screen.findByLabelText('고치기 답')).toHaveTextContent('공간을 켰어요.');
    expect(screen.getByRole('button', { name: '되돌리기' })).toBeInTheDocument();
    // 칩이 새 목록으로 바뀐다.
    expect(screen.getByRole('button', { name: '공간' })).toHaveAttribute('aria-pressed', 'true');
    // 미리보기를 다시 요청한다.
    await waitFor(() => expect(callsTo('/card/preview')).toHaveLength(2));
    // 다 그린 뒤 바뀐 구역으로 스크롤·반짝한다.
    const frame = (await screen.findByTitle('사이트 미리보기')) as HTMLIFrameElement;
    const post = vi.fn();
    Object.defineProperty(frame, 'contentWindow', { value: { postMessage: post }, configurable: true });
    fireEvent.load(frame);
    await waitFor(() => expect(post).toHaveBeenCalledWith({ type: 'agt-scroll', section: 'space' }, '*'));
    expect(post).toHaveBeenCalledWith({ type: 'agt-flash', section: 'space' }, '*');
  });

  it('rejected는 말풍선 아래 작은 글로 보인다', async () => {
    baseStub(async (url) => {
      if (url.includes('/say')) {
        return okJson({
          reply: '가격은 말씀해 주셔야 넣어요.',
          focus: null,
          features: FEATURES,
          undo: false,
          rejected: ['말씀하지 않은 가격이라 넣지 않았어요'],
          source: 'llm',
        });
      }
      return null;
    });
    render(<BuilderPage roomId="r1" />);
    await screen.findByTitle('사이트 미리보기');
    fireEvent.change(screen.getByLabelText('말로 고치기'), { target: { value: '가격 적당히 넣어 줘' } });
    fireEvent.click(screen.getByRole('button', { name: '보내기' }));
    expect(await screen.findByText('말씀하지 않은 가격이라 넣지 않았어요')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '되돌리기' })).not.toBeInTheDocument();
  });

  it('되돌리기 → POST /undo 후 버튼이 사라진다', async () => {
    const undos: unknown[] = [];
    baseStub(async (url) => {
      if (url.includes('/undo')) {
        undos.push(true);
        return okJson({ reply: '방금 고친 것을 되돌렸어요.', features: FEATURES, undo: false });
      }
      if (url.includes('/say')) {
        return okJson({
          reply: '공간을 켰어요.',
          focus: 'space',
          features: FEATURES,
          undo: true,
          rejected: [],
          source: 'rule',
        });
      }
      return null;
    });
    render(<BuilderPage roomId="r1" />);
    await screen.findByTitle('사이트 미리보기');
    fireEvent.change(screen.getByLabelText('말로 고치기'), { target: { value: '공간 보여 줘' } });
    fireEvent.click(screen.getByRole('button', { name: '보내기' }));
    fireEvent.click(await screen.findByRole('button', { name: '되돌리기' }));
    await waitFor(() => expect(undos).toHaveLength(1));
    expect(await screen.findByLabelText('고치기 답')).toHaveTextContent('방금 고친 것을 되돌렸어요.');
    await waitFor(() => expect(screen.queryByRole('button', { name: '되돌리기' })).not.toBeInTheDocument());
  });

  it('다음 칩 변경 뒤에는 되돌리기 버튼이 사라진다', async () => {
    baseStub(async (url, init) => {
      if (url.includes('/say')) {
        return okJson({
          reply: '공간을 켰어요.',
          focus: 'space',
          features: FEATURES,
          undo: true,
          rejected: [],
          source: 'rule',
        });
      }
      if (url.includes('/features') && init?.method === 'PUT') {
        return okJson({ features: FEATURES, focus: null });
      }
      return null;
    });
    render(<BuilderPage roomId="r1" />);
    await screen.findByTitle('사이트 미리보기');
    fireEvent.change(screen.getByLabelText('말로 고치기'), { target: { value: '공간 보여 줘' } });
    fireEvent.click(screen.getByRole('button', { name: '보내기' }));
    await screen.findByRole('button', { name: '되돌리기' });
    fireEvent.click(screen.getByRole('button', { name: '공간' }));
    await waitFor(() => expect(screen.queryByRole('button', { name: '되돌리기' })).not.toBeInTheDocument());
  });

  it('입력은 300자까지, 보내는 동안 잠그고 "고치는 중…"을 보인다', async () => {
    let release: (v: unknown) => void = () => {};
    baseStub(async (url) => {
      if (url.includes('/say')) {
        await new Promise((resolve) => {
          release = resolve as (v: unknown) => void;
        });
        return okJson({ reply: '고쳤어요.', focus: null, features: FEATURES, undo: false, rejected: [], source: 'rule' });
      }
      return null;
    });
    render(<BuilderPage roomId="r1" />);
    const input = (await screen.findByLabelText('말로 고치기')) as HTMLInputElement;
    expect(input.maxLength).toBe(300);
    fireEvent.change(input, { target: { value: '가'.repeat(400) } });
    expect(input.value).toHaveLength(300);
    fireEvent.click(screen.getByRole('button', { name: '보내기' }));
    // 보내는 동안 입력이 잠기고 버튼 글자가 바뀐다.
    expect((screen.getByLabelText('말로 고치기') as HTMLInputElement).disabled).toBe(true);
    expect(screen.getByRole('button', { name: '고치는 중…' })).toBeDisabled();
    release(null);
    await waitFor(() =>
      expect((screen.getByLabelText('말로 고치기') as HTMLInputElement).disabled).toBe(false),
    );
  });

  it('마이크 글은 입력에만 들어가고 보내지 않는다', async () => {
    baseStub(async () => null);
    render(<BuilderPage roomId="r1" />);
    await screen.findByTitle('사이트 미리보기');
    expect(heard).not.toBeNull();
    act(() => {
      heard!('메뉴에 빙수 넣어 줘');
    });
    expect((screen.getByLabelText('말로 고치기') as HTMLInputElement).value).toBe('메뉴에 빙수 넣어 줘');
    expect(callsTo('/say', 'POST')).toHaveLength(0);
  });
});
