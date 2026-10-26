"use strict";
/* Ancora — interface téléphone. JavaScript sans dépendance ni compilation.
   Les montants sont formatés à la française ; une donnée absente n'est jamais affichée comme 0. */

const state = {
  mask: false,
  ringMode: "envelopes",
  marketScope: "watchlist",
  perfPeriod: "1 an",
  chartPeriod: "1 an",
  refreshing: false,
};

const view = document.getElementById("view");
const navbar = document.getElementById("navbar");
const smallTitle = document.getElementById("small-title");
const navLeft = document.getElementById("nav-left");
const refreshBtn = document.getElementById("refresh-btn");
const toastEl = document.getElementById("toast");

// ------------------------------------------------------------------ Formats
const SYMBOLS = { EUR: "€", USD: "$", GBP: "£", CHF: "CHF", JPY: "¥" };
const MONTHS = ["J", "F", "M", "A", "M", "J", "J", "A", "S", "O", "N", "D"];
const formatters = {};

function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}
function num(value, decimals = 2) {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  const key = String(decimals);
  formatters[key] ??= new Intl.NumberFormat("fr-FR", { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
  return formatters[key].format(value);
}
function symbol(currency) { return SYMBOLS[currency] || currency || ""; }
function money(value, currency = "EUR", decimals = 2, { signed = false, na = "—", maskable = true } = {}) {
  if (value === null || value === undefined) return na;
  if (maskable && state.mask) return `•••• ${symbol(currency)}`;
  return `${signed && value > 0 ? "+" : ""}${num(value, decimals)} ${symbol(currency)}`;
}
function pct(value, decimals = 2, signed = true) {
  if (value === null || value === undefined) return "N/A";
  return `${signed && value > 0 ? "+" : ""}${num(value, decimals)} %`;
}
function quantity(value) {
  if (state.mask) return "••••";
  return num(value, Number.isInteger(value) ? 0 : 4);
}
function tone(value) { return value === null || value === undefined || value === 0 ? "" : value > 0 ? "gain" : "loss"; }
function frDate(iso) {
  if (!iso) return "—";
  const [y, m, d] = iso.slice(0, 10).split("-");
  return `${d}/${m}/${y}`;
}
function frDateTime(iso) {
  if (!iso) return "jamais";
  const d = new Date(iso.endsWith("Z") || iso.includes("+") ? iso : `${iso}Z`);
  return d.toLocaleString("fr-FR", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

// ------------------------------------------------------------------ Accès aux données
async function api(path, options = {}) {
  const init = { ...options, headers: { "Content-Type": "application/json", "X-Ancora": "1", ...(options.headers || {}) } };
  const response = await fetch(path, init);
  if (!response.ok) throw new Error(`Erreur ${response.status}`);
  return response.json();
}

function toast(message) {
  toastEl.textContent = message;
  toastEl.classList.add("show");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => toastEl.classList.remove("show"), 2600);
}

// ------------------------------------------------------------------ Composants
const CHEVRON = '<svg class="chevron" viewBox="0 0 8 14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M1 1l6 6-6 6"/></svg>';

function largeTitle(title, subtitle) {
  return `<h1 class="large-title">${esc(title)}</h1>${subtitle ? `<p class="subtitle">${esc(subtitle)}</p>` : ""}`;
}
function segmented(name, options, active) {
  return `<div class="segmented" role="tablist" data-name="${name}">${options.map(([value, label]) =>
    `<button role="tab" aria-selected="${value === active}" class="${value === active ? "active" : ""}" data-value="${esc(value)}">${esc(label)}</button>`).join("")}</div>`;
}
function onSegmented(name, handler) {
  view.querySelectorAll(`.segmented[data-name="${name}"] button`).forEach((button) =>
    button.addEventListener("click", () => handler(button.dataset.value)));
}
function sectionHeader(text) { return `<div class="section-header">${esc(text)}</div>`; }
function sectionFooter(text) { return `<div class="section-footer">${esc(text)}</div>`; }
function skeleton(lines = 5) {
  return `<div style="height:60px"></div>${'<div class="skeleton"></div>'.repeat(lines)}`;
}
function emptyState(title, text) { return `<div class="empty"><b>${esc(title)}</b>${esc(text)}</div>`; }

function ring(items, total) {
  // Anneau de répartition, dans l'esprit du logo : segments séparés par de fines ouvertures.
  const radius = 40;
  const circumference = 2 * Math.PI * radius;
  const gap = items.length > 1 ? 1.4 : 0;
  let offset = 0;
  const segments = items.map((item, index) => {
    const length = Math.max((item.value / total) * circumference - gap, 0.2);
    const svg = `<circle cx="50" cy="50" r="${radius}" fill="none" stroke="var(--ring-${index % 7})" stroke-width="12"
      stroke-dasharray="${length.toFixed(2)} ${circumference.toFixed(2)}" stroke-dashoffset="${(-offset).toFixed(2)}"/>`;
    offset += (item.value / total) * circumference;
    return svg;
  });
  return `<svg viewBox="0 0 100 100" aria-hidden="true">${segments.join("")}</svg>`;
}

function lineChart(points) {
  const width = 340, height = 210, top = 12, bottom = 14;
  const values = points.map((p) => p[1]);
  const min = Math.min(...values), max = Math.max(...values);
  const span = max - min || 1;
  const x = (i) => (i / Math.max(points.length - 1, 1)) * width;
  const y = (v) => top + (1 - (v - min) / span) * (height - top - bottom);
  const line = points.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(p[1]).toFixed(1)}`).join("");
  const area = `${line}L${width},${height}L0,${height}Z`;
  return `<svg viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" style="color:var(--accent)" role="img" aria-label="Évolution du cours">
    <defs><linearGradient id="area-fill" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="currentColor" stop-opacity="0.14"/><stop offset="1" stop-color="currentColor" stop-opacity="0"/>
    </linearGradient></defs>
    <path d="${area}" fill="url(#area-fill)"/>
    <path d="${line}" fill="none" stroke="currentColor" stroke-width="1.8" vector-effect="non-scaling-stroke" stroke-linejoin="round"/>
    <line class="scrub-line" x1="0" x2="0" y1="0" y2="${height}" vector-effect="non-scaling-stroke" visibility="hidden"/>
    <circle class="scrub-dot" r="4" fill="currentColor" visibility="hidden"/>
  </svg>`;
}

// ------------------------------------------------------------------ Navigation
function setNav(title, back) {
  smallTitle.textContent = title;
  navLeft.innerHTML = back
    ? `<button class="nav-btn" id="back-btn"><svg viewBox="0 0 12 22" style="width:12px;height:22px" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M10 2L2 11l8 9"/></svg>${esc(back.label)}</button>`
    : "";
  if (back) {
    document.getElementById("back-btn").addEventListener("click", () => {
      if (navigatedInApp) history.back();
      else location.hash = back.href;
    });
  }
}

window.addEventListener("scroll", () => navbar.classList.toggle("scrolled", window.scrollY > 44), { passive: true });

// ------------------------------------------------------------------ Patrimoine
async function renderPatrimoine() {
  setNav("Patrimoine");
  const d = await api("/api/summary");
  state.mask = d.mask_amounts;
  if (!d.lines) {
    view.innerHTML = largeTitle("Patrimoine") + emptyState("Aucune position",
      "Créez vos enveloppes, instruments et positions depuis Ancora sur ordinateur : ils apparaîtront ici.");
    return;
  }
  const shares = state.ringMode === "envelopes" ? d.by_envelope : d.by_type;
  const total = shares.reduce((sum, s) => sum + s.value, 0) || 1;
  const positions = d.positions.map((p) => `
    <a class="row" href="#/instrument/${p.instrument_id}">
      <div class="main"><div class="title">${esc(p.name)}</div>
        <div class="sub">${esc(p.envelope)} · ${quantity(p.quantity)} titre${p.quantity > 1 ? "s" : ""}</div></div>
      <div class="end"><div class="title">${money(p.value_eur, "EUR", 0, { na: "Non valorisée" })}</div>
        <div class="sub ${tone(p.gain_pct)}">${p.gain_pct === null ? esc(`${p.price_status.emoji} ${p.price_status.label}`) : pct(p.gain_pct)}</div></div>
      ${CHEVRON}
    </a>`).join("");

  view.innerHTML = `
    ${largeTitle("Patrimoine")}
    <section class="hero">
      <div class="caption">Valorisation totale</div>
      <div class="value num">${money(d.value_eur, "EUR", 0)}</div>
      <div class="delta"><span class="${tone(d.gain_eur)}">${money(d.gain_eur, "EUR", 0, { signed: true })} (${pct(d.gain_pct)})</span>
        <span class="muted">plus-value latente</span></div>
    </section>
    ${d.unvalued_lines ? `<div class="notice">${d.unvalued_lines} ligne${d.unvalued_lines > 1 ? "s" : ""} sans cours ou sans taux de change ${d.unvalued_lines > 1 ? "ne sont pas comptées" : "n'est pas comptée"} dans le total.</div>` : ""}
    ${segmented("ring", [["envelopes", "Enveloppes"], ["types", "Types d'actifs"]], state.ringMode)}
    <div class="ring-card">
      <div class="ring-wrap">${ring(shares, total)}
        <div class="ring-center"><span class="k">${shares.length} ${state.ringMode === "envelopes" ? "enveloppe" : "type"}${shares.length > 1 ? "s" : ""}</span>
          <span class="v">${money(d.value_eur, "EUR", 0)}</span></div></div>
      <div class="legend">${shares.map((s, i) => `
        <div class="row"><span class="dot" style="background:var(--ring-${i % 7})"></span>
          <div class="main"><div class="title">${esc(s.label)}</div></div>
          <div class="detail">${num((s.value / total) * 100, 1)} %</div></div>`).join("")}</div>
    </div>
    ${sectionHeader("Positions")}
    <div class="list">${positions}</div>
    ${sectionHeader("Résultats")}
    <div class="list">
      <div class="row"><div class="main"><div class="title">Plus-values réalisées</div></div>
        <div class="detail ${tone(d.realized_eur)}">${money(d.realized_eur, "EUR", 0, { signed: true })}</div></div>
      <div class="row"><div class="main"><div class="title">Revenus sur 12 mois</div></div>
        <div class="detail">${money(d.income_12m_eur, "EUR", 0)}</div></div>
    </div>
    ${sectionFooter(`Données du ${frDateTime(d.last_refresh)}${d.stale_count ? ` · ${d.stale_count} cours à actualiser` : ""}.`)}
  `;
  onSegmented("ring", (value) => { state.ringMode = value; renderPatrimoine(); });
}

// ------------------------------------------------------------------ Marchés
const PERF_OPTIONS = [["1 sem.", "1 S"], ["1 mois", "1 M"], ["6 mois", "6 M"], ["1 an", "1 A"], ["5 ans", "5 A"]];

async function renderMarkets() {
  setNav("Marchés");
  const scopes = [["watchlist", "Suivis"], ["held", "Détenus"], ["indices", "Indices"]];
  const head = `${largeTitle("Marchés")}${segmented("scope", scopes, state.marketScope)}`;
  if (!view.querySelector(".segmented")) view.innerHTML = head + skeleton(6);
  const { items } = await api(`/api/markets?scope=${state.marketScope}`);
  const rows = items.map((item) => {
    const change = item.perf[state.perfPeriod];
    const pillClass = change === null ? "na" : change >= 0 ? "up" : "down";
    return `
      <a class="row" href="#/instrument/${item.id}">
        <div class="main"><div class="title">${esc(item.name)}</div>
          <div class="sub">${esc(item.ticker)}${item.status.code !== "REELLE" ? ` · ${esc(item.status.emoji)} ${esc(item.status.label)}` : ""}</div></div>
        <div class="end"><div class="title">${item.price === null ? esc(item.status.label) : money(item.price, item.currency, 2, { maskable: false })}</div></div>
        <span class="pill ${pillClass}">${pct(change)}</span>
      </a>`;
  }).join("");
  view.innerHTML = `${head}
    ${segmented("period", PERF_OPTIONS, state.perfPeriod)}
    ${items.length ? `<div class="list">${rows}</div>` : emptyState("Aucun instrument", "Ajoutez des instruments depuis Ancora sur ordinateur.")}
    ${sectionFooter("Performance sur la période choisie, calculée sur l'historique réel : N/A si l'historique est insuffisant.")}`;
  onSegmented("scope", (value) => { state.marketScope = value; renderMarkets(); });
  onSegmented("period", (value) => { state.perfPeriod = value; renderMarkets(); });
}

// ------------------------------------------------------------------ Fiche instrument
const CHART_PERIODS = [["1 mois", "1 M", 31], ["6 mois", "6 M", 183], ["1 an", "1 A", 366], ["5 ans", "5 A", 1827], ["10 ans", "10 A", 3653], ["max", "Max", null]];

async function renderInstrument(id) {
  setNav("", { label: "Retour", href: "#/marches" });
  view.innerHTML = skeleton(8);
  const d = await api(`/api/instruments/${id}`);
  setNav(d.name, { label: "Retour", href: "#/marches" });

  const period = CHART_PERIODS.find((p) => p[0] === state.chartPeriod) || CHART_PERIODS[2];
  let points = d.history;
  if (period[2] && points.length) {
    const last = new Date(points[points.length - 1][0]);
    const start = new Date(last.getTime() - period[2] * 86400000).toISOString().slice(0, 10);
    points = points.filter((p) => p[0] >= start);
  }
  const change = period[0] === "max" ? null : d.perf[period[0]];
  const priceText = d.price.value === null ? d.price.status.label : money(d.price.value, d.price.currency, 2, { maskable: false });
  const meta = `${d.price.status.emoji} ${d.price.status.label}${d.price.date ? ` · ${frDate(d.price.date)}` : ""}${d.price.source ? ` · ${d.price.source}` : ""}`;

  const sections = d.sections.map((section) => `
    ${sectionHeader(section.title)}
    <div class="list">${section.rows.map((r) => `
      <div class="row"><div class="main">
          <div class="title">${esc(r["Donnée"])}${r["Exercice"] && r["Exercice"] !== "—" ? ` <span class="muted">${esc(r["Exercice"])}</span>` : ""}</div>
          <div class="sub">${esc(r["Statut"])}${r["Source"] !== "—" ? ` · ${esc(r["Source"])}` : ""}${r["Date de référence"] !== "—" ? ` · ${esc(r["Date de référence"])}` : ""}</div></div>
        <div class="detail">${esc(r["Valeur"])}</div></div>`).join("")}</div>`).join("");

  const identity = [["Type", d.subtype ? `${d.type} · ${d.subtype}` : d.type], ["Ticker", d.ticker], ["ISIN", d.isin],
    ["Place de cotation", d.exchange], ["Devise", d.currency], ["Pays", d.country], ["Société / gestionnaire", d.issuer]]
    .filter(([, v]) => v);

  view.innerHTML = `
    ${largeTitle(d.name, [d.ticker, d.exchange].filter(Boolean).join(" · ") + (d.archived ? " · archivé" : ""))}
    <div class="price-head">
      <div class="value" id="price-value">${esc(priceText)}</div>
      <div class="meta" id="price-meta">${change !== null && change !== undefined ? `<span class="${tone(change)}">${pct(change)}</span> · ` : ""}${esc(meta)}</div>
    </div>
    ${points.length > 1 ? `<div class="chart" id="chart">${lineChart(points)}</div>` : `<div class="notice">Pas d'historique de cours pour cette période.</div>`}
    ${segmented("chart", CHART_PERIODS.map((p) => [p[0], p[1]]), period[0])}
    ${sectionHeader("Performances")}
    <div class="grid">${Object.entries(d.perf).map(([label, value]) =>
      `<div class="cell"><div class="k">${esc(label)}</div><div class="v ${tone(value)}">${pct(value)}</div></div>`).join("")}</div>
    ${sections}
    ${d.not_applicable.length ? sectionFooter(`Non applicable à ce type d'instrument : ${d.not_applicable.join(", ")}.`) : ""}
    ${sectionHeader("Identité")}
    <div class="list">${identity.map(([k, v]) => `<div class="row"><div class="main"><div class="title">${esc(k)}</div></div><div class="detail">${esc(v)}</div></div>`).join("")}</div>
  `;
  onSegmented("chart", (value) => { state.chartPeriod = value; renderInstrument(id); });
  if (points.length > 1) attachScrub(points, d.price.currency, priceText, document.getElementById("price-meta").innerHTML);
}

function attachScrub(points, currency, priceText, metaHtml) {
  const svg = document.querySelector("#chart svg");
  const line = svg.querySelector(".scrub-line");
  const dot = svg.querySelector(".scrub-dot");
  const valueEl = document.getElementById("price-value");
  const metaEl = document.getElementById("price-meta");
  const [, , width, height] = svg.getAttribute("viewBox").split(" ").map(Number);
  const values = points.map((p) => p[1]);
  const min = Math.min(...values), span = (Math.max(...values) - min) || 1;
  const show = (event) => {
    const rect = svg.getBoundingClientRect();
    const ratio = Math.min(Math.max((event.clientX - rect.left) / rect.width, 0), 1);
    const index = Math.round(ratio * (points.length - 1));
    const [day, close] = points[index];
    const x = (index / (points.length - 1)) * width;
    const y = 12 + (1 - (close - min) / span) * (height - 26);
    line.setAttribute("x1", x); line.setAttribute("x2", x); line.setAttribute("visibility", "visible");
    dot.setAttribute("cx", x); dot.setAttribute("cy", y); dot.setAttribute("visibility", "visible");
    const fromStart = (close / points[0][1] - 1) * 100;
    valueEl.textContent = money(close, currency, 2, { maskable: false });
    metaEl.innerHTML = `<span class="${tone(fromStart)}">${pct(fromStart)}</span> · ${frDate(day)}`;
  };
  const hide = () => {
    line.setAttribute("visibility", "hidden"); dot.setAttribute("visibility", "hidden");
    valueEl.textContent = priceText; metaEl.innerHTML = metaHtml;
  };
  svg.addEventListener("pointermove", show);
  svg.addEventListener("pointerdown", show);
  svg.addEventListener("pointerleave", hide);
  svg.addEventListener("pointerup", hide);
  svg.addEventListener("pointercancel", hide);
}

// ------------------------------------------------------------------ Revenus
async function renderIncome() {
  setNav("Revenus");
  const d = await api("/api/income");
  const max = Math.max(...d.months.map((m) => m.value), 1);
  const barWidth = 100 / 12;
  const bars = d.months.map((m, i) => {
    const h = m.value > 0 ? Math.max((m.value / max) * 140, 3) : 0;
    return `<rect x="${(i * barWidth + barWidth * 0.2).toFixed(2)}" y="${(150 - h).toFixed(1)}" width="${(barWidth * 0.6).toFixed(2)}" height="${h.toFixed(1)}" rx="1.5" fill="var(--accent)"/>`;
  }).join("");
  const items = d.items.map((r) => `
    <div class="row"><div class="main"><div class="title">${esc(r.instrument)}</div>
        <div class="sub">${esc(r.type)} · ${frDate(r.date)} · ${esc(r.envelope)}</div></div>
      <div class="end"><div class="title">${money(r.amount, r.currency)}</div>
        ${r.currency !== "EUR" ? `<div class="sub">${money(r.amount_eur, "EUR", 2, { na: "taux indisponible" })}</div>` : ""}</div></div>`).join("");
  view.innerHTML = `
    ${largeTitle("Revenus")}
    <section class="hero">
      <div class="caption">Perçus sur 12 mois</div>
      <div class="value num">${money(d.total_12m, "EUR", 0)}</div>
      <div class="delta"><span class="muted">Dividendes, distributions et coupons</span></div>
    </section>
    ${d.missing_12m ? `<div class="notice">${d.missing_12m} revenu(s) sans taux de change ne sont pas inclus.</div>` : ""}
    <div class="bars"><svg viewBox="0 0 100 150" preserveAspectRatio="none" aria-label="Revenus par mois">${bars}</svg>
      <div class="labels">${d.months.map((m) => `<span>${MONTHS[Number(m.month.slice(5)) - 1]}</span>`).join("")}</div></div>
    ${sectionHeader("Derniers revenus")}
    ${d.items.length ? `<div class="list">${items}</div>` : emptyState("Aucun revenu", "Les dividendes saisis sur ordinateur apparaîtront ici.")}
  `;
}

// ------------------------------------------------------------------ Réglages
async function renderSettings() {
  setNav("Réglages");
  const [summary, quality, refresh] = await Promise.all([api("/api/summary"), api("/api/quality"), api("/api/refresh")]);
  state.mask = summary.mask_amounts;
  const counts = quality.counts.filter((c) => c.count > 0);
  const refreshText = refresh.running
    ? `En cours${refresh.total ? ` · ${refresh.done}/${refresh.total}` : "…"}`
    : "";
  view.innerHTML = `
    ${largeTitle("Réglages")}
    <div class="list">
      <label class="row"><div class="main"><div class="title">Masquer les montants</div></div>
        <span class="switch"><input type="checkbox" id="mask-toggle" ${state.mask ? "checked" : ""}><span></span></span></label>
    </div>
    ${sectionFooter("Les montants sont remplacés par •••• sur le téléphone et sur l'ordinateur.")}
    ${sectionHeader("Données")}
    <div class="list">
      <button class="row" id="refresh-row"><div class="main"><div class="title" style="color:var(--accent);font-weight:600">Actualiser maintenant</div></div>
        <div class="detail" id="refresh-progress">${esc(refreshText)}</div></button>
      <div class="row"><div class="main"><div class="title">Actualisé le</div></div>
        <div class="detail">${frDateTime(summary.last_refresh)}</div></div>
    </div>
    ${sectionFooter("Seuls les symboles des instruments sont envoyés aux fournisseurs de cours, jamais vos positions.")}
    ${sectionHeader("Qualité des données")}
    <div class="list">${counts.map((c) => `
      <div class="row"><div class="main"><div class="title">${esc(c.emoji)} ${esc(c.label)}</div></div>
        <div class="detail">${c.count}</div></div>`).join("") || '<div class="row"><div class="main"><div class="title muted">Aucune donnée collectée</div></div></div>'}</div>
    ${quality.errors.length ? `${sectionHeader("Erreurs récentes")}<div class="list">${quality.errors.map((e) => `
      <div class="row"><div class="main"><div class="title">${esc(e.instrument)}</div>
        <div class="sub" style="white-space:normal">${esc(e.message)}</div></div></div>`).join("")}</div>` : ""}
    ${sectionHeader("À propos")}
    <div class="list">
      <div class="row"><div class="main"><div class="title">Ancora</div></div><div class="detail">Version téléphone 1.0</div></div>
    </div>
    ${sectionFooter("La saisie des opérations et l'administration se font dans Ancora sur ordinateur. Ancora n'est pas un outil de conseil en investissement.")}
  `;
  document.getElementById("mask-toggle").addEventListener("change", async (event) => {
    state.mask = event.target.checked;
    await api("/api/preferences", { method: "PUT", body: JSON.stringify({ mask_amounts: state.mask }) });
    toast(state.mask ? "Montants masqués" : "Montants affichés");
  });
  document.getElementById("refresh-row").addEventListener("click", startRefresh);
}

// ------------------------------------------------------------------ Actualisation (en arrière-plan)
function setRefreshing(running, progress) {
  state.refreshing = running;
  refreshBtn.classList.toggle("spinning", running);
  const el = document.getElementById("refresh-progress");
  if (el) el.textContent = running ? (progress || "En cours…") : "";
}

async function pollRefresh() {
  const s = await api("/api/refresh");
  if (s.running) {
    setRefreshing(true, s.total ? `${s.done}/${s.total}` : "En cours…");
    setTimeout(pollRefresh, 1500);
    return;
  }
  setRefreshing(false);
  toast(s.errors.length ? `Actualisé · ${s.errors.length} erreur${s.errors.length > 1 ? "s" : ""}` : "Données actualisées");
  route();
}

async function startRefresh() {
  if (state.refreshing) return;
  setRefreshing(true);
  try {
    await api("/api/refresh", { method: "POST" });
    setTimeout(pollRefresh, 800);
  } catch (error) {
    setRefreshing(false);
    toast("Actualisation impossible");
  }
}
refreshBtn.addEventListener("click", startRefresh);

// ------------------------------------------------------------------ Routeur
const ROUTES = [
  [/^#?\/?$/, () => renderPatrimoine(), "patrimoine"],
  [/^#\/marches$/, () => renderMarkets(), "marches"],
  [/^#\/instrument\/(\d+)$/, (m) => renderInstrument(m[1]), "marches"],
  [/^#\/revenus$/, () => renderIncome(), "revenus"],
  [/^#\/reglages$/, () => renderSettings(), "reglages"],
];

let lastHash = null;
let navigatedInApp = false;
async function route() {
  const hash = location.hash || "#/";
  const [pattern, render, tab] = ROUTES.find(([p]) => p.test(hash)) || ROUTES[0];
  document.querySelectorAll(".tabbar a").forEach((a) => a.classList.toggle("active", a.dataset.tab === tab));
  if (hash !== lastHash) { window.scrollTo(0, 0); view.innerHTML = skeleton(); }
  lastHash = hash;
  try {
    await render(hash.match(pattern));
  } catch (error) {
    view.innerHTML = emptyState("Ancora est injoignable", "Vérifiez que l'ordinateur qui héberge Ancora est allumé, puis réessayez.");
  }
}

window.addEventListener("hashchange", () => { navigatedInApp = true; route(); });
api("/api/refresh").then((s) => { if (s.running) { setRefreshing(true); setTimeout(pollRefresh, 1500); } }).catch(() => {});
route();
