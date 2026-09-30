// 고칠 곳 한 문장 만들기 (FIX_TAGS_CONTRACT §3).
// 채팅방(room.html)과 같은 표를 쓴다.
// 칩 줄(FixTags)도 여기서 그린다. FixTags.tsx와 fixTags.ts가 한 폴더에 있으면
// macOS+tsc가 './FixTags' 찾기를 fixTags.ts와 헷갈려서, 실체는 여기 둔다.
import { createElement } from 'react';

export interface FixPart {
  key: string;
  label: string;
}

export interface FixTarget {
  key: string;
  label: string;
  current: string;
  parts: FixPart[];
}

/** 새 항목 칩을 고른 표시. parts에 없는 가짜 key다. */
export const FIX_NEW_KEY = '__new__';

/** 새 항목 표시인지 본다. */
export function isNewPart(part: FixPart | null): boolean {
  return part !== null && part.key === FIX_NEW_KEY;
}

/**
 * 보내기 본문 한 문장을 만든다.
 * part가 null이면 일반 칸, key가 FIX_NEW_KEY면 새 항목, 아니면 항목 고치기다.
 * 입력이 이미 칸 이름으로 시작하면 그대로 보낸다.
 */
export function compose(target: FixTarget, part: FixPart | null, text: string): string {
  const t = text.trim();
  if (!t) return '';
  if (t.startsWith(target.label)) return t;
  if (part && part.key !== FIX_NEW_KEY) {
    if (t.startsWith(part.key)) return t;
    if (part.label && t.startsWith(part.label)) return t;
    return `${part.key} ${t}`;
  }
  if (part) return `${target.label}에 ${t} 추가`;
  return `${target.label} ${t}`;
}

/** 칩 1개의 모양. pick이 눌렀을 때 할 일이다. */
interface FixChip {
  key: string;
  label: string;
  pick: () => void;
}

/**
 * 고칠 곳 칩 줄 (FIX_TAGS_CONTRACT §4.2).
 * 칸 칩 → (항목 있으면 항목 칩 + 새 항목 칩) → 맨 끝 직접 말하기 칩.
 * 가로 밀기 모양은 builder.css의 bd-fixtags가 맡는다.
 */
export function FixTags({
  targets,
  active,
  onTarget,
  onPart,
  onDirect,
}: {
  targets: FixTarget[];
  /** 항목 고르는 중인 칸. 없으면 칸 칩을 보인다. */
  active: FixTarget | null;
  onTarget: (t: FixTarget) => void;
  /** part가 null이면 새 항목이다. */
  onPart: (t: FixTarget, part: FixPart | null) => void;
  onDirect: () => void;
}) {
  const chips: FixChip[] = active
    ? [
        ...active.parts.map((p) => ({ key: p.key, label: p.label, pick: () => onPart(active, p) })),
        { key: FIX_NEW_KEY, label: '+ 새 항목', pick: () => onPart(active, null) },
        { key: 'direct', label: '직접 말하기', pick: onDirect },
      ]
    : [
        ...targets.map((t) => ({ key: t.key, label: t.label, pick: () => onTarget(t) })),
        { key: 'direct', label: '직접 말하기', pick: onDirect },
      ];
  return createElement(
    'div',
    { className: 'bd-fixtags', role: 'group', 'aria-label': '고칠 곳' },
    chips.map((c) => createElement('button', { key: c.key, type: 'button', className: 'bd-fixtag', onClick: c.pick }, c.label)),
  );
}
