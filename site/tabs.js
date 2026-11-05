// Market links: remember the market a buyer picks, and open it next time on pages that default to New York.
(() => {
  const nav = document.querySelector(".mkts");
  if (!nav) return;
  nav.addEventListener("click", (e) => {
    const a = e.target.closest("a[data-m]");
    if (a) try { localStorage.setItem("market", a.dataset.m); } catch (err) { /* private mode */ }
  });
  if (!("remember" in nav.dataset)) return;
  let saved = null;
  try { saved = localStorage.getItem("market"); } catch (e) { /* private mode */ }
  const link = saved && nav.querySelector(`a[data-m="${saved}"]:not([aria-current])`);
  if (link) location.replace(link.href);
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
