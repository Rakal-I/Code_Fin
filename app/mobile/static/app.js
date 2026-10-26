"use strict";
/* Ancora — interface téléphone (« Liquid Glass »). JavaScript sans dépendance ni compilation.
   Graphiques dans la DA du logo : un seul ton, opacités 100 / 62 / 34 %, extrémités arrondies.
   Les montants sont formatés à la française ; une donnée absente n'est jamais affichée comme 0. */

const state = {
  mask: false,
  ringMode: "envelopes",
  marketScope: "watchlist",
  perfPeriod: "1 an",
  chartPeriod: "1 an",
  query: "",
  refreshing: false,
};

const $ = (id) => document.getElementById(id);
const view = $("view");
const navbar = $("navbar");
const tabbar = $("tabbar");

// ------------------------------------------------------------------ Formats
const SYMBOLS = { EUR: "€", USD: "$", GBP: "£", CHF: "CHF", JPY: "¥" };
const MONTHS = ["J", "F", "M", "A", "M", "J", "J", "A", "S", "O", "N", "D"];
const MONTH_NAMES = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"];
const RING_OPACITY = [1, 0.62, 0.34, 0.2, 0.12, 0.07]; // celles du logo, prolongées
const formatters = {};

function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}
function num(value, decimals = 2) {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  formatters[decimals] ??= new Intl.NumberFormat("fr-FR", { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
  return formatters[decimals].format(value);
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
function quantity(value) { return state.mask ? "••••" : num(value, Number.isInteger(value) ? 0 : 4); }
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
const ringOpacity = (i) => RING_OPACITY[Math.min(i, RING_OPACITY.length - 1)];

// ------------------------------------------------------------------ Données
class ApiError extends Error {
  constructor(status, detail) { super(detail || `Erreur ${status}`); this.status = status; }
}

async function api(path, options = {}) {
  const init = { ...options, credentials: "same-origin",
    headers: { "Content-Type": "application/json", "X-Ancora": "1", ...(options.headers || {}) } };
  const response = await fetch(path, init);
  if (!response.ok) {
    const detail = await response.json().then((body) => body.detail).catch(() => null);
    if (response.status === 401 && !path.startsWith("/api/auth/")) showLogin("Votre session a expiré : reconnectez-vous.");
    throw new ApiError(response.status, detail);
  }
  return response.json();
}

// ------------------------------------------------------------------ Connexion
const APP_ICON = '<img class="app-icon" src="icons/apple-touch-icon.png" alt="">';

function lock() {
  document.body.classList.add("locked");
  $("small-title").textContent = "";
  navbar.classList.remove("scrolled");
  window.scrollTo(0, 0);
}

function showSetupHint() {
  lock();
  view.innerHTML = `<div class="login"><div class="login-card glass">${APP_ICON}
    <h1>Bienvenue</h1><p class="lead">Créez d'abord votre compte dans Ancora sur l'ordinateur
    (avec Apple, Google ou un mot de passe), puis revenez ici pour vous connecter.</p>
    <button class="primary" id="retry">J'ai créé mon compte</button></div></div>`;
  $("retry").addEventListener("click", boot);
}

// Face ID / Touch ID : clés d'accès (script commun /connexion/cle.js).
const FACE_ID_ICON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 8V6a2 2 0 0 1 2-2h2M16 4h2a2 2 0 0 1 2 2v2M20 16v2a2 2 0 0 1-2 2h-2M8 20H6a2 2 0 0 1-2-2v-2"/><path d="M9 9v1.5M15 9v1.5M12 9v4h-1"/><path d="M9.5 16a3.5 3.5 0 0 0 5 0"/></svg>';
const passkeyReady = () => !!(window.AncoraPasskey && AncoraPasskey.supported());
const OFFER_KEY = "ancora-faceid-propose";

async function loginWithPasskey(button) {
  const error = $("login-error");
  button.disabled = true;
  error.textContent = "";
  try {
    await AncoraPasskey.login();
    unlock();
  } catch (e) {
    error.textContent = AncoraPasskey.friendly(e);
    button.disabled = false;
  }
}

async function enablePasskey() {
  try {
    await AncoraPasskey.register();
    toast(`Activé : connexion avec ${AncoraPasskey.label()}`);
    return true;
  } catch (e) {
    toast(AncoraPasskey.friendly(e));
    return false;
  }
}

// Après une connexion par mot de passe : proposer Face ID une fois (si l'appareil le permet).
async function offerPasskey() {
  if (!passkeyReady()) return;
  try { if (localStorage.getItem(OFFER_KEY)) return; } catch (e) { /* navigation privée */ }
  const status = await api("/api/auth/status").catch(() => null);
  if (!status || status.passkeys > 0) return;
  const name = AncoraPasskey.label();
  const sheet = document.createElement("div");
  sheet.className = "sheet-backdrop";
  sheet.innerHTML = `<div class="sheet glass" role="dialog" aria-modal="true" aria-labelledby="sheet-title">
      <div class="sheet-icon">${FACE_ID_ICON}</div>
      <h2 id="sheet-title">Se connecter avec ${esc(name)} ?</h2>
      <p>La prochaine fois, un regard suffit. Votre mot de passe reste valable en secours.</p>
      <button class="primary" id="sheet-yes">Activer ${esc(name)}</button>
      <button class="sheet-later" id="sheet-no">Plus tard</button>
    </div>`;
  document.body.appendChild(sheet);
  requestAnimationFrame(() => sheet.classList.add("show"));
  const close = () => {
    try { localStorage.setItem(OFFER_KEY, "1"); } catch (e) { /* ignoré */ }
    sheet.classList.remove("show");
    setTimeout(() => sheet.remove(), 300);
  };
  $("sheet-no").addEventListener("click", close);
  $("sheet-yes").addEventListener("click", async () => { if (await enablePasskey()) close(); });
}

function showLogin(message = "") {
  if (document.body.classList.contains("locked") && $("login-form")) return;
  lock();
  view.innerHTML = `<div class="login view-enter">
    <form class="login-card glass" id="login-form" novalidate>
      ${APP_ICON}
      <h1>Ancora</h1>
      <p class="lead">Connectez-vous pour accéder à votre patrimoine.</p>
      ${passkeyReady() ? `<button type="button" class="faceid-btn" id="faceid-login">${FACE_ID_ICON}<span>Se connecter avec ${esc(AncoraPasskey.label())}</span></button>
      <div class="or">ou avec votre mot de passe</div>` : ""}
      <label class="field"><span>Identifiant</span>
        <input name="username" autocomplete="username" autocapitalize="none" autocorrect="off" spellcheck="false" required></label>
      <label class="field"><span>Mot de passe</span>
        <input name="password" type="password" autocomplete="current-password" required></label>
      <button class="primary" type="submit" id="login-submit">Se connecter</button>
      <p class="login-error" id="login-error" role="alert">${esc(message)}</p>
    </form>
    <p class="login-foot">Vos données restent chiffrées sur votre ordinateur. Face ID reste sur votre iPhone : Ancora ne reçoit ni votre visage ni votre empreinte.</p>
  </div>`;
  const form = $("login-form");
  if ($("faceid-login")) $("faceid-login").addEventListener("click", (event) => loginWithPasskey(event.currentTarget));
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = $("login-submit");
    button.disabled = true;
    button.textContent = "Connexion…";
    try {
      await api("/api/auth/login", { method: "POST",
        body: JSON.stringify({ username: form.username.value, password: form.password.value }) });
      unlock();
      setTimeout(offerPasskey, 600);
    } catch (error) {
      $("login-error").textContent = error.message;
      form.classList.remove("shake"); void form.offsetWidth; form.classList.add("shake");
      form.password.value = "";
      button.disabled = false;
      button.textContent = "Se connecter";
    }
  });
}

function unlock() {
  document.body.classList.remove("locked");
  lastHash = null;
  route();
  requestAnimationFrame(placeLens);
}

async function logout() {
  await api("/api/auth/logout", { method: "POST" }).catch(() => {});
  showLogin("Vous êtes déconnecté.");
}

async function boot() {
  try {
    const status = await api("/api/auth/status");
    if (!status.configured) return showSetupHint();
    if (!status.authenticated) return showLogin();
    unlock();
    api("/api/refresh").then((s) => { if (s.running) { setRefreshing(true); setTimeout(pollRefresh, 1500); } }).catch(() => {});
  } catch (error) {
    view.innerHTML = emptyState("Ancora est injoignable", "Vérifiez que l'ordinateur qui héberge Ancora est allumé, puis réessayez.");
  }
}

function toast(message) {
  const el = $("toast");
  el.textContent = message;
  el.classList.add("show");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => el.classList.remove("show"), 2600);
}

// ------------------------------------------------------------------ Composants
const CHEVRON = '<svg class="chevron" viewBox="0 0 8 14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M1 1l6 6-6 6"/></svg>';
const SEARCH_ICON = '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><circle cx="8.5" cy="8.5" r="6"/><path d="M13 13l4.5 4.5"/></svg>';

function largeTitle(title, subtitle) {
  return `<h1 class="large-title">${esc(title)}</h1>${subtitle ? `<p class="subtitle">${esc(subtitle)}</p>` : ""}`;
}
function sectionHeader(text) { return `<div class="section-header">${esc(text)}</div>`; }
function sectionFooter(text) { return `<div class="section-footer">${esc(text)}</div>`; }
function skeleton(lines = 5) { return `<div style="height:60px"></div>${'<div class="skeleton"></div>'.repeat(lines)}`; }
function emptyState(title, text) { return `<div class="empty"><b>${esc(title)}</b>${esc(text)}</div>`; }

/* Contrôle segmenté : un curseur en verre glisse sous l'option choisie. */
function segmented(name, options, active) {
  return `<div class="segmented" role="tablist" data-name="${name}"><span class="thumb"></span>${options.map(([value, label]) =>
    `<button role="tab" aria-selected="${value === active}" class="${value === active ? "active" : ""}" data-value="${esc(value)}">${esc(label)}</button>`).join("")}</div>`;
}
function placeThumb(control) {
  const active = control.querySelector("button.active");
  const thumb = control.querySelector(".thumb");
  if (!active || !thumb) return;
  thumb.style.width = `${active.offsetWidth}px`;
  thumb.style.transform = `translateX(${active.offsetLeft}px)`;
}
function bindSegmented(name, onChange) {
  const control = view.querySelector(`.segmented[data-name="${name}"]`);
  if (!control) return;
  const thumb = control.querySelector(".thumb");
  thumb.style.transition = "none";
  placeThumb(control);
  requestAnimationFrame(() => { thumb.style.transition = ""; });
  control.querySelectorAll("button").forEach((button) => button.addEventListener("click", () => {
    control.querySelectorAll("button").forEach((b) => { b.classList.toggle("active", b === button); b.setAttribute("aria-selected", b === button); });
    placeThumb(control);
    onChange(button.dataset.value);
  }));
}

/* Anneau de répartition, dessiné comme le logo. Toucher un segment ou une ligne l'isole. */
function ringSVG(items) {
  const radius = 41.5, stroke = 15;
  const circumference = 2 * Math.PI * radius;
  const total = items.reduce((sum, i) => sum + i.value, 0) || 1;
  const gap = items.length > 1 ? circumference * 0.015 : 0;
  let start = 0;
  const segments = items.map((item, index) => {
    const arc = (item.value / total) * circumference;
    const dash = items.length > 1 ? Math.max(arc - gap - stroke, 0.01) : circumference;
    const angle = items.length > 1 ? ((start + (gap + stroke) / 2) / circumference) * 360 : 0;
    start += arc;
    return `<circle class="seg" data-i="${index}" cx="50" cy="50" r="${radius}" fill="none" stroke="var(--accent)"
      stroke-opacity="${ringOpacity(index)}" stroke-width="${stroke}" stroke-linecap="round"
      data-dash="${dash.toFixed(2)} ${circumference.toFixed(2)}" style="stroke-dasharray:0 ${circumference.toFixed(2)};transition:stroke-dasharray .9s cubic-bezier(.2,.9,.3,1) ${index * 0.06}s"
      transform="rotate(${angle.toFixed(2)} 50 50)"/>`;
  });
  return `<svg viewBox="0 0 100 100" aria-hidden="true">${segments.join("")}</svg>`;
}
function drawRing(wrap) {
  requestAnimationFrame(() => wrap.querySelectorAll(".seg").forEach((seg) => { seg.style.strokeDasharray = seg.dataset.dash; }));
}

function lineChart(points) {
  const width = 340, height = 220, top = 14, bottom = 16;
  const values = points.map((p) => p[1]);
  const min = Math.min(...values), max = Math.max(...values);
  const span = max - min || 1;
  const x = (i) => (i / Math.max(points.length - 1, 1)) * width;
  const y = (v) => top + (1 - (v - min) / span) * (height - top - bottom);
  const line = points.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(p[1]).toFixed(1)}`).join("");
  const last = points[points.length - 1];
  return `<svg viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" style="color:var(--accent)" role="img" aria-label="Évolution du cours">
    <defs><linearGradient id="area-fill" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="currentColor" stop-opacity="0.16"/><stop offset="1" stop-color="currentColor" stop-opacity="0"/>
    </linearGradient></defs>
    <path d="${line}L${width},${height}L0,${height}Z" fill="url(#area-fill)"/>
    <path d="${line}" fill="none" stroke="currentColor" stroke-width="2.2" vector-effect="non-scaling-stroke" stroke-linejoin="round" stroke-linecap="round"/>
    <circle cx="${x(points.length - 1).toFixed(1)}" cy="${y(last[1]).toFixed(1)}" r="4.5" fill="currentColor" stroke="var(--bg)" stroke-width="2" vector-effect="non-scaling-stroke"/>
    <line class="scrub-line" x1="0" x2="0" y1="0" y2="${height}" vector-effect="non-scaling-stroke" visibility="hidden"/>
    <circle class="scrub-dot" r="5" fill="currentColor" stroke="var(--bg)" stroke-width="2" visibility="hidden"/>
  </svg>`;
}

// ------------------------------------------------------------------ Navigation
let navigatedInApp = false;

function setNav(title, back) {
  $("small-title").textContent = title;
  $("nav-left").innerHTML = back
    ? `<button class="glass-btn" id="back-btn" aria-label="${esc(back.label)}"><svg viewBox="0 0 12 22" style="width:11px;height:20px" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M10 2L2 11l8 9"/></svg></button>`
    : "";
  if (back) {
    $("back-btn").addEventListener("click", () => {
      if (navigatedInApp) history.back();
      else location.hash = back.href;
    });
  }
}

function placeLens() {
  const active = tabbar.querySelector("a.active");
  const lens = $("tab-lens");
  if (!active) return;
  lens.style.width = `${active.offsetWidth}px`;
  lens.style.transform = `translateX(${active.offsetLeft}px)`;
}

let lastY = 0;
window.addEventListener("scroll", () => {
  const y = window.scrollY;
  navbar.classList.toggle("scrolled", y > 44);
  const compact = y > 120 && y > lastY;
  if (compact !== tabbar.classList.contains("compact") && Math.abs(y - lastY) > 4) {
    tabbar.classList.toggle("compact", compact);
    setTimeout(placeLens, 0);
    setTimeout(placeLens, 380);
  }
  lastY = y;
}, { passive: true });
window.addEventListener("resize", placeLens);

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
  const total = d.value_eur || 1;
  const positions = d.positions.map((p) => {
    const weight = p.value_eur === null ? 0 : (p.value_eur / total) * 100;
    return `
    <a class="row" href="#/instrument/${p.instrument_id}">
      <div class="main"><div class="title">${esc(p.name)}</div>
        <div class="sub">${esc(p.envelope)} · ${quantity(p.quantity)} titre${p.quantity > 1 ? "s" : ""} · ${num(weight, 1)} %</div>
        <div class="weight"><span style="width:${Math.max(weight, 0.5).toFixed(1)}%"></span></div></div>
      <div class="end"><div class="title">${money(p.value_eur, "EUR", 0, { na: "Non valorisée" })}</div>
        <div class="sub ${tone(p.gain_pct)}">${p.gain_pct === null ? esc(`${p.price_status.emoji} ${p.price_status.label}`) : pct(p.gain_pct)}</div></div>
      ${CHEVRON}
    </a>`;
  }).join("");

  view.innerHTML = `
    ${largeTitle("Patrimoine")}
    <section class="hero-card">
      <div class="caption">Valorisation totale</div>
      <div class="value num">${money(d.value_eur, "EUR", 0)}</div>
      <div class="delta"><span class="${tone(d.gain_eur)}">${money(d.gain_eur, "EUR", 0, { signed: true })} (${pct(d.gain_pct)})</span>
        <span class="muted">plus-value latente</span></div>
      <div class="chips">
        <span class="chip">Réalisé <b class="${tone(d.realized_eur)}">${money(d.realized_eur, "EUR", 0, { signed: true })}</b></span>
        <span class="chip">Revenus 12 mois <b>${money(d.income_12m_eur, "EUR", 0)}</b></span>
      </div>
    </section>
    ${d.unvalued_lines ? `<div class="notice">${d.unvalued_lines} ligne${d.unvalued_lines > 1 ? "s" : ""} sans cours ou sans taux de change ${d.unvalued_lines > 1 ? "ne sont pas comptées" : "n'est pas comptée"} dans le total.</div>` : ""}
    ${segmented("ring", [["envelopes", "Enveloppes"], ["types", "Types d'actifs"]], state.ringMode)}
    <div class="ring-card" id="ring-card"></div>
    ${sectionHeader("Positions")}
    <div class="list">${positions}</div>
    ${sectionFooter(`Données du ${frDateTime(d.last_refresh)}${d.stale_count ? ` · ${d.stale_count} cours à actualiser` : ""}.`)}
  `;
  const drawCard = () => renderRingCard($("ring-card"), state.ringMode === "envelopes" ? d.by_envelope : d.by_type, d.value_eur);
  drawCard();
  bindSegmented("ring", (value) => { state.ringMode = value; drawCard(); });
}

function renderRingCard(card, shares, totalValue) {
  const total = shares.reduce((sum, s) => sum + s.value, 0) || 1;
  const caption = `${shares.length} ${state.ringMode === "envelopes" ? "enveloppe" : "type"}${shares.length > 1 ? "s" : ""}`;
  card.innerHTML = `
    <div class="ring-wrap" id="ring-wrap">${ringSVG(shares)}
      <div class="ring-center"><span class="k" id="ring-k">${esc(caption)}</span>
        <span class="v" id="ring-v">${money(totalValue, "EUR", 0)}</span><span class="p" id="ring-p"></span></div></div>
    <div class="legend">${shares.map((s, i) => `
      <div class="row" data-i="${i}"><span class="dot" style="opacity:${ringOpacity(i)}"></span>
        <div class="main"><div class="title">${esc(s.label)}</div></div>
        <div class="detail">${money(s.value, "EUR", 0)}</div>
        <div class="detail" style="min-width:52px;color:var(--label);font-weight:600">${num((s.value / total) * 100, 1)} %</div></div>`).join("")}</div>`;
  const wrap = $("ring-wrap");
  drawRing(wrap);
  let focused = null;
  const focus = (index) => {
    focused = focused === index ? null : index;
    wrap.classList.toggle("focused", focused !== null);
    wrap.querySelectorAll(".seg").forEach((seg) => seg.classList.toggle("on", Number(seg.dataset.i) === focused));
    card.querySelectorAll(".legend .row").forEach((row) => row.classList.toggle("on", Number(row.dataset.i) === focused));
    const share = focused === null ? null : shares[focused];
    $("ring-k").textContent = share ? share.label : caption;
    $("ring-v").textContent = share ? money(share.value, "EUR", 0) : money(totalValue, "EUR", 0);
    $("ring-p").textContent = share ? `${num((share.value / total) * 100, 1)} %` : "";
  };
  card.querySelectorAll(".seg, .legend .row").forEach((el) => el.addEventListener("click", () => focus(Number(el.dataset.i))));
}

// ------------------------------------------------------------------ Marchés
const PERF_OPTIONS = [["1 sem.", "1 S"], ["1 mois", "1 M"], ["6 mois", "6 M"], ["1 an", "1 A"], ["5 ans", "5 A"]];

async function renderMarkets() {
  setNav("Marchés");
  view.innerHTML = `
    ${largeTitle("Marchés")}
    <label class="search">${SEARCH_ICON}<input id="search" type="search" placeholder="Rechercher" value="${esc(state.query)}" autocomplete="off"></label>
    ${segmented("scope", [["watchlist", "Suivis"], ["held", "Détenus"], ["indices", "Indices"]], state.marketScope)}
    ${segmented("period", PERF_OPTIONS, state.perfPeriod)}
    <div id="market-list">${'<div class="skeleton"></div>'.repeat(6)}</div>
    ${sectionFooter("Performance sur la période choisie, calculée sur l'historique réel : N/A si l'historique est insuffisant.")}`;
  let items = [];
  const draw = () => {
    const needle = state.query.trim().toLowerCase();
    const shown = items.filter((i) => !needle || `${i.name} ${i.ticker}`.toLowerCase().includes(needle));
    $("market-list").innerHTML = shown.length ? `<div class="list">${shown.map((item) => {
      const change = item.perf[state.perfPeriod];
      const pillClass = change === null ? "" : change >= 0 ? "up" : "down";
      return `
        <a class="row" href="#/instrument/${item.id}">
          <div class="main"><div class="title">${esc(item.name)}</div>
            <div class="sub">${esc(item.ticker)}${item.status.code !== "REELLE" ? ` · ${esc(item.status.emoji)} ${esc(item.status.label)}` : ""}</div></div>
          <div class="end"><div class="title">${item.price === null ? esc(item.status.label) : money(item.price, item.currency, 2, { maskable: false })}</div></div>
          <span class="pill ${pillClass}">${pct(change)}</span>
        </a>`;
    }).join("")}</div>` : emptyState("Aucun résultat", needle ? "Aucun instrument ne correspond à cette recherche." : "Ajoutez des instruments depuis Ancora sur ordinateur.");
  };
  const load = async () => { items = (await api(`/api/markets?scope=${state.marketScope}`)).items; draw(); };
  bindSegmented("scope", (value) => { state.marketScope = value; load(); });
  bindSegmented("period", (value) => { state.perfPeriod = value; draw(); });
  $("search").addEventListener("input", (event) => { state.query = event.target.value; draw(); });
  await load();
}

// ------------------------------------------------------------------ Fiche instrument
const CHART_PERIODS = [["1 mois", "1 M", 31], ["6 mois", "6 M", 183], ["1 an", "1 A", 366], ["5 ans", "5 A", 1827], ["10 ans", "10 A", 3653], ["max", "Max", null]];

async function renderInstrument(id) {
  setNav("", { label: "Retour", href: "#/marches" });
  const d = await api(`/api/instruments/${id}`);
  setNav(d.name, { label: "Retour", href: "#/marches" });
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
      <div class="meta" id="price-meta"></div>
    </div>
    <div class="chart-card">
      <div class="chart" id="chart"></div>
      ${segmented("chart", CHART_PERIODS.map((p) => [p[0], p[1]]), state.chartPeriod)}
    </div>
    ${sectionHeader("Performances")}
    <div class="grid">${Object.entries(d.perf).map(([label, value]) =>
      `<div class="cell"><div class="k">${esc(label)}</div><div class="v ${tone(value)}">${pct(value)}</div></div>`).join("")}</div>
    ${sections}
    ${d.not_applicable.length ? sectionFooter(`Non applicable à ce type d'instrument : ${d.not_applicable.join(", ")}.`) : ""}
    ${sectionHeader("Identité")}
    <div class="list">${identity.map(([k, v]) => `<div class="row"><div class="main"><div class="title">${esc(k)}</div></div><div class="detail">${esc(v)}</div></div>`).join("")}</div>
  `;

  const drawChart = () => {
    const period = CHART_PERIODS.find((p) => p[0] === state.chartPeriod) || CHART_PERIODS[2];
    let points = d.history;
    if (period[2] && points.length) {
      const last = new Date(points[points.length - 1][0]);
      const start = new Date(last.getTime() - period[2] * 86400000).toISOString().slice(0, 10);
      points = points.filter((p) => p[0] >= start);
    }
    const change = period[0] === "max" ? null : d.perf[period[0]];
    const metaHtml = `${change !== null && change !== undefined ? `<span class="${tone(change)}">${pct(change)}</span> · ` : ""}${esc(meta)}`;
    $("price-meta").innerHTML = metaHtml;
    $("price-value").textContent = priceText;
    const chart = $("chart");
    if (points.length > 1) {
      chart.innerHTML = lineChart(points);
      attachScrub(points, d.price.currency, priceText, metaHtml);
    } else {
      chart.innerHTML = '<div class="empty" style="padding:40px 20px">Pas d\'historique pour cette période.</div>';
    }
  };
  drawChart();
  bindSegmented("chart", (value) => { state.chartPeriod = value; drawChart(); });
}

function attachScrub(points, currency, priceText, metaHtml) {
  const svg = document.querySelector("#chart svg");
  const line = svg.querySelector(".scrub-line");
  const dot = svg.querySelector(".scrub-dot");
  const valueEl = $("price-value"), metaEl = $("price-meta");
  const [, , width, height] = svg.getAttribute("viewBox").split(" ").map(Number);
  const values = points.map((p) => p[1]);
  const min = Math.min(...values), span = (Math.max(...values) - min) || 1;
  const show = (event) => {
    const rect = svg.getBoundingClientRect();
    const ratio = Math.min(Math.max((event.clientX - rect.left) / rect.width, 0), 1);
    const index = Math.round(ratio * (points.length - 1));
    const [day, close] = points[index];
    const x = (index / (points.length - 1)) * width;
    const y = 14 + (1 - (close - min) / span) * (height - 30);
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
  ["pointerleave", "pointerup", "pointercancel"].forEach((type) => svg.addEventListener(type, hide));
}

// ------------------------------------------------------------------ Revenus
async function renderIncome() {
  setNav("Revenus");
  const d = await api("/api/income");
  const max = Math.max(...d.months.map((m) => m.value), 1);
  const slot = 100 / 12, barWidth = slot * 0.46;
  let selected = d.months.map((m) => m.value > 0).lastIndexOf(true);
  const bars = d.months.map((m, i) => {
    const h = m.value > 0 ? Math.max((m.value / max) * 140, barWidth) : 0;
    return `<rect class="bar" data-i="${i}" x="${(i * slot + (slot - barWidth) / 2).toFixed(2)}" y="${(150 - h).toFixed(1)}" width="${barWidth.toFixed(2)}" height="${h.toFixed(1)}" rx="${(barWidth / 2).toFixed(2)}" fill="var(--accent)"/>
      <rect data-i="${i}" class="hit" x="${(i * slot).toFixed(2)}" y="0" width="${slot.toFixed(2)}" height="150" fill="transparent"/>`;
  }).join("");
  const items = d.items.map((r) => `
    <div class="row"><div class="main"><div class="title">${esc(r.instrument)}</div>
        <div class="sub">${esc(r.type)} · ${frDate(r.date)} · ${esc(r.envelope)}</div></div>
      <div class="end"><div class="title">${money(r.amount, r.currency)}</div>
        ${r.currency !== "EUR" ? `<div class="sub">${money(r.amount_eur, "EUR", 2, { na: "taux indisponible" })}</div>` : ""}</div></div>`).join("");
  view.innerHTML = `
    ${largeTitle("Revenus")}
    <section class="hero-card">
      <div class="caption">Perçus sur 12 mois</div>
      <div class="value num">${money(d.total_12m, "EUR", 0)}</div>
      <div class="delta"><span class="muted">Dividendes, distributions et coupons</span></div>
    </section>
    ${d.missing_12m ? `<div class="notice">${d.missing_12m} revenu(s) sans taux de change ne sont pas inclus.</div>` : ""}
    <div class="bars">
      <div class="readout" id="readout"></div>
      <svg viewBox="0 0 100 150" preserveAspectRatio="none" aria-label="Revenus par mois">${bars}</svg>
      <div class="labels">${d.months.map((m) => `<span>${MONTHS[Number(m.month.slice(5)) - 1]}</span>`).join("")}</div></div>
    ${sectionHeader("Derniers revenus")}
    ${d.items.length ? `<div class="list">${items}</div>` : emptyState("Aucun revenu", "Les dividendes saisis sur ordinateur apparaîtront ici.")}
  `;
  const select = (index) => {
    selected = index;
    view.querySelectorAll(".bars .bar").forEach((bar) => bar.setAttribute("fill-opacity", Number(bar.dataset.i) === selected ? 1 : 0.34));
    const m = d.months[selected];
    if (!m) { $("readout").textContent = "Touchez un mois pour voir son montant."; return; }
    const [y, mo] = m.month.split("-");
    $("readout").innerHTML = `${MONTH_NAMES[Number(mo) - 1]} ${y} · <b>${money(m.value, "EUR", 2)}</b>`;
  };
  view.querySelectorAll(".bars .hit").forEach((hit) => hit.addEventListener("click", () => select(Number(hit.dataset.i))));
  select(selected);
}

// ------------------------------------------------------------------ Réglages
async function renderSettings() {
  setNav("Réglages");
  const [summary, quality, refresh, auth] = await Promise.all([
    api("/api/summary"), api("/api/quality"), api("/api/refresh"), api("/api/auth/status")]);
  state.mask = summary.mask_amounts;
  const counts = quality.counts.filter((c) => c.count > 0);
  view.innerHTML = `
    ${largeTitle("Réglages")}
    <div class="list">
      <label class="row"><div class="main"><div class="title">Masquer les montants</div></div>
        <span class="switch"><input type="checkbox" id="mask-toggle" ${state.mask ? "checked" : ""}><span></span></span></label>
    </div>
    ${sectionFooter("Les montants sont remplacés par •••• sur le téléphone et sur l'ordinateur.")}
    ${sectionHeader("Données")}
    <div class="list">
      <button class="row" id="refresh-row"><div class="main"><div class="title" style="font-weight:650">Actualiser maintenant</div></div>
        <div class="detail" id="refresh-progress">${refresh.running ? `En cours${refresh.total ? ` · ${refresh.done}/${refresh.total}` : "…"}` : ""}</div></button>
      <div class="row"><div class="main"><div class="title">Actualisé le</div></div><div class="detail">${frDateTime(summary.last_refresh)}</div></div>
    </div>
    ${sectionFooter("Astuce : tirez l'écran vers le bas pour actualiser. Seuls les symboles des instruments sont envoyés aux fournisseurs, jamais vos positions.")}
    ${sectionHeader("Qualité des données")}
    <div class="list">${counts.map((c) => `
      <div class="row"><div class="main"><div class="title">${esc(c.emoji)} ${esc(c.label)}</div></div><div class="detail">${c.count}</div></div>`).join("")
      || '<div class="row"><div class="main"><div class="title muted">Aucune donnée collectée</div></div></div>'}</div>
    ${quality.errors.length ? `${sectionHeader("Erreurs récentes")}<div class="list">${quality.errors.map((e) => `
      <div class="row"><div class="main"><div class="title">${esc(e.instrument)}</div>
        <div class="sub" style="white-space:normal">${esc(e.message)}</div></div></div>`).join("")}</div>` : ""}
    ${sectionHeader("Compte")}
    <div class="list">
      <div class="row"><div class="main"><div class="title">Connecté</div></div><div class="detail">${esc(auth.username || "")}</div></div>
      ${passkeyReady() ? (auth.passkeys > 0
        ? `<div class="row"><div class="main"><div class="title">${esc(AncoraPasskey.label())}</div></div><div class="detail">Activé</div></div>`
        : `<button class="row" id="faceid-row"><div class="main"><div class="title" style="font-weight:650">Activer ${esc(AncoraPasskey.label())}</div></div></button>`) : ""}
      <button class="row" id="logout-row"><div class="main"><div class="title destructive">Se déconnecter</div></div></button>
    </div>
    ${sectionFooter("Pour changer de mot de passe, retirer un appareil Face ID ou déconnecter vos téléphones : Ancora sur ordinateur, Administration › Paramètres.")}
    ${sectionHeader("À propos")}
    <div class="list"><div class="row"><div class="main"><div class="title">Ancora</div></div><div class="detail">Version téléphone 1.3</div></div></div>
    ${sectionFooter("La saisie des opérations et l'administration se font dans Ancora sur ordinateur. Ancora n'est pas un outil de conseil en investissement.")}
  `;
  $("mask-toggle").addEventListener("change", async (event) => {
    state.mask = event.target.checked;
    await api("/api/preferences", { method: "PUT", body: JSON.stringify({ mask_amounts: state.mask }) });
    toast(state.mask ? "Montants masqués" : "Montants affichés");
  });
  $("refresh-row").addEventListener("click", startRefresh);
  $("logout-row").addEventListener("click", logout);
  if ($("faceid-row")) $("faceid-row").addEventListener("click", async () => { if (await enablePasskey()) renderSettings(); });
}

// ------------------------------------------------------------------ Actualisation (en arrière-plan)
function setRefreshing(running, progress) {
  state.refreshing = running;
  $("refresh-btn").classList.toggle("spinning", running);
  const el = $("refresh-progress");
  if (el) el.textContent = running ? (progress || "En cours…") : "";
  if (!running) resetPull();
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
  route(true);
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
$("refresh-btn").addEventListener("click", startRefresh);

/* Tirer pour actualiser */
const ptr = $("ptr");
let pullStart = null, pullDistance = 0;
function resetPull() {
  ptr.classList.remove("ready", "loading");
  ptr.style.transition = "opacity .3s, transform .35s cubic-bezier(.3,1.3,.5,1)";
  ptr.style.opacity = 0;
  ptr.style.transform = "translateY(-60px)";
}
window.addEventListener("touchstart", (event) => {
  const allowed = window.scrollY <= 0 && !state.refreshing && !document.body.classList.contains("locked");
  pullStart = allowed ? event.touches[0].clientY : null;
  pullDistance = 0;
}, { passive: true });
window.addEventListener("touchmove", (event) => {
  if (pullStart === null) return;
  pullDistance = Math.max(0, event.touches[0].clientY - pullStart);
  const progress = Math.min(pullDistance / 80, 1);
  ptr.style.transition = "none";
  ptr.style.opacity = progress;
  ptr.style.transform = `translateY(${Math.min(pullDistance, 110) * 0.6 - 30}px) rotate(${pullDistance * 3}deg)`;
  ptr.classList.toggle("ready", pullDistance > 80);
}, { passive: true });
window.addEventListener("touchend", () => {
  if (pullStart === null) return;
  pullStart = null;
  if (pullDistance > 80) {
    ptr.classList.add("loading");
    ptr.style.transition = "transform .3s";
    ptr.style.transform = "translateY(26px)";
    startRefresh();
  } else {
    resetPull();
  }
});

// ------------------------------------------------------------------ Routeur
const ROUTES = [
  [/^#?\/?$/, () => renderPatrimoine(), "patrimoine"],
  [/^#\/marches$/, () => renderMarkets(), "marches"],
  [/^#\/instrument\/(\d+)$/, (m) => renderInstrument(m[1]), "marches"],
  [/^#\/revenus$/, () => renderIncome(), "revenus"],
  [/^#\/reglages$/, () => renderSettings(), "reglages"],
];

let lastHash = null;
async function route(keepPosition = false) {
  if (document.body.classList.contains("locked")) return;
  const hash = location.hash || "#/";
  const [pattern, render, tab] = ROUTES.find(([p]) => p.test(hash)) || ROUTES[0];
  tabbar.querySelectorAll("a").forEach((a) => a.classList.toggle("active", a.dataset.tab === tab));
  placeLens();
  const changed = hash !== lastHash;
  if (changed && !keepPosition) { window.scrollTo(0, 0); view.innerHTML = skeleton(); tabbar.classList.remove("compact"); }
  lastHash = hash;
  try {
    await render(hash.match(pattern));
    if (changed) {
      view.classList.remove("view-enter", "view-push");
      void view.offsetWidth; // relance l'animation
      view.classList.add(hash.startsWith("#/instrument") ? "view-push" : "view-enter");
    }
  } catch (error) {
    if (error.status === 401) return; // l'écran de connexion est déjà affiché
    view.innerHTML = emptyState("Ancora est injoignable", "Vérifiez que l'ordinateur qui héberge Ancora est allumé, puis réessayez.");
  }
}

window.addEventListener("hashchange", () => { navigatedInApp = true; route(); });
boot();
