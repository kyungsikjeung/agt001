// 백엔드 호출과 유입 측정. 유입 측정은 익명 방문자 ID와 단계만 보낸다 (DECISIONS.md D16).

const VISITOR_KEY = 'agt001_visitor_id';
// room.html이 입장 직후 이 값을 첫 메시지로 보낸다.
export const PENDING_KEY = 'agt001_pending_message';

function safeGet(storage: Storage, key: string): string | null {
  try {
    return storage.getItem(key);
  } catch {
    return null;
  }
}

function safeSet(storage: Storage, key: string, value: string): void {
  try {
    storage.setItem(key, value);
  } catch {
    // 저장소를 못 쓰는 환경(일부 인앱 브라우저)에서도 화면은 계속 동작한다.
  }
}

export function visitorId(): string | null {
  let id = safeGet(localStorage, VISITOR_KEY);
  if (!id) {
    id = `v-${crypto.randomUUID ? crypto.randomUUID() : String(Math.random()).slice(2)}`;
    safeSet(localStorage, VISITOR_KEY, id);
  }
  return id;
}

function sourceInfo(): { source: string | null; campaign: string | null } {
  const params = new URLSearchParams(location.search);
  let source = params.get('utm_source');
  if (!source && document.referrer) {
    try {
      const host = new URL(document.referrer).hostname;
      source = host === location.hostname ? null : host;
    } catch {
      source = null;
    }
  }
  return { source, campaign: params.get('utm_campaign') };
}

export type FunnelEvent = 'landing_view' | 'start_click' | 'template_click' | 'login_click' | 'chat_open';

export function track(event: FunnelEvent, templateId?: string): void {
  const body = JSON.stringify({ event, visitor_id: visitorId(), template_id: templateId, ...sourceInfo() });
  // 페이지를 떠나는 클릭에서도 전송되도록 keepalive. 실패해도 화면 동작에는 영향이 없다.
  fetch('/events', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body, keepalive: true }).catch(
    () => {},
  );
}

/** 방을 만들고, 입력한 내용을 첫 메시지로 넘긴 뒤 채팅방으로 이동한다. */
export async function startRoom(message: string, templateId?: string): Promise<void> {
  const res = await fetch('/room', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ template_id: templateId ?? null }),
  });
  if (!res.ok) throw new Error(`방을 만들지 못했습니다 (${res.status})`);
  const { room_id: roomId } = (await res.json()) as { room_id: string };
  safeSet(sessionStorage, PENDING_KEY, JSON.stringify({ roomId, text: message, templateId: templateId ?? null }));
  location.href = `/room.html?room=${encodeURIComponent(roomId)}`;
}
