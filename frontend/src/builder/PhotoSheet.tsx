// 사진 시트 (PHOTO_EDIT_CONTRACT §5).
// 미리보기에서 사진을 누르면 열린다. 후보를 보고 "이걸로 쓰기"를 눌러야 바뀐다.
import { useEffect, useRef, useState } from 'react';
import {
  applyPhotoEdit,
  getPhotoTarget,
  previewPhotoEdit,
  undoPhotoEdit,
  type PhotoCandidate,
  type PhotoTarget,
} from './photoApi';
import './photoSheet.css';

export interface PhotoSheetPick {
  section: string;
  src: string;
  index: number;
}

interface PhotoSheetProps {
  roomId: string;
  pick: PhotoSheetPick | null;
  onClose: () => void;
  onApplied: (target: string, url: string) => void;
}

/** 보정 action 이름 → 짧은 버튼 말. 모르는 값은 그대로 보인다. */
function actionLabel(action: string): string {
  if (action === 'brighter') return '더 밝게';
  if (action === 'warmer') return '따뜻하게';
  if (action === 'sharper') return '선명하게';
  if (action === 'square') return '정사각형';
  if (action === 'wide') return '가로 4:3';
  return action;
}

/** AI 말 예시. */
const EXAMPLES = ['여름 느낌으로', '배경 흐리게', '더 따뜻한 조명'];

function errMsg(e: unknown): string {
  return e instanceof Error ? e.message : '고치지 못했어요.';
}

export default function PhotoSheet({ roomId, pick, onClose, onApplied }: PhotoSheetProps) {
  const [info, setInfo] = useState<PhotoTarget | null>(null);
  const [nowUrl, setNowUrl] = useState('');
  const [targetBusy, setTargetBusy] = useState(false);
  const [busy, setBusy] = useState(false);
  const [applyBusy, setApplyBusy] = useState(false);
  const [undoBusy, setUndoBusy] = useState(false);
  const [candidate, setCandidate] = useState<PhotoCandidate | null>(null);
  const [instruction, setInstruction] = useState('');
  const [err, setErr] = useState('');
  const [canUndo, setCanUndo] = useState(false);
  /** 늦게 온 미리보기 응답을 버리는 번호. */
  const reqId = useRef(0);

  useEffect(() => {
    if (!pick) return;
    let alive = true;
    setInfo(null);
    setNowUrl('');
    setCandidate(null);
    setInstruction('');
    setErr('');
    setCanUndo(false);
    setBusy(false);
    reqId.current += 1;
    setTargetBusy(true);
    (async () => {
      try {
        const t = await getPhotoTarget(roomId, pick);
        if (!alive) return;
        setInfo(t);
        setNowUrl(t.current_url);
      } catch (e) {
        if (!alive) return;
        setErr(errMsg(e));
      } finally {
        if (alive) setTargetBusy(false);
      }
    })();
    return () => {
      alive = false;
    };
  }, [roomId, pick?.section, pick?.src, pick?.index]);

  if (!pick) return null;

  /** 후보를 만든다. 늦게 오면 무시된다(취소). */
  async function runPreview(body: { target: string; action?: string; instruction?: string }) {
    const id = reqId.current + 1;
    reqId.current = id;
    setBusy(true);
    setErr('');
    try {
      const c = await previewPhotoEdit(roomId, body);
      if (reqId.current !== id) return;
      setCandidate(c);
    } catch (e) {
      if (reqId.current !== id) return;
      setErr(errMsg(e));
    } finally {
      if (reqId.current === id) setBusy(false);
    }
  }

  /** 기다림을 그만둔다. 늦게 온 답은 버린다. */
  function cancelPreview() {
    reqId.current += 1;
    setBusy(false);
  }

  async function runApply() {
    if (!info || !candidate || applyBusy) return;
    setApplyBusy(true);
    setErr('');
    try {
      const r = await applyPhotoEdit(roomId, candidate.candidate_id);
      setNowUrl(r.url);
      setCandidate(null);
      setCanUndo(r.undo);
      onApplied(info.target, r.url);
    } catch (e) {
      setErr(errMsg(e));
    } finally {
      setApplyBusy(false);
    }
  }

  async function runUndo() {
    if (!info || undoBusy) return;
    setUndoBusy(true);
    setErr('');
    try {
      const r = await undoPhotoEdit(roomId, info.target);
      setNowUrl(r.url);
      setCanUndo(false);
      onApplied(info.target, r.url);
    } catch (e) {
      setErr(errMsg(e));
    } finally {
      setUndoBusy(false);
    }
  }

  const aiOn = info !== null && info.kind !== 'owner' && info.ai_allowed;

  return (
    <div className="ph-scrim">
      <div className="ph-sheet" role="dialog" aria-label="사진 고치기">
        <div className="ph-top">
          <h2 className="ph-title">사진 고치기</h2>
          <button type="button" className="ph-btn" onClick={onClose}>
            닫기
          </button>
        </div>
        {targetBusy && <p className="ph-msg">사진을 불러오는 중이에요.</p>}
        {err !== '' && (
          <p className="ph-error" role="alert">
            {err}
          </p>
        )}
        {info && (
          <>
            {nowUrl !== '' && <img className="ph-photo" src={nowUrl} alt="지금 사진" />}
            <div className="ph-actions" role="group" aria-label="보정">
              {info.actions.map((a) => (
                <button
                  key={a}
                  type="button"
                  className="ph-btn"
                  disabled={busy || applyBusy}
                  onClick={() => void runPreview({ target: info.target, action: a })}
                >
                  {actionLabel(a)}
                </button>
              ))}
            </div>
            {info.kind === 'owner' && <p className="ph-notice">실제 사진은 밝기·색감·자르기만 바꿔요.</p>}
            {aiOn && (
              <div className="ph-ai">
                <label className="ph-label" htmlFor="ph-instruction">
                  AI로 고치기
                </label>
                <input
                  id="ph-instruction"
                  className="ph-input"
                  value={instruction}
                  onChange={(e) => setInstruction(e.target.value)}
                  placeholder="예: 더 따뜻한 느낌으로"
                />
                <div className="ph-chips">
                  {EXAMPLES.map((ex) => (
                    <button key={ex} type="button" className="ph-chip" onClick={() => setInstruction(ex)}>
                      {ex}
                    </button>
                  ))}
                </div>
                <p className="ph-msg">오늘 {info.left_today}번 남았어요.</p>
                <button
                  type="button"
                  className="ph-btn ph-btn--primary"
                  disabled={busy || instruction.trim() === ''}
                  onClick={() => void runPreview({ target: info.target, instruction: instruction.trim() })}
                >
                  AI로 고치기
                </button>
              </div>
            )}
          </>
        )}
        {busy && (
          <div className="ph-wait">
            <p className="ph-msg">사진을 고치는 중이에요(최대 1분).</p>
            <button type="button" className="ph-btn" onClick={cancelPreview}>
              취소하기
            </button>
          </div>
        )}
        {candidate && !busy && (
          <div className="ph-result">
            <div className="ph-compare">
              <figure className="ph-shot">
                <img src={candidate.before_url} alt="바꾸기 전" />
                <figcaption>바꾸기 전</figcaption>
              </figure>
              <figure className="ph-shot">
                <img src={candidate.after_url} alt="바꾼 뒤" />
                <figcaption>바꾼 뒤</figcaption>
              </figure>
            </div>
            <div className="ph-row">
              <button
                type="button"
                className="ph-btn ph-btn--primary"
                disabled={applyBusy}
                onClick={() => void runApply()}
              >
                이걸로 쓰기
              </button>
              <button type="button" className="ph-btn" disabled={applyBusy} onClick={() => setCandidate(null)}>
                그대로 두기
              </button>
            </div>
          </div>
        )}
        {canUndo && !candidate && (
          <button type="button" className="ph-btn" disabled={undoBusy} onClick={() => void runUndo()}>
            되돌리기
          </button>
        )}
      </div>
    </div>
  );
}
