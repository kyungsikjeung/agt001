// 공용 입력 부품: 전화번호 하이픈 자동·검사, 시간 두 개 빠르게 고르기 (10/4 대표 요청).
import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { useState } from 'react';
import { afterEach, describe, expect, it } from 'vitest';
import PhoneField from './PhoneField';
import TimeRangeField from './TimeRangeField';
import { caretAfterDigits, checkPhone, formatPhoneTyping } from './phone';
import { findTimes, formatPair, parsePair } from './timeRange';

afterEach(cleanup);

describe('전화번호 모양 (서버 validate.format_phone과 같은 규칙)', () => {
  it.each([
    ['01033332222', '010-3333-2222'],
    ['0103333222', '010-333-3222'],
    ['010333', '010-333'],
    ['0212345678', '02-1234-5678'],
    ['021234567', '02-123-4567'],
    ['0311234567', '031-123-4567'],
    ['15881234', '1588-1234'],
    ['050712345678', '0507-1234-5678'],
    ['010-3333-22229999', '010-3333-2222'],
  ])('%s → %s', (raw, want) => {
    expect(formatPhoneTyping(raw)).toBe(want);
  });

  it('자리 수·주민번호 검사', () => {
    expect(checkPhone('010-3333-2222')).toBeNull();
    expect(checkPhone('0507-1234-5678')).toBeNull();
    expect(checkPhone('010-333')).toBe('전화번호 자리수가 맞지 않아요');
    expect(checkPhone('900101-1234567')).toBe('주민등록번호는 받지 않아요');
  });

  it('하이픈이 끼어도 커서는 같은 숫자 뒤', () => {
    expect(caretAfterDigits('010-3333-2222', 4)).toBe(5);
    expect(caretAfterDigits('010-3333-2222', 3)).toBe(3);
  });
});

function PhoneHost({ start = '' }: { start?: string }) {
  const [v, setV] = useState(start);
  return <PhoneField id="p" label="전화번호" value={v} onChange={setV} />;
}

describe('PhoneField', () => {
  it('숫자만 넣어도 하이픈이 들어가고, 맞으면 ✓', () => {
    render(<PhoneHost />);
    const input = screen.getByLabelText('전화번호');
    expect(input).toHaveAttribute('type', 'tel');
    expect(input).toHaveAttribute('inputmode', 'tel');
    fireEvent.change(input, { target: { value: '01033332222' } });
    expect(input).toHaveValue('010-3333-2222');
    expect(screen.getByText('✓ 010-3333-2222')).toBeInTheDocument();
  });

  it('덜 쓴 채로 칸을 떠나면 이유를 보인다', () => {
    render(<PhoneHost />);
    const input = screen.getByLabelText('전화번호');
    fireEvent.change(input, { target: { value: '010333' } });
    expect(screen.queryByText('전화번호 자리수가 맞지 않아요')).toBeNull(); // 쓰는 중에는 조용히
    fireEvent.blur(input);
    expect(screen.getByText('전화번호 자리수가 맞지 않아요')).toBeInTheDocument();
    expect(input).toHaveAttribute('aria-invalid', 'true');
  });
});

describe('시간 두 개 글', () => {
  it('여러 말투에서 시간을 찾는다', () => {
    expect(findTimes('15시 / 11시')).toEqual(['15:00', '11:00']);
    expect(findTimes('체크인 오후 3시 반, 체크아웃 오전 11시')).toEqual(['15:30', '11:00']);
    expect(parsePair('체크인 15:00 · 체크아웃 11:00')).toEqual({ start: '15:00', end: '11:00' });
    expect(formatPair({ start: '15:00', end: '' }, '체크인', '체크아웃')).toBe('체크인 15:00');
  });
});

function RangeHost({ start = '' }: { start?: string }) {
  const [v, setV] = useState(start);
  return (
    <>
      <TimeRangeField id="h" label="체크인·아웃 시간" value={v} onChange={setV} />
      <output data-testid="saved">{v}</output>
    </>
  );
}

describe('TimeRangeField', () => {
  it('칩 두 번이면 "체크인 15:00 · 체크아웃 11:00"', () => {
    render(<RangeHost />);
    const inGroup = screen.getByRole('group', { name: '체크인' });
    const outGroup = screen.getByRole('group', { name: '체크아웃' });
    fireEvent.click(inGroup.querySelector('button:nth-of-type(2)') as HTMLButtonElement); // 15:00
    fireEvent.click(outGroup.querySelector('button:nth-of-type(2)') as HTMLButtonElement); // 11:00
    expect(screen.getByTestId('saved')).toHaveTextContent('체크인 15:00 · 체크아웃 11:00');
    expect(screen.getByRole('button', { name: '15:00' })).toHaveAttribute('aria-pressed', 'true');
  });

  it('예전 글("15시 / 11시")도 칩에 켜져 보이고, 시간 칸으로 직접 고를 수 있다', () => {
    render(<RangeHost start="15시 / 11시" />);
    expect(screen.getByRole('button', { name: '15:00' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('button', { name: '11:00' })).toHaveAttribute('aria-pressed', 'true');
    fireEvent.change(screen.getByLabelText('체크아웃 시간 직접 고르기'), { target: { value: '10:30' } });
    expect(screen.getByTestId('saved')).toHaveTextContent('체크인 15:00 · 체크아웃 10:30');
  });

  it('사장님이 직접 쓴 글은 "글로 직접 쓰기"로 열어 둔다(덮어쓰지 않음)', () => {
    render(<RangeHost start="체크인 15:00 · 체크아웃 11:00, 얼리 체크인 문의" />);
    expect(screen.getByRole('checkbox', { name: '글로 직접 쓰기' })).toBeChecked();
    expect(screen.getByRole('button', { name: '15:00' })).toBeDisabled();
  });
});
