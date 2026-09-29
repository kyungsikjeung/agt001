// 실제 요구사항 카드 API 호출 (contracts/ROOM_FEATURES_API.md §5).
// D23 자리 표시는 status가, D27 직접 편집은 PUT fields가, D24 사실 확인은 fact와 pending_owner이 담당한다.
export type CardFieldStatus = 'filled' | 'assumed' | 'placeholder' | 'pending_owner';

export interface CardField {
  key: string;
  label: string;
  value: string;
  status: CardFieldStatus;
  fact: boolean;
  placeholder: boolean;
}

export interface CardPhoto {
  id: string;
  url: string;
  caption?: string | null;
}

/** 공지 띠·팝업 (D56). 빈 글이면 공지 없음. */
export interface CardNotice {
  text: string;
  popup: boolean;
}

export interface RoomCard {
  title: string;
  industry: string | null;
  fields: CardField[];
  photos: CardPhoto[];
  choice: string | null;
  notice?: CardNotice;
  published: string | null;
  site_url: string | null;
  can_edit: boolean;
}

export const MEMBER_KEY = 'agt001_member_id';

/** 이 기기의 방 참여자 확인 값. 못 읽으면 null. */
export function readMemberId(): string | null {
  try {
    return localStorage.getItem(MEMBER_KEY);
  } catch {
    return null;
  }
}

/** 주소창 ?room=<id>을 읽는다. 없거나 비면 null. */
export function readRoomId(search?: string): string | null {
  try {
    const raw = search ?? (typeof location !== 'undefined' ? location.search : '');
    const value = new URLSearchParams(raw).get('room');
    if (!value || value.trim() === '') return null;
    return value;
  } catch {
    return null;
  }
}

/** 상태 배지 문구. filled는 배지를 붙이지 않는다. */
export function statusLabel(status: CardFieldStatus): string | null {
  if (status === 'placeholder') return '입력 필요';
  if (status === 'assumed') return '가정';
  if (status === 'pending_owner') return '확인 대기';
  return null;
}

function memberHeaders(memberId: string | null): Record<string, string> {
  const headers: Record<string, string> = {};
  if (memberId) headers['X-Member-Id'] = memberId;
  return headers;
}

/** 실제 카드를 불러온다. 실패하면 예외를 던져 목업 화면으로 돌린다. */
export async function fetchCard(roomId: string, memberId: string | null): Promise<RoomCard> {
  const res = await fetch(`/api/rooms/${encodeURIComponent(roomId)}/card`, {
    credentials: 'same-origin',
    headers: memberHeaders(memberId),
  });
  if (!res.ok) throw new Error(`카드를 불러오지 못했습니다 (${res.status})`);
  const data = (await res.json()) as RoomCard;
  if (!data || !Array.isArray(data.fields)) throw new Error('카드 모양이 맞지 않아요.');
  return data;
}

/** 바뀐 칸만 저장한다. 빈 문자열은 자리 표시로 되돌린다(서버 계약 §5). */
export async function saveCard(
  roomId: string,
  memberId: string | null,
  fields: Record<string, string>,
  notice?: CardNotice,
): Promise<RoomCard> {
  const res = await fetch(`/api/rooms/${encodeURIComponent(roomId)}/card`, {
    method: 'PUT',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json', ...memberHeaders(memberId) },
    body: JSON.stringify(notice ? { fields, notice } : { fields }),
  });
  if (!res.ok) throw new Error(`저장하지 못했습니다 (${res.status})`);
  const data = (await res.json()) as RoomCard;
  if (!data || !Array.isArray(data.fields)) throw new Error('카드 모양이 맞지 않아요.');
  return data;
}
