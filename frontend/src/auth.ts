// 로그인 상태 확인·시작·종료와 게스트 방 계정 귀속 (1단계 계정).
// /api/me가 404이면(서버 아직 배포 전) 로그인 안 함으로 처리해 화면이 깨지지 않게 한다.

export type LoginProvider = 'kakao' | 'google';

export interface MeUser {
  id: string;
  nickname: string;
  provider: string;
}

/** 로그인 사용자. 로그인 안 함(401)이나 서버 미배포(404), 네트워크 실패면 null. */
export async function me(): Promise<MeUser | null> {
  let res: Response;
  try {
    res = await fetch('/api/me', { credentials: 'same-origin' });
  } catch {
    return null;
  }
  if (res.status === 401 || res.status === 404) return null;
  if (!res.ok) return null;
  try {
    const data = (await res.json()) as { user?: MeUser };
    return data.user ?? null;
  } catch {
    return null;
  }
}

/** 로그아웃. 같은 출처에서만 동작하며, 실패해도 화면은 로그인 안 함으로 둔다. */
export async function logout(): Promise<void> {
  try {
    await fetch('/api/logout', { method: 'POST', credentials: 'same-origin' });
  } catch {
    // 네트워크 실패해도 화면 상태는 로그아웃으로 둔다.
  }
}

/** 제공자 로그인 페이지로 이동한다. 브라우저 이동이며 fetch가 아니다. */
export function startLogin(provider: LoginProvider, next = '/projects'): void {
  location.href = `/auth/${provider}/start?next=${encodeURIComponent(next)}`;
}

/** 이 기기의 방을 로그인 계정으로 옮긴다. 로그인 안 함(401)이면 0. */
export async function claim(roomIds: string[], memberId: string | null): Promise<number> {
  // 서버는 X-Member-Id가 그 방의 참여자일 때만 옮긴다 (AUTH_REVIEW #8).
  if (roomIds.length === 0 || !memberId) return 0;
  let res: Response;
  try {
    res = await fetch('/api/me/claim', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', 'X-Member-Id': memberId },
      body: JSON.stringify({ room_ids: roomIds }),
    });
  } catch {
    return 0;
  }
  if (!res.ok) return 0;
  try {
    const data = (await res.json()) as { claimed?: number };
    return typeof data.claimed === 'number' ? data.claimed : 0;
  } catch {
    return 0;
  }
}
