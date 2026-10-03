import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { useState } from 'react';
import { afterEach, describe, expect, it } from 'vitest';
import TimeRangeField from './TimeRangeField';

function Harness({ mode, start }: { mode: 'stay' | 'open'; start: string }) {
  const [v, setV] = useState(start);
  return <TimeRangeField id="t" label={mode === 'stay' ? '체크인·아웃 시간' : '영업시간'} mode={mode} value={v} onChange={setV} />;
}

describe('TimeRangeField', () => {
  afterEach(() => cleanup());

  it('체크인 버튼을 누르면 글 칸이 채워지고 버튼이 눌린다', () => {
    render(<Harness mode="stay" start="" />);
    fireEvent.click(screen.getByRole('group', { name: '체크인' }).querySelector('button')!); // 14:00
    const text = screen.getByLabelText(/체크인·아웃 시간: 사이트에 보이는 글/) as HTMLInputElement;
    expect(text.value).toBe('체크인 14:00 · 체크아웃 11:00');
    fireEvent.change(screen.getByLabelText('체크아웃 다른 시각'), { target: { value: '10:30' } });
    expect(text.value).toBe('체크인 14:00 · 체크아웃 10:30');
  });

  it('채팅으로 들어온 글을 읽어 버튼을 맞춘다', () => {
    render(<Harness mode="stay" start="15시 / 11시" />);
    expect(screen.getByRole('button', { name: '15:00' }).getAttribute('aria-pressed')).toBe('true');
    expect(screen.getByRole('button', { name: '11:00' }).getAttribute('aria-pressed')).toBe('true');
  });

  it('가게 시간: 요일·쉬는 날을 고른다', () => {
    render(<Harness mode="open" start="매일 10시~21시" />);
    fireEvent.click(screen.getByRole('button', { name: '평일' }));
    fireEvent.click(screen.getByRole('group', { name: '쉬는 날' }).querySelector('button')!); // 월
    expect((screen.getByLabelText(/영업시간: 사이트에 보이는 글/) as HTMLInputElement).value).toBe('평일 10:00~21:00, 월요일 휴무');
  });

  it('시간대가 여러 개면 버튼을 막고 글 칸으로 고치게 한다', () => {
    render(<Harness mode="open" start="평일 10~21시, 주말 11~18시" />);
    expect(screen.getByText(/시간대가 여러 개라/)).toBeTruthy();
    expect((screen.getByRole('button', { name: '평일' }) as HTMLButtonElement).disabled).toBe(true);
  });
});
