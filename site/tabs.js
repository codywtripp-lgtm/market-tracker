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
