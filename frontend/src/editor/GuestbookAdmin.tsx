// 청첩장 방명록 관리 (EVENT_INVITE_PLAN 3단계): 하객이 남긴 글을 최신순으로 보고 지운다.
import { useEffect, useState } from 'react';
import { deleteGuestbook, listGuestbook, readMemberId, type GuestbookEntry } from './cardApi';

function when(ts: string): string {
  const d = new Date(ts);
  return Number.isNaN(d.getTime()) ? '' : d.toLocaleDateString('ko-KR', { month: 'long', day: 'numeric', timeZone: 'Asia/Seoul' });
}

export default function GuestbookAdmin({ roomId }: { roomId: string }) {
  const [entries, setEntries] = useState<GuestbookEntry[] | null>(null);
  const [busy, setBusy] = useState<number | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    let alive = true;
    listGuestbook(roomId, readMemberId())
      .then((list) => alive && setEntries(list))
      .catch(() => alive && setError('방명록을 불러오지 못했어요.'));
    return () => {
      alive = false;
    };
  }, [roomId]);

  async function remove(id: number) {
    setBusy(id);
    setError('');
    try {
      await deleteGuestbook(roomId, readMemberId(), id);
      setEntries((prev) => (prev ?? []).filter((e) => e.id !== id));
    } catch {
      setError('지우지 못했어요. 잠시 뒤 다시 눌러 주세요.');
    } finally {
      setBusy(null);
    }
  }

  if (entries === null && !error) return <p role="status">방명록을 불러오는 중…</p>;
  return (
    <div className="ed-guestbook">
      <p className="ed-site-hint">공개 사이트에 하객이 남긴 글이에요. 맞지 않는 글은 지울 수 있어요.</p>
      {entries && entries.length === 0 ? <p>아직 남긴 글이 없어요.</p> : null}
      <ul className="ed-guestbook__list">
        {(entries ?? []).map((e) => (
          <li key={e.id} className="ed-guestbook__item">
            <p className="ed-guestbook__who">
              <b>{e.name}</b> <span>{when(e.ts)}</span>
            </p>
            <p className="ed-guestbook__text">{e.message}</p>
            <button type="button" className="ed-btn" disabled={busy === e.id} onClick={() => void remove(e.id)} aria-label={`${e.name}님 글 지우기`}>
              {busy === e.id ? '지우는 중…' : '지우기'}
            </button>
          </li>
        ))}
      </ul>
      {error ? (
        <p className="ed-error" role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}
