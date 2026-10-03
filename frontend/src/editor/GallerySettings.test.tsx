// 사진 구역 설정: 장수·비율·움직임 (모양에 맞는 것만) (10/4 대표 요청).
import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import GallerySettings from './GallerySettings';
import SectionPanel from './SectionPanel';
import type { RoomCard } from './cardApi';

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe('GallerySettings', () => {
  it('넘기기 모양: 장수·비율·자동 넘김, 흐름 속도는 없음', () => {
    const onChange = vi.fn();
    render(<GallerySettings shape="swipe" opts={{ count: 4 }} onChange={onChange} />);
    expect(screen.getByRole('button', { name: '4장' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.queryByRole('group', { name: '흐름 속도' })).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: '5초마다' }));
    expect(onChange).toHaveBeenLastCalledWith({ count: 4, autoplay: 5 });
    fireEvent.click(screen.getByRole('button', { name: /정사각/ }));
    expect(onChange).toHaveBeenLastCalledWith({ count: 4, ratio: 'square' });
    fireEvent.click(screen.getByRole('button', { name: '전부' }));
    expect(onChange).toHaveBeenLastCalledWith({});
  });

  it('흐름 모양: 속도만, 격자: 움직임 안내', () => {
    const onChange = vi.fn();
    const { rerender } = render(<GallerySettings shape="marquee" opts={{}} onChange={onChange} />);
    expect(screen.queryByRole('group', { name: '자동 넘김' })).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: '빠르게' }));
    expect(onChange).toHaveBeenLastCalledWith({ speed: 'fast' });
    rerender(<GallerySettings shape="grid" opts={{}} onChange={onChange} />);
    expect(screen.getByText(/넘기기·흐름으로 바꾸면 고를 수 있어요/)).toBeInTheDocument();
  });
});

describe('SectionPanel 사진 구역 설정', () => {
  it('사진첩 구역을 고르면 설정이 보이고, 바꾸면 미리보기 먼저·opts 저장(다른 구역 설정은 그대로)', async () => {
    const card: RoomCard = { title: 't', industry: '펜션', fields: [], photos: [], choice: 'v2', published: null, site_url: null, can_edit: true };
    const bodies: unknown[] = [];
    vi.stubGlobal('fetch', vi.fn(async (_u: string, init?: RequestInit) => {
      bodies.push(JSON.parse(String(init?.body)));
      return { ok: true, status: 200, json: async () => card } as Response;
    }));
    const preview = vi.fn();
    const sections = [
      { id: 'hero', label: '첫 화면', bind: 'hero', locked: true, hidden: false },
      { id: 'view', label: '주변', bind: 'nearby', locked: false, hidden: false, type: 'gallery', variant: 'swipe', base_variant: 'swipe', opts: {} },
      { id: 'tour', label: '펜션 둘러보기', bind: 'space_photos', locked: false, hidden: false, type: 'gallery', variant: 'marquee', base_variant: 'marquee', opts: { speed: 'slow' as const } },
    ];
    render(
      <SectionPanel roomId="r1" card={card} sections={sections} addable={[]} added={[]} baseItems={[]} variant="v2"
        selectedId="view" clickedText="" onSelect={() => {}} onSaved={() => {}} onPreviewLayout={preview} />,
    );
    fireEvent.click(screen.getByRole('button', { name: '3초마다' }));
    expect(preview).toHaveBeenCalledWith(expect.objectContaining({ opts: { tour: { speed: 'slow' }, view: { autoplay: 3 } } }));
    await waitFor(() => expect(bodies).toHaveLength(1));
    expect(bodies[0]).toMatchObject({ layout: { variant: 'v2', opts: { tour: { speed: 'slow' }, view: { autoplay: 3 } } } });
  });
});
