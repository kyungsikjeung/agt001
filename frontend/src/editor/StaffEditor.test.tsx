// 선생님 고치기 칸 테스트 (BUILDER_FIX_1003_CONTRACT S2, fetch 가짜).
import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { useState } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import StaffEditor from './StaffEditor';
import type { RoomCard, StaffMember } from './cardApi';

const MINJI: StaffMember = {
  name: '김민지',
  role: '선생님',
  subject: '영어',
  tagline: '수능 영어, 해석은 제대로',
  bio: '10년차 영어 선생님입니다.',
  specialties: ['독해', '문법'],
};

function makeCard(staff: StaffMember[] | undefined): RoomCard {
  return {
    title: '우리 학원',
    industry: '학원',
    fields: [],
    photos: [],
    choice: 'v3',
    published: null,
    site_url: null,
    can_edit: true,
    staff,
  };
}

/** 실제 빌더처럼 저장 결과 카드를 다시 내려 주는 부모 (onSaved → setCard). */
function Host({ initial }: { initial: RoomCard }) {
  const [card, setCard] = useState(initial);
  return <StaffEditor roomId="r1" card={card} onSaved={setCard} />;
}

function stubFetch(handler: (url: string, init?: RequestInit) => Promise<unknown>) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => handler(url, init)),
  );
}

function okCard(card: RoomCard) {
  return { ok: true, status: 200, json: async () => card } as Response;
}

function badRequest(detail: string) {
  return new Response(JSON.stringify({ detail }), { status: 400, headers: { 'Content-Type': 'application/json' } });
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

describe('StaffEditor', () => {
  it('빈 카드면 빈 줄 하나로 시작하고, 줄을 더해 고쳐 저장하면 staff 배열로 보낸다', async () => {
    const puts: Record<string, unknown>[] = [];
    const card = makeCard([]);
    stubFetch(async (_url, init) => {
      if (init?.method === 'PUT') {
        puts.push(JSON.parse(String(init.body)));
        return okCard({ ...card, staff: [MINJI] });
      }
      return okCard(card);
    });
    const saved = vi.fn();
    render(<StaffEditor roomId="r1" card={card} onSaved={saved} />);
    // 빈 줄 하나
    expect(screen.getAllByLabelText('이름')).toHaveLength(1);
    fireEvent.click(screen.getByRole('button', { name: '+ 선생님 더하기' }));
    expect(screen.getAllByLabelText('이름')).toHaveLength(2);
    const names = screen.getAllByLabelText('이름');
    fireEvent.change(names[0], { target: { value: '김민지' } });
    fireEvent.change(screen.getAllByLabelText('과목·분야')[0], { target: { value: '영어' } });
    fireEvent.change(screen.getAllByLabelText('전문 분야')[0], { target: { value: '독해, 문법' } });
    fireEvent.click(screen.getByRole('button', { name: '저장' }));
    expect(await screen.findByText('저장했어요.')).toBeInTheDocument();
    expect(puts).toHaveLength(1);
    const staff = puts[0].staff as StaffMember[];
    expect(staff[0]).toMatchObject({ name: '김민지', subject: '영어', specialties: ['독해', '문법'] });
    expect(saved).toHaveBeenCalled();
  });

  it('접힌 줄을 누르면 펼치고 다시 누르면 접는다', () => {
    render(<StaffEditor roomId="r1" card={makeCard([MINJI])} onSaved={() => {}} />);
    const head = screen.getByRole('button', { name: '김민지 · 영어' });
    expect(screen.getByLabelText('이름')).toBeInTheDocument();
    fireEvent.click(head);
    expect(screen.queryByLabelText('이름')).toBeNull();
    fireEvent.click(head);
    expect(screen.getByLabelText('이름')).toBeInTheDocument();
  });

  it('서버가 틀린 곳을 알려 주면 그 말을 보인다', async () => {
    stubFetch(async () => badRequest('같은 이름이 두 번 있어요: 김민지'));
    render(<StaffEditor roomId="r1" card={makeCard([MINJI, { ...MINJI, subject: '수학' }])} onSaved={() => {}} />);
    fireEvent.click(screen.getByRole('button', { name: '저장' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('같은 이름이 두 번 있어요: 김민지');
  });

  it('저장 안 된 이름은 사진 버튼이 막히고 안내가 보인다', () => {
    render(<StaffEditor roomId="r1" card={makeCard([MINJI])} onSaved={() => {}} />);
    fireEvent.click(screen.getByRole('button', { name: '+ 선생님 더하기' }));
    const photoButtons = screen.getAllByRole('button', { name: '사진 올리기' });
    expect(photoButtons).toHaveLength(2);
    // 저장된 김민지는 올릴 수 있고, 빈 새 줄은 막힌다.
    expect(photoButtons[0]).toBeEnabled();
    expect(photoButtons[1]).toBeDisabled();
    expect(screen.getByText('이름을 저장한 뒤 사진을 올릴 수 있어요.')).toBeInTheDocument();
  });

  it('사진을 고르면 staff:이름 꼬리표로 올리고 새 카드를 받아 onSaved한다', async () => {
    const calls: { url: string; init?: RequestInit }[] = [];
    const card = makeCard([MINJI]);
    stubFetch(async (url, init) => {
      calls.push({ url, init });
      if (url.includes('/photos')) return okCard(card);
      return okCard(card);
    });
    const saved = vi.fn();
    const { container } = render(<StaffEditor roomId="r1" card={card} onSaved={saved} />);
    const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement;
    expect(fileInput).not.toBeNull();
    const file = new File(['사진'], 'photo.png', { type: 'image/png' });
    fireEvent.change(fileInput, { target: { files: [file] } });
    expect(await screen.findByText('사진을 올렸어요.')).toBeInTheDocument();
    const photoCall = calls.find((c) => c.url.includes('/photos'));
    expect(photoCall).toBeDefined();
    const form = photoCall!.init?.body as FormData;
    expect(form.get('tag')).toBe('staff:김민지');
    expect(saved).toHaveBeenCalled();
  });

  it('사진을 올려도 다른 줄에서 고치던 글은 그대로이고, 미리보기와 사진 바꾸기가 보인다', async () => {
    const PARK: StaffMember = { ...MINJI, name: '박준', subject: '수학' };
    const withPhoto = makeCard([{ ...MINJI, photo: '/uploads/r1/a.jpg' }, { ...PARK, photo: '' }]);
    stubFetch(async (url) => (url.includes('/photos') ? okCard(withPhoto) : okCard(withPhoto)));
    const { container } = render(<Host initial={makeCard([MINJI, PARK])} />);
    // 박준 소개를 고치는 중(저장 전)
    fireEvent.change(screen.getAllByLabelText('소개')[1], { target: { value: '고치던 소개' } });
    const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(fileInput, { target: { files: [new File(['사진'], 'a.png', { type: 'image/png' })] } });
    expect(await screen.findByText('사진을 올렸어요.')).toBeInTheDocument();
    expect(screen.getAllByLabelText('소개')[1]).toHaveValue('고치던 소개');
    expect(screen.getByAltText('김민지 사진')).toHaveAttribute('src', '/uploads/r1/a.jpg');
    expect(screen.getByRole('button', { name: '사진 바꾸기' })).toBeEnabled();
    expect(screen.getByRole('button', { name: '사진 올리기' })).toBeEnabled();
  });

  it('이름을 바꿔 저장하면 원래 이름(prev_name)을 같이 보내고, 저장했어요가 남는다', async () => {
    const puts: Record<string, unknown>[] = [];
    stubFetch(async (_url, init) => {
      const body = JSON.parse(String(init?.body ?? '{}'));
      puts.push(body);
      const staff = (body.staff as StaffMember[]).map(({ prev_name: _p, ...m }) => ({ ...m, photo: '' }));
      return okCard(makeCard(staff));
    });
    render(<Host initial={makeCard([MINJI])} />);
    fireEvent.change(screen.getByLabelText('이름'), { target: { value: '김민아' } });
    fireEvent.click(screen.getByRole('button', { name: '+ 선생님 더하기' }));
    fireEvent.change(screen.getAllByLabelText('이름')[1], { target: { value: '박준' } });
    fireEvent.click(screen.getByRole('button', { name: '저장' }));
    expect(await screen.findByText('저장했어요.')).toBeInTheDocument();
    const staff = puts[0].staff as StaffMember[];
    expect(staff[0]).toMatchObject({ name: '김민아', prev_name: '김민지' });
    expect(staff[1].prev_name).toBeUndefined();
  });
});
