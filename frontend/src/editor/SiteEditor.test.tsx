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
    // 가격은 공용 단위 칸(금액·직접 쓰기)
    expect(screen.getByRole('group', { name: '가격' })).toBeInTheDocument();
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
    expect(await screen.findByDisplayValue('4500')).toBeInTheDocument();
    expect(screen.getByText('보이는 글: 4,500원')).toBeInTheDocument();
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
  it('데스크톱을 누르면 넓게 바뀌고 다음에도 기억한다', async () => {
    stubFetch(async (url) => {
      if (url.includes('/card/preview')) return okJson(PREVIEW);
      return okJson(CARD);
    });
    const { container, unmount } = render(<SiteEditor roomId="r1" card={CARD} onSaved={() => {}} />);
    await screen.findByTitle('사이트 미리보기');
    fireEvent.click(screen.getByRole('button', { name: '데스크톱' }));
    expect(container.querySelector('.ed-site-body--desktop')).not.toBeNull();
    unmount();
    const again = render(<SiteEditor roomId="r1" card={CARD} onSaved={() => {}} />);
    await screen.findByTitle('사이트 미리보기');
    expect(again.container.querySelector('.ed-site-body--desktop')).not.toBeNull();
    expect(screen.getByRole('button', { name: '데스크톱' })).toHaveAttribute('aria-pressed', 'true');
  });
});

describe('SiteEditor 구역 바로가기 (빌더, 넓은 화면)', () => {
  it('구역을 누르면 그 구역이 골라지고 고치기 칸이 열린다', async () => {
    vi.stubGlobal('matchMedia', (q: string) => ({
      matches: q.includes('min-width'),
      addEventListener: () => {},
      removeEventListener: () => {},
    }));
    stubFetch(async (url) => {
      if (url.includes('/card/preview')) return okJson(PREVIEW);
      return okJson(CARD);
    });
    render(<SiteEditor roomId="r1" card={CARD} onSaved={() => {}} builderMode />);
    const nav = await screen.findByRole('navigation', { name: '구역 바로가기' });
    const menu = Array.from(nav.querySelectorAll('button')).find((b) => b.textContent === '메뉴')!;
    fireEvent.click(menu);
    expect(menu).toHaveAttribute('aria-current', 'true');
    expect(screen.queryByText('미리보기에서 고칠 곳을 누르세요.')).toBeNull();
  });

  it('좁은 화면에선 구역 바로가기를 그리지 않는다', async () => {
    stubFetch(async (url) => {
      if (url.includes('/card/preview')) return okJson(PREVIEW);
      return okJson(CARD);
    });
    render(<SiteEditor roomId="r1" card={CARD} onSaved={() => {}} builderMode />);
    await screen.findByTitle('사이트 미리보기');
    expect(screen.queryByRole('navigation', { name: '구역 바로가기' })).toBeNull();
  });
});

describe('SiteEditor 구역 끌어서 순서 바꾸기 (J4)', () => {
  const DRAG_PREVIEW = {
    variant: 'v3',
    html: '<!doctype html><html><body></body></html>',
    layout: { added: [] },
    items: [],
    sections: [
      { id: 'hero', label: '첫 화면', bind: 'hero', locked: true, hidden: false },
      { id: 's2', label: '두 번째', bind: 'catalog', locked: false, hidden: false },
      { id: 's3', label: '세 번째', bind: 'catalog', locked: false, hidden: false },
      { id: 's4', label: '네 번째', bind: 'catalog', locked: false, hidden: false },
    ],
    addable: [],
  };

  function stubWide() {
    vi.stubGlobal('matchMedia', (q: string) => ({
      matches: q.includes('min-width'),
      addEventListener: () => {},
      removeEventListener: () => {},
    }));
  }

  function dragData() {
    return { setData: vi.fn(), getData: vi.fn(), effectAllowed: 'uninitialized', dropEffect: 'none' };
  }

  it('locked 구역은 끌 수 없고 줄 앞에 손잡이가 있다', async () => {
    stubWide();
    stubFetch(async (url) => {
      if (url.includes('/card/preview')) return okJson(DRAG_PREVIEW);
      return okJson(CARD);
    });
    render(<SiteEditor roomId="r1" card={CARD} onSaved={() => {}} builderMode />);
    const nav = await screen.findByRole('navigation', { name: '구역 바로가기' });
    const items = nav.querySelectorAll('li');
    expect(items).toHaveLength(4);
    expect(items[0].getAttribute('draggable')).toBe('false');
    expect(items[1].getAttribute('draggable')).toBe('true');
    const grip = items[1].querySelector('.ed-outline-grip');
    expect(grip).not.toBeNull();
    expect(grip).toHaveAttribute('aria-hidden', 'true');
    expect(grip?.textContent).toContain('⋮⋮');
  });

  it('2번째를 4번째로 끌면 바뀐 order로 1번 저장한다', async () => {
    stubWide();
    const puts: unknown[] = [];
    stubFetch(async (url, init) => {
      if (url.includes('/card/preview')) return okJson(DRAG_PREVIEW);
      if (init?.method === 'PUT') {
        puts.push(JSON.parse(String(init.body)));
        return okJson(CARD);
      }
      return okJson(CARD);
    });
    render(<SiteEditor roomId="r1" card={CARD} onSaved={() => {}} builderMode />);
    const nav = await screen.findByRole('navigation', { name: '구역 바로가기' });
    const items = nav.querySelectorAll('li');
    fireEvent.dragStart(items[1], { dataTransfer: dragData() });
    fireEvent.dragOver(items[3], { dataTransfer: dragData() });
    expect(items[3].className).toContain('ed-outline-drop');
    fireEvent.drop(items[3]);
    await waitFor(() => expect(puts).toHaveLength(1));
    expect(puts[0]).toMatchObject({ layout: { variant: 'v3', order: ['hero', 's3', 's4', 's2'] } });
  });

  it('같은 자리에 놓으면 저장하지 않는다', async () => {
    stubWide();
    const puts: unknown[] = [];
    stubFetch(async (url, init) => {
      if (url.includes('/card/preview')) return okJson(DRAG_PREVIEW);
      if (init?.method === 'PUT') {
        puts.push(JSON.parse(String(init.body)));
        return okJson(CARD);
      }
      return okJson(CARD);
    });
    render(<SiteEditor roomId="r1" card={CARD} onSaved={() => {}} builderMode />);
    const nav = await screen.findByRole('navigation', { name: '구역 바로가기' });
    const items = nav.querySelectorAll('li');
    fireEvent.dragStart(items[1], { dataTransfer: dragData() });
    fireEvent.drop(items[1]);
    await new Promise((r) => setTimeout(r, 50));
    expect(puts).toHaveLength(0);
  });

  it('저장에 실패하면 알림 문구를 보여준다', async () => {
    stubWide();
    stubFetch(async (url, init) => {
      if (url.includes('/card/preview')) return okJson(DRAG_PREVIEW);
      if (init?.method === 'PUT') return { ok: false, status: 500, json: async () => ({}) } as Response;
      return okJson(CARD);
    });
    render(<SiteEditor roomId="r1" card={CARD} onSaved={() => {}} builderMode />);
    const nav = await screen.findByRole('navigation', { name: '구역 바로가기' });
    const items = nav.querySelectorAll('li');
    fireEvent.dragStart(items[1], { dataTransfer: dragData() });
    fireEvent.dragOver(items[3], { dataTransfer: dragData() });
    fireEvent.drop(items[3]);
    expect(await screen.findByRole('alert')).toHaveTextContent('순서를 바꾸지 못했어요. 잠시 뒤 다시 해 주세요.');
  });
});
