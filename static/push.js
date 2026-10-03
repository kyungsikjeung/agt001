// 휴대폰 알림(웹 푸시) 켜기 카드 (OWNER_NOTIFY_PLAN N7). 사장님 화면이 쓴다: AgtPush.mount(요소, {loginHref}).
// 서버: /api/push (app/api/push.py). 서비스워커: /sw.js 의 push·notificationclick.
// 아이폰은 iOS 16.4 이상 + 홈 화면에 추가한 앱에서만 켤 수 있어서, 그 전에는 설치 안내를 보인다.
(function () {
  'use strict';

  const CSS = `
  .agt-push { --ap-accent: var(--accent-dark, #3fbf95); --ap-on: var(--on-accent, #0b1511); --ap-muted: var(--muted, var(--text-muted, #a3a8ad));
    --ap-line: var(--border, #34373b); --ap-ok: var(--accent, #5fd3ab); --ap-ok-bg: var(--accent-soft, rgba(63,191,149,.12));
    --ap-warn: var(--warn, #f5c26b); --ap-warn-bg: var(--warn-soft, rgba(201,163,90,.14)); }
  .agt-push__head { display: flex; align-items: center; gap: 8px; }
  .agt-push__head h2 { flex: 1; }
  .agt-push__badge { font-size: .75rem; font-weight: 700; border-radius: 999px; padding: 2px 10px; border: 1px solid var(--ap-line); color: var(--ap-muted); }
  .agt-push__badge[data-on="true"] { color: var(--ap-ok); border-color: var(--ap-ok); background: var(--ap-ok-bg); }
  .agt-push__steps { margin: 0; padding-left: 1.25rem; display: flex; flex-direction: column; gap: 6px; font-size: .9375rem; }
  .agt-push__steps kbd { font: inherit; font-weight: 700; border: 1px solid var(--ap-line); border-radius: 6px; padding: 0 6px; }
  .agt-push__warn { margin: 0; padding: 8px 12px; border-radius: 8px; background: var(--ap-warn-bg); color: var(--ap-warn); font-size: .875rem; }
  .agt-push__ok { margin: 0; padding: 8px 12px; border-radius: 8px; background: var(--ap-ok-bg); color: var(--ap-ok); font-size: .875rem; font-weight: 600; }
  .agt-push__devs { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 6px; }
  .agt-push__devs li { display: flex; align-items: center; gap: 8px; font-size: .875rem; border-top: 1px solid var(--ap-line); padding-top: 6px; }
  .agt-push__devs li span { flex: 1; min-width: 0; }
  .agt-push__devs small { display: block; color: var(--ap-muted); font-size: .75rem; }
  .agt-push__devs button { min-height: 36px; font-size: .8125rem; padding: 0 10px; }
  .agt-push__msg { margin: 0; font-size: .875rem; color: var(--ap-muted); min-height: 1.25em; }
  .agt-push__msg[data-bad="true"] { color: var(--bad, #ff8a80); }
  .agt-push.agt-push--flash { animation: agt-push-flash 1.6s ease-out 1; }
  @keyframes agt-push-flash { 0%, 40% { box-shadow: 0 0 0 3px var(--ap-ok); } 100% { box-shadow: 0 0 0 0 transparent; } }
  @media (prefers-reduced-motion: reduce) { .agt-push.agt-push--flash { animation: none; outline: 2px solid var(--ap-ok); } }
  `;

  function b64ToBytes(s) {
    const pad = '='.repeat((4 - (s.length % 4)) % 4);
    const raw = atob((s + pad).replace(/-/g, '+').replace(/_/g, '/'));
    return Uint8Array.from(raw, (c) => c.charCodeAt(0));
  }
  function bytesToB64(buf) {
    let s = '';
    for (const b of new Uint8Array(buf)) s += String.fromCharCode(b);
    return btoa(s).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
  }

  function env() {
    const ua = navigator.userAgent || '';
    const ios = /iPhone|iPad|iPod/.test(ua) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
    const standalone = (window.matchMedia && window.matchMedia('(display-mode: standalone)').matches) || navigator.standalone === true;
    return { ios, standalone };
  }

  // ok · insecure · ios-install · unsupported · denied
  function support() {
    if (!window.isSecureContext) return 'insecure';
    const has = 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window;
    const { ios, standalone } = env();
    if (!has) return ios && !standalone ? 'ios-install' : 'unsupported';
    if (Notification.permission === 'denied') return 'denied';
    return 'ok';
  }

  function deviceLabel() {
    const ua = navigator.userAgent || '';
    const { ios } = env();
    const os = ios ? (/iPad/.test(ua) || navigator.maxTouchPoints > 1 && !/iPhone/.test(ua) ? '아이패드' : '아이폰')
      : /Android/.test(ua) ? '안드로이드' : /Windows/.test(ua) ? '윈도우' : /Mac OS X/.test(ua) ? '맥' : '기기';
    const br = /SamsungBrowser/.test(ua) ? '삼성 인터넷' : /Edg\//.test(ua) ? '엣지' : /Firefox|FxiOS/.test(ua) ? '파이어폭스'
      : /CriOS|Chrome/.test(ua) ? '크롬' : /Safari/.test(ua) ? '사파리' : '';
    return br ? `${os} ${br}` : os;
  }

  async function registration() {
    const reg = (await navigator.serviceWorker.getRegistration('/')) || (await navigator.serviceWorker.register('/sw.js'));
    await navigator.serviceWorker.ready;
    return reg;
  }

  async function currentSub() {
    if (support() !== 'ok') return null;
    const reg = await navigator.serviceWorker.getRegistration('/');
    return reg ? reg.pushManager.getSubscription() : null;
  }

  async function call(path, body) {
    const r = await fetch(path, {
      method: body === undefined ? 'GET' : 'POST', credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' }, body: body === undefined ? undefined : JSON.stringify(body),
    });
    let data = {};
    try { data = await r.json(); } catch (e) { /* 빈 응답 */ }
    if (!r.ok) {
      const err = new Error((data && data.detail) || '잠시 뒤에 다시 해 주세요.');
      err.status = r.status;
      throw err;
    }
    return data;
  }

  async function state() {
    const sub = await currentSub().catch(() => null);
    const st = await call('/api/push/state', { endpoint: sub ? sub.endpoint : null });
    st.support = support();
    st.local = !!sub;
    st.here = !!sub && st.devices.some((d) => d.this);
    return st;
  }

  // 반드시 누른 순간에 부른다(사파리는 사용자 동작 안에서만 권한 창을 띄운다): await 전에 권한부터 묻는다.
  async function enable(key) {
    const perm = await Notification.requestPermission();
    if (perm !== 'granted') {
      const err = new Error(perm === 'denied' ? 'denied' : '알림 허용을 눌러야 켜져요.');
      err.code = perm;
      throw err;
    }
    const reg = await registration();
    let sub = await reg.pushManager.getSubscription();
    const had = sub && sub.options && sub.options.applicationServerKey;
    if (sub && had && bytesToB64(had) !== key) { await sub.unsubscribe(); sub = null; }  // 서버 키가 바뀌었으면 새로
    if (!sub) sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: b64ToBytes(key) });
    const j = sub.toJSON();
    return call('/api/push/subscribe', { endpoint: j.endpoint, keys: j.keys, label: deviceLabel() });
  }

  async function disable() {
    const sub = await currentSub();
    if (!sub) return;
    const endpoint = sub.endpoint;
    try { await sub.unsubscribe(); } catch (e) { /* 서버에서는 지운다 */ }
    await call('/api/push/unsubscribe', { endpoint });
  }

  function when(iso) {
    if (!iso) return '아직 받은 적 없어요';
    const d = new Date(iso);
    return '마지막으로 받음 ' + d.toLocaleString('ko-KR', { month: 'numeric', day: 'numeric', hour: 'numeric', minute: '2-digit' });
  }

  function h(tag, attrs, ...kids) {
    const e = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (k === 'class') e.className = v;
      else if (k.startsWith('on')) e.addEventListener(k.slice(2), v);
      else if (v != null && v !== false) e.setAttribute(k, v === true ? '' : v);
    }
    for (const c of kids.flat()) if (c != null && c !== false) e.append(c);
    return e;
  }

  function mount(root, opts) {
    opts = opts || {};
    if (!document.getElementById('agt-push-css')) document.head.append(h('style', { id: 'agt-push-css' }, CSS));
    root.classList.add('agt-push');
    let st = null;
    let busy = false;

    const say = (text, bad) => {
      const m = root.querySelector('.agt-push__msg');
      if (m) { m.textContent = text || ''; m.dataset.bad = String(!!bad); }
    };

    async function act(fn, okText) {
      if (busy) return;
      busy = true;
      root.querySelectorAll('button').forEach((b) => { b.disabled = true; });
      try {
        const note = await fn();
        await refresh();
        say(typeof note === 'string' ? note : okText);
      } catch (e) {
        await refresh().catch(() => {});
        if (e.code === 'denied' || e.message === 'denied') say('알림이 막혔어요. 아래 안내대로 허용으로 바꿔 주세요.', true);
        else say(e.message || '잠시 뒤에 다시 해 주세요.', true);
      } finally {
        busy = false;
        root.querySelectorAll('button').forEach((b) => { b.disabled = false; });
      }
    }

    const sendTest = () => call('/api/push/test', {}).then((r) => {
      if (!r.sent) throw new Error('보내지 못했어요. 이 기기를 끄고 다시 켜 주세요.');
    });

    function body() {
      if (!st) return [h('p', { class: 'sub' }, '확인하는 중…')];
      if (!st.configured) return [h('p', { class: 'sub' }, '휴대폰 알림은 준비 중이에요. 준비되면 여기서 켤 수 있어요.')];
      if (!st.logged_in) {
        return [h('p', { class: 'sub' }, '로그인하면 이 휴대폰으로 알림을 받을 수 있어요.'),
          h('a', { class: 'agt-push__login', href: opts.loginHref || '/owner' }, '로그인하고 켜기')];
      }
      const out = [];
      const s = st.support;
      if (s === 'insecure') out.push(h('p', { class: 'agt-push__warn' }, 'https 주소에서만 켤 수 있어요.'));
      else if (s === 'ios-install') {
        out.push(h('p', { class: 'sub' }, '아이폰은 이 화면을 홈 화면에 추가해야 알림이 와요(iOS 16.4 이상).'),
          h('ol', { class: 'agt-push__steps' },
            h('li', null, '사파리 아래쪽 ', h('kbd', null, '공유 ⬆︎'), ' 버튼을 눌러요.'),
            h('li', null, h('kbd', null, '홈 화면에 추가'), '를 눌러요.'),
            h('li', null, '홈 화면에 생긴 ', h('b', null, '사장님'), ' 아이콘으로 열고, 여기서 다시 켜요.')));
      } else if (s === 'unsupported') {
        out.push(h('p', { class: 'agt-push__warn' }, '이 브라우저는 알림을 못 받아요. 안드로이드는 크롬, 아이폰은 사파리(홈 화면 추가)로 열어 주세요.'));
      } else if (s === 'denied') {
        out.push(h('p', { class: 'agt-push__warn' },
          env().ios ? '알림이 꺼져 있어요. 아이폰 설정 > 알림 > 사장님 에서 알림 허용을 켜 주세요.'
            : '알림이 막혀 있어요. 주소창 왼쪽 자물쇠(또는 ⋮ > 설정) > 사이트 설정 > 알림을 허용으로 바꿔 주세요.'),
        h('div', { class: 'row' }, h('button', { type: 'button', onclick: () => refresh() }, '바꿨어요, 다시 확인')));
      } else if (st.here) {
        out.push(h('p', { class: 'agt-push__ok' }, '✓ 이 기기로 알림이 와요.'),
          h('div', { class: 'row' },
            h('button', { type: 'button', class: 'primary', onclick: () => act(sendTest, '시험 알림을 보냈어요. 휴대폰을 확인해 보세요.') }, '시험 알림 보내기'),
            h('button', { type: 'button', onclick: () => act(disable, '이 기기 알림을 껐어요.') }, '이 기기 끄기')));
      } else {
        out.push(h('div', { class: 'row' },
          h('button', { type: 'button', class: 'primary', onclick: () => act(async () => {
            await enable(st.key);
            try { await sendTest(); } catch (e) {
              const now = await state();
              if (!now.here) throw new Error('알림 서버가 이 기기를 받아 주지 않았어요. 한 번 더 눌러 주세요.');
              return '켜졌어요. 시험 알림은 아직 못 보냈어요 — 잠시 뒤 "시험 알림 보내기"를 눌러 보세요.';
            }
          }, '켜졌어요! 시험 알림을 보냈어요. 휴대폰을 확인해 보세요.') }, '이 휴대폰으로 알림 받기')));
        if (window.__agtInstall && !env().standalone) {
          out.push(h('button', { type: 'button', onclick: () => { window.__agtInstall.prompt(); } }, '홈 화면에 추가(앱처럼 열기)'));
        }
      }
      const others = st.devices.filter((d) => !d.this);
      if (st.devices.length) {
        out.push(h('ul', { class: 'agt-push__devs', 'aria-label': '알림 켜진 기기' },
          st.devices.map((d) => h('li', null,
            h('span', null, d.label + (d.this ? ' (이 기기)' : ''), h('small', null, (d.failing ? '⚠ 최근 보내기 실패 · ' : '') + when(d.last_ok_at))),
            d.this ? null : h('button', { type: 'button', 'aria-label': d.label + ' 알림 끄기',
              onclick: () => act(() => call('/api/push/unsubscribe', { id: d.id }), d.label + ' 알림을 껐어요.') }, '끄기')))));
      }
      if (!st.here && others.length && s === 'ok') out.push(h('p', { class: 'sub' }, `다른 기기 ${others.length}대에서 켜져 있어요.`));
      return out;
    }

    function render() {
      const on = !!(st && st.devices && st.devices.length);
      const msg = root.querySelector('.agt-push__msg');
      root.replaceChildren(
        h('div', { class: 'agt-push__head' }, h('h2', null, '📱 휴대폰 알림'),
          h('span', { class: 'agt-push__badge', 'data-on': String(on) }, on ? `켜짐 · ${st.devices.length}대` : '꺼짐')),
        h('p', { class: 'sub' }, '새 문의·예약·주문·채팅이 오면 휴대폰이 울려요. 무료예요.'),
        ...body(),
        msg || h('p', { class: 'agt-push__msg', role: 'status', 'aria-live': 'polite' }));
      if (opts.onState) opts.onState(st);
    }

    async function refresh() {
      try {
        st = await state();
      } catch (e) {
        st = st || { configured: false, logged_in: false, devices: [] };
        say(e.message, true);
      }
      render();
      return st;
    }

    render();
    window.addEventListener('agt-install-ready', render);
    return { refresh, flash: () => { root.classList.remove('agt-push--flash'); void root.offsetWidth; root.classList.add('agt-push--flash'); } };
  }

  window.AgtPush = { mount, support, deviceLabel, state, enable, disable };
})();
