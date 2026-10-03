// 줄 목록 고치기 (공용 부품). 줄 더하기·지우기·위아래 옮기기·최대 개수를 한 곳에서 다룬다.
// 줄 안 칸은 renderRow가 그린다(주변 안내: 이름+소제목+사진, 메뉴: 이름+가격+설명 …).
// 결제를 붙일 때도 줄 모양에 칸(가격 숫자·옵션·재고·결제 받기)을 더해 renderRow에서 그리면 된다.
import type { ReactNode } from 'react';

export interface RowListEditorProps<T> {
  rows: T[];
  max: number;
  /** "+ 장소 더하기"의 장소 */
  noun: string;
  emptyRow: () => T;
  rowKey: (row: T, index: number) => string | number;
  /** 줄 머리에 보일 이름(접근성 이름에도 쓴다) */
  rowTitle: (row: T, index: number) => string;
  renderRow: (row: T, index: number, update: (patch: Partial<T>) => void) => ReactNode;
  onChange: (rows: T[]) => void;
  disabled?: boolean;
}

export default function RowListEditor<T>({
  rows,
  max,
  noun,
  emptyRow,
  rowKey,
  rowTitle,
  renderRow,
  onChange,
  disabled,
}: RowListEditorProps<T>) {
  function update(i: number, patch: Partial<T>) {
    onChange(rows.map((r, j) => (j === i ? { ...r, ...patch } : r)));
  }
  function move(i: number, d: -1 | 1) {
    const j = i + d;
    if (j < 0 || j >= rows.length) return;
    const next = [...rows];
    [next[i], next[j]] = [next[j], next[i]];
    onChange(next);
  }
  return (
    <div className="ed-rows">
      <ol className="ed-rows__list">
        {rows.map((row, i) => {
          const title = rowTitle(row, i);
          return (
            <li key={rowKey(row, i)} className="ed-row" aria-label={`${i + 1}. ${title}`}>
              <div className="ed-row__head">
                <span className="ed-row__num" aria-hidden="true">{i + 1}</span>
                <strong className="ed-row__title">{title}</strong>
                <button type="button" className="ed-row__tool" aria-label={`${title} 위로`} disabled={disabled || i === 0} onClick={() => move(i, -1)}>↑</button>
                <button type="button" className="ed-row__tool" aria-label={`${title} 아래로`} disabled={disabled || i === rows.length - 1} onClick={() => move(i, 1)}>↓</button>
                <button type="button" className="ed-row__tool" aria-label={`${title} 지우기`} disabled={disabled} onClick={() => onChange(rows.filter((_, j) => j !== i))}>✕</button>
              </div>
              {renderRow(row, i, (patch) => update(i, patch))}
            </li>
          );
        })}
      </ol>
      <button type="button" className="ed-btn ed-rows__add" disabled={disabled || rows.length >= max} onClick={() => onChange([...rows, emptyRow()])}>
        + {noun} 더하기 ({rows.length}/{max})
      </button>
    </div>
  );
}
