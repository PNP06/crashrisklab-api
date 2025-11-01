"use strict";

// TODO: Remplacer par l'URL exacte de votre service Render
// Exemple: const API_URL = "https://crashrisklab.onrender.com";
const API_URL = "https://<TON_SERVICE_RENDER>.onrender.com";

const els = {
  form: document.getElementById("run-form"),
  btn: document.getElementById("run-btn"),
  console: document.getElementById("console"),
  tbody: document.getElementById("results-body"),
  symbols: document.getElementById("symbols"),
  timeframe: document.getElementById("timeframe"),
  lookback: document.getElementById("lookback"),
  horizon: document.getElementById("horizon"),
  crashDropInput: document.getElementById("crash_drop_input"),
  apiKey: document.getElementById("api_key"),
  explainBtn: document.getElementById("explain-btn"),
  modal: document.getElementById("modal"),
  modalClose: document.getElementById("close-modal"),
};

function log(msg) {
  const ts = new Date().toISOString().replace("T", " ").replace("Z", "");
  els.console.textContent += `[${ts}] ${msg}\n`;
  els.console.scrollTop = els.console.scrollHeight;
}

function clearTable() {
  els.tbody.innerHTML = "";
}

function fmtPct(p) {
  if (typeof p !== "number" || !isFinite(p)) return "n/a";
  return (p * 100).toFixed(2) + " %";
}
function fmt3(x) {
  if (typeof x !== "number" || !isFinite(x)) return "nan";
  return x.toFixed(3);
}
function fmt4(x) {
  if (typeof x !== "number" || !isFinite(x)) return "nan";
  return x.toFixed(4);
}

function renderResults(report) {
  clearTable();
  if (!report || !report.symbols) return;
  const policy = report.policy_hint || {};
  Object.keys(report.symbols).forEach((sym) => {
    const R = report.symbols[sym];
    const m = R.metrics || {};
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${sym}</td>
      <td>${fmtPct(R.p_crash)}</td>
      <td>${fmt3(R.confidence)}</td>
      <td>${fmt3(m.auc)}</td>
      <td>${fmt3(m.prauc)}</td>
      <td>${fmt4(m.brier)}</td>
      <td>${policy[sym] || ""}</td>
    `;
    els.tbody.appendChild(tr);
  });
}

async function callRun(body, headers = {}) {
  const url = `${API_URL}/run`;
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...headers },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const ct = res.headers.get("content-type") || "";
    let detail = await (ct.includes("application/json") ? res.json() : res.text());
    throw new Error(`HTTP ${res.status}: ${typeof detail === "string" ? detail : JSON.stringify(detail)}`);
  }
  return res.json();
}

function startProgressLog() {
  const steps = ["Fetching", "Features", "Training", "Calibrating", "Evaluating", "Predicting"];
  let i = 0;
  const id = setInterval(() => {
    if (i >= steps.length) return;
    log(steps[i] + " …");
    i += 1;
  }, 1200);
  return id;
}

els.form.addEventListener("submit", async (e) => {
  e.preventDefault();
  els.btn.disabled = true;
  log("Préparation de la requête /run …");
  let progressId = startProgressLog();
  try {
    const symbols = els.symbols.value.split(",").map((s) => s.trim().toUpperCase()).filter(Boolean);
    const timeframe = els.timeframe.value.trim();
    const lookback = parseInt(els.lookback.value, 10);
    const horizon = parseInt(els.horizon.value, 10);
    const rawDrop = parseFloat(els.crashDropInput.value);
    const crash_drop = isFinite(rawDrop) ? (rawDrop > 1 ? rawDrop / 100.0 : rawDrop) : 0.2;

    const body = { symbols, timeframe, lookback, horizon, crash_drop, mode: "basic" };
    log(`Envoi: symbols=${symbols.join(",")} tf=${timeframe} lookback=${lookback} H=${horizon} drop=${crash_drop}`);

    const headers = {};
    const key = els.apiKey.value.trim();
    if (key) headers["X-API-Key"] = key;

    const report = await callRun(body, headers);
    clearInterval(progressId);
    log("Réponse reçue. Rendu des résultats …");
    renderResults(report);
    log("Fini.");
  } catch (err) {
    clearInterval(progressId);
    console.error(err);
    log(`ERREUR: ${err.message || err.toString()}`);
  } finally {
    els.btn.disabled = false;
  }
});

// Modal handling
els.explainBtn.addEventListener("click", () => {
  els.modal.removeAttribute("hidden");
});
els.modalClose.addEventListener("click", () => {
  els.modal.setAttribute("hidden", "hidden");
});
els.modal.addEventListener("click", (e) => {
  if (e.target === els.modal) {
    els.modal.setAttribute("hidden", "hidden");
  }
});

