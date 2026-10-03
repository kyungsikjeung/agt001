// 사진 구역 설정 (10/4): 사진 수·움직임을 누르면 미리보기에 먼저 그리고 구역 편집으로 저장한다.
import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import SectionPanel from './SectionPanel';
import type { CardLayoutEdit, PreviewSection, RoomCard } from './cardApi';

const CARD: RoomCard = {
  title: '우리 펜션', industry: '펜션', fields: [], photos: [], choice: 'v2', published: null, site_url: null, can_edit: true,
};

const SECTIONS: PreviewSection[] = [
  { id: 'hero', label: '첫 화면', bind: 'hero', locked: true, hidden: false },
  { id: 'view', label: '주변', bind: 'space_photos', locked: false, hidden: false, settings: {} },
  { id: 'tour', label: '펜션 둘러보기', bind: 'space_photos', locked: false, hidden: false, settings: { motion: 'calm' } },
  { id: 'visit', label: '오시는 길', bind: 'location', locked: false, hidden: false },
];

function renderPanel(selectedId: string, onPreviewLayout: (l: CardLayoutEdit) => void) {
  return render(
    <SectionPanel roomId="r1" card={CARD} sections={SECTIONS} addable={[]} added={[]} baseItems={[]} variant="v2"
      selectedId={selectedId} clickedText="" onSelect={() => {}} onSaved={() => {}} onPreviewLayout={onPreviewLayout} />,
  );
}

let put: ReturnType<typeof vi.fn>;
beforeEach(() => {
  localStorage.setItem('agt001_member_id', 'm1');
  put = vi.fn(async () => new Response(JSON.stringify(CARD), { status: 200 }));
  vi.stubGlobal('fetch', put);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe('SectionPanel 사진 보이기', () => {
  it('사진 구역에만 보인다', () => {
    renderPanel('view', () => {});
    expect(screen.getByRole('group', { name: '보일 사진 수' })).toBeInTheDocument();
    cleanup();
    renderPanel('visit', () => {});
    expect(screen.queryByRole('group', { name: '보일 사진 수' })).toBeNull();
  });

  it('사진 수를 누르면 미리보기에 먼저 그리고, 다른 구역 설정은 지키며 저장한다', async () => {
    const preview = vi.fn();
    renderPanel('view', preview);
    fireEvent.click(screen.getByRole('button', { name: '6장' }));
    const want = { tour: { motion: 'calm' }, view: { count: 6 } };
    expect(preview.mock.calls[0][0].settings).toEqual(want);
    await waitFor(() => expect(put).toHaveBeenCalled());
    expect(JSON.parse(String(put.mock.calls[0][1].body)).layout.settings).toEqual(want);
  });

  it('기본으로 되돌리면 그 구역 설정을 뺀다', () => {
    const preview = vi.fn();
    renderPanel('tour', preview);
    expect(screen.getByRole('button', { name: '잔잔하게' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByText(/자동 흐름이 천천히/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '기본' }));
    expect(preview.mock.calls[0][0].settings).toEqual({});
  });
});
