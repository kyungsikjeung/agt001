// 전화번호 칸 (공용 입력 부품). 쓰는 동안 010-1234-5678처럼 하이픈을 넣고, 칸을 떠나면 자리 수를 확인한다.
// 저장 모양은 서버가 같은 규칙으로 한 가지로 맞춘다(app/services/validate.py format_phone).
import { useLayoutEffect, useRef, useState } from 'react';
import { caretAfterDigits, checkPhone, formatPhoneTyping, hasSpokenDigits, phoneDigits } from './phone';

export interface PhoneFieldProps {
  id: string;
  label: string;
  value: string;
  disabled?: boolean;
  onChange: (value: string) => void;
}

export default function PhoneField({ id, label, value, disabled, onChange }: PhoneFieldProps) {
  const input = useRef<HTMLInputElement>(null);
  const caret = useRef<number | null>(null);
  const [touched, setTouched] = useState(false);

  useLayoutEffect(() => {
    if (caret.current !== null && input.current && document.activeElement === input.current) {
      input.current.setSelectionRange(caret.current, caret.current);
    }
    caret.current = null;
  }, [value]);

  function change(raw: string, at: number | null) {
    if (hasSpokenDigits(raw)) {
      onChange(raw);
      return;
    }
    const next = formatPhoneTyping(raw);
    if (at !== null) caret.current = caretAfterDigits(next, phoneDigits(raw.slice(0, at)).length);
    onChange(next);
  }

  const filled = value.trim() !== '';
  const problem = filled && !hasSpokenDigits(value) ? checkPhone(value) : null;
  const showProblem = problem !== null && (touched || phoneDigits(value).length >= 12);
  const hintId = `${id}-hint`;
  return (
    <div className="ed-site-field">
      <label htmlFor={id}>{label}</label>
      <input
        ref={input}
        id={id}
        className="ed-input"
        type="tel"
        inputMode="tel"
        autoComplete="tel"
        placeholder="예: 010-1234-5678"
        value={value}
        disabled={disabled}
        aria-invalid={showProblem || undefined}
        aria-describedby={hintId}
        onChange={(e) => change(e.target.value, e.target.selectionStart)}
        onBlur={() => setTouched(true)}
      />
      <span id={hintId} className={showProblem ? 'ed-field-msg ed-field-msg--bad' : 'ed-field-msg'} aria-live="polite">
        {showProblem ? problem : filled && !problem ? `✓ ${value}` : '숫자만 눌러도 - 가 저절로 들어가요'}
      </span>
    </div>
  );
}
