// 주소 검색 시트 (MAP_CONTRACT §3).
// 우편번호 스크립트는 단추를 누를 때만 한 번 불러온다. 가게 이름·전화는 어디에도 보내지 않는다.
import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { geoSearch, readMemberId, saveCard, saveGeo, type RoomCard } from '../editor/cardApi';

const POSTCODE_SRC = '//t1.daumcdn.net/mapjsapi/bundle/postcode/prod/postcode.v2.js';

interface PostcodeData {
  roadAddress?: string;
  jibunAddress?: string;
  address?: string;
}

interface DaumWindow {
  daum?: { Postcode?: new (opts: { oncomplete: (data: PostcodeData) => void; width?: string; height?: string }) => { embed: (el: HTMLElement) => void } };
}

/** 우편번호 스크립트를 한 번만 붙인다. 다 붙었으면 바로 끝난다. */
function loadPostcodeOnce(): Promise<void> {
  const w = window as unknown as DaumWindow;
  let tag = document.querySelector('script[src*="postcode.v2.js"]') as HTMLScriptElement | null;
  if (!tag) {
    tag = document.createElement('script');
    tag.src = POSTCODE_SRC;
    tag.async = true;
    document.head.appendChild(tag);
  }
  if (w.daum?.Postcode) return Promise.resolve();
  const el = tag;
  return new Promise((resolve) => {
    el.addEventListener('load', () => resolve(), { once: true });
    el.addEventListener('error', () => resolve(), { once: true });
  });
}

interface AddressSearchProps {
  roomId: string;
  onSaved: (card: RoomCard) => void;
}

export default function AddressSearch({ roomId, onSaved }: AddressSearchProps) {
  const [open, setOpen] = useState(false);
  const [road, setRoad] = useState('');
  const [jibun, setJibun] = useState('');
  const [detail, setDetail] = useState('');
  const [picked, setPicked] = useState(false);
  const [msg, setMsg] = useState('');
  const [busy, setBusy] = useState(false);
  const embedRef = useRef<HTMLDivElement | null>(null);
  const closeRef = useRef<HTMLButtonElement | null>(null);

  function close() {
    setOpen(false);
    setPicked(false);
    setRoad('');
    setJibun('');
    setDetail('');
    setMsg('');
    setBusy(false);
  }

  // 시트를 열 때만 스크립트를 붙이고 그 칸에 우편번호 창을 둔다(팝업 금지).
  useEffect(() => {
    if (!open) return;
    let alive = true;
    closeRef.current?.focus();
    (async () => {
      await loadPostcodeOnce();
      if (!alive) return;
      const box = embedRef.current;
      const w = window as unknown as DaumWindow;
      if (!box || !w.daum?.Postcode) {
        setMsg('주소 창을 열지 못했어요. 잠시 뒤 다시 눌러 주세요.');
        return;
      }
      box.replaceChildren();
      try {
        // 폭을 안 주면 우편번호 창이 500px로 들어와 390px 화면에서 옆으로 넘친다
        new w.daum.Postcode({
          width: '100%',
          height: '100%',
          oncomplete: (data) => {
            if (!alive) return;
            // 지번을 고르면 도로명이 빌 수 있다 → 지번·고른 주소로 채운다
            setRoad(data.roadAddress || data.jibunAddress || data.address || '');
            setJibun(data.jibunAddress ?? '');
            setDetail('');
            setPicked(true);
            setMsg('');
          },
        }).embed(box);
      } catch {
        setMsg('주소 창을 열지 못했어요. 잠시 뒤 다시 눌러 주세요.');
      }
    })();
    return () => {
      alive = false;
    };
  }, [open ]);

  // Esc로 닫는다.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') close();
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open ]);

  // 저장: 도로명으로 좌표를 찾아 PUT /geo. 후보가 없으면 주소 글자만 저장할지 묻는다.
  async function runSave() {
    if (busy || road.trim() === '') return;
    setBusy(true);
    setMsg('');
    try {
      const cands = await geoSearch(roomId, readMemberId(), road.trim());
      const first = cands[0];
      if (first) {
        const updated = await saveGeo(roomId, readMemberId(), {
          road: road.trim(),
          jibun,
          detail: detail.trim(),
          x: first.x,
          y: first.y,
          src: 'postcode',
        });
        onSaved(updated);
        close();
        return;
      }
      if (!window.confirm('지도 위치를 찾지 못했어요. 주소만 저장할까요?')) return;
      const location = detail.trim() === '' ? road.trim() : `${road.trim()} ${detail.trim()}`;
      const updated = await saveCard(roomId, readMemberId(), { location });
      onSaved(updated);
      close();
    } catch {
      setMsg('저장하지 못했어요. 잠시 뒤 다시 눌러 주세요.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <button type="button" className="bd-addr-open" onClick={() => { setOpen(true); setMsg(''); }}>
        주소 검색
      </button>
      {/* 시트는 body로 꺼내 그린다: 헤더 안에 두면 fixed가 헤더 기준이 되어 잘리고 하단 줄 뒤로 깔린다 */}
      {open ? createPortal(
        <div className="bd-addr-scrim">
          <div className="bd-addr-sheet" role="dialog" aria-label="주소 검색">
            <div className="bd-addr-top">
              <h2 className="bd-addr-title">주소 검색</h2>
              <button ref={closeRef} type="button" className="bd-addr-close" onClick={close}>
                닫기
              </button>
            </div>
            <div ref={embedRef} className="bd-addr-post" />
            {picked ? (
              <>
                <p className="bd-addr-picked">고른 주소: {road}</p>
                <label className="bd-addr-label" htmlFor="bd-addr-detail">
                  상세 주소(층·호)
                  <input
                    id="bd-addr-detail"
                    className="ed-input"
                    type="text"
                    value={detail}
                    maxLength={100}
                    placeholder="예: 2층 201호"
                    disabled={busy}
                    onChange={(e) => setDetail(e.target.value)}
                  />
                </label>
                <button
                  type="button"
                  className="ed-btn ed-btn--primary bd-addr-save"
                  disabled={busy}
                  onClick={() => void runSave()}
                >
                  {busy ? '저장 중…' : '저장'}
                </button>
              </>
            ) : null}
            {msg !== '' ? <p className="bd-msg" role="status">{msg}</p> : null}
          </div>
        </div>,
        document.body,
      ) : null}
    </>
  );
}
