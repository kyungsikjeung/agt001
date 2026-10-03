/* static/live.js — 실시간 대화로 만들기 (COMPOSE_INTERVIEW_CONTRACT §5·§6)
 *
 * 🎤 음성: 한 번 말하면 글자로 바꿔 입력칸에 넣는다(자동 전송 없음, 채팅방 마이크와 같은 원칙).
 * 🔴 실시간 대화: 질문을 읽고 → 바로 듣고 → 말이 끝나면(무음) 알아서 보내고 → 다음 질문을 읽는다.
 * 선택지 시안: 부품 질문마다 선택지별 작은 실제 화면(지금 분위기로 그린 것)을 카드로 보여 준다.
 * 움직임 흐름(§6): 묻기(카드 차례로 등장) → 읽기(읽는 카드 강조) → 듣기(마이크 물결)
 *   → 알아듣기(맞는 카드 미리 표시) → 짓기(만드는 중 → 겹쳐 바꾸기 → 새 부품 올라오며 빛남) → 확정(칩 톡).
 * 서버: /api/rooms/{id}/live/turn·preview·options, /api/stt, /api/tts
 */
(function () {
  'use strict';

  var SILENCE_RMS = 0.02;      // 이보다 작으면 조용한 것으로 본다
  var END_SILENCE_MS = 1200;   // 말한 뒤 이만큼 조용하면 끝 (VOICE_QA FR-4)
  var NO_VOICE_MS = 8000;      // 처음부터 말이 없으면 그만 듣는다
  var MAX_RECORD_MS = 60000;   // 기존 상한
  var TTS_CHUNK = 280;         // 서버 합성 상한 300자 (1분 12번 한도라 묶어서 읽는다)
  var MOBILE = { w: 390, h: 844 };
  var PC = { w: 1280, h: 800 };
  var CARD = { w: 390, h: 560 };  // 선택지 시안 카드 속 화면 크기
  var MIME_CANDIDATES = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/ogg;codecs=opus'];
  var REDUCED = window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches;

  var $ = function (id) { return document.getElementById(id); };
  var log = $('log'), input = $('input'), statusEl = $('status'), statusText = $('statusText');
  var micBtn = $('micBtn'), liveBtn = $('liveBtn'), frames = $('frames'), partsEl = $('parts'), stage = $('stage');

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
  var lastHtml = null, lastPart = null, current = null, currentCards = [], knownParts = {};

  // ── 상태 줄 (흐름 단계마다 문구·점 색이 바뀐다) ──
  function setStatus(kind, text) {
    statusEl.className = kind || '';
    statusText.textContent = text;
    document.body.dataset.phase = kind || 'idle';
  }

  // ── 서버 ──
  function api(path, opts) {
    opts = opts || {};
    opts.headers = Object.assign({ 'X-Member-Id': memberId }, opts.headers || {});
    return fetch(path, opts);
  }
  function roomPath(tail) { return '/api/rooms/' + encodeURIComponent(roomId) + tail; }

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
    return api(roomPath('/live/turn'), {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text: text })
    }).then(function (r) {
      if (r.status === 403) throw new Error('owner');
      if (r.status === 409) throw new Error('finished');
      if (!r.ok) throw new Error('turn');
      return r.json();
    });
  }

  function loadPreview() {
    return api(roomPath('/live/preview'))
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (p) { if (p) return drawPreview(p); });
  }

  // ── 대화 말풍선 ──
  function bubble(kind, text, ack) {
    var el = document.createElement('div');
    el.className = 'msg ' + kind;
    if (ack) {
      var a = document.createElement('div');
      a.className = 'ack';
      a.textContent = ack;
      el.appendChild(a);
    }
    if (text) {
      var t = document.createElement('div');
      t.className = 'q';
      t.textContent = text;
      el.appendChild(t);
    }
    log.appendChild(el);
    log.scrollTop = log.scrollHeight;
    return el;
  }

  // 항목 판단 이유 (사진이 필요한지·어떤 모양인지·주문/예약 단추·후기 자리). 접어 두고 누르면 펼친다.
  function why(el, lines) {
    if (!lines || !lines.length) return;
    var box = document.createElement('details');
    box.className = 'why';
    var sum = document.createElement('summary');
    sum.textContent = '💡 이렇게 판단했어요';
    box.appendChild(sum);
    var ul = document.createElement('ul');
    lines.slice(0, 5).forEach(function (t) {
      var li = document.createElement('li');
      li.textContent = t;
      ul.appendChild(li);
    });
    box.appendChild(ul);
    el.appendChild(box);
  }

  function retireOldChoices() {
    Array.prototype.forEach.call(log.querySelectorAll('.choices'), function (row) {
      row.classList.add('is-old');
      Array.prototype.forEach.call(row.querySelectorAll('button'), function (b) { b.disabled = true; });
    });
    currentCards = [];
  }

  // 선택지: 부품 질문은 시안 카드, 그 밖은 작은 칩
  function choices(el, v) {
    var opts = v.options || [];
    if (!opts.length) return;
    var descs = v.option_desc || [];
    var row = document.createElement('div');
    row.className = 'choices ' + (v.has_previews ? 'cards' : 'chips');
    opts.forEach(function (label, i) {
      var b = document.createElement('button');
      b.type = 'button';
      b.className = v.has_previews ? 'opt' : 'chip';
      b.style.setProperty('--i', i);
      b.dataset.label = label;
      if (v.has_previews) {
        var shot = document.createElement('span');
        shot.className = 'shot is-loading';
        var name = document.createElement('strong');
        name.textContent = label;
        var desc = document.createElement('span');
        desc.className = 'desc';
        desc.textContent = descs[i] || '';
        b.appendChild(shot);
        b.appendChild(name);
        b.appendChild(desc);
      } else {
        b.textContent = label;
      }
      b.addEventListener('click', function () { pick(b); send(label); });
      row.appendChild(b);
      if (v.has_previews) currentCards.push(b);
    });
    el.appendChild(row);
    log.scrollTop = log.scrollHeight;
    if (v.has_previews) loadOptionShots();
  }

  function loadOptionShots() {
    var cards = currentCards.slice();
    api(roomPath('/live/options'))
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) {
        if (!d) return;
        (d.options || []).forEach(function (o) {
          var card = cards.filter(function (c) { return c.dataset.label === o.label; })[0];
          if (!card) return;
          var shot = card.querySelector('.shot');
          if (!o.html) { shot.className = 'shot is-none'; shot.textContent = '넣지 않음'; return; }
          var f = document.createElement('iframe');
          f.setAttribute('sandbox', 'allow-scripts');
          f.setAttribute('tabindex', '-1');
          f.setAttribute('aria-hidden', 'true');
          f.width = CARD.w;
          f.height = CARD.h;
          f.srcdoc = decorate(o.html, null, true);
          f.addEventListener('load', function () { shot.classList.remove('is-loading'); });
          shot.appendChild(f);
          fitShot(shot, f);
        });
        // 시안이 없는 선택지("알아서")는 추천 표시만
        cards.forEach(function (c) {
          var shot = c.querySelector('.shot');
          if (shot.classList.contains('is-loading') && !shot.firstChild) {
            shot.className = 'shot is-none';
            shot.textContent = '추천으로';
          }
        });
      })
      .catch(function () { /* 시안이 없어도 글 선택지로 고를 수 있다 */ });
  }

  function fitShot(shot, f) {
    var w = shot.clientWidth || 150;
    var s = w / CARD.w;
    f.style.transform = 'scale(' + s + ')';
    shot.style.height = Math.round(CARD.h * s * 0.62) + 'px';
  }

  function pick(card) {
    currentCards.forEach(function (c) { c.classList.toggle('is-picked', c === card); });
  }

  // 들은 말로 카드를 미리 짚는다 (서버 판단 전 손님에게 반응 보이기)
  function guessCard(text) {
    var n = (text || '').replace(/\s+/g, '');
    var hit = null;
    currentCards.forEach(function (c) {
      var label = c.dataset.label.replace(/\s+/g, '');
      var core = label.slice(0, 2);
      if (!hit && (n.indexOf(label) >= 0 || (core.length === 2 && n.indexOf(core) >= 0))) hit = c;
    });
    if (hit) pick(hit);
  }

  function showTurn(v) {
    current = v;
    retireOldChoices();
    var q = v.question_text || '';
    if (q || v.reply) {
      var el = bubble('ai', q, v.reply);
      if (!v.done) {
        why(el, v.why);
        choices(el, v);
      }
    }
    if (v.done) {
      finished = true;
      var link = document.createElement('a');
      link.className = 'next-link';
      link.href = '/room.html?room=' + encodeURIComponent(roomId);
      link.textContent = '채팅방에서 요약 보고 시안 받기 →';
      log.appendChild(link);
      stopLive();
    }
  }

  function send(text) {
    text = (text || '').trim();
    if (!text || busy || finished) return Promise.resolve();
    busy = true;
    stopSpeech();
    guessCard(text);
    bubble('me', text);
    input.value = '';
    setStatus('busy', '화면 만드는 중…');
    building(true);
    return turn(text)
      .then(function (v) {
        showTurn(v);
        return loadPreview().then(function () { return v; });
      })
      .then(function (v) {
        busy = false;
        building(false);
        setStatus('', '준비됐어요');
        if (liveOn && !finished) speakThenListen(v);
      })
      .catch(function (e) {
        busy = false;
        building(false);
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
  // 새로 정한 부품은 분위기 움직임 토큰(--m-dur·--m-ease·--m-rise)으로 올라오고 한 번 빛난다.
  var BASE_CSS =
    'section[class^="s-"]{animation:none!important;opacity:1!important;transform:none!important}' +
    '@keyframes live-build{from{opacity:0;transform:translateY(var(--m-rise,18px)) scale(.985)}to{opacity:1;transform:none}}' +
    '@keyframes live-glow{0%{box-shadow:inset 0 0 0 4px var(--c-accent,#6366f1)}100%{box-shadow:inset 0 0 0 4px transparent}}' +
    '@media (prefers-reduced-motion:reduce){[data-section-id]{animation:none!important}}';

  function decorate(html, part, still) {
    // 선택지 시안(still)은 작은 카드라 스크롤 막대·예시 안내 띠를 숨긴다.
    var css = BASE_CSS + (still ? 'html{scrollbar-width:none}body::-webkit-scrollbar{display:none}.s-draft-note{display:none!important}' : '');
    var js = '';
    if (part) {
      var sel = '[data-section-id="' + String(part).replace(/[^\w-]/g, '') + '"]';
      if (!REDUCED) {
        css += sel + '{animation:live-build var(--m-dur,700ms) var(--m-ease,ease-out) both,' +
          'live-glow 2.4s ease-out var(--m-dur,700ms) 1!important;scroll-margin-top:60px}';
      }
      // scrollIntoView는 바깥 페이지까지 움직이므로 미리보기 안에서만 부드럽게 내린다.
      js = '<script>addEventListener("load",function(){var e=document.querySelector(\'' + sel +
        '\');if(e)window.scrollTo({top:Math.max(0,e.getBoundingClientRect().top+window.scrollY-60),behavior:"' +
        (REDUCED ? 'auto' : 'smooth') + '"})});<\/script>';
    }
    var tag = '<style>' + css + '</style>' + js;
    return html.indexOf('</body>') >= 0 ? html.replace('</body>', tag + '</body>') : html + tag;
  }

  function drawPreview(p) {
    var toneChanged = lastHtml !== null && p.tone && p.tone !== drawPreview.tone;
    drawPreview.tone = p.tone;
    lastHtml = p.html;
    lastPart = p.last;
    partsEl.textContent = '';
    (p.components || []).forEach(function (c) {
      var s = document.createElement('span');
      s.textContent = c.label;
      if (c.type === 'tone') s.className = 'tone';
      if (!knownParts[c.id + ':' + c.variant]) {
        s.classList.add('new');  // 확정: 칩이 톡 나타난다
        knownParts[c.id + ':' + c.variant] = true;
      }
      partsEl.appendChild(s);
    });
    return render(toneChanged);
  }

  function building(on) {
    stage.classList.toggle('is-building', !!on);
  }

  function deviceFrame(kind, size) {
    var wrap = document.createElement('div');
    wrap.className = 'device ' + kind;
    var label = document.createElement('div');
    label.className = 'label';
    label.textContent = kind === 'mobile' ? '모바일 ' + size.w + 'px' : 'PC ' + size.w + 'px';
    var clip = document.createElement('div');
    clip.className = 'clip';
    wrap.appendChild(label);
    wrap.appendChild(clip);
    return { el: wrap, clip: clip, size: size, kind: kind };
  }

  var devices = {};

  // 같은 틀이면 새 화면을 뒤에 불러 두었다가 겹쳐 바꾼다(하얗게 깜빡이지 않게).
  function swapInto(d, html, toneChanged) {
    return new Promise(function (resolve) {
      var olds = Array.prototype.slice.call(d.clip.querySelectorAll('iframe'));
      var f = document.createElement('iframe');
      f.setAttribute('sandbox', 'allow-scripts');
      f.setAttribute('title', d.kind === 'mobile' ? '모바일 미리보기' : 'PC 미리보기');
      f.width = d.size.w;
      f.height = d.size.h;
      f.className = olds.length ? 'is-next' + (toneChanged ? ' is-tone' : '') : '';
      var done = false;
      function finish() {
        if (done) return;
        done = true;
        requestAnimationFrame(function () {
          f.classList.remove('is-next', 'is-tone');
          setTimeout(function () {
            olds.forEach(function (x) { x.remove(); });
            resolve();
          }, REDUCED || !olds.length ? 0 : 420);
        });
      }
      f.addEventListener('load', finish);
      setTimeout(finish, 4000);  // 불러오기가 늦어도 흐름은 이어 간다
      f.srcdoc = html;
      d.clip.appendChild(f);
      fit();
    });
  }

  function render(toneChanged) {
    Array.prototype.forEach.call(document.querySelectorAll('.seg button'), function (b) {
      b.setAttribute('aria-pressed', String(b.dataset.view === view));
    });
    if (!lastHtml) {
      frames.textContent = '';
      devices = {};
      var e = document.createElement('div');
      e.className = 'empty';
      e.innerHTML = '<b>말씀하시면 여기에 화면이 하나씩 생겨요</b>분위기를 고르면 색과 글씨가, 첫 화면·메뉴·사진·지도를 정할 때마다 그 부분이 바로 나타나요.';
      frames.appendChild(e);
      return Promise.resolve();
    }
    var want = [];
    if (view === 'mobile' || view === 'both') want.push('mobile');
    if (view === 'pc' || view === 'both') want.push('pc');
    if (Object.keys(devices).join() !== want.join()) {
      frames.textContent = '';
      devices = {};
      want.forEach(function (k) {
        devices[k] = deviceFrame(k, k === 'mobile' ? MOBILE : PC);
        frames.appendChild(devices[k].el);
      });
    }
    var html = decorate(lastHtml, lastPart);
    return Promise.all(want.map(function (k) { return swapInto(devices[k], html, toneChanged); }));
  }

  // 모바일 틀은 높이에 맞추고, PC 틀은 남은 너비에 맞춘다. "둘 다"는 나란히.
  function fit() {
    var W = stage.clientWidth - 32, H = frames.clientHeight - 40;
    var narrow = window.innerWidth < 820;
    var m = devices.mobile, p = devices.pc;
    function apply(d, scale) {
      scale = Math.max(0.15, Math.min(1, scale));
      Array.prototype.forEach.call(d.clip.querySelectorAll('iframe'), function (f) {
        f.style.setProperty('--s', String(scale));
      });
      d.clip.style.width = Math.round(d.size.w * scale) + 'px';
      d.clip.style.height = Math.round(d.size.h * scale) + 'px';
      return scale;
    }
    var sm = 0;
    var share = m && p ? (narrow ? 0.4 : 0.45) : 1;
    if (m) sm = apply(m, Math.min(W * share / (m.size.w + 16), H > 150 ? H / (m.size.h + 16) : 1));
    if (p) apply(p, (m ? W - m.size.w * sm - (narrow ? 20 : 36) : W) / (p.size.w + 2));
  }

  var resizeTimer = 0;
  window.addEventListener('resize', function () {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(function () {
      fit();
      currentCards.forEach(function (c) {
        var shot = c.querySelector('.shot'), f = shot && shot.querySelector('iframe');
        if (f) fitShot(shot, f);
      });
    }, 150);
  });
  Array.prototype.forEach.call(document.querySelectorAll('.seg button'), function (b) {
    b.addEventListener('click', function () {
      view = b.dataset.view;
      safeSet('agt001_live_view', view);
      render(false);
    });
  });

  // ── 소리로 읽기 (읽는 선택지 카드를 따라 강조) ──
  var audio = null, speakToken = 0;

  function stopSpeech() {
    speakToken++;
    if (audio) { try { audio.pause(); } catch (e) { /* 무시 */ } audio = null; }
    try { if (window.speechSynthesis) speechSynthesis.cancel(); } catch (e) { /* 무시 */ }
    reading(-1);
  }

  // parts[i]가 몇 번째 카드를 읽는지 (질문 글 다음부터 카드 순서, "빼기"·"알아서"는 읽지 않는다)
  function cardForPart(v, i) {
    var parts = v.speech_parts || [];
    var qi = parts.indexOf(v.question_text);
    if (qi < 0 || i <= qi) return -1;
    var k = i - qi - 1;
    var n = (v.options || []).filter(function (o) { return o !== '빼기' && o !== '알아서 해주세요'; }).length;
    return k < n ? k : -1;
  }

  function reading(k) {
    currentCards.forEach(function (c, i) { c.classList.toggle('is-reading', i === k); });
    var row = currentCards.length ? currentCards[0].parentNode : null;
    if (row) row.classList.toggle('is-reading', k >= 0);
  }

  function browserSpeak(text, token, onPart) {
    return new Promise(function (resolve) {
      if (!window.speechSynthesis || token !== speakToken) return resolve();
      var u = new SpeechSynthesisUtterance(text);
      u.lang = 'ko-KR';
      // 목소리가 없는 브라우저는 끝 신호를 안 줄 수 있어 글 길이만큼만 기다린다.
      var guard = setTimeout(resolve, 1500 + text.length * 150);
      if (onPart) onPart();
      u.onend = u.onerror = function () { clearTimeout(guard); resolve(); };
      speechSynthesis.speak(u);
    });
  }

  // 여러 부분을 280자 안으로 묶는다: [{text, parts:[{i, from, to}]}]
  function group(parts) {
    var out = [], cur = null;
    parts.forEach(function (p, i) {
      p = String(p || '').trim();
      if (!p) return;
      if (!cur || (cur.text + ' ' + p).length > TTS_CHUNK) { cur = { text: '', parts: [] }; out.push(cur); }
      var from = cur.text ? cur.text.length + 1 : 0;
      cur.text = cur.text ? cur.text + ' ' + p : p.slice(0, TTS_CHUNK);
      cur.parts.push({ i: i, from: from, to: cur.text.length });
    });
    return out;
  }

  function playChunk(chunk, token, v) {
    return api('/api/tts', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text: chunk.text })
    }).then(function (r) {
      if (!r.ok) throw new Error('tts');
      return r.blob();
    }).then(function (blob) {
      if (token !== speakToken) return;
      return new Promise(function (resolve) {
        var url = URL.createObjectURL(blob);
        audio = new Audio(url);
        var total = chunk.text.length || 1;
        // 글자 수 비율로 지금 읽는 부분을 가늠해 카드를 강조한다
        audio.ontimeupdate = function () {
          if (!audio || !audio.duration || !isFinite(audio.duration)) return;
          var at = (audio.currentTime / audio.duration) * total;
          var hit = chunk.parts.filter(function (p) { return at >= p.from && at < p.to; })[0];
          reading(hit ? cardForPart(v, hit.i) : -1);
        };
        audio.onended = audio.onerror = function () { URL.revokeObjectURL(url); resolve(); };
        audio.play().catch(function () {
          // 자동 재생이 막히면(iOS 등) 브라우저 목소리로 대신 읽는다.
          URL.revokeObjectURL(url);
          browserParts(chunk, token, v).then(resolve);
        });
      });
    }).catch(function () {
      // 서버 합성을 못 쓰면 브라우저 목소리로 부분마다 읽는다(부분마다 정확히 강조).
      return browserParts(chunk, token, v);
    });
  }

  function browserParts(chunk, token, v) {
    return chunk.parts.reduce(function (p, part) {
      return p.then(function () {
        if (token !== speakToken) return;
        return browserSpeak(chunk.text.slice(part.from, part.to), token, function () { reading(cardForPart(v, part.i)); });
      });
    }, Promise.resolve());
  }

  function speak(v) {
    stopSpeech();
    var token = speakToken;
    var parts = (v && v.speech_parts && v.speech_parts.length) ? v.speech_parts : [v && v.speech || ''];
    var chunks = group(parts);
    if (!chunks.length) return Promise.resolve(true);
    setStatus('speaking', '읽어 드리는 중… 끝나면 바로 들을게요');
    return chunks.reduce(function (p, c) {
      return p.then(function () { if (token === speakToken) return playChunk(c, token, v); });
    }, Promise.resolve()).then(function () { reading(-1); return token === speakToken; });
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

  function level(x) {
    document.documentElement.style.setProperty('--level', String(x));
    $('status').querySelector('.meter i').style.width = Math.round(x * 100) + '%';
  }

  function cleanupRec() {
    clearInterval(vadTimer); clearTimeout(maxTimer);
    if (stream) stream.getTracks().forEach(function (t) { t.stop(); });
    if (actx) { try { actx.close(); } catch (e) { /* 무시 */ } }
    stream = null; actx = null; rec = null;
    level(0);
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
          setStatus('busy', '알아듣는 중…');
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
        // 소리 크기로 말 끝을 잡는다. 크기는 마이크 물결(--level)에도 쓴다.
        try {
          actx = new (window.AudioContext || window.webkitAudioContext)();
          var an = actx.createAnalyser();
          an.fftSize = 1024;
          actx.createMediaStreamSource(s).connect(an);
          var data = new Uint8Array(an.fftSize);
          vadTimer = setInterval(function () {
            an.getByteTimeDomainData(data);
            var sum = 0;
            for (var i = 0; i < data.length; i++) { var v = (data[i] - 128) / 128; sum += v * v; }
            var rms = Math.sqrt(sum / data.length);
            level(Math.min(1, rms * 6));
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
        guessCard(text);
        setStatus('', '번호와 금액이 맞는지 확인하고 보내 주세요');
      } else if (statusEl.className) {
        // 마이크 권한 안내처럼 이미 띄운 문구(상태 없음)는 그대로 둔다
        setStatus('', sttError || '글자를 찾지 못했어요. 다시 또렷하게 말해 주세요.');
      }
    });
  });

  // 🔴 실시간 대화: 읽기 → 듣기 → 보내기 반복
  function speakThenListen(v) {
    if (!liveOn) return;
    speak(v).then(function (ok) {
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
    document.body.classList.remove('is-live');
    stopSpeech();
    stopListening();
  }

  liveBtn.addEventListener('click', function () {
    if (liveOn) { stopLive(); setStatus('', '실시간 대화를 멈췄어요'); return; }
    if (finished) return;
    liveOn = true;
    liveBtn.setAttribute('aria-pressed', 'true');
    liveBtn.textContent = '⏹ 대화 멈추기';
    document.body.classList.add('is-live');
    speakThenListen(current || {});
  });

  // ── 시작 ──
  render(false);
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
