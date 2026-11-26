(() => {
  "use strict";

  const videos = [document.querySelector("#face-a"), document.querySelector("#face-b")];
  const bootMark = document.querySelector("#boot-mark");
  const indicator = document.querySelector("#connection-indicator");
  const connectionLabel = document.querySelector("#connection-label");
  const currentLabel = document.querySelector("#current-label");
  const stateButtons = document.querySelector("#state-buttons");
  const query = new URLSearchParams(location.search);
  const uiToken = query.get("token") || "";
  let activeIndex = 0;
  let currentStateId = null;
  let states = [];
  let socket = null;
  let reconnectTimer = null;
  let fallbackTimer = null;
  let reconnectDelay = 500;
  let wakeLock = null;

  function setConnection(online) {
    indicator.classList.toggle("offline", !online);
    connectionLabel.textContent = online ? "显示服务已连接" : "连接中断 · 自动重试";
  }

  async function fetchCurrentState() {
    try {
      const response = await fetch("/api/v1/state", { cache: "no-store" });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      await playState(await response.json(), currentStateId === null);
      return true;
    } catch (_) {
      return false;
    }
  }

  function startHttpFallback() {
    if (fallbackTimer) return;
    fetchCurrentState();
    fallbackTimer = window.setInterval(fetchCurrentState, 1000);
  }

  function stopHttpFallback() {
    if (!fallbackTimer) return;
    window.clearInterval(fallbackTimer);
    fallbackTimer = null;
  }

  function updateDebugSelection(state) {
    currentLabel.textContent = `${String(state.id).padStart(2, "0")} · ${state.name}`;
    document.querySelectorAll(".state-button").forEach((button) => {
      button.classList.toggle("active", Number(button.dataset.state) === state.id);
    });
  }

  async function playState(message, initial = false) {
    if (!message?.state) return;
    const state = message.state;
    updateDebugSelection(state);
    if (state.id === currentStateId) return;

    const nextIndex = initial ? activeIndex : 1 - activeIndex;
    const nextVideo = videos[nextIndex];
    const previousVideo = videos[activeIndex];
    const transition = Number.isFinite(message.transition_ms) ? message.transition_ms : 140;
    document.documentElement.style.setProperty("--transition-ms", `${transition}ms`);

    await new Promise((resolve) => {
      let settled = false;
      const finish = () => {
        if (settled) return;
        settled = true;
        resolve();
      };
      nextVideo.addEventListener("canplay", finish, { once: true });
      nextVideo.src = state.video_url;
      nextVideo.load();
      window.setTimeout(finish, 1800);
    });

    try {
      nextVideo.currentTime = 0;
      await nextVideo.play();
    } catch (_) {
      // Muted autoplay should succeed in kiosk mode; a touch/keypress retries it.
    }

    nextVideo.classList.add("active");
    if (nextVideo !== previousVideo) {
      previousVideo.classList.remove("active");
      window.setTimeout(() => {
        previousVideo.pause();
        previousVideo.removeAttribute("src");
        previousVideo.load();
      }, transition + 80);
    }

    activeIndex = nextIndex;
    currentStateId = state.id;
    bootMark.classList.add("ready");
  }

  function buildDebugButtons() {
    stateButtons.replaceChildren();
    states.forEach((state) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "state-button";
      button.dataset.state = state.id;
      button.innerHTML = `<span>${String(state.id).padStart(2, "0")}</span><span>${state.name}</span>`;
      button.addEventListener("click", () => sendState(state.id));
      stateButtons.append(button);
    });
  }

  async function sendState(state) {
    try {
      const response = await fetch("/api/v1/state", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(uiToken ? { Authorization: `Bearer ${uiToken}` } : {}),
        },
        body: JSON.stringify({ state }),
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
    } catch (_) {
      setConnection(false);
    }
  }

  function connect() {
    clearTimeout(reconnectTimer);
    const protocol = location.protocol === "https:" ? "wss:" : "ws:";
    const tokenQuery = uiToken ? `?token=${encodeURIComponent(uiToken)}` : "";
    socket = new WebSocket(`${protocol}//${location.host}/ws${tokenQuery}`);
    socket.addEventListener("open", () => {
      reconnectDelay = 500;
      stopHttpFallback();
      setConnection(true);
    });
    socket.addEventListener("message", (event) => {
      try {
        const message = JSON.parse(event.data);
        if (message.type === "state") playState(message, currentStateId === null);
      } catch (_) {
        // Ignore malformed messages and keep the last valid face visible.
      }
    });
    socket.addEventListener("close", () => {
      setConnection(false);
      startHttpFallback();
      reconnectTimer = window.setTimeout(connect, reconnectDelay);
      reconnectDelay = Math.min(reconnectDelay * 1.7, 8000);
    });
    socket.addEventListener("error", () => socket.close());
  }

  async function requestWakeLock() {
    if (!("wakeLock" in navigator)) return;
    try { wakeLock = await navigator.wakeLock.request("screen"); } catch (_) { /* kiosk may manage this */ }
  }

  function toggleDebug(force) {
    const open = typeof force === "boolean" ? force : !document.body.classList.contains("debug-open");
    document.body.classList.toggle("debug-open", open);
  }

  async function enterFullscreen() {
    if (!document.fullscreenElement) {
      try { await document.documentElement.requestFullscreen(); } catch (_) { /* kiosk already fullscreen */ }
    }
    toggleDebug(false);
  }

  async function initialize() {
    try {
      const response = await fetch("/api/v1/states", { cache: "no-store" });
      const payload = await response.json();
      states = payload.states;
      buildDebugButtons();
    } catch (_) {
      setConnection(false);
    }

    if (query.get("debug") === "1") toggleDebug(true);
    await fetchCurrentState();
    connect();
    requestWakeLock();
  }

  document.querySelector("#close-debug").addEventListener("click", () => toggleDebug(false));
  document.querySelector("#fullscreen-button").addEventListener("click", enterFullscreen);
  document.addEventListener("dblclick", enterFullscreen);
  document.addEventListener("pointerdown", () => videos[activeIndex].play().catch(() => {}), { passive: true });
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") {
      videos[activeIndex].play().catch(() => {});
      if (!wakeLock) requestWakeLock();
    }
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "`" || event.key.toLowerCase() === "d") toggleDebug();
    if (event.key.toLowerCase() === "f") enterFullscreen();
    if (event.key === "Escape") toggleDebug(false);
    if (/^[0-9]$/.test(event.key)) sendState(event.key === "0" ? 10 : Number(event.key));
  });

  initialize();
})();
