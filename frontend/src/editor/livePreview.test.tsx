// 실시간 미리보기 테스트 (COMPONENT_ENGINE_PLAN §5·§6, fetch·iframe 창 가짜).
import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import SiteEditor from './SiteEditor';
import type { CardPreview, RoomCard } from './cardApi';
import { extractParts, frameStateOf, planUpdate, styleAttrs } from './livePatch';

const CARD: RoomCard = {
  title: '우리 가게',
  industry: '카페',
  fields: [
    { key: 'shop_name', label: '가게 이름', value: '우리 가게', status: 'filled', fact: false, placeholder: false },
    { key: 'detail', label: '소개', value: '맛있는 커피', status: 'filled', fact: false, placeholder: false },
    { key: 'hours', label: '영업시간', value: '매일', status: 'filled', fact: true, placeholder: false },
    { key: 'location', label: '위치', value: '앞골목', status: 'filled', fact: true, placeholder: false },
  ],
  photos: [],
  choice: 'v1',
  published: null,
  site_url: null,
  can_edit: true,
};

const STYLES = {
  surface: { default: 'soft', values: { soft: '부드러운 그림자', outline: '얇은 선', flat: '옅은 면', lifted: '떠 있는 카드' } },
  heading: { default: 'bar', values: { bar: '짧은 밑줄', eyebrow: '작은 윗글', center: '가운데 정렬', display: '큰 제목' } },
};
const THEME = { css: ':root{--c-primary:#111}', motion: '', attrs: {}, axes: ['data-surface', 'data-heading'] };

function doc(hero: string, space = '<ul class="s-gallery__list"></ul>') {
  return (
    '<!doctype html><html><body>' +
    `<section class="s-hero" data-section-id="hero"><h1>${hero}</h1></section>\n` +
    `<section class="s-gallery s-gallery--grid" data-section-id="space">${space}</section>` +
    '</body></html>'
  );
}

function preview(hero: string, heroHash: string, extra: Partial<CardPreview> = {}): CardPreview {
  return {
    variant: 'v1',
    html: doc(hero),
    sections: [
      { id: 'hero', label: '첫 화면', bind: 'hero', locked: true, hidden: false, variant: 'photo-overlay', base_variant: 'photo-overlay', shapes: [] },
      {
        id: 'space',
        label: '사진첩',
        bind: 'space_photos',
        locked: false,
        hidden: false,
        variant: 'grid',
        base_variant: 'grid',
        shapes: [
          { variant: 'grid', name: '격자', desc: '같은 크기', new: false },
          { variant: 'masonry', name: '벽돌 쌓기', desc: '엇갈려 쌓기', new: true },
        ],
      },
    ],
    addable: [],
    layout: {},
    items: [],
    shell: 'S1',
    order: ['hero', 'space'],
    theme: THEME,
    parts: [
      { id: 'hero', hash: heroHash },
      { id: 'space', hash: 'g1' },
    ],
    style: {},
    styles: STYLES,
    ...extra,
  };
}

function okJson(data: unknown) {
  return { ok: true, status: 200, json: async () => data } as Response;
}

function calls(part: string, method?: string) {
  const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
  return fetchMock.mock.calls.filter(
    (c) => String(c[0]).includes(part) && (method ? (c[1] as RequestInit | undefined)?.method === method : true),
  );
}

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
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('livePatch (순수 계산)', () => {
  it('문서에서 구역 뿌리 HTML을 꺼낸다', () => {
    const got = extractParts(doc('가게'), ['space']);
    expect(Object.keys(got)).toEqual(['space']);
    expect(got.space).toContain('data-section-id="space"');
  });

  it('뼈대가 같으면 바뀐 구역만, 다르거나 예전 서버면 통째로', () => {
    const frame = frameStateOf(preview('가게', 'h1'));
    const plan = planUpdate(frame, preview('새 가게', 'h2'));
    expect(plan.kind).toBe('patch');
    if (plan.kind === 'patch') {
      expect(plan.parts.map((p) => p.id)).toEqual(['hero']);
      expect(plan.parts[0].html).toContain('새 가게');
      expect(plan.theme).toBeNull();
    }
    expect(planUpdate(frame, preview('가게', 'h1', { shell: 'S2' })).kind).toBe('full');
    expect(planUpdate(frame, { ...preview('가게', 'h1'), shell: undefined }).kind).toBe('full');
    expect(planUpdate(null, preview('가게', 'h1')).kind).toBe('full');
    const recolor = planUpdate(frame, preview('가게', 'h1', { theme: { ...THEME, css: ':root{--c-primary:#222}' } }));
    expect(recolor.kind === 'patch' && recolor.parts.length === 0 && recolor.theme?.css).toBe(':root{--c-primary:#222}');
  });

  it('스타일 축 속성: 기본값·모르는 값은 뺀다', () => {
    expect(styleAttrs(STYLES, { surface: 'outline', heading: 'bar' })).toEqual({ 'data-surface': 'outline' });
    expect(styleAttrs(STYLES, { surface: 'nope' })).toEqual({});
  });
});

describe('SiteEditor 실시간 미리보기', () => {
  function setup(handler: (url: string, init?: RequestInit) => unknown) {
    const post = vi.fn();
    vi.spyOn(HTMLIFrameElement.prototype, 'contentWindow', 'get').mockReturnValue({ postMessage: post } as unknown as Window);
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string, init?: RequestInit) => okJson(handler(url, init))),
    );
    return post;
  }

  it('저장 뒤 바뀐 구역만 바꿔 끼운다: iframe 문서는 그대로(새로 불러오지 않음)', async () => {
    let n = 0;
    const post = setup((url, init) => {
      if (url.includes('/card/preview')) {
        n += 1;
        return n === 1 ? preview('우리 가게', 'h1') : preview('새 가게', 'h2');
      }
      if (init?.method === 'PUT') return CARD;
      return CARD;
    });
    render(<SiteEditor roomId="r1" card={CARD} onSaved={() => {}} />);
    const frame = (await screen.findByTitle('사이트 미리보기')) as HTMLIFrameElement;
    const before = frame.getAttribute('srcdoc');
    sendFrameMessage(frame.contentWindow, { type: 'agt-edit', section: 'hero', text: '' });
    const name = await screen.findByLabelText('가게 이름');
    fireEvent.change(name, { target: { value: '새 가게' } });
    fireEvent.click(screen.getByRole('button', { name: '저장' }));
    await waitFor(() => expect(post.mock.calls.some((c) => c[0]?.type === 'agt-patch')).toBe(true));
    const patch = post.mock.calls.find((c) => c[0]?.type === 'agt-patch')?.[0];
    expect(patch.parts.map((p: { id: string }) => p.id)).toEqual(['hero']);
    expect(patch.parts[0].html).toContain('새 가게');
    expect(patch.focus).toBe('hero');
    expect(screen.getByTitle('사이트 미리보기').getAttribute('srcdoc')).toBe(before);
  });

  it('칸을 고치는 중에는 잠깐 뒤 저장 없이 미리 그려 바꿔 끼운다', async () => {
    const post = setup((url) => {
      if (url.includes('/preview/draft')) {
        return { variant: 'v1', shell: 'S1', order: ['hero', 'space'], theme: THEME,
          parts: [{ id: 'hero', hash: 'h9', html: '<section data-section-id="hero"><h1>고치는 중</h1></section>' }, { id: 'space', hash: 'g1' }] };
      }
      if (url.includes('/card/preview')) return preview('우리 가게', 'h1');
      return CARD;
    });
    render(<SiteEditor roomId="r1" card={CARD} onSaved={() => {}} />);
    const frame = (await screen.findByTitle('사이트 미리보기')) as HTMLIFrameElement;
    sendFrameMessage(frame.contentWindow, { type: 'agt-edit', section: 'hero', text: '' });
    fireEvent.change(await screen.findByLabelText('가게 이름'), { target: { value: '고치는 중' } });
    await waitFor(() => expect(calls('/preview/draft', 'POST')).toHaveLength(1), { timeout: 2000 });
    const body = JSON.parse(String((calls('/preview/draft', 'POST')[0][1] as RequestInit).body));
    expect(body).toMatchObject({ variant: 'v1', fields: { shop_name: '고치는 중' }, have: { hero: 'h1', space: 'g1' }, shell: 'S1' });
    await waitFor(() => expect(post.mock.calls.some((c) => c[0]?.type === 'agt-patch')).toBe(true));
    const patch = post.mock.calls.find((c) => c[0]?.type === 'agt-patch')?.[0];
    expect(patch.parts).toEqual([{ id: 'hero', html: '<section data-section-id="hero"><h1>고치는 중</h1></section>' }]);
    expect(calls('/card', 'PUT')).toHaveLength(0); // 저장하지 않는다
  });

  it('스타일을 고르면 바로 토큰 속성을 바꾸고 뒤에서 저장한다', async () => {
    const post = setup((url) => {
      if (url.includes('/card/preview')) return preview('우리 가게', 'h1');
      return CARD;
    });
    render(<SiteEditor roomId="r1" card={CARD} onSaved={() => {}} />);
    await screen.findByTitle('사이트 미리보기');
    fireEvent.click(screen.getByText('스타일'));
    fireEvent.click(screen.getByRole('button', { name: '얇은 선' }));
    const theme = post.mock.calls.find((c) => c[0]?.type === 'agt-theme')?.[0];
    expect(theme.attrs).toEqual({ 'data-surface': 'outline' });
    expect(theme.axes).toEqual(['data-surface', 'data-heading']);
    await waitFor(() => expect(calls('/card', 'PUT')).toHaveLength(1));
    const body = JSON.parse(String((calls('/card', 'PUT')[0][1] as RequestInit).body));
    expect(body.style).toEqual({ variant: 'v1', surface: 'outline', heading: undefined });
  });

  it('구역 모양을 고르면 미리 그린 뒤 구역별 모양으로 저장한다', async () => {
    setup((url) => {
      if (url.includes('/preview/draft')) return { variant: 'v1', shell: 'S1', order: ['hero', 'space'], theme: THEME, parts: [] };
      if (url.includes('/card/preview')) return preview('우리 가게', 'h1');
      return CARD;
    });
    render(<SiteEditor roomId="r1" card={CARD} onSaved={() => {}} />);
    const frame = (await screen.findByTitle('사이트 미리보기')) as HTMLIFrameElement;
    sendFrameMessage(frame.contentWindow, { type: 'agt-edit', section: 'space', text: '' });
    const shape = await screen.findByRole('button', { name: /벽돌 쌓기/ });
    expect(screen.getByRole('button', { name: /격자/ })).toHaveAttribute('aria-pressed', 'true');
    expect(shape).toHaveTextContent('새');
    fireEvent.click(shape);
    await waitFor(() => expect(calls('/card', 'PUT')).toHaveLength(1));
    const draft = JSON.parse(String((calls('/preview/draft', 'POST')[0][1] as RequestInit).body));
    expect(draft.layout.variants).toEqual({ space: 'masonry' });
    const put = JSON.parse(String((calls('/card', 'PUT')[0][1] as RequestInit).body));
    expect(put.layout).toMatchObject({ variant: 'v1', order: ['hero', 'space'], variants: { space: 'masonry' } });
  });
});
