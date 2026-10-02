/* static/callbot.js — "전화로 답하기" (VOICE_QA_REQUIREMENTS §8, 브라우저 통화 PoC)
 *
 * room.html이 조회할 때마다 보내는 'agt:room' 이벤트(참여자·나·상태)로 버튼을 보이고 숨긴다.
 * 1:1 방장 + 요구사항 대화 중: 누를 수 있음 / 여러 명: 흐리게 + 이유 한 줄 / 그 밖: 숨김.
 * 통화는 Twilio Voice SDK로 브라우저에서 건다(휴대폰 번호·통화료 없음). 서버: app/api/callbot.py
 */
(function () {
  'use strict';

  var SDK_URL = 'https://cdn.jsdelivr.net/npm/@twilio/voice-sdk@2.18.5/dist/twilio.min.js';
  var CALL_STATES = ['GREETING', 'GATHERING'];
  var MSG = {
    label: '📞 전화로 답하기',
    hint: 'AI가 전화로 질문하고, 답하신 내용은 이 채팅에 그대로 남아요',
    group: '전화 답하기는 혼자 쓰는 방에서만 돼요. 여러 분이 함께인 방에서는 채팅으로 답해 주세요',
    onCall: '📞 전화로 대화 중이에요. 채팅으로 입력하면 전화가 끝나요',
    connecting: '전화 연결 중…',
    failed: '전화를 걸지 못했어요. 잠시 뒤 다시 눌러 주세요',
    micDenied: '마이크 권한이 필요해요. 브라우저 설정에서 마이크를 허용해 주세요'
  };

  var room = null;
  var device = null;
  var call = null;
  var wrap, btn, hint, banner;

  function el(tag, attrs, text) {
    var e = document.createElement(tag);
    for (var k in attrs) e.setAttribute(k, attrs[k]);
    if (text) e.textContent = text;
    return e;
  }

  function build() {
    if (wrap) return true;
    var slot = document.getElementById('walkieSlot');
    var input = document.getElementById('input');
    if (!slot || !input) return false;
    wrap = el('div', { id: 'callbotRow', hidden: '' });
    btn = el('button', { type: 'button', id: 'callbotBtn' }, MSG.label);
    btn.style.cssText = 'min-height:44px;width:100%;padding:0 14px;border:1px solid var(--border, #e5e7eb);border-radius:999px;background:var(--bg, #f7f7f8);cursor:pointer;font-size:0.8125rem;font-weight:600;';
    hint = el('p', { id: 'callbotHint' }, MSG.hint);
    hint.style.cssText = 'margin:4px 0 0;font-size:0.8125rem;color:var(--text-muted, #52525b);';
    btn.setAttribute('aria-describedby', 'callbotHint');
    wrap.appendChild(btn);
    wrap.appendChild(hint);
    slot.appendChild(wrap);
    btn.addEventListener('click', onClick);

    banner = el('div', { id: 'callbotBanner', role: 'status', hidden: '' });
    banner.style.cssText = 'display:flex;gap:8px;align-items:center;justify-content:space-between;padding:8px 12px;background:var(--ok-bg, #ecfdf5);color:var(--ok-ink, #065f46);font-size:0.875rem;';
    var bannerText = el('span', {}, MSG.onCall);
    var hang = el('button', { type: 'button' }, '끊기');
    hang.style.cssText = 'min-height:44px;min-width:64px;border-radius:8px;border:0;background:#b91c1c;color:#fff;font:inherit;';
    hang.addEventListener('click', hangup);
    banner.appendChild(bannerText);
    banner.appendChild(hang);
    var row = input.parentNode;
    row.parentNode.insertBefore(banner, row);

    // 채팅으로 입력하면 전화를 끝낸다 (두 입력이 부딪히지 않게, §8.2)
    input.addEventListener('keydown', function (e) { if (e.key === 'Enter' && call) hangup(); });
    var send = document.getElementById('sendBtn');
    if (send) send.addEventListener('click', function () { if (call) hangup(); });
    return true;
  }

  function mode() {
    if (!room || !room.me || !room.me.is_owner) return 'hidden';
    if (CALL_STATES.indexOf(room.state) < 0) return 'hidden';
    return (room.members || []).length === 1 ? 'ready' : 'group';
  }

  function render() {
    if (!build()) return;
    var m = call ? 'ready' : mode();
    wrap.hidden = m === 'hidden';
    banner.hidden = !call;
    banner.style.display = call ? 'flex' : 'none';
    btn.setAttribute('aria-disabled', m === 'group' ? 'true' : 'false');
    btn.style.opacity = m === 'group' ? '0.5' : '1';
    btn.textContent = call ? '통화 중 · 끊기' : MSG.label;
    if (m !== 'group' && hint.textContent === MSG.group) hint.textContent = MSG.hint;
  }

  function loadSdk() {
    if (window.Twilio && window.Twilio.Device) return Promise.resolve();
    return new Promise(function (ok, fail) {
      var s = el('script', { src: SDK_URL });
      s.onload = ok;
      s.onerror = fail;
      document.head.appendChild(s);
    });
  }

  function onClick() {
    if (call) return hangup();
    if (mode() === 'group') { hint.textContent = MSG.group; return; }
    if (mode() !== 'ready') return;
    start();
  }

  function start() {
    btn.textContent = MSG.connecting;
    btn.setAttribute('aria-disabled', 'true');
    var memberId = '';
    try { memberId = localStorage.getItem('agt001_member_id') || ''; } catch (e) { /* 저장소 사용 불가 */ }
    loadSdk().then(function () {
      return fetch('/api/callbot/token/' + encodeURIComponent(room.roomId), {
        method: 'POST', headers: { 'X-Member-Id': memberId }
      });
    }).then(function (res) {
      if (res.status === 403) { hint.textContent = MSG.group; throw new Error('refused'); }
      if (!res.ok) throw new Error('token ' + res.status);
      return res.json();
    }).then(function (data) {
      if (device) device.destroy();
      device = new window.Twilio.Device(data.token, { codecPreferences: ['opus', 'pcmu'] });
      return device.connect();
    }).then(function (c) {
      call = c;
      window.__agtOnCall = true;
      try { if (window.stopAllSpeech) window.stopAllSpeech(); } catch (e) { /* 무시 */ }
      try { if (window.cancelHandsfreeListen) window.cancelHandsfreeListen(); } catch (e) { /* 무시 */ }
      c.on('disconnect', ended);
      c.on('cancel', ended);
      c.on('error', ended);
      render();
    }).catch(function (e) {
      if (e && e.message !== 'refused') {
        hint.textContent = (e && /permission|NotAllowed/i.test(String(e.name || e.message))) ? MSG.micDenied : MSG.failed;
      }
      ended();
    });
  }

  function hangup() {
    try { if (call) call.disconnect(); } catch (e) { /* 무시 */ }
    ended();
  }

  function ended() {
    call = null;
    window.__agtOnCall = false;
    render();
  }

  window.addEventListener('agt:room', function (e) {
    room = e.detail || null;
    render();
  });
})();
