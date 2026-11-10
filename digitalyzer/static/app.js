"use strict";
/* DataDigititalyzer – Prüfoberfläche (ohne externe Bibliotheken) */

const COLORS = { ok: "#2e9e5b", pruefen: "#e0a800", fehler: "#d93025", bestaetigt: "#1a73e8", korrigiert: "#8e44ad" };
const LABEL = { ok: "ok", pruefen: "prüfen", fehler: "Regelverstoß", bestaetigt: "bestätigt", korrigiert: "korrigiert" };
const OPEN = new Set(["pruefen", "fehler"]);
// Bildvarianten der Texterkennung wie in pipeline.process (Standardeinstellungen)
const CAND_NAMES = { ocr1: "Texterkennung (2,5×)", ocr2: "Texterkennung (3×, geglättet)", ziffern: "gelernte Ziffernformen" };

// Projekt aus der Adresse /pruefen/<Projekt>
const PID = decodeURIComponent(location.pathname.split("/").filter(Boolean)[1] || "");
const API = `/api/p/${encodeURIComponent(PID)}`;

const S = {
  project: null, byId: new Map(), pages: [], page: 0, view: "tabelle", sel: null,
  imgs: new Map(), synthVersion: {}, pageMode: "overlay", blinkTimer: null, blinkOn: false,
  diffCache: new Map(), points: [],
};

const $ = (q) => document.querySelector(q);
const $$ = (q) => Array.from(document.querySelectorAll(q));

function toast(msg) {
  const t = $("#toast");
  t.textContent = msg;
  t.classList.add("show");
  clearTimeout(toast._t);
  toast._t = setTimeout(() => t.classList.remove("show"), 1800);
}

/* ------------------------------------------------------------------ Daten */
async function load() {
  const res = await fetch(`${API}/projekt`);
  S.project = await res.json();
  if (S.project.fehler) throw new Error(S.project.fehler);
  const back = document.querySelector("a.back");
  if (back) back.href = "/#" + encodeURIComponent(PID);
  document.title = `Prüfung – ${S.project.source || PID}`;
  $("#source").textContent = S.project.source || "";
  for (const c of S.project.cells) S.byId.set(c.id, c);
  S.pages = S.project.pages.map((p) => ({ ...p, rows: new Map() }));
  for (const c of S.project.cells) {
    const pg = S.pages[c.page];
    if (!pg.rows.has(c.row)) pg.rows.set(c.row, []);
    pg.rows.get(c.row).push(c);
  }
  for (const pg of S.pages) {
    for (const r of pg.rows.values()) r.sort((a, b) => a.col - b.col);
    pg.rowIds = Array.from(pg.rows.keys()).sort((a, b) => a - b);
    pg.ncols = pg.columns.length;
  }
  buildPoints();
  fitZoom();
  renderSummary();
  renderPageList();
  selectPage(0);
  const first = nextOpen(null, 1);
  if (first) select(first.id, { scroll: true });
}

function buildPoints() {
  S.points = S.project.cells
    .filter((c) => c.kind === "count" && c.point !== undefined && c.point !== null)
    .sort((a, b) => (a.series - b.series) || (a.point - b.point));
  S.nByPoint = new Map();
  for (const c of S.project.cells) if (c.kind === "n" && c.point != null) S.nByPoint.set(`${c.series}:${c.point}`, c);
}

function imgURL(page, kind) {
  const v = kind === "synthetisch" ? `?v=${S.synthVersion[page] || 0}` : "";
  return `${API}/bild/${page}/${kind}${v}`;
}

function getImage(page, kind) {
  const url = imgURL(page, kind);
  if (S.imgs.has(url)) return S.imgs.get(url);
  const img = new Image();
  const p = new Promise((resolve, reject) => {
    img.onload = () => resolve(img);
    img.onerror = reject;
  });
  img.src = url;
  S.imgs.set(url, p);
  return p;
}

/* ------------------------------------------------------------------ Kopfzeile, Seitenliste */
function renderSummary() {
  const s = S.project.summary || {};
  const open = (s.pruefen || 0) + (s.fehler || 0);
  const chips = [];
  for (const ser of s.series || []) {
    const ok = ser.expected ? ser.points === ser.expected : null;
    const txt = ser.expected ? `${ser.points} / ${ser.expected} Punkte` : `${ser.points} Punkte`;
    const h = ser.header || {};
    const htxt = [h.sample ? `Probe: ${h.sample}` : "", h.wavelength != null ? `Wellenlänge: ${h.wavelength}` : "",
      h.start != null ? `Start: ${h.start}°` : "", h.finish != null ? `Ende: ${h.finish}°` : "", h.step != null ? `Schritt: ${h.step}°` : "",
      ...(h.hinweise || []).map((x) => "Hinweis: " + x)].filter(Boolean).join("\n");
    chips.push(`<span class="chip ${ok === true ? "good" : ok === false ? "bad" : ""}" title="Messreihe ${ser.id + 1}: gefundene / laut Kopf erwartete Messpunkte\n${htxt.replace(/"/g, "&quot;")}">${ok === true ? "✓ " : ok === false ? "⚠ " : ""}${txt}</span>`);
  }
  chips.push(`<span class="chip ${open ? "bad" : "good"}">offen<b>${open}</b></span>`);
  for (const k of ["ok", "bestaetigt", "korrigiert"]) chips.push(`<span class="chip">${LABEL[k]}<b>${s[k] || 0}</b></span>`);
  $("#summary").innerHTML = chips.join("");
}

function renderPageList() {
  $("#pages").innerHTML = S.pages.map((pg, i) => {
    const cells = S.project.cells.filter((c) => c.page === i);
    const cnt = {};
    for (const c of cells) cnt[c.status] = (cnt[c.status] || 0) + 1;
    const open = (cnt.pruefen || 0) + (cnt.fehler || 0);
    const bar = ["ok", "bestaetigt", "korrigiert", "pruefen", "fehler"]
      .map((k) => `<span style="flex:${cnt[k] || 0};background:${COLORS[k]}"></span>`).join("");
    return `<div class="pg ${i === S.page ? "active" : ""}" data-page="${i}">Seite ${i + 1}
      <small>${open ? open + " offen" : "alles geprüft"}</small><div class="bar">${bar}</div></div>`;
  }).join("");
  $$("#pages .pg").forEach((el) => el.addEventListener("click", () => selectPage(+el.dataset.page)));
}

function selectPage(i, keepSel) {
  if (i < 0 || i >= S.pages.length) return;
  S.page = i;
  $$("#pages .pg").forEach((el) => el.classList.toggle("active", +el.dataset.page === i));
  renderTable();
  if (S.view === "seite") drawPage();
  if (!keepSel) {
    const c = S.project.cells.find((x) => x.page === i && x.status !== "leer");
    if (c && (!S.sel || S.byId.get(S.sel).page !== i)) select(c.id, { scroll: true });
  }
}

/* ------------------------------------------------------------------ Prüftabelle */
function tableGeometry(pg) {
  const zoom = parseFloat($("#zoom").value);
  const m = 4;
  const colW = new Array(pg.ncols).fill(0);
  let h = 0;
  for (const row of pg.rows.values()) for (const c of row) {
    colW[c.col] = Math.max(colW[c.col], c.box[2] + 2 * m);
    h = Math.max(h, c.box[3] + 2 * m);
  }
  h = Math.min(h, Math.round(pg.pitch * 1.1));
  return { zoom, m, colW, h };
}

function fitZoom() {
  // Vergrößerung so wählen, dass eine ganze Tabellenzeile ohne Querscrollen sichtbar ist
  const pg = S.pages[0];
  if (!pg) return;
  const g = tableGeometry(pg);
  const sum = g.colW.reduce((a, b) => a + b, 0);
  const kinds = new Map();
  for (const c of S.project.cells) if (c.page === 0) kinds.set(c.col, c.kind);
  let overhead = 92 + 30;
  for (let col = 0; col < pg.ncols; col++) overhead += (kinds.get(col) === "n" ? 22 : 42) + 17;
  const avail = $("#table").clientWidth || 900;
  const z = Math.max(1, Math.min(3, (avail - overhead) / sum));
  $("#zoom").value = String(Math.floor(z * 4) / 4);
}

function cellHTML(c, pg, g, imgUrl) {
  const [x, y, w, hh] = c.box;
  const cw = g.colW[c.col];
  const right = x + w + g.m;
  const left = right - cw;
  const top = Math.round(y + hh / 2 - g.h / 2);
  const z = g.zoom;
  const style = `width:${cw * z}px;height:${g.h * z}px;background-image:url('${imgUrl}');` +
    `background-size:${pg.width * z}px ${pg.height * z}px;background-position:${-left * z}px ${-top * z}px`;
  const cls = `cell s-${c.status} kind-${c.kind}${c.id === S.sel ? " sel" : ""}`;
  return `<div class="${cls}" data-id="${c.id}" title="${(c.flags || []).map((f) => f.msg).join("; ")}">` +
    `<div class="crop" style="${style}"></div><span class="val">${c.value || "∅"}</span></div>`;
}

function renderTable() {
  const pg = S.pages[S.page];
  if (!pg) return;
  const g = tableGeometry(pg);
  const imgUrl = imgURL(S.page, $("#contrast").checked ? "kontrast" : "original");
  const only = $("#onlyflagged").checked;
  const out = [];
  let lastShown = null;
  for (const r of pg.rowIds) {
    const row = pg.rows.get(r);
    if (only && !row.some((c) => OPEN.has(c.status))) continue;
    if (only && lastShown !== null && r !== lastShown + 1) out.push('<div class="trow gap"></div>');
    lastShown = r;
    const first = row.find((c) => c.angle != null);
    const ang = first ? `2θ ${first.angle.toFixed(2)}°` : "";
    const cells = [];
    for (let col = 0; col < pg.ncols; col++) {
      const c = row.find((x) => x.col === col);
      if (c) cells.push(cellHTML(c, pg, g, imgUrl));
      else cells.push(`<div class="cell empty"><div class="crop" style="width:${g.colW[col] * g.zoom}px;height:${g.h * g.zoom}px"></div><span class="val"></span></div>`);
    }
    out.push(`<div class="trow" data-row="${r}"><div class="rlabel"><span>Zeile ${r + 1}</span><span>${ang}</span></div>${cells.join("")}</div>`);
  }
  $("#table").innerHTML = out.join("") || '<p style="padding:20px;color:#6b7280">Keine offenen Punkte auf dieser Seite.</p>';
}

function updateCellDOM(c) {
  const el = document.querySelector(`.cell[data-id="${c.id}"]`);
  if (!el) return;
  el.className = `cell s-${c.status} kind-${c.kind}${c.id === S.sel ? " sel" : ""}`;
  el.querySelector(".val").textContent = c.value || "∅";
  el.title = (c.flags || []).map((f) => f.msg).join("; ");
}

/* ------------------------------------------------------------------ Auswahl & Detail */
function select(id, opts = {}) {
  const c = S.byId.get(id);
  if (!c) return;
  const prev = S.sel;
  S.sel = id;
  if (c.page !== S.page) selectPage(c.page, true);
  if (prev) document.querySelector(`.cell[data-id="${prev}"]`)?.classList.remove("sel");
  const el = document.querySelector(`.cell[data-id="${id}"]`);
  if (el) {
    el.classList.add("sel");
    if (opts.scroll !== false) el.scrollIntoView({ block: "nearest", inline: "nearest" });
  }
  renderDetail();
  if (S.view === "seite") drawPage(opts.scroll !== false);
  if (S.view === "diagramm") drawPlot();
}

async function renderDetail() {
  const c = S.byId.get(S.sel);
  $("#detail-empty").hidden = !!c;
  $("#detail-body").hidden = !c;
  if (!c) return;
  $("#d-id").textContent = `Seite ${c.page + 1} · Zeile ${c.row + 1} · Spalte ${c.col + 1}`;
  const b = $("#d-status");
  b.textContent = LABEL[c.status] || c.status;
  b.style.background = COLORS[c.status] || "#888";
  const inp = $("#d-input");
  if (document.activeElement !== inp || inp.dataset.id !== c.id) {
    inp.value = c.value || "";
    inp.dataset.id = c.id;
  }
  const cands = c.cand || {};
  const scores = c.score || {};
  $("#d-cands").innerHTML = Object.keys(CAND_NAMES).map((k) =>
    `<tr class="${cands[k] === c.value ? "win" : ""}" data-v="${cands[k] || ""}" title="Klicken übernimmt diesen Wert ins Eingabefeld">` +
    `<td>${CAND_NAMES[k]}</td><td class="v">${cands[k] || "–"}</td><td>${scores[k] != null ? Math.round(scores[k] * 100) + "%" : ""}</td></tr>`).join("");
  $$("#d-cands tr").forEach((tr) => tr.addEventListener("click", () => { inp.value = tr.dataset.v; inp.focus(); }));
  const flags = c.flags || [];
  $("#d-flags").innerHTML = flags.map((f) => `<li class="${f.sev}">${f.msg}</li>`).join("");
  const sug = flags.find((f) => f.suggest);
  $("#d-suggest").innerHTML = sug ? `<button id="d-sugbtn">Vorschlag übernehmen: <b>${sug.suggest}</b> (V)</button>` : "";
  if (sug) $("#d-sugbtn").addEventListener("click", () => commit(sug.suggest));
  const kind = c.kind === "n" ? "Detektoranzahl n" : "Durchschnittl. Intensität";
  const meta = [`${kind}`];
  if (c.point != null) meta.push(`Messpunkt ${c.point}${c.angle != null ? ` · 2θ = ${c.angle.toFixed(2)}°` : ""}`);
  if (c.ocr_value !== undefined && c.ocr_value !== c.value) meta.push(`ursprünglich erkannt: ${c.ocr_value || "∅"}`);
  if (c.raw) meta.push(`Rohtext OCR: ${Object.values(c.raw).map((r) => JSON.stringify(r)).join(" / ")}`);
  $("#d-meta").innerHTML = meta.join("<br>");
  // Großer Ausschnitt mit Nachbarzellen als Kontext
  const pg = S.pages[c.page];
  const img = await getImage(c.page, $("#contrast").checked ? "kontrast" : "original");
  if (S.sel !== c.id) return;
  const [x, y, w, h] = c.box;
  const cw = Math.max(w * 5, pg.char_height * 8);
  const ch = pg.pitch * 3;
  const sx = Math.max(0, x + w / 2 - cw / 2), sy = Math.max(0, y + h / 2 - ch / 2);
  const cv = document.createElement("canvas");
  const scale = 4;
  cv.width = cw * scale; cv.height = ch * scale;
  const ctx = cv.getContext("2d");
  ctx.imageSmoothingQuality = "high";
  ctx.drawImage(img, sx, sy, cw, ch, 0, 0, cv.width, cv.height);
  ctx.strokeStyle = COLORS[c.status] || "#000";
  ctx.lineWidth = 3;
  ctx.strokeRect((x - sx - 2) * scale, (y - sy - 2) * scale, (w + 4) * scale, (h + 4) * scale);
  $("#d-crop").replaceChildren(cv);
}

function allCellsOrdered() {
  return S.project.cells.filter((c) => c.status !== "leer")
    .sort((a, b) => (a.page - b.page) || (a.row - b.row) || (a.col - b.col));
}

function nextOpen(fromId, dir) {
  const list = allCellsOrdered();
  let i = fromId ? list.findIndex((c) => c.id === fromId) : (dir > 0 ? -1 : list.length);
  for (let k = 0; k < list.length; k++) {
    i += dir;
    if (i < 0 || i >= list.length) return null;
    if (OPEN.has(list[i].status)) return list[i];
  }
  return null;
}

function move(dr, dc) {
  const c = S.byId.get(S.sel);
  if (!c) return;
  const pg = S.pages[c.page];
  const only = $("#onlyflagged").checked;
  const rows = pg.rowIds.filter((r) => !only || pg.rows.get(r).some((x) => OPEN.has(x.status)));
  if (dc) {
    const row = pg.rows.get(c.row);
    const i = row.findIndex((x) => x.id === c.id) + dc;
    if (i >= 0 && i < row.length) return select(row[i].id);
    const ri = rows.indexOf(c.row) + dc;
    if (ri >= 0 && ri < rows.length) {
      const nr = pg.rows.get(rows[ri]);
      return select((dc > 0 ? nr[0] : nr[nr.length - 1]).id);
    }
    return;
  }
  const ri = rows.indexOf(c.row) + dr;
  if (ri < 0 || ri >= rows.length) return;
  const nr = pg.rows.get(rows[ri]);
  const t = nr.find((x) => x.col === c.col) || nr[nr.length - 1];
  select(t.id);
}

async function commit(valueOverride) {
  const c = S.byId.get(S.sel);
  if (!c) return;
  const inp = $("#d-input");
  const v = (valueOverride !== undefined ? valueOverride : inp.value).replace(/\D/g, "");
  const wasOpen = OPEN.has(c.status);
  const action = v === c.value ? "bestaetigen" : "korrigieren";
  const res = await fetch(`${API}/zelle`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id: c.id, aktion: action, wert: v }),
  });
  const data = await res.json();
  if (data.fehler) return toast("Fehler: " + data.fehler);
  applyChanges(data);
  toast(action === "bestaetigen" ? `bestätigt: ${v}` : `korrigiert: ${c.ocr_value || "∅"} → ${v}`);
  inp.blur();
  const nxt = wasOpen ? nextOpen(c.id, 1) : null;
  if (nxt) select(nxt.id);
  else move(0, 1);
}

async function resetCell() {
  const c = S.byId.get(S.sel);
  if (!c) return;
  const res = await fetch(`${API}/zelle`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id: c.id, aktion: "zuruecksetzen" }),
  });
  applyChanges(await res.json());
  renderDetail();
}

function applyChanges(data) {
  const pagesTouched = new Set();
  for (const ch of data.changed || []) {
    const c = S.byId.get(ch.id);
    Object.assign(c, ch);
    if (!ch.human) delete c.human;
    pagesTouched.add(c.page);
    updateCellDOM(c);
  }
  for (const p of pagesTouched) {
    S.synthVersion[p] = (S.synthVersion[p] || 0) + 1;
    for (const k of Array.from(S.diffCache.keys())) if (k.startsWith(p + ":")) S.diffCache.delete(k);
  }
  S.project.summary = data.summary;
  renderSummary();
  renderPageList();
  renderDetail();
  if (S.view === "seite") drawPage(false);
  if (S.view === "diagramm") drawPlot();
}

/* ------------------------------------------------------------------ Seitenansicht */
async function diffImage(page) {
  const key = `${page}:${S.synthVersion[page] || 0}`;
  if (S.diffCache.has(key)) return S.diffCache.get(key);
  const [a, b] = await Promise.all([getImage(page, "kontrast"), getImage(page, "synthetisch")]);
  const w = a.naturalWidth, h = a.naturalHeight;
  const ca = document.createElement("canvas");
  ca.width = w; ca.height = h;
  const ctx = ca.getContext("2d", { willReadFrequently: true });
  ctx.drawImage(a, 0, 0);
  const da = ctx.getImageData(0, 0, w, h);
  ctx.drawImage(b, 0, 0);
  const db = ctx.getImageData(0, 0, w, h);
  // Nur Zellbereiche vergleichen (Kopf, Ränder und Staub sind nicht nachgezeichnet)
  const inCell = new Uint8Array(w * h);
  for (const c of S.project.cells) {
    if (c.page !== page) continue;
    const [x, y, cw, chh] = c.box;
    for (let yy = Math.max(0, y - 3); yy < Math.min(h, y + chh + 3); yy++) inCell.fill(1, yy * w + Math.max(0, x - 3), yy * w + Math.min(w, x + cw + 3));
  }
  const out = ctx.createImageData(w, h);
  for (let i = 0, p = 0; i < da.data.length; i += 4, p++) {
    // Grundbild: Scan blass als Orientierung; in Zellen echte Abweichungen kräftig rot
    // (kleine Abweichungen durch Unschärfe werden unterdrückt)
    const base = 255 - (255 - da.data[i]) * 0.22;
    let r = base, gg = base, bb = base;
    if (inCell[p]) {
      const d = Math.min(255, Math.max(0, Math.abs(da.data[i] - db.data[i]) - 45) * 2.5);
      gg = Math.max(0, base - d); bb = Math.max(0, base - d); r = Math.max(0, base - d * 0.25);
    }
    out.data[i] = r; out.data[i + 1] = gg; out.data[i + 2] = bb; out.data[i + 3] = 255;
  }
  ctx.putImageData(out, 0, 0);
  S.diffCache.set(key, ca);
  return ca;
}

async function drawPage(scrollToSel) {
  const pg = S.pages[S.page];
  const cv = $("#pagecanvas");
  const z = parseFloat($("#pzoom").value);
  const mode = S.pageMode;
  const base = $("#contrast").checked ? "kontrast" : "original";
  let src;
  if (mode === "synth" || (mode === "blink" && S.blinkOn)) src = await getImage(S.page, "synthetisch");
  else if (mode === "diff") src = await diffImage(S.page);
  else if (mode === "blink") src = await getImage(S.page, "kontrast");
  else src = await getImage(S.page, base);
  cv.width = Math.round(pg.width * z);
  cv.height = Math.round(pg.height * z);
  const ctx = cv.getContext("2d");
  ctx.imageSmoothingQuality = "high";
  ctx.drawImage(src, 0, 0, cv.width, cv.height);
  const cells = S.project.cells.filter((c) => c.page === S.page && c.status !== "leer");
  if (mode === "overlay") {
    const fs = Math.max(9, Math.round(pg.char_height * z * 0.85));
    ctx.font = `600 ${fs}px ui-monospace, Consolas, monospace`;
    ctx.textBaseline = "middle";
    for (const c of cells) {
      const [x, y, w, h] = c.box.map((v) => v * z);
      const col = COLORS[c.status] || "#000";
      ctx.strokeStyle = col;
      ctx.lineWidth = OPEN.has(c.status) ? 2 : 1;
      ctx.globalAlpha = OPEN.has(c.status) ? 1 : 0.5;
      ctx.strokeRect(x - 1, y - 1, w + 2, h + 2);
      ctx.globalAlpha = 1;
      const txt = c.value || "∅";
      const tw = ctx.measureText(txt).width;
      // Wert direkt neben die Originalzahl: einstellige n-Spalte rechts daneben,
      // rechtsbündige Durchschnittl. Intensitäten links daneben (dort ist Platz)
      const tx = c.kind === "n" ? x + w + 3 : x - tw - 4;
      ctx.fillStyle = "rgba(255,255,255,0.85)";
      ctx.fillRect(tx - 1, y + h / 2 - fs / 2, tw + 2, fs);
      ctx.fillStyle = c.status === "ok" ? "#1b6e3d" : col;
      ctx.fillText(txt, tx, y + h / 2);
    }
  }
  const s = S.byId.get(S.sel);
  if (s && s.page === S.page) {
    const [x, y, w, h] = s.box.map((v) => v * z);
    ctx.strokeStyle = "#111";
    ctx.lineWidth = 3;
    ctx.strokeRect(x - 4, y - 4, w + 8, h + 8);
    if (scrollToSel) {
      const wrap = $("#pagewrap");
      const r = cv.getBoundingClientRect(), wr = wrap.getBoundingClientRect();
      const cx = r.left - wr.left + wrap.scrollLeft + x, cy = r.top - wr.top + wrap.scrollTop + y;
      if (cx < wrap.scrollLeft + 40 || cx > wrap.scrollLeft + wrap.clientWidth - 40 ||
          cy < wrap.scrollTop + 40 || cy > wrap.scrollTop + wrap.clientHeight - 40) {
        wrap.scrollTo({ left: cx - wrap.clientWidth / 2, top: cy - wrap.clientHeight / 2 });
      }
    }
  }
  $("#pagehint").textContent = {
    overlay: "Rahmen/Werte farbig nach Status. Klick wählt Zelle.",
    original: "Unverändertes (nur begradigtes) Scanbild.",
    synth: "Erkannte Werte, mit den gelernten Ziffernformen nachgezeichnet.",
    blink: "Wechselt zwischen Scan und Nachzeichnung – Fehler „springen“.",
    diff: "Differenz Scan − Nachzeichnung: hell = stimmt, rote Flecken = Abweichung.",
  }[mode];
}

function setPageMode(mode) {
  S.pageMode = mode;
  $$("#pagemode button").forEach((b) => b.classList.toggle("active", b.dataset.mode === mode));
  clearInterval(S.blinkTimer);
  S.blinkOn = false;
  if (mode === "blink") {
    S.blinkTimer = setInterval(() => { S.blinkOn = !S.blinkOn; drawPage(false); }, 500);
  }
  drawPage(false);
}

$("#pagecanvas").addEventListener("click", (ev) => {
  const z = parseFloat($("#pzoom").value);
  const r = ev.target.getBoundingClientRect();
  const px = (ev.clientX - r.left) / z, py = (ev.clientY - r.top) / z;
  let best = null, bd = 1e9;
  for (const c of S.project.cells) {
    if (c.page !== S.page || c.status === "leer") continue;
    const [x, y, w, h] = c.box;
    const dx = Math.max(x - px, 0, px - (x + w)), dy = Math.max(y - py, 0, py - (y + h));
    const d = dx * dx + dy * dy;
    if (d < bd) { bd = d; best = c; }
  }
  if (best && bd < 400) select(best.id, { scroll: false });
});

/* ------------------------------------------------------------------ Diagramm */
function plotGeom() {
  const cv = $("#plot");
  const dpr = window.devicePixelRatio || 1;
  const W = cv.clientWidth, H = cv.clientHeight;
  return { cv, dpr, W, H, L: 60, R: 20, T: 20, B: 40 };
}

function plotXY(g, c, xmin, xmax, ymin, ymax, log) {
  const xv = c.angle != null ? c.angle : c.point;
  const v = parseInt(c.value, 10);
  const yv = log ? Math.log10(Math.max(v, 1)) : v;
  return [g.L + (xv - xmin) / (xmax - xmin || 1) * (g.W - g.L - g.R),
          g.T + (1 - (yv - ymin) / (ymax - ymin || 1)) * (g.H - g.T - g.B)];
}

function drawPlot() {
  const g = plotGeom();
  const { cv, dpr, W, H } = g;
  cv.width = W * dpr; cv.height = H * dpr;
  const ctx = cv.getContext("2d");
  ctx.scale(dpr, dpr);
  ctx.clearRect(0, 0, W, H);
  const pts = S.points.filter((c) => /^\d+$/.test(c.value || ""));
  if (!pts.length) return;
  const log = $("#logscale").checked;
  const xs = pts.map((c) => (c.angle != null ? c.angle : c.point));
  const ys = pts.map((c) => { const v = parseInt(c.value, 10); return log ? Math.log10(Math.max(v, 1)) : v; });
  const xmin = Math.min(...xs), xmax = Math.max(...xs);
  const ymin = log ? Math.floor(Math.min(...ys)) : 0, ymax = Math.max(...ys) * 1.05;
  S.plotRange = { xmin, xmax, ymin, ymax, log };
  // Achsen
  ctx.strokeStyle = "#9ca3af"; ctx.fillStyle = "#4b5563"; ctx.font = "11px system-ui"; ctx.lineWidth = 1;
  ctx.beginPath(); ctx.moveTo(g.L, g.T); ctx.lineTo(g.L, H - g.B); ctx.lineTo(W - g.R, H - g.B); ctx.stroke();
  const xstep = Math.pow(10, Math.floor(Math.log10((xmax - xmin) / 5 || 1)));
  for (let x = Math.ceil(xmin / (xstep * 2)) * xstep * 2; x <= xmax; x += xstep * 2) {
    const px = g.L + (x - xmin) / (xmax - xmin || 1) * (W - g.L - g.R);
    ctx.fillText(x.toFixed(xstep < 1 ? 1 : 0), px - 10, H - g.B + 15);
  }
  ctx.fillText(pts[0].angle != null ? "2θ [°]" : "Messpunkt", W / 2, H - 8);
  if (log) {
    for (let e = ymin; e <= ymax; e++) {
      const py = g.T + (1 - (e - ymin) / (ymax - ymin || 1)) * (H - g.T - g.B);
      ctx.fillText(String(Math.pow(10, e)), 8, py + 4);
      ctx.strokeStyle = "#eef0f3"; ctx.beginPath(); ctx.moveTo(g.L, py); ctx.lineTo(W - g.R, py); ctx.stroke();
    }
  } else {
    const ystep = Math.pow(10, Math.floor(Math.log10(ymax / 4 || 1)));
    for (let v = 0; v <= ymax; v += ystep * (ymax / ystep > 8 ? 2 : 1)) {
      const py = g.T + (1 - v / ymax) * (H - g.T - g.B);
      ctx.fillText(String(v), 8, py + 4);
    }
  }
  ctx.save();
  ctx.translate(14, H / 2); ctx.rotate(-Math.PI / 2); ctx.textAlign = "center"; ctx.fillText("Durchschnittl. Intensität", 0, 0); ctx.restore();
  // Verlauf
  ctx.strokeStyle = "#374151"; ctx.lineWidth = 1; ctx.beginPath();
  pts.forEach((c, i) => {
    const [x, y] = plotXY(g, c, xmin, xmax, ymin, ymax, log);
    if (i === 0 || pts[i - 1].series !== c.series) ctx.moveTo(x, y); else ctx.lineTo(x, y);
  });
  ctx.stroke();
  // Punkte mit Status
  for (const c of pts) {
    if (c.status === "ok") continue;
    const [x, y] = plotXY(g, c, xmin, xmax, ymin, ymax, log);
    ctx.fillStyle = COLORS[c.status] || "#000";
    ctx.beginPath(); ctx.arc(x, y, OPEN.has(c.status) ? 4 : 2.5, 0, Math.PI * 2); ctx.fill();
  }
  const s = S.byId.get(S.sel);
  const sc = s && (s.kind === "count" ? s : S.points.find((p) => p.series === s.series && p.point === s.point));
  if (sc && /^\d+$/.test(sc.value || "")) {
    const [x, y] = plotXY(g, sc, xmin, xmax, ymin, ymax, log);
    ctx.strokeStyle = "#111"; ctx.lineWidth = 2;
    ctx.beginPath(); ctx.arc(x, y, 8, 0, Math.PI * 2); ctx.stroke();
  }
}

function nearestPoint(ev) {
  const g = plotGeom();
  const r = g.cv.getBoundingClientRect();
  const mx = ev.clientX - r.left, my = ev.clientY - r.top;
  const R = S.plotRange;
  if (!R) return null;
  let best = null, bd = 1e9;
  for (const c of S.points) {
    if (!/^\d+$/.test(c.value || "")) continue;
    const [x, y] = plotXY(g, c, R.xmin, R.xmax, R.ymin, R.ymax, R.log);
    const d = (x - mx) ** 2 + ((y - my) ** 2) * 0.3;
    if (d < bd) { bd = d; best = c; }
  }
  return bd < 900 ? { c: best, mx, my } : null;
}

$("#plot").addEventListener("mousemove", (ev) => {
  const n = nearestPoint(ev);
  const tip = $("#plottip");
  if (!n) { tip.style.display = "none"; return; }
  const nc = S.nByPoint.get(`${n.c.series}:${n.c.point}`);
  tip.innerHTML = `${n.c.angle != null ? "2θ " + n.c.angle.toFixed(2) + "° · " : ""}Durchschnittl. Intensität <b>${n.c.value}</b>` +
    `${nc ? " · n " + nc.value : ""} · ${LABEL[n.c.status]} · Seite ${n.c.page + 1}, Zeile ${n.c.row + 1}`;
  tip.style.display = "block";
  tip.style.left = (n.mx + 12) + "px";
  tip.style.top = (n.my + 40) + "px";
});
$("#plot").addEventListener("mouseleave", () => { $("#plottip").style.display = "none"; });
$("#plot").addEventListener("click", (ev) => {
  const n = nearestPoint(ev);
  if (n) { setView("tabelle"); select(n.c.id); }
});

/* ------------------------------------------------------------------ Ansichten & Tasten */
function setView(v) {
  S.view = v;
  $$("#tabs button").forEach((b) => b.classList.toggle("active", b.dataset.view === v));
  $$(".view").forEach((el) => el.classList.toggle("active", el.id === "view-" + v));
  if (v === "seite") drawPage(true);
  if (v === "diagramm") drawPlot();
  if (v === "tabelle") document.querySelector(".cell.sel")?.scrollIntoView({ block: "nearest" });
}

$$("#tabs button").forEach((b) => b.addEventListener("click", () => setView(b.dataset.view)));
$$("#pagemode button").forEach((b) => b.addEventListener("click", () => setPageMode(b.dataset.mode)));
$("#table").addEventListener("click", (ev) => {
  const el = ev.target.closest(".cell[data-id]");
  if (el) select(el.dataset.id, { scroll: false });
});
$("#table").addEventListener("dblclick", () => { $("#d-input").focus(); $("#d-input").select(); });
$("#onlyflagged").addEventListener("change", () => { renderTable(); });
$("#zoom").addEventListener("input", () => renderTable());
$("#pzoom").addEventListener("input", () => drawPage(true));
$("#contrast").addEventListener("change", () => { renderTable(); renderDetail(); if (S.view === "seite") drawPage(false); });
$("#logscale").addEventListener("change", drawPlot);
$("#nextflag").addEventListener("click", () => { const n = nextOpen(S.sel, 1); n ? select(n.id) : toast("Keine weiteren offenen Punkte."); });
$("#prevflag").addEventListener("click", () => { const n = nextOpen(S.sel, -1); n ? select(n.id) : toast("Keine weiteren offenen Punkte."); });
$("#d-confirm").addEventListener("click", () => commit());
$("#d-reset").addEventListener("click", resetCell);
$("#helpbtn").addEventListener("click", () => { $("#help").hidden = false; });
$("#export").addEventListener("click", () => {
  const s = S.project.summary || {};
  const open = (s.pruefen || 0) + (s.fehler || 0);
  if (open && !confirm(`Es sind noch ${open} Zellen offen. Trotzdem exportieren? (Status steht in der Datei)`)) return;
  window.location = `${API}/export?format=${$("#exportfmt").value}`;
});
window.addEventListener("resize", () => { if (S.view === "diagramm") drawPlot(); });

$("#d-input").addEventListener("keydown", (ev) => {
  if (ev.key === "Enter") { ev.preventDefault(); commit(); }
  else if (ev.key === "Escape") { ev.preventDefault(); const c = S.byId.get(S.sel); ev.target.value = c ? c.value : ""; ev.target.blur(); }
  else if (ev.key === "ArrowUp" || ev.key === "ArrowDown") { ev.preventDefault(); ev.target.blur(); move(ev.key === "ArrowUp" ? -1 : 1, 0); }
  ev.stopPropagation();
});

document.addEventListener("keydown", (ev) => {
  if (ev.target.tagName === "INPUT" && ev.target.type !== "checkbox" && ev.target.type !== "range") return;
  if (ev.ctrlKey || ev.metaKey || ev.altKey) return;
  const k = ev.key;
  if (/^[0-9]$/.test(k) && !ev.shiftKey && S.view !== "diagramm" && S.sel) {
    // Ziffern tippen = Wert überschreiben (Ansichtswechsel daher mit F1..F3)
    const inp = $("#d-input");
    inp.value = k; inp.focus();
    ev.preventDefault();
    return;
  }
  const map = {
    ArrowLeft: () => move(0, -1), ArrowRight: () => move(0, 1), ArrowUp: () => move(-1, 0), ArrowDown: () => move(1, 0),
    Enter: () => commit(), n: () => $("#nextflag").click(), N: () => $("#prevflag").click(),
    v: () => { const b = $("#d-sugbtn"); if (b) b.click(); },
    o: () => setPageMode("overlay"), r: () => setPageMode("original"), s: () => setPageMode("synth"),
    b: () => setPageMode("blink"), d: () => setPageMode("diff"),
    PageDown: () => selectPage(S.page + 1), PageUp: () => selectPage(S.page - 1),
    "?": () => { $("#help").hidden = !$("#help").hidden; }, Escape: () => { $("#help").hidden = true; },
  };
  // Ansichtswechsel mit F1..F3 sowie Umschalt+1..3 (Ziffern allein dienen der Eingabe)
  if (ev.shiftKey && /^Digit[123]$/.test(ev.code)) { setView(["tabelle", "seite", "diagramm"][+ev.code.slice(5) - 1]); ev.preventDefault(); return; }
  if (/^F[123]$/.test(k)) { setView(["tabelle", "seite", "diagramm"][+k.slice(1) - 1]); ev.preventDefault(); return; }
  if (map[k]) { ev.preventDefault(); map[k](); }
});

load().catch((e) => { document.body.innerHTML = `<p style="padding:20px">Projekt konnte nicht geladen werden: ${e}</p>`; });
