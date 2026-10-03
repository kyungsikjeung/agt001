// 시간 칸 빠르게 고르기 (10/4). 체크인·아웃(숙박) 또는 요일·여는·닫는 시간·쉬는 날(가게·수업)을
// 버튼과 30분 간격 고르기로 정하고, 아래 글 칸에 문장으로 채운다. 글 칸은 그대로 고칠 수 있다.
import {
  DAY_SETS,
  QUICK,
  WEEKDAYS,
  halfHours,
  readOpen,
  readStay,
  readTimes,
  writeOpen,
  writeStay,
  type TimeMode,
} from './timeRange';

const HALF_HOURS = halfHours();

interface PickProps {
  name: string;
  value: string;
  quick: readonly string[];
  disabled?: boolean;
  onPick: (v: string) => void;
}

/** 한 시각: 자주 쓰는 버튼 + 30분 간격 고르기 */
function TimePick({ name, value, quick, disabled, onPick }: PickProps) {
  return (
    <div className="ed-time__row" role="group" aria-label={name}>
      <span className="ed-time__name">{name}</span>
      <div className="ed-time__chips">
        {quick.map((q) => (
          <button key={q} type="button" aria-pressed={value === q} disabled={disabled} onClick={() => onPick(q)}>
            {q}
          </button>
        ))}
        <select
          className="ed-time__select"
          aria-label={`${name} 다른 시각`}
          value={quick.includes(value) ? '' : value}
          disabled={disabled}
          onChange={(e) => onPick(e.target.value)}
        >
          <option value="">다른 시각</option>
          {HALF_HOURS.map((h) => (
            <option key={h} value={h}>
              {h}
            </option>
          ))}
        </select>
      </div>
    </div>
  );
}

export interface TimeRangeFieldProps {
  id: string;
  label: string;
  mode: TimeMode;
  value: string;
  disabled?: boolean;
  onChange: (value: string) => void;
}

export default function TimeRangeField({ id, label, mode, value, disabled, onChange }: TimeRangeFieldProps) {
  // 시간대가 셋 이상이면("평일 10~21시, 주말 11~18시") 버튼으로 다 못 담는다 → 글 칸으로만
  const many = readTimes(value).length > 2;

  return (
    <fieldset className="ed-time">
      <legend>{label}</legend>
      {mode === 'stay' ? (
        (() => {
          const t = readStay(value);
          return (
            <>
              <TimePick name="체크인" value={t.checkin} quick={QUICK.checkin} disabled={disabled}
                onPick={(v) => onChange(writeStay({ ...t, checkin: v, checkout: t.checkout || '11:00' }))} />
              <TimePick name="체크아웃" value={t.checkout} quick={QUICK.checkout} disabled={disabled}
                onPick={(v) => onChange(writeStay({ ...t, checkout: v, checkin: t.checkin || '15:00' }))} />
            </>
          );
        })()
      ) : (
        (() => {
          const t = readOpen(value);
          const set = (patch: Partial<typeof t>) =>
            onChange(writeOpen({ ...t, open: t.open || '10:00', close: t.close || '21:00', days: t.days || '매일', ...patch }));
          return (
            <>
              <div className="ed-time__row" role="group" aria-label="여는 요일">
                <span className="ed-time__name">요일</span>
                <div className="ed-time__chips">
                  {DAY_SETS.map((d) => (
                    <button key={d} type="button" aria-pressed={t.days === d} disabled={disabled || many} onClick={() => set({ days: d })}>
                      {d}
                    </button>
                  ))}
                </div>
              </div>
              <TimePick name="여는 시간" value={t.open} quick={QUICK.open} disabled={disabled || many} onPick={(v) => set({ open: v })} />
              <TimePick name="닫는 시간" value={t.close} quick={QUICK.close} disabled={disabled || many} onPick={(v) => set({ close: v })} />
              <div className="ed-time__row" role="group" aria-label="쉬는 날">
                <span className="ed-time__name">쉬는 날</span>
                <div className="ed-time__chips">
                  {WEEKDAYS.map((d) => {
                    const on = t.closed.includes(d);
                    return (
                      <button key={d} type="button" aria-pressed={on} disabled={disabled || many}
                        onClick={() => set({ closed: WEEKDAYS.filter((w) => (w === d ? !on : t.closed.includes(w))) })}>
                        {d}
                      </button>
                    );
                  })}
                </div>
              </div>
            </>
          );
        })()
      )}
      {many ? <p className="ed-site-hint">시간대가 여러 개라 아래 글 칸에서 직접 고쳐 주세요.</p> : null}
      <label className="ed-time__text" htmlFor={id}>
        <span>사이트에 보이는 글 (직접 고쳐도 돼요)</span>
        <input id={id} className="ed-input" type="text" aria-label={`${label}: 사이트에 보이는 글`} value={value} disabled={disabled} onChange={(e) => onChange(e.target.value)} />
      </label>
    </fieldset>
  );
}
