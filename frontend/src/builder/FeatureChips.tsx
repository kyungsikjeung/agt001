// 기능 칩 줄 (BUILDER_CONTRACT §3 3번). 가로로 밀기, 켜진 칩은 채움.
import type { FeatureChip } from '../editor/cardApi';

export default function FeatureChips({
  features,
  busyKey,
  onToggle,
}: {
  features: FeatureChip[];
  busyKey: string | null;
  onToggle: (chip: FeatureChip) => void;
}) {
  return (
    <div className="bd-chips" role="group" aria-label="기능 켜고 끄기">
      {features.map((c) => (
        <button
          key={c.key}
          type="button"
          className={c.on ? 'bd-chip on' : 'bd-chip'}
          aria-pressed={c.on}
          disabled={busyKey === c.key}
          onClick={() => onToggle(c)}
        >
          {c.label}
        </button>
      ))}
    </div>
  );
}
