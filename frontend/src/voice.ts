// 첫 화면 음성 입력. 채팅방 static/voice.js와 같은 계약(POST /api/stt, multipart audio, X-Member-Id)과 같은 안내 문구.
// 녹음 → 글자로 바꿔 입력창에 넣기만 한다(자동 전송 없음). 녹음은 서버에서 전사 직후 지운다.
import { useEffect, useRef, useState } from 'react';
import { visitorId } from './api';

export const MAX_SECONDS = 60;
export const MAX_BYTES = 5 * 1024 * 1024;

export const MSG = {
  keyboardMic: '휴대폰 키보드의 마이크 버튼으로 말해도 돼요',
  uploading: '글자로 바꾸는 중…',
  checkNumbers: '번호와 금액이 맞는지 확인해 주세요',
  permissionDenied: '마이크 권한이 거부됐어요. 브라우저 설정에서 마이크를 허용한 뒤 다시 눌러 주세요.',
  noMic: '마이크를 찾을 수 없어요. 휴대폰 키보드의 마이크 버튼으로 말해도 돼요.',
  recordFail: '녹음을 시작할 수 없어요. 휴대폰 키보드의 마이크 버튼으로 말해도 돼요.',
  inApp: '인앱 브라우저에서는 녹음이 안 될 수 있어요. 오른쪽 위 메뉴에서 다른 브라우저로 열기해 보세요.',
  emptyRecord: '녹음이 비어 있어요. 다시 짧게 말해 주세요.',
  tooBig: '녹음이 너무 커요. 60초 이내, 5MB 이하로 짧게 말해 주세요.',
  emptyText: '글자를 찾지 못했어요. 다시 또렷하게 말해 주세요.',
  badRequest: '음성 파일을 읽지 못했어요. 다시 짧게 말해 주세요.',
  unsupportedType: '이 브라우저의 녹음 형식을 쓸 수 없어요. 휴대폰 키보드의 마이크 버튼으로 말해도 돼요.',
  tooMany: '요청이 너무 잦아요. 잠시 뒤에 다시 시도해 주세요.',
  unavailable: '지금은 음성 인식을 쓸 수 없어요. 키보드 마이크로 말해 주세요',
  networkFail: '전송에 실패했어요. 인터넷 연결을 확인하고 다시 시도해 주세요.',
};

const MIME_CANDIDATES = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/ogg;codecs=opus', 'audio/wav'];

export function voiceSupported(): boolean {
  return !!navigator.mediaDevices?.getUserMedia && typeof window.MediaRecorder !== 'undefined';
}

function isInApp(): boolean {
  return /kakaotalk|naver/i.test(navigator.userAgent || '');
}

function withInApp(text: string): string {
  return isInApp() ? `${text} ${MSG.inApp}` : text;
}

/** 전사 글자에 전화번호·가격이 있는지. Parakeet는 숫자를 한글("공일공…")로 내놓기도 한다. */
export function hasNumber(text: string): boolean {
  if (/[0-9]/.test(text)) return true;
  if (/[공영일두이삼사오육륙칠팔구십백천만억]{3,}/.test(text.replace(/\s+/g, ''))) return true;
  return /(전화번호|휴대폰|계좌|가격|금액)/.test(text);
}

export function errorFor(status: number): string {
  if (status === 400) return MSG.badRequest;
  if (status === 413) return MSG.tooBig;
  if (status === 415) return MSG.unsupportedType;
  if (status === 429) return MSG.tooMany;
  if (status === 503) return MSG.unavailable;
  return withInApp(MSG.networkFail);
}

function memberId(): string {
  try {
    const v = localStorage.getItem('agt001_member_id');
    if (v) return v;
  } catch {
    // 저장소를 못 쓰는 환경
  }
  return visitorId() ?? '';
}

function extFromType(type: string): string {
  if (/mp4/i.test(type)) return 'mp4';
  if (/ogg/i.test(type)) return 'ogg';
  if (/wav/i.test(type)) return 'wav';
  return 'webm';
}

/** 녹음 파일 → 글자. 실패하면 사장님께 보일 문구를 담은 Error를 던진다. */
export async function transcribe(blob: Blob): Promise<string> {
  const ext = extFromType(blob.type);
  const form = new FormData();
  form.append('audio', new File([blob], `audio.${ext}`, { type: blob.type || `audio/${ext}` }));
  let res: Response;
  try {
    res = await fetch('/api/stt', { method: 'POST', headers: { 'X-Member-Id': memberId() }, body: form });
  } catch {
    throw new Error(withInApp(MSG.networkFail));
  }
  if (!res.ok) throw new Error(errorFor(res.status));
  const data = (await res.json()) as { text?: unknown };
  const text = typeof data.text === 'string' ? data.text.trim() : '';
  if (!text) throw new Error(MSG.emptyText);
  return text;
}

type State = 'idle' | 'recording' | 'uploading';

/** 한 번 누르면 녹음, 다시 누르면(또는 60초) 멈추고 글자로 바꿔 onText로 넘긴다. */
export function useVoiceInput(onText: (text: string) => void) {
  const [state, setState] = useState<State>('idle');
  const [seconds, setSeconds] = useState(0);
  const [status, setStatus] = useState<string | null>(null);
  const [numCheck, setNumCheck] = useState(false);
  const recorder = useRef<MediaRecorder | null>(null);
  const timers = useRef<number[]>([]);
  const onTextRef = useRef(onText);
  onTextRef.current = onText;

  function clearTimers() {
    timers.current.forEach((id) => window.clearInterval(id));
    timers.current = [];
  }

  // 화면을 떠나면 마이크를 놓는다.
  useEffect(
    () => () => {
      clearTimers();
      recorder.current?.stream.getTracks().forEach((t) => t.stop());
    },
    [],
  );

  async function finish(chunks: Blob[], type: string) {
    const blob = new Blob(chunks, { type: type || 'audio/webm' });
    if (!blob.size) return setStatus(MSG.emptyRecord);
    if (blob.size > MAX_BYTES) return setStatus(MSG.tooBig);
    setState('uploading');
    setStatus(MSG.uploading);
    try {
      const text = await transcribe(blob);
      setNumCheck(hasNumber(text));
      setStatus(null);
      onTextRef.current(text);
    } catch (e) {
      setStatus(e instanceof Error ? e.message : withInApp(MSG.networkFail));
    } finally {
      setState('idle');
    }
  }

  async function start() {
    setNumCheck(false);
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (e) {
      const name = (e as { name?: string })?.name ?? '';
      if (name === 'NotAllowedError' || name === 'SecurityError') setStatus(MSG.permissionDenied);
      else if (['NotFoundError', 'NotReadableError', 'OverconstrainedError'].includes(name)) setStatus(MSG.noMic);
      else setStatus(withInApp(MSG.recordFail));
      return;
    }
    const mime = MIME_CANDIDATES.find((m) => MediaRecorder.isTypeSupported?.(m)) ?? '';
    let rec: MediaRecorder;
    try {
      rec = mime ? new MediaRecorder(stream, { mimeType: mime }) : new MediaRecorder(stream);
      const chunks: Blob[] = [];
      rec.ondataavailable = (ev) => ev.data?.size && chunks.push(ev.data);
      rec.onstop = () => {
        clearTimers();
        stream.getTracks().forEach((t) => t.stop()); // 멈추면 바로 마이크를 놓는다
        recorder.current = null;
        void finish(chunks, rec.mimeType || chunks[0]?.type || '');
      };
      rec.start(1000);
    } catch {
      stream.getTracks().forEach((t) => t.stop());
      setStatus(withInApp(MSG.recordFail));
      return;
    }
    recorder.current = rec;
    const began = Date.now();
    setSeconds(0);
    setStatus(null);
    setState('recording');
    timers.current.push(
      window.setInterval(() => setSeconds(Math.floor((Date.now() - began) / 1000)), 500),
      window.setTimeout(stop, MAX_SECONDS * 1000),
    );
  }

  function stop() {
    const rec = recorder.current;
    if (!rec || rec.state === 'inactive') return;
    clearTimers();
    rec.stop();
  }

  function toggle() {
    if (state === 'recording') stop();
    else if (state === 'idle') void start();
  }

  return { state, seconds, status, numCheck, toggle, clearNumCheck: () => setNumCheck(false) };
}
