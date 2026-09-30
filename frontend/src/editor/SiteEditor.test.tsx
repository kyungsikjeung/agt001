// 보며 고치기 테스트 (EDIT_WAVE2_CONTRACT §6 9번, fetch 가짜).
import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import SiteEditor from './SiteEditor';
import type { RoomCard } from './cardApi';

const CARD: RoomCard = {
  title: '우리 가게',
  industry: '카페',
  fields: [
    { key: 'shop_name', label: '가게 이름', value: '우리 가게', status: 'filled', fact: false, placeholder: false },
    { key: 'offerings', label: '메뉴', value: '아메리카노, 바닐라라떼', status: 'filled', fact: false, placeholder: false },
    { key: 'phone', label: '전화번호', value: '010-1234-5678', status: 'filled', fact: true, placeholder: false },
    { key: 'hours', label: '영업시간', value: '매일 09:00~18:00', status: 'filled', fact: true, placeholder: false },
    { key: 'location', label: '위치', value: '앞골목', status: 'filled', fact: true, placeholder: false },
    { key: 'detail', label: '소개', value: '맛있는 커피', status: 'filled', fact: false, placeholder: false },
    { key: 'contact_method', label: '연락 방법', value: '전화', status: 'filled', fact: false, placeholder: false },
  ],
  photos: [],
  choice: 'v3',
  published: null,
  site_url: null,
  can_edit: true,
};

const PREVIEW = {
  variant: 'v3',
  html: '<!doctype html><html><body><section data-section-id="menu">메뉴</section></body></html>',
  sections: [
    { id: 'hero', label: '첫 화면', bind: 'hero', locked: true, hidden: false },
    { id: 'menu', label: '메뉴', bind: 'catalog', locked: false, hidden: false },
  ],
  addable: [{ id: 'sign', label: '시그니처', bind: 'signature' }],
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

function previewCalls() {
  const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
  return fetchMock.mock.calls.filter((c) => String(c[0]).includes('/card/preview'));
}

/** message를 보낸다. source가 iframe 창이면 panels가 열린다. */
function sendFrameMessage(source: unknown, data: unknown) {
  const evt = new MessageEvent('message', { data });
  Object.defineProperty(evt, 'source', { value: source });
  window.dispatchEvent(evt);
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

describe('SiteEditor', () => {
  it('iframe은 sandbox="allow-scripts"만 둔다', async () => {
    stubFetch(async (url) => {
      if (url.includes('/card/preview')) return okJson(PREVIEW);
      return okJson(CARD);
    });
    render(<SiteEditor roomId="r1" card={CARD} onSaved={() => {}} />);
    const frame = (await screen.findByTitle('사이트 미리보기')) as HTMLIFrameElement;
    expect(frame.getAttribute('sandbox')).toBe('allow-scripts');
  });

  it('미리보기 누름에 해당 구역 패널을 연다', async () => {
    stubFetch(async (url) => {
      if (url.includes('/card/preview')) return okJson(PREVIEW);
      return okJson(CARD);
    });
    render(<SiteEditor roomId="r1" card={CARD} onSaved={() => {}} />);
    const frame = (await screen.findByTitle('사이트 미리보기')) as HTMLIFrameElement;
    sendFrameMessage(frame.contentWindow, { type: 'agt-edit', section: 'menu', text: '아메리카노' });
    // 해당 구역 패널이 열리고, 누른 글자 항목이 먼저 펼쳐진다.
    expect(await screen.findByRole('button', { name: '구역 위로' })).toBeInTheDocument();
    expect(await screen.findByDisplayValue('아메리카노')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('예: 4,500원')).toBeInTheDocument();
  });

  it('다른 창의 가짜 message는 무시한다', async () => {
    stubFetch(async (url) => {
      if (url.includes('/card/preview')) return okJson(PREVIEW);
      return okJson(CARD);
    });
    render(<SiteEditor roomId="r1" card={CARD} onSaved={() => {}} />);
    await screen.findByTitle('사이트 미리보기');
    sendFrameMessage(window, { type: 'agt-edit', section: 'menu', text: '' });
    await new Promise((r) => setTimeout(r, 50));
    expect(screen.queryByRole('button', { name: '구역 위로' })).not.toBeInTheDocument();
    expect(screen.getByText('미리보기에서 고칠 곳을 누르세요.')).toBeInTheDocument();
  });

  it('저장 뒤 미리보기를 다시 요청한다', async () => {
    const puts: Array<{ url: string; body: unknown }> = [];
    stubFetch(async (url, init) => {
      if (url.includes('/card/preview')) return okJson(PREVIEW);
      if (init?.method === 'PUT') {
        puts.push({ url, body: JSON.parse(String(init.body)) });
        return okJson(CARD);
      }
      return okJson(CARD);
    });
    render(<SiteEditor roomId="r1" card={CARD} onSaved={() => {}} />);
    const frame = (await screen.findByTitle('사이트 미리보기')) as HTMLIFrameElement;
    expect(previewCalls()).toHaveLength(1);
    sendFrameMessage(frame.contentWindow, { type: 'agt-edit', section: 'menu', text: '' });
    fireEvent.click(await screen.findByRole('button', { name: '숨기기' }));
    await waitFor(() => expect(puts).toHaveLength(1));
    expect(puts[0].url).toBe('/api/rooms/r1/card');
    expect(puts[0].body).toMatchObject({ layout: { variant: 'v3', hidden: ['menu'] } });
    await waitFor(() => expect(previewCalls()).toHaveLength(2));
  });

  it('서버의 지금 값에서 시작한다: 더한 구역을 유지하고 가격을 채운다', async () => {
    const puts: unknown[] = [];
    const saved = {
      ...PREVIEW,
      layout: { added: ['space'] },
      items: [{ name: '아메리카노', price: '4,500원', note: '' }],
    };
    stubFetch(async (url, init) => {
      if (url.includes('/card/preview')) return okJson(saved);
      if (init?.method === 'PUT') puts.push(JSON.parse(String(init.body)));
      return okJson(CARD);
    });
    render(<SiteEditor roomId="r1" card={CARD} onSaved={() => {}} />);
    const frame = (await screen.findByTitle('사이트 미리보기')) as HTMLIFrameElement;
    sendFrameMessage(frame.contentWindow, { type: 'agt-edit', section: 'menu', text: '아메리카노' });
    expect(await screen.findByDisplayValue('4,500원')).toBeInTheDocument();
    fireEvent.click(await screen.findByRole('button', { name: '숨기기' }));
    await waitFor(() => expect(puts).toHaveLength(1));
    expect(puts[0]).toMatchObject({ layout: { added: ['space'], hidden: ['menu'] } });
  });

  it('구역을 고르기 전에도 구역을 더할 수 있다', async () => {
    const puts: unknown[] = [];
    stubFetch(async (url, init) => {
      if (url.includes('/card/preview')) return okJson(PREVIEW);
      if (init?.method === 'PUT') puts.push(JSON.parse(String(init.body)));
      return okJson(CARD);
    });
    render(<SiteEditor roomId="r1" card={CARD} onSaved={() => {}} />);
    fireEvent.click(await screen.findByRole('button', { name: '+ 시그니처' }));
    await waitFor(() => expect(puts).toHaveLength(1));
    expect(puts[0]).toMatchObject({ layout: { variant: 'v3', added: ['sign'] } });
  });
});

describe('SiteEditor 미리보기 크기', () => {
  it('노트북을 누르면 넓게 바뀌고 다음에도 기억한다', async () => {
    stubFetch(async (url) => {
      if (url.includes('/card/preview')) return okJson(PREVIEW);
      return okJson(CARD);
    });
    const { container, unmount } = render(<SiteEditor roomId="r1" card={CARD} onSaved={() => {}} />);
    await screen.findByTitle('사이트 미리보기');
    fireEvent.click(screen.getByRole('button', { name: '노트북' }));
    expect(container.querySelector('.ed-site-body--desktop')).not.toBeNull();
    unmount();
    const again = render(<SiteEditor roomId="r1" card={CARD} onSaved={() => {}} />);
    await screen.findByTitle('사이트 미리보기');
    expect(again.container.querySelector('.ed-site-body--desktop')).not.toBeNull();
    expect(screen.getByRole('button', { name: '노트북' })).toHaveAttribute('aria-pressed', 'true');
  });
});
