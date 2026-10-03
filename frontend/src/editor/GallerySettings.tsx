// 사진 구역 설정 (10/4 대표 요청): 보일 장수·사진 비율·움직임(넘기기 자동·흐름 속도).
// 사진첩 구역(type gallery)에서 '모양' 아래에 보인다. 바꾸면 미리보기에 먼저 보이고 저장된다(구역 편집 opts).
// 움직임은 지금 모양에 맞는 것만: 넘기기(swipe)=자동 넘김 초, 흐름(marquee)=속도. 손님이 움직임 줄이기를 켜면 멈춘다.
import { useId } from 'react';
import OptionCards from './fields/OptionCards';
import type { GalleryOpts } from './cardApi';

const COUNTS: (number | null)[] = [null, 2, 3, 4, 6, 8, 12];
const INTERVALS: (number | null)[] = [null, 3, 5, 7];
const SPEEDS = [
  ['slow', '느리게'],
  ['normal', '보통'],
  ['fast', '빠르게'],
] as const;

const RATIOS = [
  { key: 'wide', title: '가로', desc: '4:3 (기본)', preview: <span className="ed-ratio" style={{ aspectRatio: '4 / 3' }} /> },
  { key: 'square', title: '정사각', desc: '1:1', preview: <span className="ed-ratio" style={{ aspectRatio: '1' }} /> },
  { key: 'tall', title: '세로', desc: '3:4 (사람·건물)', preview: <span className="ed-ratio" style={{ aspectRatio: '3 / 4' }} /> },
];

function ChipRow<T extends string | number | null>({
  label,
  values,
  current,
  name,
  disabled,
  onPick,
}: {
  label: string;
  values: readonly T[];
  current: T;
  name: (v: T) => string;
  disabled?: boolean;
  onPick: (v: T) => void;
}) {
  const id = useId();
  return (
    <div className="ed-set-row">
      <span className="ed-set-row__label" id={id}>{label}</span>
      <div className="ed-chips" role="group" aria-labelledby={id}>
        {values.map((v) => (
          <button key={String(v)} type="button" className="ed-chip" aria-pressed={v === current} disabled={disabled} onClick={() => onPick(v)}>
            {name(v)}
          </button>
        ))}
      </div>
    </div>
  );
}

export default function GallerySettings({
  shape,
  opts,
  disabled,
  onChange,
}: {
  shape: string;
  opts: GalleryOpts;
  disabled?: boolean;
  onChange: (opts: GalleryOpts) => void;
}) {
  const set = (patch: Partial<GalleryOpts>) => {
    const next: GalleryOpts = { ...opts, ...patch };
    for (const k of Object.keys(next) as (keyof GalleryOpts)[]) if (next[k] == null) delete next[k];
    onChange(next);
  };
  return (
    <fieldset className="ed-gallery-set">
      <legend>사진 구역 설정</legend>
      <ChipRow label="보일 장수" values={COUNTS} current={opts.count ?? null} name={(v) => (v == null ? '전부' : `${v}장`)} disabled={disabled} onPick={(v) => set({ count: v })} />
      <OptionCards legend="사진 비율" options={RATIOS} value={opts.ratio ?? 'wide'} disabled={disabled} onChange={(k) => set({ ratio: k === 'wide' ? null : (k as GalleryOpts['ratio']) })} />
      {shape === 'swipe' ? (
        <ChipRow label="자동 넘김" values={INTERVALS} current={opts.autoplay ?? null} name={(v) => (v == null ? '끔' : `${v}초마다`)} disabled={disabled} onPick={(v) => set({ autoplay: v })} />
      ) : null}
      {shape === 'marquee' ? (
        <ChipRow
          label="흐름 속도"
          values={SPEEDS.map(([k]) => k)}
          current={opts.speed ?? 'normal'}
          name={(v) => SPEEDS.find(([k]) => k === v)?.[1] ?? String(v)}
          disabled={disabled}
          onPick={(v) => set({ speed: v === 'normal' ? null : (v as GalleryOpts['speed']) })}
        />
      ) : null}
      <p className="ed-field-msg">
        {shape === 'swipe' || shape === 'marquee'
          ? '손님이 휴대폰에서 움직임 줄이기를 켜면 자동으로 움직이지 않아요. 손을 대면 잠시 멈춰요.'
          : '움직임(자동 넘김·흐름 속도)은 위 모양을 넘기기·흐름으로 바꾸면 고를 수 있어요.'}
      </p>
    </fieldset>
  );
}
