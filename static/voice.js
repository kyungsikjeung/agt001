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
    networkFail: '전송에 실패했어요. 인터넷 연결을 확인하고 다시 시도해 주세요.',
    walkieTooShort: '길게 누르고 말해 주세요',
    walkiePreview: '보내는 중… 취소하려면 취소를 눌러 주세요',
    listening: '듣고 있어요… 말이 끝나면 자동으로 보내요',
    noVoice: '말씀이 없어서 듣기를 멈췄어요. 🎤를 누르면 다시 들어요',
    missHeard: '잘 못 들었어요. 다시 말씀해 주세요',
    micBlocked: '마이크를 쓸 수 없어 손 안 쓰는 모드를 껐어요'
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
    statusEl.style.cssText = 'display:none;padding:8px 16px;font-size:0.8125rem;color:var(--text-muted, #52525b);background:var(--surface, #fff);border-top:1px solid var(--border, #e5e7eb);';
    row.parentNode.insertBefore(statusEl, row.nextSibling);
  }

  // 입력칸 위 번호 확인 안내. 없으면 만든다.
  var numEl = document.getElementById('voiceNumCheck');
  if (!numEl) {
    numEl = document.createElement('div');
    numEl.id = 'voiceNumCheck';
    numEl.style.cssText = 'display:none;padding:8px 16px;font-size:0.8125rem;color:var(--accent-dark, #4338ca);background:var(--tint, #eef2ff);border-top:1px solid var(--border, #e5e7eb);';
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

  // 음성 인식 카운터(전사 글자·IP 저장 없음, D16). 올리기 실패·빈결과를 1건씩만 POST /events로 센다.
  // 성공은 서버(app/api/stt.py)가 has_number와 함께 센다. 손 안 쓰는 모드 재시도는 세지 않는다(중복 방지).
  function countVoiceEvent(event) {
    try {
      var body = JSON.stringify({ event: event });
      fetch('/events', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: body, keepalive: true }).catch(function () { /* 카운터 실패 무시 */ });
    } catch (e) { /* 카운터 실패 무시 */ }
  }

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
  var DOT_SVG = '<svg width="10" height="10" viewBox="0 0 10 10" fill="currentColor" aria-hidden="true"><circle cx="5" cy="5" r="5"/></svg>';

  // Walkie-talkie mode (push to talk). Default off, persisted in localStorage.
  var WALKIE_KEY = 'agt001_walkie';
  var WALKIE_MIN_MS = 500;
  var WALKIE_PREVIEW_MS = 800;
  var walkieOn = loadWalkie();
  var walkieHolding = false;
  var walkieSend = false;
  var walkiePreviewTimer = null;
  var walkieSwitch = null;
  var walkieCancelBtn = null;

  // 손 안 쓰는 모드: 답장 읽기가 끝나면 스스로 듣기를 시작한다. 기본은 꺼짐.
  var HANDSFREE_KEY = 'agt001_handsfree';
  // 말소리 판단 기준값. 작게 하면 작은 소리에도 반응하고 크게 하면 큰 소리만 잡는다.
  var SILENCE_RMS = 0.02;
  // 말소리가 나온 뒤 이 시간만큼 조용하면 말 끝으로 본다.
  var END_SILENCE_MS = 1200;
  // 처음 이 시간 동안 말소리가 없으면 듣기를 그만둔다.
  var NO_VOICE_MS = 8000;
  // 읽기가 끝난 뒤 듣기를 시작하기까지 기다리는 시간.
  var HANDSFREE_DELAY_MS = 300;
  var handsfreeOn = loadHandsfree();
  var handsfreeSwitch = null;
  var handsfreeListening = false;
  var handsfreeWaiting = null;
  var handsfreeDiscard = false;
  var handsfreePreview = false;
  var handsfreeFail = 0;
  // 말끝 감지용 소리 분석기 상태.
  var vadCtx = null;
  var vadAnalyser = null;
  var vadData = null;
  var vadTimer = null;
  var vadHasVoice = false;
  var vadQuietAt = 0;

  function loadHandsfree() {
    try {
      if (typeof localStorage !== 'undefined') return localStorage.getItem(HANDSFREE_KEY) === '1';
    } catch (e) { /* 저장소 사용 불가 */ }
    return false;
  }

  function saveHandsfree(on) {
    try {
      if (typeof localStorage !== 'undefined') localStorage.setItem(HANDSFREE_KEY, on ? '1' : '0');
    } catch (e) { /* 저장소 사용 불가 */ }
  }

  // 답할 질문이 있는지. 선택지 막대가 열려 있거나 답장 글에 물음표가 있으면 있다.
  function hasQuestion(text) {
    try {
      var bar = document.getElementById('choiceBar');
      if (bar && bar.classList && bar.classList.contains('show')) return true;
    } catch (e) { /* 무시 */ }
    return (text || '').indexOf('?') >= 0;
  }

  function setHandsfree(on) {
    handsfreeOn = !!on;
    saveHandsfree(handsfreeOn);
    updateHandsfreeUI();
    if (!handsfreeOn) {
      handsfreeFail = 0;
      cancelHandsfreeListen();
    }
  }

  function updateHandsfreeUI() {
    try {
      if (!handsfreeSwitch) return;
      handsfreeSwitch.setAttribute('aria-checked', handsfreeOn ? 'true' : 'false');
      handsfreeSwitch.textContent = handsfreeOn ? '손 안 쓰는 모드: 켜짐' : '손 안 쓰는 모드: 꺼짐';
      handsfreeSwitch.setAttribute('aria-label', handsfreeOn ? '손 안 쓰는 모드 켜짐' : '손 안 쓰는 모드 꺼짐');
      handsfreeSwitch.style.background = handsfreeOn ? 'var(--accent-dark, #4338ca)' : 'var(--bg, #f7f7f8)';
      handsfreeSwitch.style.color = handsfreeOn ? 'var(--on-accent, #fff)' : '';
      handsfreeSwitch.style.borderColor = handsfreeOn ? 'var(--accent-dark, #4338ca)' : '';
    } catch (e) { /* 무시 */ }
  }

  function buildHandsfreeUI() {
    try {
      handsfreeSwitch = document.createElement('button');
      handsfreeSwitch.type = 'button';
      handsfreeSwitch.id = 'handsfreeSwitch';
      handsfreeSwitch.setAttribute('role', 'switch');
      handsfreeSwitch.style.cssText = 'min-height:44px;padding:0 14px;border:1px solid var(--border, #e5e7eb);border-radius:999px;background:var(--bg, #f7f7f8);cursor:pointer;font-size:0.8125rem;';
      handsfreeSwitch.addEventListener('click', function () {
        var next = !handsfreeOn;
        if (next) {
          // 읽어주기를 함께 켜고 소리 재생을 미리 푼다.
          try { if (typeof window.setAutoreadMode === 'function') window.setAutoreadMode(true); } catch (e) { /* 무시 */ }
          try { if (typeof window.unlockSpeech === 'function') window.unlockSpeech(); } catch (e) { /* 무시 */ }
          setHandsfree(true);
          try { micBtn.focus(); } catch (e) { /* 무시 */ }
          // 켜는 누름 안에서 마이크 권한을 미리 받아 둔다. 바로 끊어서 녹음은 안 남긴다.
          try {
            if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
              navigator.mediaDevices.getUserMedia({ audio: true }).then(function (s) {
                try {
                  var ts = s.getTracks();
                  for (var i = 0; i < ts.length; i++) ts[i].stop();
                } catch (e2) { /* 무시 */ }
              }).catch(function () {
                setHandsfree(false);
                showStatus(MSG.micBlocked);
              });
            }
          } catch (e) { /* 무시 */ }
        } else {
          setHandsfree(false);
          try { micBtn.focus(); } catch (e) { /* 무시 */ }
        }
      });
      var slot = document.getElementById('walkieSlot');
      if (slot) {
        slot.appendChild(handsfreeSwitch);
      } else {
        var rowEl = document.getElementById('walkieRow');
        if (rowEl) rowEl.appendChild(handsfreeSwitch);
      }
      updateHandsfreeUI();
    } catch (e) { /* 화면 만들기가 실패해도 음성 입력은 유지 */ }
  }

  // 읽기 끝 알림을 받으면 질문이 있을 때만 잠시 뒤 듣기를 시작한다.
  function onTtsFinished(ok, text) {
    if (!ok) return;
    if (!handsfreeOn) return;
    if (recording || uploading) return;
    if (!hasQuestion(text)) return;
    handsfreeFail = 0;
    if (handsfreeWaiting) { clearTimeout(handsfreeWaiting); handsfreeWaiting = null; }
    handsfreeWaiting = setTimeout(function () {
      handsfreeWaiting = null;
      startHandsfreeListen();
    }, HANDSFREE_DELAY_MS);
  }

  function startHandsfreeListen() {
    if (!handsfreeOn || recording || uploading || window.__agtOnCall) return;
    handsfreeListening = true;
    handsfreeDiscard = false;
    walkieDownAt = 0;
    showStatus(MSG.listening);
    showWalkieCancel();
    startRecording(true);
  }

  // 진행 중인 자동 듣기를 그만둔다. 녹음 중이면 보내지 않고 끊는다.
  function cancelHandsfreeListen() {
    if (handsfreeWaiting) { clearTimeout(handsfreeWaiting); handsfreeWaiting = null; }
    if (handsfreePreview) {
      handsfreePreview = false;
      cancelWalkiePreview();
    }
    if (handsfreeListening && recording) {
      handsfreeDiscard = true;
      stopVad();
      stopRecording();
      hideWalkieCancel();
      clearStatus();
      try { input.focus(); } catch (e) { /* 무시 */ }
    } else if (handsfreeListening) {
      handsfreeListening = false;
      stopVad();
      hideWalkieCancel();
      clearStatus();
    } else {
      hideWalkieCancel();
    }
    handsfreeListening = false;
  }

  // 자동 재생이나 마이크가 막히면 모드를 끄고 한 줄로 알린다.
  function stopHandsfreeBlocked() {
    if (!handsfreeOn && !handsfreeListening && !handsfreeWaiting) return;
    handsfreeOn = false;
    saveHandsfree(false);
    updateHandsfreeUI();
    if (handsfreeWaiting) { clearTimeout(handsfreeWaiting); handsfreeWaiting = null; }
    handsfreeListening = false;
    stopVad();
    hideWalkieCancel();
    showStatus(MSG.micBlocked);
  }

  // 녹음 소리를 작게 나눠서 RMS(소리 크기)를 본다.
  function startVad() {
    stopVad();
    try {
      if (!stream) return;
      var AC = window.AudioContext || window.webkitAudioContext;
      if (!AC) return;
      vadCtx = new AC();
      var src = vadCtx.createMediaStreamSource(stream);
      vadAnalyser = vadCtx.createAnalyser();
      vadAnalyser.fftSize = 2048;
      src.connect(vadAnalyser);
      var len = vadAnalyser.fftSize;
      vadData = new Uint8Array(len);
      vadHasVoice = false;
      vadQuietAt = Date.now();
      vadTimer = setInterval(checkVad, 120);
    } catch (e) {
      stopVad();
    }
  }

  function stopVad() {
    if (vadTimer) { clearInterval(vadTimer); vadTimer = null; }
    if (vadCtx) {
      try { vadCtx.close(); } catch (e) { /* 무시 */ }
      vadCtx = null;
    }
    vadAnalyser = null;
    vadData = null;
  }

  function checkVad() {
    try {
      if (!vadAnalyser || !vadData || !recording) return;
      vadAnalyser.getByteTimeDomainData(vadData);
      var sum = 0;
      for (var i = 0; i < vadData.length; i++) {
        var v = (vadData[i] - 128) / 128;
        sum += v * v;
      }
      var rms = Math.sqrt(sum / vadData.length);
      var now = Date.now();
      if (rms >= SILENCE_RMS) {
        vadHasVoice = true;
        vadQuietAt = now;
        return;
      }
      if (vadHasVoice && (now - vadQuietAt) >= END_SILENCE_MS) {
        // 말이 끝난 뒤 조용하면 자동 전송을 위해 끊는다.
        stopRecording();
        return;
      }
      if (!vadHasVoice && (now - startTime) >= NO_VOICE_MS) {
        // 처음부터 말소리가 없으면 보내지 않고 그만둔다.
        handsfreeDiscard = true;
        stopVad();
        stopRecording();
        hideWalkieCancel();
        handsfreeListening = false;
        showStatus(MSG.noVoice);
      }
    } catch (e) { /* 소리 분석 실패는 무시하고 최대 시간까지 둔다 */ }
  }

  // 자동 듣기 중에는 글자를 치거나 보내기·선택지를 누르면 듣기를 그만둔다.
  function bindHandsfreeCancel() {
    try {
      input.addEventListener('input', function () {
        if (handsfreeOn && handsfreeListening && recording) cancelHandsfreeListen();
      });
      var sendBtn = document.getElementById('sendBtn');
      if (sendBtn) {
        sendBtn.addEventListener('click', function () {
          if (handsfreeOn && (handsfreeListening || handsfreeWaiting)) cancelHandsfreeListen();
        }, true);
      }
      var bar = document.getElementById('choiceBar');
      if (bar) {
        bar.addEventListener('click', function () {
          if (handsfreeOn && (handsfreeListening || handsfreeWaiting)) cancelHandsfreeListen();
        }, true);
      }
    } catch (e) { /* 무시 */ }
  }

  function loadWalkie() {
    try {
      if (typeof localStorage !== 'undefined') return localStorage.getItem(WALKIE_KEY) === '1';
    } catch (e) { /* storage unavailable */ }
    return false;
  }

  function saveWalkie(on) {
    try {
      if (typeof localStorage !== 'undefined') localStorage.setItem(WALKIE_KEY, on ? '1' : '0');
    } catch (e) { /* storage unavailable */ }
  }

  function buzz() {
    try {
      if (navigator && typeof navigator.vibrate === 'function') navigator.vibrate(20);
    } catch (e) { /* ignore */ }
  }

  function buildWalkieUI() {
    try {
      var wrap = document.createElement('div');
      wrap.id = 'walkieRow';
      wrap.style.cssText = 'display:flex;gap:8px;align-items:center;padding:8px 16px;background:var(--surface, #fff);border-top:1px solid var(--border, #e5e7eb);font-size:0.8125rem;color:var(--text-muted, #52525b);';
      walkieSwitch = document.createElement('button');
      walkieSwitch.type = 'button';
      walkieSwitch.id = 'walkieSwitch';
      walkieSwitch.setAttribute('role', 'switch');
      walkieSwitch.style.cssText = 'min-height:44px;padding:0 14px;border:1px solid var(--border, #e5e7eb);border-radius:999px;background:var(--bg, #f7f7f8);cursor:pointer;font-size:0.8125rem;';
      walkieSwitch.addEventListener('click', function () {
        setWalkie(!walkieOn);
        try { micBtn.focus(); } catch (e) { /* ignore */ }
      });
      wrap.appendChild(walkieSwitch);
      walkieCancelBtn = document.createElement('button');
      walkieCancelBtn.type = 'button';
      walkieCancelBtn.id = 'walkieCancel';
      walkieCancelBtn.hidden = true;
      walkieCancelBtn.style.cssText = 'min-height:44px;padding:0 14px;border:1px solid var(--border, #e5e7eb);border-radius:8px;background:var(--surface, #fff);cursor:pointer;font-size:0.8125rem;';
      walkieCancelBtn.addEventListener('click', cancelWalkiePreview);
      wrap.appendChild(walkieCancelBtn);
      row.parentNode.insertBefore(wrap, row);
    } catch (e) { /* UI build failure must not break voice input */ }
  }

  function setWalkie(on) {
    walkieOn = !!on;
    saveWalkie(walkieOn);
    updateWalkieUI();
  }

  function updateWalkieUI() {
    try {
      if (walkieSwitch) {
        walkieSwitch.setAttribute('aria-checked', walkieOn ? 'true' : 'false');
        walkieSwitch.textContent = walkieOn ? '무전기 모드: 켜짐' : '무전기 모드: 꺼짐';
        walkieSwitch.setAttribute('aria-label', walkieOn ? '무전기 모드 켜짐' : '무전기 모드 꺼짐');
        walkieSwitch.style.background = walkieOn ? 'var(--accent-dark, #4338ca)' : 'var(--bg, #f7f7f8)';
        walkieSwitch.style.color = walkieOn ? 'var(--on-accent, #fff)' : '';
        walkieSwitch.style.borderColor = walkieOn ? 'var(--accent-dark, #4338ca)' : '';
      }
      if (!walkieOn) hideWalkieCancel();
      updateMicLabel();
    } catch (e) { /* ignore */ }
  }

  function updateMicLabel() {
    try {
      if (recording) {
        micBtn.setAttribute('aria-label', walkieOn ? '녹음 중, 떼면 전송' : '녹음 정지');
      } else {
        micBtn.setAttribute('aria-label', walkieOn ? '누르고 말하기' : '말로 입력');
      }
    } catch (e) { /* ignore */ }
  }

  function showWalkieCancel() {
    if (!walkieCancelBtn) return;
    walkieCancelBtn.textContent = '취소';
    walkieCancelBtn.setAttribute('aria-label', '전송 취소');
    walkieCancelBtn.hidden = false;
  }

  function hideWalkieCancel() {
    if (walkiePreviewTimer) { clearTimeout(walkiePreviewTimer); walkiePreviewTimer = null; }
    if (walkieCancelBtn) walkieCancelBtn.hidden = true;
  }

  function cancelWalkiePreview() {
    // 자동 듣기 중 취소 버튼은 녹음을 보내지 않고 끊는다.
    if (handsfreeListening && recording) {
      handsfreeDiscard = true;
      handsfreePreview = false;
      stopVad();
      stopRecording();
      hideWalkieCancel();
      handsfreeListening = false;
      clearStatus();
      try { input.focus(); } catch (e) { /* 무시 */ }
      return;
    }
    hideWalkieCancel();
    handsfreePreview = false;
    walkieSend = false;
    clearStatus();
    try { input.focus(); } catch (e) { /* ignore */ }
  }

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
      updateMicLabel();
      micBtn.innerHTML = STOP_SVG;
      if (walkieOn) {
        var dot = document.createElement('span');
        dot.setAttribute('aria-hidden', 'true');
        dot.innerHTML = DOT_SVG;
        dot.style.cssText = 'line-height:1;color:#fff;';
        micBtn.appendChild(dot);
      }
      var ts = document.createElement('span');
      ts.id = 'micTimer';
      ts.style.cssText = 'font-size:10px;line-height:1.2;';
      ts.textContent = '0초';
      micBtn.appendChild(ts);
      timerSpan = ts;
    } else {
      micBtn.style.background = '';
      micBtn.style.borderColor = '';
      micBtn.style.color = '';
      micBtn.style.flexDirection = '';
      micBtn.innerHTML = origBtnHtml;
      timerSpan = null;
      updateMicLabel();
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
    // 자동 듣기 중 마이크가 막히면 모드를 끄고 한 줄로 알린다.
    if (handsfreeOn || handsfreeListening || handsfreeWaiting) {
      if (handsfreeWaiting) { clearTimeout(handsfreeWaiting); handsfreeWaiting = null; }
      handsfreeListening = false;
      stopVad();
      hideWalkieCancel();
      stopHandsfreeBlocked();
      return;
    }
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

  var walkieDownAt = 0;

  function startRecording(isWalkie) {
    if (recording || uploading) return;
    // 녹음이 시작되면 읽던 소리를 바로 끊는다.
    try { if (typeof window.stopAllSpeech === 'function') window.stopAllSpeech(); } catch (e) { /* 무시 */ }
    // 손 안 쓰는 모드도 무전기와 같은 자동 전송 길을 쓴다.
    walkieSend = !!isWalkie && (walkieOn || handsfreeOn);
    if (walkieSend && !handsfreeListening) buzz();
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
      // Walkie: pointer was released before permission resolved.
      // 손 안 쓰는 모드는 누름이 없어 이 경우에 걸리면 안 된다.
      if (walkieSend && !walkieHolding && walkieOn && !handsfreeListening) {
        try { recorder.stop(); } catch (e) { onRecorderStop(); }
        return;
      }
      recording = true;
      startTime = Date.now();
      setRecordingUI(true);
      tick();
      tickId = setInterval(tick, 500);
      autoStopId = setTimeout(function () { stopRecording(); }, MAX_SECONDS * 1000);
      clearStatus();
      if (handsfreeListening) {
        showStatus(MSG.listening);
        showWalkieCancel();
        startVad();
      }
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
    stopVad();
    recording = false;
    setRecordingUI(false);
    var wasWalkie = walkieSend;
    var wasHandsfree = handsfreeListening;
    var discarded = handsfreeDiscard;
    handsfreeListening = false;
    handsfreeDiscard = false;
    walkieSend = false;
    var heldMs = walkieDownAt ? Date.now() - walkieDownAt : 9999;
    walkieDownAt = 0;
    walkieHolding = false;
    var type = '';
    try {
      type = (recorder && recorder.mimeType) || (chunks.length && chunks[0].type) || '';
    } catch (e) { /* 무시 */ }
    recorder = null;
    cleanupStream(); // 녹음 스트림은 정지 후 즉시 해제
    // 자동 듣기 취소·말소리 없음이면 보내지 않고 끝낸다. 안내는 부른 쪽이 이미 남겼다.
    if (discarded || (wasHandsfree && handsfreeDiscard)) {
      handsfreeDiscard = false;
      chunks = [];
      hideWalkieCancel();
      return;
    }
    var blob = new Blob(chunks, { type: type || 'audio/webm' });
    chunks = [];
    if (wasWalkie && heldMs < WALKIE_MIN_MS && !wasHandsfree) {
      showStatus(MSG.walkieTooShort);
      return;
    }
    if (!blob.size) {
      // 손 안 쓰는 모드의 빈 녹음은 놓친 말로 다룬다.
      if (wasHandsfree && handsfreeOn) {
        onHandsfreeMiss();
        return;
      }
      showStatus(MSG.emptyRecord);
      return;
    }
    if (blob.size > MAX_BYTES) {
      showStatus(MSG.tooBig); // 서버 413과 같은 안내
      return;
    }
    upload(blob, wasWalkie, wasHandsfree);
  }

  // 받아쓰기가 비었거나 한 글자일 때. 한 번만 다시 듣고 두 번 연속이면 그만둔다.
  function onHandsfreeMiss() {
    handsfreeFail++;
    if (handsfreeOn && handsfreeFail < 2) {
      showStatus(MSG.missHeard);
      if (handsfreeWaiting) { clearTimeout(handsfreeWaiting); handsfreeWaiting = null; }
      handsfreeWaiting = setTimeout(function () {
        handsfreeWaiting = null;
        startHandsfreeListen();
      }, HANDSFREE_DELAY_MS);
      return;
    }
    handsfreeFail = 0;
    hideWalkieCancel();
    showStatus(MSG.noVoice);
  }

  function upload(blob, isWalkie, isHandsfree) {
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
      // 손 안 쓰는 모드는 비었거나 한 글자면 보내지 않고 다시 듣는다.
      if (isHandsfree && (!text || text.length < 2)) {
        onHandsfreeMiss();
        return;
      }
      if (!text) {
        showStatus(MSG.emptyText);
        countVoiceEvent('voice_stt_empty');
        return;
      }
      handsfreeFail = 0;
      if (isWalkie && (walkieOn || isHandsfree)) {
        // Walkie: show briefly, allow cancel, then send immediately.
        var curW = input.value.trim();
        var combined = curW ? curW + ' ' + text : text;
        input.value = combined;
        input.focus();
        if (hasNumber(text)) showNumCheck(); else hideNumCheck();
        showStatus(MSG.walkiePreview);
        showWalkieCancel();
        handsfreePreview = !!isHandsfree;
        walkieSend = true;
        if (walkiePreviewTimer) clearTimeout(walkiePreviewTimer);
        walkiePreviewTimer = setTimeout(function () {
          walkiePreviewTimer = null;
          handsfreePreview = false;
          if (!walkieSend) return;
          walkieSend = false;
          hideWalkieCancel();
          clearStatus();
          var toSend = input.value.trim() || combined;
          try { input.value = ''; } catch (e) { /* ignore */ }
          try {
            if (typeof window.sendRoomMessage === 'function') window.sendRoomMessage(toSend);
          } catch (e) { /* send failure keeps text cleared; status shows below */ }
        }, WALKIE_PREVIEW_MS);
        return;
      }
      // 입력칸에 넣기만 한다. 자동 전송 금지. 기존 초안이 있으면 뒤에 이어 붙인다.
      var cur = input.value.trim();
      input.value = cur ? cur + ' ' + text : text;
      input.focus();
      if (hasNumber(text)) showNumCheck(); else hideNumCheck();
      clearStatus();
    }).catch(function (err) {
      countVoiceEvent('voice_stt_fail'); // 올리기 실패(HTTP 오류·네트워크 단절) 1건
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

  function startWalkieHold() {
    if (uploading) return;
    if (recording) return;
    hideWalkieCancel();
    walkieHolding = true;
    walkieDownAt = Date.now();
    startRecording(true);
  }

  function endWalkieHold() {
    if (!walkieHolding && !recording) return;
    walkieHolding = false;
    if (recording) stopRecording();
    else {
      // Released before recorder started; startRecording completion will stop itself.
      // If nothing started, reset short-press timer state shortly.
      var downAt = walkieDownAt;
      setTimeout(function () {
        if (!recording && walkieDownAt === downAt) {
          walkieDownAt = 0;
          walkieSend = false;
        }
      }, 50);
    }
  }

  micBtn.addEventListener('click', function () {
    if (walkieOn) return; // walkie uses press-and-hold, ignore toggle click
    if (uploading) return;
    if (recording) stopRecording();
    else startRecording(false);
  });

  micBtn.addEventListener('pointerdown', function (ev) {
    if (!walkieOn) return;
    if (uploading) return;
    try { ev.preventDefault(); } catch (e) { /* ignore */ }
    try { micBtn.setPointerCapture(ev.pointerId); } catch (e) { /* ignore */ }
    startWalkieHold();
  });
  micBtn.addEventListener('pointerup', function () {
    if (!walkieOn) return;
    endWalkieHold();
  });
  micBtn.addEventListener('pointercancel', function () {
    if (!walkieOn) return;
    endWalkieHold();
  });
  micBtn.addEventListener('pointerleave', function () {
    if (!walkieOn) return;
    if (walkieHolding && recording) endWalkieHold();
  });
  micBtn.addEventListener('keydown', function (ev) {
    if (!walkieOn) return;
    if (ev.key !== ' ' && ev.key !== 'Spacebar') return;
    if (ev.repeat) { try { ev.preventDefault(); } catch (e) { /* ignore */ } return; }
    try { ev.preventDefault(); } catch (e) { /* ignore */ }
    startWalkieHold();
  });
  micBtn.addEventListener('keyup', function (ev) {
    if (!walkieOn) return;
    if (ev.key !== ' ' && ev.key !== 'Spacebar') return;
    try { ev.preventDefault(); } catch (e) { /* ignore */ }
    endWalkieHold();
  });

  buildWalkieUI();
  updateWalkieUI();
  buildHandsfreeUI();
  bindHandsfreeCancel();
  window.setWalkieMode = setWalkie;
  window.isWalkieOn = function () { return walkieOn; };
  // 손 안 쓰는 모드 바깥 연결. 듣기 부분과 방 화면이 쓴다.
  window.setHandsfreeMode = setHandsfree;
  window.isHandsfreeOn = function () { return handsfreeOn; };
  window.cancelHandsfreeListen = cancelHandsfreeListen;
  window.__handsfreeTtsEnd = onTtsFinished;
  window.__handsfreeBlocked = stopHandsfreeBlocked;
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

  // 재생 상태: 손으로 누른 듣기와 자동 읽기가 하나로 합쳐진다. 새 답장이 오면 이전 것을 끊는다.
  var activeAudio = null;
  // iOS Safari는 사람이 누를 때 재생한 오디오 객체만 나중에 스스로 재생을 허락한다. 켜는 누름에서 푼 객체 하나를 계속 쓴다.
  var sharedAudio = null;
  var activeUrl = null;
  var activeBtn = null;
  var activeChunks = null;
  var activeIndex = 0;
  var prefetchUrl = null;
  var prefetchIdx = -1;
  var loading = false;
  var activeIsAuto = false;
  // 손 안 쓰는 모드가 끝난 뒤 들을지 판단하는 마지막 자동 읽기 글자.
  var lastAutoText = '';
  // 입장 읽기: 처음 들어와 지난 글을 다 받은 직후 한 번만 읽는다.
  var enterDone = false;
  var enterPending = false;
  var enterText = '';
  var pendingEnterText = '';
  // 끊기 세대 번호: 늦게 도착한 요청 결과는 버린다.
  var speechGen = 0;
  // 긴 답장 나누기 상수
  var CHUNK_MAX = 280;
  var MAX_CHUNKS = 4;

  function cleanupActive() {
    if (activeAudio) {
      try { activeAudio.pause(); } catch (e) { /* 무시 */ }
      activeAudio = null;
    }
    if (activeUrl) {
      try { URL.revokeObjectURL(activeUrl); } catch (e) { /* 무시 */ }
      activeUrl = null;
    }
  }

  function clearPrefetch() {
    if (prefetchUrl) {
      try { URL.revokeObjectURL(prefetchUrl); } catch (e) { /* 무시 */ }
      prefetchUrl = null;
    }
    prefetchIdx = -1;
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
      if (activeBtn !== btn) resetBtn(btn);
    }, 2500);
  }

  // 읽던 소리를 멈추고 대기 중인 읽기를 모두 비운다. 듣기 버튼 재생도 함께 멈춘다.
  function stopAllSpeech() {
    speechGen++;
    enterPending = false;
    cleanupActive();
    clearPrefetch();
    if (activeBtn) resetBtn(activeBtn);
    activeBtn = null;
    activeChunks = null;
    activeIndex = 0;
    activeIsAuto = false;
    lastAutoText = '';
    loading = false;
  }

  function isWalkieEnabled() {
    try {
      if (typeof window.isWalkieOn === 'function') return !!window.isWalkieOn();
      if (typeof localStorage !== 'undefined') return localStorage.getItem('agt001_walkie') === '1';
    } catch (e) { /* 무시 */ }
    return false;
  }

  // 답변 읽어주기 켜짐 여부: 무전기가 켜져 있으면 켜진 것으로 본다.
  var AUTOREAD_KEY = 'agt001_autoread';
  var autoreadOn = loadAutoread();
  var autoreadSwitch = null;

  function loadAutoread() {
    try {
      if (typeof localStorage !== 'undefined') return localStorage.getItem(AUTOREAD_KEY) !== '0';
    } catch (e) { /* 저장소 사용 불가 */ }
    return true;
  }

  function saveAutoread(on) {
    try {
      if (typeof localStorage !== 'undefined') localStorage.setItem(AUTOREAD_KEY, on ? '1' : '0');
    } catch (e) { /* 저장소 사용 불가 */ }
  }

  function shouldAutoRead() {
    if (window.__agtOnCall) return false;  // 전화 중에는 전화가 읽는다 (callbot.js)
    if (autoreadOn) return true;
    return isWalkieEnabled();
  }

  function setAutoread(on) {
    autoreadOn = !!on;
    saveAutoread(autoreadOn);
    updateAutoreadUI();
  }

  function updateAutoreadUI() {
    try {
      if (!autoreadSwitch) return;
      autoreadSwitch.setAttribute('aria-checked', autoreadOn ? 'true' : 'false');
      autoreadSwitch.textContent = autoreadOn ? '답변 읽어주기: 켜짐' : '답변 읽어주기: 꺼짐';
      autoreadSwitch.setAttribute('aria-label', autoreadOn ? '답변 읽어주기 켜짐' : '답변 읽어주기 꺼짐');
      autoreadSwitch.style.background = autoreadOn ? 'var(--accent-dark, #4338ca)' : 'var(--bg, #f7f7f8)';
      autoreadSwitch.style.color = autoreadOn ? 'var(--on-accent, #fff)' : '';
      autoreadSwitch.style.borderColor = autoreadOn ? 'var(--accent-dark, #4338ca)' : '';
    } catch (e) { /* 무시 */ }
  }

  // 켜는 누름 안에서 소리 재생을 풀어 둔다. 막히면 조용히 넘어간다.
  function unlockAudio() {
    try {
      var AC = window.AudioContext || window.webkitAudioContext;
      if (AC) {
        var ctx = new AC();
        try {
          if (ctx.state === 'suspended' && typeof ctx.resume === 'function') ctx.resume();
        } catch (e) { /* 무시 */ }
        try {
          var rate = ctx.sampleRate || 44100;
          var len = Math.floor(rate * 0.05);
          if (len < 1) len = 1;
          var buf = ctx.createBuffer(1, len, rate);
          var src = ctx.createBufferSource();
          src.buffer = buf;
          src.connect(ctx.destination);
          try { src.start(0); } catch (e2) { /* 무시 */ }
        } catch (e) { /* 무시 */ }
        try {
          setTimeout(function () { try { ctx.close(); } catch (e2) { /* 무시 */ } }, 500);
        } catch (e) { /* 무시 */ }
      }
    } catch (e) { /* 무시 */ }
    try {
      if (!sharedAudio) sharedAudio = new Audio();
      var a = sharedAudio;
      if (activeAudio === a) return;  // 읽는 중이면 이미 풀린 상태
      a.src = 'data:audio/wav;base64,UklGRigAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQAAAAA=';
      try {
        var p = a.play();
        if (p && typeof p.catch === 'function') p.catch(function () { /* 무시 */ });
      } catch (e) { /* 무시 */ }
    } catch (e) { /* 무시 */ }
  }

  function buildAutoreadUI() {
    try {
      autoreadSwitch = document.createElement('button');
      autoreadSwitch.type = 'button';
      autoreadSwitch.id = 'autoreadSwitch';
      autoreadSwitch.setAttribute('role', 'switch');
      autoreadSwitch.style.cssText = 'min-height:44px;padding:0 14px;border:1px solid var(--border, #e5e7eb);border-radius:999px;background:var(--bg, #f7f7f8);cursor:pointer;font-size:0.8125rem;';
      autoreadSwitch.addEventListener('click', function () {
        setAutoread(!autoreadOn);
        unlockAudio();
        try {
          var mic = document.getElementById('micBtn');
          if (mic) mic.focus();
        } catch (e) { /* 무시 */ }
      });
      var slot = document.getElementById('walkieSlot');
      if (slot) {
        slot.appendChild(autoreadSwitch);
      } else {
        var rowEl = document.getElementById('walkieRow');
        if (rowEl) rowEl.appendChild(autoreadSwitch);
      }
      updateAutoreadUI();
    } catch (e) { /* 화면 만들기가 실패해도 듣기는 유지 */ }
  }

  // 처음 방에 들어올 때 불러오는 지난 답장은 읽지 않는다. 방 화면이 첫 조회를 마치면 표시한다.
  function historyReady() {
    try {
      return !!window.__agtHistoryDone;
    } catch (e) { /* 무시 */ }
    return false;
  }

  // 긴 답장을 280자 이하 조각으로 나눈다. 줄바꿈과 문장 끝에서 자르고 최대 4조각까지만 둔다.
  function splitLongText(text) {
    var s = (text || '').replace(/^\s+|\s+$/g, '');
    if (!s) return [];
    if (s.length <= MAX_CHARS) return [s.slice(0, MAX_CHARS)];
    var out = [];
    var rest = s;
    while (rest && out.length < MAX_CHUNKS) {
      rest = rest.replace(/^\s+/, '');
      if (!rest) break;
      if (rest.length <= MAX_CHARS && (rest.length <= CHUNK_MAX || out.length === MAX_CHUNKS - 1)) {
        out.push(rest.slice(0, MAX_CHARS));
        break;
      }
      var limit = CHUNK_MAX;
      if (rest.length < limit) limit = rest.length;
      var head = rest.slice(0, limit);
      var cut = -1;
      for (var i = head.length - 1; i >= 0; i--) {
        var ch = head.charAt(i);
        if (ch === '\n' || ch === '.' || ch === '?' || ch === '!') { cut = i + 1; break; }
        if (ch === '요' || ch === '다') { cut = i + 1; break; }
      }
      if (cut < 120) cut = limit;
      if (cut < 1) cut = limit;
      out.push(rest.slice(0, cut));
      rest = rest.slice(cut);
    }
    return out;
  }

  function fetchChunkBlob(chunkText) {
    return fetch(TTS_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Member-Id': getMemberId() },
      body: JSON.stringify({ text: chunkText })
    }).then(function (res) {
      if (res.ok) return res.blob();
      var err = new Error('tts fail');
      err.status = res.status;
      throw err;
    });
  }

  function finishReading(natural) {
    var wasAuto = activeIsAuto;
    var doneText = lastAutoText;
    cleanupActive();
    clearPrefetch();
    if (activeBtn) resetBtn(activeBtn);
    activeBtn = null;
    activeChunks = null;
    activeIndex = 0;
    activeIsAuto = false;
    loading = false;
    if (natural) enterPending = false;
    // 끝까지 스스로 다 읽었을 때만 손 안 쓰는 모드에 알린다. 끊기·오류·차단은 알리지 않는다.
    if (natural && wasAuto) {
      try {
        if (typeof window.__handsfreeTtsEnd === 'function') window.__handsfreeTtsEnd(true, doneText);
      } catch (e) { /* 무시 */ }
    }
  }

  function failReading(btn, gen, isAuto, err) {
    if (gen !== speechGen) return;
    finishReading(false);
    if (isAuto) return;
    if (err instanceof TypeError) {
      flashBtn(btn, '인터넷 연결을 확인해 주세요');
      return;
    }
    if (err && err.status === 429) {
      flashBtn(btn, '요청이 많아요 잠시 뒤에');
      return;
    }
    if (err && err.message === '소리가 비어 있어요') {
      flashBtn(btn, '소리가 비어 있어요');
      return;
    }
    flashBtn(btn, '지금은 듣기를 쓸 수 없어요');
  }

  // 다음 조각을 미리 요청해 둔다. 끊기 세대가 바뀌면 버린다.
  function prefetchNext(chunks, nextIdx, gen) {
    if (nextIdx < 0 || nextIdx >= chunks.length) return;
    var myGen = gen;
    fetchChunkBlob(chunks[nextIdx]).then(function (blob) {
      if (myGen !== speechGen) return;
      if (!blob || !blob.size) return;
      if (prefetchIdx !== -1) return;
      try {
        prefetchUrl = URL.createObjectURL(blob);
        prefetchIdx = nextIdx;
      } catch (e) { /* 무시 */ }
    }).catch(function () { /* 미리 요청 실패는 조용히 넘긴다 */ });
  }

  function playChunkUrl(url, chunks, idx, btn, gen, isAuto) {
    if (gen !== speechGen) {
      try { URL.revokeObjectURL(url); } catch (e) { /* 무시 */ }
      return;
    }
    var audio = sharedAudio || new Audio();
    audio.src = url;
    activeUrl = url;
    activeAudio = audio;
    loading = false;
    if (btn) {
      btn.textContent = LABEL_STOP;
      btn.disabled = false;
    }
    prefetchNext(chunks, idx + 1, gen);
    audio.onended = function () {
      if (gen !== speechGen) return;
      playNextChunk(gen);
    };
    audio.onerror = function () {
      if (gen !== speechGen) return;
      if (isAuto) {
        finishReading(false);
        return;
      }
      finishReading(false);
      flashBtn(btn, '재생에 실패했어요');
    };
    var played = null;
    try {
      played = audio.play();
    } catch (e) {
      if (isAuto) {
        if (enterPending) {
          finishReading(false);
          enterPending = false;
          pendingEnterText = enterText;
          showEnterListenBtn();
          return;
        }
        finishReading(false);
        try { if (typeof window.__handsfreeBlocked === 'function') window.__handsfreeBlocked(); } catch (e2) { /* 무시 */ }
        return;
      }
      finishReading(false);
      flashBtn(btn, '재생에 실패했어요');
      return;
    }
    if (played && typeof played.catch === 'function') {
      played.catch(function () {
        if (gen !== speechGen) return;
        if (isAuto) {
          if (enterPending) {
            finishReading(false);
            enterPending = false;
            pendingEnterText = enterText;
            showEnterListenBtn();
            return;
          }
          finishReading(false);
          try { if (typeof window.__handsfreeBlocked === 'function') window.__handsfreeBlocked(); } catch (e2) { /* 무시 */ }
          return;
        }
        finishReading(false);
        flashBtn(btn, '재생에 실패했어요');
      });
    }
  }

  function playNextChunk(gen) {
    if (gen !== speechGen) return;
    cleanupActive();
    activeIndex++;
    if (!activeChunks || activeIndex >= activeChunks.length) {
      finishReading(true);
      return;
    }
    var btn = activeBtn;
    var isAuto = activeIsAuto;
    if (prefetchIdx === activeIndex && prefetchUrl) {
      var url = prefetchUrl;
      prefetchUrl = null;
      prefetchIdx = -1;
      playChunkUrl(url, activeChunks, activeIndex, btn, gen, isAuto);
      return;
    }
    var chunks = activeChunks;
    var idx = activeIndex;
    fetchChunkBlob(chunks[idx]).then(function (blob) {
      if (gen !== speechGen) return;
      if (!blob || !blob.size) throw new Error('소리가 비어 있어요');
      var url2 = URL.createObjectURL(blob);
      playChunkUrl(url2, chunks, idx, btn, gen, isAuto);
    }).catch(function (err) {
      failReading(btn, gen, isAuto, err);
    });
  }

  // 조각 목록을 처음부터 읽는다. 재생 시작과 함께 다음 조각을 미리 요청한다.
  function startReading(chunks, btn, isAuto, gen) {
    activeChunks = chunks;
    activeIndex = 0;
    activeBtn = btn || null;
    activeIsAuto = !!isAuto;
    loading = true;
    if (btn) {
      btn.textContent = LABEL_LOADING;
      btn.disabled = true;
    }
    fetchChunkBlob(chunks[0]).then(function (blob) {
      if (gen !== speechGen) return;
      if (!blob || !blob.size) throw new Error('소리가 비어 있어요');
      var url = URL.createObjectURL(blob);
      playChunkUrl(url, chunks, 0, btn, gen, isAuto);
    }).catch(function (err) {
      failReading(btn, gen, isAuto, err);
    });
  }

  function queueNewReading(text, btn, isAuto) {
    var chunks = splitLongText(text);
    if (!chunks.length) {
      if (!isAuto) flashBtn(btn, '들을 내용이 없어요');
      return;
    }
    stopAllSpeech();
    var gen = speechGen;
    startReading(chunks, btn || null, isAuto, gen);
  }

  window.queueWalkieTts = function (text, btn) {
    try {
      if (!shouldAutoRead()) return;
      if (!historyReady()) return;
      var clean = (text || '').replace(/^\s+|\s+$/g, '');
      if (!clean) return;
      lastAutoText = clean;
      queueNewReading(clean, btn || null, true);
    } catch (e) { /* 무시 */ }
  };

  // 입장 안내가 막혔을 때 입력줄 위에 한 줄 버튼을 보인다. 자동읽기는 끄지 않는다.
  function removeEnterListenBtn() {
    try {
      var b = document.getElementById('enterListenBtn');
      if (b && b.parentNode) b.parentNode.removeChild(b);
    } catch (e) { /* 무시 */ }
  }

  function showEnterListenBtn() {
    try {
      if (!pendingEnterText) return;
      if (document.getElementById('enterListenBtn')) return;
      var rowEl = document.getElementById('row');
      if (!rowEl || !rowEl.parentNode) return;
      var b = document.createElement('button');
      b.type = 'button';
      b.id = 'enterListenBtn';
      b.textContent = '🔊 눌러서 안내 듣기';
      b.style.cssText = 'display:block;min-height:44px;margin:8px 16px 0;padding:0 14px;border:1px solid var(--border, #e5e7eb);border-radius:8px;background:var(--surface, #fff);cursor:pointer;font-size:0.875rem;';
      b.addEventListener('click', function () {
        try { unlockAudio(); } catch (e) { /* 무시 */ }
        var t = pendingEnterText;
        pendingEnterText = '';
        removeEnterListenBtn();
        if (t) queueNewReading(t, null, true);
      });
      rowEl.parentNode.insertBefore(b, rowEl);
    } catch (e) { /* 화면 만들기가 실패해도 읽기는 유지 */ }
  }

  // 방에 처음 들어와 지난 글을 다 받은 직후 한 번, 마지막 AI 답을 읽는다.
  window.speakOnEnter = function (text) {
    if (enterDone) return;
    enterDone = true;
    try {
      if (!shouldAutoRead()) return;
      if (window.__agtOnCall) return;
      var clean = (text || '').replace(/^\s+|\s+$/g, '');
      if (!clean) return;
      lastAutoText = clean;
      queueNewReading(clean, null, true);
      enterText = clean;
      enterPending = true;
    } catch (e) { /* 무시 */ }
  };

  // 첫 누름이 입력칸·보내기·마이크 밖이면 대기 중인 입장 글을 읽는다.
  document.addEventListener('pointerdown', function (ev) {
    try {
      if (!pendingEnterText) return;
      var t = ev && ev.target;
      if (!t || typeof t.closest !== 'function') return;
      if (t.closest('#input') || t.closest('#sendBtn') || t.closest('#micBtn')) return;
      try { unlockAudio(); } catch (e2) { /* 무시 */ }
      var txt = pendingEnterText;
      pendingEnterText = '';
      removeEnterListenBtn();
      if (txt) queueNewReading(txt, null, true);
    } catch (e) { /* 무시 */ }
  }, true);

  window.speakAiText = function (text, btn) {
    if (!btn) return;
    // 읽던 말풍선의 버튼을 다시 누르면 멈춘다. 자동 읽기도 함께 멈춘다.
    if (activeBtn === btn && (activeAudio || loading)) {
      stopAllSpeech();
      return;
    }
    if (loading) return;
    var clean = (text || '').replace(/^\s+|\s+$/g, '');
    if (!clean) {
      flashBtn(btn, '들을 내용이 없어요');
      return;
    }
    queueNewReading(clean, btn, false);
  };

  window.stopAllSpeech = stopAllSpeech;
  // 보내기·🎤 누름마다 소리를 다시 풀어 둔다(새로고침 뒤 첫 답장이 막히지 않게). 읽어주기가 켜졌을 때만.
  window.unlockSpeech = function () { try { if (shouldAutoRead()) unlockAudio(); } catch (e) { /* 무시 */ } };
  window.queueAutoRead = window.queueWalkieTts;
  window.setAutoreadMode = setAutoread;
  window.isAutoreadOn = function () { return autoreadOn; };

  // 입력창에 첫 글자가 들어오면 읽던 소리를 끊는다.
  function bindInputStop() {
    try {
      var inp = document.getElementById('input');
      if (!inp) return;
      var prevLen = inp.value ? inp.value.length : 0;
      inp.addEventListener('input', function () {
        try {
          var len = inp.value ? inp.value.length : 0;
          if (len > 0 && (prevLen === 0 || len === 1)) {
            if (typeof window.stopAllSpeech === 'function') window.stopAllSpeech();
            // 입장 대기는 글자를 치기 시작하면 버린다.
            pendingEnterText = '';
            enterText = '';
            removeEnterListenBtn();
          }
          prevLen = len;
        } catch (e) { /* 무시 */ }
      });
    } catch (e) { /* 무시 */ }
  }

  buildAutoreadUI();
  bindInputStop();
})();
