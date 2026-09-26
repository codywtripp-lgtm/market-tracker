// Produce Price Check: list of this week's prices and a seasonal chart per item.
const MARKETS = [
  { key: "New York", label: "New York", match: (i) => i.type === "terminal" && i.market === "New York" },
  { key: "Los Angeles", label: "Los Angeles", match: (i) => i.type === "terminal" && i.market === "Los Angeles" },
  { key: "Chicago", label: "Chicago", match: (i) => i.type === "terminal" && i.market === "Chicago" },
  { key: "sp", label: "Shipping point", match: (i) => i.type === "shipping point" },
  { key: "retail", label: "Grocery ads", match: (i) => i.type === "retail" },
  { key: "meat", label: "Beef & chicken", match: (i) => i.type === "wholesale" },
];
const STATUSES = [
  { key: "all", label: "All" },
  { key: "cheap", label: "▼ Cheap" },
  { key: "expensive", label: "▲ Expensive" },
];
const ORDER = { cheap: 0, normal: 1, expensive: 2 };
const state = { market: "New York", status: "all", items: [] };

const $ = (id) => document.getElementById(id);
const money = (v) => (v == null ? "—" : v >= 100 ? `$${v.toFixed(0)}` : `$${v.toFixed(2)}`);
const unitShort = (u) => {
  if (!u) return "";
  const known = { "per lb": "/lb", "per each": "/ea", "$/package": "/case", "$/cwt": "/cwt", "cents/lb": "¢/lb" };
  return known[u] || "/" + u.replace(/^\$\//, "");
};
const pct = (v) => (v == null ? "—" : `${v > 0 ? "+" : ""}${v.toFixed(0)}%`);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const tidy = (s) => (!s || s === "N/A" ? "" : s.charAt(0) + s.slice(1).toLowerCase());

function badge(item) {
  if (item.status === "cheap") return `<span class="badge cheap"><span class="dot"></span>▼ Cheap</span>`;
  if (item.status === "expensive") return `<span class="badge expensive"><span class="dot"></span>▲ Expensive</span>`;
  if (item.status === "normal") return `<span class="badge normal">Normal</span>`;
  return `<span class="badge none">Not enough history</span>`;
}

function vsText(item) {
  if (item.vsNorm == null) return "";
  const v = Math.round(item.vsNorm);
  if (v === 0) return "about usual";
  return `${Math.abs(v)}% ${v < 0 ? "below" : "above"} usual`;
}

function title(item) {
  const variety = tidy(item.variety);
  return variety && !item.commodity.toLowerCase().includes(variety.toLowerCase())
    ? `${item.commodity} · ${variety}` : item.commodity;
}

function describe(item) {
  const bits = [item.pack, item.size && item.size !== "N/A" ? item.size : ""].filter(Boolean);
  if (item.type !== "terminal") bits.push(tidy(item.market));
  return bits.join(" · ");
}

function renderChips() {
  $("markets").innerHTML = MARKETS.map((m) =>
    `<button class="chip" aria-pressed="${m.key === state.market}" data-m="${m.key}">${m.label}</button>`).join("");
  $("statuses").innerHTML = STATUSES.map((s) =>
    `<button class="chip" aria-pressed="${s.key === state.status}" data-s="${s.key}">${s.label}</button>`).join("");
}

function renderList() {
  const market = MARKETS.find((m) => m.key === state.market);
  let items = state.items.filter(market.match);
  const counts = { cheap: 0, expensive: 0 };
  items.forEach((i) => { if (i.status in counts) counts[i.status]++; });
  if (state.status !== "all") items = items.filter((i) => i.status === state.status);
  items.sort((a, b) => (ORDER[a.status] ?? 3) - (ORDER[b.status] ?? 3) || (a.vsNorm ?? 0) - (b.vsNorm ?? 0));

  $("summary").textContent = `${counts.cheap} cheap and ${counts.expensive} expensive right now in ${market.label}.`;
  $("list").innerHTML = items.map((i) => `
    <li><button class="item" data-id="${esc(i.id)}">
      <span class="name">${esc(title(i))}</span>
      <span class="right"><span class="price">${money(i.price)}<small>${unitShort(i.unit)}</small></span><br>${badge(i)}</span>
      <span class="detail">${esc(describe(i))}${vsText(i) ? " · " + vsText(i) : ""}</span>
    </button></li>`).join("");
  $("empty").hidden = items.length > 0;
}

// ---- Seasonal chart -------------------------------------------------------

function isoWeek(dateStr) {
  const d = new Date(dateStr + "T00:00:00Z");
  d.setUTCDate(d.getUTCDate() + 4 - (d.getUTCDay() || 7)); // Thursday of this ISO week
  const yearStart = new Date(Date.UTC(d.getUTCFullYear(), 0, 1));
  return { year: d.getUTCFullYear(), week: Math.ceil(((d - yearStart) / 86400000 + 1) / 7) };
}

function quantile(sorted, q) {
  if (!sorted.length) return null;
  const pos = (sorted.length - 1) * q, lo = Math.floor(pos), hi = Math.ceil(pos);
  return sorted[lo] + (sorted[hi] - sorted[lo]) * (pos - lo);
}

function seasonal(history) {
  // history: [[week_start, nominal, real], ...] -> per week-of-year: this year, last year, usual range
  const rows = history.map(([d, nominal, real]) => ({ d, v: real ?? nominal, ...isoWeek(d) }));
  const thisYear = rows.length ? rows[rows.length - 1].year : new Date().getFullYear();
  const byWeek = Array.from({ length: 53 }, (_, i) => ({ week: i + 1, cur: null, last: null, past: [], date: null }));
  for (const r of rows) {
    const w = byWeek[r.week - 1];
    if (r.year === thisYear) { w.cur = r.v; w.date = r.d; }
    else if (r.year === thisYear - 1) { w.last = r.v; w.past.push(r.v); w.lastDate = r.d; }
    else w.past.push(r.v);
  }
  for (const w of byWeek) {
    // smooth the band with neighbouring weeks so it isn't jagged
    const pool = [-1, 0, 1].flatMap((o) => byWeek[(w.week - 1 + o + 53) % 53].past).sort((a, b) => a - b);
    w.lo = pool.length >= 3 ? quantile(pool, 0.25) : null;
    w.hi = pool.length >= 3 ? quantile(pool, 0.75) : null;
  }
  return { thisYear, weeks: byWeek.slice(0, 52) };
}

function drawChart(el, data, unit) {
  // Draw at the real on-screen width so text stays 11px on phones (no viewBox shrinking).
  const W = Math.max(280, Math.round(el.clientWidth || 640)), H = Math.round(Math.min(260, W * 0.62));
  const m = { t: 10, r: 12, b: 26, l: 48 };
  const vals = data.weeks.flatMap((w) => [w.cur, w.last, w.lo, w.hi]).filter((v) => v != null);
  if (!vals.length) { el.innerHTML = `<p class="sub">No history yet.</p>`; return; }
  let lo = Math.min(...vals), hi = Math.max(...vals);
  const pad = (hi - lo) * 0.1 || hi * 0.1 || 1;
  lo = Math.max(0, lo - pad); hi += pad;
  const x = (wk) => m.l + ((wk - 1) / 51) * (W - m.l - m.r);
  const y = (v) => m.t + (1 - (v - lo) / (hi - lo)) * (H - m.t - m.b);
  const line = (key) => {
    let d = "", pen = false;
    for (const w of data.weeks) {
      if (w[key] == null) { pen = false; continue; }
      d += `${pen ? "L" : "M"}${x(w.week).toFixed(1)},${y(w[key]).toFixed(1)}`;
      pen = true;
    }
    return d;
  };
  // band as separate polygons over runs of weeks that have a range
  let band = "", run = [];
  const flush = () => {
    if (run.length > 1) band += `<path d="M${run.map((w) => `${x(w.week)},${y(w.hi)}`).join("L")}L${run.slice().reverse().map((w) => `${x(w.week)},${y(w.lo)}`).join("L")}Z" fill="var(--band)"/>`;
    run = [];
  };
  for (const w of data.weeks) { if (w.lo != null) run.push(w); else flush(); }
  flush();

  const ticks = 4, grid = [];
  for (let i = 0; i <= ticks; i++) {
    const v = lo + ((hi - lo) * i) / ticks;
    grid.push(`<line x1="${m.l}" x2="${W - m.r}" y1="${y(v)}" y2="${y(v)}" stroke="var(--grid)"/>
      <text x="${m.l - 6}" y="${y(v) + 4}" text-anchor="end" font-size="11" fill="var(--muted)">${money(v)}</text>`);
  }
  const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const every = W < 420 ? 2 : 1; // every other month on narrow screens
  const monthTicks = months.map((mo, i) => i % every ? "" :
    `<text x="${x(1 + i * 4.345)}" y="${H - 6}" font-size="11" fill="var(--muted)">${mo}</text>`).join("");

  // end label on the current-year line
  const lastCur = [...data.weeks].reverse().find((w) => w.cur != null);
  const endLabel = lastCur ? `<circle cx="${x(lastCur.week)}" cy="${y(lastCur.cur)}" r="4" fill="var(--series-1)" stroke="var(--surface)" stroke-width="2"/>` : "";

  el.innerHTML = `<svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" role="img" aria-label="Weekly price this year vs last year and the usual range">
    ${grid.join("")}
    ${band}
    <line x1="${m.l}" x2="${W - m.r}" y1="${H - m.b}" y2="${H - m.b}" stroke="var(--axis)"/>
    ${monthTicks}
    <path d="${line("last")}" fill="none" stroke="var(--muted)" stroke-width="2" stroke-dasharray="4 3"/>
    <path d="${line("cur")}" fill="none" stroke="var(--series-1)" stroke-width="2" stroke-linejoin="round"/>
    ${endLabel}
    <line id="xh" y1="${m.t}" y2="${H - m.b}" stroke="var(--axis)" visibility="hidden"/>
    <rect x="${m.l}" y="${m.t}" width="${W - m.l - m.r}" height="${H - m.t - m.b}" fill="transparent" id="hit"/>
  </svg><div class="tip" hidden></div>`;

  const svg = el.querySelector("svg"), tip = el.querySelector(".tip"), xh = el.querySelector("#xh");
  const move = (evt) => {
    const pt = svg.getBoundingClientRect();
    const px = ((evt.clientX - pt.left) / pt.width) * W;
    const wk = Math.min(52, Math.max(1, Math.round(((px - m.l) / (W - m.l - m.r)) * 51) + 1));
    const w = data.weeks[wk - 1];
    xh.setAttribute("x1", x(wk)); xh.setAttribute("x2", x(wk)); xh.setAttribute("visibility", "visible");
    tip.hidden = false;
    tip.innerHTML = `<strong>Week ${wk}${w.date ? " · " + w.date : ""}</strong><br>
      ${data.thisYear}: ${money(w.cur)}${unitShort(unit)}<br>
      ${data.thisYear - 1}: ${money(w.last)}${unitShort(unit)}<br>
      Usual: ${w.lo == null ? "—" : `${money(w.lo)}–${money(w.hi)}`}`;
    const left = (x(wk) / W) * pt.width;
    tip.style.left = `${Math.min(Math.max(0, left - 70), pt.width - 150)}px`;
    tip.style.top = `0px`;
  };
  const leave = () => { tip.hidden = true; xh.setAttribute("visibility", "hidden"); };
  const hit = el.querySelector("#hit");
  hit.addEventListener("pointermove", move);
  hit.addEventListener("pointerdown", move);
  hit.addEventListener("pointerleave", leave);
}

function drawTable(el, data, unit) {
  const rows = data.weeks.filter((w) => w.cur != null || w.last != null).reverse();
  el.innerHTML = `<table><thead><tr><th>Week</th><th>${data.thisYear}</th><th>${data.thisYear - 1}</th><th>Usual range</th></tr></thead><tbody>
    ${rows.map((w) => `<tr><td>${w.week}</td><td>${money(w.cur)}</td><td>${money(w.last)}</td>
      <td>${w.lo == null ? "—" : `${money(w.lo)}–${money(w.hi)}`}</td></tr>`).join("")}
  </tbody></table><p class="note">Prices ${unit || ""}, today's dollars.</p>`;
}

async function openDetail(id) {
  const item = state.items.find((i) => i.id === id);
  if (!item) return;
  $("d-title").textContent = title(item);
  $("d-sub").textContent = [describe(item), item.type === "terminal" ? item.market : ""].filter(Boolean).join(" · ");
  $("d-stats").innerHTML = [
    ["This week", `${money(item.price)}${unitShort(item.unit)}`],
    ["Usual for this week", item.norm == null ? "—" : `${money(item.norm)}${unitShort(item.unit)}`],
    ["Status", badge(item)],
    ["vs 4 weeks ago", pct(item.vs4w)],
    ["vs last year", pct(item.vsYear)],
  ].map(([k, v]) => `<div class="stat"><div class="k">${k}</div><div class="v">${v}</div></div>`).join("");
  $("d-cap").textContent = `Weekly price ${item.unit || ""}`;
  $("d-legend").innerHTML = `<span><i class="sw-line"></i>This year</span><span><i class="sw-last"></i>Last year</span><span><i class="sw-band"></i>Usual range (past years)</span>`;
  $("d-chart").innerHTML = `<p class="sub">Loading…</p>`;
  $("d-table").innerHTML = "";
  $("detail").showModal();
  try {
    const history = await (await fetch(`data/s/${encodeURIComponent(id)}.json`)).json();
    const data = seasonal(history);
    drawChart($("d-chart"), data, item.unit);
    drawTable($("d-table"), data, item.unit);
  } catch (e) {
    $("d-chart").innerHTML = `<p class="sub">Couldn't load history.</p>`;
  }
}

document.addEventListener("click", (e) => {
  const m = e.target.closest("[data-m]"), s = e.target.closest("[data-s]"), it = e.target.closest("[data-id]");
  if (m) { state.market = m.dataset.m; renderChips(); renderList(); }
  else if (s) { state.status = s.dataset.s; renderChips(); renderList(); }
  else if (it) openDetail(it.dataset.id);
});
$("d-close").addEventListener("click", () => $("detail").close());
$("detail").addEventListener("click", (e) => { if (e.target === $("detail")) $("detail").close(); });

(async function init() {
  renderChips();
  try {
    const data = await (await fetch("data/latest.json")).json();
    state.items = data.items;
    $("asof").textContent = data.asOf ? `Week of ${data.asOf}.` : "";
  } catch (e) {
    $("summary").textContent = "Couldn't load prices.";
  }
  renderList();
})();
