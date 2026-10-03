// 보며 고치기 항목 목록: 그룹 아래 카드 (GROUP_CARDS_CONTRACT §3).
// 상태는 SectionPanel이 갖고(저장 본문을 만든다), 여기서는 칸을 그린다.
import { useState, type Dispatch, type SetStateAction } from 'react';
import type { CardGroupsEdit, CardItemEdit, PreviewItem } from './cardApi';
import PriceField from './fields/PriceField';

export type ItemPhoto = 'own' | 'auto' | 'none';

export interface ItemDraft {
  key: number;
  prevName: string;
  name: string;
  price: string;
  note: string;
  /** GroupDraft.key. 그룹이 없으면 null */
  group: number | null;
  photo: ItemPhoto;
  /** 내 사진이 있는 항목 (사진 없음으로 바꿨다 되돌릴 때 "내 사진") */
  hasOwn: boolean;
  touched: boolean;
}

export interface GroupDraft {
  key: number;
  /** 서버에 있던 이름. 새 그룹이면 null */
  prevName: string | null;
  name: string;
}

export const GROUP_MAX = 10;
export const ITEM_MAX = 20;
const GROUP_NAME_MAX = 12;
const GROUP_BAD = /[,·/]/;

/** 서버의 지금 값으로 칸을 채운다. 그룹은 지금 보이는 그대로 시작한다 (§2-6). */
export function initDrafts(
  names: string[],
  baseItems: PreviewItem[],
  baseGroups: string[],
): { items: ItemDraft[]; groups: GroupDraft[] } {
  const groups: GroupDraft[] = baseGroups.map((g, i) => ({ key: i, prevName: g, name: g }));
  const keyOf = new Map(groups.map((g) => [g.name, g.key]));
  const base = new Map(baseItems.map((b) => [b.name, b]));
  const items = names.map((n, i) => {
    const b = base.get(n);
    return {
      key: i,
      prevName: n,
      name: n,
      price: b?.price ?? '',
      note: b?.note ?? '',
      group: keyOf.get(b?.group ?? '') ?? groups[0]?.key ?? null,
      photo: b?.photo ?? 'auto',
      hasOwn: b?.photo === 'own',
      touched: false,
    };
  });
  return { items, groups };
}

/** 그룹 이름 규칙 (§1-1). 문제가 없으면 빈 글. */
export function groupError(groups: GroupDraft[]): string {
  const names = groups.map((g) => g.name.trim());
  if (names.length > GROUP_MAX) return `그룹은 ${GROUP_MAX}개까지예요`;
  if (names.some((n) => !n || n.length > GROUP_NAME_MAX || GROUP_BAD.test(n))) {
    return '그룹 이름은 1~12자로, 쉼표·가운뎃점·빗금 없이 적어 주세요';
  }
  if (new Set(names).size !== names.length) return '같은 이름의 그룹이 있어요';
  return '';
}

/** 그룹 목록이 바뀌었으면 groups 본문, 그대로면 null (§3-4). */
export function buildGroupsOp(groups: GroupDraft[], baseGroups: string[]): CardGroupsEdit | null {
  const order = groups.map((g) => g.name.trim());
  const rename: Record<string, string> = {};
  for (const g of groups) {
    if (g.prevName !== null && g.name.trim() !== g.prevName) rename[g.prevName] = g.name.trim();
  }
  const renamed = Object.keys(rename).length > 0;
  if (!renamed && order.length === baseGroups.length && order.every((n, i) => n === baseGroups[i])) return null;
  return renamed ? { order, rename } : { order };
}

/** 항목 목록을 items ops로 바꾼다 (EDIT_WAVE2 §2.2, 그룹 카드 §3-4). 손대지 않은 줄은 안 보낸다. */
export function buildItemOps(
  items: ItemDraft[],
  groups: GroupDraft[],
  orig: string[],
  baseItems: PreviewItem[],
): CardItemEdit[] {
  const ops: CardItemEdit[] = [];
  const kept = new Set(items.map((it) => it.prevName));
  for (const name of orig) {
    if (!kept.has(name)) ops.push({ name, remove: true });
  }
  const nameOf = (key: number | null) => groups.find((g) => g.key === key)?.name.trim();
  // 처음 있던 그룹(이름을 바꿨어도 같은 그룹)
  const keyOfBase = (group: string | undefined) => groups.find((g) => g.prevName !== null && g.prevName === group)?.key;
  for (const it of items) {
    const name = it.name.trim();
    if (!name) continue;
    const group = nameOf(it.group);
    if (!orig.includes(it.prevName)) {
      const op: CardItemEdit = { name, add: true };
      if (it.price.trim()) op.price = it.price.trim();
      if (it.note.trim()) op.note = it.note.trim();
      if (group) op.group = group;
      if (it.photo === 'none') op.photo = 'none';
      ops.push(op);
      continue;
    }
    if (!it.touched) continue;
    const was = baseItems.find((b) => b.name === it.prevName);
    const op: CardItemEdit = { name: it.prevName };
    if (name !== it.prevName) {
      op.rename = name;
      op.price = it.price.trim();
      op.note = it.note.trim();
    } else if (it.price.trim() !== (was?.price ?? '') || it.note.trim() !== (was?.note ?? '')) {
      // 지운 가격·설명도 보낸다(빈 글 = 삭제)
      op.price = it.price.trim();
      op.note = it.note.trim();
    }
    if (group && it.group !== keyOfBase(was?.group)) op.group = group;
    if (it.photo !== (was?.photo ?? 'auto')) op.photo = it.photo === 'none' ? 'none' : 'auto';
    if (Object.keys(op).length > 1) ops.push(op);
  }
  return ops;
}

export interface ItemListProps {
  sectionId: string;
  items: ItemDraft[];
  groups: GroupDraft[];
  /** 그룹 묶음으로 그릴지 (분류 구역만) */
  grouped: boolean;
  saving: boolean;
  photoBusy: boolean;
  expanded: string[];
  setItems: Dispatch<SetStateAction<ItemDraft[]>>;
  setGroups: Dispatch<SetStateAction<GroupDraft[]>>;
  setExpanded: Dispatch<SetStateAction<string[]>>;
  onPhoto: (file: File | undefined, tag: string) => void;
}

export default function ItemList({
  sectionId,
  items,
  groups,
  grouped,
  saving,
  photoBusy,
  expanded,
  setItems,
  setGroups,
  setExpanded,
  onPhoto,
}: ItemListProps) {
  const [newNames, setNewNames] = useState<Record<string, string>>({});
  const [newGroup, setNewGroup] = useState('');
  const [menu, setMenu] = useState<number | null>(null);
  const [confirmDel, setConfirmDel] = useState<number | null>(null);
  const [msg, setMsg] = useState('');
  const full = items.length >= ITEM_MAX;

  function patch(key: number, p: Partial<ItemDraft>) {
    setItems((prev) => prev.map((it) => (it.key === key ? { ...it, ...p, touched: true } : it)));
  }

  function addItem(slot: string, group: number | null) {
    const name = (newNames[slot] ?? '').trim();
    if (!name || full) return;
    if (items.some((it) => it.name.trim() === name)) {
      setMsg('같은 이름의 항목이 있어요');
      return;
    }
    setItems((prev) => [
      ...prev,
      { key: Date.now(), prevName: name, name, price: '', note: '', group, photo: 'auto', hasOwn: false, touched: true },
    ]);
    setExpanded((prev) => [...prev, name]);
    setNewNames((prev) => ({ ...prev, [slot]: '' }));
    setMsg('');
  }

  function addGroup() {
    const name = newGroup.trim();
    const next = [...groups, { key: Date.now(), prevName: null, name }];
    const err = groupError(next);
    if (err) {
      setMsg(err);
      return;
    }
    setGroups(next);
    if (groups.length === 0) setItems((prev) => prev.map((it) => ({ ...it, group: next[0].key })));
    setNewGroup('');
    setMsg('');
  }

  function moveGroup(key: number, dir: -1 | 1) {
    setGroups((prev) => {
      const i = prev.findIndex((g) => g.key === key);
      const j = i + dir;
      if (i < 0 || j < 0 || j >= prev.length) return prev;
      const next = [...prev];
      [next[i], next[j]] = [next[j], next[i]];
      return next;
    });
  }

  // 지운 그룹의 항목은 첫 그룹으로 간다(서버와 같은 규칙, §2-2). 마지막 그룹이면 그룹 없음.
  function deleteGroup(key: number) {
    const rest = groups.filter((g) => g.key !== key);
    setGroups(rest);
    setItems((prev) => prev.map((it) => (it.group === key ? { ...it, group: rest[0]?.key ?? null } : it)));
    setConfirmDel(null);
    setMenu(null);
  }

  function card(it: ItemDraft) {
    const open = expanded.includes(it.prevName);
    const own = it.hasOwn;
    return (
      <li key={it.key} className="ed-item">
        <button
          type="button"
          aria-expanded={open}
          onClick={() =>
            setExpanded((prev) => (prev.includes(it.prevName) ? prev.filter((n) => n !== it.prevName) : [...prev, it.prevName]))
          }
        >
          {it.prevName}
          {it.photo === 'none' ? <span className="ed-item__tag">사진 없음</span> : null}
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
                onChange={(e) => patch(it.key, { name: e.target.value })}
              />
            </label>
            {/* 가격: 공용 단위 칸(UnitValueField). 숫자로 적으면 4,500원 모양으로 저장 — 나중에 결제 금액으로 그대로 쓴다 */}
            <PriceField price={it.price} disabled={saving} onChange={(price) => patch(it.key, { price })} />
            <label className="ed-site-field">
              설명
              <input
                className="ed-input"
                type="text"
                value={it.note}
                maxLength={80}
                disabled={saving}
                onChange={(e) => patch(it.key, { note: e.target.value })}
              />
            </label>
            {grouped && groups.length > 0 ? (
              <label className="ed-site-field">
                그룹
                <select
                  className="ed-input"
                  value={it.group ?? ''}
                  disabled={saving}
                  onChange={(e) => patch(it.key, { group: Number(e.target.value) })}
                >
                  {groups.map((g) => (
                    <option key={g.key} value={g.key}>
                      {g.name.trim() || '(이름 없음)'}
                    </option>
                  ))}
                </select>
              </label>
            ) : null}
            <fieldset className="ed-photo-pick">
              <legend>사진</legend>
              <label>
                <input
                  type="radio"
                  name={`ed-photo-${sectionId}-${it.key}`}
                  checked={it.photo !== 'none'}
                  disabled={saving}
                  onChange={() => patch(it.key, { photo: own ? 'own' : 'auto' })}
                />
                {own ? '내 사진' : '예시 사진'}
              </label>
              <label>
                <input
                  type="radio"
                  name={`ed-photo-${sectionId}-${it.key}`}
                  checked={it.photo === 'none'}
                  disabled={saving}
                  onChange={() => patch(it.key, { photo: 'none' })}
                />
                사진 없음
              </label>
            </fieldset>
            <label className="ed-site-field ed-file">
              항목 사진 올리기
              <input
                type="file"
                accept="image/*"
                disabled={photoBusy}
                onChange={(e) => onPhoto(e.target.files?.[0], `item:${it.name.trim() || it.prevName}`)}
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
  }

  function adder(slot: string, group: number | null, label: string) {
    const id = `ed-site-${sectionId}-new-${slot}`;
    return (
      <div className="ed-item-add">
        <label className="ed-site-field" htmlFor={id}>
          {label}
          <input
            id={id}
            className="ed-input"
            type="text"
            value={newNames[slot] ?? ''}
            maxLength={30}
            disabled={saving || full}
            onChange={(e) => setNewNames((prev) => ({ ...prev, [slot]: e.target.value }))}
          />
        </label>
        <button
          type="button"
          className="ed-btn"
          disabled={saving || full || !(newNames[slot] ?? '').trim()}
          onClick={() => addItem(slot, group)}
        >
          더하기
        </button>
      </div>
    );
  }

  const showGroups = grouped && groups.length > 0;

  return (
    <div className="ed-item-list">
      <h3>항목</h3>
      {showGroups ? (
        groups.map((g, i) => {
          const inGroup = items.filter((it) => it.group === g.key);
          const title = g.name.trim() || '(이름 없음)';
          return (
            <section key={g.key} className="ed-group" aria-label={`${title} 그룹`}>
              <h4 className="ed-group__head">
                <button type="button" aria-expanded={menu === g.key} onClick={() => setMenu((m) => (m === g.key ? null : g.key))}>
                  {title} <span className="ed-group__count">{inGroup.length}개</span>
                </button>
              </h4>
              {menu === g.key ? (
                <div className="ed-group__menu">
                  <label className="ed-site-field">
                    그룹 이름
                    <input
                      className="ed-input"
                      type="text"
                      value={g.name}
                      maxLength={GROUP_NAME_MAX}
                      disabled={saving}
                      onChange={(e) =>
                        setGroups((prev) => prev.map((x) => (x.key === g.key ? { ...x, name: e.target.value } : x)))
                      }
                    />
                  </label>
                  <div className="ed-sheet-row">
                    <button type="button" className="ed-btn" disabled={saving || i === 0} onClick={() => moveGroup(g.key, -1)}>
                      그룹 위로
                    </button>
                    <button
                      type="button"
                      className="ed-btn"
                      disabled={saving || i === groups.length - 1}
                      onClick={() => moveGroup(g.key, 1)}
                    >
                      그룹 아래로
                    </button>
                    <button type="button" className="ed-btn" disabled={saving} onClick={() => setConfirmDel(g.key)}>
                      그룹 지우기
                    </button>
                  </div>
                  {confirmDel === g.key ? (
                    <div className="ed-sheet-row" role="group" aria-label="그룹 지우기 확인">
                      <p className="ed-site-hint">
                        {groups.length > 1 ? '안의 항목은 첫 그룹으로 가요. 지울까요?' : '그룹이 없어지고 항목은 자동으로 나눠져요. 지울까요?'}
                      </p>
                      <button type="button" className="ed-btn ed-btn--primary" onClick={() => deleteGroup(g.key)}>
                        지우기
                      </button>
                      <button type="button" className="ed-btn" onClick={() => setConfirmDel(null)}>
                        그만두기
                      </button>
                    </div>
                  ) : null}
                </div>
              ) : null}
              <ul>{inGroup.map(card)}</ul>
              {adder(String(g.key), g.key, `${title}에 새 항목`)}
            </section>
          );
        })
      ) : (
        <>
          <ul>{items.map(card)}</ul>
          {adder('flat', null, '새 항목 이름')}
        </>
      )}
      {grouped ? (
        <div className="ed-item-add ed-group-add">
          <label className="ed-site-field" htmlFor={`ed-site-${sectionId}-newgroup`}>
            새 그룹 이름
            <input
              id={`ed-site-${sectionId}-newgroup`}
              className="ed-input"
              type="text"
              value={newGroup}
              maxLength={GROUP_NAME_MAX}
              placeholder="예: 파스타"
              disabled={saving || groups.length >= GROUP_MAX}
              onChange={(e) => setNewGroup(e.target.value)}
            />
          </label>
          <button
            type="button"
            className="ed-btn"
            disabled={saving || groups.length >= GROUP_MAX || !newGroup.trim()}
            onClick={addGroup}
          >
            + 그룹 추가
          </button>
        </div>
      ) : null}
      {full ? <p className="ed-site-hint">항목은 {ITEM_MAX}개까지예요.</p> : null}
      {msg ? (
        <p className="ed-error" role="alert">
          {msg}
        </p>
      ) : null}
    </div>
  );
}
