// 주변 안내 고치기 (10/4 대표 요청). 줄마다 대제목(장소 이름) + 소제목(도보 n분·차로 n분·거리·직접 글) + 사진,
// 그리고 글 배치(위아래·배지·한 줄)를 고른다. 공용 부품 RowListEditor·UnitValueField·OptionCards로 만든다.
// 사진은 저장된 이름에만 올린다(nearby:<이름> 태그). 이름을 바꿔 저장하면 prev_name으로 사진이 따라간다.
import { useEffect, useRef, useState } from 'react';
import {
  fetchCard,
  readMemberId,
  saveCard,
  uploadPhoto,
  type CardNearby,
  type NearbyStyle,
  type NearbyUnit,
  type RoomCard,
} from './cardApi';
import OptionCards from './fields/OptionCards';
import RowListEditor from './fields/RowListEditor';
import UnitValueField, { NEARBY_UNITS } from './fields/UnitValueField';

interface Row {
  key: number;
  prev: string;
  name: string;
  unit: NearbyUnit;
  value: string;
  photo: string;
}

const MAX = 8;
let seq = 0;

function toRows(n: CardNearby | undefined): Row[] {
  return (n?.items ?? []).map((i) => ({
    key: ++seq,
    prev: i.name,
    name: i.name,
    unit: i.unit,
    value: i.unit === 'text' ? i.text ?? '' : i.value == null ? '' : String(i.value),
    photo: i.photo ?? '',
  }));
}

/** 사진을 뺀 내용(사진만 바뀌면 고치던 줄을 되돌리지 않게) */
function contentKey(n: CardNearby | undefined): string {
  return JSON.stringify({ s: n?.style, i: (n?.items ?? []).map(({ photo: _p, ...rest }) => rest) });
}

const STYLE_OPTIONS = [
  {
    key: 'stack',
    title: '위아래',
    desc: '이름 아래 작게',
    preview: (
      <span className="ed-optprev__stack">
        <b>해수욕장</b>
        <small>도보 3분</small>
      </span>
    ),
  },
  {
    key: 'badge',
    title: '사진 위 배지',
    desc: '거리를 눈에 띄게',
    preview: (
      <span className="ed-optprev__badge">
        <i>도보 3분</i>
        <b>해수욕장</b>
      </span>
    ),
  },
  {
    key: 'inline',
    title: '한 줄',
    desc: '이름 · 거리',
    preview: (
      <span className="ed-optprev__inline">
        <b>해수욕장</b> · <small>도보 3분</small>
      </span>
    ),
  },
];

export default function NearbyEditor({ roomId, card, onSaved }: { roomId: string; card: RoomCard; onSaved: (c: RoomCard) => void }) {
  const [rows, setRows] = useState<Row[]>(() => toRows(card.nearby));
  const [style, setStyle] = useState<NearbyStyle>(card.nearby?.style ?? 'stack');
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const seen = useRef(contentKey(card.nearby));

  // 서버 내용이 바뀌면 다시 채운다. 사진만 바뀐 경우는 사진 주소만 새로
  useEffect(() => {
    const k = contentKey(card.nearby);
    if (k !== seen.current) {
      seen.current = k;
      setRows(toRows(card.nearby));
      setStyle(card.nearby?.style ?? 'stack');
    } else {
      const photos = new Map((card.nearby?.items ?? []).map((i) => [i.name, i.photo ?? '']));
      setRows((rs) => rs.map((r) => (r.prev && photos.has(r.prev) ? { ...r, photo: photos.get(r.prev) ?? '' } : r)));
    }
  }, [card.nearby]);

  async function save() {
    setBusy(true);
    setMsg(null);
    try {
      const items = rows.map((r) => ({
        name: r.name.trim(),
        unit: r.unit,
        ...(r.unit === 'text' ? { text: r.value.trim() } : { value: r.value === '' ? null : Number(r.value) }),
        ...(r.prev && r.prev !== r.name.trim() ? { prev_name: r.prev } : {}),
      }));
      const updated = await saveCard(roomId, readMemberId(), {}, undefined, { nearby: { items, style } });
      onSaved(updated);
      setMsg({ ok: true, text: '저장했어요.' });
    } catch (e) {
      setMsg({ ok: false, text: e instanceof Error && !e.message.startsWith('저장하지 못했습니다') ? e.message : '저장하지 못했어요. 잠시 뒤 다시 눌러 주세요.' });
    } finally {
      setBusy(false);
    }
  }

  async function photo(row: Row, file: File | undefined) {
    if (!file || !row.prev) return;
    setBusy(true);
    setMsg(null);
    try {
      await uploadPhoto(roomId, readMemberId(), file, `nearby:${row.prev}`);
      onSaved(await fetchCard(roomId, readMemberId()));
      setMsg({ ok: true, text: `${row.prev} 사진을 올렸어요.` });
    } catch {
      setMsg({ ok: false, text: '사진을 올리지 못했어요.' });
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="ed-nearby" aria-label="주변 안내">
      <p className="ed-site-hint">근처 가볼 곳을 적으면 이 구역에 이름과 거리(도보·차로·km)가 함께 보여요. 비우면 예전처럼 사진만 보여요.</p>
      <RowListEditor<Row>
        rows={rows}
        max={MAX}
        noun="장소"
        disabled={busy}
        emptyRow={() => ({ key: ++seq, prev: '', name: '', unit: 'walk', value: '', photo: '' })}
        rowKey={(r) => r.key}
        rowTitle={(r) => r.name.trim() || '새 장소'}
        onChange={setRows}
        renderRow={(r, _i, update) => (
          <div className="ed-row__body">
            <label className="ed-site-field">
              대제목 (장소 이름)
              <input className="ed-input" type="text" maxLength={30} placeholder="예: ○○해수욕장" value={r.name} disabled={busy} onChange={(e) => update({ name: e.target.value })} />
            </label>
            <UnitValueField label="소제목 (거리)" units={NEARBY_UNITS} unit={r.unit} value={r.value} disabled={busy} onChange={(unit, value) => update({ unit: unit as NearbyUnit, value })} />
            <div className="ed-row__photo">
              {r.photo ? <img src={r.photo} alt={`${r.prev} 사진`} width={56} height={42} /> : null}
              {r.prev ? (
                <label className="ed-btn ed-file">
                  {r.photo ? '사진 바꾸기' : '사진 올리기'}
                  <input type="file" accept="image/*" disabled={busy} onChange={(e) => void photo(r, e.target.files?.[0])} />
                </label>
              ) : (
                <span className="ed-field-msg">저장한 뒤 사진을 올릴 수 있어요(사진이 없으면 글 칸으로 보여요)</span>
              )}
            </div>
          </div>
        )}
      />
      <OptionCards legend="글 배치" options={STYLE_OPTIONS} value={style} disabled={busy} onChange={(k) => setStyle(k as NearbyStyle)} />
      <button type="button" className="ed-btn ed-btn--primary" disabled={busy} onClick={() => void save()}>
        {busy ? '저장 중…' : '주변 안내 저장'}
      </button>
      {msg ? (
        <p className={msg.ok ? 'ed-site-hint' : 'ed-error'} role={msg.ok ? 'status' : 'alert'}>
          {msg.text}
        </p>
      ) : null}
    </section>
  );
}
