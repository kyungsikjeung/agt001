// 말로 고치기 입력줄 (SAY_CONTRACT §7).
// 글 입력 + 보내기 + 마이크(voice.ts, 알아들은 글은 입력에만 넣고 자동 전송 없음).
// 답은 칩 줄 위 말풍선(4초 뒤 흐려지고 누르면 다시), rejected는 말풍선 아래 작은 글,
// undo:true면 다음 변경 전까지 되돌리기 버튼, 보내는 중엔 입력 잠금.
import { useEffect, useRef, useState } from 'react';
import { readMemberId, say, undoSay, type SayResponse, type UndoResponse } from '../editor/cardApi';
import { useVoiceInput } from '../voice';

export const SAY_MAX_LEN = 300;
const FADE_MS = 4000;

export default function SayBar({
  roomId,
  clearUndoOn,
  onApplied,
  onUndone,
}: {
  roomId: string;
  /** 다른 변경(칩·위 칸·모양)이 있으면 되돌리기 버튼을 숨긴다. 바뀔 때마다 올리는 수. */
  clearUndoOn: number;
  /** say 응답 뒤: 칩 갱신 + 미리보기 다시 그림은 부모가 한다. */
  onApplied: (r: SayResponse) => void;
  /** undo 응답 뒤: 칩 갱신 + 미리보기 다시 그림은 부모가 한다. */
  onUndone: (r: UndoResponse) => void;
}) {
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [reply, setReply] = useState<string | null>(null);
  const [rejected, setRejected] = useState<string[]>([]);
  const [faded, setFaded] = useState(false);
  const [canUndo, setCanUndo] = useState(false);
  const [undoBusy, setUndoBusy] = useState(false);
  const [failed, setFailed] = useState('');
  const fadeTimer = useRef(0);
  const firstClear = useRef(true);

  const voice = useVoiceInput((text) => {
    setInput((prev) => (prev ? `${prev} ${text}` : text).slice(0, SAY_MAX_LEN));
  });

  useEffect(() => {
    if (firstClear.current) {
      firstClear.current = false;
      return;
    }
    setCanUndo(false);
  }, [clearUndoOn]);

  useEffect(() => () => window.clearTimeout(fadeTimer.current), []);

  function showReply(text: string) {
    window.clearTimeout(fadeTimer.current);
    setReply(text);
    setFaded(false);
    fadeTimer.current = window.setTimeout(() => setFaded(true), FADE_MS);
  }

  function reopen() {
    if (!faded || !reply) return;
    showReply(reply);
  }

  async function send() {
    const text = input.trim().slice(0, SAY_MAX_LEN);
    if (!text || sending) return;
    setSending(true);
    setFailed('');
    try {
      const r = await say(roomId, readMemberId(), text);
      setRejected(r.rejected ?? []);
      setCanUndo(r.undo);
      showReply(r.reply);
      setInput('');
      onApplied(r);
    } catch {
      setFailed('보내지 못했어요. 잠시 뒤 다시 말해 주세요.');
    } finally {
      setSending(false);
    }
  }

  async function undo() {
    if (undoBusy) return;
    setUndoBusy(true);
    setFailed('');
    try {
      const r = await undoSay(roomId, readMemberId());
      setCanUndo(false);
      showReply(r.reply);
      onUndone(r);
    } catch {
      setFailed('되돌리지 못했어요. 잠시 뒤 다시 눌러 주세요.');
    } finally {
      setUndoBusy(false);
    }
  }

  return (
    <div className="bd-say">
      {reply ? (
        <button
          type="button"
          className={faded ? 'bd-say-bubble bd-say-bubble--faded' : 'bd-say-bubble'}
          aria-live="polite"
          aria-label={faded ? '답 다시 보기' : '고치기 답'}
          onClick={reopen}
        >
          {reply}
        </button>
      ) : null}
      {rejected.length > 0 ? (
        <ul className="bd-say-rejected" aria-label="넣지 않은 말">
          {rejected.map((r, i) => (
            <li key={i}>{r}</li>
          ))}
        </ul>
      ) : null}
      {canUndo ? (
        <button
          type="button"
          className="ed-btn bd-say-undo"
          disabled={undoBusy}
          onClick={() => void undo()}
        >
          {undoBusy ? '되돌리는 중…' : '되돌리기'}
        </button>
      ) : null}
      {failed ? (
        <p className="bd-msg bd-msg--error" role="alert">
          {failed}
        </p>
      ) : null}
      <div className="bd-say-row">
        <input
          className="bd-say-input"
          type="text"
          value={input}
          maxLength={SAY_MAX_LEN}
          disabled={sending}
          placeholder="예: 메뉴에 빙수 넣어 줘"
          aria-label="말로 고치기"
          onChange={(e) => setInput(e.target.value.slice(0, SAY_MAX_LEN))}
          onKeyDown={(e) => {
            if (e.key === 'Enter') void send();
          }}
        />
        <button
          type="button"
          className="ed-btn ed-btn--primary bd-say-send"
          disabled={sending || !input.trim()}
          onClick={() => void send()}
        >
          {sending ? '고치는 중…' : '보내기'}
        </button>
        <button
          type="button"
          className="ed-btn bd-say-mic"
          disabled={voice.state === 'uploading'}
          aria-label={voice.state === 'recording' ? '녹음 멈추기' : '음성으로 적기'}
          onClick={voice.toggle}
        >
          {voice.state === 'recording' ? '멈춤' : '마이크'}
        </button>
      </div>
      {voice.state === 'recording' ? <p className="bd-msg" role="status">듣는 중… {voice.seconds}초</p> : null}
      {voice.status ? <p className="bd-msg" role="status">{voice.status}</p> : null}
    </div>
  );
}
