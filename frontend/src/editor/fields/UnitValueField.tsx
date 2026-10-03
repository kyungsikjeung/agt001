// 단위 고르고 값 넣기 (공용 입력 부품). 소제목처럼 "무엇을 어떤 단위로" 적는 칸:
// 주변 안내(도보 n분·차로 n분·n km·직접 글), 메뉴 가격(n원·직접 글) 등에 같은 모양으로 쓴다.
// 값은 숫자로 따로 두어(가격·거리) 나중에 결제·정렬에 그대로 쓸 수 있게 한다.
import { useId } from 'react';

export interface UnitOption {
  key: string;
  /** 칩 글 */
  label: string;
  /** 값 칸 종류: 정수·소수·글 */
  input: 'int' | 'decimal' | 'text';
  placeholder: string;
  /** 값 칸 뒤 단위 글(분·km·원). 글 칸이면 없음 */
  suffix?: string;
  /** 손님에게 보일 글 */
  show: (value: string) => string;
}

function kmText(v: string): string {
  const n = Number(v);
  if (!v || !Number.isFinite(n) || n <= 0) return '';
  return n < 1 ? `${Math.round(n * 1000)}m` : `${Number(n.toFixed(2))}km`;
}

export const NEARBY_UNITS: UnitOption[] = [
  { key: 'walk', label: '도보', input: 'int', placeholder: '3', suffix: '분', show: (v) => (v ? `도보 ${v}분` : '') },
  { key: 'car', label: '차로', input: 'int', placeholder: '10', suffix: '분', show: (v) => (v ? `차로 ${v}분` : '') },
  { key: 'km', label: '거리', input: 'decimal', placeholder: '1.2', suffix: 'km', show: kmText },
  { key: 'text', label: '직접 쓰기', input: 'text', placeholder: '예: 바로 앞, 주말에만', show: (v) => v.trim() },
];

export const PRICE_UNITS: UnitOption[] = [
  { key: 'won', label: '금액', input: 'int', placeholder: '4500', suffix: '원', show: (v) => (v ? `${Number(v).toLocaleString('ko-KR')}원` : '') },
  { key: 'text', label: '직접 쓰기', input: 'text', placeholder: '예: 시가, 가격 문의', show: (v) => v.trim() },
];

/** 값 칸에 넣을 수 있는 글자만 남긴다. */
export function cleanValue(input: UnitOption['input'], raw: string): string {
  if (input === 'int') return raw.replace(/\D/g, '').slice(0, 7);
  if (input === 'decimal') {
    const t = raw.replace(/[^\d.]/g, '');
    const [a, ...b] = t.split('.');
    return (b.length ? `${a}.${b.join('').slice(0, 2)}` : a).slice(0, 7);
  }
  return raw.slice(0, 30);
}

/** 저장된 가격 글("4,500원", "시가") → 단위·값. */
export function parsePrice(text: string): { unit: string; value: string } {
  const t = (text || '').trim();
  const m = /^([\d,]+)\s*원$/.exec(t);
  if (!t) return { unit: 'won', value: '' };
  return m ? { unit: 'won', value: m[1].replace(/,/g, '') } : { unit: 'text', value: t };
}

export interface UnitValueFieldProps {
  label: string;
  units: UnitOption[];
  unit: string;
  value: string;
  disabled?: boolean;
  onChange: (unit: string, value: string) => void;
}

export default function UnitValueField({ label, units, unit, value, disabled, onChange }: UnitValueFieldProps) {
  const id = useId();
  const cur = units.find((u) => u.key === unit) ?? units[0];
  const shown = cur.show(value);
  return (
    <div className="ed-unitval" role="group" aria-labelledby={`${id}-l`}>
      <span className="ed-unitval__label" id={`${id}-l`}>{label}</span>
      <div className="ed-chips">
        {units.map((u) => (
          <button
            key={u.key}
            type="button"
            className="ed-chip"
            aria-pressed={u.key === cur.key}
            disabled={disabled}
            onClick={() => onChange(u.key, u.input === cur.input ? value : '')}
          >
            {u.label}
          </button>
        ))}
      </div>
      <div className="ed-unitval__box">
        <input
          className="ed-input"
          type="text"
          inputMode={cur.input === 'int' ? 'numeric' : cur.input === 'decimal' ? 'decimal' : 'text'}
          aria-label={`${label} ${cur.input === 'text' ? '글' : `(${cur.suffix})`}`}
          placeholder={cur.placeholder}
          value={value}
          disabled={disabled}
          onChange={(e) => onChange(cur.key, cleanValue(cur.input, e.target.value))}
        />
        {cur.suffix ? <span className="ed-unitval__suffix" aria-hidden="true">{cur.suffix}</span> : null}
      </div>
      <span className="ed-field-msg">{shown ? `보이는 글: ${shown}` : '비워 두면 이름만 보여요'}</span>
    </div>
  );
}
