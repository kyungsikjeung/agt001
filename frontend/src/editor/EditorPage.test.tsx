// EditorPage 화면 테스트 (목업 데이터, 서버 연결 없음).
import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import EditorPage from './EditorPage';

afterEach(() => cleanup());

describe('EditorPage', () => {
  it('자리 표시 배너가 보이고 개수를 알린다', () => {
    render(<EditorPage />);
    expect(screen.getByText(/공개 전에 채울 곳 \d+개/)).toBeInTheDocument();
    // 자리 표시 칸이 눈에 띄게 표시된다
    expect(screen.getAllByText('[전화번호 입력]').length).toBeGreaterThan(0);
    // 저장 상태가 보인다
    expect(screen.getByText(/저장됨 v\d+/)).toBeInTheDocument();
  });

  it('잠긴 값을 고치면 화면 안 확인창이 뜬다 (window.confirm 사용 안 함)', () => {
    const confirmSpy = vi.spyOn(window, 'confirm');
    render(<EditorPage />);
    // 편집 모드로 전환
    fireEvent.click(screen.getByRole('button', { name: '편집' }));
    // hero.title은 잠긴 값 → 버튼으로 표시됨
    fireEvent.click(screen.getByRole('button', { name: /가게 이름 고치기/ }));
    expect(screen.getByRole('dialog', { name: '가게 이름 고치기' })).toBeInTheDocument();
    // 저장 → 잠금 확인 대화상자
    fireEvent.click(screen.getByRole('button', { name: '저장' }));
    expect(screen.getByText('직접 정하신 값이에요. 바꿀까요?')).toBeInTheDocument();
    expect(confirmSpy).not.toHaveBeenCalled();
    confirmSpy.mockRestore();
  });

  it('AI 부탁 자리는 채팅방 이동 링크(#)로 둔다', () => {
    render(<EditorPage />);
    const link = screen.getByRole('link', { name: /AI에게 부탁하기/ });
    expect(link.getAttribute('href')).toBe('#');
  });
});
