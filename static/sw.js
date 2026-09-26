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
