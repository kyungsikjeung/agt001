// 사진 구역 설정 (10/4): 보일 사진 수·움직임. 모양(격자·넘기기·자동 흐름·벽돌 쌓기)은 위 '모양' 카드에서 고른다.
// 누르면 미리보기에 먼저 그리고 저장한다(SectionPanel.changeSettings → 구역 편집 layout.settings).
import type { GallerySettings as Settings } from './cardApi';

export const COUNTS: { value: Settings['count']; label: string }[] = [
  { value: undefined, label: '전체' },
  { value: 3, label: '3장' },
  { value: 6, label: '6장' },
  { value: 9, label: '9장' },
  { value: 12, label: '12장' },
];

export const MOTIONS: { value: Settings['motion']; label: string; desc: string }[] = [
  { value: undefined, label: '기본', desc: '지금 모양 그대로 움직여요.' },
  { value: 'calm', label: '잔잔하게', desc: '자동 흐름이 천천히, 사진에 손대도 커지지 않아요.' },
  { value: 'lively', label: '생동감 있게', desc: '자동 흐름이 빠르게, 손대면 사진이 조금 더 커져요.' },
  { value: 'still', label: '움직임 없음', desc: '나타나기·흐름·확대를 모두 끄고, 자동 흐름은 옆으로 넘기는 띠가 돼요.' },
];

export default function GallerySettings({
  value,
  disabled,
  onChange,
}: {
  value: Settings;
  disabled?: boolean;
  onChange: (patch: Settings) => void;
}) {
  const motion = MOTIONS.find((m) => m.value === value.motion) ?? MOTIONS[0];
  return (
    <fieldset className="ed-gallery-set">
      <legend>사진 보이기</legend>
      <div className="ed-gallery-set__row" role="group" aria-label="보일 사진 수">
        <span className="ed-gallery-set__name">사진 수</span>
        <div className="ed-seg">
          {COUNTS.map((c) => (
            <button key={c.label} type="button" aria-pressed={value.count === c.value} disabled={disabled}
              onClick={() => value.count !== c.value && onChange({ ...value, count: c.value })}>
              {c.label}
            </button>
          ))}
        </div>
      </div>
      <div className="ed-gallery-set__row" role="group" aria-label="움직임">
        <span className="ed-gallery-set__name">움직임</span>
        <div className="ed-seg">
          {MOTIONS.map((m) => (
            <button key={m.label} type="button" aria-pressed={value.motion === m.value} disabled={disabled}
              onClick={() => value.motion !== m.value && onChange({ ...value, motion: m.value })}>
              {m.label}
            </button>
          ))}
        </div>
      </div>
      <p className="ed-site-hint">{motion.desc}</p>
    </fieldset>
  );
}
