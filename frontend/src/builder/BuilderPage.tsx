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
import AddressSearch from './AddressSearch';
import FeatureChips from './FeatureChips';
import PhotoSheet, { type PhotoSheetPick } from './PhotoSheet';
import NoticePhotos from '../editor/NoticePhotos';
import PublishBar from './PublishBar';
import SayBar from './SayBar';
import type { SayResponse, UndoResponse } from '../editor/cardApi';

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
  const [noticePhotos, setNoticePhotos] = useState<string[]>([]);
  const [pubBusy, setPubBusy] = useState(false);
  const [pubResult, setPubResult] = useState<PublishResult | null>(null);
  const [siteUrl, setSiteUrl] = useState<string | null>(null);
  const [changeSeq, setChangeSeq] = useState(0);
  const [photoPick, setPhotoPick] = useState<PhotoSheetPick | null>(null);
  const control = useRef<BuilderControl | null>(null);
  const bottomRef = useRef<HTMLElement | null>(null);

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

  // 주소 검색 저장 뒤: 카드와 미리보기를 새로 부른다.
  function handleAddrSaved(updated: RoomCard) {
    handleSaved(updated);
    control.current?.reload(null);
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
      setChangeSeq((n) => n + 1);
      control.current?.reload(null); // 미리보기 첫 화면의 [가게 이름 입력]이 저장 뒤에도 남던 것 (B4)
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
      setChangeSeq((n) => n + 1);
      control.current?.setVariant(v);
    } catch {
      setTopMsg('저장하지 못했어요. 잠시 뒤 다시 눌러 주세요.');
    } finally {
      setChoiceBusy(false);
    }
  }

  async function sendChip(key: string, on: boolean, text?: string, photos?: string[]) {
    setChipBusy(key);
    setChipMsg('');
    try {
      const r = await putFeature(roomId, readMemberId(), key, on, text, photos);
      setFeatures(r.features);
      setNoticeKey(null);
      setNoticeText('');
      setNoticePhotos([]);
      setChangeSeq((n) => n + 1);
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

  // 말로 고친 뒤 위 제목·가게 정보 칸도 새 카드로 (미리보기만 바뀌고 제목은 옛 이름이던 것)
  async function refreshCard() {
    try {
      handleSaved(await fetchCard(roomId, readMemberId()));
    } catch {
      /* 제목만 늦게 바뀐다. 미리보기는 이미 새것 */
    }
  }

  // 말로 고치기 답 뒤: 칩을 새 목록으로 바꾸고 미리보기를 다시 그린다.
  function handleSayApplied(r: SayResponse) {
    setFeatures(r.features);
    control.current?.reload(r.focus);
    void refreshCard();
  }

  // 되돌리기 뒤: 칩을 새 목록으로 바꾸고 미리보기를 다시 그린다.
  function handleSayUndone(r: UndoResponse) {
    setFeatures(r.features);
    control.current?.reload(null);
    void refreshCard();
  }

  // 사진 시트에서 "이걸로 쓰기"·되돌리기 뒤: 누른 구역으로 미리보기를 다시 그리고 반짝인다.
  function handlePhotoApplied(_target: string, _url: string) {
    const focus = photoPick?.section ?? null;
    setChangeSeq((n) => n + 1);
    control.current?.reload(focus);
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
          {topOpen ? '가게 정보 닫기' : '가게 정보 입력'}
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
            <AddressSearch roomId={roomId} onSaved={handleAddrSaved} />
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
        {card?.quota ? (
          <p className="bd-quota">
            {card.quota.restyle.left > 0
              ? `무료 디자인 고치기 ${card.quota.restyle.left}번 남음 · ${card.quota.resets}에 다시 채워져요`
              : `이번 달 무료 디자인 고치기를 다 썼어요 · ${card.quota.resets}에 다시 채워져요`}
          </p>
        ) : null}
      </header>

      <main className="bd-main">
        <SiteEditor
          roomId={roomId}
          card={card}
          onSaved={handleSaved}
          builderMode
          controlRef={control}
          onPhotoPick={setPhotoPick}
          bottomRef={bottomRef}
        />
        <PhotoSheet
          roomId={roomId}
          pick={photoPick}
          onClose={() => setPhotoPick(null)}
          onApplied={handlePhotoApplied}
        />
      </main>

      <footer ref={bottomRef} className="bd-bottom">
        <SayBar
          roomId={roomId}
          clearUndoOn={changeSeq}
          onApplied={handleSayApplied}
          onUndone={handleSayUndone}
        />
        <FeatureChips features={features} busyKey={chipBusy} onToggle={toggleChip} />
        {noticeChip ? (
          <div className="bd-notice-sheet" role="dialog" aria-label="공지 적기">
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
            <NoticePhotos roomId={roomId} photos={noticePhotos} onChange={setNoticePhotos} />
            <div className="ed-sheet-row">
              <button type="button" className="ed-btn" onClick={() => setNoticeKey(null)}>
                닫기
              </button>
              <button
                type="button"
                className="ed-btn ed-btn--primary"
                disabled={chipBusy !== null || (!noticeText.trim() && noticePhotos.length === 0)}
                onClick={() => void sendChip(noticeChip.key, true, noticeText.trim(), noticePhotos)}
              >
                켜기
              </button>
            </div>
          </div>
        ) : null}
        {chipMsg ? <p className="bd-msg" role="status">{chipMsg}</p> : null}
        <div className="bd-voice-line">
          <a className="bd-chat-link" href={`/room.html?room=${encodeURIComponent(roomId)}`}>
            채팅으로 설명하기
          </a>
        </div>
      </footer>
    </div>
  );
}
