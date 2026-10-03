// agt001 서비스 워커 (PWA: 안드로이드 홈 화면 설치, 주최 요구 5).
// 원칙: 온라인이 먼저다. 대화·로그인·API는 절대 저장하지 않고, 화면 이동이 오프라인으로 실패할 때만 안내 페이지를 보인다.
const CACHE = 'agt001-shell-v1';
const SHELL = ['/offline.html', '/icons/icon-192.png', '/manifest.json'];
const NEVER = ['/api/', '/auth/', '/room/', '/chat', '/design/', '/site/'];

self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin || NEVER.some((p) => url.pathname.startsWith(p))) return;
  if (req.mode === 'navigate') {
    event.respondWith(fetch(req).catch(() => caches.match('/offline.html')));
  }
});

// ── 휴대폰 알림(웹 푸시, OWNER_NOTIFY_PLAN N6) ──
// 서버(app/services/push.py)가 {title, body, url, tag}를 암호화해 보낸다. 누르면 우리 사이트 안 주소만 연다.
self.addEventListener('push', (event) => {
  let data = {};
  try { data = event.data ? event.data.json() : {}; } catch (e) { data = { body: event.data ? event.data.text() : '' }; }
  const title = data.title || '한마디';
  const options = {
    body: data.body || '새 알림이 있어요.',
    icon: '/icons/icon-192.png',
    badge: '/icons/icon-192.png',
    lang: 'ko',
    data: { url: data.url || '/owner' },
  };
  if (data.tag) { options.tag = data.tag; options.renotify = true; }  // 같은 가게 알림은 하나로 모으되 다시 울린다
  event.waitUntil(self.registration.showNotification(title, options));
});

function safeUrl(raw) {
  try {
    const u = new URL(raw || '/owner', self.location.origin);
    return u.origin === self.location.origin ? u.href : self.location.origin + '/owner';
  } catch (e) {
    return self.location.origin + '/owner';
  }
}

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const target = safeUrl(event.notification.data && event.notification.data.url);
  event.waitUntil((async () => {
    const wins = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
    const same = wins.find((w) => w.url === target);
    if (same) return same.focus();
    const any = wins.find((w) => new URL(w.url).origin === self.location.origin);
    if (any && 'navigate' in any) {
      try { await any.focus(); return await any.navigate(target); } catch (e) { /* 아래에서 새 창 */ }
    }
    return self.clients.openWindow(target);
  })());
});

// 브라우저가 구독을 바꾸면(주로 파이어폭스) 새 구독을 서버에 다시 알린다. 로그인 쿠키가 없으면 조용히 끝난다.
self.addEventListener('pushsubscriptionchange', (event) => {
  event.waitUntil((async () => {
    const st = await fetch('/api/push', { credentials: 'same-origin' }).then((r) => r.json());
    if (!st.configured || !st.key || !st.logged_in) return;
    const pad = '='.repeat((4 - (st.key.length % 4)) % 4);
    const raw = atob((st.key + pad).replace(/-/g, '+').replace(/_/g, '/'));
    const key = Uint8Array.from(raw, (c) => c.charCodeAt(0));
    const sub = event.newSubscription
      || await self.registration.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: key });
    const j = sub.toJSON();
    await fetch('/api/push/subscribe', {
      method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ endpoint: j.endpoint, keys: j.keys }),
    });
  })().catch(() => {}));
});
