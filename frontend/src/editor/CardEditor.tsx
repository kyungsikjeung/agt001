// 실제 요구사항 카드 직접 편집 화면 (contracts/ROOM_FEATURES_API.md §5).
// ?room=<id>로 열 때 GET /api/rooms/{id}/card로 불러오고, 바뀐 칸만 PUT {"fields": {...}}로 저장한다.
// D23 자리 표시는 "입력 필요" 배지, D24 사실 확인은 "확인 대기" 배지와 사실 표시로 보여준다.
import { useEffect, useMemo, useState } from 'react';
import { fetchCard, readMemberId, saveCard, statusLabel, type RoomCard } from './cardApi';
import MockEditor from './MockEditor';

interface CardEditorProps {
  roomId: string;
}

type Notice = { kind: 'success' | 'error'; text: string };

function fieldInputId(key: string): string {
  return `card-field-${key}`;
}

export default function CardEditor({ roomId }: CardEditorProps) {
  const [card, setCard] = useState<RoomCard | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState<Notice | null>(null);
  const [confirmEmpty, setConfirmEmpty] = useState<string[] | null>(null);

  useEffect(() => {
    let alive = true;
    setCard(null);
    setLoadFailed(false);
    setNotice(null);
    setConfirmEmpty(null);
    (async () => {
      try {
        const data = await fetchCard(roomId, readMemberId());
        if (!alive) return;
        setCard(data);
        const next: Record<string, string> = {};
        for (const f of data.fields) next[f.key] = f.value;
        setDrafts(next);
      } catch {
        if (!alive) return;
        setLoadFailed(true);
      }
    })();
    return () => {
      alive = false;
    };
  }, [roomId]);

  const dirty = useMemo(() => {
    if (!card) return {};
    const out: Record<string, string> = {};
    for (const f of card.fields) {
      const draft = drafts[f.key] ?? '';
      if (draft !== f.value) out[f.key] = draft;
    }
    return out;
  }, [card, drafts]);
  const dirtyKeys = Object.keys(dirty);
  const emptyKeys = dirtyKeys.filter((k) => (dirty[k] ?? '').trim() === '');

  if (loadFailed) return <MockEditor />;
  if (!card) {
    return (
      <div className="ed-page">
        <main className="ed-main">
          <p role="status">불러오는 중…</p>
        </main>
      </div>
    );
  }

  const readonly = !card.can_edit;

  function setDraft(key: string, value: string) {
    setDrafts((prev) => ({ ...prev, [key]: value }));
  }

  function requestSave() {
    setNotice(null);
    if (dirtyKeys.length === 0 || saving || readonly) return;
    // 빈 값은 자리 표시(입력 필요)로 돌아가므로 화면 안 대화상자로 한 번 더 묻는다.
    if (emptyKeys.length > 0) {
      setConfirmEmpty(emptyKeys);
      return;
    }
    void doSave(dirty);
  }

  async function doSave(fields: Record<string, string>) {
    setSaving(true);
    setNotice(null);
    setConfirmEmpty(null);
    try {
      const updated = await saveCard(roomId, readMemberId(), fields);
      setCard(updated);
      const next: Record<string, string> = {};
      for (const f of updated.fields) next[f.key] = f.value;
      setDrafts(next);
      setNotice({
        kind: 'success',
        text: updated.published ? '저장했어요. 사이트에도 반영했어요.' : '저장했어요.',
      });
    } catch {
      setNotice({ kind: 'error', text: '저장하지 못했어요. 잠시 뒤 다시 눌러 주세요.' });
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="ed-page">
      <header className="ed-top">
        <div className="ed-top-row">
          <h1 className="ed-shop">{card.title}</h1>
        </div>
        {card.industry ? <p className="ed-fact-note">{card.industry}</p> : null}
        {readonly ? <p className="ed-banner">방장만 고칠 수 있어요. 내용은 볼 수 있어요.</p> : null}
      </header>

      <main className="ed-main">
        {notice ? (
          <p className={notice.kind === 'success' ? 'ed-banner-ok' : 'ed-error'} role={notice.kind === 'error' ? 'alert' : 'status'}>
            {notice.text}
          </p>
        ) : null}

        <section aria-label="요구사항 칸">
          <ul className="ed-card-list">
            {card.fields.map((field) => {
              const badge = statusLabel(field.status);
              const draft = drafts[field.key] ?? '';
              return (
                <li key={field.key} className="ed-card-field">
                  <label htmlFor={fieldInputId(field.key)}>
                    {field.label}
                    {field.fact ? <span className="ed-fact"> · 사실</span> : null}
                  </label>
                  {badge ? <span className="ed-badge">{badge}</span> : null}
                  <input
                    id={fieldInputId(field.key)}
                    type="text"
                    value={draft}
                    disabled={readonly || saving}
                    readOnly={readonly}
                    onChange={(e) => setDraft(field.key, e.target.value)}
                  />
                </li>
              );
            })}
          </ul>
        </section>

        {readonly ? null : (
          <div className="ed-sheet-row">
            <button
              type="button"
              className="ed-btn ed-btn--primary"
              disabled={dirtyKeys.length === 0 || saving}
              onClick={requestSave}
            >
              {saving ? '저장 중…' : `바뀐 칸 저장${dirtyKeys.length > 0 ? ` (${dirtyKeys.length}개)` : ''}`}
            </button>
          </div>
        )}

        {card.photos.length > 0 ? (
          <section aria-label="사진 목록">
            <h2>사진</h2>
            <ul className="ed-photo-list">
              {card.photos.map((photo) => (
                <li key={photo.id}>
                  <img src={photo.url} alt={photo.caption || '방 사진'} loading="lazy" width={120} />
                </li>
              ))}
            </ul>
          </section>
        ) : null}

        <div className="ed-ai-box">
          {card.site_url ? (
            <a href={card.site_url} target="_blank" rel="noopener noreferrer">
              공개 사이트 보기
            </a>
          ) : null}
          <a href={`/room.html?room=${encodeURIComponent(roomId)}`}>채팅방으로 돌아가기</a>
          <a href={`/room.html?room=${encodeURIComponent(roomId)}`}>AI에게 부탁하기 — 채팅방으로 이동</a>
        </div>
      </main>

      {confirmEmpty ? (
        <div className="ed-scrim" onClick={() => setConfirmEmpty(null)}>
          <div
            className="ed-dialog"
            role="dialog"
            aria-modal="true"
            aria-label="빈 값 저장 확인"
            onClick={(e) => e.stopPropagation()}
          >
            <h2>입력 필요로 돌아가요. 저장할까요?</h2>
            <p>비운 칸은 자리 표시(입력 필요)로 돌아가요. 공개 전에는 다시 채워야 해요.</p>
            <div className="ed-sheet-row">
              <button type="button" className="ed-btn" autoFocus onClick={() => setConfirmEmpty(null)}>
                그대로 두기
              </button>
              <button type="button" className="ed-btn ed-btn--primary" disabled={saving} onClick={() => void doSave(dirty)}>
                {saving ? '저장 중…' : '입력 필요로 저장'}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
