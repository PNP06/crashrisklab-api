// app.js (ES module)
import { featureExplanations } from "./reverse_explain.js";

// URL de l'API Render (mise à jour)
// Service: crashrisklab-api (Render)
export const API_URL = "https://crashrisklab-api.onrender.com";

const els = {
  // Crash tab
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
  // Tabs
  tabBtnCrash: document.getElementById("tab-btn-crash"),
  tabBtnReverse: document.getElementById("tab-btn-reverse"),
  tabCrash: document.getElementById("tab-crash"),
  tabReverse: document.getElementById("tab-reverse"),\n  downloadBtn: document.getElementById("download-report"),
  // Reverse tab
  revSymbol: document.getElementById("rev_symbol"),
  revRunBtn: document.getElementById("rev-run-btn"),
  revStatus: document.getElementById("rev_status"),
  revError: document.getElementById("rev_error"),
  revLoading: document.getElementById("rev_loading"),
  revBody: document.getElementById("reverse-body"),
  revChartCanvas: document.getElementById("reverse-chart"),\n  revCopyBtn: document.getElementById("rev-copy-btn"),
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

// Tabs handling
function showTab(which) {
  if (which === "crash") {
    els.tabCrash.hidden = false;
    els.tabReverse.hidden = true;
    els.tabBtnCrash.classList.add("active");
    els.tabBtnReverse.classList.remove("active");
  } else {
    els.tabCrash.hidden = true;
    els.tabReverse.hidden = false;
    els.tabBtnCrash.classList.remove("active");
    els.tabBtnReverse.classList.add("active");
  }
}
if (els.tabBtnCrash && els.tabBtnReverse) {
  els.tabBtnCrash.addEventListener("click", () => showTab("crash"));
  els.tabBtnReverse.addEventListener("click", () => showTab("reverse"));
}

// Reverse Model Viewer
let revChart = null;

function setReverseLoading(on, msg = "Chargement...") {
  els.revLoading.hidden = !on;
  els.revStatus.textContent = on ? msg : "";
  els.revError.hidden = true;
  if (on) els.revError.textContent = "";
}

function setReverseError(message) {
  els.revError.hidden = false;
  els.revError.textContent = message;
  els.revStatus.textContent = "";
  els.revLoading.hidden = true;
}

function renderReverseTable(features) {
  els.revBody.innerHTML = "";
  for (const f of features) {
    const tr = document.createElement("tr");
    const explain = f.explain || featureExplanations[f.name] || "(non documente)";
    const coefStr = typeof f.coef === "number" && isFinite(f.coef) ? f.coef.toFixed(3) : "n/a";
    const orStr = typeof f.or_at_1 === "number" && isFinite(f.or_at_1) ? f.or_at_1.toFixed(3) : "n/a";
    const scoreStr = typeof f.score === "number" && isFinite(f.score) ? f.score.toFixed(4) : "n/a";
    tr.innerHTML = `
      <td>${f.name}</td>
      <td>${coefStr}</td>
      <td>${orStr}</td>
      <td>${scoreStr}</td>
      <td>${explain}</td>
    `;
    els.revBody.appendChild(tr);
  }
}

function renderReverseChart(features) {
  const labels = features.map(f => f.name);
  const scores = features.map(f => (typeof f.score === "number" ? f.score : 0));
  const colors = features.map(f => (typeof f.coef === "number" && f.coef >= 0 ? "#16a34a" : "#dc2626"));

  if (revChart) {
    revChart.destroy();
    revChart = null;
  }
  const ctx = els.revChartCanvas.getContext("2d");
  revChart = new Chart(ctx, {
    type: "bar",
    data: {
      labels,
      datasets: [
        {
          label: "Score",
          data: scores,
          backgroundColor: colors,
        },
      ],
    },
    options: {
      indexAxis: "y",
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        x: { title: { display: true, text: "Score" } },
        y: { title: { display: true, text: "Feature" } },
      },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: (ctx) => `Score: ${ctx.parsed.x.toFixed ? ctx.parsed.x.toFixed(4) : ctx.parsed.x}`,
          },
        },
      },
    },
  });
}

async function runReverseAnalysis() {
  try {
    const symbol = (els.revSymbol.value || "ETH/USDT").trim().toUpperCase();
    // Reuse horizon/crash_drop from main inputs
    const horizon = parseInt(els.horizon.value, 10) || 10;
    const rawDrop = parseFloat(els.crashDropInput.value);
    const crash_drop = isFinite(rawDrop) ? (rawDrop > 1 ? rawDrop / 100.0 : rawDrop) : 0.2;

    setReverseLoading(true, "Calcul du reverse en cours...");

    const body = { symbol, horizon, crash_drop, top_k: 10 };
    const headers = { "Content-Type": "application/json" };
    const key = els.apiKey.value.trim();
    if (key) headers["X-API-Key"] = key;

    const res = await fetch(`${API_URL}/v1/reverse`, {
      method: "POST",
      headers,
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      const ct = res.headers.get("content-type") || "";
      const detail = await (ct.includes("application/json") ? res.json() : res.text());
      throw new Error(`HTTP ${res.status}: ${typeof detail === "string" ? detail : JSON.stringify(detail)}`);
    }
    const payload = await res.json();
    const features = Array.isArray(payload.features) ? payload.features : [];
    setReverseLoading(false);
    els.revStatus.textContent = payload.explain || `Modele: ${payload.model || "n/a"}`;

    renderReverseTable(features);
    renderReverseChart(features);
  } catch (err) {
    setReverseError(err.message || String(err));
  }
}

if (els.revRunBtn) {
  els.revRunBtn.addEventListener("click", runReverseAnalysis);\n}\n\nif (els.revCopyBtn) {\n  els.revCopyBtn.addEventListener("click", () => {\n    const rows = Array.from(els.revBody.querySelectorAll("tr")).map(tr =>\n      Array.from(tr.children).map(td => td.textContent.trim()).join("\t")\n    );\n    const header = ["Feature","Coefficient","OR@1","Score","Source","Explication"].join("\t");\n    const txt = [header, ...rows].join("\n");\n    navigator.clipboard.writeText(txt).catch(()=>{});\n  });
}

\nif (els.downloadBtn) {\n  els.downloadBtn.addEventListener('click', async () => {\n    try {\n      const res = await fetch(${API_URL}/last_report);\n      if(!res.ok) throw new Error(HTTP );\n      const data = await res.json();\n      const blob = new Blob([JSON.stringify(data,null,2)], {type:'application/json'});\n      const url = URL.createObjectURL(blob);\n      const a = document.createElement('a');\n      a.href = url; a.download = 'report.json'; document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);\n    } catch(err){ log(ERREUR download: ); }\n  });\n}\n
