/* static/live.js — 실시간 대화로 만들기 (COMPOSE_INTERVIEW_CONTRACT §5)
 *
 * 🎤 음성: 한 번 말하면 글자로 바꿔 입력칸에 넣는다(자동 전송 없음, 채팅방 마이크와 같은 원칙).
 * 🔴 실시간 대화: 질문을 소리로 읽고 → 바로 듣고 → 말이 끝나면(무음) 알아서 보내고 → 다음 질문을 읽는다.
 * 미리보기: 정한 부품만 그린 화면을 모바일·PC·둘 다로 보여 준다. 방금 정한 부품은 잠깐 강조한다.
 * 서버: POST /api/rooms/{id}/live/turn, GET /api/rooms/{id}/live/preview, POST /api/stt, POST /api/tts
 */
(function () {
  'use strict';

  var SILENCE_RMS = 0.02;      // 이보다 작으면 조용한 것으로 본다
  var END_SILENCE_MS = 1200;   // 말한 뒤 이만큼 조용하면 끝 (VOICE_QA FR-4)
  var NO_VOICE_MS = 8000;      // 처음부터 말이 없으면 그만 듣는다
  var MAX_RECORD_MS = 60000;   // 기존 상한
  var TTS_CHUNK = 280;         // 서버 합성 상한 300자
  var MOBILE = { w: 390, h: 844 };
  var PC = { w: 1280, h: 800 };
  var MIME_CANDIDATES = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/ogg;codecs=opus'];

  var $ = function (id) { return document.getElementById(id); };
  var log = $('log'), input = $('input'), statusEl = $('status'), statusText = $('statusText');
  var micBtn = $('micBtn'), liveBtn = $('liveBtn'), frames = $('frames'), partsEl = $('parts');

  function safeGet(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }
  function safeSet(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* 저장 못 해도 동작 */ } }
  function makeId() {
    if (window.crypto && typeof crypto.randomUUID === 'function') return crypto.randomUUID();
    return 'm-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 10);
  }

  var params = new URLSearchParams(location.search);
  var roomId = params.get('room');
  var memberId = safeGet('agt001_member_id') || makeId();
  safeSet('agt001_member_id', memberId);
  var nickname = safeGet('agt001_nickname') || '사장님';
  var view = safeGet('agt001_live_view') || (window.innerWidth < 820 ? 'mobile' : 'both');

  var busy = false, liveOn = false, finished = false;
  var lastHtml = null, lastPart = null, current = null;

  // ── 상태 줄 ──
  function setStatus(kind, text) {
    statusEl.className = kind || '';
    statusText.textContent = text;
  }

  // ── 서버 ──
  function api(path, opts) {
    opts = opts || {};
    opts.headers = Object.assign({ 'X-Member-Id': memberId }, opts.headers || {});
    return fetch(path, opts);
  }

  function ensureRoom() {
    if (roomId) return join();
    return fetch('/room', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        roomId = d.room_id;
        params.set('room', roomId);
        history.replaceState(null, '', location.pathname + '?' + params.toString());
        try {
          var list = JSON.parse(safeGet('agt001_rooms') || '[]').filter(function (x) { return x !== roomId; });
          list.unshift(roomId);
          safeSet('agt001_rooms', JSON.stringify(list.slice(0, 50)));
        } catch (e) { /* 목록 저장 실패는 무시 */ }
        return join();
      });
  }

  function join() {
    $('roomLink').href = '/room.html?room=' + encodeURIComponent(roomId);
    return fetch('/room/' + encodeURIComponent(roomId) + '/chat', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ member_id: memberId, nickname: nickname, message: '' })
    });
  }

  function turn(text) {
    return api('/api/rooms/' + encodeURIComponent(roomId) + '/live/turn', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text: text })
    }).then(function (r) {
      if (r.status === 403) throw new Error('owner');
      if (r.status === 409) throw new Error('finished');
      if (!r.ok) throw new Error('turn');
      return r.json();
    });
  }

  function loadPreview() {
    return api('/api/rooms/' + encodeURIComponent(roomId) + '/live/preview')
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (p) { if (p) drawPreview(p); });
  }

  // ── 대화 ──
  function bubble(kind, text, ack, options) {
    var el = document.createElement('div');
    el.className = 'msg ' + kind;
    if (ack) {
      var a = document.createElement('div');
      a.className = 'ack';
      a.textContent = ack;
      el.appendChild(a);
    }
    if (text) el.appendChild(document.createTextNode(text));
    if (options && options.length) {
      var row = document.createElement('div');
      row.className = 'chips';
      options.forEach(function (o) {
        var b = document.createElement('button');
        b.type = 'button';
        b.textContent = o;
        b.addEventListener('click', function () { send(o); });
        row.appendChild(b);
      });
      el.appendChild(row);
    }
    log.appendChild(el);
    log.scrollTop = log.scrollHeight;
    return el;
  }

  function disableOldChips() {
    Array.prototype.forEach.call(log.querySelectorAll('.chips button'), function (b) { b.disabled = true; });
  }

  function showTurn(v) {
    current = v;
    var q = v.question_text || '';
    if (q || v.reply) bubble('ai', q, v.reply, v.done ? [] : v.options);
    if (v.done) {
      finished = true;
      var link = document.createElement('a');
      link.href = '/room.html?room=' + encodeURIComponent(roomId);
      link.textContent = '채팅방에서 요약 보고 시안 받기 →';
      link.style.cssText = 'align-self:flex-start;font-weight:700;color:var(--accent-dark)';
      log.appendChild(link);
      stopLive();
    }
  }

  function send(text) {
    text = (text || '').trim();
    if (!text || busy || finished) return Promise.resolve();
    busy = true;
    disableOldChips();
    bubble('me', text);
    input.value = '';
    setStatus('busy', '화면 만드는 중…');
    return turn(text)
      .then(function (v) {
        showTurn(v);
        return loadPreview().then(function () { return v; });
      })
      .then(function (v) {
        busy = false;
        setStatus('', '준비됐어요');
        if (liveOn && !finished) speakThenListen(v.speech);
      })
      .catch(function (e) {
        busy = false;
        if (e.message === 'finished') {
          finished = true;
          bubble('ai', '질문은 다 끝났어요. 채팅방에서 이어서 진행해 주세요.');
        } else if (e.message === 'owner') {
          bubble('ai', '실시간 대화는 방장만 쓸 수 있어요.');
        } else {
          bubble('ai', '전송에 실패했어요. 인터넷 연결을 확인하고 다시 시도해 주세요.');
        }
        setStatus('', '준비됐어요');
        stopLive();
      });
  }

  $('composer').addEventListener('submit', function (e) {
    e.preventDefault();
    send(input.value);
  });

  // ── 미리보기 ──
  var HIGHLIGHT_CSS =
    'section[class^="s-"]{animation:none!important;opacity:1!important;transform:none!important}' +
    '@keyframes live-glow{0%{box-shadow:inset 0 0 0 4px #6366f1}100%{box-shadow:inset 0 0 0 4px rgba(99,102,241,0)}}';

  function decorate(html, part) {
    var css = HIGHLIGHT_CSS;
    var js = '';
    if (part) {
      var sel = '[data-section-id="' + String(part).replace(/[^\w-]/g, '') + '"]';
      css += sel + '{animation:live-glow 2.4s ease-out 1!important;scroll-margin-top:60px}';
      // scrollIntoView는 바깥 페이지까지 움직이므로 미리보기 안에서만 스크롤한다.
      js = '<script>addEventListener("load",function(){var e=document.querySelector(\'' + sel +
        '\');if(e)window.scrollTo(0,Math.max(0,e.getBoundingClientRect().top+window.scrollY-60))});<\/script>';
    }
    var tag = '<style>' + css + '</style>' + js;
    return html.indexOf('</body>') >= 0 ? html.replace('</body>', tag + '</body>') : html + tag;
  }

  function drawPreview(p) {
    lastHtml = p.html;
    lastPart = p.last;
    partsEl.textContent = '';
    (p.components || []).forEach(function (c) {
      var s = document.createElement('span');
      s.textContent = c.label;
      if (c.id === p.last) s.className = 'new';
      partsEl.appendChild(s);
    });
    render();
  }

  function deviceFrame(kind, size, html) {
    var wrap = document.createElement('div');
    wrap.className = 'device ' + kind;
    var label = document.createElement('div');
    label.className = 'label';
    label.textContent = kind === 'mobile' ? '모바일 ' + size.w + 'px' : 'PC ' + size.w + 'px';
    var clip = document.createElement('div');
    clip.className = 'clip';
    var f = document.createElement('iframe');
    f.setAttribute('sandbox', 'allow-scripts');
    f.setAttribute('title', kind === 'mobile' ? '모바일 미리보기' : 'PC 미리보기');
    f.width = size.w;
    f.height = size.h;
    f.srcdoc = html;
    clip.appendChild(f);
    wrap.appendChild(label);
    wrap.appendChild(clip);
    return { el: wrap, clip: clip, frame: f, size: size };
  }

  function render() {
    Array.prototype.forEach.call(document.querySelectorAll('.seg button'), function (b) {
      b.setAttribute('aria-pressed', String(b.dataset.view === view));
    });
    frames.textContent = '';
    if (!lastHtml) {
      var e = document.createElement('div');
      e.className = 'empty';
      e.innerHTML = '<b>말씀하시면 여기에 화면이 하나씩 생겨요</b>첫 화면, 메뉴, 사진, 지도처럼 정할 때마다 바로 보여 드릴게요.';
      frames.appendChild(e);
      return;
    }
    var html = decorate(lastHtml, lastPart);
    var list = [];
    if (view === 'mobile' || view === 'both') list.push(deviceFrame('mobile', MOBILE, html));
    if (view === 'pc' || view === 'both') list.push(deviceFrame('pc', PC, html));
    list.forEach(function (d) { frames.appendChild(d.el); });
    fit(list);
  }

  // 모바일 틀은 높이에 맞추고, PC 틀은 남은 너비에 맞춘다. 좁은 화면에서는 위아래로 쌓는다.
  function fit(list) {
    var stage = frames.parentNode;
    var W = stage.clientWidth - 32, H = frames.clientHeight - 40;
    var narrow = window.innerWidth < 820;
    var m = list.filter(function (d) { return d.size === MOBILE; })[0];
    var p = list.filter(function (d) { return d.size === PC; })[0];
    function apply(d, scale) {
      scale = Math.max(0.15, Math.min(1, scale));
      d.frame.style.transform = 'scale(' + scale + ')';
      d.clip.style.width = Math.round(d.size.w * scale) + 'px';
      d.clip.style.height = Math.round(d.size.h * scale) + 'px';
      return scale;
    }
    var sm = 0;
    // 둘 다: 나란히 둔다. 좁은 화면에서는 모바일 틀이 너비의 40%까지만 쓴다.
    var mobileShare = m && p ? (narrow ? 0.4 : 0.45) : 1;
    if (m) sm = apply(m, Math.min(W * mobileShare / (m.size.w + 16), H > 150 ? H / (m.size.h + 16) : 1));
    if (p) apply(p, (m ? W - m.size.w * sm - (narrow ? 20 : 36) : W) / (p.size.w + 2));
  }

  var resizeTimer = 0;
  window.addEventListener('resize', function () {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(render, 150);
  });
  Array.prototype.forEach.call(document.querySelectorAll('.seg button'), function (b) {
    b.addEventListener('click', function () {
      view = b.dataset.view;
      safeSet('agt001_live_view', view);
      render();
    });
  });

  // ── 소리로 읽기 ──
  var audio = null, speakToken = 0;

  function chunks(text) {
    var out = [], buf = '';
    (String(text || '').match(/[^.?!]+[.?!]*\s*/g) || []).forEach(function (s) {
      if ((buf + ' ' + s).trim().length > TTS_CHUNK && buf) { out.push(buf.trim()); buf = ''; }
      buf += ' ' + s;
    });
    if (buf.trim()) out.push(buf.trim().slice(0, TTS_CHUNK));
    return out;
  }

  function stopSpeech() {
    speakToken++;
    if (audio) { try { audio.pause(); } catch (e) { /* 무시 */ } audio = null; }
    try { if (window.speechSynthesis) speechSynthesis.cancel(); } catch (e) { /* 무시 */ }
  }

  function browserSpeak(text, token) {
    return new Promise(function (resolve) {
      if (!window.speechSynthesis || token !== speakToken) return resolve();
      var u = new SpeechSynthesisUtterance(text);
      u.lang = 'ko-KR';
      // 목소리가 없는 브라우저는 끝 신호를 안 줄 수 있어 글 길이만큼만 기다린다.
      var guard = setTimeout(resolve, 1500 + text.length * 150);
      u.onend = u.onerror = function () { clearTimeout(guard); resolve(); };
      speechSynthesis.speak(u);
    });
  }

  function speakOne(text, token) {
    return api('/api/tts', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text: text })
    }).then(function (r) {
      if (!r.ok) throw new Error('tts');
      return r.blob();
    }).then(function (blob) {
      if (token !== speakToken) return;
      return new Promise(function (resolve) {
        var url = URL.createObjectURL(blob);
        audio = new Audio(url);
        audio.onended = audio.onerror = function () { URL.revokeObjectURL(url); resolve(); };
        audio.play().catch(function () {
          // 자동 재생이 막히면(iOS 등) 브라우저 목소리로 대신 읽는다.
          URL.revokeObjectURL(url);
          browserSpeak(text, token).then(resolve);
        });
      });
    }).catch(function () {
      // 서버 합성을 못 쓰면 브라우저 목소리로 읽는다.
      return browserSpeak(text, token);
    });
  }

  function speak(text) {
    stopSpeech();
    var token = speakToken;
    var parts = chunks(text);
    if (!parts.length) return Promise.resolve();
    setStatus('speaking', '읽어 드리는 중… (말씀하시려면 잠깐 기다려 주세요)');
    return parts.reduce(function (p, part) {
      return p.then(function () { if (token === speakToken) return speakOne(part, token); });
    }, Promise.resolve()).then(function () { return token === speakToken; });
  }

  // ── 듣기 (말 끝 자동 감지) ──
  var rec = null, stream = null, chunksBuf = [], vadTimer = 0, maxTimer = 0, actx = null;
  var sttError = '';  // 마지막 글자 바꾸기 실패 사유 (빈 글과 구별)
  var STT_MSG = {
    429: '요청이 너무 잦아요. 잠시 뒤에 다시 해 주세요.',
    503: '지금은 음성 인식을 쓸 수 없어요. 글자로 적어 주세요.',
    415: '이 브라우저의 녹음 형식을 쓸 수 없어요. 글자로 적어 주세요.'
  };

  function pickMime() {
    if (!window.MediaRecorder || !MediaRecorder.isTypeSupported) return '';
    for (var i = 0; i < MIME_CANDIDATES.length; i++) if (MediaRecorder.isTypeSupported(MIME_CANDIDATES[i])) return MIME_CANDIDATES[i];
    return '';
  }

  function cleanupRec() {
    clearInterval(vadTimer); clearTimeout(maxTimer);
    if (stream) stream.getTracks().forEach(function (t) { t.stop(); });
    if (actx) { try { actx.close(); } catch (e) { /* 무시 */ } }
    stream = null; actx = null; rec = null;
    $('status').querySelector('.meter i').style.width = '0';
    micBtn.setAttribute('aria-pressed', 'false');
  }

  // 말이 끝날 때까지 듣고 글자를 돌려준다. 말이 없으면 ''.
  function listenOnce() {
    if (!navigator.mediaDevices || !window.MediaRecorder) {
      setStatus('', '이 브라우저는 녹음이 안 돼요. 휴대폰 키보드의 마이크로 말해 주세요.');
      return Promise.resolve('');
    }
    return navigator.mediaDevices.getUserMedia({ audio: true }).then(function (s) {
      stream = s;
      return new Promise(function (resolve) {
        var mime = pickMime();
        try { rec = mime ? new MediaRecorder(s, { mimeType: mime }) : new MediaRecorder(s); }
        catch (e) { cleanupRec(); resolve(''); return; }
        chunksBuf = [];
        var heard = false, quietAt = Date.now(), startAt = Date.now(), discard = false;
        rec.ondataavailable = function (e) { if (e.data && e.data.size) chunksBuf.push(e.data); };
        rec.onstop = function () {
          var type = rec && rec.mimeType || mime || 'audio/webm';
          var blob = new Blob(chunksBuf, { type: type });
          cleanupRec();
          if (discard || !heard || !blob.size) return resolve('');
          setStatus('busy', '글자로 바꾸는 중…');
          var fd = new FormData();
          var ext = type.indexOf('mp4') >= 0 ? 'm4a' : type.indexOf('ogg') >= 0 ? 'ogg' : 'webm';
          fd.append('audio', blob, 'speech.' + ext);
          sttError = '';
          api('/api/stt', { method: 'POST', body: fd })
            .then(function (r) {
              if (!r.ok) sttError = STT_MSG[r.status] || '글자로 바꾸지 못했어요. 다시 말해 주세요.';
              return r.ok ? r.json() : { text: '' };
            })
            .then(function (d) { resolve((d && d.text) || ''); })
            .catch(function () { sttError = '전송에 실패했어요. 인터넷 연결을 확인해 주세요.'; resolve(''); });
        };
        // 소리 크기로 말 끝을 잡는다
        try {
          actx = new (window.AudioContext || window.webkitAudioContext)();
          var an = actx.createAnalyser();
          an.fftSize = 1024;
          actx.createMediaStreamSource(s).connect(an);
          var data = new Uint8Array(an.fftSize);
          var meter = $('status').querySelector('.meter i');
          vadTimer = setInterval(function () {
            an.getByteTimeDomainData(data);
            var sum = 0;
            for (var i = 0; i < data.length; i++) { var v = (data[i] - 128) / 128; sum += v * v; }
            var rms = Math.sqrt(sum / data.length);
            meter.style.width = Math.min(100, Math.round(rms * 600)) + '%';
            var now = Date.now();
            if (rms >= SILENCE_RMS) { heard = true; quietAt = now; return; }
            if (heard && now - quietAt >= END_SILENCE_MS) { if (rec && rec.state === 'recording') rec.stop(); }
            else if (!heard && now - startAt >= NO_VOICE_MS) { discard = true; if (rec && rec.state === 'recording') rec.stop(); }
          }, 80);
        } catch (e) { heard = true; /* 소리 분석이 안 되면 최대 시간까지 */ }
        maxTimer = setTimeout(function () { if (rec && rec.state === 'recording') rec.stop(); }, MAX_RECORD_MS);
        setStatus('listening', '듣고 있어요… 말씀이 끝나면 알아서 보내요');
        rec.start(250);
      });
    }).catch(function () {
      cleanupRec();
      setStatus('', '마이크 권한이 필요해요. 브라우저 설정에서 마이크를 허용해 주세요.');
      stopLive();
      return '';
    });
  }

  function stopListening() {
    if (rec && rec.state === 'recording') {
      try { rec.stop(); } catch (e) { cleanupRec(); }
    }
  }

  // 🎤 음성: 받아쓰기만 (자동 전송 없음)
  micBtn.addEventListener('click', function () {
    if (liveOn) return;
    if (rec) { stopListening(); return; }
    stopSpeech();
    micBtn.setAttribute('aria-pressed', 'true');
    listenOnce().then(function (text) {
      if (text) {
        input.value = (input.value ? input.value + ' ' : '') + text;
        input.focus();
        setStatus('', '번호와 금액이 맞는지 확인하고 보내 주세요');
      } else if (statusEl.className) {
        // 마이크 권한 안내처럼 이미 띄운 문구(상태 없음)는 그대로 둔다
        setStatus('', sttError || '글자를 찾지 못했어요. 다시 또렷하게 말해 주세요.');
      }
    });
  });

  // 🔴 실시간 대화: 읽기 → 듣기 → 보내기 반복
  function speakThenListen(text) {
    if (!liveOn) return;
    speak(text).then(function (ok) {
      if (!ok || !liveOn) return;
      return listenOnce().then(function (heard) {
        if (!liveOn) return;
        if (heard) return send(heard);
        setStatus('', sttError || '말씀이 없어서 잠깐 멈췄어요. 다시 누르면 이어서 들어요');
        stopLive();
      });
    });
  }

  function stopLive() {
    if (!liveOn) return;
    liveOn = false;
    liveBtn.setAttribute('aria-pressed', 'false');
    liveBtn.textContent = '🔴 실시간 대화';
    stopSpeech();
    stopListening();
  }

  liveBtn.addEventListener('click', function () {
    if (liveOn) { stopLive(); setStatus('', '실시간 대화를 멈췄어요'); return; }
    if (finished) return;
    liveOn = true;
    liveBtn.setAttribute('aria-pressed', 'true');
    liveBtn.textContent = '⏹ 대화 멈추기';
    speakThenListen(current ? current.speech : '');
  });

  // ── 시작 ──
  render();
  setStatus('busy', '준비하는 중…');
  ensureRoom()
    .then(function () { return turn(''); })
    .then(function (v) {
      showTurn(v);
      setStatus('', '🔴 실시간 대화를 누르면 질문을 읽어 드리고 바로 들어요');
      return loadPreview();
    })
    .catch(function (e) {
      if (e && e.message === 'owner') {
        bubble('ai', '실시간 대화는 방장만 쓸 수 있어요. 채팅방에서 이어서 대화해 주세요.');
      } else if (e && e.message === 'finished') {
        finished = true;
        bubble('ai', '질문은 다 끝났어요. 채팅방에서 요약을 보고 시안을 받아 보세요.');
        loadPreview();
      } else {
        bubble('ai', '시작하지 못했어요. 새로고침해 주세요.');
      }
      setStatus('', '');
    });
})();
