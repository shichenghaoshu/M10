async function fetchStatus() {
  const response = await fetch("/api/status");
  if (!response.ok) {
    throw new Error(`Status request failed: ${response.status}`);
  }
  return response.json();
}

function renderStatus(status) {
  const hardware = status.hardware || {};
  const state = status.state_machine || {};
  const server = status.server || {};
  const battery = status.battery || {};

  const cards = [
    ["Robot State", state.state || "unknown", state.reason || ""],
    ["ESP32", hardware.esp32?.status || "unknown", hardware.esp32?.reason || hardware.esp32?.port || ""],
    ["Serial", hardware.serial?.status || "unknown", (hardware.serial?.devices || []).join(", ")],
    ["Camera", hardware.camera?.status || "unknown", hardware.camera?.reason || (hardware.camera?.devices || []).join(", ")],
    ["Display", hardware.display?.status || "unknown", hardware.display?.backend || hardware.display?.reason || ""],
    ["Audio In", hardware.audio_input?.status || "unknown", hardware.audio_input?.reason || ""],
    ["Audio Out", hardware.audio_output?.status || "unknown", hardware.audio_output?.reason || ""],
    ["Battery", battery.status || "unknown", battery.reason || ""],
    ["Server", server.status || "unknown", server.reason || server.base_url || ""],
  ];

  const grid = document.getElementById("status-grid");
  grid.innerHTML = cards
    .map(
      ([title, value, detail]) => `
        <article class="status-card">
          <h3>${title}</h3>
          <strong>${value}</strong>
          <div>${detail || "&nbsp;"}</div>
        </article>
      `,
    )
    .join("");

  document.getElementById("log-output").textContent = (status.logs || []).join("\n") || "No logs yet.";
}

async function runCommand(endpoint) {
  const output = document.getElementById("command-output");
  output.textContent = `POST ${endpoint}\nRunning...`;
  try {
    const response = await fetch(endpoint, { method: "POST" });
    const data = await response.json();
    output.textContent = JSON.stringify(data, null, 2);
    await refreshPage();
  } catch (error) {
    output.textContent = `Command failed: ${error.message}`;
  }
}

async function refreshPage() {
  try {
    const status = await fetchStatus();
    renderStatus(status);
  } catch (error) {
    document.getElementById("command-output").textContent = `Refresh failed: ${error.message}`;
  }
}

document.getElementById("refresh-button").addEventListener("click", refreshPage);
document.querySelectorAll("[data-endpoint]").forEach((button) => {
  button.addEventListener("click", () => runCommand(button.dataset.endpoint));
});

refreshPage();
setInterval(refreshPage, 5000);
