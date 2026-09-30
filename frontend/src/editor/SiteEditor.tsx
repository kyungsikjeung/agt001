// 보며 고치기 (EDIT_WAVE2_CONTRACT §1, §4).
// 미리보기를 iframe(srcdoc, sandbox allow-scripts만)으로 띄우고,
// iframe이 알린 구역의 패널을 옆(휴대폰은 아래)에 연다.
import { useCallback, useEffect, useRef, useState } from 'react';
import { getPreview, readMemberId, type CardPreview, type RoomCard } from './cardApi';
import SectionPanel from './SectionPanel';

const VARIANTS = ['v1', 'v2', 'v3'] as const;

function startVariant(choice: string | null): string {
  return choice === 'v1' || choice === 'v2' || choice === 'v3' ? choice : 'v1';
}

interface AgtEditMessage {
  type?: unknown;
  section?: unknown;
  text?: unknown;
  img?: unknown;
  src?: unknown;
  index?: unknown;
}

/** 빌더 화면이 미리보기를 다루는 손잡이 (BUILDER_CONTRACT §3).
 * reload는 미리보기를 다시 그리고 다 그린 뒤 focus 구역으로 스크롤·반짝한다. */
export interface BuilderControl {
  reload: (focus?: string | null) => void;
  flash: (section: string) => void;
  setVariant: (v: string) => void;
}

export default function SiteEditor({
  roomId,
  card,
  onSaved,
  builderMode,
  controlRef,
  onPhotoPick,
}: {
  roomId: string;
  card: RoomCard;
  onSaved: (c: RoomCard) => void;
  /** 빌더 모드면 구역 목록 대신 칩을 쓰므로 목록은 접는다(builder.css). */
  builderMode?: boolean;
  /** 부모가 미리보기를 다시 그리게 하는 손잡이. */
  controlRef?: { current: BuilderControl | null };
  /** 미리보기에서 사진을 누르면 구역 패널 대신 사진 시트를 연다(PHOTO_EDIT_CONTRACT §5). */
  onPhotoPick?: (pick: { section: string; src: string; index: number }) => void;
}) {
  const [variant, setVariant] = useState(() => startVariant(card.choice));
  const [preview, setPreview] = useState<CardPreview | null>(null);
  const [failed, setFailed] = useState<'no-design' | 'error' | null>(null);
  const [loading, setLoading] = useState(true);
  const [pick, setPick] = useState<{ id: string | null; text: string }>({ id: null, text: '' });
  const frameRef = useRef<HTMLIFrameElement | null>(null);
  const pendingScroll = useRef<string | null>(null);
  const pendingFlash = useRef<string | null>(null);
  const variantRef = useRef(variant);
  variantRef.current = variant;

  const load = useCallback(
    async (v: string) => {
      setLoading(true);
      setFailed(null);
      try {
        const p = await getPreview(roomId, readMemberId(), v);
        setPreview(p);
      } catch (e) {
        setPreview(null);
        setFailed((e as { status?: number })?.status === 409 ? 'no-design' : 'error');
      } finally {
        setLoading(false);
      }
    },
    [roomId],
  );

  useEffect(() => {
    setPick({ id: null, text: '' });
    void load(variant);
  }, [load, variant]);

  // iframe에 메시지를 보낸다. 아직 안 떴으면 건너뛴다.
  function postToFrame(msg: { type: string; section: string }) {
    try {
      frameRef.current?.contentWindow?.postMessage(msg, '*');
    } catch {
      // iframe이 아직 안 떴으면 스크롤·반짝을 건너뛴다.
    }
  }

  // 빌더 부모용 손잡이. variant는 ref로 읽어 오래된 값을 쓰지 않는다.
  useEffect(() => {
    if (!controlRef) return;
    controlRef.current = {
      reload: (focus) => {
        pendingScroll.current = focus ?? null;
        pendingFlash.current = focus ?? null;
        void load(variantRef.current);
      },
      flash: (section) => {
        postToFrame({ type: 'agt-scroll', section });
        postToFrame({ type: 'agt-flash', section });
      },
      setVariant: (v) => {
        if (v === 'v1' || v === 'v2' || v === 'v3') setVariant(v);
      },
    };
    return () => {
      controlRef.current = null;
    };
  }, [controlRef, load]);

  // iframe 알림만 받는다. 출처가 다르면 무시한다.
  useEffect(() => {
    function onMessage(e: MessageEvent) {
      const frame = frameRef.current;
      if (!frame || e.source !== frame.contentWindow) return;
      const data = (e.data ?? {}) as AgtEditMessage;
      if (data.type !== 'agt-edit' || typeof data.section !== 'string' || !data.section) return;
      // 사진을 누르면 구역 패널 대신 사진 시트를 연다.
      if (data.img === true && typeof data.src === 'string' && data.src !== '') {
        onPhotoPick?.({
          section: data.section,
          src: data.src,
          index: typeof data.index === 'number' ? data.index : 0,
        });
        return;
      }
      // 한 번에 갱신한다 (두 번 나누면 패널이 접힌 채로 먼저 그려진다).
      setPick({ id: data.section, text: typeof data.text === 'string' ? data.text : '' });
    }
    window.addEventListener('message', onMessage);
    return () => window.removeEventListener('message', onMessage);
  }, [onPhotoPick]);

  // 저장 뒤 미리보기를 다시 불러오고, 누른 구역으로 스크롤한다.
  function handleSaved(updated: RoomCard, section: string) {
    onSaved(updated);
    pendingScroll.current = section;
    void load(variant);
  }

  function onFrameLoad() {
    const section = pendingScroll.current;
    pendingScroll.current = null;
    if (section) postToFrame({ type: 'agt-scroll', section });
    const flash = pendingFlash.current;
    pendingFlash.current = null;
    if (flash) postToFrame({ type: 'agt-flash', section: flash });
  }

  const legacy = !loading && !failed && preview && preview.sections.length === 0;

  return (
    <div className={builderMode ? 'ed-site ed-site--builder' : 'ed-site'}>
      <div className="ed-site-bar" role="group" aria-label="시안 고르기">
        {VARIANTS.map((v, i) => (
          <button
            key={v}
            type="button"
            aria-pressed={variant === v}
            onClick={() => setVariant(v)}
          >
            {`${i + 1}안`}
          </button>
        ))}
      </div>

      {loading ? <p role="status">미리보기를 불러오는 중…</p> : null}
      {failed === 'no-design' ? <p role="status">아직 시안이 없어요. 채팅방에서 시안을 먼저 만들어 주세요.</p> : null}
      {failed === 'error' ? (
        <p className="ed-error" role="alert">
          미리보기를 불러오지 못했어요. 잠시 뒤 다시 열어 주세요.
        </p>
      ) : null}
      {legacy ? <p role="status">이 시안은 구역 편집이 안 돼요.</p> : null}

      {!loading && !failed && preview && !legacy ? (
        <div className="ed-site-body">
          <iframe
            ref={frameRef}
            className="ed-site-frame"
            title="사이트 미리보기"
            sandbox="allow-scripts"
            srcDoc={preview.html}
            onLoad={onFrameLoad}
          />
          <SectionPanel
            roomId={roomId}
            card={card}
            sections={preview.sections}
            addable={preview.addable}
            added={preview.layout?.added ?? []}
            baseItems={preview.items ?? []}
            variant={variant}
            selectedId={pick.id}
            clickedText={pick.text}
            onSelect={(id) => setPick((prev) => ({ ...prev, id }))}
            onSaved={handleSaved}
          />
        </div>
      ) : null}
    </div>
  );
}
