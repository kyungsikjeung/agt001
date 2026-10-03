// 보며 고치기 (EDIT_WAVE2_CONTRACT §1, §4).
// 미리보기를 iframe(srcdoc, sandbox allow-scripts만)으로 띄우고,
// iframe이 알린 구역의 패널을 옆(휴대폰은 아래)에 연다.
// 실시간 미리보기 (COMPONENT_ENGINE_PLAN §5): 저장·고치는 중에는 iframe을 새로 불러오지 않고
// 바뀐 구역 조각만 바꿔 끼운다(agt-patch). 색·여백·스타일 축은 토큰만 갈아 끼운다(agt-theme). 스크롤이 그대로다.
import Mascot from '../Mascot';
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  draftPreview,
  getPreview,
  readMemberId,
  saveCard,
  type CardLayoutEdit,
  type CardPreview,
  type DraftRequest,
  type RoomCard,
  type StyleAxis,
} from './cardApi';
import { frameStateOf, planUpdate, sameTheme, styleAttrs, type FrameState } from './livePatch';
import SectionPanel from './SectionPanel';

/** 고치는 칸 글을 미리보기에 그리기까지 기다리는 시간(글자마다 부르지 않게). */
const DRAFT_DELAY_MS = 300;

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
  photo?: unknown;
}

/** 글자를 눌렀을 때 구역 안에 있던 첫 사진. 첫 화면은 글자에 가려 사진 누름이 안 오므로 이 값으로 사진 시트를 연다. */
interface PickPhoto {
  src: string;
  index: number;
}

interface PickState {
  id: string | null;
  text: string;
  photo: PickPhoto | null;
}

/** 미리보기 메시지의 photo를 읽는다. 주소가 글자가 아니면 null. */
function photoOf(data: AgtEditMessage): PickPhoto | null {
  const p = data.photo as { src?: unknown; index?: unknown } | null | undefined;
  if (!p || typeof p !== 'object' || typeof p.src !== 'string' || p.src === '') return null;
  return { src: p.src, index: typeof p.index === 'number' ? p.index : 0 };
}

/** 끌어서 바꾼 새 순서. locked 구역은 원래 자리(index)에 둔다. 같으면 null. */
export function reorderOutline(
  sections: Pick<CardPreview['sections'][number], 'id' | 'locked'>[],
  fromId: string,
  toId: string,
): string[] | null {
  if (fromId === toId) return null;
  const orderIds = sections.map((s) => s.id);
  const movable = sections.filter((s) => !s.locked).map((s) => s.id);
  if (!movable.includes(fromId)) return null;
  const targetIdx = orderIds.indexOf(toId);
  if (targetIdx < 0) return null;
  const without = movable.filter((id) => id !== fromId);
  const lockedBefore = sections.slice(0, targetIdx).filter((s) => s.locked).length;
  const insertAt = Math.max(0, Math.min(without.length, targetIdx - lockedBefore));
  const reordered = [...without.slice(0, insertAt), fromId, ...without.slice(insertAt)];
  const out: string[] = [];
  let mi = 0;
  for (const s of sections) {
    out.push(s.locked ? s.id : (reordered[mi++] ?? s.id));
  }
  return out.join(',') === orderIds.join(',') ? null : out;
}
/** 빌더 화면이 미리보기를 다루는 손잡이 (BUILDER_CONTRACT §3).
 * reload는 미리보기를 다시 그리고 다 그린 뒤 focus 구역으로 스크롤·반짝한다. */
export interface BuilderControl {
  reload: (focus?: string | null) => void;
  flash: (section: string) => void;
  setVariant: (v: string) => void;
}

const DEVICE_KEY = 'agt001_preview_device';
/** 넓은 화면 미리보기: 실제 기기 크기로 그린 뒤 남는 칸에 맞게 통째로 줄여 기기 테두리 안에 띄운다.
 * chromeW·chromeH는 줄이지 않는 테두리(휴대폰 베젤+상태줄, 브라우저 창 머리줄) 크기다(editor.css와 맞춘다). */
const DEVICES = {
  mobile: { w: 390, h: 844, chromeW: 24, chromeH: 24 + 28 },
  desktop: { w: 1280, h: 800, chromeW: 2, chromeH: 2 + 36 },
} as const;
/** 기기 아래로 남겨 둘 여백. */
const STAGE_GAP = 16;
const WIDE = '(min-width: 760px)';

export default function SiteEditor({
  roomId,
  card,
  onSaved,
  builderMode,
  controlRef,
  onPhotoPick,
  bottomRef,
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
  /** 화면 아래 고정 띠(빌더 칩 줄). 기기 미리보기가 그 뒤로 숨지 않게 높이만큼 비운다. */
  bottomRef?: { current: HTMLElement | null };
}) {
  const [variant, setVariant] = useState(() => startVariant(card.choice));
  const [preview, setPreview] = useState<CardPreview | null>(null);
  // iframe 문서는 미리보기 정보와 따로 둔다: 조각만 바꿔 끼울 때는 문서를 바꾸지 않아 새로 불러오지 않는다.
  // key는 통째로 다시 불러와야 할 때만 올린다(같은 문서 글이어도 확실히 새로 그리게).
  const [frameDoc, setFrameDoc] = useState('');
  const [frameKey, setFrameKey] = useState(0);
  const frameState = useRef<FrameState | null>(null);
  const [styleBusy, setStyleBusy] = useState(false);
  const [styleError, setStyleError] = useState('');
  const [failed, setFailed] = useState<'no-design' | 'error' | null>(null);
  const [loading, setLoading] = useState(true);
  const [pick, setPick] = useState<PickState>({ id: null, text: '', photo: null });
  // 넓은 화면에서 미리보기 폭: 휴대폰(390px) 또는 데스크톱(가득). 사이트는 반응형이라 폭만 바꾸면 된다.
  const [device, setDevice] = useState<'mobile' | 'desktop'>(() => {
    try {
      return localStorage.getItem(DEVICE_KEY) === 'desktop' ? 'desktop' : 'mobile';
    } catch {
      return 'mobile';
    }
  });
  function pickDevice(next: 'mobile' | 'desktop') {
    setDevice(next);
    try {
      localStorage.setItem(DEVICE_KEY, next);
    } catch {
      /* 저장이 막혀도 이번 화면에선 바뀐다 */
    }
  }
  // 넓은 화면에서만 기기 테두리를 쓴다. 휴대폰으로 열면 미리보기가 곧 휴대폰 화면이다.
  const [wide, setWide] = useState(() => {
    try {
      return window.matchMedia(WIDE).matches;
    } catch {
      return false;
    }
  });
  useEffect(() => {
    let mq: MediaQueryList;
    try {
      mq = window.matchMedia(WIDE);
    } catch {
      return;
    }
    const on = () => setWide(mq.matches);
    mq.addEventListener?.('change', on);
    return () => mq.removeEventListener?.('change', on);
  }, []);
  const frameRef = useRef<HTMLIFrameElement | null>(null);
  const viewRef = useRef<HTMLDivElement | null>(null);
  // 기기를 띄울 수 있는 칸: 폭은 미리보기 칸, 높이는 창 높이에서 아래 고정 띠와 여백을 뺀 것.
  const [room, setRoom] = useState({ w: 0, h: 0 });
  useEffect(() => {
    const el = viewRef.current;
    if (!wide || !el) return;
    // 높이는 스크롤하지 않은 첫 화면에서 기기가 통째로 보이게: 기기 칸이 시작하는 곳부터 아래 띠까지.
    const measure = () => {
      const top = Math.max(12, el.getBoundingClientRect().top + window.scrollY);
      const bottom = bottomRef?.current?.offsetHeight ?? 0;
      setRoom({ w: el.clientWidth, h: window.innerHeight - top - bottom - STAGE_GAP });
    };
    measure();
    // ponytail: 아래 띠 높이는 칸·창 크기가 바뀔 때만 다시 잰다. 공지 시트처럼 띠가 잠깐 커지는 건 따라가지 않는다.
    const ro = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(measure);
    ro?.observe(el);
    window.addEventListener('resize', measure);
    return () => {
      ro?.disconnect();
      window.removeEventListener('resize', measure);
    };
  }, [wide, device, preview, bottomRef]);
  // 줄임 비율. 휴대폰은 칸이 기기 폭에 맞춰지므로 높이로만, 데스크톱은 폭·높이 둘 다로 맞춘다.
  const dev = DEVICES[device];
  const scale =
    wide && room.h > 0
      ? Math.max(
          0.3,
          Math.min(
            1,
            (room.h - dev.chromeH) / dev.h,
            device === 'desktop' && room.w > 0 ? (room.w - dev.chromeW) / dev.w : 1,
          ),
        )
      : 0;
  const pendingScroll = useRef<string | null>(null);
  const pendingFlash = useRef<string | null>(null);
  const variantRef = useRef(variant);
  variantRef.current = variant;

  /** iframe을 이 문서로 통째로 다시 그린다. */
  const showFull = useCallback((html: string, state: FrameState | null) => {
    frameState.current = state;
    setFrameDoc(html);
    setFrameKey((k) => k + 1);
  }, []);

  // 처음 열 때·안을 바꿀 때: 기다림 표시와 함께 통째로 불러온다.
  const load = useCallback(
    async (v: string) => {
      setLoading(true);
      setFailed(null);
      try {
        const p = await getPreview(roomId, readMemberId(), v);
        setPreview(p);
        showFull(p.html, frameStateOf(p));
      } catch (e) {
        setPreview(null);
        setFailed((e as { status?: number })?.status === 409 ? 'no-design' : 'error');
      } finally {
        setLoading(false);
      }
    },
    [roomId, showFull],
  );

  useEffect(() => {
    setPick({ id: null, text: '', photo: null });
    void load(variant);
  }, [load, variant]);

  // iframe에 메시지를 보낸다. 아직 안 떴으면 건너뛴다.
  function postToFrame(msg: Record<string, unknown>) {
    try {
      frameRef.current?.contentWindow?.postMessage(msg, '*');
    } catch {
      // iframe이 아직 안 떴으면 스크롤·반짝을 건너뛴다.
    }
  }

  // 저장 뒤: 기다림 표시 없이 다시 받아 바뀐 구역만 바꿔 끼운다. 뼈대(내비·행동 바·글꼴)가 달라졌으면 통째로.
  // mode 'reload'(빌더 칩·말로 고치기): 그 구역으로 스크롤하고 반짝인다.
  // mode 'saved'(구역 칸 저장): 보던 자리 그대로, 바뀐 구역만 반짝인다(통째로 다시 그리면 그 구역으로 스크롤).
  const refresh = useCallback(
    async (v: string, focus: string | null, mode: 'reload' | 'saved' = 'saved') => {
      let p: CardPreview;
      try {
        p = await getPreview(roomId, readMemberId(), v);
      } catch {
        pendingScroll.current = focus;
        if (mode === 'reload') pendingFlash.current = focus;
        void load(v);
        return;
      }
      if (v !== variantRef.current) return; // 그사이 다른 안으로 갔다
      const plan = planUpdate(frameState.current, p);
      setPreview(p);
      if (plan.kind === 'full') {
        pendingScroll.current = focus;
        if (mode === 'reload') pendingFlash.current = focus;
        showFull(p.html, frameStateOf(p));
        return;
      }
      if (plan.theme) postToFrame({ type: 'agt-theme', ...plan.theme });
      if (plan.parts.length > 0 || plan.order.join(',') !== Object.keys(frameState.current?.hashes ?? {}).join(',')) {
        postToFrame({ type: 'agt-patch', parts: plan.parts, order: plan.order, focus: focus ?? undefined });
      } else if (focus) {
        postToFrame({ type: 'agt-flash', section: focus });
      }
      if (focus && mode === 'reload') postToFrame({ type: 'agt-scroll', section: focus });
      frameState.current = frameStateOf(p);
    },
    [roomId, load, showFull],
  );

  // 저장 전 미리 그리기: 고치는 중인 값으로 바뀐 구역만 받아 바꿔 끼운다. 늦게 온 응답은 버린다.
  const draftSeq = useRef(0);
  const runDraft = useCallback(
    async (req: Omit<DraftRequest, 'variant' | 'have' | 'shell'>) => {
      const cur = frameState.current;
      if (!cur) return;
      const seq = ++draftSeq.current;
      const v = variantRef.current;
      let res;
      try {
        res = await draftPreview(roomId, readMemberId(), { ...req, variant: v, have: cur.hashes, shell: cur.shell });
      } catch {
        return; // 미리 그리기는 실패해도 저장은 따로 된다
      }
      if (seq !== draftSeq.current || v !== variantRef.current) return;
      const next = frameStateOf(res);
      if (res.html) {
        showFull(res.html, next);
        return;
      }
      if (!sameTheme(cur.theme, res.theme)) postToFrame({ type: 'agt-theme', ...res.theme });
      const parts = res.parts.filter((p) => typeof p.html === 'string').map((p) => ({ id: p.id, html: p.html as string }));
      if (parts.length > 0 || res.order.join(',') !== Object.keys(cur.hashes).join(',')) {
        postToFrame({ type: 'agt-patch', parts, order: res.order });
      }
      frameState.current = next;
    },
    [roomId, showFull],
  );

  // 칸 글을 고치는 동안: 잠깐 멈추면 그린다.
  const draftTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const draftFields = useCallback(
    (fields: Record<string, string>) => {
      if (draftTimer.current) clearTimeout(draftTimer.current);
      draftTimer.current = setTimeout(() => {
        draftTimer.current = null;
        void runDraft({ fields });
      }, DRAFT_DELAY_MS);
    },
    [runDraft],
  );
  useEffect(
    () => () => {
      if (draftTimer.current) clearTimeout(draftTimer.current);
    },
    [],
  );

  // 스타일 축(카드 면·구역 제목): 누르는 즉시 iframe 속성만 바꾸고, 저장은 뒤에서.
  async function pickStyle(axis: string, value: string) {
    if (!preview?.styles || styleBusy) return;
    const picked = { ...(preview.style ?? {}), [axis]: value };
    const attrs = styleAttrs(preview.styles, picked);
    const theme = frameState.current?.theme;
    if (theme) {
      const next = { ...theme, attrs };
      postToFrame({ type: 'agt-theme', ...next });
      if (frameState.current) frameState.current = { ...frameState.current, theme: next };
    }
    setPreview((prev) => (prev ? { ...prev, style: Object.fromEntries(Object.entries(attrs).map(([k, v]) => [k.slice(5), v])) } : prev));
    setStyleBusy(true);
    setStyleError('');
    try {
      const updated = await saveCard(roomId, readMemberId(), {}, undefined, {
        style: { variant, surface: picked.surface, heading: picked.heading },
      });
      onSaved(updated);
      void refresh(variant, null);
    } catch {
      setStyleError('스타일을 저장하지 못했어요. 잠시 뒤 다시 골라 주세요.');
      void refresh(variant, null);
    } finally {
      setStyleBusy(false);
    }
  }

  // 빌더 부모용 손잡이. variant는 ref로 읽어 오래된 값을 쓰지 않는다.
  useEffect(() => {
    if (!controlRef) return;
    controlRef.current = {
      reload: (focus) => {
        void refresh(variantRef.current, focus ?? null, 'reload');
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
  }, [controlRef, refresh]);

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
      // 글자를 눌렀어도 구역 안에 사진이 있으면 사진 시트로 갈 수 있게 기억한다.
      // 한 번에 갱신한다 (두 번 나누면 패널이 접힌 채로 먼저 그려진다).
      setPick({ id: data.section, text: typeof data.text === 'string' ? data.text : '', photo: photoOf(data) });
    }
    window.addEventListener('message', onMessage);
    return () => window.removeEventListener('message', onMessage);
  }, [onPhotoPick]);

  // 저장 뒤 미리보기를 맞춘다: 바뀐 구역만 바꿔 끼우고 그 구역을 반짝인다(새로 불러오면 그 구역으로 스크롤).
  function handleSaved(updated: RoomCard, section: string) {
    onSaved(updated);
    void refresh(variant, section || null);
  }

  // 왼쪽 구역 끌어서 순서 바꾸기 (BUILDER_FIX_1003 J4). locked는 끌 수 없고 원래 자리에 둔다.
  const [dragId, setDragId] = useState<string | null>(null);
  const [dropId, setDropId] = useState<string | null>(null);
  const [orderError, setOrderError] = useState('');
  const [ordering, setOrdering] = useState(false);
  const dragRef = useRef<string | null>(null);

  async function commitOutlineDrop(targetId: string) {
    const fromId = dragRef.current;
    setDropId(null);
    if (!fromId || !preview || ordering) return;
    const order = reorderOutline(preview.sections, fromId, targetId);
    dragRef.current = null;
    setDragId(null);
    if (!order) return;
    const hidden = preview.sections.filter((s) => s.hidden).map((s) => s.id);
    const added = preview.layout?.added ?? [];
    setOrdering(true);
    setOrderError('');
    try {
      const updated = await saveCard(roomId, readMemberId(), {}, undefined, {
        layout: { variant, order, hidden, added },
      });
      handleSaved(updated, fromId);
    } catch {
      setOrderError('순서를 바꾸지 못했어요. 잠시 뒤 다시 해 주세요.');
    } finally {
      setOrdering(false);
    }
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

      {!loading && !failed && preview?.styles ? (
        <StylePicker
          styles={preview.styles}
          value={preview.style ?? {}}
          busy={styleBusy}
          onPick={(axis, value) => void pickStyle(axis, value)}
        />
      ) : null}
      {styleError ? (
        <p className="ed-error" role="alert">
          {styleError}
        </p>
      ) : null}

      {loading ? (
        <Mascot mood="wait" role="status">
          <p>미리보기를 불러오는 중…</p>
        </Mascot>
      ) : null}
      {failed === 'no-design' ? <p role="status">아직 시안이 없어요. 채팅방에서 시안을 먼저 만들어 주세요.</p> : null}
      {failed === 'error' ? (
        <Mascot mood="oops" role="alert">
          <p className="ed-error">미리보기를 불러오지 못했어요. 잠시 뒤 다시 열어 주세요.</p>
        </Mascot>
      ) : null}
      {legacy ? <p role="status">이 시안은 구역 편집이 안 돼요.</p> : null}

      {!loading && !failed && preview && !legacy ? (
        <div className={`ed-site-body${device === 'desktop' ? ' ed-site-body--desktop' : ''}`}>
          {/* 빌더 넓은 화면: 왼쪽 칸에 구역 바로가기. 누르면 미리보기가 그 구역으로 가서 반짝이고 오른쪽 고치기 칸이 열린다 */}
          {builderMode && wide ? (
            <nav className="ed-outline" aria-label="구역 바로가기">
              <h2>구역</h2>
              <ul>
                {preview.sections.map((s) => (
                  <li
                    key={s.id}
                    draggable={!s.locked}
                    className={dropId === s.id && dragId ? 'ed-outline-drop' : undefined}
                    onDragStart={(e) => {
                      if (s.locked) {
                        e.preventDefault();
                        return;
                      }
                      dragRef.current = s.id;
                      setDragId(s.id);
                      setOrderError('');
                      if (e.dataTransfer) {
                        try {
                          e.dataTransfer.effectAllowed = 'move';
                          e.dataTransfer.setData('text/plain', s.id);
                        } catch {
                          /* 끌기 모양이 안 잡혀도 순서는 바뀐다 */
                        }
                      }
                    }}
                    onDragOver={(e) => {
                      if (!dragRef.current || dragRef.current === s.id) return;
                      e.preventDefault();
                      setDropId(s.id);
                      if (e.dataTransfer) {
                        try {
                          e.dataTransfer.dropEffect = 'move';
                        } catch {
                          /* 무시 */
                        }
                      }
                    }}
                    onDrop={(e) => {
                      e.preventDefault();
                      void commitOutlineDrop(s.id);
                    }}
                    onDragEnd={() => {
                      dragRef.current = null;
                      setDragId(null);
                      setDropId(null);
                    }}
                  >
                    <span className="ed-outline-grip" aria-hidden="true">
                      ⋮⋮
                    </span>
                    <button
                      type="button"
                      aria-current={pick.id === s.id}
                      onClick={() => {
                        setPick({ id: s.id, text: '', photo: null });
                        postToFrame({ type: 'agt-scroll', section: s.id });
                        postToFrame({ type: 'agt-flash', section: s.id });
                      }}
                    >
                      {s.label}
                      {s.hidden ? <span className="ed-outline-hidden">숨김</span> : null}
                    </button>
                  </li>
                ))}
              </ul>
              {orderError ? <p role="alert">{orderError}</p> : null}
            </nav>
          ) : null}
          <div className="ed-site-view">
            <div className="ed-device" role="group" aria-label="미리보기 크기">
              <button
                type="button"
                aria-label="휴대폰"
                title="휴대폰 미리보기"
                aria-pressed={device === 'mobile'}
                onClick={() => pickDevice('mobile')}
              >
                <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <rect x="6" y="2" width="12" height="20" rx="2.5" />
                  <path d="M11 18h2" />
                </svg>
              </button>
              <button
                type="button"
                aria-label="데스크톱"
                title="데스크톱 미리보기"
                aria-pressed={device === 'desktop'}
                onClick={() => pickDevice('desktop')}
              >
                <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <rect x="3" y="4" width="18" height="12" rx="1.5" />
                  <path d="M9 20h6M12 16v4" />
                </svg>
              </button>
            </div>
            <div ref={viewRef} className="ed-site-screen">
              {/* 넓은 화면: 실제 기기 크기로 그린 사이트를 줄여 휴대폰 베젤·브라우저 창 안에 띄운다 */}
              <div className={`ed-dev ed-dev--${device}`}>
                {device === 'desktop' ? (
                  <div className="ed-dev-bar" aria-hidden="true">
                    <i />
                    <i />
                    <i />
                    <span>{card.fields.find((f) => f.key === 'shop_name')?.value || card.title}</span>
                  </div>
                ) : (
                  <div className="ed-dev-status" aria-hidden="true">
                    <span>9:41</span>
                    <b />
                  </div>
                )}
                <div className="ed-dev-glass" style={scale ? { width: dev.w * scale, height: dev.h * scale } : undefined}>
                  <iframe
                    key={frameKey}
                    ref={frameRef}
                    className="ed-site-frame"
                    title="사이트 미리보기"
                    sandbox="allow-scripts"
                    srcDoc={frameDoc}
                    onLoad={onFrameLoad}
                    style={
                      scale
                        ? { width: dev.w, height: dev.h, transform: `scale(${scale})`, transformOrigin: '0 0' }
                        : undefined
                    }
                  />
                </div>
              </div>
            </div>
          </div>
          <SectionPanel
            roomId={roomId}
            card={card}
            sections={preview.sections}
            addable={preview.addable}
            added={preview.layout?.added ?? []}
            baseItems={preview.items ?? []}
            baseGroups={preview.groups}
            variant={variant}
            selectedId={pick.id}
            clickedText={pick.text}
            onSelect={(id) => setPick((prev) => ({ ...prev, id, photo: null }))}
            onSaved={handleSaved}
            onDraft={draftFields}
            onPreviewLayout={(layout: CardLayoutEdit) => void runDraft({ layout })}
          />
          {pick.id !== null && pick.photo !== null && onPhotoPick ? (
            <button
              type="button"
              className="ed-btn"
              onClick={() =>
                pick.id !== null &&
                pick.photo !== null &&
                onPhotoPick({ section: pick.id, src: pick.photo.src, index: pick.photo.index })
              }
            >
              사진 고치기
            </button>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

/** 축 이름 (components.json styles 키 → 화면 글). 모르는 축은 키 그대로. */
const AXIS_LABEL: Record<string, string> = { surface: '카드 면', heading: '구역 제목' };

/** 사이트 스타일 고르기: 축마다 한 줄 버튼. 고르면 미리보기에 바로 보이고 저장은 뒤에서. */
export function StylePicker({
  styles,
  value,
  busy,
  onPick,
}: {
  styles: Record<string, StyleAxis>;
  value: Record<string, string>;
  busy: boolean;
  onPick: (axis: string, value: string) => void;
}) {
  return (
    <details className="ed-style">
      <summary>스타일</summary>
      {Object.entries(styles).map(([axis, spec]) => {
        const current = value[axis] ?? spec.default;
        return (
          <div key={axis} className="ed-style__row" role="group" aria-label={AXIS_LABEL[axis] ?? axis}>
            <span className="ed-style__label" aria-hidden="true">
              {AXIS_LABEL[axis] ?? axis}
            </span>
            <div className="ed-seg">
              {Object.entries(spec.values).map(([v, name]) => (
                <button
                  key={v}
                  type="button"
                  aria-pressed={current === v}
                  disabled={busy}
                  onClick={() => current !== v && onPick(axis, v)}
                >
                  {name}
                </button>
              ))}
            </div>
          </div>
        );
      })}
    </details>
  );
}
