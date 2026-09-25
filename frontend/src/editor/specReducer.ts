// 편집 규칙 순수 함수 (D27: set_content만 허용).
// - 스키마에 없는 필드 거부, 최대 길이·형식 위반 거부
// - locked 필드는 needsConfirm 반환, force로 적용
// - 적용마다 version+1, history 기록, undo/redo
// - 자리 표시 목록(D23) + 공개 가능 여부
import type { DesignSection, DesignSpec, PlaceholderSlot, SectionType } from './types';

export interface HistoryEntry {
  version: number;
  sectionId: string;
  key: string;
  prevValue: unknown;
  nextValue: unknown;
  forced: boolean;
  at: string;
}

export interface EditorState {
  spec: DesignSpec;
  past: DesignSpec[];
  future: DesignSpec[];
  history: HistoryEntry[];
}

export interface ApplyResult {
  state: EditorState;
  ok: boolean;
  needsConfirm?: boolean;
  error?: string;
}

interface FieldRule {
  maxLength?: number;
  pattern?: RegExp;
  itemFields?: Record<string, { maxLength?: number; pattern?: RegExp }>;
  maxItems?: number;
}

/** SPEC §2 content 스키마 중 편집기가 검사하는 부분 (문자열 필드 + items). */
const SCHEMA: Record<SectionType, Record<string, FieldRule>> = {
  hero: {
    title: { maxLength: 30 },
    subtitle: { maxLength: 60 },
    image: {},
    cta: {},
  },
  intro: {
    body: { maxLength: 300 },
    owner_name: { maxLength: 20 },
    stats: { maxItems: 4, itemFields: { value: { maxLength: 10 }, label: { maxLength: 12 } } },
  },
  offerings: {
    label: { maxLength: 12 },
    items: {
      maxItems: 12,
      itemFields: {
        name: { maxLength: 30 },
        desc: { maxLength: 80 },
        price: { maxLength: 20 },
      },
    },
  },
  gallery: {
    items: {
      maxItems: 12,
      itemFields: { alt: { maxLength: 60 } },
    },
  },
  around: {
    address: { maxLength: 80 },
    map_url: { pattern: /^https:\/\/(map\.kakao\.com|maps\.google\.com|naver\.me)\// },
    items: {
      maxItems: 8,
      itemFields: { name: { maxLength: 30 }, note: { maxLength: 60 } },
    },
  },
  contact: {
    phone: { maxLength: 20 },
    hours: { maxLength: 80 },
    address: { maxLength: 80 },
    channel_url: { pattern: /^https:\/\// },
    booking_url: { pattern: /^https:\/\// },
  },
  reviews: {
    items: {
      maxItems: 6,
      itemFields: {
        quote: { maxLength: 140 },
        author: { maxLength: 20 },
        source: { maxLength: 30 },
      },
    },
  },
  cta: {
    phone: { maxLength: 20 },
    booking_url: { pattern: /^https:\/\// },
    channel_url: { pattern: /^https:\/\// },
  },
};

const HREF_PATTERN = /^(tel:|https:\/\/|#)/;
const PHONE_CHARS = /^[0-9+\-() ]*$/;

function isBlank(v: unknown): boolean {
  return v === undefined || v === null || (typeof v === 'string' && v.trim() === '');
}

export function getSection(spec: DesignSpec, sectionId: string): DesignSection | undefined {
  return spec.sections.find((s) => s.id === sectionId);
}

export function isLocked(spec: DesignSpec, sectionId: string, key: string): boolean {
  return spec.locked.includes(`${sectionId}.${key}`);
}

function checkString(rule: FieldRule, value: string, key: string): string | null {
  if (rule.maxLength !== undefined && value.length > rule.maxLength) {
    return `${key}: 최대 ${rule.maxLength}자까지 입력할 수 있어요 (지금 ${value.length}자)`;
  }
  if (rule.pattern && value !== '' && !rule.pattern.test(value)) {
    return `${key}: 형식이 맞지 않아요`;
  }
  return null;
}

function checkItems(rule: FieldRule, value: unknown, key: string): string | null {
  if (!Array.isArray(value)) return `${key}: 목록 형태여야 해요`;
  if (rule.maxItems !== undefined && value.length > rule.maxItems) {
    return `${key}: 최대 ${rule.maxItems}개까지 입력할 수 있어요`;
  }
  if (rule.itemFields) {
    for (let i = 0; i < value.length; i += 1) {
      const item = value[i] as Record<string, unknown>;
      if (typeof item !== 'object' || item === null) return `${key}[${i}]: 항목 형태가 맞지 않아요`;
      for (const [fk, fr] of Object.entries(rule.itemFields)) {
        const fv = item[fk];
        if (fv === undefined || fv === null || fv === '') continue;
        if (typeof fv !== 'string') return `${key}[${i}].${fk}: 글자로 입력해 주세요`;
        if (fr.maxLength !== undefined && fv.length > fr.maxLength) {
          return `${key}[${i}].${fk}: 최대 ${fr.maxLength}자까지 입력할 수 있어요`;
        }
      }
    }
  }
  return null;
}

/** set_content 값 검증. ok=false면 error에 사유. */
export function validateSetContent(
  spec: DesignSpec,
  sectionId: string,
  key: string,
  value: unknown,
): { ok: boolean; error?: string } {
  const section = getSection(spec, sectionId);
  if (!section) return { ok: false, error: `없는 섹션 ID예요: ${sectionId}` };
  const rules = SCHEMA[section.type];
  const rule = rules[key];
  if (!rule) return { ok: false, error: `이 항목은 직접 고칠 수 없어요: ${sectionId}.${key}` };
  if (value === undefined || value === null) {
    return { ok: true };
  }
  if (key === 'items') {
    const err = checkItems(rule, value, key);
    return err ? { ok: false, error: err } : { ok: true };
  }
  if (key === 'cta' || key === 'stats') {
    if (typeof value !== 'object') return { ok: false, error: `${key}: 형태가 맞지 않아요` };
    if (key === 'cta') {
      const cta = value as { label?: unknown; href?: unknown };
      if (cta.label !== undefined && cta.label !== null && cta.label !== '') {
        if (typeof cta.label !== 'string') return { ok: false, error: 'cta.label: 글자로 입력해 주세요' };
        if (cta.label.length > 12) return { ok: false, error: 'cta.label: 최대 12자까지 입력할 수 있어요' };
      }
      if (cta.href !== undefined && cta.href !== null && cta.href !== '') {
        if (typeof cta.href !== 'string' || !HREF_PATTERN.test(cta.href)) {
          return { ok: false, error: 'cta.href: tel:·https://·# 로 시작해야 해요' };
        }
      }
    }
    return { ok: true };
  }
  if (typeof value !== 'string') return { ok: false, error: `${key}: 글자로 입력해 주세요` };
  const err = checkString(rule, value, key);
  if (err) return { ok: false, error: err };
  if (key === 'phone' && value !== '' && !PHONE_CHARS.test(value)) {
    return { ok: false, error: 'phone: 숫자·+·-·괄호·공백만 입력할 수 있어요' };
  }
  return { ok: true };
}

export function initialEditorState(spec: DesignSpec): EditorState {
  return { spec, past: [], future: [], history: [] };
}

/** set_content 적용. locked + force 없음 → needsConfirm. 성공 시 version+1. */
export function applySetContent(
  state: EditorState,
  sectionId: string,
  key: string,
  value: unknown,
  opts?: { force?: boolean },
): ApplyResult {
  const { spec } = state;
  if (isLocked(spec, sectionId, key) && !opts?.force) {
    return { state, ok: false, needsConfirm: true };
  }
  const v = validateSetContent(spec, sectionId, key, value);
  if (!v.ok) return { state, ok: false, error: v.error };
  const section = getSection(spec, sectionId);
  if (!section) return { state, ok: false, error: `없는 섹션 ID예요: ${sectionId}` };
  const prevValue = section.content[key];
  if (JSON.stringify(prevValue) === JSON.stringify(value)) {
    return { state, ok: true };
  }
  const nextSpec: DesignSpec = {
    ...spec,
    version: spec.version + 1,
    sections: spec.sections.map((s) =>
      s.id === sectionId ? { ...s, content: { ...s.content, [key]: value } } : s,
    ),
  };
  const entry: HistoryEntry = {
    version: nextSpec.version,
    sectionId,
    key,
    prevValue,
    nextValue: value,
    forced: Boolean(opts?.force && isLocked(spec, sectionId, key)),
    at: new Date().toISOString(),
  };
  return {
    state: {
      spec: nextSpec,
      past: [...state.past, spec],
      future: [],
      history: [...state.history, entry],
    },
    ok: true,
  };
}

export function undo(state: EditorState): EditorState {
  if (state.past.length === 0) return state;
  const prev = state.past[state.past.length - 1];
  return {
    spec: prev,
    past: state.past.slice(0, -1),
    future: [state.spec, ...state.future],
    history: state.history,
  };
}

export function redo(state: EditorState): EditorState {
  if (state.future.length === 0) return state;
  const [next, ...rest] = state.future;
  return {
    spec: next,
    past: [...state.past, state.spec],
    future: rest,
    history: state.history,
  };
}

export function canUndo(state: EditorState): boolean {
  return state.past.length > 0;
}

export function canRedo(state: EditorState): boolean {
  return state.future.length > 0;
}

/** 자리 표시 칸 목록 (공개 전 필수, D23). */
export function listPlaceholders(spec: DesignSpec): PlaceholderSlot[] {
  const out: PlaceholderSlot[] = [];
  for (const section of spec.sections) {
    const c = section.content;
    if (section.type === 'hero' && isBlank(c['title'])) {
      out.push({ sectionId: section.id, key: 'title', label: '가게 이름', placeholder: '[가게 이름 입력]' });
    }
    if ((section.type === 'contact' || section.type === 'cta') && isBlank(c['phone'])) {
      out.push({ sectionId: section.id, key: 'phone', label: '전화번호', placeholder: '[전화번호 입력]' });
    }
    if (section.type === 'contact' && isBlank(c['hours'])) {
      out.push({ sectionId: section.id, key: 'hours', label: '영업시간', placeholder: '[영업시간 입력]' });
    }
    if ((section.type === 'contact' || section.type === 'around') && isBlank(c['address'])) {
      out.push({ sectionId: section.id, key: 'address', label: '주소', placeholder: '[주소 입력]' });
    }
    if (section.type === 'offerings') {
      const items = c['items'];
      if (!Array.isArray(items) || items.length === 0) {
        out.push({ sectionId: section.id, key: 'items', label: '상품·메뉴', placeholder: '[메뉴 입력]' });
      } else {
        (items as Array<Record<string, unknown>>).forEach((item, i) => {
          if (isBlank(item['price'])) {
            const name = typeof item['name'] === 'string' && item['name'] !== '' ? String(item['name']) : `항목 ${i + 1}`;
            out.push({
              sectionId: section.id,
              key: 'items',
              itemIndex: i,
              label: `${name} 가격`,
              placeholder: '[가격 입력]',
            });
          }
        });
      }
    }
  }
  // cta.phone은 contact.phone과 같은 사실(D24)이다. contact 섹션이 있으면
  // cta 쪽은 중복 집계하지 않는다(원본 contact만 채우면 됨).
  if (spec.sections.some((s) => s.type === 'contact')) {
    const dup = out.findIndex((p) => p.key === 'phone' && getSection(spec, p.sectionId)?.type === 'cta');
    if (dup >= 0) out.splice(dup, 1);
  }
  return out;
}

/** 공개 가능 여부 (빈 자리 표시가 없으면 공개 가능). */
export function isPublishable(spec: DesignSpec): { publishable: boolean; missing: PlaceholderSlot[] } {
  const missing = listPlaceholders(spec);
  return { publishable: missing.length === 0, missing };
}
