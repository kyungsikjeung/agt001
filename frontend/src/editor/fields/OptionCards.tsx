// 보기 고르기 카드 (공용 부품). 글로만 고르기 어려운 모양(배치·보기 방식)을 작은 그림과 함께 하나 고른다.
// 주변 안내 글 배치, 사진 구역 보기 방식 등에 쓴다. 모양은 '구역 모양 바꾸기'(.ed-shape)와 같다.
import type { ReactNode } from 'react';

export interface OptionCard {
  key: string;
  title: string;
  desc?: string;
  /** 작은 그림(미리 보기) */
  preview?: ReactNode;
}

export default function OptionCards({
  legend,
  options,
  value,
  disabled,
  onChange,
}: {
  legend: string;
  options: OptionCard[];
  value: string;
  disabled?: boolean;
  onChange: (key: string) => void;
}) {
  return (
    <fieldset className="ed-shapes ed-options">
      <legend>{legend}</legend>
      <div className="ed-shapes__list">
        {options.map((o) => (
          <button
            key={o.key}
            type="button"
            className="ed-shape"
            aria-pressed={o.key === value}
            disabled={disabled}
            onClick={() => onChange(o.key)}
          >
            {o.preview ? <span className="ed-optprev" aria-hidden="true">{o.preview}</span> : null}
            <span className="ed-shape__name">{o.title}</span>
            {o.desc ? <span className="ed-shape__desc">{o.desc}</span> : null}
          </button>
        ))}
      </div>
    </fieldset>
  );
}
