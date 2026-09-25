/* static/voice.js — 채팅방 음성 입력 (MediaRecorder → POST /api/stt → #input에 넣기만)
 *
 * 계약: POST /api/stt (multipart/form-data, 필드 audio), 헤더 X-Member-Id.
 * 전사 결과는 입력칸(#input)에 넣기만 하고 자동 전송하지 않는다.
 * room.html의 `memberId`는 inline 스크립트의 let 변수라 다른 스크립트에서 직접
 * 참조할 수 없어, 같은 값이 저장된 localStorage('agt001_member_id')에서 읽는다.
 */
(function () {
  'use strict';

  var STT_URL = '/api/stt';
  var MAX_SECONDS = 60;
  var MAX_BYTES = 5 * 1024 * 1024;

  var MSG = {
    keyboardMic: '휴대폰 키보드의 마이크 버튼으로 말해도 돼요',
    uploading: '글자로 바꾸는 중…',
    checkNumbers: '번호와 금액이 맞는지 확인해 주세요',
    permissionDenied: '마이크 권한이 거부됐어요. 브라우저 설정에서 마이크를 허용한 뒤 다시 눌러 주세요.',
    noMic: '마이크를 찾을 수 없어요. 휴대폰 키보드의 마이크 버튼으로 말해도 돼요.',
    recordFail: '녹음을 시작할 수 없어요. 휴대폰 키보드의 마이크 버튼으로 말해도 돼요.',
    inApp: '인앱 브라우저에서는 녹음이 안 될 수 있어요. 오른쪽 위 메뉴에서 다른 브라우저로 열기해 보세요.',
    emptyRecord: '녹음이 비어 있어요. 다시 짧게 말해 주세요.',
    tooBig: '녹음이 너무 커요. 60초 이내, 5MB 이하로 짧게 말해 주세요.',
    emptyText: '글자를 찾지 못했어요. 다시 또렷하게 말해 주세요.',
    badRequest: '음성 파일을 읽지 못했어요. 다시 짧게 말해 주세요.',
    unsupportedType: '이 브라우저의 녹음 형식을 쓸 수 없어요. 휴대폰 키보드의 마이크 버튼으로 말해도 돼요.',
    tooMany: '요청이 너무 잦아요. 잠시 뒤에 다시 시도해 주세요.',
    unavailable: '지금은 음성 인식을 쓸 수 없어요. 키보드 마이크로 말해 주세요',
    networkFail: '전송에 실패했어요. 인터넷 연결을 확인하고 다시 시도해 주세요.'
  };

  var micBtn = document.getElementById('micBtn');
  var input = document.getElementById('input');
  var row = document.getElementById('row');
  if (!micBtn || !input || !row) return;

  // 입력칸 아래 상태 표시줄 (업로드 중·오류·권한 안내). 없으면 만든다.
  var statusEl = document.getElementById('voiceStatus');
  if (!statusEl) {
    statusEl = document.createElement('div');
    statusEl.id = 'voiceStatus';
    statusEl.setAttribute('role', 'status');
    statusEl.setAttribute('aria-live', 'polite');
    statusEl.style.cssText = 'display:none;padding:8px 16px;font-size:0.8125rem;color:#52525b;background:#fff;border-top:1px solid #e5e7eb;';
    row.parentNode.insertBefore(statusEl, row.nextSibling);
  }

  // 입력칸 위 번호 확인 안내. 없으면 만든다.
  var numEl = document.getElementById('voiceNumCheck');
  if (!numEl) {
    numEl = document.createElement('div');
    numEl.id = 'voiceNumCheck';
    numEl.style.cssText = 'display:none;padding:8px 16px;font-size:0.8125rem;color:#4338ca;background:#eef2ff;border-top:1px solid #e5e7eb;';
    numEl.textContent = MSG.checkNumbers;
    row.parentNode.insertBefore(numEl, row);
  }

  function showStatus(text) {
    statusEl.textContent = text;
    statusEl.style.display = 'block';
  }

  function clearStatus() {
    statusEl.textContent = '';
    statusEl.style.display = 'none';
  }

  function showNumCheck() { numEl.style.display = 'block'; }
  function hideNumCheck() { numEl.style.display = 'none'; }

  function isInApp() {
    var ua = (navigator && navigator.userAgent) || '';
    return /kakaotalk|naver/i.test(ua);
  }

  function voiceSupported() {
    return typeof navigator !== 'undefined' &&
      !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia) &&
      typeof window.MediaRecorder !== 'undefined';
  }

  // 미지원 환경: 버튼 숨기고 키보드 마이크 안내를 한 번 보여준다.
  if (!voiceSupported()) {
    micBtn.style.display = 'none';
    showStatus(MSG.keyboardMic);
    return;
  }

  function getMemberId() {
    try {
      if (typeof window.memberId === 'string' && window.memberId) return window.memberId;
    } catch (e) { /* 무시 */ }
    try {
      if (typeof localStorage !== 'undefined') {
        var v = localStorage.getItem('agt001_member_id');
        if (v) return v;
      }
    } catch (e) { /* storage 사용 불가 */ }
    return '';
  }

  var MIME_CANDIDATES = [
    'audio/webm;codecs=opus',
    'audio/webm',
    'audio/mp4',
    'audio/ogg;codecs=opus',
    'audio/wav'
  ];

  function pickMimeType() {
    try {
      if (typeof MediaRecorder.isTypeSupported === 'function') {
        for (var i = 0; i < MIME_CANDIDATES.length; i++) {
          if (MediaRecorder.isTypeSupported(MIME_CANDIDATES[i])) return MIME_CANDIDATES[i];
        }
      }
    } catch (e) { /* 무시하고 기본값 */ }
    return '';
  }

  // 전사 글자에 숫자(전화번호·가격)가 있는지. Parakeet가 한글 숫자로 내놓는
  // 경우("공일공…")도 잡기 위해 한글 숫자 연속 + 관련 키워드를 함께 본다.
  function hasNumber(text) {
    if (/[0-9]/.test(text)) return true;
    var compact = text.replace(/\s+/g, '');
    if (/[공영일두이삼사오육륙칠팔구십백천만억]{3,}/.test(compact)) return true;
    return /(전화번호|휴대폰|계좌|가격|금액)/.test(text);
  }

  var recorder = null;
  var stream = null;
  var chunks = [];
  var recording = false;
  var uploading = false;
  var tickId = null;
  var autoStopId = null;
  var startTime = 0;
  var timerSpan = null;
  var origBtnHtml = micBtn.innerHTML;

  var STOP_SVG = '<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><rect x="6" y="6" width="12" height="12" rx="2"/></svg>';

  function elapsedText() {
    return Math.floor((Date.now() - startTime) / 1000) + '초';
  }

  function tick() {
    if (timerSpan) timerSpan.textContent = elapsedText();
  }

  function setRecordingUI(on) {
    if (on) {
      micBtn.style.background = '#dc2626';
      micBtn.style.borderColor = '#dc2626';
      micBtn.style.color = '#fff';
      micBtn.style.flexDirection = 'column';
      micBtn.setAttribute('aria-label', '녹음 정지');
      micBtn.innerHTML = STOP_SVG + '<span id="micTimer" style="font-size:10px;line-height:1.2;">0초</span>';
      timerSpan = document.getElementById('micTimer');
    } else {
      micBtn.style.background = '';
      micBtn.style.borderColor = '';
      micBtn.style.color = '';
      micBtn.style.flexDirection = '';
      micBtn.setAttribute('aria-label', '말로 입력');
      micBtn.innerHTML = origBtnHtml;
      timerSpan = null;
    }
  }

  function cleanupStream() {
    if (stream) {
      try {
        var tracks = stream.getTracks();
        for (var i = 0; i < tracks.length; i++) tracks[i].stop();
      } catch (e) { /* 무시 */ }
      stream = null;
    }
  }

  function clearTimers() {
    if (tickId) { clearInterval(tickId); tickId = null; }
    if (autoStopId) { clearTimeout(autoStopId); autoStopId = null; }
  }

  function withInApp(text) {
    return isInApp() ? text + ' ' + MSG.inApp : text;
  }

  function onGetUserMediaFail(err) {
    var name = (err && err.name) || '';
    if (name === 'NotAllowedError' || name === 'SecurityError') {
      showStatus(MSG.permissionDenied);
    } else if (name === 'NotFoundError' || name === 'NotReadableError' || name === 'OverconstrainedError') {
      showStatus(MSG.noMic);
    } else {
      showStatus(withInApp(MSG.recordFail));
    }
  }

  function onRecordFail() {
    showStatus(withInApp(MSG.recordFail));
  }

  function extFromType(type) {
    if (/mp4/i.test(type)) return 'mp4';
    if (/ogg/i.test(type)) return 'ogg';
    if (/wav/i.test(type)) return 'wav';
    return 'webm';
  }

  function startRecording() {
    if (recording || uploading) return;
    hideNumCheck();
    navigator.mediaDevices.getUserMedia({ audio: true }).then(function (s) {
      stream = s;
      chunks = [];
      var mime = pickMimeType();
      try {
        recorder = mime
          ? new MediaRecorder(stream, { mimeType: mime })
          : new MediaRecorder(stream);
      } catch (e) {
        recorder = null;
        cleanupStream();
        onRecordFail();
        return;
      }
      recorder.ondataavailable = function (ev) {
        if (ev && ev.data && ev.data.size) chunks.push(ev.data);
      };
      recorder.onstop = onRecorderStop;
      try {
        recorder.start(1000);
      } catch (e) {
        recorder = null;
        cleanupStream();
        onRecordFail();
        return;
      }
      recording = true;
      startTime = Date.now();
      setRecordingUI(true);
      tick();
      tickId = setInterval(tick, 500);
      autoStopId = setTimeout(function () { stopRecording(); }, MAX_SECONDS * 1000);
      clearStatus();
    }).catch(onGetUserMediaFail);
  }

  function stopRecording() {
    if (!recording || !recorder) return;
    clearTimers();
    recording = false;
    try {
      recorder.stop();
    } catch (e) {
      // stop이 던지면 onstop이 안 올 수 있으니 직접 마무리
      onRecorderStop();
    }
  }

  function onRecorderStop() {
    clearTimers();
    recording = false;
    setRecordingUI(false);
    var type = '';
    try {
      type = (recorder && recorder.mimeType) || (chunks.length && chunks[0].type) || '';
    } catch (e) { /* 무시 */ }
    recorder = null;
    cleanupStream(); // 녹음 스트림은 정지 후 즉시 해제
    var blob = new Blob(chunks, { type: type || 'audio/webm' });
    chunks = [];
    if (!blob.size) {
      showStatus(MSG.emptyRecord);
      return;
    }
    if (blob.size > MAX_BYTES) {
      showStatus(MSG.tooBig); // 서버 413과 같은 안내
      return;
    }
    upload(blob);
  }

  function upload(blob) {
    uploading = true;
    micBtn.disabled = true;
    showStatus(MSG.uploading);
    var ext = extFromType(blob.type);
    var file;
    try {
      file = new File([blob], 'audio.' + ext, { type: blob.type || 'audio/' + ext });
    } catch (e) {
      file = blob; // 구형 브라우저 폴백 (파일명은 append 3번째 인자로)
    }
    var form = new FormData();
    form.append('audio', file, 'audio.' + ext);
    fetch(STT_URL, {
      method: 'POST',
      headers: { 'X-Member-Id': getMemberId() },
      body: form
    }).then(function (res) {
      if (res.ok) return res.json();
      if (res.status === 400) throw new Error(MSG.badRequest);
      if (res.status === 413) throw new Error(MSG.tooBig);
      if (res.status === 415) throw new Error(MSG.unsupportedType);
      if (res.status === 429) throw new Error(MSG.tooMany);
      if (res.status === 503) throw new Error(MSG.unavailable);
      throw new Error(withInApp(MSG.networkFail));
    }).then(function (data) {
      var text = (data && typeof data.text === 'string') ? data.text.trim() : '';
      if (!text) {
        showStatus(MSG.emptyText);
        return;
      }
      // 입력칸에 넣기만 한다. 자동 전송 금지. 기존 초안이 있으면 뒤에 이어 붙인다.
      var cur = input.value.trim();
      input.value = cur ? cur + ' ' + text : text;
      input.focus();
      if (hasNumber(text)) showNumCheck(); else hideNumCheck();
      clearStatus();
    }).catch(function (err) {
      if (err instanceof TypeError) {
        showStatus(withInApp(MSG.networkFail)); // 네트워크 단절 등
      } else {
        showStatus(err && err.message ? err.message : withInApp(MSG.networkFail));
      }
    }).then(function () {
      uploading = false;
      micBtn.disabled = false;
    });
  }

  micBtn.addEventListener('click', function () {
    if (uploading) return;
    if (recording) stopRecording();
    else startRecording();
  });
})();

/* static/voice.js 듣기 부분 — AI 답장 읽어주기 (POST /api/tts → WAV 재생)
 *
 * 계약: POST /api/tts (JSON {text}), 헤더 X-Member-Id. 성공 200 audio/wav.
 * room.html의 addMessage가 AI 답장 말풍선에 작은 "듣기" 버튼을 달고,
 * 누르면 window.speakAiText(글자, 버튼)를 부른다. 자동 재생하지 않는다.
 * 재생 중에 같은 버튼을 다시 누르면 멈춘다. 실패하면 버튼에 짧게 안내한다.
 */
(function () {
  'use strict';

  var TTS_URL = '/api/tts';
  var MAX_CHARS = 300;
  var LABEL_LISTEN = '듣기';
  var LABEL_STOP = '멈춤';
  var LABEL_LOADING = '준비 중…';

  function getMemberId() {
    try {
      if (typeof window.memberId === 'string' && window.memberId) return window.memberId;
    } catch (e) { /* 무시 */ }
    try {
      if (typeof localStorage !== 'undefined') {
        var v = localStorage.getItem('agt001_member_id');
        if (v) return v;
      }
    } catch (e) { /* storage 사용 불가 */ }
    return '';
  }

  var currentAudio = null;
  var currentBtn = null;
  var currentUrl = null;
  var loading = false;

  function cleanupAudio() {
    if (currentAudio) {
      try { currentAudio.pause(); } catch (e) { /* 무시 */ }
      currentAudio = null;
    }
    if (currentUrl) {
      try { URL.revokeObjectURL(currentUrl); } catch (e) { /* 무시 */ }
      currentUrl = null;
    }
  }

  function resetBtn(btn, label) {
    if (!btn) return;
    btn.textContent = label || LABEL_LISTEN;
    btn.disabled = false;
  }

  // 짧은 실패 안내를 버튼에 보여주고 잠시 뒤 원래 표시로 돌린다.
  function flashBtn(btn, msg) {
    if (!btn) return;
    btn.textContent = msg;
    btn.disabled = false;
    setTimeout(function () {
      if (currentBtn !== btn) resetBtn(btn);
    }, 2500);
  }

  function stopAll() {
    cleanupAudio();
    if (currentBtn) resetBtn(currentBtn);
    currentBtn = null;
    loading = false;
  }

  window.speakAiText = function (text, btn) {
    if (!btn) return;
    // 재생 중에 같은 버튼을 다시 누르면 멈춘다.
    if (currentAudio && currentBtn === btn) {
      stopAll();
      return;
    }
    if (loading) return;
    // 다른 답장을 듣던 중이면 멈추고 새로 시작한다.
    stopAll();
    var clean = (text || '').trim().slice(0, MAX_CHARS);
    if (!clean) {
      flashBtn(btn, '들을 내용이 없어요');
      return;
    }
    loading = true;
    currentBtn = btn;
    btn.textContent = LABEL_LOADING;
    btn.disabled = true;
    fetch(TTS_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Member-Id': getMemberId() },
      body: JSON.stringify({ text: clean })
    }).then(function (res) {
      if (res.ok) return res.blob();
      if (res.status === 429) throw new Error('요청이 많아요 잠시 뒤에');
      throw new Error('지금은 듣기를 쓸 수 없어요');
    }).then(function (blob) {
      if (!blob || !blob.size) throw new Error('소리가 비어 있어요');
      var url = URL.createObjectURL(blob);
      var audio = new Audio(url);
      currentUrl = url;
      currentAudio = audio;
      btn.textContent = LABEL_STOP;
      btn.disabled = false;
      audio.onended = function () { stopAll(); };
      audio.onerror = function () { stopAll(); flashBtn(btn, '재생에 실패했어요'); };
      var played = audio.play();
      if (played && typeof played.catch === 'function') {
        played.catch(function () { stopAll(); flashBtn(btn, '재생에 실패했어요'); });
      }
    }).catch(function (err) {
      stopAll();
      if (err instanceof TypeError) {
        flashBtn(btn, '인터넷 연결을 확인해 주세요');
      } else {
        flashBtn(btn, err && err.message ? err.message : '지금은 듣기를 쓸 수 없어요');
      }
    });
  };
})();
