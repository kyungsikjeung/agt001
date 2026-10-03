import { describe, expect, it } from 'vitest';
import { readOpen, readStay, readTimes, timeModeOf, writeOpen, writeStay } from './timeRange';

describe('시간 칸 읽고 쓰기', () => {
  it('라벨로 모양을 고른다', () => {
    expect(timeModeOf('체크인·아웃 시간')).toBe('stay');
    expect(timeModeOf('영업시간')).toBe('open');
    expect(timeModeOf('수업 시간')).toBe('open');
    expect(timeModeOf('예식 일시')).toBeNull();
  });
  it('여러 말투의 시각을 읽는다', () => {
    expect(readTimes('15시 / 11시')).toEqual(['15:00', '11:00']);
    expect(readTimes('매일 10~21시')).toEqual(['10:00', '21:00']);
    expect(readTimes('오후 3시 반, 오전 11시')).toEqual(['15:30', '11:00']);
    expect(readTimes('체크인 15:00 · 체크아웃 11:00')).toEqual(['15:00', '11:00']);
    expect(readTimes('9시 30분부터')).toEqual(['09:30']);
  });
  it('숙박: 체크인·아웃', () => {
    expect(readStay('15시 / 11시')).toEqual({ checkin: '15:00', checkout: '11:00' });
    expect(writeStay({ checkin: '16:00', checkout: '11:00' })).toBe('체크인 16:00 · 체크아웃 11:00');
  });
  it('가게: 요일·시간·쉬는 날', () => {
    const t = readOpen('매일 10시~21시, 월요일 휴무');
    expect(t).toEqual({ days: '매일', open: '10:00', close: '21:00', closed: ['월'] });
    expect(writeOpen({ ...t, closed: ['월', '화'] })).toBe('매일 10:00~21:00, 월·화요일 휴무');
    expect(writeOpen({ days: '평일', open: '09:00', close: '18:00', closed: [] })).toBe('평일 09:00~18:00');
    expect(readOpen(writeOpen({ days: '주말', open: '11:00', close: '22:00', closed: ['수', '목'] }))).toEqual({
      days: '주말', open: '11:00', close: '22:00', closed: ['수', '목'],
    });
  });
});
