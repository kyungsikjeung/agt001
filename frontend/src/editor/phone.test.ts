import { describe, expect, it } from 'vitest';
import { formatPhone, nextPhone, phoneLooksOk } from './phone';

describe('formatPhone (치는 중 자동 하이픈)', () => {
  it('휴대폰은 3-4-4', () => {
    expect(formatPhone('01096567830')).toBe('010-9656-7830');
    expect(formatPhone('010')).toBe('010');
    expect(formatPhone('0109')).toBe('010-9');
    expect(formatPhone('0109656')).toBe('010-9656');
    expect(formatPhone('01096567')).toBe('010-9656-7');
    expect(formatPhone('010-9656-78301')).toBe('010-9656-7830'); // 11자리에서 멈춤
  });
  it('서울 02, 지역번호, 대표번호, 안심번호', () => {
    expect(formatPhone('021234567')).toBe('02-123-4567');
    expect(formatPhone('0212345678')).toBe('02-1234-5678');
    expect(formatPhone('0311234567')).toBe('031-123-4567');
    expect(formatPhone('03112345678')).toBe('031-1234-5678');
    expect(formatPhone('15881234')).toBe('1588-1234');
    expect(formatPhone('050712345678')).toBe('0507-1234-5678');
    expect(formatPhone('+82 10 9656 7830')).toBe('010-9656-7830');
  });
  it('글이 섞이면 손대지 않는다', () => {
    expect(formatPhone('카톡으로 문의')).toBe('카톡으로 문의');
    expect(formatPhone('010-1234-5678 (사장님)')).toBe('010-1234-5678 (사장님)');
    expect(formatPhone('')).toBe('');
  });
  it('하이픈 뒤에서 백스페이스하면 숫자까지 지운다', () => {
    expect(nextPhone('010-9656', '010-965')).toBe('010-965');
    expect(nextPhone('010-9', '010-')).toBe('010');
    expect(nextPhone('010-9656-7', '010-9656-')).toBe('010-9656');
  });
  it('모양 확인', () => {
    expect(phoneLooksOk('010-9656-7830')).toBe(true);
    expect(phoneLooksOk('010-9656')).toBe(false);
    expect(phoneLooksOk('카톡 문의')).toBe(true);
    expect(phoneLooksOk('')).toBe(true);
  });
});
