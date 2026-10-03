// 시간 두 개 빠르게 고르기 (공용 입력 부품). 펜션 체크인·체크아웃처럼 자주 쓰는 시간은 칩으로 한 번에,
// 그 밖은 시간 칸(30분 단위)으로. 결과는 "체크인 15:00 · 체크아웃 11:00" 글 한 줄로 저장한다.
// 직접 쓰기를 펴면 글로도 고칠 수 있다(예: "체크인 15:00 · 체크아웃 11:00, 얼리 체크인 문의").
import { useState } from 'react';
import { formatPair, isComposed, parsePair, type TimePair } from './timeRange';

export interface TimeRangeFieldProps {
  id: string;
  label: string;
  value: string;
  disabled?: boolean;
  onChange: (value: string) => void;
  startName?: string;
  endName?: string;
  startPresets?: string[];
  endPresets?: string[];
}

export const STAY_PRESETS = {
  startName: '체크인',
  endName: '체크아웃',
  startPresets: ['14:00', '15:00', '16:00'],
  endPresets: ['10:00', '11:00', '12:00'],
};

export default function TimeRangeField({
  id,
  label,
  value,
  disabled,
  onChange,
  startName = STAY_PRESETS.startName,
  endName = STAY_PRESETS.endName,
  startPresets = STAY_PRESETS.startPresets,
  endPresets = STAY_PRESETS.endPresets,
}: TimeRangeFieldProps) {
  const pair = parsePair(value);
  const [free, setFree] = useState(() => !isComposed(value, startName, endName));

  function set(which: keyof TimePair, time: string) {
    onChange(formatPair({ ...pair, [which]: time }, startName, endName));
  }

  function row(which: keyof TimePair, name: string, presets: string[]) {
    const cur = pair[which];
    return (
      <div className="ed-timerange__row">
        <span className="ed-timerange__name" id={`${id}-${which}`}>{name}</span>
        <div className="ed-chips" role="group" aria-labelledby={`${id}-${which}`}>
          {presets.map((t) => (
            <button
              key={t}
              type="button"
              className="ed-chip"
              aria-pressed={cur === t}
              disabled={disabled || free}
              onClick={() => set(which, cur === t ? '' : t)}
            >
              {t}
            </button>
          ))}
          <input
            type="time"
            step={1800}
            className="ed-input ed-timerange__time"
            aria-label={`${name} 시간 직접 고르기`}
            value={cur}
            disabled={disabled || free}
            onChange={(e) => set(which, e.target.value)}
          />
        </div>
      </div>
    );
  }

  return (
    <fieldset className="ed-timerange" aria-describedby={`${id}-out`}>
      <legend>{label}</legend>
      {row('start', startName, startPresets)}
      {row('end', endName, endPresets)}
      <p className="ed-timerange__out" id={`${id}-out`}>
        {value.trim() ? <>손님에게 보이는 글: <b>{value}</b></> : '시간을 고르면 여기에 손님에게 보일 글이 나와요'}
      </p>
      <label className="ed-timerange__free">
        <input type="checkbox" checked={free} disabled={disabled} onChange={(e) => setFree(e.target.checked)} /> 글로 직접 쓰기
      </label>
      {free ? (
        <input
          id={id}
          className="ed-input"
          type="text"
          value={value}
          disabled={disabled}
          placeholder={`예: ${startName} 15:00 · ${endName} 11:00, 얼리 ${startName} 문의`}
          aria-label={`${label} 글`}
          onChange={(e) => onChange(e.target.value)}
        />
      ) : null}
    </fieldset>
  );
}
