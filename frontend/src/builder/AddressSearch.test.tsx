// 주소 검색 시트 테스트 (MAP_CONTRACT §6 6번, fetch·우편번호 가짜).
import '@testing-library/jest-dom/vitest';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import AddressSearch from './AddressSearch';

const CARD = {
  title: '우리 가게',
  industry: null,
  fields: [],
  photos: [],
  choice: 'v1',
  published: null,
  site_url: null,
  can_edit: true,
};

type Complete = (d: { roadAddress: string; jibunAddress: string }) => void;

let completeCb: Complete | null = null;
let embedded = 0;

/** 우편번호 창 가짜. 고른 주소는 completeCb로 넘긴다. */
function stubPostcode() {
  completeCb = null;
  embedded = 0;
  (window as unknown as { daum: unknown }).daum = {
    Postcode: function (opts: { oncomplete: Complete }) {
      completeCb = opts.oncomplete;
      return { embed: () => { embedded += 1; } };
    },
  };
}

function stubFetch(handler: (url: string, init?: RequestInit) => Promise<unknown>) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => handler(url, init)),
  );
}

function okJson(data: unknown) {
  return { ok: true, status: 200, json: async () => data } as Response;
}

function postcodeScripts(): HTMLScriptElement[] {
  return [...document.head.querySelectorAll('script[src*="postcode"]')] as HTMLScriptElement[];
}

beforeEach(() => {
  localStorage.clear();
  localStorage.setItem('agt001_member_id', 'm1');
  postcodeScripts().forEach((s) => s.remove());
  delete (window as unknown as { daum?: unknown }).daum;
  completeCb = null;
  embedded = 0;
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('AddressSearch', () => {
  it('단추를 누르기 전에는 스크립트를 안 받고, 눌 때 한 번만 받는다', async () => {
    stubPostcode();
    stubFetch(async () => okJson(CARD));
    render(<AddressSearch roomId="r1" onSaved={() => {}} />);
    expect(postcodeScripts()).toHaveLength(0);
    fireEvent.click(screen.getByRole('button', { name: '주소 검색' }));
    expect(await screen.findByRole('dialog', { name: '주소 검색' })).toBeInTheDocument();
    expect(postcodeScripts()).toHaveLength(1);
    fireEvent.click(screen.getByRole('button', { name: '닫기' }));
    expect(screen.queryByRole('dialog', { name: '주소 검색' })).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: '주소 검색' }));
    expect(await screen.findByRole('dialog', { name: '주소 검색' })).toBeInTheDocument();
    expect(postcodeScripts()).toHaveLength(1);
  });

  it('고르면 도로명+상세 주소로 PUT /geo에 저장한다 (이름·전화 없음)', async () => {
    stubPostcode();
    const sent: { url: string; body?: unknown }[] = [];
    stubFetch(async (url, init) => {
      if (url.includes('/geo/search')) return okJson({ candidates: [{ road: '서울 마포구 연남로 35', jibun: '연남동 123', x: 126.9, y: 37.5 }] });
      if (url.includes('/geo') && init?.method === 'PUT') {
        sent.push({ url, body: JSON.parse(String(init.body)) });
        return okJson(CARD);
      }
      throw new Error(`몰라요: ${url}`);
    });
    const onSaved = vi.fn();
    render(<AddressSearch roomId="r1" onSaved={onSaved} />);
    fireEvent.click(screen.getByRole('button', { name: '주소 검색' }));
    await waitFor(() => expect(embedded).toBe(1));
    await act(async () => {
      completeCb?.({ roadAddress: '서울 마포구 연남로 35', jibunAddress: '연남동 123' });
    });
    expect(await screen.findByText('고른 주소: 서울 마포구 연남로 35')).toBeInTheDocument();
    fireEvent.change(screen.getByPlaceholderText('예: 2층 201호'), { target: { value: '2층 201호' } });
    fireEvent.click(screen.getByRole('button', { name: '저장' }));
    await waitFor(() => expect(sent).toHaveLength(1));
    expect(sent[0].body).toEqual({
      road: '서울 마포구 연남로 35',
      jibun: '연남동 123',
      detail: '2층 201호',
      x: 126.9,
      y: 37.5,
      src: 'postcode',
    });
    // 검색에는 주소 말만 간다.
    const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
    const searchUrl = String(fetchMock.mock.calls.find((c) => String(c[0]).includes('/geo/search'))?.[0] ?? '');
    expect(searchUrl).toContain(encodeURIComponent('서울 마포구 연남로 35'));
    expect(searchUrl).not.toContain('010');
    expect(onSaved).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole('dialog', { name: '주소 검색' })).toBeNull();
  });

  it('후보가 없으면 묻고 주소 글자만 PUT /card에 저장한다', async () => {
    stubPostcode();
    const puts: unknown[] = [];
    stubFetch(async (url, init) => {
      if (url.includes('/geo/search')) return okJson({ candidates: [] });
      if (url.includes('/card') && init?.method === 'PUT') {
        puts.push(JSON.parse(String(init.body)));
        return okJson(CARD);
      }
      throw new Error(`몰라요: ${url}`);
    });
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    const onSaved = vi.fn();
    render(<AddressSearch roomId="r1" onSaved={onSaved} />);
    fireEvent.click(screen.getByRole('button', { name: '주소 검색' }));
    await waitFor(() => expect(embedded).toBe(1));
    await act(async () => {
      completeCb?.({ roadAddress: '서울 마포구 연남로 35', jibunAddress: '연남동 123' });
    });
    fireEvent.change(await screen.findByPlaceholderText('예: 2층 201호'), { target: { value: '3층' } });
    fireEvent.click(screen.getByRole('button', { name: '저장' }));
    await waitFor(() => expect(confirmSpy).toHaveBeenCalledWith('지도 위치를 찾지 못했어요. 주소만 저장할까요?'));
    await waitFor(() => expect(puts).toHaveLength(1));
    expect(puts[0]).toEqual({ fields: { location: '서울 마포구 연남로 35 3층' } });
    expect(onSaved).toHaveBeenCalledTimes(1);
  });

  it('후보가 없고 거절하면 저장하지 않는다', async () => {
    stubPostcode();
    stubFetch(async (url) => {
      if (url.includes('/geo/search')) return okJson({ candidates: [] });
      throw new Error(`몰라요: ${url}`);
    });
    vi.spyOn(window, 'confirm').mockReturnValue(false);
    const onSaved = vi.fn();
    render(<AddressSearch roomId="r1" onSaved={onSaved} />);
    fireEvent.click(screen.getByRole('button', { name: '주소 검색' }));
    await waitFor(() => expect(embedded).toBe(1));
    await act(async () => {
      completeCb?.({ roadAddress: '서울 마포구 연남로 35', jibunAddress: '연남동 123' });
    });
    fireEvent.click(await screen.findByRole('button', { name: '저장' }));
    await waitFor(() => expect(window.confirm).toHaveBeenCalled());
    await new Promise((r) => setTimeout(r, 30));
    expect(onSaved).not.toHaveBeenCalled();
    expect(screen.getByRole('dialog', { name: '주소 검색' })).toBeInTheDocument();
  });

  it('Esc로 닫힌다', async () => {
    stubPostcode();
    stubFetch(async () => okJson(CARD));
    render(<AddressSearch roomId="r1" onSaved={() => {}} />);
    fireEvent.click(screen.getByRole('button', { name: '주소 검색' }));
    expect(await screen.findByRole('dialog', { name: '주소 검색' })).toBeInTheDocument();
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(screen.queryByRole('dialog', { name: '주소 검색' })).toBeNull();
  });
});
