import '@testing-library/jest-dom/vitest';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import Landing from './Landing';
import HeroDemo from './landing/HeroDemo';

vi.mock('./api', () => ({
  visitorId: () => 'v-test',
  track: vi.fn(),
  startRoom: vi.fn(),
}));
vi.mock('./auth', () => ({
  me: () => Promise.resolve(null),
  startLogin: vi.fn(),
  logout: vi.fn(),
}));
vi.mock('./voice', async (orig) => {
  const actual = (await orig()) as object;
  return { ...actual, voiceSupported: false, useVoiceInput: () => ({ state: 'idle', seconds: 0, status: null, numCheck: false, toggle: () => {} }) };
});

describe('landing smoke', () => {
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });
  it('핵심 기능 요소가 모두 렌더된다', () => {
    render(<Landing />);
    expect(document.getElementById('prompt-input')).not.toBeNull();
    expect(screen.getByRole('button', { name: '시작하기' })).not.toBeNull();
    expect(screen.getByRole('link', { name: '내 프로젝트' })).not.toBeNull();
    expect(screen.getByRole('button', { name: '로그인' })).not.toBeNull();
    expect(screen.getByRole('list', { name: '업종 예시로 채우기' })).not.toBeNull();
    expect(screen.getByRole('navigation', { name: '약관' })).not.toBeNull();
    expect(screen.getByText('말하지 않은 전화·가격은 넣지 않아요')).not.toBeNull();
  });
  it('데모가 정지 상태로도 렌더된다', () => {
    Object.defineProperty(window, 'matchMedia', {
      value: () => ({ matches: true }),
      configurable: true,
    });
    render(<HeroDemo />);
    expect(document.querySelector('.lp-stage')).not.toBeNull();
  });
  it('템플릿을 누른 뒤 뒤로 가기로 돌아오면 다시 누를 수 있다', async () => {
    // 빌더 이동이 끝나지 않아 busy로 잠긴 채로 둔다.
    const fetchMock = vi.fn(() => new Promise<Response>(() => {}));
    vi.stubGlobal('fetch', fetchMock);
    render(<Landing />);
    // 템플릿 카드(그리드)를 누른다. 칩과 달리 busy 때 disabled가 붙는다.
    const btn = screen.getByText('객실, 바비큐장, 주변 맛집과 여행지').closest('button');
    expect(btn).not.toBeNull();
    fireEvent.click(btn!);
    await waitFor(() => expect(btn!).toBeDisabled());
    act(() => {
      window.dispatchEvent(new Event('pageshow'));
    });
    await waitFor(() => expect(btn!).not.toBeDisabled());
    // 잠금이 풀려 다시 누르면 빌더 시작을 다시 부른다.
    fireEvent.click(btn!);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
  });
});
