// 보며 고치기 구역 패널 (EDIT_WAVE2_CONTRACT §4).
// bind별로 칸을 열고, 아래에 구역 위로·아래로·숨기기를 둔다. locked면 공통 버튼을 그리지 않는다.
import { useEffect, useState } from 'react';
import {
  fetchCard,
  readMemberId,
  saveCard,
  uploadPhoto,
  type CardItemEdit,
  type CardLayoutEdit,
  type PreviewAddable,
  type PreviewItem,
  type PreviewSection,
  type RoomCard,
} from './cardApi';

/** 항목 목록을 쓰는 bind (계약 §4 2번). */
const CATALOG_BINDS = ['catalog', 'classes', 'rooms', 'signature', 'menu_photos'];

type BindKind = 'hero' | 'catalog' | 'location' | 'contact' | 'photos' | 'chat';

/** bind를 패널 종류로 묶는다 (계약 §4 표). */
function kindOf(bind: string): BindKind {
  if (bind === 'hero') return 'hero';
  if (CATALOG_BINDS.includes(bind)) return 'catalog';
  if (bind === 'location') return 'location';
  if (bind === 'booking' || bind === 'dates' || bind === 'order_soon' || bind === 'none' || bind === 'inquiry') {
    return 'contact';
  }
  if (bind === 'space_photos' || bind === 'style_photos') return 'photos';
  return 'chat';
}

/** 종류별 fields 칸 (계약 §4 표). */
function fieldKeys(kind: BindKind): string[] {
  if (kind === 'hero') return ['shop_name', 'detail', 'hours', 'location'];
  if (kind === 'location') return ['location', 'hours', 'phone'];
  if (kind === 'contact') return ['phone', 'contact_method', 'hours'];
  return [];
}

function fieldVal(card: RoomCard, key: string): string {
  return card.fields.find((f) => f.key === key)?.value ?? '';
}

function fieldLabel(card: RoomCard, key: string): string {
  return card.fields.find((f) => f.key === key)?.label ?? key;
}

/** offerings 칸 값을 이름 목록으로 푼다. */
function offeringNames(card: RoomCard): string[] {
  const raw = fieldVal(card, 'offerings');
  return raw
    .split(',')
    .map((v) => v.trim())
    .filter((v) => v !== '');
}

interface ItemDraft {
  key: number;
  prevName: string;
  name: string;
  price: string;
  note: string;
  touched: boolean;
}

export interface SectionPanelProps {
  roomId: string;
  card: RoomCard;
  sections: PreviewSection[];
  addable: PreviewAddable[];
  added: string[];
  baseItems: PreviewItem[];
  variant: string;
  selectedId: string | null;
  clickedText: string;
  onSelect: (id: string) => void;
  onSaved: (card: RoomCard, sectionId: string) => void;
}

export default function SectionPanel({
  roomId,
  card,
  sections,
  addable,
  added: addedIds,
  baseItems,
  variant,
  selectedId,
  clickedText,
  onSelect,
  onSaved,
}: SectionPanelProps) {
  const selected = sections.find((s) => s.id === selectedId) ?? null;
  const kind: BindKind | null = selected ? kindOf(selected.bind) : null;
  const keys = kind ? fieldKeys(kind) : [];

  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [items, setItems] = useState<ItemDraft[]>([]);
  const [expanded, setExpanded] = useState<string[]>([]);
  const [newName, setNewName] = useState('');
  const [confirmReset, setConfirmReset] = useState(false);
  const [saving, setSaving] = useState(false);
  const [photoBusy, setPhotoBusy] = useState(false);
  const [error, setError] = useState('');
  const [info, setInfo] = useState('');

  // 고른 구역·카드가 바뀌면 칸을 다시 채운다. 누른 글자가 항목 이름과 같으면 먼저 펼친다.
  useEffect(() => {
    const d: Record<string, string> = {};
    for (const k of fieldKeys(kindOf(selected?.bind ?? ''))) d[k] = fieldVal(card, k);
    setDrafts(d);
    const names = offeringNames(card);
    const base = new Map(baseItems.map((b) => [b.name, b]));
    setItems(names.map((n, i) => ({
      key: i, prevName: n, name: n, price: base.get(n)?.price ?? '', note: base.get(n)?.note ?? '', touched: false,
    })));
    const hit = clickedText.trim();
    setExpanded(hit && names.includes(hit) ? [hit] : []);
    setNewName('');
    setError('');
    setInfo('');
    setConfirmReset(false);
  }, [card, baseItems, clickedText, selected?.bind, selectedId]);

  // 구역 고르기 전에도 "구역 더하기"가 쓰므로 조기 반환보다 앞에 둔다
  const orderIds = sections.map((s) => s.id);
  const hiddenIds = sections.filter((s) => s.hidden).map((s) => s.id);

  if (!selected || !kind) {
    return (
      <div className="ed-site-panel">
        <SectionList
          sections={sections}
          addable={addable}
          selectedId={selectedId}
          saving={saving}
          confirmReset={confirmReset}
          onSelect={onSelect}
          onAdd={(id) => void addSection(id)}
          onAskReset={() => setConfirmReset(true)}
          onCancelReset={() => setConfirmReset(false)}
          onReset={() => void resetLayout()}
        />
        <p className="ed-site-hint">미리보기에서 고칠 곳을 누르세요.</p>
      </div>
    );
  }

  const selId = selected.id;
  const index = orderIds.indexOf(selId);

  async function sendLayout(layout: CardLayoutEdit) {
    setSaving(true);
    setError('');
    setInfo('');
    try {
      const updated = await saveCard(roomId, readMemberId(), {}, undefined, { layout });
      onSaved(updated, selId);
      setInfo('저장했어요.');
    } catch {
      setError('저장하지 못했어요. 잠시 뒤 다시 눌러 주세요.');
    } finally {
      setSaving(false);
    }
  }

  function move(dir: -1 | 1) {
    const next = [...orderIds];
    const j = index + dir;
    if (index < 0 || j < 0 || j >= next.length) return;
    [next[index], next[j]] = [next[j], next[index]];
    void sendLayout({ variant, order: next, hidden: hiddenIds, added: addedIds });
  }

  function toggleHide() {
    const isHidden = sections.find((s) => s.id === selId)?.hidden ?? false;
    const hidden = isHidden ? hiddenIds.filter((id) => id !== selId) : [...hiddenIds, selId];
    void sendLayout({ variant, order: orderIds, hidden, added: addedIds });
  }

  async function addSection(id: string) {
    const added = addedIds.includes(id) ? addedIds : [...addedIds, id];
    setSaving(true);
    setError('');
    setInfo('');
    try {
      const updated = await saveCard(roomId, readMemberId(), {}, undefined, {
        layout: { variant, order: [...orderIds, id], hidden: hiddenIds, added },
      });
      onSaved(updated, id);
      onSelect(id);
      setInfo('구역을 더했어요.');
    } catch {
      setError('저장하지 못했어요. 잠시 뒤 다시 눌러 주세요.');
    } finally {
      setSaving(false);
    }
  }

  async function resetLayout() {
    setConfirmReset(false);
    setSaving(true);
    setError('');
    setInfo('');
    try {
      const updated = await saveCard(roomId, readMemberId(), {}, undefined, {
        layout: { variant, reset: true },
      });
      onSaved(updated, selectedId ?? '');
      setInfo('처음 모양으로 되돌렸어요.');
    } catch {
      setError('저장하지 못했어요. 잠시 뒤 다시 눌러 주세요.');
    } finally {
      setSaving(false);
    }
  }

  /** 항목 목록을 items ops로 바꾼다 (계약 §2.2). 손대지 않은 줄은 안 보낸다. */
  function buildItemOps(orig: string[]): CardItemEdit[] {
    const ops: CardItemEdit[] = [];
    const kept = new Set(items.map((it) => it.prevName));
    for (const name of orig) {
      if (!kept.has(name)) ops.push({ name, remove: true });
    }
    for (const it of items) {
      const name = it.name.trim();
      if (!name) continue;
      const isNew = !orig.includes(it.prevName);
      if (isNew) {
        const op: CardItemEdit = { name, add: true };
        if (it.price.trim()) op.price = it.price.trim();
        if (it.note.trim()) op.note = it.note.trim();
        ops.push(op);
      } else if (it.touched) {
        if (name !== it.prevName) {
          const op: CardItemEdit = { name: it.prevName, rename: name };
          op.price = it.price.trim();
          op.note = it.note.trim();
          ops.push(op);
        } else {
          // 지운 가격·설명도 보낸다(빈 글 = 삭제). 그대로면 안 보낸다.
          const was = baseItems.find((b) => b.name === name);
          if (it.price.trim() !== (was?.price ?? '') || it.note.trim() !== (was?.note ?? '')) {
            ops.push({ name, price: it.price.trim(), note: it.note.trim() });
          }
        }
      }
    }
    return ops;
  }

  async function saveContent() {
    setSaving(true);
    setError('');
    setInfo('');
    try {
      const fields: Record<string, string> = {};
      for (const k of keys) {
        const cur = drafts[k] ?? '';
        if (cur !== fieldVal(card, k)) fields[k] = cur;
      }
      const ops = kind === 'catalog' ? buildItemOps(offeringNames(card)) : [];
      if (Object.keys(fields).length === 0 && ops.length === 0) return;
      const updated = await saveCard(
        roomId,
        readMemberId(),
        fields,
        undefined,
        ops.length > 0 ? { items: ops } : undefined,
      );
      onSaved(updated, selId);
      setInfo('저장했어요.');
    } catch {
      setError('저장하지 못했어요. 잠시 뒤 다시 눌러 주세요.');
    } finally {
      setSaving(false);
    }
  }

  async function onPhoto(file: File | undefined, tag: string) {
    if (!file) return;
    setPhotoBusy(true);
    setError('');
    try {
      await uploadPhoto(roomId, readMemberId(), file, tag);
      const updated = await fetchCard(roomId, readMemberId());
      onSaved(updated, selId);
      setInfo('사진을 올렸어요.');
    } catch {
      setError('사진을 올리지 못했어요.');
    } finally {
      setPhotoBusy(false);
    }
  }

  function toggleExpand(name: string) {
    setExpanded((prev) => (prev.includes(name) ? prev.filter((n) => n !== name) : [...prev, name]));
  }

  function patchItem(key: number, patch: Partial<ItemDraft>) {
    setItems((prev) => prev.map((it) => (it.key === key ? { ...it, ...patch, touched: true } : it)));
  }

  return (
    <div className="ed-site-panel">
      <SectionList
        sections={sections}
        addable={addable}
        selectedId={selectedId}
        saving={saving}
        confirmReset={confirmReset}
        onSelect={onSelect}
        onAdd={(id) => void addSection(id)}
        onAskReset={() => setConfirmReset(true)}
        onCancelReset={() => setConfirmReset(false)}
        onReset={() => void resetLayout()}
      />

      <section aria-label={`${selected.label} 고치기`}>
        <h2>{selected.label}</h2>

        {kind === 'chat' ? <p>이 구역의 내용은 채팅으로 말해 주세요.</p> : null}

        {keys.map((k) => (
          <label key={k} className="ed-site-field" htmlFor={`ed-site-${selected.id}-${k}`}>
            {fieldLabel(card, k)}
            <input
              id={`ed-site-${selected.id}-${k}`}
              className="ed-input"
              type="text"
              value={drafts[k] ?? ''}
              disabled={saving}
              onChange={(e) => setDrafts((prev) => ({ ...prev, [k]: e.target.value }))}
            />
          </label>
        ))}

        {kind === 'hero' ? (
          <label className="ed-site-field ed-file" htmlFor={`ed-site-${selected.id}-photo`}>
            대표 사진 바꾸기
            <input
              id={`ed-site-${selected.id}-photo`}
              type="file"
              accept="image/*"
              disabled={photoBusy}
              onChange={(e) => void onPhoto(e.target.files?.[0], 'hero')}
            />
          </label>
        ) : null}

        {kind === 'photos' ? (
          <label className="ed-site-field ed-file" htmlFor={`ed-site-${selected.id}-photo`}>
            사진 올리기
            <input
              id={`ed-site-${selected.id}-photo`}
              type="file"
              accept="image/*"
              disabled={photoBusy}
              onChange={(e) => void onPhoto(e.target.files?.[0], 'space')}
            />
          </label>
        ) : null}

        {kind === 'catalog' ? (
          <div className="ed-item-list">
            <h3>항목</h3>
            <ul>
              {items.map((it) => {
                const open = expanded.includes(it.prevName);
                return (
                  <li key={it.key} className="ed-item">
                    <button type="button" aria-expanded={open} onClick={() => toggleExpand(it.prevName)}>
                      {it.prevName}
                    </button>
                    {open ? (
                      <div className="ed-item-form">
                        <label className="ed-site-field">
                          이름
                          <input
                            className="ed-input"
                            type="text"
                            value={it.name}
                            maxLength={30}
                            disabled={saving}
                            onChange={(e) => patchItem(it.key, { name: e.target.value })}
                          />
                        </label>
                        <label className="ed-site-field">
                          가격
                          <input
                            className="ed-input"
                            type="text"
                            value={it.price}
                            maxLength={20}
                            placeholder="예: 4,500원"
                            disabled={saving}
                            onChange={(e) => patchItem(it.key, { price: e.target.value })}
                          />
                        </label>
                        <label className="ed-site-field">
                          설명
                          <input
                            className="ed-input"
                            type="text"
                            value={it.note}
                            maxLength={80}
                            disabled={saving}
                            onChange={(e) => patchItem(it.key, { note: e.target.value })}
                          />
                        </label>
                        <label className="ed-site-field ed-file">
                          항목 사진 올리기
                          <input
                            type="file"
                            accept="image/*"
                            disabled={photoBusy}
                            onChange={(e) => void onPhoto(e.target.files?.[0], `item:${it.name.trim() || it.prevName}`)}
                          />
                        </label>
                        <button
                          type="button"
                          className="ed-btn"
                          disabled={saving}
                          onClick={() => setItems((prev) => prev.filter((x) => x.key !== it.key))}
                        >
                          빼기
                        </button>
                      </div>
                    ) : null}
                  </li>
                );
              })}
            </ul>
            <div className="ed-item-add">
              <label className="ed-site-field" htmlFor={`ed-site-${selected.id}-new`}>
                새 항목 이름
                <input
                  id={`ed-site-${selected.id}-new`}
                  className="ed-input"
                  type="text"
                  value={newName}
                  maxLength={30}
                  disabled={saving}
                  onChange={(e) => setNewName(e.target.value)}
                />
              </label>
              <button
                type="button"
                className="ed-btn"
                disabled={saving || !newName.trim()}
                onClick={() => {
                  const name = newName.trim();
                  if (!name) return;
                  setItems((prev) => [
                    ...prev,
                    { key: Date.now(), prevName: name, name, price: '', note: '', touched: true },
                  ]);
                  setExpanded((prev) => [...prev, name]);
                  setNewName('');
                }}
              >
                더하기
              </button>
            </div>
          </div>
        ) : null}

        {kind === 'hero' || kind === 'catalog' || kind === 'location' || kind === 'contact' ? (
          <button type="button" className="ed-btn ed-btn--primary ed-btn--block" disabled={saving} onClick={() => void saveContent()}>
            {saving ? '저장 중…' : '저장'}
          </button>
        ) : null}

        {selected.locked ? null : (
          <div className="ed-sheet-row" aria-label="구역 순서·숨기기">
            <button type="button" className="ed-btn" disabled={saving || index <= 0} onClick={() => move(-1)}>
              구역 위로
            </button>
            <button
              type="button"
              className="ed-btn"
              disabled={saving || index < 0 || index >= orderIds.length - 1}
              onClick={() => move(1)}
            >
              구역 아래로
            </button>
            <button type="button" className="ed-btn" disabled={saving} onClick={() => toggleHide()}>
              {selected.hidden ? '보이기' : '숨기기'}
            </button>
          </div>
        )}

        {error ? (
          <p className="ed-error" role="alert">
            {error}
          </p>
        ) : null}
        {info ? <p role="status">{info}</p> : null}
      </section>
    </div>
  );
}

function SectionList({
  sections,
  addable,
  selectedId,
  saving,
  confirmReset,
  onSelect,
  onAdd,
  onAskReset,
  onCancelReset,
  onReset,
}: {
  sections: PreviewSection[];
  addable: PreviewAddable[];
  selectedId: string | null;
  saving: boolean;
  confirmReset: boolean;
  onSelect: (id: string) => void;
  onAdd: (id: string) => void;
  onAskReset: () => void;
  onCancelReset: () => void;
  onReset: () => void;
}) {
  return (
    <nav aria-label="구역 목록">
      <button type="button" className="ed-btn" disabled={saving} onClick={onAskReset}>
        이 안 처음 모양으로
      </button>
      {confirmReset ? (
        <div role="dialog" aria-label="처음 모양으로 되돌리기">
          <p>이 안을 처음 모양으로 되돌릴까요?</p>
          <div className="ed-sheet-row">
            <button type="button" className="ed-btn" onClick={onCancelReset}>
              그대로 두기
            </button>
            <button type="button" className="ed-btn ed-btn--primary" disabled={saving} onClick={onReset}>
              되돌리기
            </button>
          </div>
        </div>
      ) : null}
      <ul className="ed-sec-list">
        {sections.map((s) => (
          <li key={s.id}>
            <button
              type="button"
              aria-current={s.id === selectedId}
              disabled={saving}
              onClick={() => onSelect(s.id)}
            >
              {s.label}
              {s.hidden ? ' (숨김)' : ''}
            </button>
          </li>
        ))}
      </ul>
      {addable.length > 0 ? (
        <div className="ed-sec-add">
          <h3>구역 더하기</h3>
          <ul className="ed-sec-list">
            {addable.map((a) => (
              <li key={a.id}>
                <button type="button" disabled={saving} onClick={() => onAdd(a.id)}>
                  + {a.label}
                </button>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </nav>
  );
}
