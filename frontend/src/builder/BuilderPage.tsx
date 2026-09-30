// 빌더 화면 (BUILDER_CONTRACT §3).
// 위 3칸 + 모양 바꾸기, 가운데는 SiteEditor 재사용(빌더 모드), 아래는 기능 칩 + 공개.
import { useEffect, useRef, useState } from 'react';
import SiteEditor, { type BuilderControl } from '../editor/SiteEditor';
import {
  fetchCard,
  getFeatures,
  putFeature,
  publishRoom,
  readMemberId,
  saveCard,
  type FeatureChip,
  type PublishResult,
  type RoomCard,
} from '../editor/cardApi';
import FeatureChips from './FeatureChips';
import PublishBar from './PublishBar';

const CHOICES = ['v1', 'v2', 'v3'] as const;
const TOP_KEYS = ['shop_name', 'phone', 'location'] as const;

function validChoice(v: string | null): string {
  return v === 'v1' || v === 'v2' || v === 'v3' ? v : 'v1';
}

function fieldVal(card: RoomCard | null, key: string): string {
  return card?.fields.find((f) => f.key === key)?.value ?? '';
}

function fieldLabel(card: RoomCard | null, key: string, fallback: string): string {
  return card?.fields.find((f) => f.key === key)?.label ?? fallback;
}

function topDraftsOf(card: RoomCard): Record<string, string> {
  return { shop_name: fieldVal(card, 'shop_name'), phone: fieldVal(card, 'phone'), location: fieldVal(card, 'location') };
}

export default function BuilderPage({ roomId }: { roomId: string }) {
  const [card, setCard] = useState<RoomCard | null>(null);
  const [features, setFeatures] = useState<FeatureChip[]>([]);
  const [loadFailed, setLoadFailed] = useState(false);
  const [topOpen, setTopOpen] = useState(false);
  const [drafts, setDrafts] = useState<Record<string, string>>({ shop_name: '', phone: '', location: '' });
  const [topMsg, setTopMsg] = useState('');
  const [topBusy, setTopBusy] = useState(false);
  const [choiceBusy, setChoiceBusy] = useState(false);
  const [chipBusy, setChipBusy] = useState<string | null>(null);
  const [chipMsg, setChipMsg] = useState('');
  const [noticeKey, setNoticeKey] = useState<string | null>(null);
  const [noticeText, setNoticeText] = useState('');
  const [pubBusy, setPubBusy] = useState(false);
  const [pubResult, setPubResult] = useState<PublishResult | null>(null);
  const [siteUrl, setSiteUrl] = useState<string | null>(null);
  const control = useRef<BuilderControl | null>(null);

  useEffect(() => {
    let alive = true;
    setCard(null);
    setLoadFailed(false);
    (async () => {
      try {
        const [c, f] = await Promise.all([fetchCard(roomId, readMemberId()), getFeatures(roomId, readMemberId())]);
        if (!alive) return;
        setCard(c);
        setFeatures(f.features);
        setDrafts(topDraftsOf(c));
      } catch {
        if (!alive) return;
        setLoadFailed(true);
      }
    })();
    return () => {
      alive = false;
    };
  }, [roomId]);

  function handleSaved(updated: RoomCard) {
    setCard(updated);
    setDrafts(topDraftsOf(updated));
  }

  async function saveTop() {
    if (!card || topBusy) return;
    const fields: Record<string, string> = {};
    for (const k of TOP_KEYS) {
      const cur = drafts[k] ?? '';
      if (cur !== fieldVal(card, k)) fields[k] = cur;
    }
    if (Object.keys(fields).length === 0) return;
    setTopBusy(true);
    setTopMsg('');
    try {
      const updated = await saveCard(roomId, readMemberId(), fields);
      handleSaved(updated);
      setTopMsg('저장했어요.');
    } catch {
      setTopMsg('저장하지 못했어요. 잠시 뒤 다시 눌러 주세요.');
    } finally {
      setTopBusy(false);
    }
  }

  async function changeChoice(v: string) {
    if (choiceBusy) return;
    setChoiceBusy(true);
    setTopMsg('');
    try {
      const updated = await saveCard(roomId, readMemberId(), {}, undefined, { choice: v });
      handleSaved(updated);
      control.current?.setVariant(v);
    } catch {
      setTopMsg('저장하지 못했어요. 잠시 뒤 다시 눌러 주세요.');
    } finally {
      setChoiceBusy(false);
    }
  }

  async function sendChip(key: string, on: boolean, text?: string) {
    setChipBusy(key);
    setChipMsg('');
    try {
      const r = await putFeature(roomId, readMemberId(), key, on, text);
      setFeatures(r.features);
      setNoticeKey(null);
      setNoticeText('');
      control.current?.reload(r.focus);
    } catch {
      setChipMsg('바꾸지 못했어요. 잠시 뒤 다시 눌러 주세요.');
    } finally {
      setChipBusy(null);
    }
  }

  function toggleChip(chip: FeatureChip) {
    // 공개 뒤에 켜는 기능은 안내만 한다(PUT 없음).
    if (chip.after_publish) {
      setChipMsg('공개한 뒤 사장님 화면에서 켤 수 있어요');
      return;
    }
    // 공지는 글을 적고 켠다.
    if (chip.kind === 'shop' && chip.needs_text && !chip.on) {
      setNoticeKey(chip.key);
      setNoticeText('');
      return;
    }
    void sendChip(chip.key, !chip.on);
  }

  async function publish(force: boolean) {
    if (pubBusy) return;
    setPubBusy(true);
    try {
      const r = await publishRoom(roomId, readMemberId(), force);
      setPubResult(r.need ? r : null);
      if (r.ok) setSiteUrl(r.site_url ?? null);
    } catch {
      setPubResult({ need: 'blocked', message: '공개하지 못했어요. 잠시 뒤 다시 눌러 주세요.' });
    } finally {
      setPubBusy(false);
    }
  }

  if (loadFailed) {
    return (
      <div className="bd-page ed-page">
        <main className="bd-main">
          <h1>빌더를 열지 못했어요</h1>
          <p>방을 만든 기기에서 열거나, 방을 만든 계정으로 로그인해 주세요.</p>
          <a className="bd-chat-link" href={`/room.html?room=${encodeURIComponent(roomId)}`}>
            채팅으로 설명하기
          </a>
        </main>
      </div>
    );
  }
  if (!card) {
    return (
      <div className="bd-page ed-page">
        <main className="bd-main">
          <p role="status">불러오는 중…</p>
        </main>
      </div>
    );
  }

  const choice = validChoice(card.choice);
  const noticeChip = noticeKey ? features.find((f) => f.key === noticeKey) ?? null : null;

  return (
    <div className="bd-page ed-page">
      <header className="bd-top">
        <div className="bd-top-row">
          <h1 className="bd-title">{fieldVal(card, 'shop_name') || card.title}</h1>
          <PublishBar view={{ busy: pubBusy, result: pubResult, siteUrl }} onPublish={(force) => void publish(force)} />
        </div>
        <button type="button" className="ed-btn" aria-expanded={topOpen} onClick={() => setTopOpen((v) => !v)}>
          {topOpen ? '가게 정보 접기' : '가게 정보 펼치기'}
        </button>
        {topOpen ? (
          <div className="bd-top-fields">
            {TOP_KEYS.map((k) => (
              <label key={k} htmlFor={`bd-top-${k}`}>
                {fieldLabel(card, k, k)}
                <input
                  id={`bd-top-${k}`}
                  className="ed-input"
                  type="text"
                  value={drafts[k] ?? ''}
                  disabled={topBusy}
                  onChange={(e) => setDrafts((prev) => ({ ...prev, [k]: e.target.value }))}
                />
              </label>
            ))}
            <button type="button" className="ed-btn ed-btn--primary" disabled={topBusy} onClick={() => void saveTop()}>
              {topBusy ? '저장 중…' : '저장'}
            </button>
            {topMsg ? <p className="bd-msg" role="status">{topMsg}</p> : null}
          </div>
        ) : null}
        <div className="bd-choice" role="group" aria-label="모양 바꾸기">
          <span>모양 바꾸기</span>
          {CHOICES.map((v, i) => (
            <button
              key={v}
              type="button"
              aria-pressed={choice === v}
              disabled={choiceBusy}
              onClick={() => void changeChoice(v)}
            >
              {`${i + 1}안`}
            </button>
          ))}
        </div>
      </header>

      <main className="bd-main">
        <SiteEditor roomId={roomId} card={card} onSaved={handleSaved} builderMode controlRef={control} />
      </main>

      <footer className="bd-bottom">
        <FeatureChips features={features} busyKey={chipBusy} onToggle={toggleChip} />
        {noticeChip ? (
          <div className="bd-notice-sheet" role="dialog" aria-label="공지 글 적기">
            <label htmlFor="bd-notice-text">
              {noticeChip.label} 글
              <input
                id="bd-notice-text"
                className="ed-input"
                type="text"
                value={noticeText}
                maxLength={200}
                placeholder="예: 10월 3일은 쉬어요"
                onChange={(e) => setNoticeText(e.target.value)}
              />
            </label>
            <div className="ed-sheet-row">
              <button type="button" className="ed-btn" onClick={() => setNoticeKey(null)}>
                닫기
              </button>
              <button
                type="button"
                className="ed-btn ed-btn--primary"
                disabled={chipBusy !== null || !noticeText.trim()}
                onClick={() => void sendChip(noticeChip.key, true, noticeText.trim())}
              >
                켜기
              </button>
            </div>
          </div>
        ) : null}
        {chipMsg ? <p className="bd-msg" role="status">{chipMsg}</p> : null}
        <div className="bd-voice-line">
          <input type="text" disabled placeholder="곧 말로 고칠 수 있어요" aria-label="말로 고치기 (준비 중)" />
          <a className="bd-chat-link" href={`/room.html?room=${encodeURIComponent(roomId)}`}>
            채팅으로 설명하기
          </a>
        </div>
      </footer>
    </div>
  );
}
