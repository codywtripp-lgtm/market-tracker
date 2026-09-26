// Produce Price Check — one page: filters on the left, big moves, what's going on, one chart, cheap/expensive list.
"use strict";

const MARKETS = [
  { key: "ny", label: "New York", match: (i) => i.type === "terminal" && i.market === "New York" },
  { key: "la", label: "Los Angeles", match: (i) => i.type === "terminal" && i.market === "Los Angeles" },
  { key: "chi", label: "Chicago", match: (i) => i.type === "terminal" && i.market === "Chicago" },
  { key: "sp", label: "Shipping point", match: (i) => i.type === "shipping point" },
  { key: "retail", label: "Grocery ads", match: (i) => i.type === "retail" },
  { key: "meat", label: "Beef & chicken", match: (i) => i.type === "wholesale" },
];
const RANGES = [
  { key: "3m", label: "3 mo", days: 92 }, { key: "1y", label: "1 yr", days: 366 },
  { key: "5y", label: "5 yr", days: 1827 }, { key: "all", label: "All", days: 1e6 },
];
const VIEWS = [
  { key: "auto", label: "Auto" }, { key: "pct", label: "% vs usual" }, { key: "price", label: "Price" },
];
const MAX_SERIES = 8; // categorical palette has 8 validated slots
const ORDER = { cheap: 0, expensive: 1, normal: 2 };

const state = {
  market: "ny", range: "1y", view: "auto",
  selected: [],            // item keys, in the order added
  slots: {},               // item key -> color slot 1..8 (stable while selected)
  items: [], asOf: "", alerts: [],
  histories: {},           // series id -> rows
};

// ---------- helpers ----------
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const cap = (s) => (!s || s === "N/A" ? "" : s.charAt(0).toUpperCase() + s.slice(1).toLowerCase());
const money = (v) => (v == null ? "—" : v >= 100 ? `$${Math.round(v).toLocaleString()}` : `$${v.toFixed(2)}`);
const pct = (v) => (v == null ? "—" : `${v > 0 ? "+" : ""}${Math.round(v)}%`);
const unitLabel = (u) => ({ "$/package": "/case", "$/cwt": "/cwt", "per lb": "/lb", "$/per lb": "/lb", "$/each": " each" }[u]
  || (u ? " / " + u.replace(/^\$\//, "").replace(/^per /, "") : ""));
const color = (key) => `var(--s${state.slots[key] || 1})`;
const market = () => MARKETS.find((m) => m.key === state.market);

// One "item" per commodity in a market (its best-covered series); for meat, one per cut/grade.
function itemKey(i) {
  if (i.type === "wholesale") return `${i.commodity}: ${cap(i.variety.replace(/\s*\(.*\)$/, ""))}${i.props ? " · " + i.props : ""}`;
  return i.commodity;
}
function itemsInMarket() {
  const best = new Map();
  for (const i of state.items.filter(market().match)) {
    const k = itemKey(i);
    const cur = best.get(k);
    if (!cur || (i.coverage ?? 0) > (cur.coverage ?? 0)) best.set(k, i);
  }
  return [...best.entries()].map(([key, i]) => ({ key, ...i })).sort((a, b) => a.key.localeCompare(b.key));
}
const findItem = (key) => itemsInMarket().find((i) => i.key === key);

function describePack(i) {
  const bits = [cap(i.variety) && !i.commodity.toLowerCase().includes(i.variety.toLowerCase()) && i.type !== "wholesale" ? cap(i.variety) : "",
    i.pack, i.size && i.size !== "N/A" ? i.size : "", i.props && i.type !== "wholesale" ? cap(i.props) : ""];
  if (i.type === "shipping point") bits.push(cap(i.market));
  return bits.filter(Boolean).join(" · ");
}

function badge(i) {
  if (i.status === "cheap") return `<span class="badge cheap">▼ Cheap</span>`;
  if (i.status === "expensive") return `<span class="badge expensive">▲ Expensive</span>`;
  if (i.status === "normal") return `<span class="badge normal">Normal</span>`;
  return `<span class="badge none">New</span>`;
}

// ---------- URL state ----------
function readUrl() {
  const p = new URLSearchParams(location.search);
  if (MARKETS.some((m) => m.key === p.get("m"))) state.market = p.get("m");
  if (RANGES.some((r) => r.key === p.get("r"))) state.range = p.get("r");
  if (VIEWS.some((v) => v.key === p.get("v"))) state.view = p.get("v");
  if (p.get("c")) p.get("c").split("|").filter(Boolean).slice(0, MAX_SERIES).forEach(add);
}
function writeUrl() {
  const p = new URLSearchParams({ m: state.market, r: state.range, v: state.view, c: state.selected.join("|") });
  history.replaceState(null, "", `?${p}`);
}

// ---------- selection ----------
function add(key) {
  if (state.selected.includes(key)) return true;
  if (state.selected.length >= MAX_SERIES) { toast(`Up to ${MAX_SERIES} items at once — take one off first.`); return false; }
  const used = new Set(Object.values(state.slots));
  let slot = 1; while (used.has(slot)) slot++;
  state.slots[key] = slot;
  state.selected.push(key);
  return true;
}
function remove(key) {
  state.selected = state.selected.filter((k) => k !== key);
  delete state.slots[key];
}
function toggle(key) { state.selected.includes(key) ? remove(key) : add(key); update(); }
function only(key) { [...state.selected].forEach(remove); add(key); update(); }
function defaultSelection() {
  // Start with what's moving most vs. usual (falls back to best-covered items).
  const items = itemsInMarket();
  const ranked = [...items].sort((a, b) => Math.abs(b.vsNorm ?? -1) - Math.abs(a.vsNorm ?? -1) || (b.coverage ?? 0) - (a.coverage ?? 0));
  ranked.slice(0, 4).forEach((i) => add(i.key));
}

let toastTimer;
function toast(msg) {
  const t = $("toast"); t.textContent = msg; t.hidden = false;
  clearTimeout(toastTimer); toastTimer = setTimeout(() => (t.hidden = true), 2600);
}

// ---------- filters ----------
function seg(el, options, current, attr) {
  el.innerHTML = options.map((o) =>
    `<button role="radio" aria-checked="${o.key === current}" data-${attr}="${o.key}">${o.label}</button>`).join("");
}
function renderFilters() {
  seg($("f-market"), MARKETS, state.market, "market");
  seg($("f-range"), RANGES, state.range, "range");
  seg($("f-view"), VIEWS, state.view, "view");
  $("view-hint").textContent = "Auto: % vs usual when several items are selected, price when one is.";
  $("f-items").innerHTML = itemsInMarket().map((i) => {
    const on = state.selected.includes(i.key);
    return `<li>
      <label><input type="checkbox" data-toggle="${esc(i.key)}" ${on ? "checked" : ""}>
        <span class="sw" style="background:${on ? color(i.key) : "transparent"}"></span>
        <span class="dot ${i.status === "cheap" || i.status === "expensive" || i.status === "normal" ? i.status : "none"}" title="${esc(i.status)}"></span>
        ${esc(i.key)}</label>
      <button class="link only" data-only="${esc(i.key)}" aria-label="Show only ${esc(i.key)}">only</button>
    </li>`;
  }).join("") || `<li class="hint">No items for this market yet.</li>`;
  $("filter-count").textContent = state.selected.length ? `(${state.selected.length})` : "";
}

// ---------- alerts (backtested early warnings) ----------
const MARKET_KEY = { "New York": "ny", "Los Angeles": "la", "Chicago": "chi" };
function renderAlerts() {
  const here = market().label;
  const terminal = ["ny", "la", "chi"].includes(state.market);
  const mine = terminal ? state.alerts.filter((a) => a.market === here) : state.alerts;
  const elsewhere = terminal ? state.alerts.length - mine.length : 0;
  $("alerts-h").textContent = terminal ? `Alerts · ${here}` : "Alerts";
  const body = mine.map((a) => `<button class="alert" data-alert="${esc(a.market)}|${esc(a.commodity)}">
      <span class="arrow ${a.direction}" aria-hidden="true">${a.direction === "up" ? "▲" : "▼"}</span>
      <span class="h">${esc(a.headline)}</span>
      <span class="e">${esc(a.expect)}</span>
      <span class="r">Track record: ${esc(a.record)}</span></button>`).join("");
  $("alerts-list").innerHTML = (body || `<p class="hint">No alerts for ${esc(here)} right now. Alerts only fire when a signal with a strong 10-year track record is on.</p>`)
    + (elsewhere ? `<p class="hint">${elsewhere} more in other markets — switch market above.</p>` : "");
}
function openAlert(marketName, commodity) {
  const key = MARKET_KEY[marketName];
  if (key && key !== state.market) { state.market = key; }
  [...state.selected].forEach(remove);
  add(commodity);
  update();
  $("chart-h").scrollIntoView({ behavior: "smooth", block: "start" });
}

// ---------- big moves ----------
function renderMoves() {
  const moves = itemsInMarket()
    .filter((i) => (i.vs4w != null && Math.abs(i.vs4w) >= 15) || (i.vsNorm != null && Math.abs(i.vsNorm) >= 25))
    .map((i) => ({ i, size: Math.max(Math.abs(i.vs4w ?? 0), Math.abs(i.vsNorm ?? 0)) }))
    .sort((a, b) => b.size - a.size).slice(0, 3);
  $("moves-h").textContent = `Big moves · ${market().label}`;
  $("moves-list").innerHTML = moves.length ? `<div class="moves">${moves.map(({ i }) => {
    const up = (i.vs4w ?? i.vsNorm ?? 0) > 0;
    const why = [i.vs4w != null ? `${pct(i.vs4w)} in 4 weeks` : "", i.vsNorm != null ? `${pct(i.vsNorm)} vs usual for this time of year` : "",
      i.tone ? `USDA: “${cap(i.tone)}”` : ""].filter(Boolean).join(" · ");
    return `<button class="move" data-only="${esc(i.key)}">
      <span class="arrow ${up ? "up" : "down"}" aria-hidden="true">${up ? "▲" : "▼"}</span>
      <span><strong>${esc(i.key)}</strong> ${money(i.price)}${unitLabel(i.unit)}</span>
      <span class="why">${esc(why)}</span></button>`;
  }).join("")}</div><p class="hint">Tap one to chart it. Predictive alerts are being tested against 10 years of history before they go live.</p>`
    : `<p class="hint">Nothing unusual this week in ${market().label}.</p>`;
}

// ---------- what's going on ----------
function newsLine(i) {
  const parts = [];
  if (i.vsNorm != null) parts.push(Math.abs(i.vsNorm) < 5 ? "about usual for this time of year" : `${Math.abs(Math.round(i.vsNorm))}% ${i.vsNorm > 0 ? "above" : "below"} usual for this time of year`);
  else parts.push("not enough history yet to say what's usual");
  if (i.vs4w != null && Math.abs(i.vs4w) >= 3) parts.push(`${i.vs4w > 0 ? "up" : "down"} ${Math.abs(Math.round(i.vs4w))}% in 4 weeks`);
  else if (i.vs4w != null) parts.push("steady over 4 weeks");
  if (i.tone) parts.push(`USDA says “${cap(i.tone)}”`);
  const f2 = i.forecast && i.forecast["2"];
  if (f2) parts.push(`next 2 weeks: likely ${money(f2[0])}–${money(f2[2])}${unitLabel(i.unit)}`);
  if (i.origins) parts.push(`coming from ${i.origins.split("; ").slice(0, 3).map(cap).join(", ")}`);
  return parts.join("; ") + ".";
}
function renderNews() {
  const sel = state.selected.map(findItem).filter(Boolean);
  $("news").innerHTML = sel.length ? sel.map((i) => `<li>
      <span class="sw" style="background:${color(i.key)}"></span>
      <div><div class="t">${esc(i.key)} · ${money(i.price)}${unitLabel(i.unit)} ${badge(i)}</div>
      <div class="d">${esc(describePack(i))}</div>
      <div class="d">${esc(newsLine(i))}</div></div></li>`).join("")
    : `<li class="hint">Pick items in Filters to see what's going on.</li>`;
}

// ---------- chart ----------
async function history(id) {
  if (!state.histories[id]) {
    state.histories[id] = fetch(`data/s/${encodeURIComponent(id)}.json`).then((r) => r.json()).catch(() => []);
  }
  return state.histories[id];
}

function chartMode(n) {
  if (state.view === "pct") return "pct";
  if (state.view === "price") return n > 1 ? "pct" : "price";
  return n > 1 ? "pct" : "price";
}

let lastChart = null;
async function renderChart() {
  const sel = state.selected.map(findItem).filter(Boolean);
  const mode = chartMode(sel.length);
  const range = RANGES.find((r) => r.key === state.range);
  const cutoff = new Date(Date.now() - range.days * 86400000).toISOString().slice(0, 10);
  $("chart-h").textContent = mode === "pct" ? "Price vs. usual for this time of year" : sel[0] ? `${sel[0].key} price` : "Chart";
  $("chart-sub").textContent = mode === "pct" ? "0% = usual · above the line = pricier than usual" : sel[0] ? `${unitLabel(sel[0].unit).replace(/^\s*\/\s*/, "per ").replace(/^\//, "per ")}, today's dollars` : "";
  $("chart-note").textContent = state.view === "price" && sel.length > 1 ? "Different items can't share a price scale, so several items are shown as % vs usual. Tap “only” to see one item's price." : "";

  const series = await Promise.all(sel.map(async (i) => {
    const rows = (await history(i.id)).filter((r) => r[0] >= cutoff);
    return { item: i, rows };
  }));
  lastChart = { series, mode };
  draw();
}

// Forecast points for a single item in price view, starting at its last actual week.
// Forecasts are in actual dollars; the chart line is in today's dollars (nearly identical for
// recent weeks), so they're scaled by the last week's ratio to join up smoothly.
function forecastPoints(drawn, mode) {
  if (mode !== "price" || drawn.length !== 1) return [];
  const item = drawn[0].item, f = item.forecast || {};
  const last = [...drawn[0].rows].reverse().find((r) => r[1] != null);
  if (!last || !f["1"]) return [];
  const k = (last[2] ?? last[1]) / last[1];
  const addWeeks = (d, n) => new Date(Date.parse(d + "T00:00:00Z") + n * 7 * 86400000).toISOString().slice(0, 10);
  return [{ d: last[0], h: 0, lo: last[2] ?? last[1], mid: last[2] ?? last[1], hi: last[2] ?? last[1] }]
    .concat([1, 2, 3, 4].filter((h) => f[h]).map((h) => ({ d: addWeeks(last[0], h), h, lo: f[h][0] * k, mid: f[h][1] * k, hi: f[h][2] * k })));
}

function draw() {
  const el = $("chart");
  if (!lastChart) return;
  const { series, mode } = lastChart;
  const valueOf = (r) => (mode === "pct" ? r[3] : r[2] ?? r[1]);
  const drawn = series.filter((s) => s.rows.some((r) => valueOf(r) != null));
  const missing = series.filter((s) => !drawn.includes(s)).map((s) => s.item.key);

  // legend (always for >= 2 series; single series gets line + band key)
  $("legend").innerHTML = drawn.length > 1
    ? drawn.map((s) => `<span><i class="ln" style="background:${color(s.item.key)}"></i>${esc(s.item.key)}</span>`).join("") + `<span><i class="zero"></i>Usual</span>`
    : drawn.length === 1 ? `<span><i class="ln" style="background:${color(drawn[0].item.key)}"></i>Weekly price</span>` + (mode === "price" ? `<span><i class="bd"></i>Usual range (past years)</span>` : `<span><i class="zero"></i>Usual</span>`)
      + (forecastPoints(drawn, mode).length ? `<span><i class="fc" style="border-color:${color(drawn[0].item.key)}"></i>Forecast, 80% range</span>` : "") : "";

  if (!drawn.length) {
    el.innerHTML = `<div class="empty-chart">${series.length ? "Not enough history yet to chart these." : "Pick items in Filters to chart them."}</div>`;
    $("table").innerHTML = "";
    return;
  }
  if (missing.length) $("chart-note").textContent = `Not enough history yet: ${missing.join(", ")}.`;

  const W = Math.max(200, Math.round(el.clientWidth)), H = Math.round(Math.min(340, Math.max(220, W * 0.5)));
  const direct = drawn.length <= 4 && W >= 520;
  const m = { t: 12, r: direct ? 110 : 14, b: 26, l: 52 };
  const fc = forecastPoints(drawn, mode);
  const dates = [...new Set(drawn.flatMap((s) => s.rows.map((r) => r[0])).concat(fc.map((p) => p.d)))].sort();
  const t0 = Date.parse(dates[0]), t1 = Date.parse(dates[dates.length - 1]) || t0 + 1;
  const x = (d) => m.l + ((Date.parse(d) - t0) / Math.max(1, t1 - t0)) * (W - m.l - m.r);
  const vals = drawn.flatMap((s) => s.rows.flatMap((r) => mode === "price" ? [valueOf(r), r[4], r[5]] : [valueOf(r)]))
    .concat(fc.flatMap((p) => [p.lo, p.hi])).filter((v) => v != null);
  let lo = Math.min(...vals, mode === "pct" ? 0 : Infinity), hi = Math.max(...vals, mode === "pct" ? 0 : -Infinity);
  const pad = (hi - lo) * 0.08 || 1; lo -= pad; hi += pad;
  if (mode === "price") lo = Math.max(0, lo);
  // round tick values (…, 10, 20, 25, 50, 100 …) and snap the scale to them
  const raw = (hi - lo) / 4, mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((f) => f * mag).find((s) => s >= raw) || 10 * mag;
  lo = Math.floor(lo / step) * step; hi = Math.ceil(hi / step) * step;
  const y = (v) => m.t + (1 - (v - lo) / (hi - lo)) * (H - m.t - m.b);
  const fmt = (v) => (mode === "pct" ? (Math.abs(v) < 1e-9 ? "0%" : pct(v)) : money(v));

  const path = (s) => {
    let d = "", pen = false;
    for (const r of s.rows) {
      const v = valueOf(r);
      if (v == null) { pen = false; continue; }
      d += `${pen ? "L" : "M"}${x(r[0]).toFixed(1)},${y(v).toFixed(1)}`; pen = true;
    }
    return d;
  };
  let band = "";
  if (mode === "price" && drawn.length === 1) {
    const rs = drawn[0].rows; let run = [];
    const flush = () => { if (run.length > 1) band += `<path d="M${run.map((r) => `${x(r[0])},${y(r[5])}`).join("L")}L${run.slice().reverse().map((r) => `${x(r[0])},${y(r[4])}`).join("L")}Z" fill="var(--band)"/>`; run = []; };
    for (const r of rs) { if (r[4] != null) run.push(r); else flush(); } flush();
  }

  // forecast: 80% range + dashed middle line, continuing from the last actual week
  let fcSvg = "";
  if (fc.length) {
    const c = color(drawn[0].item.key), start = fc[0];
    const pts = fc.slice(1);
    fcSvg = `<path d="M${x(start.d)},${y(start.mid)}${pts.map((p) => `L${x(p.d)},${y(p.hi)}`).join("")}` +
      `${pts.slice().reverse().map((p) => `L${x(p.d)},${y(p.lo)}`).join("")}Z" fill="${c}" opacity="0.15"/>` +
      `<path d="M${fc.map((p) => `${x(p.d)},${y(p.mid)}`).join("L")}" fill="none" stroke="${c}" stroke-width="2" stroke-dasharray="5 4"/>` +
      `<line x1="${x(start.d)}" x2="${x(start.d)}" y1="${m.t}" y2="${H - m.b}" stroke="var(--axis)" stroke-dasharray="2 3"/>` +
      `<text x="${x(start.d) + 4}" y="${m.t + 10}" font-size="11" fill="var(--muted)">forecast</text>`;
  }
  const grid = [];
  for (let v = lo; v <= hi + step / 2; v += step) {
    grid.push(`<line x1="${m.l}" x2="${W - m.r}" y1="${y(v)}" y2="${y(v)}" stroke="var(--grid)"/>
      <text x="${m.l - 6}" y="${y(v) + 4}" text-anchor="end" font-size="11" fill="var(--muted)">${fmt(v)}</text>`);
  }
  const xt = [], nx = W < 480 ? 3 : 5;
  for (let i = 0; i <= nx; i++) {
    const t = new Date(t0 + ((t1 - t0) * i) / nx);
    const lbl = (t1 - t0) > 400 * 86400000 ? t.toLocaleDateString(undefined, { month: "short", year: "2-digit" }) : t.toLocaleDateString(undefined, { month: "short", day: "numeric" });
    xt.push(`<text x="${x(t.toISOString().slice(0, 10))}" y="${H - 6}" font-size="11" fill="var(--muted)" text-anchor="${i === 0 ? "start" : i === nx ? "end" : "middle"}">${lbl}</text>`);
  }
  const zero = mode === "pct" ? `<line x1="${m.l}" x2="${W - m.r}" y1="${y(0)}" y2="${y(0)}" stroke="var(--muted)" stroke-dasharray="4 3"/>` : "";

  // direct end labels, nudged apart so they don't collide
  let labels = "";
  if (direct) {
    const ends = drawn.map((s) => { const r = [...s.rows].reverse().find((q) => valueOf(q) != null); return { s, yy: y(valueOf(r)), r }; })
      .sort((a, b) => a.yy - b.yy);
    for (let i = 1; i < ends.length; i++) ends[i].yy = Math.max(ends[i].yy, ends[i - 1].yy + 14);
    labels = ends.map((e) => `<text x="${W - m.r + 8}" y="${e.yy + 4}" font-size="11" fill="var(--ink-2)">${esc(e.s.item.key.length > 16 ? e.s.item.key.slice(0, 15) + "…" : e.s.item.key)}</text>`).join("");
  }
  const endDots = drawn.map((s) => { const r = [...s.rows].reverse().find((q) => valueOf(q) != null);
    return `<circle cx="${x(r[0])}" cy="${y(valueOf(r))}" r="4" fill="${color(s.item.key)}" stroke="var(--surface)" stroke-width="2"/>`; }).join("");

  el.innerHTML = `<svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc($("chart-h").textContent)}">
    ${grid.join("")}${band}
    <line x1="${m.l}" x2="${W - m.r}" y1="${H - m.b}" y2="${H - m.b}" stroke="var(--axis)"/>
    ${zero}${xt.join("")}
    ${fcSvg}
    ${drawn.map((s) => `<path d="${path(s)}" fill="none" stroke="${color(s.item.key)}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>`).join("")}
    ${endDots}${labels}
    <line class="xh" y1="${m.t}" y2="${H - m.b}" stroke="var(--axis)" visibility="hidden"/>
    <rect class="hit" x="${m.l}" y="0" width="${W - m.l - m.r}" height="${H}" fill="transparent"/>
  </svg><div class="tip" hidden></div>`;

  // crosshair + tooltip (all series at the nearest date)
  const svg = el.querySelector("svg"), tip = el.querySelector(".tip"), xh = el.querySelector(".xh");
  const byDate = drawn.map((s) => new Map(s.rows.map((r) => [r[0], r])));
  const move = (evt) => {
    const box = svg.getBoundingClientRect();
    const px = evt.clientX - box.left;
    let best = dates[0], bd = Infinity;
    for (const d of dates) { const dd = Math.abs(x(d) - px); if (dd < bd) { bd = dd; best = d; } }
    xh.setAttribute("x1", x(best)); xh.setAttribute("x2", x(best)); xh.setAttribute("visibility", "visible");
    const rows = drawn.map((s, k) => ({ s, r: byDate[k].get(best) })).filter((o) => o.r && valueOf(o.r) != null)
      .sort((a, b) => valueOf(b.r) - valueOf(a.r));
    const f = fc.find((p) => p.d === best && p.h > 0);
    tip.innerHTML = `<strong>Week of ${new Date(best + "T00:00:00").toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })}</strong>` +
      (f ? `<div class="trow"><span>Forecast</span><span>${money(f.mid)}</span></div><div class="trow"><span>80% range</span><span>${money(f.lo)}–${money(f.hi)}</span></div>` : "") +
      rows.map(({ s, r }) => `<div class="trow"><span><i style="background:${color(s.item.key)}"></i>${esc(s.item.key)}</span><span>${fmt(valueOf(r))}</span></div>`).join("") +
      (mode === "price" && rows[0] && rows[0].r[4] != null ? `<div class="trow"><span>Usual</span><span>${money(rows[0].r[4])}–${money(rows[0].r[5])}</span></div>` : "");
    tip.hidden = false;
    const tw = tip.offsetWidth;
    tip.style.left = `${Math.min(Math.max(0, x(best) + 12), W - tw)}px`;
  };
  const hit = el.querySelector(".hit");
  hit.addEventListener("pointermove", move);
  hit.addEventListener("pointerdown", move);
  hit.addEventListener("pointerleave", () => { tip.hidden = true; xh.setAttribute("visibility", "hidden"); });

  // table view
  const recent = dates.slice(-26).reverse();
  $("table").innerHTML = `<div class="table-wrap"><table><thead><tr><th>Week of</th>${drawn.map((s) => `<th>${esc(s.item.key)}</th>`).join("")}</tr></thead><tbody>
    ${recent.map((d) => `<tr><td>${d}</td>${drawn.map((s, k) => { const r = byDate[k].get(d); return `<td>${r && valueOf(r) != null ? fmt(valueOf(r)) : "—"}</td>`; }).join("")}</tr>`).join("")}
    </tbody></table></div><p class="hint">Last 26 weeks shown.</p>`;
}

// ---------- list ----------
function renderList() {
  const items = itemsInMarket().sort((a, b) => (ORDER[a.status] ?? 3) - (ORDER[b.status] ?? 3) || Math.abs(b.vsNorm ?? 0) - Math.abs(a.vsNorm ?? 0));
  $("list-h").textContent = `Cheap & expensive right now · ${market().label}`;
  $("list").innerHTML = items.map((i) => {
    const on = state.selected.includes(i.key);
    return `<li><button class="row" aria-pressed="${on}" data-toggle="${esc(i.key)}">
      <span class="sw" style="background:${on ? color(i.key) : "transparent"}"></span>
      <span class="name">${esc(i.key)}</span>
      <span class="right">${money(i.price)}<small>${unitLabel(i.unit)}</small><br>${badge(i)}</span>
      <span class="det">${esc(describePack(i))}${i.vsNorm != null ? ` · ${pct(i.vsNorm)} vs usual` : ""}</span>
    </button></li>`;
  }).join("");
}

// ---------- wiring ----------
function update() {
  renderFilters(); renderAlerts(); renderMoves(); renderNews(); renderList(); renderChart(); writeUrl();
}
function setMarket(key) {
  if (key === state.market) return;
  state.market = key;
  [...state.selected].forEach(remove);
  defaultSelection();
  update();
}
function openSheet(open) {
  $("filters").classList.toggle("open", open);
  $("scrim").hidden = !open;
  $("open-filters").setAttribute("aria-expanded", String(open));
}

document.addEventListener("click", (e) => {
  const t = e.target.closest("[data-market],[data-range],[data-view],[data-only],[data-toggle],[data-alert]");
  if (!t) return;
  if (t.dataset.alert) { const [mk, c] = t.dataset.alert.split("|"); openAlert(mk, c); }
  else if (t.dataset.market) setMarket(t.dataset.market);
  else if (t.dataset.range) { state.range = t.dataset.range; update(); }
  else if (t.dataset.view) { state.view = t.dataset.view; update(); }
  else if (t.dataset.only) { only(t.dataset.only); if (t.classList.contains("move")) $("chart-h").scrollIntoView({ behavior: "smooth", block: "start" }); }
  else if (t.dataset.toggle && t.tagName !== "INPUT") toggle(t.dataset.toggle);
});
document.addEventListener("change", (e) => { if (e.target.dataset.toggle) toggle(e.target.dataset.toggle); });
$("clear").addEventListener("click", () => { [...state.selected].forEach(remove); update(); });
$("open-filters").addEventListener("click", () => openSheet(true));
$("close-filters").addEventListener("click", () => openSheet(false));
$("scrim").addEventListener("click", () => openSheet(false));
document.addEventListener("keydown", (e) => { if (e.key === "Escape") openSheet(false); });
let resizeTimer;
window.addEventListener("resize", () => { clearTimeout(resizeTimer); resizeTimer = setTimeout(draw, 150); });

(async function init() {
  try {
    const data = await (await fetch("data/latest.json")).json();
    state.items = data.items; state.asOf = data.asOf;
    $("asof").textContent = data.asOf ? `Week of ${new Date(data.asOf + "T00:00:00").toLocaleDateString(undefined, { month: "long", day: "numeric", year: "numeric" })}.` : "";
  } catch (e) {
    $("news").innerHTML = `<li class="hint">Couldn't load prices.</li>`;
  }
  try {
    state.alerts = (await (await fetch("data/alerts.json")).json()).alerts || [];
  } catch (e) {
    state.alerts = [];
  }
  readUrl();
  state.selected.filter((k) => !itemsInMarket().some((i) => i.key === k)).forEach(remove);
  if (!state.selected.length) defaultSelection();
  update();
})();
