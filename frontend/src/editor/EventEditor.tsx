// 초대·기념(청첩장) 고치기 칸: 양가 연락처·마음 전하실 곳 (EVENT_INVITE_PLAN).
// 측마다 최대 4줄. 저장하면 시안의 예시 대신 이 값이 보이고 공개 사이트에도 나간다.
import { useEffect, useState } from 'react';
import { readMemberId, saveCard, type CardEvent, type EventAccount, type EventPerson, type RoomCard } from './cardApi';

type Kind = 'family' | 'gift';
type Row = Record<string, string>;
type Side = { side: string; rows: Row[] };

const MAX_ROWS = 4;
const COLS: Record<Kind, { key: string; label: string; placeholder: string; inputMode?: 'tel' | 'numeric' }[]> = {
  family: [
    { key: 'role', label: '관계', placeholder: '아버지' },
    { key: 'name', label: '이름', placeholder: '김철수' },
    { key: 'phone', label: '전화번호', placeholder: '010-0000-0000', inputMode: 'tel' },
  ],
  gift: [
    { key: 'role', label: '관계', placeholder: '신랑' },
    { key: 'holder', label: '예금주', placeholder: '김민준' },
    { key: 'bank', label: '은행', placeholder: '국민은행' },
    { key: 'number', label: '계좌번호', placeholder: '123456-01-234567', inputMode: 'numeric' },
  ],
};

/** 카드의 묶음 → 편집용 줄. 아직 넣지 않은 계좌는 예시 은행·번호를 비운다. */
function toSides(event: CardEvent | undefined, kind: Kind): Side[] {
  if (!event) return [];
  if (kind === 'family') {
    return event.family.map((s) => ({ side: s.side, rows: s.people.map((p) => ({ role: p.role, name: p.name, phone: p.phone ?? '' })) }));
  }
  const fresh = !event.saved.gift;
  return event.gift.map((s) => ({
    side: s.side,
    rows: s.accounts.map((a) => ({ role: a.role, holder: a.holder, bank: fresh ? '' : a.bank, number: fresh ? '' : a.number })),
  }));
}

function emptyRow(kind: Kind): Row {
  return Object.fromEntries(COLS[kind].map((c) => [c.key, '']));
}

export default function EventEditor({
  roomId,
  card,
  kind,
  onSaved,
}: {
  roomId: string;
  card: RoomCard;
  kind: Kind;
  onSaved: (card: RoomCard) => void;
}) {
  const [sides, setSides] = useState<Side[]>(() => toSides(card.event, kind));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [info, setInfo] = useState('');

  useEffect(() => {
    setSides(toSides(card.event, kind));
    setError('');
    setInfo('');
  }, [card, kind]);

  function setCell(si: number, ri: number, key: string, value: string) {
    setSides((prev) => prev.map((s, i) => (i !== si ? s : { ...s, rows: s.rows.map((r, j) => (j !== ri ? r : { ...r, [key]: value })) })));
  }

  function addRow(si: number) {
    setSides((prev) => prev.map((s, i) => (i !== si || s.rows.length >= MAX_ROWS ? s : { ...s, rows: [...s.rows, emptyRow(kind)] })));
  }

  function removeRow(si: number, ri: number) {
    setSides((prev) => prev.map((s, i) => (i !== si ? s : { ...s, rows: s.rows.filter((_, j) => j !== ri) })));
  }

  async function save() {
    setSaving(true);
    setError('');
    setInfo('');
    try {
      const payload =
        kind === 'family'
          ? { family: sides.map((s) => ({ side: s.side, people: s.rows as unknown as EventPerson[] })) }
          : { gift: sides.map((s) => ({ side: s.side, accounts: s.rows as unknown as EventAccount[] })) };
      const updated = await saveCard(roomId, readMemberId(), {}, undefined, { event: payload });
      onSaved(updated);
      setInfo('저장했어요.');
    } catch (e) {
      setError(e instanceof Error && !e.message.startsWith('저장하지 못했습니다') ? e.message : '저장하지 못했어요. 잠시 뒤 다시 눌러 주세요.');
    } finally {
      setSaving(false);
    }
  }

  if (sides.length === 0) return <p className="ed-site-hint">먼저 채팅에서 주인공 이름을 알려 주세요.</p>;

  return (
    <div className="ed-event">
      <p className="ed-site-hint">
        {kind === 'family' ? '번호를 넣으면 손님이 바로 전화·문자할 수 있어요.' : '계좌는 측마다 접혀 있다가, 손님이 누르면 펼쳐져요.'}
      </p>
      {sides.map((s, si) => (
        <fieldset key={s.side} className="ed-event__side">
          <legend>{s.side}</legend>
          {s.rows.map((row, ri) => (
            <div key={ri} className="ed-event__row">
              {COLS[kind].map((c) => (
                <label key={c.key} className="ed-event__cell">
                  <span>{c.label}</span>
                  <input
                    className="ed-input"
                    type="text"
                    inputMode={c.inputMode}
                    value={row[c.key] ?? ''}
                    placeholder={c.placeholder}
                    maxLength={40}
                    disabled={saving}
                    onChange={(e) => setCell(si, ri, c.key, e.target.value)}
                  />
                </label>
              ))}
              <button type="button" className="ed-btn ed-event__remove" disabled={saving} onClick={() => removeRow(si, ri)} aria-label={`${s.side} ${ri + 1}번째 줄 지우기`}>
                지우기
              </button>
            </div>
          ))}
          {s.rows.length < MAX_ROWS ? (
            <button type="button" className="ed-btn" disabled={saving} onClick={() => addRow(si)}>
              + {kind === 'family' ? '사람' : '계좌'} 더하기
            </button>
          ) : null}
        </fieldset>
      ))}
      <div className="ed-site-save">
        <button type="button" className="ed-btn ed-btn--primary ed-btn--block" disabled={saving} onClick={() => void save()}>
          {saving ? '저장 중…' : '저장'}
        </button>
      </div>
      {error ? (
        <p className="ed-error" role="alert">
          {error}
        </p>
      ) : null}
      {info ? <p role="status">{info}</p> : null}
    </div>
  );
}
