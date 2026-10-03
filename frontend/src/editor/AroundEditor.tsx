// 주변 안내 고치기 칸 (10/4). 오시는 길에 "홍대입구역 · 도보 7분", "해수욕장 · 1.2km" 같은 줄을 넣는다.
// 한 줄 = 장소 이름 + 어떻게(도보·차로·거리·직접) + 값. 숫자만 넣으면 단위(분·km)를 붙인다(서버 site_data.around_note와 같은 규칙).
// 맨 위에서 어느 쪽을 크게(대제목) 보일지 고른다: 장소 이름 / 거리·시간.
// 같은 줄 모양({이름, 작은 글})은 메뉴·결제 항목 칸에도 옮겨 쓸 수 있게 따로 둔다(AROUND_HOWS·aroundNote).
import { useEffect, useState } from 'react';
import { readMemberId, saveCard, type AroundEdit, type AroundItem, type RoomCard } from './cardApi';

export const AROUND_MAX = 8;

export const AROUND_HOWS: { key: AroundItem['how']; label: string; unit: string; placeholder: string }[] = [
  { key: 'walk', label: '도보', unit: '분', placeholder: '3' },
  { key: 'car', label: '차로', unit: '분', placeholder: '10' },
  { key: 'distance', label: '거리', unit: 'km', placeholder: '1.2 또는 800m' },
  { key: 'text', label: '직접 쓰기', unit: '', placeholder: '예: 버스 7번 종점' },
];

/** 자주 넣는 장소 (누르면 그 이름으로 줄이 생긴다) */
const SUGGEST = ['지하철역', '버스 정류장', '주차장', '편의점', '해수욕장', '관광지'];

const EMPTY: AroundEdit = { title: 'place', items: [] };

/** 줄의 안내 글: walk 3 → 도보 3분, distance 1.2 → 1.2km, text는 그대로 */
export function aroundNote(how: AroundItem['how'], value: string): string {
  const v = value.trim().replace(/\s+/g, ' ');
  if (!v) return '';
  const number = /^\d+(?:\.\d+)?$/.test(v);
  if (how === 'walk') return number ? `도보 ${v}분` : `도보 ${v}`;
  if (how === 'car') return number ? `차로 ${v}분` : `차로 ${v}`;
  if (how === 'distance') return number ? `${v}km` : v;
  return v;
}

function emptyRow(name = ''): AroundItem {
  return { name, how: 'walk', value: '' };
}

export default function AroundEditor({
  roomId,
  card,
  onSaved,
}: {
  roomId: string;
  card: RoomCard;
  onSaved: (card: RoomCard) => void;
}) {
  const saved = card.around ?? EMPTY;
  const savedKey = JSON.stringify(saved);
  const [title, setTitle] = useState<AroundEdit['title']>(saved.title);
  const [rows, setRows] = useState<AroundItem[]>(saved.items.length > 0 ? saved.items : [emptyRow()]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [info, setInfo] = useState('');

  // 서버 값이 바뀌었을 때만 다시 채운다(저장 결과 문구는 지우지 않는다)
  useEffect(() => {
    setTitle(saved.title);
    setRows(saved.items.length > 0 ? saved.items : [emptyRow()]);
  }, [savedKey]);

  function setCell(i: number, patch: Partial<AroundItem>) {
    setRows((prev) => prev.map((r, j) => (j !== i ? r : { ...r, ...patch })));
  }

  function addRow(name = '') {
    setRows((prev) => {
      if (prev.length >= AROUND_MAX) return prev;
      // 비어 있는 줄이 하나뿐이면 그 줄에 채운다
      if (name && prev.length === 1 && !prev[0].name.trim() && !prev[0].value.trim()) return [emptyRow(name)];
      return [...prev, emptyRow(name)];
    });
  }

  function removeRow(i: number) {
    setRows((prev) => (prev.length <= 1 ? [emptyRow()] : prev.filter((_, j) => j !== i)));
  }

  async function save() {
    setSaving(true);
    setError('');
    setInfo('');
    try {
      const items = rows
        .map((r) => ({ name: r.name.trim(), how: r.how, value: r.value.trim() }))
        .filter((r) => r.name !== '');
      const updated = await saveCard(roomId, readMemberId(), {}, undefined, { around: { title, items } });
      onSaved(updated);
      setInfo(items.length > 0 ? '저장했어요.' : '주변 안내를 비웠어요.');
    } catch (e) {
      setError(
        e instanceof Error && e.message && !e.message.startsWith('저장하지 못했습니다')
          ? e.message
          : '저장하지 못했어요. 잠시 뒤 다시 눌러 주세요.',
      );
    } finally {
      setSaving(false);
    }
  }

  const sample = rows.find((r) => r.name.trim()) ?? { name: '홍대입구역', how: 'walk' as const, value: '7' };
  const sampleNote = aroundNote(sample.how, sample.value) || '도보 7분';

  return (
    <fieldset className="ed-around">
      <legend>주변 안내</legend>
      <p className="ed-site-hint">역·주차장·관광지까지 얼마나 걸리는지 적으면 오시는 길 위에 보여요.</p>

      <div className="ed-around__title" role="group" aria-label="크게 보일 것">
        <span className="ed-around__label">크게 보일 것</span>
        <div className="ed-seg">
          <button type="button" aria-pressed={title === 'place'} disabled={saving} onClick={() => setTitle('place')}>
            장소 이름
          </button>
          <button type="button" aria-pressed={title === 'distance'} disabled={saving} onClick={() => setTitle('distance')}>
            거리·시간
          </button>
        </div>
        <p className="ed-around__sample" aria-label="보이는 모양 예시">
          <strong>{title === 'place' ? sample.name.trim() : sampleNote}</strong>
          <span>{title === 'place' ? sampleNote : sample.name.trim()}</span>
        </p>
      </div>

      {rows.map((row, i) => {
        const how = AROUND_HOWS.find((h) => h.key === row.how) ?? AROUND_HOWS[0];
        const note = aroundNote(row.how, row.value);
        return (
          <div key={i} className="ed-around__row" role="group" aria-label={`주변 ${i + 1}번째 줄`}>
            <label className="ed-around__cell">
              <span>장소</span>
              <input
                className="ed-input"
                type="text"
                value={row.name}
                placeholder="예: 홍대입구역 3번 출구"
                maxLength={20}
                disabled={saving}
                onChange={(e) => setCell(i, { name: e.target.value })}
              />
            </label>
            <div className="ed-seg ed-around__how" role="group" aria-label="어떻게 가나요">
              {AROUND_HOWS.map((h) => (
                <button key={h.key} type="button" aria-pressed={row.how === h.key} disabled={saving} onClick={() => setCell(i, { how: h.key })}>
                  {h.label}
                </button>
              ))}
            </div>
            <label className="ed-around__cell ed-around__value">
              <span>{row.how === 'text' ? '안내' : row.how === 'distance' ? '거리' : '걸리는 시간'}</span>
              <span className="ed-around__input">
                <input
                  className="ed-input"
                  type="text"
                  inputMode={row.how === 'text' ? undefined : 'decimal'}
                  value={row.value}
                  placeholder={how.placeholder}
                  maxLength={20}
                  disabled={saving}
                  onChange={(e) => setCell(i, { value: e.target.value })}
                />
                {how.unit ? <span className="ed-around__unit" aria-hidden="true">{how.unit}</span> : null}
              </span>
            </label>
            <div className="ed-around__foot">
              <span className="ed-around__note">{row.name.trim() && note ? `${row.name.trim()} · ${note}` : ''}</span>
              <button type="button" className="ed-btn ed-around__remove" disabled={saving} onClick={() => removeRow(i)} aria-label={`주변 ${i + 1}번째 줄 지우기`}>
                지우기
              </button>
            </div>
          </div>
        );
      })}

      {rows.length < AROUND_MAX ? (
        <div className="ed-around__add">
          <button type="button" className="ed-btn" disabled={saving} onClick={() => addRow()}>
            줄 더하기
          </button>
          <div className="ed-seg" role="group" aria-label="자주 넣는 장소">
            {SUGGEST.map((s) => (
              <button key={s} type="button" disabled={saving} onClick={() => addRow(s)}>
                + {s}
              </button>
            ))}
          </div>
        </div>
      ) : (
        <p className="ed-site-hint">주변 안내는 {AROUND_MAX}줄까지예요.</p>
      )}

      <button type="button" className="ed-btn ed-btn--primary ed-btn--block" disabled={saving} onClick={() => void save()}>
        {saving ? '저장 중…' : '주변 안내 저장'}
      </button>
      {error ? <p className="ed-error" role="alert">{error}</p> : null}
      {info ? <p className="ed-site-hint" role="status">{info}</p> : null}
    </fieldset>
  );
}
