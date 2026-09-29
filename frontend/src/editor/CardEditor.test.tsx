// 실제 카드 편집 화면 테스트 (fetch 가짜, contracts/ROOM_FEATURES_API.md §5).
import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import CardEditor from './CardEditor';
import EditorPage from './EditorPage';

const CARD = {
  title: '우리 가게',
  industry: '카페',
  fields: [
    { key: 'shop_name', label: '가게 이름', value: '우리 가게', status: 'filled', fact: false, placeholder: false },
    { key: 'phone', label: '전화번호', value: '', status: 'placeholder', fact: true, placeholder: true },
    { key: 'hours', label: '영업시간', value: '매일 09:00~18:00 (가정)', status: 'assumed', fact: true, placeholder: false },
    { key: 'detail', label: '소개', value: '사장님 확인 전', status: 'pending_owner', fact: false, placeholder: false },
  ],
  photos: [{ id: 'p1', url: 'https://example.com/p1.jpg', caption: '앞모습' }],
  choice: 'v2',
  published: null,
  site_url: 'https://example.com/s1',
  can_edit: true,
};

function stubFetch(handler: (url: string, init?: RequestInit) => Promise<unknown>) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => handler(url, init)),
  );
}

function okCard(card: unknown) {
  return { ok: true, status: 200, json: async () => card } as Response;
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

describe('CardEditor', () => {
  it('실제 카드를 불러와 칸·배지·사진·링크를 보여준다', async () => {
    stubFetch(async (url) => {
      expect(url).toBe('/api/rooms/r1/card');
      return okCard(CARD);
    });
    render(<CardEditor roomId="r1" />);
    expect(await screen.findByText('우리 가게')).toBeInTheDocument();
    // 상태 배지 3종
    expect(screen.getByText('입력 필요')).toBeInTheDocument();
    expect(screen.getByText('가정')).toBeInTheDocument();
    expect(screen.getByText('확인 대기')).toBeInTheDocument();
    // 사실 칸 표시
    expect(screen.getAllByText(/사실/).length).toBeGreaterThan(0);
    // 사진 썸네일(읽기만)
    expect(screen.getByAltText('앞모습')).toBeInTheDocument();
    // 공개 사이트 링크와 채팅방 돌아가기 링크
    expect(screen.getByRole('link', { name: '공개 사이트 보기' }).getAttribute('href')).toBe('https://example.com/s1');
    expect(screen.getByRole('link', { name: '채팅방으로 돌아가기' }).getAttribute('href')).toBe('/room.html?room=r1');
    // 공개 전에는 채팅방의 공개하기로 돌아가는 큰 링크 (EDIT_PUBLISH_PLAN §4-7)
    expect(screen.getByRole('link', { name: /채팅방에서 공개하기/ }).getAttribute('href')).toBe('/room.html?room=r1');
    // X-Member-Id 헤더를 보낸다
    const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
    const headers = fetchMock.mock.calls[0][1]?.headers as Record<string, string>;
    expect(headers['X-Member-Id']).toBe('m1');
  });

  it('방장이 아니면 읽기 전용으로 보여준다', async () => {
    stubFetch(async () => okCard({ ...CARD, can_edit: false }));
    render(<CardEditor roomId="r1" />);
    expect(await screen.findByText('방장만 고칠 수 있어요. 내용은 볼 수 있어요.')).toBeInTheDocument();
    const input = (await screen.findByLabelText(/전화번호/)) as HTMLInputElement;
    expect(input.readOnly || input.disabled).toBe(true);
    expect(screen.queryByRole('button', { name: /바뀐 칸 저장/ })).not.toBeInTheDocument();
  });

  it('바뀐 칸만 PUT {"fields": {...}}로 보내고 성공을 알린다', async () => {
    const puts: Array<{ url: string; body: unknown }> = [];
    stubFetch(async (url, init) => {
      if (init?.method === 'PUT') {
        puts.push({ url, body: JSON.parse(String(init.body)) });
        return okCard({ ...CARD, published: 'v2', fields: [{ ...CARD.fields[0], value: '바꾼 이름' }, ...CARD.fields.slice(1)] });
      }
      return okCard(CARD);
    });
    render(<CardEditor roomId="r1" />);
    const nameInput = await screen.findByLabelText('가게 이름');
    fireEvent.change(nameInput, { target: { value: '바꾼 이름' } });
    fireEvent.click(screen.getByRole('button', { name: /바뀐 칸 저장/ }));
    await waitFor(() => expect(puts).toHaveLength(1));
    expect(puts[0].url).toBe('/api/rooms/r1/card');
    expect(puts[0].body).toEqual({ fields: { shop_name: '바꾼 이름' } });
    expect(await screen.findByText('저장했어요. 사이트에도 반영했어요.')).toBeInTheDocument();
  });

  it('빈 값 저장은 화면 안 대화상자로 "입력 필요로 돌아가요"를 묻는다', async () => {
    const puts: unknown[] = [];
    stubFetch(async (_url, init) => {
      if (init?.method === 'PUT') {
        puts.push(JSON.parse(String(init.body)));
        return okCard(CARD);
      }
      return okCard(CARD);
    });
    const confirmSpy = vi.spyOn(window, 'confirm');
    render(<CardEditor roomId="r1" />);
    const hoursInput = await screen.findByLabelText(/영업시간/);
    fireEvent.change(hoursInput, { target: { value: '' } });
    fireEvent.click(screen.getByRole('button', { name: /바뀐 칸 저장/ }));
    // 화면 안 대화상자 (window.confirm 사용 안 함)
    expect(await screen.findByRole('dialog', { name: '빈 값 저장 확인' })).toBeInTheDocument();
    expect(screen.getByText(/입력 필요로 돌아가요/)).toBeInTheDocument();
    expect(puts).toHaveLength(0);
    expect(confirmSpy).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: '입력 필요로 저장' }));
    await waitFor(() => expect(puts).toHaveLength(1));
    confirmSpy.mockRestore();
  });

  it('저장 실패를 알린다', async () => {
    stubFetch(async (_url, init) => {
      if (init?.method === 'PUT') return { ok: false, status: 500, json: async () => ({}) } as Response;
      return okCard(CARD);
    });
    render(<CardEditor roomId="r1" />);
    const nameInput = await screen.findByLabelText('가게 이름');
    fireEvent.change(nameInput, { target: { value: '바꾼 이름' } });
    fireEvent.click(screen.getByRole('button', { name: /바뀐 칸 저장/ }));
    expect(await screen.findByRole('alert')).toHaveTextContent('저장하지 못했어요');
  });

  it('room이 없으면 목업(예시 화면)으로 보여준다', () => {
    render(<EditorPage />);
    expect(screen.getByText(/예시 화면/)).toBeInTheDocument();
    expect(screen.getByText(/공개 전에 채울 곳 \d+개/)).toBeInTheDocument();
  });

  it('불러오기 실패하면 로그인 안내를 보여준다', async () => {
    stubFetch(async () => ({ ok: false, status: 404, json: async () => ({}) }) as Response);
    render(<EditorPage roomId="nope" />);
    expect(await screen.findByText('이 기기에서는 사이트를 고칠 수 없어요')).toBeInTheDocument();
    expect(screen.getByText('방을 만든 기기에서 열거나, 방을 만든 계정으로 로그인해 주세요.')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '카카오로 로그인' }).getAttribute('href')).toContain(
      '/auth/kakao/start?next=%2Feditor%3Froom%3Dnope',
    );
    expect(screen.getByRole('link', { name: '구글로 로그인' }).getAttribute('href')).toContain(
      '/auth/google/start?next=%2Feditor%3Froom%3Dnope',
    );
    expect(screen.getByRole('link', { name: '채팅방으로 가기' }).getAttribute('href')).toBe('/room.html?room=nope');
  });
});
