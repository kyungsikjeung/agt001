// 실시간 미리보기 계획 (COMPONENT_ENGINE_PLAN §5).
// 미리보기 iframe에 지금 무엇이 그려져 있는지(FrameState)와 새 미리보기를 비교해
// 바뀐 구역만 바꿔 끼울지(patch), 통째로 다시 불러올지(full) 정한다. DOM·네트워크 없이 순수 계산만 한다
// (extractParts만 DOMParser를 쓴다).
import type { CardPreview, PreviewPart, PreviewTheme, StyleAxis } from './cardApi';

/** iframe에 지금 그려진 것: 뼈대 해시, 구역별 해시, 토큰. */
export interface FrameState {
  shell: string;
  hashes: Record<string, string>;
  theme: PreviewTheme | null;
}

export type UpdatePlan =
  | { kind: 'full' }
  | { kind: 'patch'; parts: { id: string; html: string }[]; order: string[]; theme: PreviewTheme | null };

export function frameStateOf(p: { shell?: string; parts?: PreviewPart[]; theme?: PreviewTheme }): FrameState | null {
  if (!p.shell || !Array.isArray(p.parts)) return null;
  const hashes: Record<string, string> = {};
  for (const part of p.parts) hashes[part.id] = part.hash;
  return { shell: p.shell, hashes, theme: p.theme ?? null };
}

/** 완전한 문서에서 구역 뿌리(data-section-id)의 HTML을 꺼낸다. */
export function extractParts(html: string, ids: string[]): Record<string, string> {
  const out: Record<string, string> = {};
  const want = new Set(ids);
  if (want.size === 0) return out;
  const doc = new DOMParser().parseFromString(html, 'text/html');
  for (const el of Array.from(doc.querySelectorAll('[data-section-id]'))) {
    const id = el.getAttribute('data-section-id') ?? '';
    if (want.has(id) && !(id in out)) out[id] = el.outerHTML;
  }
  return out;
}

export function sameTheme(a: PreviewTheme | null, b: PreviewTheme | null | undefined): boolean {
  if (!a || !b) return a === (b ?? null);
  if (a.css !== b.css || a.motion !== b.motion) return false;
  const ka = Object.keys(a.attrs).sort();
  const kb = Object.keys(b.attrs).sort();
  return ka.join(',') === kb.join(',') && ka.every((k) => a.attrs[k] === b.attrs[k]);
}

/** 새 미리보기(GET /preview)를 iframe에 반영하는 방법. 뼈대가 같으면 바뀐 구역 조각·토큰만. */
export function planUpdate(frame: FrameState | null, next: CardPreview): UpdatePlan {
  if (!frame || !next.shell || !next.parts || !next.order || frame.shell !== next.shell) return { kind: 'full' };
  const changed = next.parts.filter((p) => frame.hashes[p.id] !== p.hash).map((p) => p.id);
  const html = extractParts(next.html, changed);
  if (changed.some((id) => !(id in html))) return { kind: 'full' };
  return {
    kind: 'patch',
    parts: changed.map((id) => ({ id, html: html[id] })),
    order: next.order,
    theme: sameTheme(frame.theme, next.theme ?? null) ? null : (next.theme ?? null),
  };
}

/** 고른 스타일 축 → <body> 속성 (서버 components.body_attrs와 같은 규칙: 기본값·모르는 값은 빼기). */
export function styleAttrs(styles: Record<string, StyleAxis>, picked: Record<string, string>): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [axis, spec] of Object.entries(styles)) {
    const v = picked[axis];
    if (typeof v === 'string' && v in spec.values && v !== spec.default) out[`data-${axis}`] = v;
  }
  return out;
}
