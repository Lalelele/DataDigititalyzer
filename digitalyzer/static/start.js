"use strict";
/* DataDigititalyzer – Projektübersicht: Dokumente hochladen, Einstellungen, Vorschau, Scan starten */

const $ = (q) => document.querySelector(q);
const $$ = (q) => Array.from(document.querySelectorAll(q));

const S = {
  projects: [], pid: null, info: null, settings: null, defaults: null, desc: [],
  page: 0, pages: 0, previewTimer: null, saveTimer: null, previewSeq: 0, pollTimer: null,
};

function toast(msg, err) {
  const t = $("#toast");
  t.textContent = msg;
  t.className = "show" + (err ? " err" : "");
  clearTimeout(toast._t);
  toast._t = setTimeout(() => (t.className = ""), err ? 5000 : 2200);
}

async function api(path, opts) {
  const res = await fetch(path, opts);
  let data = null;
  try { data = await res.json(); } catch (e) { data = null; }
  if (!res.ok || (data && data.fehler)) throw new Error((data && data.fehler) || `Fehler ${res.status}`);
  return data;
}

const post = (path, body) => api(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) });
const P = (pid) => `/api/p/${encodeURIComponent(pid)}`;
const fmtNum = (v) => String(v).replace(".", ",");

/* ------------------------------------------------------------ Projektliste */
async function loadProjects() {
  const data = await api("/api/projekte");
  $("#ws").textContent = "Arbeitsordner: " + data.arbeitsordner;
  S.projects = data.projekte;
  renderList();
  const running = S.projects.some((p) => p.job && p.job.laeuft);
  clearTimeout(S.listTimer);
  if (running) S.listTimer = setTimeout(loadProjects, 2000);
}

function statusLine(p) {
  if (p.job && p.job.laeuft) {
    const pct = Math.round((p.job.fortschritt || 0) * 100);
    return `<span class="badge run">wird ausgewertet</span>${pct} %<div class="mini"><div style="width:${pct}%"></div></div>`;
  }
  if (p.job && p.job.fehler) return `<span class="badge err">Fehler</span>`;
  if (!p.ausgewertet) return `<span class="badge">neu</span>noch nicht ausgewertet`;
  const s = p.summary || {};
  const open = (s.pruefen || 0) + (s.fehler || 0);
  const ser = (s.series || [])[0] || {};
  const pts = ser.expected ? `${s.points}/${ser.expected} Punkte` : `${s.points} Punkte`;
  const complete = !ser.expected || ser.points === ser.expected;
  return `<span class="badge ${open ? "warn" : "ok"}">${open ? open + " offen" : "geprüft"}</span>` +
    `${complete ? "" : "⚠ "}${pts}`;
}

function renderList() {
  const el = $("#list");
  if (!S.projects.length) {
    el.innerHTML = '<div class="hint" style="color:#6b7280;padding:6px">Noch keine Projekte.</div>';
    return;
  }
  el.innerHTML = S.projects.map((p) => {
    const date = p.erstellt ? new Date(p.erstellt).toLocaleString("de-DE", { dateStyle: "short", timeStyle: "short" }) : "";
    return `<div class="item ${p.id === S.pid ? "active" : ""}" data-id="${encodeURIComponent(p.id)}">
      <div class="n">${esc(p.name)}</div>
      <div class="m">${esc(p.quelle || "")}${date ? " · " + date : ""}</div>
      <div class="s">${statusLine(p)}</div></div>`;
  }).join("");
  $$("#list .item").forEach((it) => it.addEventListener("click", () => selectProject(decodeURIComponent(it.dataset.id))));
}

function esc(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

/* ------------------------------------------------------------ Hochladen */
async function upload(files) {
  let last = null;
  for (const f of files) {
    $("#upmsg").textContent = `Lade ${f.name} …`;
    try {
      const buf = await f.arrayBuffer();
      const r = await api(`/api/hochladen?name=${encodeURIComponent(f.name)}`, { method: "POST", body: buf });
      last = r.id;
    } catch (e) {
      toast(`${f.name}: ${e.message}`, true);
    }
  }
  $("#upmsg").textContent = "";
  await loadProjects();
  if (last) selectProject(last);
}

$("#file").addEventListener("change", (ev) => { upload(Array.from(ev.target.files)); ev.target.value = ""; });
const drop = $("#drop");
["dragenter", "dragover"].forEach((t) => document.addEventListener(t, (ev) => { ev.preventDefault(); drop.classList.add("over"); }));
["dragleave", "drop"].forEach((t) => document.addEventListener(t, (ev) => { ev.preventDefault(); if (t === "drop" || ev.target === document.documentElement) drop.classList.remove("over"); }));
document.addEventListener("drop", (ev) => {
  drop.classList.remove("over");
  const files = Array.from(ev.dataTransfer.files || []);
  if (files.length) upload(files);
});

/* ------------------------------------------------------------ Projekt */
async function selectProject(pid) {
  S.pid = pid;
  location.hash = encodeURIComponent(pid);
  renderList();
  $("#empty").hidden = true;
  $("#proj").hidden = false;
  const info = await api(`${P(pid)}/info`);
  S.info = info;
  S.settings = Object.assign({}, info.einstellungen);
  S.pages = info.seiten;
  S.page = 0;
  $("#pname").textContent = info.name;
  $("#psub").textContent = [info.quelle, info.seiten ? `${info.seiten} Seite(n)` : ""].filter(Boolean).join(" · ");
  $("#noscan").hidden = !!info.scan;
  $("#work").hidden = !info.scan;
  renderButtons();
  renderForm();
  renderJob(info.job);
  if (info.job && info.job.laeuft) poll();
  if (info.scan) schedulePreview(0);
}

function renderButtons() {
  const info = S.info;
  const running = info.job && info.job.laeuft;
  const rev = $("#btn-review");
  rev.href = `/pruefen/${encodeURIComponent(S.pid)}`;
  rev.classList.toggle("disabled", !info.ausgewertet || running);
  rev.classList.toggle("primary", !!info.ausgewertet);
  const st = $("#btn-start");
  st.hidden = !info.scan;
  st.disabled = !!running;
  st.textContent = info.ausgewertet ? "Neu auswerten" : "Scan starten";
  st.classList.toggle("primary", !info.ausgewertet);
}

/* ------------------------------------------------------------ Einstellungen */
function renderForm() {
  const groups = {};
  for (const d of S.desc) (groups[d[0]] = groups[d[0]] || []).push(d);
  const html = [];
  for (const [g, items] of Object.entries(groups)) {
    html.push(`<fieldset><legend>${g}</legend>`);
    for (const [, key, label, type, help, min, max, step] of items) {
      const v = S.settings[key];
      const changed = JSON.stringify(v) !== JSON.stringify(S.defaults[key]) ? " changed" : "";
      let input;
      if (type === "bool") {
        input = `<input type="checkbox" name="${key}" ${v ? "checked" : ""}>`;
      } else if (type.startsWith("select:")) {
        const opts = type.slice(7).split("|");
        input = `<select name="${key}" class="${changed}">${opts.map((o) => `<option ${o === v ? "selected" : ""}>${o}</option>`).join("")}</select>`;
      } else {
        input = `<input type="number" name="${key}" class="${changed}" value="${v === null || v === undefined ? "" : v}"` +
          `${min !== null ? ` min="${min}"` : ""}${max !== null ? ` max="${max}"` : ""}${step ? ` step="${step}"` : ""}>`;
      }
      let lbl = label;
      if (key === "winkel" && S.settings.winkel_auto) lbl = "Feinkorrektur Winkel (Grad)";
      html.push(`<div class="field"><label><span>${lbl}</span>${input}</label>${help ? `<div class="help">${help}</div>` : ""}</div>`);
    }
    html.push("</fieldset>");
  }
  $("#form").innerHTML = html.join("");
}

function readForm() {
  const out = Object.assign({}, S.settings);
  for (const el of $$("#form [name]")) {
    const k = el.name;
    if (el.type === "checkbox") out[k] = el.checked;
    else if (el.tagName === "SELECT") out[k] = el.value;
    else out[k] = el.value === "" ? null : Number(el.value);
  }
  return out;
}

$("#form").addEventListener("input", (ev) => {
  S.settings = readForm();
  ev.target.classList.toggle("changed", JSON.stringify(S.settings[ev.target.name]) !== JSON.stringify(S.defaults[ev.target.name]));
  if (ev.target.name === "winkel_auto") renderForm();
  schedulePreview(400);
  clearTimeout(S.saveTimer);
  S.saveTimer = setTimeout(() => post(`${P(S.pid)}/einstellungen`, { einstellungen: S.settings }).catch(() => {}), 800);
});

$("#btn-default").addEventListener("click", () => {
  S.settings = Object.assign({}, S.defaults);
  renderForm();
  schedulePreview(0);
  post(`${P(S.pid)}/einstellungen`, { einstellungen: S.settings }).catch(() => {});
});

/* ------------------------------------------------------------ Vorschau */
function schedulePreview(delay) {
  clearTimeout(S.previewTimer);
  S.previewTimer = setTimeout(updatePreview, delay);
}

async function updatePreview() {
  if (!S.pid || !S.info || !S.info.scan) return;
  const seq = ++S.previewSeq;
  $("#pg-label").textContent = `Seite ${S.page + 1} / ${S.pages}`;
  $("#pg-prev").disabled = S.page <= 0;
  $("#pg-next").disabled = S.page >= S.pages - 1;
  $("#ploading").classList.add("show");
  try {
    const r = await post(`${P(S.pid)}/vorschau`, { seite: S.page, einstellungen: S.settings });
    if (seq !== S.previewSeq) return;
    $("#pimg").src = r.bild;
    const i = r.info;
    const warn = [];
    if (i.leer > 2) warn.push(`<span class="warnx">${i.leer} leere Zellen</span>`);
    $("#pinfo").innerHTML = `Winkel <b>${fmtNum(i.winkel.toFixed(2))}°</b> · <b>${i.spalten}</b> Spalten · <b>${i.zeilen}</b> Zeilen · ` +
      `<b>${i.zellen}</b> Zellen · Zeilenabstand <b>${fmtNum(i.zeilenabstand.toFixed(1))}</b> px · Zeichenhöhe ${fmtNum(i.zeichenhoehe)} px` +
      (warn.length ? " · " + warn.join(" · ") : "");
  } catch (e) {
    if (seq === S.previewSeq) toast("Vorschau: " + e.message, true);
  } finally {
    if (seq === S.previewSeq) $("#ploading").classList.remove("show");
  }
}

$("#pg-prev").addEventListener("click", () => { if (S.page > 0) { S.page--; schedulePreview(0); } });
$("#pg-next").addEventListener("click", () => { if (S.page < S.pages - 1) { S.page++; schedulePreview(0); } });
$("#fit").addEventListener("change", () => $("#pimg").classList.toggle("fit", $("#fit").checked));
$("#pimg").classList.add("fit");

/* ------------------------------------------------------------ Auswertung */
$("#btn-start").addEventListener("click", async () => {
  if (S.info.ausgewertet) {
    const s = S.info.summary || {};
    const manual = (s.bestaetigt || 0) + (s.korrigiert || 0);
    const msg = manual
      ? `Neu auswerten? ${manual} von Hand geprüfte Werte werden übernommen, soweit die Zellen an derselben Stelle wieder erkannt werden. Die bisherige Auswertung wird ersetzt.`
      : "Neu auswerten? Die bisherige Auswertung wird ersetzt.";
    if (!confirm(msg)) return;
  }
  try {
    const job = await post(`${P(S.pid)}/analyse`, { einstellungen: S.settings });
    S.info.job = job;
    renderButtons();
    renderJob(job);
    poll();
    loadProjects();
  } catch (e) {
    toast(e.message, true);
  }
});

function renderJob(job) {
  const box = $("#job");
  if (!job || (!job.laeuft && !job.fehler && !job.beendet)) { box.hidden = true; return; }
  box.hidden = false;
  const pct = Math.round((job.fortschritt || 0) * 100);
  const bar = $("#jobbar");
  bar.style.width = (job.laeuft ? pct : 100) + "%";
  bar.className = job.fehler ? "fail" : (!job.laeuft ? "done" : "");
  let txt;
  if (job.laeuft) txt = `Auswertung läuft … ${pct} %`;
  else if (job.fehler) txt = `Fehler: ${job.fehler}`;
  else txt = "Fertig.";
  $("#jobtext").innerHTML = esc(txt) + (!job.laeuft && !job.fehler ? ` <a class="btn primary small" href="/pruefen/${encodeURIComponent(S.pid)}">Prüfung öffnen</a>` : "");
  const log = $("#joblog");
  log.textContent = (job.meldungen || []).join("\n");
  log.scrollTop = log.scrollHeight;
}

function poll() {
  clearTimeout(S.pollTimer);
  const pid = S.pid;
  S.pollTimer = setTimeout(async () => {
    if (pid !== S.pid) return;
    try {
      const job = await api(`${P(pid)}/status`);
      renderJob(job);
      if (job.laeuft) return poll();
      const info = await api(`${P(pid)}/info`);
      S.info = info;
      renderButtons();
      renderJob(info.job);
      loadProjects();
      if (!job.fehler) toast("Auswertung abgeschlossen.");
    } catch (e) {
      toast(e.message, true);
    }
  }, 1000);
}

/* ------------------------------------------------------------ Start */
(async function init() {
  try {
    const d = await api("/api/einstellungen");
    S.defaults = d.standard;
    S.desc = d.beschreibung;
    await loadProjects();
    const fromHash = decodeURIComponent(location.hash.slice(1));
    if (fromHash && S.projects.some((p) => p.id === fromHash)) selectProject(fromHash);
  } catch (e) {
    toast(e.message, true);
  }
})();
