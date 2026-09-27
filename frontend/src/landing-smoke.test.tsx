import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
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
});
