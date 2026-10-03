// 도움말 말풍선 (공용 부품, 토글팁). ⓘ를 누르면(또는 키보드로 고르면) 아래에 설명이 열리고, 다시 누르거나
// Esc·바깥을 누르면 닫힌다. 마우스를 올려도 보인다. 설명은 aria-live로 읽어 준다.
import { useEffect, useId, useRef, useState, type ReactNode } from 'react';

export interface InfoTipProps {
  /** ⓘ 단추의 이름 (예: "공지 도움말") */
  label: string;
  children: ReactNode;
  /** 처음부터 열어 둘지 (예: 막 켠 직후 한 번) */
  defaultOpen?: boolean;
}

export default function InfoTip({ label, children, defaultOpen = false }: InfoTipProps) {
  const [open, setOpen] = useState(defaultOpen);
  const [hover, setHover] = useState(false);
  const box = useRef<HTMLSpanElement>(null);
  const id = useId();
  const shown = open || hover;

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false);
    };
    const onDown = (e: PointerEvent) => {
      if (box.current && !box.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('keydown', onKey);
    document.addEventListener('pointerdown', onDown);
    return () => {
      document.removeEventListener('keydown', onKey);
      document.removeEventListener('pointerdown', onDown);
    };
  }, [open]);

  return (
    <span className="ed-tip" ref={box} onMouseEnter={() => setHover(true)} onMouseLeave={() => setHover(false)}>
      <button
        type="button"
        className="ed-tip__btn"
        aria-label={label}
        aria-expanded={shown}
        aria-controls={id}
        onClick={() => setOpen((v) => !v)}
      >
        i
      </button>
      <span id={id} className="ed-tip__bubble" role="status" hidden={!shown}>
        {shown ? children : null}
      </span>
    </span>
  );
}
