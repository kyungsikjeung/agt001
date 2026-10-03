// 빌더 화면 테스트 (BUILDER_CONTRACT §6 8번, fetch 가짜).
import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
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
  { key: 'chat', label: '채팅', kind: 'shop', on: true, after_publish: true },
  { key: 'stamps', label: '스탬프', kind: 'shop', on: false, after_publish: true },
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

/** iframe 창이 보낸 것처럼 message를 보낸다. */
function sendFrameMessage(source: unknown, data: unknown) {
  const evt = new MessageEvent('message', { data });
  Object.defineProperty(evt, 'source', { value: source });
  window.dispatchEvent(evt);
}

const PHOTO_TARGET = {
  target: 'hero',
  kind: 'ai',
  current_url: 'http://x/before.jpg',
  actions: ['brighter', 'warmer', 'sharper', 'square', 'wide'],
  ai_allowed: true,
  left_today: 9,
  cooldown_sec: 0,
};

beforeEach(() => {
  localStorage.clear();
  localStorage.setItem('agt001_member_id', 'm1');
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('BuilderPage', () => {
  it('칩 누름 → PUT → 미리보기 다시 요청 → agt-scroll(focus) 전송', async () => {
    const puts: unknown[] = [];
    // 다시 그리면 iframe이 새로 붙는다. 어느 iframe이든 같은 가짜 창으로 받는다.
    const post = vi.fn();
    vi.spyOn(HTMLIFrameElement.prototype, 'contentWindow', 'get').mockReturnValue({ postMessage: post } as unknown as Window);
    let previews = 0;
    stubFetch(async (url, init) => {
      if (url.includes('/card/preview')) {
        previews += 1;
        return okJson({ ...PREVIEW, html: `${PREVIEW.html}<!--p${previews}-->` });
      }
      if (url.includes('/features') && init?.method === 'PUT') {
        puts.push(JSON.parse(String(init.body)));
        const on = (puts[puts.length - 1] as { on: boolean }).on;
        return okJson({
          features: FEATURES.map((f) => (f.key === 'section:space' ? { ...f, on } : f)),
          focus: on ? 'space' : null,
        });
      }
      if (url.includes('/features')) return okJson({ variant: 'v1', features: FEATURES });
      return okJson(CARD);
    });
    render(<BuilderPage roomId="r1" />);
    fireEvent.click(await screen.findByRole('button', { name: '공간' }));
    await waitFor(() => expect(puts).toHaveLength(1));
    expect(puts[0]).toEqual({ key: 'section:space', on: true });
    // 미리보기를 다시 요청한다.
    await waitFor(() => expect(callsTo('/card/preview')).toHaveLength(2));
    // 다시 그린 iframe이 뜬 뒤 load → 붙은 구역으로 스크롤·반짝한다 (옛 iframe을 잡으면 CI에서 가끔 놓친다).
    await waitFor(() => {
      const frame = screen.getByTitle('사이트 미리보기');
      expect(frame.getAttribute('srcdoc')).toContain('<!--p2-->');
      fireEvent.load(frame);
      expect(post).toHaveBeenCalledWith({ type: 'agt-scroll', section: 'space' }, '*');
    });
    expect(post).toHaveBeenCalledWith({ type: 'agt-flash', section: 'space' }, '*');
  });

  it('무료 디자인 고치기 남은 횟수를 보인다 (USAGE_QUOTA_CONTRACT §3)', async () => {
    const withQuota = { ...CARD, quota: { design: { left: 3, total: 3 }, restyle: { left: 18, total: 20 }, resets: '11월 1일' } };
    stubFetch(async (url) => {
      if (url.includes('/card/preview')) return okJson(PREVIEW);
      if (url.includes('/features')) return okJson({ variant: 'v1', features: FEATURES });
      return okJson(withQuota);
    });
    render(<BuilderPage roomId="r1" />);
    expect(await screen.findByText('무료 디자인 고치기 18번 남음 · 11월 1일에 다시 채워져요')).toBeInTheDocument();
  });

  it('까치를 누르면 처음 화면으로 간다 (J7)', async () => {
    stubFetch(async (url) => {
      if (url.includes('/card/preview')) return okJson(PREVIEW);
      if (url.includes('/features')) return okJson({ variant: 'v1', features: FEATURES });
      return okJson(CARD);
    });
    render(<BuilderPage roomId="r1" />);
    await screen.findByTitle('사이트 미리보기');
    expect(screen.getByRole('link', { name: '처음 화면으로' }).getAttribute('href')).toBe('/');
  });

  it('빌더 모드에서는 구역 목록을 접는다', async () => {
    stubFetch(async (url) => {
      if (url.includes('/card/preview')) return okJson(PREVIEW);
      if (url.includes('/features')) return okJson({ variant: 'v1', features: FEATURES });
      return okJson(CARD);
    });
    render(<BuilderPage roomId="r1" />);
    await screen.findByTitle('사이트 미리보기');
    // 목록은 CSS로 접고(SiteEditor는 그대로), 칩을 쓴다.
    expect(document.querySelector('.ed-site--builder')).not.toBeNull();
    expect(screen.getByRole('group', { name: '기능 켜고 끄기' })).toBeInTheDocument();
  });

  it('after_publish 채팅 칩은 PUT 없이 안내 창을 연다', async () => {
    stubFetch(async (url) => {
      if (url.includes('/card/preview')) return okJson(PREVIEW);
      if (url.includes('/features')) return okJson({ variant: 'v1', features: FEATURES });
      return okJson(CARD);
    });
    render(<BuilderPage roomId="r1" />);
    fireEvent.click(await screen.findByRole('button', { name: '채팅' }));
    expect(await screen.findByRole('dialog', { name: '채팅' })).toBeInTheDocument();
    expect(screen.getByText('손님 채팅')).toBeInTheDocument();
    expect(screen.getByText('지금: 켜짐')).toBeInTheDocument();
    expect(screen.getByText('사이트를 공개하면 바로 쓸 수 있어요.')).toBeInTheDocument();
    expect(callsTo('/features', 'PUT')).toHaveLength(0);
    fireEvent.click(screen.getByRole('button', { name: '닫기' }));
    await waitFor(() => expect(screen.queryByRole('dialog', { name: '채팅' })).not.toBeInTheDocument());
    expect(callsTo('/features', 'PUT')).toHaveLength(0);
  });

  it('스탬프 칩 안내에는 꺼짐 상태가 보인다 (PUT 없음)', async () => {
    stubFetch(async (url) => {
      if (url.includes('/card/preview')) return okJson(PREVIEW);
      if (url.includes('/features')) return okJson({ variant: 'v1', features: FEATURES });
      return okJson(CARD);
    });
    render(<BuilderPage roomId="r1" />);
    fireEvent.click(await screen.findByRole('button', { name: '스탬프' }));
    expect(await screen.findByText('스탬프 적립')).toBeInTheDocument();
    expect(screen.getByText('지금: 꺼짐')).toBeInTheDocument();
    expect(callsTo('/features', 'PUT')).toHaveLength(0);
  });

  it('안내 창은 Esc로 닫히고 공개 뒤에는 사장님 화면 링크를 보인다', async () => {
    const published = { ...CARD, published: '2026-10-03', site_url: 'https://example.com/s1' };
    stubFetch(async (url) => {
      if (url.includes('/card/preview')) return okJson(PREVIEW);
      if (url.includes('/features')) return okJson({ variant: 'v1', features: FEATURES });
      return okJson(published);
    });
    render(<BuilderPage roomId="r1" />);
    fireEvent.click(await screen.findByRole('button', { name: '채팅' }));
    const link = await screen.findByRole('link', { name: '사장님 화면 열기' });
    expect(link.getAttribute('href')).toBe('/owner');
    fireEvent.keyDown(window, { key: 'Escape' });
    await waitFor(() => expect(screen.queryByRole('dialog', { name: '채팅' })).not.toBeInTheDocument());
    expect(callsTo('/features', 'PUT')).toHaveLength(0);
  });

  it('공지 칩은 글을 적고 켠다', async () => {
    const puts: unknown[] = [];
    stubFetch(async (url, init) => {
      if (url.includes('/card/preview')) return okJson(PREVIEW);
      if (url.includes('/features') && init?.method === 'PUT') {
        puts.push(JSON.parse(String(init.body)));
        return okJson({ features: FEATURES.map((f) => (f.key === 'notice' ? { ...f, on: true } : f)), focus: null });
      }
      if (url.includes('/features')) return okJson({ variant: 'v1', features: FEATURES });
      return okJson(CARD);
    });
    render(<BuilderPage roomId="r1" />);
    fireEvent.click(await screen.findByRole('button', { name: '공지' }));
    fireEvent.change(await screen.findByPlaceholderText('예: 10월 3일은 쉬어요'), {
      target: { value: '10월 3일은 쉬어요' },
    });
    fireEvent.click(screen.getByRole('button', { name: '켜기' }));
    await waitFor(() => expect(puts).toHaveLength(1));
    expect(puts[0]).toEqual({ key: 'notice', on: true, text: '10월 3일은 쉬어요' });
  });

  it('공지를 켜면 "공지 칩을 다시 누르세요" 안내가 뜨고, 도움말(ⓘ)은 고치는 곳을 알려 준다', async () => {
    stubFetch(async (url, init) => {
      if (url.includes('/card/preview')) return okJson(PREVIEW);
      if (url.includes('/features') && init?.method === 'PUT') {
        return okJson({ features: FEATURES.map((f) => (f.key === 'notice' ? { ...f, on: true } : f)), focus: null });
      }
      if (url.includes('/features')) return okJson({ variant: 'v1', features: FEATURES });
      return okJson(CARD);
    });
    render(<BuilderPage roomId="r1" />);
    fireEvent.click(await screen.findByRole('button', { name: '공지' }));
    const tip = screen.getByRole('button', { name: '공지 도움말' });
    expect(tip).toHaveAttribute('aria-expanded', 'false');
    fireEvent.click(tip);
    expect(tip).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByText(/칩을 다시 누르세요\. 이 창이 다시 열려요/)).toBeInTheDocument();
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(tip).toHaveAttribute('aria-expanded', 'false');
    fireEvent.change(screen.getByPlaceholderText('예: 10월 3일은 쉬어요'), { target: { value: '추석 휴무' } });
    fireEvent.click(screen.getByRole('button', { name: '켜기' }));
    expect(await screen.findByText(/공지를 켰어요\. 고치거나 끄려면 위/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '알겠어요' }));
    expect(screen.queryByText(/공지를 켰어요\. 고치거나 끄려면 위/)).not.toBeInTheDocument();
  });

  it('켜진 공지 칩을 다시 누르면 바로 끄지 않고 지금 글로 고치기 창을 연다(저장·끄기)', async () => {
    const puts: unknown[] = [];
    const on = FEATURES.map((f) => (f.key === 'notice' ? { ...f, on: true } : f));
    stubFetch(async (url, init) => {
      if (url.includes('/card/preview')) return okJson(PREVIEW);
      if (url.includes('/features') && init?.method === 'PUT') {
        puts.push(JSON.parse(String(init.body)));
        return okJson({ features: on, focus: null });
      }
      if (url.includes('/features')) return okJson({ variant: 'v1', features: on });
      return okJson({ ...CARD, notice: { text: '추석 휴무', popup: false, photos: [] } });
    });
    render(<BuilderPage roomId="r1" />);
    fireEvent.click(await screen.findByRole('button', { name: '공지' }));
    expect(puts).toHaveLength(0); // 누르자마자 끄지 않는다
    expect(screen.getByRole('dialog', { name: '공지 고치기' })).toBeInTheDocument();
    expect(screen.getByDisplayValue('추석 휴무')).toBeInTheDocument();
    fireEvent.change(screen.getByDisplayValue('추석 휴무'), { target: { value: '추석 연휴 9/16~18 휴무' } });
    fireEvent.click(screen.getByRole('button', { name: '저장' }));
    await waitFor(() => expect(puts).toHaveLength(1));
    expect(puts[0]).toEqual({ key: 'notice', on: true, text: '추석 연휴 9/16~18 휴무' });
    fireEvent.click(await screen.findByRole('button', { name: '공지' }));
    fireEvent.click(screen.getByRole('button', { name: '공지 끄기' }));
    await waitFor(() => expect(puts).toHaveLength(2));
    expect(puts[1]).toEqual({ key: 'notice', on: false });
  });

  it('회원 가입을 아직 안 정했으면 한 번 묻고, 고르면 PUT /features {members}', async () => {
    const puts: unknown[] = [];
    const feats = [...FEATURES, { key: 'members', label: '회원', kind: 'shop', on: false, members: true }];
    stubFetch(async (url, init) => {
      if (url.includes('/card/preview')) return okJson(PREVIEW);
      if (url.includes('/features') && init?.method === 'PUT') {
        puts.push(JSON.parse(String(init.body)));
        return okJson({ features: feats.map((f) => (f.key === 'members' ? { ...f, on: true } : f)), focus: null });
      }
      if (url.includes('/features')) return okJson({ variant: 'v1', features: feats });
      return okJson({ ...CARD, members: puts.length ? { signup: true, method: 'phone' } : null });
    });
    render(<BuilderPage roomId="r1" />);
    const ask = await screen.findByRole('group', { name: /손님 회원 가입을 받을까요/ });
    fireEvent.click(within(ask).getByRole('button', { name: '회원 가입 받기' }));
    await waitFor(() => expect(puts).toEqual([{ key: 'members', on: true }]));
    await waitFor(() => expect(screen.queryByRole('group', { name: /손님 회원 가입을 받을까요/ })).not.toBeInTheDocument());
    expect(screen.getByText("손님 회원 가입을 받아요. 공개 사이트 메뉴에 '내 정보'가 생겨요.")).toBeInTheDocument();
  });

  it('회원 칩은 설명 창(무엇이 생기나·문자 비용)에서 켜고 끈다', async () => {
    const puts: unknown[] = [];
    const feats = [...FEATURES, { key: 'members', label: '회원', kind: 'shop', on: true, members: true }];
    stubFetch(async (url, init) => {
      if (url.includes('/card/preview')) return okJson(PREVIEW);
      if (url.includes('/features') && init?.method === 'PUT') {
        puts.push(JSON.parse(String(init.body)));
        return okJson({ features: feats.map((f) => (f.key === 'members' ? { ...f, on: false } : f)), focus: null });
      }
      if (url.includes('/features')) return okJson({ variant: 'v1', features: feats });
      return okJson({ ...CARD, members: { signup: true, method: 'phone' } });
    });
    render(<BuilderPage roomId="r1" />);
    expect(screen.queryByRole('group', { name: /손님 회원 가입을 받을까요/ })).toBeNull(); // 이미 정한 사이트는 안 물음
    fireEvent.click(await screen.findByRole('button', { name: '회원' }));
    const sheet = screen.getByRole('dialog', { name: '손님 회원 가입' });
    expect(within(sheet).getByText('지금: 받는 중')).toBeInTheDocument();
    expect(within(sheet).getByText(/하루 30건/)).toBeInTheDocument();
    expect(puts).toHaveLength(0);
    fireEvent.click(within(sheet).getByRole('button', { name: '회원 가입 그만 받기' }));
    await waitFor(() => expect(puts).toEqual([{ key: 'members', on: false }]));
  });

  it('모양 바꾸기는 PUT /card {choice}로 저장한다', async () => {
    const puts: unknown[] = [];
    stubFetch(async (url, init) => {
      if (url.includes('/card/preview')) return okJson(PREVIEW);
      if (url.includes('/features')) return okJson({ variant: 'v1', features: FEATURES });
      if (init?.method === 'PUT') {
        puts.push(JSON.parse(String(init?.body)));
        return okJson({ ...CARD, choice: 'v2' });
      }
      return okJson(CARD);
    });
    render(<BuilderPage roomId="r1" />);
    await screen.findByTitle('사이트 미리보기');
    const second = screen.getAllByRole('button', { name: '2안' })[0];
    fireEvent.click(second);
    await waitFor(() => expect(puts).toHaveLength(1));
    expect(puts[0]).toEqual({ fields: {}, choice: 'v2' });
  });

  it('가게 정보 저장 뒤 미리보기를 다시 부른다 (B4)', async () => {
    stubFetch(async (url, init) => {
      if (url.includes('/card/preview')) return okJson(PREVIEW);
      if (url.includes('/features')) return okJson({ variant: 'v1', features: FEATURES });
      if (init?.method === 'PUT') return okJson(CARD);
      return okJson(CARD);
    });
    render(<BuilderPage roomId="r1" />);
    await screen.findByTitle('사이트 미리보기');
    const before = callsTo('/card/preview').length;
    fireEvent.click(screen.getByRole('button', { name: '가게 정보 입력' }));
    fireEvent.change(screen.getByLabelText('가게 이름'), { target: { value: '모퉁이 커피' } });
    fireEvent.click(screen.getByRole('button', { name: '저장' }));
    await waitFor(() => expect(callsTo('/card/preview').length).toBe(before + 1));
  });

  it('공개 need=login이면 로그인 버튼 2개를 보인다', async () => {
    stubFetch(async (url) => {
      if (url.includes('/card/preview')) return okJson(PREVIEW);
      if (url.includes('/features')) return okJson({ variant: 'v1', features: FEATURES });
      if (url.includes('/publish')) {
        return okJson({
          need: 'login',
          message: '로그인하고 공개해요.',
          login_urls: ['/auth/kakao/start?next=/start?room=r1', '/auth/google/start?next=/start?room=r1'],
        });
      }
      return okJson(CARD);
    });
    render(<BuilderPage roomId="r1" />);
    await screen.findByTitle('사이트 미리보기');
    fireEvent.click(screen.getByRole('button', { name: '공개하기' }));
    expect(await screen.findByText('로그인하고 공개해요.')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '카카오로 계속하기' }).getAttribute('href')).toContain('/auth/kakao/start');
    expect(screen.getByRole('link', { name: '구글로 계속하기' }).getAttribute('href')).toContain('/auth/google/start');
  });

  it('공개 need=confirm이면 그대로 공개로 다시 보낸다', async () => {
    const posts: unknown[] = [];
    stubFetch(async (url, init) => {
      if (url.includes('/card/preview')) return okJson(PREVIEW);
      if (url.includes('/features')) return okJson({ variant: 'v1', features: FEATURES });
      if (url.includes('/publish')) {
        posts.push(JSON.parse(String(init?.body)));
        if (posts.length === 1) return okJson({ need: 'confirm', message: '전화가 비었어요. 그래도 공개할까요?' });
        return okJson({ ok: true, site_url: 'https://example.com/s1' });
      }
      return okJson(CARD);
    });
    render(<BuilderPage roomId="r1" />);
    await screen.findByTitle('사이트 미리보기');
    fireEvent.click(screen.getByRole('button', { name: '공개하기' }));
    fireEvent.click(await screen.findByRole('button', { name: '그대로 공개' }));
    await waitFor(() => expect(posts).toHaveLength(2));
    expect(posts[1]).toEqual({ force: true });
    expect(await screen.findByRole('link', { name: '공개 사이트 보기' })).toBeInTheDocument();
  });

  it('말로 고치기 입력은 빈 말풍선 없이 켜져 있다', async () => {
    stubFetch(async (url) => {
      if (url.includes('/card/preview')) return okJson(PREVIEW);
      if (url.includes('/features')) return okJson({ variant: 'v1', features: FEATURES });
      return okJson(CARD);
    });
    render(<BuilderPage roomId="r1" />);
    const say = (await screen.findByLabelText('말로 고치기')) as HTMLInputElement;
    expect(say.disabled).toBe(false);
    expect(say.maxLength).toBe(300);
    expect(screen.queryByLabelText('고치기 답')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '되돌리기' })).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: '채팅으로 설명하기' }).getAttribute('href')).toBe('/room.html?room=r1');
  });

  it('사진 누름(img:true+src)은 사진 시트를 연다', async () => {
    stubFetch(async (url) => {
      if (url.includes('/card/preview')) return okJson(PREVIEW);
      if (url.includes('/photo-edit/target')) return okJson(PHOTO_TARGET);
      if (url.includes('/features')) return okJson({ variant: 'v1', features: FEATURES });
      return okJson(CARD);
    });
    render(<BuilderPage roomId="r1" />);
    const frame = (await screen.findByTitle('사이트 미리보기')) as HTMLIFrameElement;
    sendFrameMessage(frame.contentWindow, {
      type: 'agt-edit',
      section: 'hero',
      text: '',
      img: true,
      src: 'http://x/a.jpg',
      index: 0,
    });
    expect(await screen.findByRole('dialog', { name: '사진 고치기' })).toBeInTheDocument();
    await waitFor(() => expect(callsTo('/photo-edit/target')).toHaveLength(1));
    expect(String(callsTo('/photo-edit/target')[0][0])).toContain('section=hero');
    // 구역 패널은 열지 않는다.
    expect(screen.queryByRole('button', { name: '구역 위로' })).not.toBeInTheDocument();
  });

  it('글자 누름은 사진 시트를 열지 않는다', async () => {
    stubFetch(async (url) => {
      if (url.includes('/card/preview')) return okJson(PREVIEW);
      if (url.includes('/photo-edit/target')) return okJson(PHOTO_TARGET);
      if (url.includes('/features')) return okJson({ variant: 'v1', features: FEATURES });
      return okJson(CARD);
    });
    render(<BuilderPage roomId="r1" />);
    const frame = (await screen.findByTitle('사이트 미리보기')) as HTMLIFrameElement;
    sendFrameMessage(frame.contentWindow, { type: 'agt-edit', section: 'menu', text: '아메리카노' });
    // 구역 패널이 열리고 사진 시트는 뜨지 않는다.
    expect(await screen.findByRole('button', { name: '구역 위로' })).toBeInTheDocument();
    expect(screen.queryByRole('dialog', { name: '사진 고치기' })).not.toBeInTheDocument();
    expect(callsTo('/photo-edit/target')).toHaveLength(0);
  });

  it('사진 있는 구역 글자 누름은 구역 패널에 사진 고치기를 보이고 누르면 사진 시트를 연다', async () => {
    stubFetch(async (url) => {
      if (url.includes('/card/preview')) return okJson(PREVIEW);
      if (url.includes('/photo-edit/target')) return okJson(PHOTO_TARGET);
      if (url.includes('/features')) return okJson({ variant: 'v1', features: FEATURES });
      return okJson(CARD);
    });
    render(<BuilderPage roomId="r1" />);
    const frame = (await screen.findByTitle('사이트 미리보기')) as HTMLIFrameElement;
    sendFrameMessage(frame.contentWindow, {
      type: 'agt-edit',
      section: 'menu',
      text: '아메리카노',
      photo: { src: 'http://x/hero.jpg', index: 0 },
    });
    // 구역 패널은 열리고 사진 시트는 아직 뜨지 않는다.
    expect(await screen.findByRole('button', { name: '구역 위로' })).toBeInTheDocument();
    expect(screen.queryByRole('dialog', { name: '사진 고치기' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '사진 고치기' }));
    expect(await screen.findByRole('dialog', { name: '사진 고치기' })).toBeInTheDocument();
    await waitFor(() => expect(callsTo('/photo-edit/target')).toHaveLength(1));
  });
});
