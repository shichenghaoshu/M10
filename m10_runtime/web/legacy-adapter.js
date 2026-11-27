// M10 adapter; the vendored Dreamupers HTML remains byte-for-byte unchanged.
const m10Fragment = new URLSearchParams(location.hash.slice(1));
if (m10Fragment.get('token')) {
  sessionStorage.setItem('m10-control-token', m10Fragment.get('token'));
  history.replaceState(null, '', location.pathname);
}
let m10HoldTimer = null;
function m10Release(sendStop) {
  clearInterval(m10HoldTimer);
  m10HoldTimer = null;
  if (sendStop && typeof sendControl === 'function') sendControl('stop');
}
function m10Hold(action) {
  m10Release(false);
  const currentSocket = ws;
  sendControl(action);
  m10HoldTimer = setInterval(() => {
    if (document.hidden || ws !== currentSocket || ws.readyState !== WebSocket.OPEN) return m10Release(false);
    sendControl(action);
  }, 100);
}
const m10Fetch = window.fetch.bind(window);
window.fetch = (url, options = {}) => {
  const destination = new URL(url, location.href);
  if (destination.origin === location.origin) {
    options.headers = new Headers(options.headers || {});
    options.headers.set('Authorization', 'Bearer ' + sessionStorage.getItem('m10-control-token'));
  }
  return m10Fetch(url, options);
};
window.addEventListener('blur', () => m10Release(true));
window.addEventListener('pointerup', () => m10Release(true));
window.addEventListener('pointercancel', () => m10Release(true));
document.addEventListener('visibilitychange', () => { if (document.hidden) m10Release(true); });
window.addEventListener('DOMContentLoaded', () => {
  for (const id of ['bus_voltage', 'current', 'power', 'battery_percent', 'cpu_percent', 'mem_percent', 'cpu_temp']) {
    const node = document.getElementById(id);
    if (node) node.textContent = '—';
  }
  for (const id of ['laser', 'open-sleep-modal']) {
    const node = document.getElementById(id);
    if (node) { node.disabled = true; node.title = '当前运行器未接入此功能'; }
  }
  window.fetch('/health').then((reply) => reply.json()).then((health) => {
    const banner = document.createElement('div');
    banner.style.cssText = 'padding:12px;background:#183c31;color:white;font:14px system-ui;text-align:center';
    banner.textContent = health.simulated ? '电脑演示 · 模拟电机 · 未连接传感器显示 —' : health.profile + ' · 硬件模式';
    const back = document.createElement('a'); back.href = '/'; back.textContent = '　返回 M10 控制台';
    back.style.textDecoration = 'underline'; banner.append(back); document.body.prepend(banner);
  });
  window.fetch('/api/runtime/pair', { method: 'POST' });
});
