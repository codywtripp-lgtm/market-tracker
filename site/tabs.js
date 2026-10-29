// Market tabs (New York / Los Angeles / Chicago): show one market at a time and remember the choice.
// Without JavaScript every tab is a plain link to that market's own page.
(() => {
  const tabs = [...document.querySelectorAll(".tabs [data-tab]")];
  const panels = [...document.querySelectorAll(".panel[data-market]")];
  if (tabs.length < 2 || panels.length < 2) return;
  const show = (key, save) => {
    if (!panels.some((p) => p.dataset.market === key)) return;
    tabs.forEach((t) => t.setAttribute("aria-selected", String(t.dataset.tab === key)));
    panels.forEach((p) => { p.hidden = p.dataset.market !== key; });
    if (save) try { localStorage.setItem("market", key); } catch (e) { /* private mode */ }
  };
  tabs.forEach((t) => t.addEventListener("click", (e) => { e.preventDefault(); show(t.dataset.tab, true); }));
  let saved = null;
  try { saved = localStorage.getItem("market"); } catch (e) { /* private mode */ }
  if (saved) show(saved, false);
})();

// Quality ratings: the reason shows on hover (desktop, via CSS) or on tap (phones); tap elsewhere to close.
(() => {
  const close = (except) => document.querySelectorAll('.ql-btn[aria-expanded="true"]').forEach((b) => {
    if (b !== except) b.setAttribute("aria-expanded", "false");
  });
  document.addEventListener("click", (e) => {
    const b = e.target.closest(".ql-btn");
    close(b);
    if (b) b.setAttribute("aria-expanded", b.getAttribute("aria-expanded") === "true" ? "false" : "true");
  });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") close(null); });
})();

// Grocery list: type to filter the "every item" table.
(() => {
  const box = document.getElementById("find");
  if (!box) return;
  const rows = [...document.querySelectorAll("tr[data-name]")];
  box.addEventListener("input", () => {
    const q = box.value.trim().toLowerCase();
    rows.forEach((r) => { r.hidden = q !== "" && !r.dataset.name.includes(q); });
  });
})();

// Every-item table: sort by item, how the price compares with usual, or quality. Items with no comparison go last.
(() => {
  const table = document.querySelector("table.sortable");
  if (!table) return;
  const body = table.tBodies[0];
  const key = { name: (r) => r.dataset.name, v: (r) => r.dataset.v === "" ? null : +r.dataset.v,
                q: (r) => +r.dataset.q < 0 ? null : -r.dataset.q };  // quality: best first
  table.querySelectorAll("th button[data-sort]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const th = btn.parentElement;
      const dir = th.getAttribute("aria-sort") === "ascending" ? -1 : 1;
      table.querySelectorAll("th[aria-sort]").forEach((t) => t.removeAttribute("aria-sort"));
      th.setAttribute("aria-sort", dir === 1 ? "ascending" : "descending");
      const k = key[btn.dataset.sort];
      [...body.rows].sort((a, b) => {
        const x = k(a), y = k(b);
        if (x === null || y === null) return (x === null) - (y === null);
        return (x < y ? -1 : x > y ? 1 : 0) * dir || a.dataset.name.localeCompare(b.dataset.name);
      }).forEach((r) => body.appendChild(r));
    });
  });
})();
