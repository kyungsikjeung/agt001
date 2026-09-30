// 한 문장 만들기 테스트 (FIX_TAGS_CONTRACT §3 표).
import { describe, expect, it } from 'vitest';
import { FIX_NEW_KEY, compose, type FixTarget } from './fixTags';

const HOURS: FixTarget = { key: 'hours', label: '영업시간', current: '매일 9시~8시', parts: [] };
const MENU: FixTarget = {
  key: 'items',
  label: '메뉴·가격',
  current: '',
  parts: [{ key: '아메리카노', label: '아메리카노 4,500원' }],
};

describe('compose', () => {
  it('일반 칸은 "이름 + 입력"이다', () => {
    expect(compose(HOURS, null, '매일 10시~9시')).toBe('영업시간 매일 10시~9시');
  });

  it('항목 고치기는 "항목 + 입력"이다', () => {
    expect(compose(MENU, MENU.parts[0], '5,000원으로')).toBe('아메리카노 5,000원으로');
  });

  it('새 항목은 "칸에 입력 추가"이다', () => {
    expect(compose(MENU, { key: FIX_NEW_KEY, label: '+ 새 항목' }, '바닐라라떼 5,500원')).toBe(
      '메뉴·가격에 바닐라라떼 5,500원 추가',
    );
  });

  it('입력이 이미 칸 이름으로 시작하면 그대로 둔다', () => {
    expect(compose(HOURS, null, '영업시간 매일 10시~9시')).toBe('영업시간 매일 10시~9시');
    expect(compose(MENU, MENU.parts[0], '아메리카노 5,000원으로')).toBe('아메리카노 5,000원으로');
  });

  it('빈 입력은 보내지 않는다', () => {
    expect(compose(HOURS, null, '   ')).toBe('');
  });
});
