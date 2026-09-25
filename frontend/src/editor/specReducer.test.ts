// specReducer 규칙 테스트 (D27 편집 규칙 · D23 자리 표시 · locked).
import { describe, expect, it } from 'vitest';
import { MOCK_CAFE, MOCK_PENSION } from './mockSpec';
import {
  applySetContent,
  canRedo,
  canUndo,
  initialEditorState,
  isLocked,
  isPublishable,
  listPlaceholders,
  redo,
  undo,
  validateSetContent,
} from './specReducer';

function pension() {
  return initialEditorState(structuredClone(MOCK_PENSION));
}

describe('specReducer', () => {
  it('허용: 일반 내용 수정이 적용된다', () => {
    const res = applySetContent(pension(), 'intro', 'body', '새 소개 글입니다.');
    expect(res.ok).toBe(true);
    expect(res.state.spec.sections.find((s) => s.id === 'intro')?.content['body']).toBe('새 소개 글입니다.');
  });

  it('허용: 빈 문자열로 비우면 자리 표시가 된다', () => {
    const res = applySetContent(pension(), 'contact', 'address', '');
    expect(res.ok).toBe(true);
    const slots = listPlaceholders(res.state.spec);
    expect(slots.some((p) => p.sectionId === 'contact' && p.key === 'address')).toBe(true);
  });

  it('거부: 스키마에 없는 필드', () => {
    const res = applySetContent(pension(), 'contact', 'no_such_field', '값');
    expect(res.ok).toBe(false);
    expect(res.error).toMatch(/직접 고칠 수 없어요/);
  });

  it('거부: 최대 길이 초과 (hero.title 30자)', () => {
    const long = '가'.repeat(31);
    const res = applySetContent(pension(), 'hero', 'title', long, { force: true });
    expect(res.ok).toBe(false);
    expect(res.error).toMatch(/최대 30자/);
  });

  it('거부: 형식 위반 (around.map_url 외부 링크 규칙)', () => {
    const res = applySetContent(pension(), 'around', 'map_url', 'https://evil.example/x');
    expect(res.ok).toBe(false);
    expect(res.error).toMatch(/형식/);
  });

  it('거부: 존재하지 않는 섹션 ID', () => {
    const v = validateSetContent(MOCK_PENSION, 'nope', 'phone', '010-0000-0000');
    expect(v.ok).toBe(false);
  });

  it('locked: force 없이는 needsConfirm을 반환하고 명세를 바꾸지 않는다', () => {
    expect(isLocked(MOCK_PENSION, 'hero', 'title')).toBe(true);
    const st = pension();
    const res = applySetContent(st, 'hero', 'title', '새 이름');
    expect(res.ok).toBe(false);
    expect(res.needsConfirm).toBe(true);
    expect(res.state.spec.sections.find((s) => s.id === 'hero')?.content['title']).toBe('예시 솔숲 펜션');
  });

  it('locked: force 확인 후 적용된다', () => {
    const res = applySetContent(pension(), 'hero', 'title', '새 이름', { force: true });
    expect(res.ok).toBe(true);
    expect(res.state.spec.sections.find((s) => s.id === 'hero')?.content['title']).toBe('새 이름');
    expect(res.state.history[0].forced).toBe(true);
  });

  it('undo/redo: 값을 되돌렸다가 다시 적용한다', () => {
    const s0 = pension();
    const r1 = applySetContent(s0, 'intro', 'body', '바꾼 소개');
    expect(canUndo(r1.state)).toBe(true);
    const back = undo(r1.state);
    expect(back.spec.sections.find((s) => s.id === 'intro')?.content['body']).toBe(
      s0.spec.sections.find((s) => s.id === 'intro')?.content['body'],
    );
    expect(canRedo(back)).toBe(true);
    const fwd = redo(back);
    expect(fwd.spec.sections.find((s) => s.id === 'intro')?.content['body']).toBe('바꾼 소개');
  });

  it('undo할 것이 없으면 같은 상태를 돌려준다', () => {
    const s0 = pension();
    expect(undo(s0)).toBe(s0);
    expect(canUndo(s0)).toBe(false);
  });

  it('version: 적용할 때마다 1씩 증가한다', () => {
    const s0 = pension();
    const v0 = s0.spec.version;
    const r1 = applySetContent(s0, 'intro', 'body', '첫 번째');
    const r2 = applySetContent(r1.state, 'intro', 'body', '두 번째');
    expect(r1.state.spec.version).toBe(v0 + 1);
    expect(r2.state.spec.version).toBe(v0 + 2);
  });

  it('자리 표시 계산: 펜션 목업의 빈 칸을 모두 찾는다', () => {
    const slots = listPlaceholders(MOCK_PENSION);
    expect(slots.some((p) => p.sectionId === 'contact' && p.key === 'phone' && p.placeholder === '[전화번호 입력]')).toBe(
      true,
    );
    expect(slots.some((p) => p.sectionId === 'around' && p.key === 'address')).toBe(true);
    expect(slots.some((p) => p.sectionId === 'rooms' && p.key === 'items' && p.itemIndex === 0)).toBe(true);
    expect(slots.length).toBeGreaterThanOrEqual(3);
  });

  it('공개 가능 여부: 빈 칸이 있으면 false, 다 채우면 true', () => {
    expect(isPublishable(MOCK_PENSION).publishable).toBe(false);
    let st = pension();
    for (const slot of listPlaceholders(st.spec)) {
      if (slot.key === 'items' && slot.itemIndex !== undefined) {
        const section = st.spec.sections.find((s) => s.id === slot.sectionId);
        const items = [...((section?.content['items'] ?? []) as Array<Record<string, unknown>>)];
        items[slot.itemIndex] = { ...(items[slot.itemIndex] as Record<string, unknown>), price: '예시 5,000원' };
        const r = applySetContent(st, slot.sectionId, 'items', items, { force: true });
        expect(r.ok).toBe(true);
        st = r.state;
      } else {
        const fill = slot.key === 'phone' ? '010-0000-0000' : slot.key === 'hours' ? '매일 09:00~18:00' : '예시 주소 123';
        const r = applySetContent(st, slot.sectionId, slot.key, fill, { force: true });
        expect(r.ok).toBe(true);
        st = r.state;
      }
    }
    // cta.phone은 contact.phone과 중복 집계하지 않으므로 contact만 채우면 됨. 남은 칸 확인:
    const rest = listPlaceholders(st.spec);
    expect(rest.length).toBe(0);
    expect(isPublishable(st.spec).publishable).toBe(true);
  });

  it('history: 적용마다 기록이 남는다', () => {
    const r1 = applySetContent(pension(), 'intro', 'body', '기록 확인용');
    expect(r1.state.history.length).toBe(1);
    expect(r1.state.history[0]).toMatchObject({ sectionId: 'intro', key: 'body', nextValue: '기록 확인용' });
  });

  it('카페 목업도 자리 표시·공개 불가로 시작한다', () => {
    expect(listPlaceholders(MOCK_CAFE).length).toBeGreaterThan(0);
    expect(isPublishable(MOCK_CAFE).publishable).toBe(false);
  });
});
