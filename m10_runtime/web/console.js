(() => {
  'use strict';
  const $ = (id) => document.getElementById(id);
  const fragment = new URLSearchParams(location.hash.slice(1));
  if (fragment.get('token')) {
    sessionStorage.setItem('m10-control-token', fragment.get('token'));
    history.replaceState(null, '', location.pathname);
  }
  let token = sessionStorage.getItem('m10-control-token') || '';
  let ws, holdTimer, player, poll;
  $('token').value = token;
  function message(value) { $('message').textContent = value || ''; }
  async function api(path, body) {
    const response = await fetch(path, {
      method: body === undefined ? 'GET' : 'POST',
      headers: { 'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    const value = await response.json();
    if (!response.ok) throw new Error(value.detail || `HTTP ${response.status}`);
    return value;
  }
  function send(action) {
    if (ws?.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ action }));
    else if (action !== 'stop') message('遥控连接未就绪');
  }
  function release() {
    clearInterval(holdTimer); holdTimer = null; send('stop');
  }
  function hold(action) {
    clearInterval(holdTimer); send(action);
    holdTimer = setInterval(() => send(action), 100);
  }
  async function status() {
    try {
      const value = await api('/api/runtime/status');
      $('mode').textContent = value.profile === 'demo' ? '电脑演示 · 模拟电机' : value.profile + ' · 硬件模式';
      $('status').textContent = JSON.stringify(value, null, 2);
      $('stream-message').textContent = value.media.preview_received ? '已收到图传输出' : (value.media.running ? '图传进程运行中，等待画面' : '图传未启动');
    } catch (error) { message(error.message); }
  }
  async function pair() {
    release(); ws?.close();
    token = $('token').value.trim();
    sessionStorage.setItem('m10-control-token', token);
    await api('/api/runtime/pair', {});
    ws = new WebSocket((location.protocol === 'https:' ? 'wss://' : 'ws://') + location.host + '/control/ws', ['m10', 'm10.token.' + token]);
    ws.onopen = () => message('已连接');
    ws.onmessage = (event) => {
      const value = JSON.parse(event.data);
      if (value.status === 'error') { clearInterval(holdTimer); holdTimer = null; message(value.message); }
    };
    ws.onclose = () => { clearInterval(holdTimer); holdTimer = null; message('遥控连接已断开，请重新连接'); };
    clearInterval(poll); poll = setInterval(status, 1000); await status();
  }
  $('pair-form').onsubmit = (event) => { event.preventDefault(); pair().catch((e) => message(e.message)); };
  document.querySelectorAll('[data-action]').forEach((button) => {
    button.onpointerdown = (event) => { event.preventDefault(); button.setPointerCapture(event.pointerId); hold(button.dataset.action); };
    button.onpointerup = release; button.onpointercancel = release; button.onlostpointercapture = release;
  });
  window.addEventListener('blur', release);
  document.addEventListener('visibilitychange', () => { if (document.hidden) release(); });
  $('stop').onclick = () => { release(); api('/control', { action: 'stop' }).catch((e) => message(e.message)); };
  $('speed').oninput = () => { $('speed-label').textContent = $('speed').value + '%'; };
  $('speed').onchange = () => api('/set_speed', { speed: Number($('speed').value) }).catch((e) => message(e.message));
  $('emergency').onclick = () => { release(); api('/api/runtime/emergency_stop', {}).then(status).catch((e) => message(e.message)); };
  $('clear').onclick = () => api('/api/runtime/clear_emergency_stop', {}).then(status).catch((e) => message(e.message));
  $('reconnect').onclick = () => { release(); api('/api/runtime/reconnect', {}).then(status).catch((e) => message(e.message)); };
  ['待机', '呼吸', '开心', '兴奋', '调皮', '睡眠', '好奇', '聆听', '思考', '低电量'].forEach((name, index) => {
    const button = document.createElement('button'); button.textContent = name;
    button.onclick = () => api('/api/v1/state', { state: index + 1 }).catch((e) => message(e.message));
    $('faces').append(button);
  });
  function loadHls() {
    if (window.Hls) return Promise.resolve();
    return new Promise((resolve, reject) => {
      const script = document.createElement('script');
      script.src = 'https://cdn.jsdelivr.net/npm/hls.js@1.6.13/dist/hls.min.js';
      script.onload = resolve; script.onerror = () => reject(new Error('hls.js 无法加载，请检查网络')); document.head.append(script);
    });
  }
  $('stream-start').onclick = async () => {
    try {
      await api('/start_stream', {}); const video = $('preview'); video.hidden = false;
      player?.destroy();
      if (video.canPlayType('application/vnd.apple.mpegurl')) video.src = '/stream/index.m3u8';
      else { await loadHls(); if (!window.Hls.isSupported()) throw new Error('浏览器不支持 HLS 播放'); player = new Hls(); player.loadSource('/stream/index.m3u8'); player.attachMedia(video); }
      await status();
    } catch (error) { message(error.message); }
  };
  $('stream-stop').onclick = async () => {
    try { await api('/stop_stream', {}); player?.destroy(); $('preview').removeAttribute('src'); $('preview').load(); $('preview').hidden = true; await status(); }
    catch (error) { message(error.message); }
  };
  fetch('/health').then((r) => r.json()).then((v) => { $('mode').textContent = v.simulated ? '电脑演示 · 模拟电机' : v.profile + ' · 硬件模式'; });
  if (token) pair().catch((e) => message(e.message));
})();
