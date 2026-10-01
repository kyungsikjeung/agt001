// 그룹 + 카드 추가 (GROUP_CARDS_CONTRACT §5 6번, fetch 가짜).
import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import SiteEditor from './SiteEditor';
import { buildGroupsOp, buildItemOps, initDrafts } from './ItemList';
import type { PreviewItem, RoomCard } from './cardApi';

const BASE: PreviewItem[] = [
  { name: '아메리카노', price: '4,500원', note: '', group: '커피', photo: 'own' },
  { name: '카페라떼', price: '5,000원', note: '', group: '커피', photo: 'auto' },
  { name: '치즈케이크', price: '6,000원', note: '', group: '디저트', photo: 'auto' },
];
const NAMES = BASE.map((b) => b.name);

describe('저장 본문 만들기', () => {
  it('그대로면 아무것도 안 보낸다', () => {
    const { items, groups } = initDrafts(NAMES, BASE, ['커피', '디저트']);
    expect(buildGroupsOp(groups, ['커피', '디저트'])).toBeNull();
    expect(buildItemOps(items, groups, NAMES, BASE)).toEqual([]);
  });

  it('그룹 순서·이름 바꾸기와 지우기', () => {
    const { groups } = initDrafts(NAMES, BASE, ['커피', '디저트']);
    expect(buildGroupsOp([groups[1], groups[0]], ['커피', '디저트'])).toEqual({ order: ['디저트', '커피'] });
    const renamed = [{ ...groups[0], name: '에스프레소바' }, groups[1]];
    expect(buildGroupsOp(renamed, ['커피', '디저트'])).toEqual({
      order: ['에스프레소바', '디저트'],
      rename: { 커피: '에스프레소바' },
    });
    expect(buildGroupsOp([groups[1]], ['커피', '디저트'])).toEqual({ order: ['디저트'] });
  });

  it('그룹 이름만 바꾸면 항목 줄은 안 보내고, 옮기기·사진 없음·새 항목은 보낸다', () => {
    const { items, groups } = initDrafts(NAMES, BASE, ['커피', '디저트']);
    const g = [{ ...groups[0], name: '에스프레소바' }, groups[1]];
    expect(buildItemOps(items, g, NAMES, BASE)).toEqual([]);
    const next = [
      { ...items[0], photo: 'none' as const, touched: true },
      { ...items[1], group: groups[1].key, touched: true },
      items[2],
      { key: 99, prevName: '호박라떼', name: '호박라떼', price: '', note: '', group: groups[1].key,
        photo: 'none' as const, hasOwn: false, touched: true },
    ];
    expect(buildItemOps(next, g, NAMES, BASE)).toEqual([
      { name: '아메리카노', photo: 'none' },
      { name: '카페라떼', group: '디저트' },
      { name: '호박라떼', add: true, group: '디저트', photo: 'none' },
    ]);
    // 내 사진 → 사진 없음 → 내 사진은 처음과 같아서 안 보낸다
    expect(buildItemOps([{ ...items[0], photo: 'own', touched: true }], groups, ['아메리카노'], BASE)).toEqual([]);
  });
});

const CARD: RoomCard = {
  title: '우리 가게',
  industry: '카페',
  fields: [
    { key: 'shop_name', label: '가게 이름', value: '우리 가게', status: 'filled', fact: false, placeholder: false },
    { key: 'offerings', label: '메뉴', value: NAMES.join(', '), status: 'filled', fact: false, placeholder: false },
  ],
  photos: [],
  choice: 'v1',
  published: null,
  site_url: null,
  can_edit: true,
};

const PREVIEW = {
  variant: 'v1',
  html: '<!doctype html><html><body><section data-section-id="menu">메뉴</section></body></html>',
  sections: [{ id: 'menu', label: '메뉴', bind: 'catalog', locked: false, hidden: false }],
  addable: [],
  layout: {},
  items: BASE,
  groups: ['커피', '디저트'],
};

function stubFetch(handler: (url: string, init?: RequestInit) => Promise<unknown>) {
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => handler(url, init)));
}

function okJson(data: unknown) {
  return { ok: true, status: 200, json: async () => data } as Response;
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

async function openMenuPanel(puts: unknown[]) {
  stubFetch(async (url, init) => {
    if (url.includes('/card/preview')) return okJson(PREVIEW);
    if (init?.method === 'PUT') puts.push(JSON.parse(String(init.body)));
    return okJson(CARD);
  });
  render(<SiteEditor roomId="r1" card={CARD} onSaved={() => {}} />);
  const frame = (await screen.findByTitle('사이트 미리보기')) as HTMLIFrameElement;
  const evt = new MessageEvent('message', { data: { type: 'agt-edit', section: 'menu', text: '' } });
  Object.defineProperty(evt, 'source', { value: frame.contentWindow });
  window.dispatchEvent(evt);
  return screen.findByRole('region', { name: '커피 그룹' });
}

describe('그룹 묶음 화면', () => {
  it('보이는 그룹 그대로 열고, 그룹 추가 → 그 그룹에 항목 → 이름 바꾸기 → 저장', async () => {
    const puts: unknown[] = [];
    const coffee = await openMenuPanel(puts);
    expect(within(coffee).getByRole('button', { name: /커피 2개/ })).toBeInTheDocument();
    expect(screen.getByRole('region', { name: '디저트 그룹' })).toBeInTheDocument();
    // 그룹 추가
    fireEvent.change(screen.getByLabelText('새 그룹 이름'), { target: { value: '시즌' } });
    fireEvent.click(screen.getByRole('button', { name: '+ 그룹 추가' }));
    const season = screen.getByRole('region', { name: '시즌 그룹' });
    fireEvent.change(within(season).getByLabelText('시즌에 새 항목'), { target: { value: '호박라떼' } });
    fireEvent.click(within(season).getByRole('button', { name: '더하기' }));
    expect(within(season).getByRole('button', { name: '호박라떼' })).toBeInTheDocument();
    // 커피 그룹 이름 바꾸기
    fireEvent.click(within(coffee).getByRole('button', { name: /커피 2개/ }));
    fireEvent.change(within(coffee).getByLabelText('그룹 이름'), { target: { value: '에스프레소바' } });
    fireEvent.click(screen.getByRole('button', { name: '저장' }));
    await waitFor(() => expect(puts).toHaveLength(1));
    expect(puts[0]).toMatchObject({
      groups: { order: ['에스프레소바', '디저트', '시즌'], rename: { 커피: '에스프레소바' } },
      items: [{ name: '호박라떼', add: true, group: '시즌' }],
    });
  });

  it('그룹 지우기는 한 번 더 묻고, 안의 항목은 첫 그룹으로 간다', async () => {
    const puts: unknown[] = [];
    await openMenuPanel(puts);
    const dessert = screen.getByRole('region', { name: '디저트 그룹' });
    fireEvent.click(within(dessert).getByRole('button', { name: /디저트 1개/ }));
    fireEvent.click(within(dessert).getByRole('button', { name: '그룹 지우기' }));
    expect(within(dessert).getByText('안의 항목은 첫 그룹으로 가요. 지울까요?')).toBeInTheDocument();
    fireEvent.click(within(dessert).getByRole('button', { name: '지우기' }));
    expect(screen.queryByRole('region', { name: '디저트 그룹' })).toBeNull();
    expect(within(screen.getByRole('region', { name: '커피 그룹' })).getByRole('button', { name: '치즈케이크' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '저장' }));
    await waitFor(() => expect(puts).toHaveLength(1));
    expect(puts[0]).toMatchObject({ groups: { order: ['커피'] } });
  });

  it('같은 이름 그룹은 더하지 않고 알린다, 사진 없음 고르기는 저장 본문에', async () => {
    const puts: unknown[] = [];
    await openMenuPanel(puts);
    fireEvent.change(screen.getByLabelText('새 그룹 이름'), { target: { value: '커피' } });
    fireEvent.click(screen.getByRole('button', { name: '+ 그룹 추가' }));
    expect(screen.getByRole('alert')).toHaveTextContent('같은 이름의 그룹이 있어요');
    fireEvent.click(screen.getByRole('button', { name: '카페라떼' }));
    expect(screen.getByRole('radio', { name: '예시 사진' })).toBeChecked();
    fireEvent.click(screen.getByRole('radio', { name: '사진 없음' }));
    fireEvent.click(screen.getByRole('button', { name: '저장' }));
    await waitFor(() => expect(puts).toHaveLength(1));
    expect(puts[0]).toMatchObject({ items: [{ name: '카페라떼', photo: 'none' }] });
    expect((puts[0] as { groups?: unknown }).groups).toBeUndefined();
  });
});
