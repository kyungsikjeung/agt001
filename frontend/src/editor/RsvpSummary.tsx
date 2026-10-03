// 청첩장 참석 여부 집계 (빌더 '참석 여부' 칸): 합계·측별 인원·명단.
import { useEffect, useState } from 'react';
import { getRsvp, readMemberId, type RsvpSummary as Summary } from './cardApi';

export default function RsvpSummary({ roomId }: { roomId: string }) {
  const [data, setData] = useState<Summary | null>(null);
  const [error, setError] = useState('');
  const [onlyComing, setOnlyComing] = useState(false);

  useEffect(() => {
    let alive = true;
    getRsvp(roomId, readMemberId())
      .then((d) => alive && setData(d))
      .catch(() => alive && setError('참석 여부를 불러오지 못했어요.'));
    return () => {
      alive = false;
    };
  }, [roomId]);

  if (error) return <p className="ed-error" role="alert">{error}</p>;
  if (!data) return <p role="status">참석 여부를 불러오는 중…</p>;
  const t = data.total;
  const rows = onlyComing ? data.entries.filter((e) => e.attend) : data.entries;
  return (
    <div className="ed-rsvp">
      {data.entries.length === 0 ? (
        <p className="ed-site-hint">공개하면 하객이 보낸 참석 여부가 여기에 모여요.</p>
      ) : (
        <>
          <dl className="ed-rsvp__totals">
            <div><dt>참석 인원</dt><dd>{t.people ?? 0}명</dd></div>
            <div><dt>식사</dt><dd>{t.meal ?? 0}명</dd></div>
            <div><dt>불참</dt><dd>{t.declined ?? 0}건</dd></div>
            <div><dt>응답</dt><dd>{t.replies ?? 0}건</dd></div>
          </dl>
          {Object.keys(data.sides).length > 0 ? (
            <p className="ed-rsvp__sides">
              {Object.entries(data.sides).map(([side, n]) => `${side} ${n}명`).join(' · ')}
            </p>
          ) : null}
          <label className="ed-rsvp__filter">
            <input type="checkbox" checked={onlyComing} onChange={(e) => setOnlyComing(e.target.checked)} /> 참석만 보기
          </label>
          <ul className="ed-rsvp__list">
            {rows.map((e) => (
              <li key={e.id} className={e.attend ? 'ed-rsvp__item' : 'ed-rsvp__item is-declined'}>
                <p className="ed-rsvp__who">
                  <b>{e.name}</b> {e.side ? <span>{e.side}</span> : null}
                  <span className="ed-rsvp__state">{e.attend ? `참석 ${e.count}명${e.meal ? ' · 식사' : ''}` : '불참'}</span>
                </p>
                {e.note ? <p className="ed-rsvp__note">{e.note}</p> : null}
                {e.contact ? <p className="ed-rsvp__contact">{e.contact}</p> : null}
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
