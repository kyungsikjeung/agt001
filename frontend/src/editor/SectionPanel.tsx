// 보며 고치기 구역 패널 (EDIT_WAVE2_CONTRACT §4).
// bind별로 칸을 열고, 아래에 구역 위로·아래로·숨기기를 둔다. locked면 공통 버튼을 그리지 않는다.
// 실시간 (COMPONENT_ENGINE_PLAN §5·§6): 칸을 고치는 동안 미리보기에 바로 그리고(onDraft, 저장 안 함),
// 같은 데이터로 바꿔 쓸 수 있는 구역 모양(shapes)을 고르면 미리보기에 먼저 보인 뒤 저장한다.
import { useEffect, useState } from 'react';
import AddressSearch from '../builder/AddressSearch';
import AroundEditor from './AroundEditor';
import EventEditor from './EventEditor';
import GuestbookAdmin from './GuestbookAdmin';
import RsvpSummary from './RsvpSummary';
import StaffEditor from './StaffEditor';
import { nextPhone, phoneLooksOk } from './phone';
import TimeRangeField from './TimeRangeField';
import { timeModeOf } from './timeRange';
import ItemList, { buildGroupsOp, buildItemOps, groupError, initDrafts, type GroupDraft, type ItemDraft } from './ItemList';
import {
  fetchCard,
  readMemberId,
  saveCard,
  uploadPhoto,
  type CardLayoutEdit,
  type PreviewAddable,
  type PreviewItem,
  type PreviewSection,
  type RoomCard,
} from './cardApi';

/** 그룹이 없을 때 (기본값을 매번 새 배열로 만들면 칸 다시 채우기가 끝없이 돈다) */
const NO_GROUPS: string[] = [];

/** 항목 목록을 쓰는 bind (계약 §4 2번). */
const CATALOG_BINDS = ['catalog', 'classes', 'rooms', 'signature', 'menu_photos'];

type BindKind = 'hero' | 'catalog' | 'location' | 'contact' | 'photos' | 'chat' | 'greeting' | 'when' | 'event' | 'guestbook' | 'rsvp' | 'staff';

/** bind를 패널 종류로 묶는다 (계약 §4 표). */
function kindOf(bind: string): BindKind {
  if (bind === 'hero') return 'hero';
  if (CATALOG_BINDS.includes(bind)) return 'catalog';
  if (bind === 'location') return 'location';
  if (bind === 'booking' || bind === 'dates' || bind === 'order_soon' || bind === 'none' || bind === 'inquiry') {
    return 'contact';
  }
  if (bind === 'space_photos' || bind === 'style_photos') return 'photos';
  // 초대·기념(청첩장): 인사말·날짜와 장소는 카드 칸, 양가 연락처·계좌는 EventEditor
  if (bind === 'greeting') return 'greeting';
  if (bind === 'event') return 'when';
  if (bind === 'family' || bind === 'gift') return 'event';
  if (bind === 'guestbook') return 'guestbook';
  if (bind === 'rsvp') return 'rsvp';
  // 공방·학원 선생님 구역 (BUILDER_FIX_1003_CONTRACT S2)
  if (bind === 'staff') return 'staff';
  return 'chat';
}

/** 종류별 fields 칸 (계약 §4 표). */
function fieldKeys(kind: BindKind): string[] {
  if (kind === 'hero') return ['shop_name', 'detail', 'hours', 'location'];
  if (kind === 'location') return ['location', 'hours', 'phone'];
  if (kind === 'contact') return ['phone', 'contact_method', 'hours'];
  if (kind === 'greeting') return ['detail'];
  if (kind === 'when') return ['hours', 'location'];
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

export interface SectionPanelProps {
  roomId: string;
  card: RoomCard;
  sections: PreviewSection[];
  addable: PreviewAddable[];
  added: string[];
  baseItems: PreviewItem[];
  /** 지금 보이는 그룹 순서 (GROUP_CARDS_CONTRACT §2-6) */
  baseGroups?: string[];
  variant: string;
  selectedId: string | null;
  clickedText: string;
  onSelect: (id: string) => void;
  onSaved: (card: RoomCard, sectionId: string) => void;
  /** 고치는 중인 칸 값(저장된 값과 다른 것만). 미리보기가 저장 전에 그린다 */
  onDraft?: (fields: Record<string, string>) => void;
  /** 저장 전에 미리보기에 먼저 그릴 구역 편집(모양 바꾸기) */
  onPreviewLayout?: (layout: CardLayoutEdit) => void;
}

export default function SectionPanel({
  roomId,
  card,
  sections,
  addable,
  added: addedIds,
  baseItems,
  baseGroups = NO_GROUPS,
  variant,
  selectedId,
  clickedText,
  onSelect,
  onSaved,
  onDraft,
  onPreviewLayout,
}: SectionPanelProps) {
  const selected = sections.find((s) => s.id === selectedId) ?? null;
  const kind: BindKind | null = selected ? kindOf(selected.bind) : null;
  const keys = kind ? fieldKeys(kind) : [];

  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [items, setItems] = useState<ItemDraft[]>([]);
  const [groups, setGroups] = useState<GroupDraft[]>([]);
  const [expanded, setExpanded] = useState<string[]>([]);
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
    const drafts = initDrafts(names, baseItems, baseGroups);
    setItems(drafts.items);
    setGroups(drafts.groups);
    const hit = clickedText.trim();
    setExpanded(hit && names.includes(hit) ? [hit] : []);
    setError('');
    setInfo('');
    setConfirmReset(false);
  }, [card, baseItems, baseGroups, clickedText, selected?.bind, selectedId]);

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
  const shapes = selected.shapes ?? [];
  const currentShape = selected.variant ?? '';

  /** 칸 하나를 고친다. 저장된 값과 다른 칸만 미리보기에 보낸다(모두 같으면 빈 값 = 저장된 모양으로). */
  function editField(k: string, raw: string) {
    // 전화번호는 치는 동안 010-1234-5678로 나눠 보인다(저장 형식은 서버가 같은 규칙으로 맞춤)
    const value = k === 'phone' ? nextPhone(drafts[k] ?? '', raw) : raw;
    const next = { ...drafts, [k]: value };
    setDrafts(next);
    if (!onDraft) return;
    const fields: Record<string, string> = {};
    for (const key of keys) {
      const cur = next[key] ?? '';
      if (cur !== fieldVal(card, key)) fields[key] = cur;
    }
    onDraft(fields);
  }

  /** 구역 모양 바꾸기: 미리보기에 먼저 그리고 저장한다. 기본 모양으로 돌아가면 그 구역 값을 뺀다. */
  function changeShape(v: string) {
    const variants: Record<string, string> = {};
    for (const s of sections) {
      if (s.variant && s.base_variant && s.variant !== s.base_variant) variants[s.id] = s.variant;
    }
    if (v === selected?.base_variant) delete variants[selId];
    else variants[selId] = v;
    const layout: CardLayoutEdit = { variant, order: orderIds, hidden: hiddenIds, added: addedIds, variants };
    onPreviewLayout?.(layout);
    void sendLayout(layout);
  }

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
      const ops = kind === 'catalog' ? buildItemOps(items, groups, offeringNames(card), baseItems) : [];
      const groupsOp = kind === 'catalog' ? buildGroupsOp(groups, baseGroups) : null;
      if (groupsOp) {
        const bad = groupError(groups);
        if (bad) {
          setError(bad);
          return;
        }
      }
      if (Object.keys(fields).length === 0 && ops.length === 0 && !groupsOp) return;
      const extra = ops.length > 0 || groupsOp ? { ...(ops.length > 0 ? { items: ops } : {}), ...(groupsOp ? { groups: groupsOp } : {}) } : undefined;
      const updated = await saveCard(roomId, readMemberId(), fields, undefined, extra);
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

        {shapes.length > 1 ? (
          <fieldset className="ed-shapes">
            <legend>모양</legend>
            <div className="ed-shapes__list">
              {shapes.map((sh) => (
                <button
                  key={sh.variant}
                  type="button"
                  className="ed-shape"
                  aria-pressed={currentShape === sh.variant}
                  disabled={saving}
                  onClick={() => currentShape !== sh.variant && changeShape(sh.variant)}
                >
                  <span className="ed-shape__name">
                    {sh.name}
                    {sh.new ? <span className="ed-shape__new">새</span> : null}
                  </span>
                  <span className="ed-shape__desc">{sh.desc}</span>
                </button>
              ))}
            </div>
          </fieldset>
        ) : null}

        {kind === 'chat' ? <p>이 구역의 내용은 채팅으로 말해 주세요.</p> : null}

        {kind === 'location' || kind === 'when' ? (
          <AddressSearch roomId={roomId} onSaved={(c) => onSaved(c, selected.id)} />
        ) : null}

        {keys.map((k) => {
          // 체크인·아웃 / 영업·수업 시간은 버튼으로 빠르게 고른다(날짜·장소 칸의 시간은 글 그대로)
          const timeMode = k === 'hours' && kind !== 'when' ? timeModeOf(fieldLabel(card, k)) : null;
          if (timeMode) {
            return (
              <TimeRangeField
                key={k}
                id={`ed-site-${selected.id}-${k}`}
                label={fieldLabel(card, k)}
                mode={timeMode}
                value={drafts[k] ?? ''}
                disabled={saving}
                onChange={(v) => editField(k, v)}
              />
            );
          }
          return (
            <label key={k} className="ed-site-field" htmlFor={`ed-site-${selected.id}-${k}`}>
              {fieldLabel(card, k)}
              <input
                id={`ed-site-${selected.id}-${k}`}
                className="ed-input"
                type={k === 'phone' ? 'tel' : 'text'}
                inputMode={k === 'phone' ? 'tel' : undefined}
                autoComplete={k === 'phone' ? 'tel' : undefined}
                placeholder={k === 'phone' ? '010-0000-0000' : undefined}
                value={drafts[k] ?? ''}
                disabled={saving}
                aria-describedby={k === 'phone' && !phoneLooksOk(drafts[k] ?? '') ? `ed-site-${selected.id}-phone-hint` : undefined}
                onChange={(e) => editField(k, e.target.value)}
              />
              {k === 'phone' && !phoneLooksOk(drafts[k] ?? '') ? (
                <span id={`ed-site-${selected.id}-phone-hint`} className="ed-site-hint ed-site-hint--warn">
                  번호가 덜 들어간 것 같아요. 예: 010-1234-5678
                </span>
              ) : null}
            </label>
          );
        })}

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
          <ItemList
            sectionId={selected.id}
            items={items}
            groups={groups}
            grouped={selected.bind === 'catalog'}
            saving={saving}
            photoBusy={photoBusy}
            expanded={expanded}
            setItems={setItems}
            setGroups={setGroups}
            setExpanded={setExpanded}
            onPhoto={(file, tag) => void onPhoto(file, tag)}
          />
        ) : null}

        {kind === 'guestbook' ? <GuestbookAdmin roomId={roomId} /> : null}

        {kind === 'rsvp' ? <RsvpSummary roomId={roomId} /> : null}

        {kind === 'event' ? (
          <EventEditor roomId={roomId} card={card} kind={selected.bind === 'gift' ? 'gift' : 'family'} onSaved={(c) => onSaved(c, selId)} />
        ) : null}

        {kind === 'staff' ? <StaffEditor roomId={roomId} card={card} onSaved={(c) => onSaved(c, selId)} /> : null}

        {kind === 'hero' || kind === 'catalog' || kind === 'location' || kind === 'contact' || kind === 'greeting' || kind === 'when' ? (
          <div className="ed-site-save">
            <button type="button" className="ed-btn ed-btn--primary ed-btn--block" disabled={saving} onClick={() => void saveContent()}>
              {saving ? '저장 중…' : '저장'}
            </button>
          </div>
        ) : null}

        {kind === 'location' ? <AroundEditor roomId={roomId} card={card} onSaved={(c) => onSaved(c, selId)} /> : null}

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
