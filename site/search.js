// Header search: suggestions as you type, from /search.json (every item page on the site).
// Keyboard: arrows move, Enter opens, Escape closes. Without JavaScript the form opens /search/ (A to Z list).
(() => {
  const input = document.getElementById("q");
  const list = document.getElementById("q-list");
  if (!input || !list) return;
  const root = input.form.getAttribute("data-root") || "/";
  let index = null;
  let active = -1;
  // "strawberries" ~ "strawberry", "apples" ~ "apple", "eggs" ~ "egg"
  const one = (w) => (w.endsWith("ies") ? w.slice(0, -3) + "y" : w.length > 3 && w.endsWith("s") && !w.endsWith("ss") ? w.slice(0, -1) : w);
  const norm = (s) => s.toLowerCase().replace(/[^a-z0-9 ]/g, " ").split(/\s+/).filter(Boolean).map(one).join(" ");
  const load = () => index || (index = fetch(root + "search.json").then((r) => r.json()).catch(() => []));

  const close = () => { list.hidden = true; input.setAttribute("aria-expanded", "false"); active = -1; };
  const mark = (i) => {
    [...list.children].forEach((li, n) => li.setAttribute("aria-selected", String(n === i)));
    active = i;
    if (i >= 0) input.setAttribute("aria-activedescendant", list.children[i].id);
  };
  const go = (li) => { if (li) window.location.href = li.dataset.url; };

  async function show() {
    const q = norm(input.value);
    if (!q) return close();
    const items = await load();
    const words = q.split(" ");
    const hits = items
      .map((it) => ({ it, key: norm(it.n + " " + (it.a || "")) }))
      .filter(({ key }) => words.every((w) => key.split(" ").some((k) => k.startsWith(w)) || key.includes(w)))
      .sort((a, b) => (b.key.startsWith(q) - a.key.startsWith(q)) || a.it.n.localeCompare(b.it.n))
      .slice(0, 8);
    list.innerHTML = hits.length ? hits.map(({ it }, n) =>
      `<li role="option" id="q-${n}" data-url="${root}${it.u}"><span class="q-name">${it.n}</span>` +
      `<span class="q-meta">${it.k}</span></li>`).join("")
      : `<li class="q-none" role="option" aria-disabled="true">No match. Try “eggs”, “chicken” or “apples”.</li>`;
    list.hidden = false;
    input.setAttribute("aria-expanded", "true");
    mark(hits.length ? 0 : -1);
  }

  input.addEventListener("focus", load);
  input.addEventListener("input", show);
  input.addEventListener("keydown", (e) => {
    const n = list.querySelectorAll("[data-url]").length;
    if (e.key === "ArrowDown" && n) { e.preventDefault(); mark((active + 1) % n); }
    else if (e.key === "ArrowUp" && n) { e.preventDefault(); mark((active - 1 + n) % n); }
    else if (e.key === "Enter" && active >= 0) { e.preventDefault(); go(list.children[active]); }
    else if (e.key === "Escape") close();
  });
  list.addEventListener("mousedown", (e) => { const li = e.target.closest("[data-url]"); if (li) { e.preventDefault(); go(li); } });
  document.addEventListener("click", (e) => { if (!input.form.contains(e.target)) close(); });

  // the A to Z page: filter its list with ?q=
  const az = document.getElementById("az");
  const q0 = new URLSearchParams(location.search).get("q");
  if (az && q0) {
    input.value = q0;
    const w = norm(q0);
    az.querySelectorAll("li[data-k]").forEach((li) => { li.hidden = !li.dataset.k.includes(w); });
  }
})();
