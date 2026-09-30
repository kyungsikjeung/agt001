// 사진 고치기 API (PHOTO_EDIT_CONTRACT §4).
// cardApi.ts와 같은 방식: 같은 출처, X-Member-Id는 localStorage에서 읽는다.

/** 미리보기에서 사진을 눌렀다는 뜻. */
export interface PhotoPick {
  section: string;
  src: string;
  index: number;
}

/** 사진 종류. 사장님 사진은 보정만 된다. */
export type PhotoKind = 'owner' | 'ai' | 'example';

/** GET target 응답 (PHOTO_EDIT_CONTRACT §4). */
export interface PhotoTarget {
  target: string;
  kind: PhotoKind;
  current_url: string;
  actions: string[];
  ai_allowed: boolean;
  left_today: number;
  cooldown_sec: number;
}

/** POST preview 응답. 후보로만 저장된다. */
export interface PhotoCandidate {
  candidate_id: string;
  before_url: string;
  after_url: string;
}

/** POST apply 응답. */
export interface PhotoApplied {
  ok: boolean;
  url: string;
  undo: boolean;
}

/** POST undo 응답. */
export interface PhotoUndone {
  ok: boolean;
  url: string;
}

const MEMBER_KEY = 'agt001_member_id';

/** 이 기기의 방 참여자 확인 값. 못 읽으면 null. */
function readMemberId(): string | null {
  try {
    return localStorage.getItem(MEMBER_KEY);
  } catch {
    return null;
  }
}

function memberHeaders(): Record<string, string> {
  const headers: Record<string, string> = {};
  const id = readMemberId();
  if (id) headers['X-Member-Id'] = id;
  return headers;
}

/** 실패 응답의 서버 detail을 읽는다. 없으면 상태 번호만. */
async function detailOf(res: Response): Promise<string> {
  try {
    const data = (await res.json()) as { detail?: unknown };
    if (data && typeof data.detail === 'string' && data.detail.trim() !== '') return data.detail;
  } catch {
    // 아래 기본 문구로 떨어진다.
  }
  return `요청하지 못했습니다 (${res.status})`;
}

/** 대상 사진을 찾는다. 못 정하면 서버가 400 detail을 준다. */
export async function getPhotoTarget(roomId: string, pick: PhotoPick): Promise<PhotoTarget> {
  const q = new URLSearchParams({
    section: pick.section,
    src: pick.src,
    index: String(pick.index),
  });
  const res = await fetch(`/api/rooms/${encodeURIComponent(roomId)}/photo-edit/target?${q.toString()}`, {
    credentials: 'same-origin',
    headers: memberHeaders(),
  });
  if (!res.ok) throw new Error(await detailOf(res));
  const data = (await res.json()) as PhotoTarget;
  if (!data || typeof data.target !== 'string' || typeof data.current_url !== 'string' || !Array.isArray(data.actions)) {
    throw new Error('사진 모양이 맞지 않아요.');
  }
  return data;
}

/** 후보를 만든다. action(보정) 또는 instruction(AI 말) 중 하나만 보낸다. */
export async function previewPhotoEdit(
  roomId: string,
  body: { target: string; action?: string; instruction?: string },
): Promise<PhotoCandidate> {
  const res = await fetch(`/api/rooms/${encodeURIComponent(roomId)}/photo-edit/preview`, {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json', ...memberHeaders() },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await detailOf(res));
  const data = (await res.json()) as PhotoCandidate;
  if (!data || typeof data.candidate_id !== 'string' || typeof data.after_url !== 'string') {
    throw new Error('사진 모양이 맞지 않아요.');
  }
  return data;
}

/** 후보를 그 칸에 쓴다. */
export async function applyPhotoEdit(roomId: string, candidateId: string): Promise<PhotoApplied> {
  const res = await fetch(`/api/rooms/${encodeURIComponent(roomId)}/photo-edit/apply`, {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json', ...memberHeaders() },
    body: JSON.stringify({ candidate_id: candidateId }),
  });
  if (!res.ok) throw new Error(await detailOf(res));
  const data = (await res.json()) as PhotoApplied;
  if (!data || typeof data.url !== 'string') throw new Error('사진 모양이 맞지 않아요.');
  return data;
}

/** 직전 사진으로 되돌린다. 1단계만 된다. */
export async function undoPhotoEdit(roomId: string, target: string): Promise<PhotoUndone> {
  const res = await fetch(`/api/rooms/${encodeURIComponent(roomId)}/photo-edit/undo`, {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json', ...memberHeaders() },
    body: JSON.stringify({ target }),
  });
  if (!res.ok) throw new Error(await detailOf(res));
  const data = (await res.json()) as PhotoUndone;
  if (!data || typeof data.url !== 'string') throw new Error('사진 모양이 맞지 않아요.');
  return data;
}
