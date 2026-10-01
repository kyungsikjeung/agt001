// 공지 사진 고르기 테스트 (NOTICE_PHOTO_CONTRACT §5의 5).
import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import NoticePhotos from './NoticePhotos';

function file(name: string) {
  return new File(['x'], name, { type: 'image/jpeg' });
}

beforeEach(() => {
  localStorage.clear();
  localStorage.setItem('agt001_member_id', 'm1');
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe('NoticePhotos', () => {
  it('notice 태그로 올리고 목록에 더한다, 빼기는 목록에서만', async () => {
    const tags: string[] = [];
    let n = 0;
    vi.stubGlobal(
      'fetch',
      vi.fn(async (_url: string, init?: RequestInit) => {
        tags.push(String((init?.body as FormData).get('tag')));
        n += 1;
        return { ok: true, status: 201, json: async () => ({ id: `p${n}`, url: `/uploads/r1/p${n}.jpg` }) } as Response;
      }),
    );
    const onChange = vi.fn();
    const { rerender } = render(<NoticePhotos roomId="r1" photos={[]} onChange={onChange} />);
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [file('a.jpg'), file('b.jpg')] } });
    await waitFor(() => expect(onChange).toHaveBeenCalledWith(['/uploads/r1/p1.jpg', '/uploads/r1/p2.jpg']));
    expect(tags).toEqual(['notice', 'notice']);
    rerender(<NoticePhotos roomId="r1" photos={['/uploads/r1/p1.jpg', '/uploads/r1/p2.jpg']} onChange={onChange} />);
    expect(screen.getByAltText('공지 사진 2')).toBeInTheDocument();
    fireEvent.click(screen.getAllByRole('button', { name: '빼기' })[0]);
    expect(onChange).toHaveBeenLastCalledWith(['/uploads/r1/p2.jpg']);
  });

  it('5장 상한: 남은 칸만 올리고 다 차면 추가 칸이 없다', async () => {
    let n = 0;
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        n += 1;
        return { ok: true, status: 201, json: async () => ({ id: `p${n}`, url: `/uploads/r1/n${n}.jpg` }) } as Response;
      }),
    );
    const four = ['/uploads/r1/1.jpg', '/uploads/r1/2.jpg', '/uploads/r1/3.jpg', '/uploads/r1/4.jpg'];
    const onChange = vi.fn();
    const { rerender } = render(<NoticePhotos roomId="r1" photos={four} onChange={onChange} />);
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [file('a.jpg'), file('b.jpg'), file('c.jpg')] } });
    await waitFor(() => expect(onChange).toHaveBeenCalledWith([...four, '/uploads/r1/n1.jpg']));
    expect(n).toBe(1);
    expect(screen.getByRole('status')).toHaveTextContent('5장까지');
    rerender(<NoticePhotos roomId="r1" photos={[...four, '/uploads/r1/n1.jpg']} onChange={onChange} />);
    expect(document.querySelector('input[type="file"]')).toBeNull();
  });
});
